"""shared_state 的语义锁定测试（P0.7，2026-09-05）。

为什么这些测试值得存在：P0.7 把六处进程内状态外置，而外置的价值全部体现在
"多 worker / Redis 挂掉"这两种测试环境里不存在的情况下。所以断言必须针对
**语义**（限流不被放大、降级不放行、认领只有一个属主），而不是针对 Redis 命令。

全部用 ``offline_state_store()``：本机有没有起 Redis 不该改变限流语义，否则测试
变成环境依赖，而且在共享 Redis 上会互相污染计数窗口。需要"两个 worker"的场景
用两个独立 store 实例模拟 —— 这正是多进程的真实形态（各自一份进程内状态）。
"""

import os
import time
import unittest
from unittest import mock

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths, offline_state_store

ensure_repo_import_paths()

from shared_state import SlidingWindowLimiter, reset_state_store_for_tests  # noqa: E402

from routes.account_routes import (  # noqa: E402
    _INVITE_ACCEPT_WINDOW_SECONDS,
    check_invite_accept_rate_limit,
)


class SlidingWindowLimiterTests(unittest.TestCase):
    """回落限流器本身 —— 它是 Redis 挂掉时唯一还在把关的东西。"""

    def test_allows_up_to_limit_then_blocks(self):
        limiter = SlidingWindowLimiter()
        for _ in range(5):
            allowed, _retry = limiter.register("k", limit=5, window_seconds=60)
            self.assertTrue(allowed)
        allowed, retry_after = limiter.register("k", limit=5, window_seconds=60)
        self.assertFalse(allowed)
        self.assertGreater(retry_after, 0)

    def test_over_limit_attempt_does_not_extend_window(self):
        """撞限的那次不计数：否则持续重试会把窗口无限往后推，越限越罚得久。"""
        limiter = SlidingWindowLimiter()
        base = 1_000_000.0
        for _ in range(3):
            limiter.register("k", limit=3, window_seconds=60, now=base)
        # 在 base+30 连续撞限五次（都不该进窗口）
        for i in range(5):
            allowed, _ = limiter.register("k", limit=3, window_seconds=60, now=base + 30 + i)
            self.assertFalse(allowed)
        # 窗口按首次计数时刻起算：base+61 就该放行，而不是 base+30+5+60
        allowed, _ = limiter.register("k", limit=3, window_seconds=60, now=base + 61)
        self.assertTrue(allowed)

    def test_window_slides_per_attempt(self):
        limiter = SlidingWindowLimiter()
        base = 2_000_000.0
        limiter.register("k", limit=2, window_seconds=60, now=base)
        limiter.register("k", limit=2, window_seconds=60, now=base + 40)
        # 最早一次已过期，但 40 与 50 两次仍在窗口内 → 拒绝
        allowed, _ = limiter.register("k", limit=2, window_seconds=60, now=base + 50)
        self.assertFalse(allowed)
        # 61 时只剩 base+50 一次 → 放行
        allowed, _ = limiter.register("k", limit=2, window_seconds=60, now=base + 61)
        self.assertTrue(allowed)

    def test_limit_zero_or_negative_means_no_limit(self):
        limiter = SlidingWindowLimiter()
        for limit in (0, -1):
            for _ in range(50):
                allowed, _ = limiter.register("k", limit=limit, window_seconds=60)
                self.assertTrue(allowed)

    def test_key_count_is_bounded(self):
        """回落实现不能有内存泄漏：原 _login_attempts 在失败路径上从不回收键。"""
        limiter = SlidingWindowLimiter(max_keys=8)
        for i in range(200):
            limiter.register(f"email-{i}@x.com", limit=5, window_seconds=60)
        self.assertLessEqual(len(limiter._windows), 8)

    def test_isolation_between_keys(self):
        limiter = SlidingWindowLimiter()
        for _ in range(5):
            limiter.register("a", limit=5, window_seconds=60)
        allowed, _ = limiter.register("b", limit=5, window_seconds=60)
        self.assertTrue(allowed)


class FallbackMustNotFailOpenTests(unittest.TestCase):
    """核心安全性质：Redis 不可用 ≠ 不限流。"""

    def setUp(self):
        self.store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)

    def test_register_attempt_enforces_limit_without_redis(self):
        for _ in range(3):
            allowed, _ = self.store.register_attempt("s", "k", limit=3, window_seconds=60)
            self.assertTrue(allowed)
        allowed, _ = self.store.register_attempt("s", "k", limit=3, window_seconds=60)
        self.assertFalse(allowed)

    def test_failing_redis_client_falls_back_instead_of_raising(self):
        """Redis 抛异常时必须回落，而不是把异常冒到请求链路（那才是真事故）。"""

        class _ExplodingCache:
            prefix = "boom"

            def _get_client(self):
                raise RuntimeError("connection refused")

            def _record_failure(self):
                pass

            def _full_key(self, scope, key):
                return f"{scope}:{key}"

            def get_json(self, scope, key):
                return None

            def set_json(self, scope, key, value, ttl_seconds):
                pass

        from shared_state import SharedStateStore

        store = SharedStateStore(cache=_ExplodingCache())
        for _ in range(2):
            allowed, _ = store.register_attempt("s", "k", limit=2, window_seconds=60)
            self.assertTrue(allowed)
        allowed, _ = store.register_attempt("s", "k", limit=2, window_seconds=60)
        self.assertFalse(allowed)


    def test_malformed_redis_url_degrades_instead_of_500(self):
        """用真实 RedisResponseCache + 畸形 URL，而不是桩。

        为什么必须是真实实现：``redis.Redis.from_url`` 在构造阶段就抛，而既有熔断
        只统计命令执行失败 —— 桩测不出这条路径。拼错一个 REDIS_URL 若未被兜住，
        后果是每个经过限流/缓存的端点都 500（比「没有跨 worker 限流」严重得多）。
        """
        from shared_state import SharedStateStore

        with mock.patch.dict(os.environ, {"REDIS_URL": "not-a-valid-redis-scheme://x"}):
            store = SharedStateStore()
            for _ in range(2):
                allowed, _ = store.register_attempt("s", "k", limit=2, window_seconds=60)
                self.assertTrue(allowed)
            self.assertFalse(store.register_attempt("s", "k", limit=2, window_seconds=60)[0])
            # 缓存原语同样不能抛
            store.remember("s", "k", {"v": 1}, 60)
            self.assertEqual(store.recall("s", "k"), {"v": 1})
            # 构造失败已计入熔断：后续调用应直接短路，不再反复尝试建连
            self.assertTrue(store._cache._is_circuit_open())


class TwoWorkerSimulationTests(unittest.TestCase):
    """两个独立 store 实例 = 两个 worker 的进程内状态。

    这组断言的是外置**之前**的行为缺陷：证明了"为什么必须外置"。当 Redis 可用时
    两个 store 会看到同一个窗口；离线时它们各自计数 —— 所以必须同时断言"限流值
    按 worker 数放大"这一可观测后果，避免将来有人把回落当成等价方案。
    """

    def test_per_worker_windows_do_not_share_counts(self):
        worker_a = offline_state_store()
        worker_b = offline_state_store()
        # 各自允许 5 次：合计 10 次，说明单靠进程内限流挡不住分布式爆破
        for _ in range(5):
            self.assertTrue(worker_a.register_attempt("login_rl", "e@x.com", limit=5, window_seconds=60)[0])
        for _ in range(5):
            self.assertTrue(worker_b.register_attempt("login_rl", "e@x.com", limit=5, window_seconds=60)[0])
        # 而每台内部第 6 次仍被拒 —— 回落是"打折"，不是"失效"
        self.assertFalse(worker_a.register_attempt("login_rl", "e@x.com", limit=5, window_seconds=60)[0])

    def test_scopes_do_not_interfere(self):
        store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)
        for _ in range(2):
            store.register_attempt("login_rl", "same-key", limit=2, window_seconds=60)
        # 另一个 scope 用同样的 key 不应被已耗尽的窗口挡住
        allowed, _ = store.register_attempt("bootstrap_rl", "same-key", limit=2, window_seconds=60)
        self.assertTrue(allowed)


class CacheSemanticsTests(unittest.TestCase):
    def setUp(self):
        self.store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)

    def test_recall_returns_none_before_write(self):
        self.assertIsNone(self.store.recall("s", "missing"))

    def test_remember_then_recall(self):
        self.store.remember("s", "k", {"v": 1}, 60)
        self.assertEqual(self.store.recall("s", "k"), {"v": 1})

    def test_entry_expires_after_ttl(self):
        self.store.remember("s", "k", [1, 2], ttl_seconds=1)
        self.assertIsNotNone(self.store.recall("s", "k"))
        # 直接改影子到期时刻，避免让测试睡一秒
        full_key = self.store._full_key("s", "k")
        with self.store._local_cache_guard:
            value, _expires = self.store._local_cache[full_key]
            self.store._local_cache[full_key] = (value, time.time() - 1)
        self.assertIsNone(self.store.recall("s", "k"))

    def test_multiple_keys_in_one_scope_all_survive(self):
        """回归锁定：初版影子缓存按 scope 单槽存，多 key 场景等于没缓存。"""
        for i in range(5):
            self.store.remember("coopt_result", f"key-{i}", {"i": i}, 60)
        got = [self.store.recall("coopt_result", f"key-{i}") for i in range(5)]
        self.assertEqual(got, [{"i": i} for i in range(5)])

    def test_eviction_drops_earliest_expiring_first(self):
        original_max = 256
        import shared_state

        shared_state._LOCAL_CACHE_MAX_ENTRIES = 3
        self.addCleanup(setattr, shared_state, "_LOCAL_CACHE_MAX_ENTRIES", original_max)
        for i in range(6):
            self.store.remember("s", f"k{i}", {"i": i}, ttl_seconds=100 + i)
        survivors = sorted(self.store.keys("s"))
        self.assertLessEqual(len(survivors), 4)
        # 最后写入（到期最晚）必须还在：淘汰的是"最没用"的，不是"最老插入"的
        self.assertIn("k5", survivors)

    def test_forget_removes_entry(self):
        self.store.remember("s", "k", 1, 60)
        self.store.forget("s", "k")
        self.assertIsNone(self.store.recall("s", "k"))

    def test_reset_for_tests_clears_everything(self):
        self.store.remember("s", "k", 1, 60)
        self.store.register_attempt("s", "rate", limit=1, window_seconds=60)
        self.store.reset_for_tests()
        self.assertIsNone(self.store.recall("s", "k"))
        self.assertTrue(self.store.register_attempt("s", "rate", limit=1, window_seconds=60)[0])


class ClaimTests(unittest.TestCase):
    """认领锁：in-flight 去重的正确性根基 —— 只能有一个属主。"""

    def setUp(self):
        self.store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)

    def test_first_claim_wins_and_second_loses(self):
        token = self.store.acquire_claim("inflight", "key-a", 60)
        self.assertIsNotNone(token)
        self.assertIsNone(self.store.acquire_claim("inflight", "key-a", 60))

    def test_different_keys_are_independent(self):
        self.assertIsNotNone(self.store.acquire_claim("inflight", "key-a", 60))
        self.assertIsNotNone(self.store.acquire_claim("inflight", "key-b", 60))

    def test_release_with_wrong_token_keeps_claim(self):
        """属主超时后锁可能已易主，无条件删等于让别人的计算被第三次请求重复触发。"""
        token = self.store.acquire_claim("inflight", "key-a", 60)
        self.store.release_claim("inflight", "key-a", "not-" + token)
        self.assertTrue(self.store.is_claimed("inflight", "key-a"))
        self.assertIsNone(self.store.acquire_claim("inflight", "key-a", 60))

    def test_release_with_own_token_frees_claim(self):
        token = self.store.acquire_claim("inflight", "key-a", 60)
        self.store.release_claim("inflight", "key-a", token)
        self.assertFalse(self.store.is_claimed("inflight", "key-a"))
        self.assertIsNotNone(self.store.acquire_claim("inflight", "key-a", 60))

    def test_claim_scoped_per_namespace(self):
        self.assertIsNotNone(self.store.acquire_claim("scope-1", "same", 60))
        self.assertIsNotNone(self.store.acquire_claim("scope-2", "same", 60))


class ConsumeTests(unittest.TestCase):
    """一次性凭据的读删（R1.2 的 OAuth state 依赖它）。

    这组断言全部围绕一个命题：**同一个 state 第二次必须拿不到**，无论两次请求落在
    同一个 worker 还是两个 worker、无论 Redis 是活着还是半路挂掉。做不到这一点，
    state 就不是 CSRF 防线，只是一个「用掉一次还剩一次」的随机数。
    """

    class FakeClient:
        """共享字典当 Redis：两个 store 实例 = 两个 worker 看到同一个后端。"""

        def __init__(self, store, *, fail_getdel=False, fail_pipeline=False):
            self.store = store
            self.fail_getdel = fail_getdel
            self.fail_pipeline = fail_pipeline
            self.getdel_calls = 0

        def getdel(self, full_key):
            self.getdel_calls += 1
            if self.fail_getdel:
                raise RuntimeError("ERR unknown command 'GETDEL'")
            return self.store.pop(full_key, None)

        def pipeline(self, transaction=True):
            if self.fail_pipeline:
                raise RuntimeError("connection reset")
            return ConsumeTests.FakePipeline(self.store)

        def delete(self, full_key):
            self.store.pop(full_key, None)

        def scan_iter(self, match=None, count=None):
            prefix = (match or "").rstrip("*")
            return [key for key in list(self.store) if key.startswith(prefix)]

    class FakePipeline:
        def __init__(self, store):
            self.store = store
            self.ops = []

        def get(self, full_key):
            self.ops.append(("get", full_key))

        def delete(self, full_key):
            self.ops.append(("delete", full_key))

        def execute(self):
            out = []
            for op, full_key in self.ops:
                if op == "get":
                    out.append(self.store.get(full_key))
                else:
                    self.store.pop(full_key, None)
                    out.append(1)
            return out

    class FakeCache:
        prefix = "aus_ele_test"

        def __init__(self, backing, client):
            self.backing = backing
            self.client = client
            self.failures = 0

        def _get_client(self):
            return self.client

        def _record_failure(self):
            self.failures += 1

        def _full_key(self, scope, key):
            return f"{self.prefix}:{scope}:{key}"

        def get_json(self, scope, key):
            import json as _json

            raw = self.backing.get(self._full_key(scope, key))
            return None if raw is None else _json.loads(raw)

        def set_json(self, scope, key, value, ttl_seconds):
            import json as _json

            self.backing[self._full_key(scope, key)] = _json.dumps(value)

    def setUp(self):
        self.backing = {}
        self.client = self.FakeClient(self.backing)
        self.store = self._make_store(self.client)

    def _make_store(self, client, backing=None):
        from shared_state import SharedStateStore

        cache = self.FakeCache(backing if backing is not None else self.backing, client)
        return SharedStateStore(cache=cache)

    def test_consume_is_single_use_in_one_worker(self):
        self.store.remember("oauth_state", "k", {"provider": "google"}, 600)
        self.assertEqual(self.store.consume("oauth_state", "k"), {"provider": "google"})
        self.assertIsNone(self.store.consume("oauth_state", "k"))
        self.assertEqual(self.store.keys("oauth_state"), [])

    def test_consume_clears_both_sides(self):
        """只删 Redis 会在本 worker 影子里留下一份可读的 state。"""
        self.store.remember("oauth_state", "k", {"v": 1}, 600)
        full = self.store._full_key("oauth_state", "k")
        self.assertIn(full, self.store._local_cache)
        self.store.consume("oauth_state", "k")
        self.assertNotIn(full, self.store._local_cache)
        self.assertNotIn("aus_ele_test:oauth_state:k", self.backing)

    def test_second_worker_cannot_replay_state_held_in_first_worker_shadow(self):
        """决定性一条：/start 落在 A、回调落在 B 之后，A 也不能再消费同一个 state。

        A 的影子缓存里有这个 state（remember 两侧都写），Redis 里那份已被 B 删掉。
        如果 Redis 可用时还允许读影子，A 就会把「已消费」的 state 再交出去一次。
        """
        worker_a = self._make_store(self.FakeClient(self.backing))
        worker_b = self._make_store(self.FakeClient(self.backing))
        worker_a.remember("oauth_state", "shared", {"provider": "github"}, 600)
        # 前提成立：两个 worker 各自都「看得见」这个 state
        self.assertIn("shared", worker_a.keys("oauth_state"))
        self.assertEqual(worker_b.consume("oauth_state", "shared"), {"provider": "github"})
        # 结论：A 只能把它当已消费处理（并顺手清掉自己那份影子）
        self.assertIsNone(worker_a.consume("oauth_state", "shared"))
        self.assertNotIn("shared", worker_a.keys("oauth_state"))

    def test_missing_getdel_falls_back_to_transaction(self):
        """老版本 Redis（< 6.2）无 GETDEL：必须仍然原子，而不是抛到请求链路。"""
        client = self.FakeClient(self.backing, fail_getdel=True)
        store = self._make_store(client)
        store.remember("oauth_state", "k", {"v": 7}, 600)
        self.assertEqual(store.consume("oauth_state", "k"), {"v": 7})
        self.assertNotIn("aus_ele_test:oauth_state:k", self.backing)
        self.assertIsNone(store.consume("oauth_state", "k"))

    def test_total_redis_failure_degrades_to_shadow_once(self):
        """Redis 命令彻底失败时回落影子（单 worker 语义），但仍要读删成对。"""
        client = self.FakeClient(self.backing, fail_getdel=True, fail_pipeline=True)
        store = self._make_store(client)
        store.remember("oauth_state", "k", {"v": 8}, 600)
        self.assertEqual(store.consume("oauth_state", "k"), {"v": 8})
        self.assertIsNone(store.consume("oauth_state", "k"))
        self.assertGreaterEqual(client.store and store._cache.failures, 2)

    def test_expired_entry_is_not_returned(self):
        self.store.remember("oauth_state", "k", {"v": 1}, ttl_seconds=1)
        full_key = self.store._full_key("oauth_state", "k")
        with self.store._local_cache_guard:
            value, _expires = self.store._local_cache[full_key]
            self.store._local_cache[full_key] = (value, time.time() - 1)
        # Redis 侧同样让它「看起来已过期」：直接从后端删掉，模拟 TTL 已回收
        self.backing.pop(f"{self.store._cache.prefix}:oauth_state:k", None)
        self.assertIsNone(self.store.consume("oauth_state", "k"))

    def test_undecodable_payload_returns_none_and_still_deletes(self):
        self.backing[f"{self.store._cache.prefix}:oauth_state:k"] = "not-json{"
        self.store._local_cache[self.store._full_key("oauth_state", "k")] = ({"v": 1}, time.time() + 60)
        self.assertIsNone(self.store.consume("oauth_state", "k"))
        self.assertNotIn(f"{self.store._cache.prefix}:oauth_state:k", self.backing)
        self.assertNotIn(self.store._full_key("oauth_state", "k"), self.store._local_cache)


class InviteAcceptRateLimitTests(unittest.TestCase):
    """端点级接线：函数签名/语义未变，但窗口已外置。"""

    def setUp(self):
        self.store = reset_state_store_for_tests(offline_state_store())
        self.addCleanup(reset_state_store_for_tests)

    def test_blocks_eleventh_attempt_for_same_token_and_ip(self):
        for _ in range(10):
            check_invite_accept_rate_limit("tok-a", "1.1.1.1")
        with self.assertRaises(HTTPException) as ctx:
            check_invite_accept_rate_limit("tok-a", "1.1.1.1")
        self.assertEqual(ctx.exception.status_code, 429)
        self.assertIn("Retry-After", ctx.exception.headers or {})

    def test_different_ip_is_unaffected(self):
        for _ in range(10):
            check_invite_accept_rate_limit("tok-b", "1.1.1.1")
        check_invite_accept_rate_limit("tok-b", "2.2.2.2")

    def test_window_seconds_unchanged(self):
        """10 分钟窗口是被记录在任务文档里的行为，外置不该悄悄改它。"""
        self.assertEqual(_INVITE_ACCEPT_WINDOW_SECONDS, 600)


if __name__ == "__main__":
    unittest.main()
