import os
import sys
import tempfile
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from database import DatabaseManager
import server


class P3BessDecisionApiTests(unittest.TestCase):
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

    def test_p3_decision_route_returns_structured_payload(self):
        fake_backtest = {
            "market": "NEM",
            "region": "NSW1",
            "year": 2025,
            "revenue_breakdown": {
                "gross_energy_revenue": 180.0,
                "net_revenue": 160.0,
            },
            "cost_breakdown": {
                "network_fees": 8.0,
                "degradation": 6.0,
                "variable_om": 2.0,
            },
            "cycle_summary": {
                "charge_throughput_mwh": 4.0,
                "discharge_throughput_mwh": 4.0,
                "equivalent_cycles": 2.0,
            },
            "soc_summary": {
                "soc_start_mwh": 1.0,
                "soc_end_mwh": 1.0,
                "soc_min_mwh": 0.2,
                "soc_max_mwh": 2.0,
            },
            "timeline_points": 4,
            "timeline": [
                {"timestamp": "2025-01-01T00:00:00Z", "price": 12.0, "interval_hours": 1.0},
                {"timestamp": "2025-01-01T01:00:00Z", "price": 140.0, "interval_hours": 1.0},
                {"timestamp": "2025-01-01T02:00:00Z", "price": -18.0, "interval_hours": 1.0},
                {"timestamp": "2025-01-01T03:00:00Z", "price": 165.0, "interval_hours": 1.0},
            ],
            "metadata": {"dataset_family": "bess_backtest"},
        }
        fake_forecast = {
            "market": "NEM",
            "region": "NSW1",
            "horizon": "24h",
            "summary": {
                "fcas_opportunity_score": 68.0,
                "charge_window_score": 61.0,
                "discharge_window_score": 74.0,
            },
            "baseline_forecast": {
                "probabilities": {
                    "price_spike": 0.72,
                    "negative_price": 0.43,
                    "negative_price_duration_intervals": 2,
                    "negative_price_duration_hours": 1.0,
                    "duration_method": "window_probability_scan_v1",
                },
                "evaluation": {
                    "diagnostics": {
                        "status": "available",
                        "error_grade": "moderate_error",
                        "primary_gap_domain": "coverage",
                    },
                    "calibration": {
                        "status": "baseline_only",
                        "summary_grade": "mixed",
                        "sample_count": 2,
                    },
                },
            },
            "regime_compact": {
                "availability_status": "available",
                "primary_regime": {"regime": "scarcity", "score": 72.0},
            },
            "metadata": {"dataset_family": "forecast_layer"},
        }

        with mock.patch("server.run_bess_backtest", return_value=fake_backtest), mock.patch(
            "server.get_p2_forecast_layer", return_value=fake_forecast
        ):
            response = self.client.post(
                "/api/p3/bess/decision-layer",
                json={
                    "market": "NEM",
                    "region": "NSW1",
                    "year": 2025,
                    "power_mw": 1.0,
                    "energy_mwh": 2.0,
                    "duration_hours": 2.0,
                    "forecast_horizon": "24h",
                    "reserve_soc_pct": 15.0,
                    "risk_mode": "balanced",
                },
            )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["market"], "NEM")
        self.assertEqual(payload["forecast_context"]["horizon"], "24h")
        self.assertEqual(payload["decision_summary"]["recommended_strategy"], "forecast_driven_dispatch")
        self.assertIn("recommendation_summary", payload["decision_summary"])
        self.assertIn("explanation_chain", payload["decision_summary"])
        self.assertIn("risk_boundary", payload["decision_summary"])
        self.assertEqual(payload["decision_summary"]["recommendation_summary"]["action"], "forecast_driven_dispatch")
        self.assertEqual(len(payload["decision_summary"]["explanation_chain"]), 3)
        self.assertEqual(payload["decision_summary"]["explanation_chain"][0]["step"], "Current Market")
        self.assertEqual(payload["decision_summary"]["risk_boundary"]["usage_scope"], "decision-grade")
        self.assertIn("rule_based_dispatch", payload["strategy_bundle"])
        self.assertIn("forecast_driven_dispatch", payload["strategy_bundle"])
        self.assertIn("stochastic_dispatch", payload["strategy_bundle"])
        self.assertIn("revenue_attribution", payload)
        self.assertGreater(payload["strategy_bundle"]["forecast_driven_dispatch"]["net_revenue"], 160.0)
        self.assertEqual(payload["strategy_bundle"]["stochastic_dispatch"]["scenario_count"], 3)
        self.assertEqual(payload["decision_summary"]["co_optimization_mode"], "energy_fcas_headroom_optimizer_v2")
        self.assertEqual(payload["decision_summary"]["degradation_mode"], "throughput_penalty_with_reserve_buffer_v2")
        self.assertIn("dispatch_summary", payload["strategy_bundle"]["forecast_driven_dispatch"])
        self.assertIn("reserve_value_revenue", payload["strategy_bundle"]["forecast_driven_dispatch"])
        self.assertGreaterEqual(
            payload["strategy_bundle"]["forecast_driven_dispatch"]["dispatch_summary"]["total_charge_mwh"],
            0.0,
        )
        self.assertGreaterEqual(
            payload["strategy_bundle"]["forecast_driven_dispatch"]["dispatch_summary"]["total_raise_reserve_mwh"],
            0.0,
        )
        self.assertIn("scenarios", payload["strategy_bundle"]["stochastic_dispatch"])
        self.assertEqual(len(payload["strategy_bundle"]["stochastic_dispatch"]["scenarios"]), 3)
        self.assertIn("governance", payload)
        self.assertEqual(payload["governance"]["disclaimer"]["investment_grade"], False)
        self.assertGreater(payload["governance"]["forecast_value_attribution"]["net_uplift"], 0.0)
        self.assertEqual(payload["governance"]["forecast_value_attribution"]["status"], "available")
        self.assertIn("freshness", payload["governance"])
        self.assertIn("lineage", payload["governance"])
        self.assertIn("source_backtest", payload)
        self.assertEqual(payload["source_backtest"]["timeline_points"], 4)
        self.assertEqual(payload["source_backtest"]["cycle_summary"]["equivalent_cycles"], 2.0)
        self.assertEqual(payload["governance"]["lineage"]["source_id"], "p3_bess_decision_layer")
        self.assertEqual(payload["metadata"]["dataset_family"], "bess_decision_layer")
        self.assertEqual(payload["metadata"]["data_grade"], "decision-grade")
        self.assertEqual(payload["coverage_mode"], "decision-support")
        self.assertEqual(payload["regulatory_scope"], "NEM")
        self.assertEqual(payload["result_type"], "investment_conclusion")

    def test_p3_decision_route_propagates_missing_source_data(self):
        with mock.patch("server.run_bess_backtest", side_effect=server.HTTPException(status_code=404, detail="No backtest source data found")):
            response = self.client.post(
                "/api/p3/bess/decision-layer",
                json={
                    "market": "NEM",
                    "region": "NSW1",
                    "year": 2025,
                    "power_mw": 1.0,
                    "energy_mwh": 2.0,
                    "duration_hours": 2.0,
                    "forecast_horizon": "24h",
                },
            )

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "No backtest source data found")
