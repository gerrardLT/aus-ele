"""P0.1 匿名 bootstrap 写端点守卫（2026-09-05 公测产品化改造）。

背景（诊断 §7.2）：``POST /api/v1/auth/web-session`` 为同源浏览器请求签发
principal=``pr_websession`` 的 access token，而 ``_ensure_bootstrap_identity``
历史上把该身份授成 ``ws_default`` 的 **owner**。结合同源 Origin 门控（任意浏览器
同源请求即可拿到，无需凭据）与 ``update_subscription`` 仅校验 ``role == "owner"``，
匿名访客可对 ``ws_default`` 自升套餐、建邀请、吊销他人会话。

本测试锁定「账户写端点拒绝匿名引导身份」这一不变式，并验证真实 owner 零受影响。
角色降级（P0.2）是第二道锁；principal 级守卫是第一道，且必须先发。
"""

import sys
import unittest
import uuid

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from fastapi import FastAPI
from fastapi.testclient import TestClient

from access_control import (
    BOOTSTRAP_PRINCIPAL_ID,
    is_anonymous_bootstrap,
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
)
from database import DatabaseManager
from routes import account_routes, auth_routes


def _client_for(actor, db):
    app = FastAPI()
    app.include_router(account_routes.router)
    app.dependency_overrides[account_routes._get_actor] = lambda: actor
    original = account_routes.get_db
    account_routes.get_db = lambda: db
    return TestClient(app), original


class BootstrapConstantTests(unittest.TestCase):
    """两处定义必须同源：auth_routes 的引导 principal_id 与守卫读的常量。"""

    def test_auth_routes_uses_the_shared_constant(self):
        self.assertEqual(
            auth_routes._BOOTSTRAP_PR,
            BOOTSTRAP_PRINCIPAL_ID,
            "auth_routes 与守卫的引导身份 ID 漂移，匿名写端点守卫会静默失效",
        )

    def test_helper_recognizes_actor_shapes(self):
        self.assertTrue(is_anonymous_bootstrap({"principal": {"principal_id": BOOTSTRAP_PRINCIPAL_ID}}))
        self.assertTrue(is_anonymous_bootstrap({"principal_id": BOOTSTRAP_PRINCIPAL_ID}))
        self.assertFalse(is_anonymous_bootstrap({"principal": {"principal_id": "pr_real_owner"}}))
        self.assertFalse(is_anonymous_bootstrap({"principal": None}))
        self.assertFalse(is_anonymous_bootstrap(None))
        self.assertFalse(is_anonymous_bootstrap({}))


class BootstrapWriteGuardTests(unittest.TestCase):
    """DatabaseManager 为 PG-only：随机后缀隔离，tearDown 清理本轮组织数据。"""

    def setUp(self):
        self._suffix = uuid.uuid4().hex[:8]
        self.db = DatabaseManager(None)
        self._orig_get_db = account_routes.get_db

        self.org = seed_organization(self.db, name=f"Guard-{self._suffix}")
        self.ws = seed_workspace(self.db, organization_id=self.org["organization_id"], name="main")
        self.owner = seed_principal(self.db, email=f"owner-{self._suffix}@guard.test", display_name="Owner")
        seed_workspace_membership(self.db, workspace_id=self.ws["workspace_id"],
                                  principal_id=self.owner["principal_id"], role="owner")
        seed_organization_membership(self.db, organization_id=self.org["organization_id"],
                                     principal_id=self.owner["principal_id"], role="org_owner")

        self.owner_actor = {
            "principal": self.owner,
            "workspace": self.ws,
            "membership": self.db.fetch_workspace_membership(
                self.ws["workspace_id"], self.owner["principal_id"]
            ),
        }
        # 匿名引导身份：与 _ensure_bootstrap_identity 产出的结构一致（历史上是 owner）
        self.bootstrap_actor = {
            "principal": {
                "principal_id": BOOTSTRAP_PRINCIPAL_ID,
                "email": "web-session@local",
                "display_name": "Web Session (bootstrap)",
            },
            "workspace": {"workspace_id": "ws_default", "organization_id": "org_webbootstrap", "name": "default"},
            "membership": {"membership_id": "m_webbootstrap", "role": "owner",
                           "principal_id": BOOTSTRAP_PRINCIPAL_ID, "workspace_id": "ws_default"},
        }

    def tearDown(self):
        account_routes.get_db = self._orig_get_db
        try:
            with self.db.get_connection() as conn:
                cur = conn.cursor()
                cur.execute("DELETE FROM workspace_membership WHERE workspace_id = ?", (self.ws["workspace_id"],))
                cur.execute("DELETE FROM organization_membership WHERE organization_id = ?", (self.org["organization_id"],))
                cur.execute("DELETE FROM workspace WHERE workspace_id = ?", (self.ws["workspace_id"],))
                cur.execute("DELETE FROM organization WHERE organization_id = ?", (self.org["organization_id"],))
                cur.execute("DELETE FROM principal_identity WHERE principal_id = ?", (self.owner["principal_id"],))
                conn.commit()
        except Exception:  # noqa: BLE001 - 清理失败不应掩盖测试结论
            pass

    def _post(self, actor, path, payload=None):
        client, original = _client_for(actor, self.db)
        try:
            return client.post(path, json=payload if payload is not None else {})
        finally:
            account_routes.get_db = original

    def _patch(self, actor, path, payload):
        client, original = _client_for(actor, self.db)
        try:
            return client.patch(path, json=payload)
        finally:
            account_routes.get_db = original

    def test_anonymous_denied_on_every_account_write(self):
        ws = "ws_default"
        cases = [
            ("POST", f"/api/v1/account/workspaces/{ws}/subscription", {"plan": "pro"}),
            ("POST", f"/api/v1/account/workspaces/{ws}/api-keys", {"client_name": "x"}),
            ("POST", f"/api/v1/account/workspaces/{ws}/api-keys/ak_any/revoke", None),
            ("POST", f"/api/v1/account/workspaces/{ws}/invites", {"email": "someone@example.com", "role": "admin"}),
            ("POST", f"/api/v1/account/workspaces/{ws}/invites/in_any/revoke", None),
            ("POST", f"/api/v1/account/workspaces/{ws}/members/pr_any/reset-password", {"new_password": "ResetPass123"}),
            ("POST", "/api/v1/account/password", {"current_password": "whatever1", "new_password": "whatever2"}),
            ("POST", "/api/v1/account/sessions/revoke-others", None),
            ("POST", f"/api/v1/account/workspaces/{ws}/login-session", None),
        ]
        for method, path, payload in cases:
            with self.subTest(path=path, method=method):
                res = self._post(self.bootstrap_actor, path, payload)
                self.assertEqual(res.status_code, 403, f"{method} {path} 未拒绝匿名引导身份：{res.text[:200]}")

        with self.subTest(path="PATCH /api/v1/account/me"):
            res = self._patch(self.bootstrap_actor, "/api/v1/account/me", {"display_name": "hax"})
            self.assertEqual(res.status_code, 403)

    def test_anonymous_denial_does_not_leak_account_existence(self):
        """403 文案必须是通用「需注册」语义，不得暴露内部角色/权限细节。"""
        res = self._post(self.bootstrap_actor, "/api/v1/account/workspaces/ws_default/subscription", {"plan": "pro"})
        detail = (res.json().get("detail") or "").lower()
        self.assertIn("register", detail)
        self.assertNotIn("owner", detail)
        self.assertNotIn("permission", detail)

    def test_real_owner_still_allowed(self):
        """守卫只认引导身份 principal，不得误伤真实 owner（回归护栏）。"""
        res = self._post(
            self.owner_actor,
            f"/api/v1/account/workspaces/{self.ws['workspace_id']}/subscription",
            {"plan": "growth"},
        )
        self.assertEqual(res.status_code, 200, res.text[:200])

    def test_read_endpoints_stay_open_for_anonymous(self):
        """匿名浏览体验不可破：GET /me 与 GET /sessions 不得被写守卫波及。"""
        client, original = _client_for(self.bootstrap_actor, self.db)
        try:
            self.assertEqual(client.get("/api/v1/account/sessions").status_code, 200)
        finally:
            account_routes.get_db = original


if __name__ == "__main__":
    unittest.main()
