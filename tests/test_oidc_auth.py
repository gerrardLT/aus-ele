import os
import tempfile
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from access_control import (
    authenticate_session_token,
    issue_oidc_session,
    link_auth_identity,
    logout_session,
    resolve_principal_for_oidc_claims,
)
from database import DatabaseManager
from oidc_client import build_authorization_redirect, parse_discovery_document


class OidcAuthDatabaseTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_oidc_provider_round_trip(self):
        organization = self.db.upsert_organization(
            {
                "organization_id": "org_acme",
                "name": "Acme",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        record = self.db.upsert_oidc_provider(
            {
                "provider_id": "op_google_acme",
                "organization_id": organization["organization_id"],
                "provider_key": "google",
                "issuer": "https://accounts.google.com",
                "discovery_url": "https://accounts.google.com/.well-known/openid-configuration",
                "client_id": "client-123",
                "client_secret_encrypted": "secret-ciphertext",
                "scopes_json": ["openid", "email", "profile"],
                "enabled": 1,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.assertEqual(record["provider_key"], "google")
        self.assertEqual(record["organization_id"], "org_acme")

    def test_auth_identity_round_trip(self):
        principal = self.db.upsert_principal(
            {
                "principal_id": "pr_123",
                "email": "user@example.com",
                "display_name": "User",
                "password_hash": None,
                "password_salt": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        identity = self.db.upsert_auth_identity(
            {
                "auth_identity_id": "ai_123",
                "principal_id": principal["principal_id"],
                "provider_type": "oidc",
                "provider_key": "google",
                "subject": "google-subject-1",
                "email": "user@example.com",
                "email_verified": 1,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        fetched = self.db.fetch_auth_identity_by_subject("oidc", "google", "google-subject-1")
        self.assertEqual(identity["auth_identity_id"], fetched["auth_identity_id"])
        self.assertEqual(fetched["principal_id"], principal["principal_id"])

    def test_organization_domain_round_trip(self):
        organization = self.db.upsert_organization(
            {
                "organization_id": "org_acme",
                "name": "Acme",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        record = self.db.upsert_organization_domain(
            {
                "domain_id": "dom_acme",
                "organization_id": organization["organization_id"],
                "domain": "acme.com",
                "verified_at": "2026-04-28T00:00:00Z",
                "join_mode": "invite_only",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        fetched = self.db.fetch_organization_domain_by_name("acme.com")
        self.assertEqual(record["domain_id"], fetched["domain_id"])
        self.assertEqual(fetched["join_mode"], "invite_only")


class OidcClientHelperTests(unittest.TestCase):
    def test_parse_discovery_document_extracts_required_endpoints(self):
        document = {
            "issuer": "https://accounts.google.com",
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
            "token_endpoint": "https://oauth2.googleapis.com/token",
            "userinfo_endpoint": "https://openidconnect.googleapis.com/v1/userinfo",
            "jwks_uri": "https://www.googleapis.com/oauth2/v3/certs",
        }
        parsed = parse_discovery_document(document)
        self.assertEqual(parsed["issuer"], "https://accounts.google.com")
        self.assertTrue(parsed["token_endpoint"].startswith("https://"))

    def test_build_authorization_redirect_contains_state_nonce_and_scopes(self):
        provider = {
            "client_id": "client-123",
            "scopes_json": ["openid", "email", "profile"],
        }
        discovery = {
            "authorization_endpoint": "https://accounts.google.com/o/oauth2/v2/auth",
        }
        redirect = build_authorization_redirect(
            provider=provider,
            discovery=discovery,
            redirect_uri="https://app.example.com/api/auth/oidc/callback",
            state="state-1",
            nonce="nonce-1",
        )
        self.assertIn("state=state-1", redirect)
        self.assertIn("nonce=nonce-1", redirect)
        self.assertIn("scope=openid+email+profile", redirect)


class OidcAccessControlTests(unittest.TestCase):
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
        self.workspace = self.db.upsert_workspace(
            {
                "workspace_id": "ws_primary",
                "organization_id": self.organization["organization_id"],
                "name": "Primary",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.principal = self.db.upsert_principal(
            {
                "principal_id": "pr_owner",
                "email": "owner@example.com",
                "display_name": "Owner",
                "password_hash": None,
                "password_salt": None,
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.db.upsert_workspace_membership(
            {
                "membership_id": "m_owner",
                "workspace_id": self.workspace["workspace_id"],
                "principal_id": self.principal["principal_id"],
                "role": "owner",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_link_auth_identity_creates_oidc_binding(self):
        identity = link_auth_identity(
            self.db,
            principal_id=self.principal["principal_id"],
            provider_key="google",
            subject="sub-001",
            email="owner@example.com",
            email_verified=True,
        )
        self.assertEqual(identity["principal_id"], self.principal["principal_id"])
        self.assertEqual(identity["provider_type"], "oidc")

    def test_resolve_principal_for_oidc_claims_reuses_existing_principal_by_email(self):
        resolved = resolve_principal_for_oidc_claims(
            self.db,
            provider_key="google",
            subject="sub-002",
            email="owner@example.com",
            email_verified=True,
            display_name="Owner OIDC",
        )
        self.assertEqual(resolved["principal"]["principal_id"], self.principal["principal_id"])
        self.assertEqual(resolved["auth_identity"]["subject"], "sub-002")

    def test_issue_oidc_session_and_logout(self):
        session = issue_oidc_session(
            self.db,
            principal_id=self.principal["principal_id"],
            organization_id=self.organization["organization_id"],
            workspace_id=self.workspace["workspace_id"],
            auth_identity_id="ai_oidc_1",
            auth_method="oidc",
        )
        actor = authenticate_session_token(self.db, session["session_token"])
        self.assertEqual(actor["session"]["auth_method"], "oidc")
        logout_session(self.db, session["session_token"])
        with self.assertRaises(HTTPException):
            authenticate_session_token(self.db, session["session_token"])
