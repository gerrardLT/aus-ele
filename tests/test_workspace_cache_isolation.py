import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server


class WorkspaceResponseCacheIsolationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_scope_cache_payload_includes_org_and_workspace(self):
        payload = server._scope_cache_payload(
            {
                "year": 2026,
                "region": "NSW1",
            },
            organization_id="org_a",
            workspace_id="ws_a",
        )
        self.assertEqual(payload["organization_id"], "org_a")
        self.assertEqual(payload["workspace_id"], "ws_a")

    def test_same_business_payload_different_workspace_produces_different_cache_key(self):
        payload_a = server._scope_cache_payload(
            {"year": 2026, "region": "NSW1"}, organization_id="org_a", workspace_id="ws_a"
        )
        payload_b = server._scope_cache_payload(
            {"year": 2026, "region": "NSW1"}, organization_id="org_a", workspace_id="ws_b"
        )
        self.assertNotEqual(server._stable_cache_key(payload_a), server._stable_cache_key(payload_b))

    def test_fetch_response_cache_uses_scoped_payload(self):
        payload = server._scope_cache_payload(
            {"region": "NSW1", "year": 2026}, organization_id="org_a", workspace_id="ws_a"
        )
        cache_key = server._stable_cache_key(payload)
        self.assertIn("org_a", str(payload))
        self.assertIn("ws_a", str(payload))
        self.assertTrue(cache_key)

    def test_analysis_cache_payload_can_be_scoped(self):
        payload = server._scope_analysis_payload(
            {"region": "NSW1", "backtest_years": [2025, 2026]},
            organization_id="org_a",
            workspace_id="ws_a",
        )
        self.assertEqual(payload["organization_id"], "org_a")
        self.assertEqual(payload["workspace_id"], "ws_a")

    def test_analysis_cache_round_trip_preserves_workspace_scope(self):
        self.db.upsert_analysis_cache(
            scope="investment_response_v2",
            cache_key="key-1",
            data_version="version-1",
            response_payload={"npv": 1},
            organization_id="org_a",
            workspace_id="ws_a",
        )
        row = self.db.fetch_analysis_cache(
            scope="investment_response_v2",
            cache_key="key-1",
            data_version="version-1",
            organization_id="org_a",
            workspace_id="ws_a",
        )
        self.assertEqual(row["organization_id"], "org_a")
        self.assertEqual(row["workspace_id"], "ws_a")

    def test_analysis_cache_lookup_does_not_cross_workspace(self):
        self.db.upsert_analysis_cache(
            scope="investment_response_v2",
            cache_key="key-1",
            data_version="version-1",
            response_payload={"npv": 1},
            organization_id="org_a",
            workspace_id="ws_a",
        )
        row = self.db.fetch_analysis_cache(
            scope="investment_response_v2",
            cache_key="key-1",
            data_version="version-1",
            organization_id="org_a",
            workspace_id="ws_b",
        )
        self.assertIsNone(row)
