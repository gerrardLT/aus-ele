import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from fcas_opportunity import summarize_nem_fcas_opportunity
import server


def make_nem_record(timestamp: str, region: str, price: float, **overrides):
    record = {
        "settlement_date": timestamp,
        "region_id": region,
        "rrp_aud_mwh": price,
        "raise1sec_rrp": 0.0,
        "raise6sec_rrp": 0.0,
        "raise60sec_rrp": 0.0,
        "raise5min_rrp": 0.0,
        "raisereg_rrp": 0.0,
        "lower1sec_rrp": 0.0,
        "lower6sec_rrp": 0.0,
        "lower60sec_rrp": 0.0,
        "lower5min_rrp": 0.0,
        "lowerreg_rrp": 0.0,
    }
    record.update(overrides)
    return record


class FcasOpportunityModelUnitTests(unittest.TestCase):
    def test_summarize_nem_fcas_opportunity_returns_incremental_metrics(self):
        result = summarize_nem_fcas_opportunity(
            [
                make_nem_record("2025-01-01 00:00:00", "NSW1", 80.0, raise1sec_rrp=220.0),
                make_nem_record("2025-01-01 00:05:00", "NSW1", 70.0, raise1sec_rrp=180.0),
            ],
            capacity_mw=50.0,
            duration_hours=1.0,
        )

        raise_1s = next(item for item in result["service_breakdown"] if item["key"] == "raise1sec")
        self.assertIn("avg_reserved_capacity_mw", raise_1s)
        self.assertIn("opportunity_cost_k", raise_1s)
        self.assertIn("net_incremental_revenue_k", raise_1s)
        self.assertIn("soc_binding_interval_ratio", raise_1s)
        self.assertIn("power_binding_interval_ratio", raise_1s)
        self.assertIn("incremental_revenue_positive", raise_1s)
        self.assertGreater(raise_1s["net_incremental_revenue_k"], 0.0)
        self.assertTrue(raise_1s["incremental_revenue_positive"])
        self.assertIn("total_net_incremental_revenue_k", result["summary"])

    def test_raise_service_marks_soc_binding_when_starting_soc_is_near_empty(self):
        result = summarize_nem_fcas_opportunity(
            [
                make_nem_record("2025-01-01 00:00:00", "NSW1", 150.0, raise1sec_rrp=120.0),
            ],
            capacity_mw=50.0,
            duration_hours=1.0,
            starting_soc_fraction=0.05,
        )

        raise_1s = next(item for item in result["service_breakdown"] if item["key"] == "raise1sec")
        self.assertGreater(raise_1s["soc_binding_interval_ratio"], 0.0)
        self.assertLess(raise_1s["avg_reserved_capacity_mw"], 50.0)


class FcasOpportunityApiTests(unittest.TestCase):
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

    def test_nem_fcas_analysis_exposes_incremental_revenue_signals(self):
        self.db.batch_insert(
            [
                make_nem_record("2025-01-01 00:00:00", "NSW1", 80.0, raise1sec_rrp=220.0, lower1sec_rrp=10.0),
                make_nem_record("2025-01-01 00:05:00", "NSW1", 70.0, raise1sec_rrp=180.0, lower1sec_rrp=12.0),
            ]
        )

        result = server.get_fcas_analysis(
            year=2025,
            region="NSW1",
            aggregation="daily",
            capacity_mw=50,
        )

        raise_1s = next(item for item in result["service_breakdown"] if item["key"] == "raise1sec")
        self.assertIn("net_incremental_revenue_k", raise_1s)
        self.assertIn("opportunity_cost_k", raise_1s)
        self.assertIn("soc_binding_interval_ratio", raise_1s)
        self.assertIn("power_binding_interval_ratio", raise_1s)
        self.assertIn("incremental_revenue_positive", raise_1s)
        self.assertIn("total_net_incremental_revenue_k", result["summary"])
        self.assertIn("viable_service_count", result["summary"])


if __name__ == "__main__":
    unittest.main()
