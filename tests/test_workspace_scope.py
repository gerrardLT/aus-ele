import os
import tempfile
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from access_control import (
    assert_scope_allows_region_market,
    build_workspace_access_scope,
    seed_organization,
    seed_principal,
    seed_workspace,
    seed_workspace_membership,
)
from database import DatabaseManager


class WorkspaceScopeTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.organization = seed_organization(self.db, name="Acme")
        self.principal = seed_principal(self.db, email="owner@acme.com", display_name="Owner")
        self.workspace = seed_workspace(
            self.db, organization_id=self.organization["organization_id"], name="Primary"
        )
        seed_workspace_membership(
            self.db,
            workspace_id=self.workspace["workspace_id"],
            principal_id=self.principal["principal_id"],
            role="owner",
        )
        self.db.upsert_workspace_policy(
            {
                "workspace_id": self.workspace["workspace_id"],
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_build_workspace_access_scope_contains_workspace_policy(self):
        scope = build_workspace_access_scope(
            self.db,
            organization_id=self.organization["organization_id"],
            workspace_id=self.workspace["workspace_id"],
            principal_id=self.principal["principal_id"],
        )
        self.assertEqual(scope["workspace_id"], self.workspace["workspace_id"])
        self.assertIn("NSW1", scope["allowed_regions"])
        self.assertIn("NEM", scope["allowed_markets"])

    def test_assert_scope_allows_region_market_rejects_outside_policy(self):
        scope = build_workspace_access_scope(
            self.db,
            organization_id=self.organization["organization_id"],
            workspace_id=self.workspace["workspace_id"],
            principal_id=self.principal["principal_id"],
        )
        with self.assertRaises(HTTPException) as ctx:
            assert_scope_allows_region_market(scope, region="QLD1", market="NEM")
        self.assertEqual(ctx.exception.status_code, 403)
