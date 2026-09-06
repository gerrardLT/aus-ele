"""跨 worker in-flight 去重的语义锁定（P0.7 第 6 站点，2026-09-05）。

外置前的缺陷：``_ANALYSIS_INFLIGHT`` 是模块级 dict，去重只在单 worker 内成立；
GUNICORN_WORKERS>1 时同一份昂贵分析（20 年现金流 + 蒙特卡洛 + co-optimization MILP）
会被并发打到不同 worker 各算一遍。

怎么在没有多进程的情况下测出这个增量：进程内表每台一份，所以「本表的 ``key-1`` 为空
但共享 store 里 ``key-1`` 已被认领」就是另一台 worker 正在算的真实拓扑；认领放在
注入的共享 store 里（不连本机 Redis，避免测试结果取决于环境）。
"""

import threading
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths, offline_state_store

ensure_repo_import_paths()

import routes.investment_routes as inv  # noqa: E402
from shared_state import reset_state_store_for_tests  # noqa: E402


class InflightClaimTests(unittest.TestCase):
    def setUp(self):
        # 一个 store 实例 = 所有 worker 共享的那个 Redis 视图
        self.store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)
        # 清空进程内表 = 一台刚启动、手上没有登记的 worker；测试结束后原样还原
        table_guard = mock.patch.dict(inv._ANALYSIS_INFLIGHT, {}, clear=True)
        table_guard.start()
        self.addCleanup(table_guard.stop)

    # --- 同 worker 快路径（原有行为必须保留，Event 比轮询便宜）-------------

    def test_first_request_becomes_owner(self):
        entry, kind = inv._acquire_inflight_entry("key-1")
        self.assertEqual(kind, "owner")
        self.assertIsNotNone(entry)
        self.assertIn("event", entry)

    def test_second_request_same_worker_receives_same_entry_object(self):
        first, _ = inv._acquire_inflight_entry("key-1")
        second, kind = inv._acquire_inflight_entry("key-1")
        self.assertEqual(kind, "local")
        # 必须是同一个对象：waiter 靠它拿属主写回的 response/error
        self.assertIs(second, first)

    def test_different_keys_are_separate_owners(self):
        a, _ = inv._acquire_inflight_entry("key-a")
        b, kind_b = inv._acquire_inflight_entry("key-b")
        self.assertEqual(kind_b, "owner")
        self.assertIsNot(a, b)

    # --- 跨 worker：这才是本轮修的洞 ---------------------------------------

    def test_other_worker_holding_claim_makes_us_remote_waiter(self):
        """另一台已在算时，本机不能也开算（原实现完全挡不住）。"""
        self.assertIsNotNone(self.store.acquire_claim(inv._INFLIGHT_CLAIM_SCOPE, "key-1", 60))
        entry, kind = inv._acquire_inflight_entry("key-1")
        self.assertEqual(kind, "remote")
        self.assertIsNone(entry)
        # 关键：本机没有登记属主，否则会以为"有人在算"而永远等一个不存在的 Event
        self.assertNotIn("key-1", inv._ANALYSIS_INFLIGHT)

    def test_owner_releasing_claim_lets_next_worker_take_over(self):
        entry, kind = inv._acquire_inflight_entry("key-1")
        self.assertEqual(kind, "owner")
        inv._release_inflight_entry("key-1", entry)
        # 认领已释放：另一台现在应当能拿到属主身份，而不是永远等一个不存在的人
        self.assertFalse(self.store.is_claimed(inv._INFLIGHT_CLAIM_SCOPE, "key-1"))
        self.assertEqual(inv._acquire_inflight_entry("key-1")[1], "owner")

    def test_takeover_after_owner_vanishes_registers_locally(self):
        token = self.store.acquire_claim(inv._INFLIGHT_CLAIM_SCOPE, "key-1", 60)
        # 属主崩溃 / 认领被 TTL 回收
        self.store.release_claim(inv._INFLIGHT_CLAIM_SCOPE, "key-1", token)
        entry, kind = inv._claim_inflight_after_owner_loss("key-1")
        self.assertEqual(kind, "owner")
        self.assertIsNotNone(entry["claim_token"])

    def test_takeover_defers_to_local_owner(self):
        original, _ = inv._acquire_inflight_entry("key-1")
        rival, kind = inv._claim_inflight_after_owner_loss("key-1")
        self.assertEqual(kind, "local")
        self.assertIs(rival, original)

    # --- 释放路径的三个陷阱 -------------------------------------------------

    def test_release_does_not_evict_another_requests_entry(self):
        """按对象身份删除：无条件 pop 会把重建者的登记抹掉，使其 waiter 永久干等。"""
        stale = {"event": threading.Event(), "response": None, "error": None, "claim_token": None}
        replacement = {"event": threading.Event(), "response": None, "error": None, "claim_token": None}
        inv._ANALYSIS_INFLIGHT["key-1"] = stale
        inv._ANALYSIS_INFLIGHT["key-1"] = replacement
        inv._release_inflight_entry("key-1", stale)
        self.assertIs(inv._ANALYSIS_INFLIGHT["key-1"], replacement)

    def test_release_sets_event_so_waiter_wakes_even_on_error(self):
        entry, _ = inv._acquire_inflight_entry("key-1")
        entry["error"] = RuntimeError("boom")
        inv._release_inflight_entry("key-1", entry)
        self.assertTrue(entry["event"].is_set())

    def test_release_with_foreign_token_keeps_claim(self):
        """拿别人的 token 去 release 不该生效 —— 否则会把易主后的锁抢走。"""
        entry, _ = inv._acquire_inflight_entry("key-1")
        real_token = entry["claim_token"]
        entry["claim_token"] = "someone-elses-token"
        inv._release_inflight_entry("key-1", entry)
        self.assertTrue(self.store.is_claimed(inv._INFLIGHT_CLAIM_SCOPE, "key-1"))
        entry["claim_token"] = real_token
        inv._release_inflight_entry("key-1", entry)
        self.assertFalse(self.store.is_claimed(inv._INFLIGHT_CLAIM_SCOPE, "key-1"))

    # --- 认领 TTL 是个真实约束，不能被静默改小 ------------------------------

    def test_claim_ttl_exceeds_wait_timeout(self):
        """TTL 小于正常计算耗时 = 属主还在算而认领先过期，去重直接失效。"""
        self.assertGreater(
            inv._INFLIGHT_CLAIM_TTL_SECONDS,
            inv._ANALYSIS_INFLIGHT_WAIT_TIMEOUT_SECONDS,
        )


class RemoteWaitTests(unittest.TestCase):
    """等待路径的三种结局，各自的取舍不同，必须分开锁。"""

    def setUp(self):
        self.store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)
        table_guard = mock.patch.dict(inv._ANALYSIS_INFLIGHT, {}, clear=True)
        table_guard.start()
        self.addCleanup(table_guard.stop)

    def test_returns_result_once_shared_cache_has_it(self):
        self.store.acquire_claim(inv._INFLIGHT_CLAIM_SCOPE, "key-1", 60)
        expected = {"metrics": {"npv": 123}}
        with mock.patch.object(inv, "_analysis_cache_lookup", return_value=expected) as lookup:
            got = inv._await_remote_analysis(
                inflight_key="key-1", scope="s", payload={"p": 1}, data_version="v1"
            )
        self.assertEqual(got, expected)
        lookup.assert_called_once()

    def test_gives_up_immediately_when_owner_vanished(self):
        """属主崩溃后不能干等 60s：立即让调用方接管自算。"""
        with mock.patch.object(inv, "_analysis_cache_lookup", return_value=None):
            started = threading.Event()
            with mock.patch.object(inv.time, "sleep", side_effect=lambda _s: started.set()):
                got = inv._await_remote_analysis(
                    inflight_key="nobody-holds-this", scope="s", payload={}, data_version="v"
                )
        self.assertIsNone(got)

    def test_still_claimed_at_timeout_raises_503_not_duplicate_compute(self):
        """超时但属主仍在算 → 503（沿用原语义）。

        刻意不降级为"那我自己算"：一次超过等待窗口的慢分析会把所有并发请求转成
        重复计算，负载反而被放大成 O(请求数 × 单次成本)。
        """
        from fastapi import HTTPException

        self.store.acquire_claim(inv._INFLIGHT_CLAIM_SCOPE, "key-1", 60)
        clock = iter([0.0, 10_000.0])
        with mock.patch.object(inv, "_analysis_cache_lookup", return_value=None), \
                mock.patch.object(inv.time, "monotonic", side_effect=lambda: next(clock)), \
                mock.patch.object(inv.time, "sleep"):
            with self.assertRaises(HTTPException) as ctx:
                inv._await_remote_analysis(
                    inflight_key="key-1", scope="s", payload={}, data_version="v"
                )
        self.assertEqual(ctx.exception.status_code, 503)


if __name__ == "__main__":
    unittest.main()
