import os
import tempfile
import unittest
from unittest.mock import patch

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from access_control import (
    ORG_ROLE_PERMISSIONS,
    accept_membership_invite,
    authenticate_org_actor,
    authenticate_access_token,
    authenticate_session_token,
    check_organization_permission,
    create_membership_invite,
    join_organization_by_domain,
    login_with_password,
    reactivate_organization_member,
    remove_organization_member,
    reissue_membership_invite,
    revoke_membership_invite,
    set_principal_password,
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
    suspend_organization_member,
    transfer_organization_owner,
)
from database import DatabaseManager


class OrganizationGovernanceDatabaseTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.organization = self.db.upsert_organization(
            {
                "organization_id": "org_acme",
                "name": "Acme",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.owner = self.db.upsert_principal(
            {
                "principal_id": "pr_owner",
                "email": "owner@acme.com",
                "display_name": "Owner",
                "password_hash": None,
                "password_salt": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_organization_membership_round_trip(self):
        membership = self.db.upsert_organization_membership(
            {
                "organization_membership_id": "om_1",
                "organization_id": self.organization["organization_id"],
                "principal_id": self.owner["principal_id"],
                "role": "org_owner",
                "status": "active",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        fetched = self.db.fetch_organization_membership(
            self.organization["organization_id"], self.owner["principal_id"]
        )
        self.assertEqual(membership["role"], fetched["role"])
        self.assertEqual(fetched["status"], "active")

    def test_list_organization_memberships_returns_multiple_members(self):
        for idx in range(2):
            principal_id = f"pr_{idx}"
            self.db.upsert_principal(
                {
                    "principal_id": principal_id,
                    "email": f"user{idx}@acme.com",
                    "display_name": f"User {idx}",
                    "password_hash": None,
                    "password_salt": None,
                    "created_at": "2026-04-28T00:00:00Z",
                    "updated_at": "2026-04-28T00:00:00Z",
                }
            )
            self.db.upsert_organization_membership(
                {
                    "organization_membership_id": f"om_{idx}",
                    "organization_id": self.organization["organization_id"],
                    "principal_id": principal_id,
                    "role": "org_member",
                    "status": "active",
                    "created_at": "2026-04-28T00:00:00Z",
                    "updated_at": "2026-04-28T00:00:00Z",
                }
            )
        items = self.db.list_organization_memberships(self.organization["organization_id"])
        self.assertEqual(len(items), 2)

    def test_membership_invite_round_trip_supports_org_scope(self):
        invite = self.db.upsert_membership_invite(
            {
                "invite_id": "inv_org_1",
                "organization_id": self.organization["organization_id"],
                "workspace_id": None,
                "target_scope_type": "organization",
                "email": "analyst@acme.com",
                "target_role": "org_member",
                "invite_token": "invite-token-1",
                "status": "pending",
                "invited_by_principal_id": self.owner["principal_id"],
                "accepted_by_principal_id": None,
                "revoked_by_principal_id": None,
                "expires_at": "2026-05-01T00:00:00Z",
                "accepted_at": None,
                "revoked_at": None,
                "revoke_reason": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        fetched = self.db.fetch_membership_invite(invite["invite_id"])
        self.assertEqual(fetched["target_scope_type"], "organization")
        self.assertEqual(fetched["status"], "pending")

    def test_membership_invite_can_be_fetched_by_token(self):
        self.db.upsert_membership_invite(
            {
                "invite_id": "inv_org_2",
                "organization_id": self.organization["organization_id"],
                "workspace_id": None,
                "target_scope_type": "organization",
                "email": "analyst@acme.com",
                "target_role": "org_member",
                "invite_token": "invite-token-2",
                "status": "pending",
                "invited_by_principal_id": self.owner["principal_id"],
                "accepted_by_principal_id": None,
                "revoked_by_principal_id": None,
                "expires_at": "2026-05-01T00:00:00Z",
                "accepted_at": None,
                "revoked_at": None,
                "revoke_reason": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        invite = self.db.fetch_membership_invite_by_token("invite-token-2")
        self.assertEqual(invite["email"], "analyst@acme.com")

    def test_list_membership_invites_can_filter_by_status(self):
        self.db.upsert_membership_invite(
            {
                "invite_id": "inv_org_3",
                "organization_id": self.organization["organization_id"],
                "workspace_id": None,
                "target_scope_type": "organization",
                "email": "pending@acme.com",
                "target_role": "org_member",
                "invite_token": "invite-token-3",
                "status": "pending",
                "invited_by_principal_id": self.owner["principal_id"],
                "accepted_by_principal_id": None,
                "revoked_by_principal_id": None,
                "expires_at": "2026-05-01T00:00:00Z",
                "accepted_at": None,
                "revoked_at": None,
                "revoke_reason": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.db.upsert_membership_invite(
            {
                "invite_id": "inv_org_4",
                "organization_id": self.organization["organization_id"],
                "workspace_id": None,
                "target_scope_type": "organization",
                "email": "accepted@acme.com",
                "target_role": "org_member",
                "invite_token": "invite-token-4",
                "status": "accepted",
                "invited_by_principal_id": self.owner["principal_id"],
                "accepted_by_principal_id": "pr_other",
                "revoked_by_principal_id": None,
                "expires_at": "2026-05-01T00:00:00Z",
                "accepted_at": "2026-04-28T01:00:00Z",
                "revoked_at": None,
                "revoke_reason": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T01:00:00Z",
            }
        )
        items = self.db.list_membership_invites(self.organization["organization_id"], status="pending")
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0]["email"], "pending@acme.com")


class OrganizationGovernanceAccessControlTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.organization = seed_organization(self.db, name="Acme")
        self.owner_principal = seed_principal(self.db, email="owner@acme.com", display_name="Owner")
        self.member_principal = seed_principal(self.db, email="member@acme.com", display_name="Member")
        self.owner_membership = seed_organization_membership(
            self.db,
            organization_id=self.organization["organization_id"],
            principal_id=self.owner_principal["principal_id"],
            role="org_owner",
            status="active",
        )
        self.member_membership = seed_organization_membership(
            self.db,
            organization_id=self.organization["organization_id"],
            principal_id=self.member_principal["principal_id"],
            role="org_member",
            status="active",
        )
        self.org_owner_actor = authenticate_org_actor(
            self.db, self.organization["organization_id"], self.owner_principal["principal_id"]
        )
        self.pending_invite = create_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            workspace_id=None,
            target_scope_type="organization",
            email="invitee@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_org_owner_contains_governance_permissions(self):
        self.assertIn("org_manage", ORG_ROLE_PERMISSIONS["org_owner"])
        self.assertIn("member_manage", ORG_ROLE_PERMISSIONS["org_owner"])

    def test_authenticate_org_actor_uses_active_organization_membership(self):
        actor = authenticate_org_actor(
            self.db, self.organization["organization_id"], self.owner_principal["principal_id"]
        )
        self.assertEqual(actor["organization_membership"]["role"], "org_owner")

    def test_check_organization_permission_rejects_org_member_for_org_manage(self):
        actor = {
            "organization_membership": {"role": "org_member", "status": "active"},
        }
        with self.assertRaises(HTTPException) as ctx:
            check_organization_permission(actor, "org_manage")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_org_admin_can_create_org_invite(self):
        invite = create_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            workspace_id=None,
            target_scope_type="organization",
            email="invitee2@acme.com",
            target_role="org_member",
            expires_at="2026-05-01T00:00:00Z",
        )
        self.assertEqual(invite["status"], "pending")
        self.assertEqual(invite["target_scope_type"], "organization")

    def test_create_membership_invite_reuses_existing_pending_invite(self):
        invite = create_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            workspace_id=None,
            target_scope_type="organization",
            email="invitee@acme.com",
            target_role="org_member",
            expires_at="2026-05-03T00:00:00Z",
        )
        self.assertEqual(invite["invite_id"], self.pending_invite["invite_id"])
        self.assertEqual(invite["status"], "pending")

    def test_revoke_membership_invite_marks_status_and_reason(self):
        revoked = revoke_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            invite_id=self.pending_invite["invite_id"],
            revoke_reason="duplicate",
        )
        self.assertEqual(revoked["status"], "revoked")
        self.assertEqual(revoked["revoke_reason"], "duplicate")

    def test_accept_org_invite_creates_active_org_membership(self):
        accepted = accept_membership_invite(
            self.db,
            invite_token=self.pending_invite["invite_token"],
            display_name="Invitee",
        )
        membership = self.db.fetch_organization_membership(
            self.organization["organization_id"], accepted["principal"]["principal_id"]
        )
        self.assertEqual(membership["status"], "active")
        self.assertEqual(membership["role"], "org_member")

    def test_accept_org_invite_rejects_expired_invite(self):
        expired_invite = create_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            workspace_id=None,
            target_scope_type="organization",
            email="expired@acme.com",
            target_role="org_member",
            expires_at="2026-04-01T00:00:00Z",
        )
        with patch("access_control._utc_now_iso", return_value="2026-04-28T00:00:00Z"):
            with self.assertRaises(HTTPException) as ctx:
                accept_membership_invite(
                    self.db,
                    invite_token=expired_invite["invite_token"],
                    display_name="Expired",
                )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_revoke_membership_invite_rejects_accepted_invite(self):
        accepted = accept_membership_invite(
            self.db,
            invite_token=self.pending_invite["invite_token"],
            display_name="Invitee",
        )
        self.assertIsNotNone(accepted["organization_membership"])
        with self.assertRaises(HTTPException) as ctx:
            revoke_membership_invite(
                self.db,
                actor=self.org_owner_actor,
                invite_id=self.pending_invite["invite_id"],
                revoke_reason="late_revoke",
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_reissue_membership_invite_rotates_token_and_returns_pending_status(self):
        revoked = revoke_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            invite_id=self.pending_invite["invite_id"],
            revoke_reason="refresh_delivery",
        )
        reissued = reissue_membership_invite(
            self.db,
            actor=self.org_owner_actor,
            invite_id=revoked["invite_id"],
            expires_at="2026-05-10T00:00:00Z",
        )
        self.assertEqual(reissued["status"], "pending")
        self.assertNotEqual(reissued["invite_token"], revoked["invite_token"])
        self.assertEqual(reissued["expires_at"], "2026-05-10T00:00:00Z")

    def test_reissue_membership_invite_rejects_accepted_invite(self):
        accepted = accept_membership_invite(
            self.db,
            invite_token=self.pending_invite["invite_token"],
            display_name="Invitee",
        )
        self.assertIsNotNone(accepted["organization_membership"])
        with self.assertRaises(HTTPException) as ctx:
            reissue_membership_invite(
                self.db,
                actor=self.org_owner_actor,
                invite_id=self.pending_invite["invite_id"],
                expires_at="2026-05-10T00:00:00Z",
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_suspend_and_reactivate_organization_member(self):
        suspended = suspend_organization_member(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            principal_id=self.member_principal["principal_id"],
        )
        self.assertEqual(suspended["status"], "suspended")
        reactivated = reactivate_organization_member(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            principal_id=self.member_principal["principal_id"],
        )
        self.assertEqual(reactivated["status"], "active")

    def test_remove_organization_member_marks_removed(self):
        removed = remove_organization_member(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            principal_id=self.member_principal["principal_id"],
        )
        self.assertEqual(removed["status"], "removed")

    def test_remove_organization_member_revokes_existing_auth_context(self):
        workspace = seed_workspace(
            self.db,
            organization_id=self.organization["organization_id"],
            name="Primary",
        )
        seed_workspace_membership(
            self.db,
            workspace_id=workspace["workspace_id"],
            principal_id=self.member_principal["principal_id"],
            role="analyst",
        )
        set_principal_password(
            self.db,
            principal_id=self.member_principal["principal_id"],
            password="Str0ngPass!",
        )
        session = login_with_password(
            self.db,
            email="member@acme.com",
            password="Str0ngPass!",
            workspace_id=workspace["workspace_id"],
        )

        remove_organization_member(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            principal_id=self.member_principal["principal_id"],
        )

        stored_session = self.db.fetch_auth_session_by_token(session["session_token"])
        stored_token = self.db.fetch_access_token_by_value(session["access_token"])
        self.assertTrue(stored_session["revoked"])
        self.assertTrue(stored_token["revoked"])
        with self.assertRaises(HTTPException):
            authenticate_session_token(self.db, session["session_token"])
        with self.assertRaises(HTTPException):
            authenticate_access_token(self.db, session["access_token"])

    def test_cannot_suspend_org_owner_membership(self):
        with self.assertRaises(HTTPException) as ctx:
            suspend_organization_member(
                self.db,
                actor=self.org_owner_actor,
                organization_id=self.organization["organization_id"],
                principal_id=self.owner_principal["principal_id"],
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_cannot_remove_org_owner_membership(self):
        with self.assertRaises(HTTPException) as ctx:
            remove_organization_member(
                self.db,
                actor=self.org_owner_actor,
                organization_id=self.organization["organization_id"],
                principal_id=self.owner_principal["principal_id"],
            )
        self.assertEqual(ctx.exception.status_code, 400)

    def test_transfer_organization_owner_promotes_target_and_demotes_current_owner(self):
        result = transfer_organization_owner(
            self.db,
            actor=self.org_owner_actor,
            organization_id=self.organization["organization_id"],
            new_owner_principal_id=self.member_principal["principal_id"],
        )
        self.assertEqual(result["new_owner"]["role"], "org_owner")
        self.assertEqual(result["previous_owner"]["role"], "org_admin")

    def test_domain_auto_join_org_creates_active_org_membership_without_workspace_membership(self):
        self.db.upsert_organization_domain(
            {
                "domain_id": "dom_acme",
                "organization_id": self.organization["organization_id"],
                "domain": "acme.com",
                "verified_at": None,
                "join_mode": "domain_auto_join_org",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

        joined = join_organization_by_domain(
            self.db,
            organization_id=self.organization["organization_id"],
            email="newuser@acme.com",
            display_name="New User",
            password="Welc0mePass!",
        )

        self.assertEqual(joined["principal"]["email"], "newuser@acme.com")
        self.assertEqual(joined["organization_membership"]["role"], "org_member")
        self.assertEqual(joined["organization_membership"]["status"], "active")
        self.assertEqual(joined["workspace_memberships"], [])

    def test_domain_join_reuses_existing_principal_when_password_matches(self):
        self.db.upsert_organization_domain(
            {
                "domain_id": "dom_acme",
                "organization_id": self.organization["organization_id"],
                "domain": "acme.com",
                "verified_at": None,
                "join_mode": "domain_auto_join_org",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        principal = seed_principal(self.db, email="existing@acme.com", display_name="Existing")
        set_principal_password(self.db, principal_id=principal["principal_id"], password="Welc0mePass!")

        joined = join_organization_by_domain(
            self.db,
            organization_id=self.organization["organization_id"],
            email="existing@acme.com",
            display_name="Existing User",
            password="Welc0mePass!",
        )

        self.assertEqual(joined["principal"]["principal_id"], principal["principal_id"])
        self.assertEqual(joined["organization_membership"]["principal_id"], principal["principal_id"])

    def test_domain_join_rejects_invite_only_policy(self):
        self.db.upsert_organization_domain(
            {
                "domain_id": "dom_acme",
                "organization_id": self.organization["organization_id"],
                "domain": "acme.com",
                "verified_at": None,
                "join_mode": "invite_only",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

        with self.assertRaises(HTTPException) as ctx:
            join_organization_by_domain(
                self.db,
                organization_id=self.organization["organization_id"],
                email="blocked@acme.com",
                display_name="Blocked",
                password="Welc0mePass!",
            )

        self.assertEqual(ctx.exception.status_code, 403)
