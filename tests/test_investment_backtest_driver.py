import os
import tempfile
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from models.financial_params import FinancialAssumptions
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


class InvestmentBacktestDriverTests(unittest.TestCase):
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

    def test_investment_analysis_prefers_standardized_backtest_engine_when_intervals_exist(self):
        self.db.batch_insert(
            [
                make_nem_record("2025-01-01 00:00:00", "NSW1", 10.0),
                make_nem_record("2025-01-01 01:00:00", "NSW1", 100.0),
                make_nem_record("2025-01-01 02:00:00", "NSW1", 10.0),
                make_nem_record("2025-01-01 03:00:00", "NSW1", 100.0),
            ]
        )

        result = server.investment_analysis(
            server.InvestmentParams(
                region="NSW1",
                power_mw=1.0,
                duration_hours=2.0,
                backtest_years=[2025],
                revenue_capture_rate=1.0,
                forecast_inefficiency=0.0,
                fcas_revenue_mode="manual",
                fcas_revenue_per_mw_year=0,
                financial=FinancialAssumptions(
                    variable_om_per_mwh=10.0,
                    project_life_years=5,
                ),
            )
        )

        self.assertEqual(result["backtest_reference"]["methodology_version"], "bess_backtest_v1")
        self.assertEqual(result["backtest_reference"]["inputs"][0]["region"], "NSW1")
        self.assertEqual(result["backtest_reference"]["inputs"][0]["year"], 2025)
        self.assertGreater(result["baseline_revenue"]["arbitrage"], 0.0)
        self.assertIn("arbitrage_net_observed", result["baseline_revenue"])
        self.assertIn("backtest_observed", result)
        self.assertEqual(result["backtest_observed"]["methodology_version"], "bess_backtest_v1")
        self.assertGreaterEqual(result["backtest_observed"]["gross_energy_revenue"], result["backtest_observed"]["net_energy_revenue"])
        self.assertIn("summary", result["backtest_reference"]["drivers"][0])
        self.assertIn("costs", result["backtest_reference"]["drivers"][0]["summary"])
        self.assertIn("equivalent_cycles", result["backtest_reference"]["drivers"][0]["summary"])
        self.assertEqual(
            result["baseline_revenue"]["arbitrage"],
            result["backtest_observed"]["net_energy_revenue"],
        )
        self.assertFalse(result["backtest_fallback_used"])

    def test_investment_analysis_does_not_fall_back_to_legacy_backtest_when_standardized_path_is_unavailable(self):
        with mock.patch("bess_backtest.backtest_arbitrage") as mock_legacy_backtest:
            result = server.investment_analysis(
                server.InvestmentParams(
                    region="NSW1",
                    power_mw=100,
                    duration_hours=4,
                    backtest_years=[2025],
                    revenue_capture_rate=1.0,
                    forecast_inefficiency=0.0,
                    fcas_revenue_mode="manual",
                    fcas_revenue_per_mw_year=0,
                )
            )

        mock_legacy_backtest.assert_not_called()
        self.assertFalse(result["backtest_fallback_used"])
        self.assertEqual(result["arbitrage_baseline_source"], "no_standardized_backtest_data")
        self.assertEqual(result["backtest_observed"]["methodology_version"], "unavailable")
        self.assertEqual(result["baseline_revenue"]["arbitrage"], 0.0)


if __name__ == "__main__":
    unittest.main()
