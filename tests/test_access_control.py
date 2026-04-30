import base64
import json
import os
import tempfile
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from access_control import (
    ROLE_PERMISSIONS,
    authenticate_access_token,
    authenticate_session_token,
    check_workspace_permission,
    create_workspace_invite,
    accept_workspace_invite,
    issue_access_token,
    login_with_password,
    logout_session,
    refresh_session_access_token,
    revoke_workspace_invite,
    set_principal_password,
    seed_organization,
    seed_organization_membership,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
    suspend_organization_member,
)
from database import DatabaseManager


class AccessControlTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _decode_payload(self, token: str) -> dict:
        payload_segment = token.split(".")[1]
        padding = "=" * (-len(payload_segment) % 4)
        decoded = base64.urlsafe_b64decode((payload_segment + padding).encode("ascii")).decode("utf-8")
        return json.loads(decoded)

    def test_owner_role_contains_export_and_audit_permissions(self):
        self.assertIn("export", ROLE_PERMISSIONS["owner"])
        self.assertIn("read_audit", ROLE_PERMISSIONS["owner"])

    def test_issue_and_authenticate_access_token(self):
        org = seed_organization(self.db, name="Acme Energy")
        principal = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_workspace_membership(
            self.db,
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="owner",
        )

        token = issue_access_token(self.db, principal_id=principal["principal_id"], workspace_id=workspace["workspace_id"])
        actor = authenticate_access_token(self.db, token["token"])

        self.assertEqual(actor["principal"]["principal_id"], principal["principal_id"])
        self.assertEqual(actor["workspace"]["workspace_id"], workspace["workspace_id"])
        self.assertEqual(actor["membership"]["role"], "owner")
        self.assertEqual(len(token["token"].split(".")), 3)
        claims = self._decode_payload(token["token"])
        self.assertEqual(claims["sub"], principal["principal_id"])
        self.assertEqual(claims["workspace_id"], workspace["workspace_id"])

    def test_workspace_permission_check_rejects_viewer_for_export(self):
        org = seed_organization(self.db, name="Acme Energy")
        principal = seed_principal(self.db, email="viewer@example.com", display_name="Viewer")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_workspace_membership(
            self.db,
            workspace_id=workspace["workspace_id"],
            principal_id=principal["principal_id"],
            role="viewer",
        )
        actor = {
            "principal": principal,
            "workspace": workspace,
            "membership": {"role": "viewer"},
        }

        with self.assertRaises(HTTPException) as ctx:
            check_workspace_permission(actor, "export")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_audit_log_is_written_for_resource_creation(self):
        org = seed_organization(self.db, name="Acme Energy")
        logs = self.db.fetch_audit_logs()

        self.assertEqual(org["name"], "Acme Energy")
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["action"], "organization.created")

    def test_password_login_issues_authenticated_session(self):
        org = seed_organization(self.db, name="Acme Energy")
        principal = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=principal["principal_id"],
            role="org_owner",
            status="active",
        )
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=principal["principal_id"], role="owner")
        set_principal_password(self.db, principal_id=principal["principal_id"], password="Str0ngPass!")

        session = login_with_password(self.db, email="owner@example.com", password="Str0ngPass!", workspace_id=workspace["workspace_id"])
        actor = authenticate_session_token(self.db, session["session_token"])

        self.assertEqual(actor["principal"]["principal_id"], principal["principal_id"])
        self.assertEqual(actor["workspace"]["workspace_id"], workspace["workspace_id"])
        self.assertEqual(actor["membership"]["role"], "owner")
        self.assertIn("access_token", session)
        jwt_actor = authenticate_access_token(self.db, session["access_token"])
        self.assertEqual(jwt_actor["principal"]["principal_id"], principal["principal_id"])

    def test_refresh_session_access_token_rotates_access_token(self):
        org = seed_organization(self.db, name="Acme Energy")
        principal = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=principal["principal_id"],
            role="org_owner",
            status="active",
        )
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=principal["principal_id"], role="owner")
        set_principal_password(self.db, principal_id=principal["principal_id"], password="Str0ngPass!")

        session = login_with_password(self.db, email="owner@example.com", password="Str0ngPass!", workspace_id=workspace["workspace_id"])
        refreshed = refresh_session_access_token(self.db, session["session_token"])

        self.assertIn("access_token", refreshed)
        self.assertNotEqual(session["access_token"], refreshed["access_token"])
        claims = self._decode_payload(refreshed["access_token"])
        self.assertEqual(claims["session_id"], session["session_id"])
        actor = authenticate_access_token(self.db, refreshed["access_token"])
        self.assertEqual(actor["principal"]["principal_id"], principal["principal_id"])

    def test_logout_revokes_session_and_blocks_refresh(self):
        org = seed_organization(self.db, name="Acme Energy")
        principal = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=principal["principal_id"],
            role="org_owner",
            status="active",
        )
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=principal["principal_id"], role="owner")
        set_principal_password(self.db, principal_id=principal["principal_id"], password="Str0ngPass!")

        session = login_with_password(self.db, email="owner@example.com", password="Str0ngPass!", workspace_id=workspace["workspace_id"])
        logout_session(self.db, session["session_token"])

        with self.assertRaises(HTTPException) as ctx:
            refresh_session_access_token(self.db, session["session_token"])
        self.assertEqual(ctx.exception.status_code, 401)

    def test_suspended_organization_membership_blocks_existing_session_and_access_token(self):
        org = seed_organization(self.db, name="Acme Energy")
        owner = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        member = seed_principal(self.db, email="member@example.com", display_name="Member")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        owner_org_membership = seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=owner["principal_id"],
            role="org_owner",
            status="active",
        )
        seed_organization_membership(
            self.db,
            organization_id=org["organization_id"],
            principal_id=member["principal_id"],
            role="org_member",
            status="active",
        )
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=owner["principal_id"], role="owner")
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=member["principal_id"], role="analyst")
        set_principal_password(self.db, principal_id=member["principal_id"], password="Str0ngPass!")

        session = login_with_password(self.db, email="member@example.com", password="Str0ngPass!", workspace_id=workspace["workspace_id"])
        owner_actor = {
            "organization": org,
            "principal": owner,
            "organization_membership": owner_org_membership,
        }
        suspend_organization_member(
            self.db,
            actor=owner_actor,
            organization_id=org["organization_id"],
            principal_id=member["principal_id"],
        )

        with self.assertRaises(HTTPException) as session_ctx:
            authenticate_session_token(self.db, session["session_token"])
        self.assertEqual(session_ctx.exception.status_code, 401)

        with self.assertRaises(HTTPException) as token_ctx:
            authenticate_access_token(self.db, session["access_token"])
        self.assertEqual(token_ctx.exception.status_code, 401)

        stored_session = self.db.fetch_auth_session_by_token(session["session_token"])
        stored_token = self.db.fetch_access_token_by_value(session["access_token"])
        self.assertTrue(stored_session["revoked"])
        self.assertTrue(stored_token["revoked"])

    def test_workspace_invite_acceptance_creates_membership(self):
        org = seed_organization(self.db, name="Acme Energy")
        owner = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=owner["principal_id"], role="owner")
        actor = {"principal": owner, "workspace": workspace, "membership": {"role": "owner"}}

        invite = create_workspace_invite(
            self.db,
            actor=actor,
            workspace_id=workspace["workspace_id"],
            email="invitee@example.com",
            role="analyst",
        )
        accepted = accept_workspace_invite(
            self.db,
            invite_token=invite["invite_token"],
            display_name="Invitee",
            password="Welc0mePass!",
        )

        membership = self.db.fetch_workspace_membership(workspace["workspace_id"], accepted["principal"]["principal_id"])
        self.assertEqual(membership["role"], "analyst")
        self.assertEqual(accepted["workspace"]["workspace_id"], workspace["workspace_id"])

    def test_workspace_invite_can_be_revoked(self):
        org = seed_organization(self.db, name="Acme Energy")
        owner = seed_principal(self.db, email="owner@example.com", display_name="Owner")
        workspace = seed_workspace(self.db, organization_id=org["organization_id"], name="Primary")
        seed_workspace_membership(self.db, workspace_id=workspace["workspace_id"], principal_id=owner["principal_id"], role="owner")
        actor = {"principal": owner, "workspace": workspace, "membership": {"role": "owner"}}

        invite = create_workspace_invite(
            self.db,
            actor=actor,
            workspace_id=workspace["workspace_id"],
            email="invitee@example.com",
            role="viewer",
        )
        revoked = revoke_workspace_invite(self.db, actor=actor, invite_id=invite["invite_id"])

        self.assertTrue(revoked["revoked"])
