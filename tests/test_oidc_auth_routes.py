import contextlib
import os
import sys
import tempfile
import unittest
import uuid
from unittest import mock

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from database import DatabaseManager
import server


class OidcAuthRouteTests(unittest.TestCase):
    """随机后缀隔离（2026-08-14 技术债修复）：DatabaseManager 为 PG-only，
    temp path 被忽略直连共享库；邮箱/域名/OIDC subject 均带随机后缀，可重复运行。

    P0.5（2026-09-05）：/api/auth/oidc/callback 默认关闭 → 本类断言本体不变，
    只在 fixture 里显式开启 AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK。
    默认关闭的行为由 LegacyOidcCallbackDisabledTests 单独锁定。
    """

    def setUp(self):
        self._s = uuid.uuid4().hex[:8]
        self._legacy_flag = mock.patch.dict(os.environ, {"AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK": "true"})
        self._legacy_flag.start()
        self.addCleanup(self._legacy_flag.stop)
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_orchestrator_db = server.job_orchestrator.db
        server.db = self.db
        server.job_orchestrator.db = self.db

    def tearDown(self):
        server.db = self.original_db
        server.job_orchestrator.db = self.original_orchestrator_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _email(self, name: str) -> str:
        return f"{name}-{self._s}@acme-{self._s}.com"

    def _domain(self) -> str:
        return f"acme-{self._s}.com"

    def _bootstrap_oidc_org(self):
        org = server.create_organization_route(name=f"Acme Energy-{self._s}")
        provider = server.create_oidc_provider_route(
            organization_id=org["organization_id"],
            provider_key="google",
            issuer="https://accounts.google.com",
            discovery_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id=f"client-{self._s}",
            client_secret=f"secret-{self._s}",
            scopes="openid,email,profile",
        )
        domain = server.create_organization_domain_route(
            organization_id=org["organization_id"],
            domain=self._domain(),
            join_mode="invite_only",
        )
        workspace = server.create_workspace_route(organization_id=org["organization_id"], name="Primary")
        return org, provider, domain, workspace

    def test_admin_can_create_oidc_provider_and_domain(self):
        org = server.create_organization_route(name=f"Acme Energy-{self._s}")
        provider = server.create_oidc_provider_route(
            organization_id=org["organization_id"],
            provider_key="google",
            issuer="https://accounts.google.com",
            discovery_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id=f"client-{self._s}",
            client_secret=f"secret-{self._s}",
            scopes="openid,email,profile",
        )
        domain = server.create_organization_domain_route(
            organization_id=org["organization_id"],
            domain=self._domain(),
            join_mode="invite_only",
        )

        self.assertEqual(provider["organization_id"], org["organization_id"])
        self.assertEqual(provider["provider_key"], "google")
        self.assertEqual(domain["domain"], self._domain())

    def test_oidc_start_route_returns_redirect_payload(self):
        org, _, _, _ = self._bootstrap_oidc_org()

        response = server.start_oidc_login_route(
            organization_id=org["organization_id"],
            provider_key="google",
            redirect_uri="https://app.example.com/api/auth/oidc/callback",
        )

        self.assertIn("authorization_url", response)
        self.assertEqual(response["organization_id"], org["organization_id"])
        self.assertEqual(response["provider_key"], "google")
        self.assertIn("state=", response["authorization_url"])
        self.assertIn("nonce=", response["authorization_url"])

    def test_oidc_callback_creates_local_session_for_matching_domain(self):
        org, _, domain, workspace = self._bootstrap_oidc_org()
        self.db.upsert_organization_domain(
            {
                **domain,
                "join_mode": "domain_auto_join_org",
                "verified_at": "2026-04-28T00:00:00Z",
            }
        )
        principal = server.create_principal_route(email=self._email("owner"), display_name="Owner")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )

        result = server.complete_oidc_callback_route(
            organization_id=org["organization_id"],
            provider_key="google",
            subject=f"google-sub-1-{self._s}",
            email=self._email("owner"),
            email_verified=True,
            display_name="Owner",
            workspace_id=workspace["workspace_id"],
            state="state-1",
            expected_state="state-1",
            nonce="nonce-1",
            expected_nonce="nonce-1",
        )

        self.assertIn("session_token", result["session"])
        actor = server.get_session_route(x_session_token=result["session"]["session_token"])
        self.assertEqual(actor["principal"]["email"], self._email("owner"))
        self.assertEqual(actor["session"]["auth_method"], "oidc")
        self.assertEqual(actor["organization_membership"]["status"], "active")

    def test_oidc_callback_rejects_invite_only_domain_join_without_existing_org_membership(self):
        org, _, _, workspace = self._bootstrap_oidc_org()
        principal = server.create_principal_route(email=self._email("blocked"), display_name="Blocked")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )

        with self.assertRaises(HTTPException) as ctx:
            server.complete_oidc_callback_route(
                organization_id=org["organization_id"],
                provider_key="google",
                subject=f"google-sub-blocked-{self._s}",
                email=self._email("blocked"),
                email_verified=True,
                display_name="Blocked",
                workspace_id=workspace["workspace_id"],
                state="state-1",
                expected_state="state-1",
                nonce="nonce-1",
                expected_nonce="nonce-1",
            )

        self.assertEqual(ctx.exception.status_code, 403)

    def test_logout_route_revokes_oidc_session(self):
        org, _, domain, workspace = self._bootstrap_oidc_org()
        self.db.upsert_organization_domain(
            {
                **domain,
                "join_mode": "domain_auto_join_org",
                "verified_at": "2026-04-28T00:00:00Z",
            }
        )
        principal = server.create_principal_route(email=self._email("viewer"), display_name="Viewer")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )
        result = server.complete_oidc_callback_route(
            organization_id=org["organization_id"],
            provider_key="google",
            subject=f"google-sub-2-{self._s}",
            email=self._email("viewer"),
            email_verified=True,
            display_name="Viewer",
            workspace_id=workspace["workspace_id"],
            state="state-2",
            expected_state="state-2",
            nonce="nonce-2",
            expected_nonce="nonce-2",
        )

        logout_result = server.logout_route(x_session_token=result["session"]["session_token"])
        self.assertEqual(logout_result["status"], "ok")

        with self.assertRaises(HTTPException):
            server.get_session_route(x_session_token=result["session"]["session_token"])

    def test_oidc_flow_writes_audit_records(self):
        org, _, domain, workspace = self._bootstrap_oidc_org()
        self.db.upsert_organization_domain(
            {
                **domain,
                "join_mode": "domain_auto_join_org",
                "verified_at": "2026-04-28T00:00:00Z",
            }
        )
        principal = server.create_principal_route(email=self._email("audit"), display_name="Audit")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )
        result = server.complete_oidc_callback_route(
            organization_id=org["organization_id"],
            provider_key="google",
            subject=f"google-sub-3-{self._s}",
            email=self._email("audit"),
            email_verified=True,
            display_name="Audit",
            workspace_id=workspace["workspace_id"],
            state="state-3",
            expected_state="state-3",
            nonce="nonce-3",
            expected_nonce="nonce-3",
        )

        server.logout_route(x_session_token=result["session"]["session_token"])
        logs = self.db.fetch_audit_logs(limit=50)
        actions = {item["action"] for item in logs}

        self.assertIn("auth.oidc_login", actions)
        self.assertIn("auth.session_revoked", actions)


class LegacyOidcCallbackDisabledTests(unittest.TestCase):
    """P0.5：默认关闭的守卫本身。

    刻意不搭 DB fixture —— 守卫必须在任何数据库查询之前触发，否则关闭只是
    「查完库再拒绝」，仍然会泄露 provider/workspace 存在性。
    """

    def _call(self):
        return server.complete_oidc_callback_route(
            organization_id="org_missing",
            provider_key="google",
            subject="sub-x",
            email="victim@example.com",
            email_verified=True,
            display_name="Victim",
            workspace_id="ws_missing",
            state="s",
            expected_state="s",
            nonce="n",
            expected_nonce="n",
        )

    @contextlib.contextmanager
    def _flag_unset(self):
        """只摘掉这一个 key。

        不用 ``patch.dict(..., clear=True)`` —— 那会连带清掉 PG/Redis/JWT 连接
        环境变量，让「守卫先于任何 DB 查询」这一点失去可信的测试环境。
        """
        saved = os.environ.pop("AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK", None)
        try:
            yield
        finally:
            if saved is not None:
                os.environ["AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK"] = saved
            else:
                os.environ.pop("AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK", None)

    def test_callback_disabled_by_default(self):
        with self._flag_unset():
            with self.assertRaises(HTTPException) as ctx:
                self._call()
        self.assertEqual(ctx.exception.status_code, 501)

    def test_falsy_env_values_keep_it_closed(self):
        for raw in ("false", "0", "no", "off", ""):
            with self.subTest(value=raw), mock.patch.dict(
                os.environ, {"AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK": raw}
            ):
                with self.assertRaises(HTTPException) as ctx:
                    self._call()
                self.assertEqual(ctx.exception.status_code, 501)

    def test_explicit_true_reopens_without_code_change(self):
        # 回滚路径 = 设环境变量重启，零代码：开启后必须越过守卫、进到 provider 查询
        with mock.patch.dict(
            os.environ, {"AUS_ELE_ENABLE_LEGACY_OIDC_CALLBACK": "true"}
        ):
            with self.assertRaises(HTTPException) as ctx:
                self._call()
        self.assertEqual(ctx.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
