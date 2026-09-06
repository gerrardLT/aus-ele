"""公测运营控制台端点测试（R5.5，2026-09-06）。

跑在真实 PG 上（与其余认证测试同族：setUp 重置权限表，邮箱带随机后缀）。

这一批测试里最值钱的不是「200 且字段齐」，而是三条反向断言：

1. **缺表必须报 null，不能报 0**（``test_missing_agent_log_reports_null_not_zero``）。
   运营面板把「数据源没接上」显示成「零个用户在用」，是会直接导致错误决策的那类 bug ——
   读的人会得出「没人要这个功能」的结论，而真相是表还没建。asset_project（R4）现在就是
   这个状态，所以这条断言在今天是实打实的守门。
2. **白名单未配置时必须失败关闭**（``test_allowlist_not_configured_is_503``）。平台侧没有
   「超级管理员」这个角色，控制台是靠一个显式允许名单把关的；名单为空的那一刻它必须是
   「谁也进不去」，而不是「大家进得来」。
3. **这个模块必须只读、零新表**（``test_module_is_read_only_and_creates_no_tables``）。
   Spec §163 的「零新表」是个会被慢慢侵蚀的约束：往控制台里加一张聚合表看起来是合理的
   性能优化，实际是引入一条会失真的链路。源码级断言是唯一能长期守住它的方式。
"""

import datetime
import os
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

from access_control import (  # noqa: E402
    BOOTSTRAP_PRINCIPAL_ID,
    issue_access_token,
    seed_organization,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
)
from database import DatabaseManager  # noqa: E402
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from routes import account_routes, console_routes  # noqa: E402

CONSOLE_PREFIX = "/api/v1/console"


class ConsoleRouteTests(unittest.TestCase):
    def setUp(self):
        self.suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        reset_access_control_tables(self.db)
        self.state_store = offline_state_store()
        mock.patch.object(console_routes, "get_db", lambda: self.db).start()
        mock.patch.object(account_routes, "get_db", lambda: self.db).start()
        mock.patch("shared_state.get_state_store", lambda: self.state_store).start()
        console_routes._cache.clear()
        self.addCleanup(console_routes._cache.clear)
        self.addCleanup(mock.patch.stopall)

        self.org = seed_organization(self.db, name=f"Ops-{self.suffix}")
        self.ws = seed_workspace(self.db, organization_id=self.org["organization_id"], name="OpsWS")
        self.app = FastAPI()
        self.app.include_router(console_routes.router)
        self.client = TestClient(self.app, raise_server_exceptions=False)

    # -- helpers ---------------------------------------------------------

    def make_member(self, *, email_verified=False, operator=False):
        email = f"op-{self.suffix}-{uuid.uuid4().hex[:6]}@{self.suffix}.test"
        principal = seed_principal(self.db, email=email, display_name="Ops")
        seed_workspace_membership(
            self.db, workspace_id=self.ws["workspace_id"], principal_id=principal["principal_id"], role="owner"
        )
        if email_verified:
            self._execute(
                "UPDATE principal_identity SET email_verified_at = ? WHERE principal_id = ?",
                (self._now(), principal["principal_id"]),
            )
        token = issue_access_token(
            self.db, principal_id=principal["principal_id"], workspace_id=self.ws["workspace_id"]
        )
        if operator:
            self._set_allowlist([email.upper()])  # 顺带验证大小写不敏感
        return {"email": email, "principal_id": principal["principal_id"],
                "headers": {"Authorization": f"Bearer {token['token']}"}}

    def _set_allowlist(self, entries):
        mock.patch.dict(os.environ, {console_routes.ALLOWLIST_ENV: ", ".join(entries)}, clear=False).start()

    def _now(self):
        return datetime.datetime.now(datetime.timezone.utc).isoformat().replace("+00:00", "Z")

    def _execute(self, sql, params=()):
        with self.db.get_connection() as conn:
            conn.execute(sql, params)
            conn.commit()

    def seed_agent_run(self, principal_id, *, query="peak analysis", status="completed"):
        self._execute(
            "INSERT INTO agent_execution_log (id, query, market, status, created_at, workspace_id, principal_id) "
            "VALUES (?, ?, 'NEM', ?, ?, ?, ?)",
            (f"exec-{uuid.uuid4().hex[:8]}", query, status, _utc_of_day(), self.ws["workspace_id"], principal_id),
        )

    def _stage(self, payload, stage):
        return next(s for s in payload["activation_funnel"] if s["stage"] == stage)

    def _runs_in_window(self, days=30):
        """engagement 是**全站窗口量**：共享开发库里有历史运行行，所以只能断言增量。

        这不是把测试写弱。拿绝对值断言等于假设这个测试独占一张生产表，而它并不独占 ——
        那种断言会在别人跑完一轮回归后无理由变红。
        """
        cutoff = console_routes._cutoff(days)
        with self.db.get_connection() as conn:
            row = conn.execute(
                "SELECT COUNT(*) FROM agent_execution_log WHERE created_at >= ?", (cutoff,)
            ).fetchone()
        return row[0]


def _utc_of_day():
    return datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")


def _monday_of_today():
    """本周一（naive UTC）。周留存同期群要按周对齐，写死日期会让这个测试在两周后失去意义。"""
    now = datetime.datetime.now(datetime.timezone.utc)
    return (now - datetime.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)


class ActivationMetricsTests(ConsoleRouteTests):
    def setUp(self):
        super().setUp()
        # 先确保 agent_execution_log 存在（生产由路由模块首次使用时建表）：否则「表不存在」
        # 会被当成正常状态，下面那些指标断言就成了空转。
        self._execute(
            "CREATE TABLE IF NOT EXISTS agent_execution_log ("
            "id TEXT PRIMARY KEY, query TEXT NOT NULL, market TEXT, region TEXT, workflow_type TEXT, "
            "status TEXT, steps_json TEXT, report_json TEXT, total_duration_ms REAL, "
            "created_at TIMESTAMPTZ DEFAULT now())"
        )
        for ddl in (
            "ALTER TABLE agent_execution_log ADD COLUMN IF NOT EXISTS workspace_id TEXT",
            "ALTER TABLE agent_execution_log ADD COLUMN IF NOT EXISTS principal_id TEXT",
        ):
            self._execute(ddl)

    def test_no_token_is_401(self):
        self.assertEqual(self.client.get(f"{CONSOLE_PREFIX}/activation").status_code, 401)

    def test_allowlist_not_configured_is_503(self):
        member = self.make_member()
        mock.patch.dict(os.environ, {}, clear=False).start()
        os.environ.pop(console_routes.ALLOWLIST_ENV, None)
        res = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=member["headers"])
        self.assertEqual(res.status_code, 503, "白名单为空必须失败关闭，而不是放行")
        self.assertIn(console_routes.ALLOWLIST_ENV, res.json()["detail"])

    def test_authenticated_but_not_on_allowlist_is_403(self):
        member = self.make_member()
        self._set_allowlist(["someone-else@other.test"])
        res = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=member["headers"])
        self.assertEqual(res.status_code, 403)

    def test_anonymous_bootstrap_cannot_read_platform_metrics(self):
        self._set_allowlist(["*"])  # 即便把通配写进名单，引导身份也要在上一层就被挡掉
        self.db.upsert_principal({
            "principal_id": BOOTSTRAP_PRINCIPAL_ID,
            "email": f"bootstrap-{self.suffix}@{self.suffix}.test",
            "display_name": "Anonymous bootstrap",
            "password_hash": None,
            "password_salt": None,
            "created_at": _now_static(),
            "updated_at": _now_static(),
        })
        seed_workspace_membership(
            self.db, workspace_id=self.ws["workspace_id"], principal_id=BOOTSTRAP_PRINCIPAL_ID, role="owner"
        )
        token = issue_access_token(
            self.db, principal_id=BOOTSTRAP_PRINCIPAL_ID, workspace_id=self.ws["workspace_id"]
        )
        for path in ("activation", "feedback", "sources"):
            res = self.client.get(f"{CONSOLE_PREFIX}/{path}",
                                  headers={"Authorization": f"Bearer {token['token']}"})
            self.assertEqual(res.status_code, 403, f"匿名 bootstrap 读到了全站指标：/{path}")

    def test_operator_by_principal_id_gets_full_funnel(self):
        verified = self.make_member(email_verified=True)
        self._set_allowlist([verified["principal_id"]])
        self.make_member(email_verified=False)
        baseline = self._runs_in_window()
        self.seed_agent_run(verified["principal_id"])
        res = self.client.get(f"{CONSOLE_PREFIX}/activation?days=30&weeks=4", headers=verified["headers"])
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertEqual(body["accounts"]["total"], 2)
        self.assertEqual(body["accounts"]["signed_up_in_window"], 2)
        self.assertEqual(body["accounts"]["email_verified_in_window"], 1)
        self.assertEqual(self._stage(body, "first_agent_run")["count"], 1)
        self.assertEqual(self._stage(body, "email_verified")["of_previous"], 0.5)
        self.assertEqual(self._stage(body, "first_agent_run")["of_previous"], 1.0)
        self.assertEqual(body["engagement"]["agent_runs"], baseline + 1)
        self.assertEqual(
            body["engagement"]["scope"], "all_accounts_in_window",
            "漏斗按同期群、参与度按全站：两个口径都必须写在响应里，否则前端一定拿来互除",
        )

    def test_funnel_denominator_is_the_window_cohort_not_all_accounts(self):
        """历史账户不得混进激活分母，否则注册池越大、激活率越低，读的人会以为产品在退步。

        这条断言在共享开发库上才有意义：那里残留着不属于本轮的 principal 与 agent 行。
        """
        operator = self.make_member(operator=True)
        # 造一个「窗口之外」的老账户，并且它有一堆天枢运行 —— 全量口径会把它的运行算进漏斗
        veteran = self.make_member(email_verified=True)
        self._execute(
            "UPDATE principal_identity SET created_at = ? WHERE principal_id = ?",
            ("2020-01-01T00:00:00Z", veteran["principal_id"]),
        )
        self.seed_agent_run(veteran["principal_id"])
        body = self.client.get(f"{CONSOLE_PREFIX}/activation?days=30", headers=operator["headers"]).json()
        self.assertEqual(body["accounts"]["total"], 2, "全量基数仍能看到两个账户")
        self.assertEqual(body["accounts"]["signed_up_in_window"], 1, "分母只含窗口内注册的那一个")
        self.assertEqual(self._stage(body, "first_agent_run")["count"], 0, "老账户的运行不算本期激活")
        self.assertTrue(any("同期群" in c for c in body["caveats"]), "口径必须写在 caveats 里")

    def test_repeat_run_counts_people_not_runs(self):
        """第二级「回来过」按人去重：一个人跑 3 次与 3 个人各跑 1 次必须给出不同的 first_run。"""
        operator = self.make_member(operator=True)
        baseline = self._runs_in_window()
        for _ in range(3):
            self.seed_agent_run(operator["principal_id"])
        body = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        self.assertEqual(self._stage(body, "first_agent_run")["count"], 1)
        self.assertEqual(self._stage(body, "repeat_run")["count"], 1)
        self.assertEqual(body["engagement"]["agent_runs"], baseline + 3)
        self.assertGreaterEqual(body["engagement"]["distinct_runners"], 1)

    def test_missing_agent_log_reports_null_not_zero(self):
        operator = self.make_member(operator=True)
        with mock.patch.object(console_routes, "_table_exists", return_value=False):
            body = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        self.assertIsNone(self._stage(body, "first_agent_run")["count"], "表不存在时 0 会被读成「没人用」")
        self.assertIsNone(self._stage(body, "repeat_run")["count"])
        self.assertTrue(any("agent_execution_log" in c for c in body["caveats"]),
                        "每一个 null 都必须有一句解释")
        self.assertEqual(body["engagement"]["available"], False)

    def test_uncacheable_second_hit_is_served_from_cache(self):
        operator = self.make_member(operator=True)
        first = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        second = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"], "控制台会被反复刷新，聚合查询必须有 TTL")
        # 缓存命中时不得重新读数：改一条数据，指标应保持旧值
        self.seed_agent_run(operator["principal_id"])
        third = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        self.assertEqual(third["engagement"]["agent_runs"], first["engagement"]["agent_runs"])

    def test_week_two_return_rate_is_measured_on_the_signup_cohort(self):
        """周留存：上上周注册、紧接着的下一周又跑一次 → 该同期群 return_rate = 1.0。

        这是公测期最该盯的单一指标（比 DAU 更难被一次拉新冲淡），所以它的分桶口径要能被
        测试钉住：注册日与回访日跨周时，按「第 N 天 ÷ 7」分桶会把同一个人算成未回访。
        """
        operator = self.make_member(operator=True)
        cohort_monday = _monday_of_today() - datetime.timedelta(weeks=2)
        veteran = self.make_member(email_verified=True)
        self._execute(
            "UPDATE principal_identity SET created_at = ? WHERE principal_id = ?",
            (cohort_monday.strftime("%Y-%m-%dT12:00:00Z"), veteran["principal_id"]),
        )
        self._execute(
            "INSERT INTO agent_execution_log (id, query, market, status, created_at, workspace_id, principal_id) "
            "VALUES (?, 'w2', 'NEM', 'completed', ?, ?, ?)",
            (
                f"exec-{uuid.uuid4().hex[:8]}",
                # +1 周再 +1 天：回访必须落在「下一周」这一桶里，落到本周就成了次周未回访
                (cohort_monday + datetime.timedelta(weeks=1, days=1)).strftime("%Y-%m-%d %H:%M:%S+00"),
                self.ws["workspace_id"],
                veteran["principal_id"],
            ),
        )
        body = self.client.get(f"{CONSOLE_PREFIX}/activation?weeks=4", headers=operator["headers"]).json()
        retention = body["retention"]
        self.assertTrue(retention["available"])
        cohort = next(c for c in retention["cohorts"] if c["cohort_week"] == console_routes._week_key(cohort_monday))
        self.assertEqual(cohort["signups"], 1)
        self.assertEqual(cohort["returned_next_week"], 1)
        self.assertEqual(cohort["return_rate"], 1.0)

    def test_retention_query_failure_is_not_reported_as_zero_returns(self):
        operator = self.make_member(operator=True)
        with mock.patch.object(console_routes, "_rows", return_value=None):
            body = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        self.assertFalse(body["retention"]["available"])
        self.assertEqual(body["retention"]["cohorts"], [])
        self.assertTrue(any("零回访" in c for c in body["caveats"]),
                        "查询失败必须被写成「指标不可用」，不能留一排 0 在面板上")

    def test_zero_runs_give_ratio_zero_not_crash(self):
        """没有任何运行时：of_total 是真实的 0.0，而 of_previous 必须是 None（分母为零）。"""
        operator = self.make_member(operator=True)
        body = self.client.get(f"{CONSOLE_PREFIX}/activation", headers=operator["headers"]).json()
        stage = self._stage(body, "first_agent_run")
        self.assertEqual(stage["count"], 0)
        self.assertEqual(stage["of_total"], 0.0)
        self.assertIsNone(stage["of_previous"], "0/0 不能是一个数字")
        self.assertIsNone(self._stage(body, "repeat_run")["of_previous"])


class FeedbackReadTests(ConsoleRouteTests):
    def test_feedback_list_is_returned_and_audited(self):
        operator = self.make_member(operator=True)
        feedback_id = f"fb-{uuid.uuid4().hex[:8]}"
        self._execute(
            "INSERT INTO feedback (feedback_id, email, workspace_id, message, created_at) VALUES (?, ?, ?, ?, ?)",
            (feedback_id, f"user-{self.suffix}@x.test", self.ws["workspace_id"],
             "希望支持 FCAS 收益拆解", self._now()),
        )
        before = self._audit_count()
        res = self.client.get(f"{CONSOLE_PREFIX}/feedback?limit=5", headers=operator["headers"])
        self.assertEqual(res.status_code, 200, res.text)
        body = res.json()
        self.assertTrue(body["available"])
        # feedback 不是认证表、不随 setUp 清空（清了会毁掉真实反馈），所以断言「上限被尊重 +
        # 我这条在里面」，而不是断言全站只有一条反馈。
        self.assertEqual(body["count"], min(5, self._feedback_rows()))
        self.assertLessEqual(body["count"], 5)
        self.assertIn(feedback_id, [item["feedback_id"] for item in body["items"]])
        dates = [item["created_at"] for item in body["items"]]
        self.assertEqual(dates, sorted(dates, reverse=True), "运营看反馈必须从新到旧")
        self.assertIn("pii_notice", body)
        self.assertGreater(self._audit_count(), before, "读全站反馈是一个需要留痕的能力")

    def _feedback_rows(self):
        with self.db.get_connection() as conn:
            return conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]

    def _audit_count(self):
        with self.db.get_connection() as conn:
            conn.row_factory = True
            row = conn.execute("SELECT COUNT(*) FROM audit_log WHERE action = ?",
                               ("console.feedback_read",)).fetchone()
        return row[0] if row else 0


class SurfaceTests(ConsoleRouteTests):
    #: 每个 FastAPI 实例自带的文档端点，与被测路由无关
    FRAMEWORK_PATHS = {"/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"}

    def test_module_is_registered_with_expected_paths(self):
        from routes import ROUTE_MODULES

        self.assertIn("routes.console_routes", ROUTE_MODULES, "未登记的模块会静默不上线")
        paths = {route.path for route in self.app.routes if hasattr(route, "path")} - self.FRAMEWORK_PATHS
        self.assertEqual(
            paths,
            {f"{CONSOLE_PREFIX}/activation", f"{CONSOLE_PREFIX}/feedback", f"{CONSOLE_PREFIX}/sources"},
        )
        # 三条端点都必须带前缀：漏掉前缀的端点会逃过网关层的 /api/v1 鉴权约定
        for route in console_routes.router.routes:
            self.assertTrue(getattr(route, "path", "").startswith(CONSOLE_PREFIX), route.path)

    def test_module_is_read_only_and_creates_no_tables(self):
        import inspect

        source = _code_only_source(inspect.getsource(console_routes))
        for forbidden in ("CREATE TABLE", "INSERT INTO", "UPDATE ", "DELETE FROM", "ALTER TABLE"):
            self.assertNotIn(forbidden, source, f"控制台必须只读：发现 {forbidden!r}")
        # 不得现算重指标（同 R6.3 StatusPage 的判据）
        self.assertNotIn("compute_quality_snapshots", source)


def _code_only_source(source: str) -> str:
    """去掉注释与 docstring，只留下真正的代码。

    只读守卫必须能容忍「文档里提到被禁的东西」：这个模块的 docstring 需要解释它为什么不调
    ``compute_quality_snapshots``，而按整份源码做子串检查会让「写下这条约束」本身变成违规 ——
    那种守卫的第一次演进就是被人整个删掉。
    """
    import ast

    tree = ast.parse(source)
    doc_lines: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant):
                doc_lines.update(range(body[0].lineno, body[0].end_lineno + 1))

    kept = []
    lines = source.splitlines()
    for index, line in enumerate(lines, start=1):
        if index in doc_lines:
            continue
        stripped = line.lstrip()
        if stripped.startswith("#"):
            continue
        kept.append(line.split("#", 1)[0] if " #" in line else line)
    return "\n".join(kept)


def _now_static():
    return datetime.datetime(2026, 9, 1, tzinfo=datetime.timezone.utc).isoformat().replace("+00:00", "Z")


class WeekKeyTests(unittest.TestCase):
    def test_iso_week_bucketing_is_stable_across_year_boundary(self):
        """跨年那一周最容易错：2027-01-01 属于 ISO 2026-W53，按日历年分会把 cohort 挪一个桶。"""
        self.assertEqual(console_routes._week_key("2027-01-01"), "2026-W53")
        self.assertEqual(console_routes._shift_week("2026-W53", 1), "2027-W01")
        self.assertEqual(console_routes._shift_week("2026-W05", 1), "2026-W06")
        self.assertEqual(console_routes._week_key(None), "unknown")
        # 2026-01-01 是周四 → ISO 第 1 周含元旦，故 9/5（周六）落在 W36 而不是按日历年除 7 的 W37
        self.assertEqual(console_routes._week_key(datetime.date(2026, 9, 5)), "2026-W36")
        self.assertEqual(console_routes._week_key("2026-09-05"), "2026-W36")
        self.assertEqual(
            console_routes._week_key(datetime.datetime(2026, 9, 5, 23, 30, tzinfo=datetime.timezone.utc)),
            "2026-W36",
            "TIMESTAMPTZ 列回来的是 datetime，不是 str：走错分支会把所有人塞进 unknown 桶",
        )
        self.assertEqual(console_routes._week_key("not-a-date"), "unknown")


if __name__ == "__main__":
    unittest.main()
