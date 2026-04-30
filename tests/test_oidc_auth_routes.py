import os
import sys
import tempfile
import types
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


class OidcAuthRouteTests(unittest.TestCase):
    def setUp(self):
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

    def _bootstrap_oidc_org(self):
        org = server.create_organization_route(name="Acme Energy")
        provider = server.create_oidc_provider_route(
            organization_id=org["organization_id"],
            provider_key="google",
            issuer="https://accounts.google.com",
            discovery_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id="client-123",
            client_secret="secret-123",
            scopes="openid,email,profile",
        )
        domain = server.create_organization_domain_route(
            organization_id=org["organization_id"],
            domain="acme.com",
            join_mode="invite_only",
        )
        workspace = server.create_workspace_route(organization_id=org["organization_id"], name="Primary")
        return org, provider, domain, workspace

    def test_admin_can_create_oidc_provider_and_domain(self):
        org = server.create_organization_route(name="Acme Energy")
        provider = server.create_oidc_provider_route(
            organization_id=org["organization_id"],
            provider_key="google",
            issuer="https://accounts.google.com",
            discovery_url="https://accounts.google.com/.well-known/openid-configuration",
            client_id="client-123",
            client_secret="secret-123",
            scopes="openid,email,profile",
        )
        domain = server.create_organization_domain_route(
            organization_id=org["organization_id"],
            domain="acme.com",
            join_mode="invite_only",
        )

        self.assertEqual(provider["organization_id"], org["organization_id"])
        self.assertEqual(provider["provider_key"], "google")
        self.assertEqual(domain["domain"], "acme.com")

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
            }
        )
        principal = server.create_principal_route(email="owner@acme.com", display_name="Owner")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )

        result = server.complete_oidc_callback_route(
            organization_id=org["organization_id"],
            provider_key="google",
            subject="google-sub-1",
            email="owner@acme.com",
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
        self.assertEqual(actor["principal"]["email"], "owner@acme.com")
        self.assertEqual(actor["session"]["auth_method"], "oidc")
        self.assertEqual(actor["organization_membership"]["status"], "active")

    def test_oidc_callback_rejects_invite_only_domain_join_without_existing_org_membership(self):
        org, _, _, workspace = self._bootstrap_oidc_org()
        principal = server.create_principal_route(email="blocked@acme.com", display_name="Blocked")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )

        with self.assertRaises(HTTPException) as ctx:
            server.complete_oidc_callback_route(
                organization_id=org["organization_id"],
                provider_key="google",
                subject="google-sub-blocked",
                email="blocked@acme.com",
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
            }
        )
        principal = server.create_principal_route(email="viewer@acme.com", display_name="Viewer")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )
        result = server.complete_oidc_callback_route(
            organization_id=org["organization_id"],
            provider_key="google",
            subject="google-sub-2",
            email="viewer@acme.com",
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
            }
        )
        principal = server.create_principal_route(email="audit@acme.com", display_name="Audit")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )
        result = server.complete_oidc_callback_route(
            organization_id=org["organization_id"],
            provider_key="google",
            subject="google-sub-3",
            email="audit@acme.com",
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
