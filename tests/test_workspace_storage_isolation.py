import json
import os
import tempfile
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from storage_lake import LocalArtifactLake
import server


class WorkspaceStorageIsolationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        server.db = self.db

    def tearDown(self):
        server.db = self.original_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_artifact_metadata_contains_org_and_workspace(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lake = LocalArtifactLake(tmpdir)
            artifact = lake.write_artifact(
                layer="derived",
                namespace="reports",
                partition="organization=org_a/workspace=ws_a/date=2026-04-28",
                payload={"ok": True},
                metadata={"organization_id": "org_a", "workspace_id": "ws_a"},
            )
            self.assertEqual(artifact["organization_id"], "org_a")
            self.assertEqual(artifact["workspace_id"], "ws_a")
            with open(artifact["metadata_path"], "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
            self.assertEqual(metadata["organization_id"], "org_a")
            self.assertEqual(metadata["workspace_id"], "ws_a")

    def test_artifact_scope_mismatch_is_rejected(self):
        artifact = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
        }
        with self.assertRaises(HTTPException):
            server._assert_artifact_scope(
                artifact,
                {
                    "organization_id": "org_a",
                    "workspace_id": "ws_b",
                },
            )

    def test_alert_rule_round_trip_preserves_workspace_scope(self):
        saved = self.db.upsert_alert_rule(
            {
                "rule_id": "rule_1",
                "name": "Spike",
                "rule_type": "price_threshold",
                "market": "NEM",
                "region_or_zone": "NSW1",
                "config": {},
                "channel_type": "webhook",
                "channel_target": "https://example.com",
                "enabled": True,
                "organization_id": "org_a",
                "workspace_id": "ws_a",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        self.assertEqual(saved["organization_id"], "org_a")
        self.assertEqual(saved["workspace_id"], "ws_a")

    def test_fetch_alert_rules_does_not_cross_workspace(self):
        self.db.upsert_alert_rule(
            {
                "rule_id": "rule_1",
                "name": "Spike",
                "rule_type": "price_threshold",
                "market": "NEM",
                "region_or_zone": "NSW1",
                "config": {},
                "channel_type": "webhook",
                "channel_target": "https://example.com",
                "enabled": True,
                "organization_id": "org_a",
                "workspace_id": "ws_a",
                "created_at": "2026-04-28T00:00:00Z",
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        items = self.db.fetch_alert_rules(workspace_id="ws_b")
        self.assertEqual(items, [])

    def test_generate_report_payload_preserves_workspace_scope(self):
        payload = server.generate_report(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            organization_id="org_a",
            workspace_id="ws_a",
        )
        self.assertEqual(payload["report_context"]["organization_id"], "org_a")
        self.assertEqual(payload["report_context"]["workspace_id"], "ws_a")
