import os
import sys
import tempfile
import unittest
import types
from unittest import mock

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


def make_nem_record(timestamp: str, region: str, price: float):
    return {
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


class BessBacktestApiTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_scheduler_flag = os.environ.get("AUS_ELE_ENABLE_SCHEDULER")
        os.environ["AUS_ELE_ENABLE_SCHEDULER"] = "0"
        server.db = self.db
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server.db = self.original_db
        if self.original_scheduler_flag is None:
            os.environ.pop("AUS_ELE_ENABLE_SCHEDULER", None)
        else:
            os.environ["AUS_ELE_ENABLE_SCHEDULER"] = self.original_scheduler_flag
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_backtest_route_returns_structured_payload_for_nem(self):
        self.db.batch_insert(
            [
                make_nem_record("2025-01-01 00:00:00", "NSW1", 10.0),
                make_nem_record("2025-01-01 01:00:00", "NSW1", 100.0),
                make_nem_record("2025-01-01 02:00:00", "NSW1", 10.0),
                make_nem_record("2025-01-01 03:00:00", "NSW1", 100.0),
            ]
        )

        with mock.patch(
            "server.run_bess_backtest_v1",
            return_value={
                "summary": {
                    "gross_revenue": 180.0,
                    "net_revenue": 170.0,
                    "charge_throughput_mwh": 4.0,
                    "discharge_throughput_mwh": 4.0,
                    "equivalent_cycles": 2.0,
                    "soc_start_mwh": 0.0,
                    "soc_end_mwh": 0.0,
                    "soc_min_mwh": 0.0,
                    "soc_max_mwh": 2.0,
                    "costs": {"energy_cost": 10.0},
                    "warnings": [],
                },
                "timeline": [{}, {}, {}, {}],
            },
        ):
            response = self.client.post(
                "/api/bess/backtests",
                json={
                    "market": "NEM",
                    "region": "NSW1",
                    "year": 2025,
                    "power_mw": 1.0,
                    "energy_mwh": 2.0,
                    "duration_hours": 2.0,
                    "round_trip_efficiency": 1.0,
                    "max_cycles_per_day": 10.0,
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["market"], "NEM")
        self.assertEqual(payload["region"], "NSW1")
        self.assertEqual(payload["year"], 2025)
        self.assertEqual(payload["timeline_points"], 4)
        self.assertIn("revenue_breakdown", payload)
        self.assertIn("cost_breakdown", payload)
        self.assertIn("soc_summary", payload)
        self.assertIn("cycle_summary", payload)
        self.assertIn("timeline", payload)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical")
        self.assertEqual(payload["metadata"]["unit"], "AUD")
        self.assertGreater(payload["revenue_breakdown"]["gross_energy_revenue"], 0.0)

    def test_backtest_route_returns_404_when_source_data_is_missing(self):
        response = self.client.post(
            "/api/bess/backtests",
            json={
                "market": "NEM",
                "region": "NSW1",
                "year": 2025,
                "power_mw": 1.0,
                "energy_mwh": 2.0,
                "duration_hours": 2.0,
            },
        )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "No backtest source data found")

    def test_backtest_coverage_route_returns_structured_payload_for_nem(self):
        self.db.batch_insert(
            [
                make_nem_record("2025-01-01 00:00:00", "NSW1", 10.0),
                make_nem_record("2025-01-01 00:05:00", "NSW1", 100.0),
                make_nem_record("2025-01-01 00:10:00", "NSW1", 20.0),
            ]
        )

        response = self.client.get(
            "/api/bess/backtests/coverage",
            params={"market": "NEM", "region": "NSW1", "year": 2025},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["market"], "NEM")
        self.assertEqual(payload["region"], "NSW1")
        self.assertEqual(payload["year"], 2025)
        self.assertTrue(payload["has_source_data"])
        self.assertEqual(payload["interval_count"], 3)
        self.assertEqual(payload["coverage_start"], "2025-01-01 00:00:00")
        self.assertEqual(payload["coverage_end"], "2025-01-01 00:10:00")
        self.assertEqual(payload["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical")

    def test_backtest_coverage_route_returns_empty_shape_when_source_data_is_missing(self):
        response = self.client.get(
            "/api/bess/backtests/coverage",
            params={"market": "NEM", "region": "NSW1", "year": 2025},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertFalse(payload["has_source_data"])
        self.assertEqual(payload["interval_count"], 0)
        self.assertIsNone(payload["coverage_start"])
        self.assertIsNone(payload["coverage_end"])
        self.assertEqual(payload["interval_minutes"], 5)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical")


if __name__ == "__main__":
    unittest.main()
