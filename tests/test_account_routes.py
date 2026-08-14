"""Tests for account self-service routes（P0 账户中心，2026-08-13）.

覆盖：/me、成员/邀请权限矩阵、API Key 生命周期（创建一次性 raw/列表脱敏/吊销）、
用量端点结构。用 dependency_overrides 注入伪造 actor；DatabaseManager 为 PG-only，
测试直连开发库（随机后缀隔离 + tearDown 清理）。
"""

import sys
import types
import unittest
import uuid

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from fastapi import FastAPI
from fastapi.testclient import TestClient

from database import DatabaseManager
from routes import account_routes
from access_control import (
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
)


def _build_client(db, actor):
    app = FastAPI()
    app.include_router(account_routes.router)
    app.dependency_overrides[account_routes._get_actor] = lambda: actor
    return TestClient(app)


class AccountRoutesTests(unittest.TestCase):
    """DatabaseManager 为 PG-only，测试直连开发库：用随机后缀邮箱避免冲突，
    tearDown 在本测试组织内做清理（成员移除/邀请撤销/Key 吊销）。"""

    def setUp(self):
        self._suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        # account_routes 以 from deps import get_db 按名绑定，补丁到模块属性
        self._orig_get_db = account_routes.get_db
        account_routes.get_db = lambda: self.db

        self.org = seed_organization(self.db, name=f"Acme-{self._suffix}")
        self.ws = seed_workspace(self.db, organization_id=self.org["organization_id"], name="main")
        self.owner = seed_principal(self.db, email=f"owner-{self._suffix}@acme.test", display_name="Owner")
        self.viewer = seed_principal(self.db, email=f"viewer-{self._suffix}@acme.test", display_name="Viewer")
        seed_workspace_membership(self.db, workspace_id=self.ws["workspace_id"],
                                  principal_id=self.owner["principal_id"], role="owner")
        seed_workspace_membership(self.db, workspace_id=self.ws["workspace_id"],
                                  principal_id=self.viewer["principal_id"], role="viewer")
        # 登录链路要求激活的组织成员关系
        seed_organization_membership(self.db, organization_id=self.org["organization_id"],
                                     principal_id=self.owner["principal_id"], role="org_owner")
        seed_organization_membership(self.db, organization_id=self.org["organization_id"],
                                     principal_id=self.viewer["principal_id"], role="org_member")

        self.owner_actor = {
            "principal": self.owner,
            "workspace": self.ws,
            "membership": self.db.fetch_workspace_membership(self.ws["workspace_id"], self.owner["principal_id"]),
        }
        self.viewer_actor = {
            "principal": self.viewer,
            "workspace": self.ws,
            "membership": self.db.fetch_workspace_membership(self.ws["workspace_id"], self.viewer["principal_id"]),
        }

    def tearDown(self):
        account_routes.get_db = self._orig_get_db
        # 清理本轮插入的 agent_execution_log 计量行 + 订阅行
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='agent_execution_log'"
                )
                if cursor.fetchone():
                    cursor.execute(
                        "DELETE FROM agent_execution_log WHERE id LIKE ?",
                        (f"test-{self._suffix}%",),
                    )
                    conn.commit()
            with self.db.get_connection() as conn:
                self.db.ensure_workspace_subscription_table(conn)
                conn.execute(
                    "DELETE FROM workspace_subscription WHERE workspace_id = ?",
                    (self.ws["workspace_id"],),
                )
                conn.commit()
        except Exception:
            pass
        # 组织内清理：Key 吊销 + 邀请撤销（成员留在隔离的测试 workspace，无外泄风险）
        try:
            from access_control import revoke_workspace_invite

            for client in self.db.list_external_api_clients(self.ws["workspace_id"]):
                self.db.upsert_external_api_client({**client, "enabled": False})
            for inv in self.db.list_workspace_invites(self.ws["workspace_id"]):
                if not inv["revoked"]:
                    revoke_workspace_invite(self.db, actor=self.owner_actor, invite_id=inv["invite_id"])
        except Exception:
            pass

    def _emails(self):
        return (f"owner-{self._suffix}@acme.test", f"viewer-{self._suffix}@acme.test")

    # ── invite accept（JSON body 版，密码不进 URL） ────────────────────────

    def test_invite_accept_via_json_body(self):
        from access_control import create_workspace_invite

        app = FastAPI()
        app.include_router(account_routes.router)
        client = TestClient(app)
        invite = create_workspace_invite(
            self.db, actor=self.owner_actor,
            workspace_id=self.ws["workspace_id"],
            email=f"joiner-{self._suffix}@acme.test", role="analyst",
        )
        resp = client.post(
            "/api/v1/account/invites/accept",
            json={
                "invite_token": invite["invite_token"],
                "display_name": "Joiner",
                "password": "long-enough-pw",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["principal"]["email"], f"joiner-{self._suffix}@acme.test")
        self.assertTrue(body["invite"]["accepted_at"])
        # 再次接受应失败（已接受）
        resp2 = client.post(
            "/api/v1/account/invites/accept",
            json={
                "invite_token": invite["invite_token"],
                "display_name": "Joiner",
                "password": "long-enough-pw",
            },
        )
        self.assertEqual(resp2.status_code, 400)

    def test_login_email_case_insensitive(self):
        from access_control import set_principal_password

        set_principal_password(self.db, principal_id=self.owner["principal_id"], password="s3cret-pw")
        app = FastAPI()
        app.include_router(account_routes.router)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/account/login",
            json={"email": f"OWNER-{self._suffix}@ACME.TEST", "password": "s3cret-pw"},
        )
        self.assertEqual(resp.status_code, 200)

    # ── login（友好入口） ────────────────────────────────────────────

    def test_login_without_workspace_id_resolves_first_membership(self):
        from access_control import set_principal_password

        set_principal_password(self.db, principal_id=self.owner["principal_id"], password="s3cret-pw")
        app = FastAPI()
        app.include_router(account_routes.router)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/account/login",
            json={"email": f"owner-{self._suffix}@acme.test", "password": "s3cret-pw"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["access_token"])
        self.assertEqual(body["workspace_id"], self.ws["workspace_id"])

    def test_login_wrong_password_returns_401(self):
        from access_control import set_principal_password

        set_principal_password(self.db, principal_id=self.owner["principal_id"], password="s3cret-pw")
        app = FastAPI()
        app.include_router(account_routes.router)
        client = TestClient(app)
        resp = client.post(
            "/api/v1/account/login",
            json={"email": f"owner-{self._suffix}@acme.test", "password": "wrong"},
        )
        self.assertEqual(resp.status_code, 401)

    # ── /me ─────────────────────────────────────────────────────────────

    def test_me_returns_principal_and_workspaces(self):
        client = _build_client(self.db, self.owner_actor)
        resp = client.get("/api/v1/account/me")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        owner_email, _ = self._emails()
        self.assertEqual(body["principal"]["email"], owner_email)
        self.assertGreaterEqual(len(body["workspaces"]), 1)
        ws_entry = next(w for w in body["workspaces"] if w["workspace_id"] == self.ws["workspace_id"])
        self.assertEqual(ws_entry["role"], "owner")
        self.assertEqual(ws_entry["organization_name"], self.org["name"])

    # ── members ─────────────────────────────────────────────────────────

    def test_members_listed_with_emails(self):
        client = _build_client(self.db, self.viewer_actor)
        resp = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/members")
        self.assertEqual(resp.status_code, 200)
        emails = {m["email"] for m in resp.json()["members"]}
        self.assertEqual(emails, set(self._emails()))

    def test_workspace_mismatch_returns_403(self):
        client = _build_client(self.db, self.owner_actor)
        resp = client.get("/api/v1/account/workspaces/ws_other/members")
        self.assertEqual(resp.status_code, 403)

    # ── invites 权限矩阵 ────────────────────────────────────────────────

    def test_owner_can_create_invite_viewer_cannot(self):
        owner_client = _build_client(self.db, self.owner_actor)
        resp = owner_client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites",
            json={"email": f"new-{self._suffix}@acme.test", "role": "analyst"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertTrue(body["invite_token"])
        self.assertIn("/invite?token=", body["invite_url_path"])

        viewer_client = _build_client(self.db, self.viewer_actor)
        resp2 = viewer_client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites",
            json={"email": f"x-{self._suffix}@acme.test", "role": "analyst"},
        )
        self.assertEqual(resp2.status_code, 403)

    def test_invite_role_validation(self):
        client = _build_client(self.db, self.owner_actor)
        resp = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites",
            json={"email": f"x-{self._suffix}@acme.test", "role": "owner"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_invite_lifecycle_list_revoke(self):
        client = _build_client(self.db, self.owner_actor)
        created = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites",
            json={"email": f"pending-{self._suffix}@acme.test", "role": "viewer"},
        ).json()

        listed = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites").json()
        pending = next(i for i in listed["invites"] if i["invite_id"] == created["invite_id"])
        self.assertEqual(pending["status"], "pending")
        self.assertIsNotNone(pending["invite_token"])

        revoked = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites/{created['invite_id']}/revoke"
        )
        self.assertEqual(revoked.status_code, 200)

        listed2 = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/invites").json()
        revoked_row = next(i for i in listed2["invites"] if i["invite_id"] == created["invite_id"])
        self.assertEqual(revoked_row["status"], "revoked")
        self.assertIsNone(revoked_row["invite_token"])

    # ── API Keys ────────────────────────────────────────────────────────

    def test_api_key_create_raw_once_list_masked_revoke(self):
        owner_client = _build_client(self.db, self.owner_actor)
        created = owner_client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/api-keys",
            json={"client_name": f"ci-bot-{self._suffix}"},
        )
        self.assertEqual(created.status_code, 200)
        raw = created.json()["api_key_raw"]
        self.assertTrue(raw.startswith("ak_"))

        listed = owner_client.get(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/api-keys"
        ).json()
        self.assertEqual(listed["total"], 1)
        key_row = listed["api_keys"][0]
        self.assertNotEqual(key_row.get("api_key_masked", ""), raw)
        self.assertNotIn(raw, str(listed))  # raw key 绝不出现在列表
        self.assertTrue(key_row["api_key_masked"].startswith("****"))
        self.assertTrue(key_row["enabled"])

        client_id = key_row["client_id"]
        revoked = owner_client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/api-keys/{client_id}/revoke"
        )
        self.assertEqual(revoked.status_code, 200)
        listed2 = owner_client.get(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/api-keys"
        ).json()
        self.assertFalse(listed2["api_keys"][0]["enabled"])

    def test_viewer_cannot_manage_api_keys(self):
        viewer_client = _build_client(self.db, self.viewer_actor)
        resp = viewer_client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/api-keys",
            json={"client_name": "nope"},
        )
        self.assertEqual(resp.status_code, 403)

    # ── usage ───────────────────────────────────────────────────────────

    def test_usage_structure(self):
        client = _build_client(self.db, self.viewer_actor)
        resp = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/usage?days=7")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["window_days"], 7)
        self.assertIsInstance(body["api_usage_daily"], list)
        self.assertIsInstance(body["agent_runs_daily"], list)
        self.assertIn("totals", body)

    # ── P1-1：usage 按 workspace 过滤（agent_execution_log 带 workspace_id） ──

    def test_usage_agent_runs_filtered_by_workspace(self):
        from routes.agent_routes import _ensure_agent_log_table

        _ensure_agent_log_table()
        other_ws = f"ws-other-{self._suffix}"
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for ws, rid in ((self.ws["workspace_id"], "own"), (other_ws, "other")):
                cursor.execute(
                    "INSERT INTO agent_execution_log "
                    "(id, query, status, workspace_id, principal_id) "
                    "VALUES (?, ?, 'completed', ?, ?)",
                    (f"test-{self._suffix}-{rid}", f"q-{rid}", ws, f"pr-{rid}"),
                )
            conn.commit()

        client = _build_client(self.db, self.viewer_actor)
        resp = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/usage?days=7")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # 只计本 workspace 的 1 条，其他 workspace 不泄露
        self.assertEqual(body["totals"]["agent_runs"], 1)
        self.assertEqual(body["agent_runs_daily"][0]["runs"], 1)

    def test_agent_log_migration_columns_exist(self):
        """计量迁移：ensure 后 agent_execution_log 含 workspace_id/principal_id。"""
        from routes.agent_routes import _ensure_agent_log_table

        _ensure_agent_log_table()
        with self.db.get_connection() as conn:
            cursor = conn.cursor()
            for col in ("workspace_id", "principal_id"):
                cursor.execute(
                    "SELECT 1 FROM information_schema.columns "
                    "WHERE table_name = 'agent_execution_log' AND column_name = ?",
                    (col,),
                )
                self.assertIsNotNone(cursor.fetchone(), f"missing column {col}")

    # ── P1-2：订阅与配额 ────────────────────────────────────────────────

    def test_subscription_default_starter_without_record(self):
        client = _build_client(self.db, self.viewer_actor)
        resp = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription")
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["plan"], "starter")
        self.assertEqual(body["status"], "active")
        today = body["today"]
        self.assertEqual(today["agent_run_limit"], 50)   # AGENT_RUN_DAILY_LIMITS["starter"]
        self.assertEqual(today["api_unit_limit"], 1000)  # PLAN_DAILY_UNIT_LIMITS["starter"]
        self.assertFalse(today["agent_over_quota"])

    def test_subscription_owner_can_change_plan(self):
        client = _build_client(self.db, self.owner_actor)
        resp = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription",
            json={"plan": "growth"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["plan"], "growth")
        # GET 确认生效（payment_provider=manual，支付预留）
        got = client.get(f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription")
        self.assertEqual(got.json()["plan"], "growth")
        self.assertEqual(got.json()["payment_provider"], "manual")
        self.assertEqual(got.json()["today"]["agent_run_limit"], 200)

    def test_subscription_viewer_cannot_change_plan(self):
        client = _build_client(self.db, self.viewer_actor)
        resp = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription",
            json={"plan": "pro"},
        )
        self.assertEqual(resp.status_code, 403)

    def test_subscription_invalid_plan_rejected(self):
        client = _build_client(self.db, self.owner_actor)
        resp = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription",
            json={"plan": "enterprise"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_subscription_internal_plan_not_self_service(self):
        """internal 为无限配额内部档，不得自助切换（2026-08-14 代码审查）。"""
        client = _build_client(self.db, self.owner_actor)
        resp = client.post(
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription",
            json={"plan": "internal"},
        )
        self.assertEqual(resp.status_code, 422)

    # ── 修改密码（2026-08-14） ─────────────────────────────────────

    def test_password_change_flow(self):
        from access_control import set_principal_password, login_with_password

        set_principal_password(self.db, principal_id=self.owner["principal_id"], password="OldPass-123")
        client = _build_client(self.db, self.owner_actor)
        ws = self.ws["workspace_id"]
        # 旧密码错误 → 401
        resp = client.post("/api/v1/account/password", json={
            "current_password": "WrongPass-1", "new_password": "NewPass-456",
        })
        self.assertEqual(resp.status_code, 401)
        # 正确旧密码 → 修改成功，新密码可登录
        resp = client.post("/api/v1/account/password", json={
            "current_password": "OldPass-123", "new_password": "NewPass-456",
        })
        self.assertEqual(resp.status_code, 200)
        session = login_with_password(self.db, email=self.owner["email"],
                                      password="NewPass-456", workspace_id=ws)
        self.assertIn("access_token", session)

    # ── 邀请接受限流（2026-08-14） ───────────────────────────────────

    def test_invite_accept_rate_limit_blocks_token_probing(self):
        from routes.account_routes import check_invite_accept_rate_limit
        from fastapi import HTTPException

        token = f"probe_{self._suffix}"
        for _ in range(10):
            check_invite_accept_rate_limit(token, "1.2.3.4")
        with self.assertRaises(HTTPException) as ctx:
            check_invite_accept_rate_limit(token, "1.2.3.4")
        self.assertEqual(ctx.exception.status_code, 429)
        # 不同 IP 不受影响
        check_invite_accept_rate_limit(token, "5.6.7.8")

    def test_invite_accept_endpoint_rate_limited(self):
        app = FastAPI()
        app.include_router(account_routes.router)
        client = TestClient(app)
        token = f"probe2_{self._suffix}"
        statuses = []
        for _ in range(11):
            resp = client.post("/api/v1/account/invites/accept", json={
                "invite_token": token, "display_name": "X", "password": "long-enough-pw",
            })
            statuses.append(resp.status_code)
        self.assertIn(429, statuses)


if __name__ == "__main__":
    unittest.main()
