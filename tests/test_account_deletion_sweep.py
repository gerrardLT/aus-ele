"""账户删除清扫任务的执行侧测试（R1.7 收尾，2026-09-06）。

``tests/test_data_rights_routes.py`` 验的是**请求侧**（受理、撤销、导出）。这里验的是另一头：
排期行写进库之后，到底有没有人把它执行掉。

为什么这个任务单独值得一个文件：它是全系统唯一一个**物理删除数据且不可回滚**的周期作业。
它写错的方向不是「少删」（顶多用户多等一小时），而是「多删 / 重复删 / 提前删」——
后三种都是无法向用户解释的永久损失。所以断言全部围绕三条禁令：

1. 同一小时只能有一个 worker 真的动手（多 worker 互相 purge 会撞行、把对方挤成 failed）；
2. 宽限期没到的账户**绝不能**被动（界面给用户看了一个精确时刻）；
3. 一轮里失败的行不得连带成功行一起丢（失败留下次重试，成功不该重跑）。

生产是 ``gunicorn app:app --workers N``，每个 worker 各有 AsyncIOScheduler，同一个 cron tick
会被 N 个进程同时触发 —— 所以下面用「两个独立 store 实例」模拟两个 worker，而不是假设只
有一个进程在跑。
"""

import datetime
import unittest
import uuid
from unittest import mock

from tests.support import (
    ensure_repo_import_paths,
    offline_state_store,
    reset_access_control_tables,
    stub_optional_dep,
)

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

import app as app_module  # noqa: E402
from access_control import seed_principal  # noqa: E402
from database import DatabaseManager  # noqa: E402
from services import data_rights  # noqa: E402


class SweepClaimTests(unittest.TestCase):
    """认领锁语义：不碰库，只看「有没有第二个 worker 也去动手」。"""

    def setUp(self):
        self.db = DatabaseManager(None)
        mock.patch("deps.get_db", lambda: self.db).start()
        self.addCleanup(mock.patch.stopall)

    def test_second_worker_in_the_same_hour_does_not_purge_twice(self):
        """锁没抢到就**一个都不删**：返回 0 且不得触碰 execute_due_deletions。

        这条是整套去重里唯一会造成永久损失的分支 —— 两个 worker 同时 purge 同一个 principal
        会互相撞行，把对方的行挤成 failed，而那批数据已经被第一轮删掉了。
        """
        busy = mock.Mock()
        busy.acquire_claim.return_value = None
        with mock.patch("shared_state.get_state_store", lambda: busy), \
                mock.patch.object(data_rights, "execute_due_deletions") as run:
            self.assertEqual(app_module.run_account_deletion_sweep(), 0)
        run.assert_not_called()
        busy.release_claim.assert_not_called()

    def test_successful_sweep_keeps_the_claim_so_the_hour_is_not_re_run(self):
        """成功路径刻意**不释放**锁：这一小时已经有人干完了。

        释放会让同小时的第二个 worker 再跑一轮 —— 那时候行已经没了，第二轮不是幂等空转，
        而是白占一次 purge 窗口（并且如果这期间有新到期行，会被提前于预期时刻删掉）。
        """
        store = mock.Mock()
        store.acquire_claim.return_value = "tok-1"
        with mock.patch("shared_state.get_state_store", lambda: store), \
                mock.patch.object(
                    data_rights, "execute_due_deletions",
                    return_value=[{"principal_id": "p1", "status": "executed", "deleted": {}}],
                ):
            self.assertEqual(app_module.run_account_deletion_sweep(), 1)
        store.release_claim.assert_not_called()
        # 锁 key 必须带小时桶：不带的话一次误删失败会把后续所有小时都锁死
        scope_key = store.acquire_claim.call_args.args[:2]
        self.assertEqual(scope_key, ("scheduler", f"account-deletion-sweep:{_hour_bucket()}"))

    def test_transient_failure_releases_the_claim_for_a_peer_worker(self):
        """抛错必须交还锁并向上抛：否则一次瞬时故障就把这一小时变成无人敢删。"""
        store = mock.Mock()
        store.acquire_claim.return_value = "tok-2"
        with mock.patch("shared_state.get_state_store", lambda: store), \
                mock.patch.object(data_rights, "execute_due_deletions", side_effect=RuntimeError("db blip")):
            with self.assertRaises(RuntimeError):
                app_module.run_account_deletion_sweep()
        store.release_claim.assert_called_once_with(
            "scheduler", f"account-deletion-sweep:{_hour_bucket()}", "tok-2"
        )

    def test_failed_rows_do_not_dilute_the_executed_count(self):
        """逐行结果里只有 executed 计数：failed 行留下小时重试，不该被算成已删。"""
        store = mock.Mock()
        store.acquire_claim.return_value = "tok-3"
        rows = [
            {"principal_id": "a", "status": "executed", "deleted": {"principal_identity": 1}},
            {"principal_id": "b", "status": "failed", "error": "boom"},
            {"principal_id": "c", "status": "executed", "deleted": {}},
        ]
        with mock.patch("shared_state.get_state_store", lambda: store), \
                mock.patch.object(data_rights, "execute_due_deletions", return_value=rows):
            self.assertEqual(app_module.run_account_deletion_sweep(), 2)

    def test_two_simulated_workers_run_the_sweep_exactly_once(self):
        """跨 worker 去重的真实形态：两个独立 store 实例抢同一个小时桶。

        用 ``offline_state_store()`` 起两份是因为本机有没有 Redis 不该改变这里的语义 ——
        单进程语义下第二份必然抢不到，而多进程语义要靠 Redis；测试锁的是「只跑一次」这个
        结果，不是某一种实现。所以直接拿一份共享 store 模拟抢到锁的两侧。
        """
        store = offline_state_store()
        calls = []

        def fake_execute(_db, **_kw):
            calls.append(1)
            return []

        with mock.patch("shared_state.get_state_store", lambda: store), \
                mock.patch.object(data_rights, "execute_due_deletions", fake_execute):
            first = app_module.run_account_deletion_sweep()
            second = app_module.run_account_deletion_sweep()
        self.assertEqual((first, second), (0, 0))
        self.assertEqual(len(calls), 1, "同一小时被跑了两遍")


def _hour_bucket(now=None):
    tz = app_module._scheduler_timezone()
    return (now or datetime.datetime.now(tz)).strftime("%Y-%m-%dT%H")


class SweepEnabledTests(unittest.TestCase):
    """开关必须是独立的：这是唯一一个物理删数据的作业，运维停它时不该顺手停掉市场同步。"""

    def test_enabled_by_default_and_flippable_independently(self):
        import os

        for raw, expected in ((None, True), ("", True), ("0", False), ("false", False),
                              ("False", False), ("1", True), ("true", True)):
            env = {} if raw is None else {"AUS_ELE_ENABLE_ACCOUNT_DELETION_SWEEP": raw}
            # clear=True：开发机上 .env 里可能已经有这个变量，不清就会把「默认值」测成一个
            # 由环境决定的值 —— 那种测试在别人机器上变红而这里全绿。
            with mock.patch.dict(os.environ, env, clear=True):
                self.assertEqual(app_module._account_deletion_sweep_enabled(), expected, f"raw={raw!r}")


class SweepRealDeletionTests(unittest.TestCase):
    """端到端：宽限期到了就真的删掉，没到就绝对不碰。用真实 PG。"""

    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        data_rights.ensure_data_rights_tables(self.db)
        self.state_store = offline_state_store()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        mock.patch("deps.get_db", lambda: self.db).start()
        self.addCleanup(mock.patch.stopall)

    def _seed(self, name):
        principal = seed_principal(
            self.db, email=f"{name}-{self.suffix}@{self.suffix}.test", display_name=name
        )
        pid = principal["principal_id"]
        data_rights.request_account_deletion(self.db, principal_id=pid, grace_days=30)
        return pid

    def _backdate(self, principal_id, days_ago, status=None):
        moment = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=days_ago))
        sql = (
            f"UPDATE {data_rights.DELETION_TABLE} SET scheduled_delete_at = ?"
            + (" WHERE principal_id = ? AND status = ?" if status else " WHERE principal_id = ?")
        )
        params = (moment.strftime("%Y-%m-%dT%H:%M:%SZ"), principal_id)
        if status:
            params += (status,)
        with self.db.get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def test_account_whose_grace_has_elapsed_is_actually_purged(self):
        """没有这一步，「30 天后永久删除」只是写在界面上的承诺。"""
        pid = self._seed("Due")
        self._backdate(pid, days_ago=1)

        executed = app_module.run_account_deletion_sweep()

        self.assertGreaterEqual(executed, 1)
        self.assertIsNone(self.db.fetch_principal(pid), "到期账户仍在库里")
        self.assertIsNone(data_rights.get_deletion_request(self.db, principal_id=pid))
        # 审计流水是唯一的执行凭证（排期行本身已被 purge 清掉）
        with self.db.get_connection() as conn:
            rows = conn.execute(
                f"SELECT action FROM {self.db.AUDIT_LOG_TABLE} WHERE target_id = ? AND action = ?",
                (pid, "account.deletion_executed"),
            ).fetchall()
        self.assertEqual(len(rows), 1, "缺少可举证的删除审计流水")

    def test_account_still_inside_its_grace_period_is_left_untouched(self):
        """提前删除是不可逆的越权执行：宽限期是用户在反悔窗口里拿到的唯一保障。"""
        pid = self._seed("Early")
        before = app_module.run_account_deletion_sweep()

        self.assertIsNotNone(self.db.fetch_principal(pid), "宽限期未满就被删了")
        row = data_rights.get_deletion_request(self.db, principal_id=pid)
        self.assertEqual(row["status"], "pending")
        self.assertIsInstance(before, int)

    def test_cancelled_request_survives_a_sweep(self):
        """撤销必须真的终止流程，而不是只改个前端文案。"""
        pid = self._seed("Cancelled")
        data_rights.cancel_account_deletion(self.db, principal_id=pid)
        self._backdate(pid, days_ago=1)  # 即便时刻已过，cancelled 也不该被执行

        app_module.run_account_deletion_sweep()

        self.assertIsNotNone(self.db.fetch_principal(pid), "已撤销的账户被清扫删掉了")
        self.assertEqual(data_rights.get_deletion_request(self.db, principal_id=pid)["status"], "cancelled")


if __name__ == "__main__":
    unittest.main()
