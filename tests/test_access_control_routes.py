import os
import sys
import tempfile
import types
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


class AccessControlRouteTests(unittest.TestCase):
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

    def _bootstrap_owner_token(self):
        org = server.create_organization_route(name="Acme Energy")
        principal = server.create_principal_route(email="owner@example.com", display_name="Owner")
        workspace = server.create_workspace_route(organization_id=org["organization_id"], name="Primary")
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="owner",
        )
        token = server.create_access_token_route(principal_id=principal["principal_id"], workspace_id=workspace["workspace_id"])
        return org, principal, workspace, token["token"]

    def test_owner_can_list_workspace_members_and_export_permission(self):
        _, _, workspace, token = self._bootstrap_owner_token()

        members = server.list_workspace_members_route(workspace_id=workspace["workspace_id"], x_access_token=token)
        export_access = server.get_workspace_export_permission_route(workspace_id=workspace["workspace_id"], x_access_token=token)

        self.assertEqual(len(members["items"]), 1)
        self.assertTrue(export_access["allowed"])
        self.assertEqual(export_access["role"], "owner")

    def test_audit_logs_route_returns_entries_for_owner(self):
        _, _, workspace, token = self._bootstrap_owner_token()

        payload = server.list_audit_logs_route(x_access_token=token, workspace_id=workspace["workspace_id"], limit=50)

        self.assertGreaterEqual(len(payload["items"]), 3)
        self.assertEqual(payload["items"][0]["workspace_id"], workspace["workspace_id"])

    def test_login_and_session_routes_return_authenticated_actor(self):
        org, principal, workspace, _ = self._bootstrap_owner_token()
        server.seed_organization_membership(
            server.db,
            organization_id=org["organization_id"],
            principal_id=principal["principal_id"],
            role="org_owner",
            status="active",
        )
        server.set_password_route(principal_id=principal["principal_id"], password="Str0ngPass!")

        session = server.login_route(email="owner@example.com", password="Str0ngPass!", workspace_id=workspace["workspace_id"])
        actor = server.get_session_route(x_session_token=session["session_token"])

        self.assertEqual(actor["principal"]["principal_id"], principal["principal_id"])
        self.assertEqual(actor["workspace"]["workspace_id"], workspace["workspace_id"])
        self.assertIn("access_token", session)
        refreshed = server.refresh_session_route(x_session_token=session["session_token"])
        self.assertIn("access_token", refreshed)
        self.assertNotEqual(session["access_token"], refreshed["access_token"])

    def test_logout_route_revokes_refresh(self):
        org, principal, workspace, _ = self._bootstrap_owner_token()
        server.seed_organization_membership(
            server.db,
            organization_id=org["organization_id"],
            principal_id=principal["principal_id"],
            role="org_owner",
            status="active",
        )
        server.set_password_route(principal_id=principal["principal_id"], password="Str0ngPass!")
        session = server.login_route(email="owner@example.com", password="Str0ngPass!", workspace_id=workspace["workspace_id"])

        payload = server.logout_route(x_session_token=session["session_token"])

        self.assertEqual(payload["status"], "ok")
        with self.assertRaises(server.HTTPException) as ctx:
            server.refresh_session_route(x_session_token=session["session_token"])
        self.assertEqual(ctx.exception.status_code, 401)

    def test_invite_accept_and_revoke_routes_work(self):
        _, principal, workspace, token = self._bootstrap_owner_token()
        invite = server.create_workspace_invite_route(
            workspace_id=workspace["workspace_id"],
            email="invitee@example.com",
            role="analyst",
            x_access_token=token,
        )

        accepted = server.accept_workspace_invite_route(
            invite_token=invite["invite_token"],
            display_name="Invitee",
            password="Welc0mePass!",
        )
        self.assertEqual(accepted["workspace"]["workspace_id"], workspace["workspace_id"])

        invite2 = server.create_workspace_invite_route(
            workspace_id=workspace["workspace_id"],
            email="invitee2@example.com",
            role="viewer",
            x_access_token=token,
        )
        revoked = server.revoke_workspace_invite_route(invite_id=invite2["invite_id"], x_access_token=token)
        self.assertTrue(revoked["revoked"])
