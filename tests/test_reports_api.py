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
from fastapi import HTTPException


class ReportsApiTests(unittest.TestCase):
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

    def _seed_nsw_prices(self):
        self.db.batch_insert(
            [
                {
                    "settlement_date": "2025-04-01 00:00:00",
                    "region_id": "NSW1",
                    "rrp_aud_mwh": 20.0,
                    "raise1sec_rrp": 15.0,
                    "raise6sec_rrp": 10.0,
                    "raise60sec_rrp": 0.0,
                    "raise5min_rrp": 0.0,
                    "raisereg_rrp": 0.0,
                    "lower1sec_rrp": 2.0,
                    "lower6sec_rrp": 0.0,
                    "lower60sec_rrp": 0.0,
                    "lower5min_rrp": 0.0,
                    "lowerreg_rrp": 0.0,
                },
                {
                    "settlement_date": "2025-04-01 00:05:00",
                    "region_id": "NSW1",
                    "rrp_aud_mwh": 220.0,
                    "raise1sec_rrp": 25.0,
                    "raise6sec_rrp": 20.0,
                    "raise60sec_rrp": 0.0,
                    "raise5min_rrp": 0.0,
                    "raisereg_rrp": 0.0,
                    "lower1sec_rrp": 2.0,
                    "lower6sec_rrp": 0.0,
                    "lower60sec_rrp": 0.0,
                    "lower5min_rrp": 0.0,
                    "lowerreg_rrp": 0.0,
                },
            ]
        )
        self.db.set_last_update_time("2025-04-01 00:10:00")

    def test_monthly_market_report_returns_structured_payload(self):
        self._seed_nsw_prices()

        payload = server.generate_report(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
        )

        self.assertEqual(payload["report_type"], "monthly_market_report")
        self.assertIn("title", payload)
        self.assertIn("sections", payload)
        self.assertGreater(len(payload["sections"]), 0)
        self.assertIn("metadata", payload)
        self.assertIn("reproducibility", payload)
        self.assertEqual(payload["reproducibility"]["methodology_version"], "report_payload_v1")

    def test_investment_memo_returns_structured_payload(self):
        self._seed_nsw_prices()

        payload = server.generate_report(
            report_type="investment_memo_draft",
            year=2025,
            region="NSW1",
            month="04",
        )

        self.assertEqual(payload["report_type"], "investment_memo_draft")
        self.assertIn("title", payload)
        self.assertIn("sections", payload)
        self.assertGreater(len(payload["sections"]), 0)

    def test_generate_report_rejects_scope_violation(self):
        self._seed_nsw_prices()
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["QLD1"],
            "allowed_markets": ["NEM"],
        }

        with self.assertRaises(HTTPException) as ctx:
            server.generate_report(
                report_type="monthly_market_report",
                year=2025,
                region="NSW1",
                month="04",
                access_scope=scope,
            )
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
