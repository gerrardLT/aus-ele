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


class OrganizationGovernanceRouteTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_orchestrator_db = server.job_orchestrator.db
        server.db = self.db
        server.job_orchestrator.db = self.db

        self.organization = server.create_organization_route(name="Acme")
        self.owner = server.create_principal_route(email="owner@acme.com", display_name="Owner")
        self.member = server.create_principal_route(email="member@acme.com", display_name="Member")
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            role="org_owner",
            status="active",
        )

    def tearDown(self):
        server.db = self.original_db
        server.job_orchestrator.db = self.original_orchestrator_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_owner_can_list_organization_members(self):
        payload = server.list_organization_members_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
        )
        self.assertEqual(len(payload["items"]), 1)

    def test_owner_can_invite_and_suspend_member(self):
        invite = server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="invitee@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        self.assertEqual(invite["status"], "pending")
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.member["principal_id"],
            role="org_member",
            status="active",
        )
        suspended = server.suspend_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.member["principal_id"],
            actor_principal_id=self.owner["principal_id"],
        )
        self.assertEqual(suspended["status"], "suspended")

    def test_owner_can_list_pending_organization_invites(self):
        server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="pending1@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="pending2@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        payload = server.list_organization_invites_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            status="pending",
        )
        self.assertEqual(len(payload["items"]), 2)

    def test_duplicate_pending_invite_is_reused(self):
        invite1 = server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="same@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        invite2 = server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="same@acme.com",
            target_role="org_member",
            expires_at="2026-05-10T00:00:00Z",
        )
        self.assertEqual(invite1["invite_id"], invite2["invite_id"])

    def test_owner_can_reissue_revoked_org_invite(self):
        invite = server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="reissue@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        revoked = server.revoke_organization_invite_route(
            invite_id=invite["invite_id"],
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            revoke_reason="retry_send",
        )
        reissued = server.reissue_organization_invite_route(
            invite_id=revoked["invite_id"],
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            expires_at="2026-05-10T00:00:00Z",
        )
        self.assertEqual(reissued["status"], "pending")
        self.assertNotEqual(reissued["invite_token"], revoked["invite_token"])

    def test_org_member_cannot_create_org_invite(self):
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.member["principal_id"],
            role="org_member",
            status="active",
        )
        with self.assertRaises(HTTPException) as ctx:
            server.create_organization_invite_route(
                organization_id=self.organization["organization_id"],
                principal_id=self.member["principal_id"],
                email="blocked@acme.com",
                target_role="org_member",
                expires_at="2026-05-01T00:00:00Z",
            )
        self.assertEqual(ctx.exception.status_code, 403)

    def test_workspace_admin_cannot_mutate_org_membership(self):
        workspace = server.create_workspace_route(
            organization_id=self.organization["organization_id"], name="Primary"
        )
        server.add_workspace_member_route(
            workspace_id=workspace["workspace_id"],
            principal_id=self.member["principal_id"],
            role="admin",
        )
        with self.assertRaises(HTTPException):
            server.suspend_organization_member_route(
                organization_id=self.organization["organization_id"],
                principal_id=self.owner["principal_id"],
                actor_principal_id=self.member["principal_id"],
            )

    def test_org_member_list_supports_status_role_and_query_filters(self):
        suspended = server.create_principal_route(email="suspended@acme.com", display_name="Suspended User")
        admin = server.create_principal_route(email="admin@acme.com", display_name="Admin User")
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=suspended["principal_id"],
            role="org_member",
            status="suspended",
        )
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=admin["principal_id"],
            role="org_admin",
            status="active",
        )

        payload = server.list_organization_members_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            status="active",
            role="org_admin",
            query="admin@acme.com",
        )

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["principal"]["email"], "admin@acme.com")

    def test_org_admin_can_query_organization_audit_logs_with_filters(self):
        invite = server.create_organization_invite_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            email="audit-filter@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )

        payload = server.list_organization_audit_logs_route(
            organization_id=self.organization["organization_id"],
            principal_id=self.owner["principal_id"],
            action="membership_invite.created",
            target_type="membership_invite",
            query="audit-filter@acme.com",
            limit=50,
        )

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["target_id"], invite["invite_id"])

    def test_bulk_member_update_route_can_suspend_multiple_members(self):
        member_a = server.create_principal_route(email="bulk-a@acme.com", display_name="Bulk A")
        member_b = server.create_principal_route(email="bulk-b@acme.com", display_name="Bulk B")
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=member_a["principal_id"],
            role="org_member",
            status="active",
        )
        server.add_organization_member_route(
            organization_id=self.organization["organization_id"],
            principal_id=member_b["principal_id"],
            role="org_member",
            status="active",
        )

        payload = server.bulk_update_organization_members_route(
            organization_id=self.organization["organization_id"],
            actor_principal_id=self.owner["principal_id"],
            principal_ids=f"{member_a['principal_id']},{member_b['principal_id']}",
            operation="suspend",
        )

        self.assertEqual(payload["operation"], "suspend")
        self.assertEqual(len(payload["items"]), 2)
        self.assertTrue(all(item["status"] == "suspended" for item in payload["items"]))

    def test_domain_join_route_creates_org_membership_under_domain_auto_join_policy(self):
        server.create_organization_domain_route(
            organization_id=self.organization["organization_id"],
            domain="acme.com",
            join_mode="domain_auto_join_org",
        )

        payload = server.domain_join_route(
            organization_id=self.organization["organization_id"],
            email="joiner@acme.com",
            display_name="Joiner",
            password="Welc0mePass!",
        )

        self.assertEqual(payload["principal"]["email"], "joiner@acme.com")
        self.assertEqual(payload["organization_membership"]["status"], "active")
        self.assertFalse(payload["workspace_access_ready"])

    def test_domain_join_route_rejects_invite_only_policy(self):
        server.create_organization_domain_route(
            organization_id=self.organization["organization_id"],
            domain="acme.com",
            join_mode="invite_only",
        )

        with self.assertRaises(HTTPException) as ctx:
            server.domain_join_route(
                organization_id=self.organization["organization_id"],
                email="blocked@acme.com",
                display_name="Blocked",
                password="Welc0mePass!",
            )

        self.assertEqual(ctx.exception.status_code, 403)
