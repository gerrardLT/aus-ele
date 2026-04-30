import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.bess_backtest_v1 import run_bess_backtest_v1
from models.bess_backtest_params import BessBacktestParams


class BessBacktestEngineTests(unittest.TestCase):
    def _build_params(self, **overrides):
        payload = {
            "market": "NEM",
            "region": "NSW1",
            "year": 2025,
            "power_mw": 1.0,
            "energy_mwh": 2.0,
            "duration_hours": 2.0,
            "round_trip_efficiency": 1.0,
            "max_cycles_per_day": 10.0,
        }
        payload.update(overrides)
        return BessBacktestParams(**payload)

    def test_returns_timeline_and_summary(self):
        params = self._build_params()
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 10.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 100.0, "interval_hours": 1.0},
        ]

        result = run_bess_backtest_v1(params, intervals)

        self.assertEqual(len(result["timeline"]), 2)
        self.assertIn("summary", result)
        self.assertAlmostEqual(result["summary"]["soc_start_mwh"], 1.0)
        self.assertAlmostEqual(result["summary"]["soc_end_mwh"], 1.0)
        self.assertGreater(result["summary"]["gross_revenue"], 0.0)

    def test_never_charges_and_discharges_simultaneously(self):
        params = self._build_params(round_trip_efficiency=0.9)
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 20.0, "interval_hours": 0.5},
            {"timestamp": "2025-01-01T00:30:00Z", "price": 200.0, "interval_hours": 0.5},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 20.0, "interval_hours": 0.5},
            {"timestamp": "2025-01-01T01:30:00Z", "price": 200.0, "interval_hours": 0.5},
        ]

        result = run_bess_backtest_v1(params, intervals)

        for row in result["timeline"]:
            self.assertFalse(row["charge_mw"] > 0 and row["discharge_mw"] > 0)

    def test_applies_cost_haircuts_to_net_revenue(self):
        base_params = self._build_params()
        costed_params = self._build_params(
            network_fee_per_mwh=5.0,
            degradation_cost_per_mwh=7.0,
            variable_om_per_mwh=3.0,
        )
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 0.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 100.0, "interval_hours": 1.0},
        ]

        base_result = run_bess_backtest_v1(base_params, intervals)
        costed_result = run_bess_backtest_v1(costed_params, intervals)

        self.assertGreater(base_result["summary"]["net_revenue"], costed_result["summary"]["net_revenue"])
        self.assertGreater(costed_result["summary"]["costs"]["network_fees"], 0.0)
        self.assertGreater(costed_result["summary"]["costs"]["degradation"], 0.0)
        self.assertGreater(costed_result["summary"]["costs"]["variable_om"], 0.0)

    def test_respects_max_cycles_per_day_limit(self):
        params = self._build_params(
            energy_mwh=1.0,
            duration_hours=1.0,
            max_cycles_per_day=0.5,
        )
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 0.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 100.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T02:00:00Z", "price": 0.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T03:00:00Z", "price": 100.0, "interval_hours": 1.0},
        ]

        result = run_bess_backtest_v1(params, intervals)

        self.assertLessEqual(result["summary"]["equivalent_cycles"], 0.5 + 1e-6)

    def test_soc_stays_within_declared_bounds(self):
        params = self._build_params(
            energy_mwh=4.0,
            duration_hours=4.0,
            min_soc_pct=25.0,
            max_soc_pct=75.0,
            initial_soc_pct=50.0,
        )
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 0.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 300.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T02:00:00Z", "price": 0.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T03:00:00Z", "price": 300.0, "interval_hours": 1.0},
        ]

        result = run_bess_backtest_v1(params, intervals)

        for row in result["timeline"]:
            self.assertGreaterEqual(row["soc_mwh"], 1.0 - 1e-6)
            self.assertLessEqual(row["soc_mwh"], 3.0 + 1e-6)

    def test_energy_conservation_matches_soc_movement(self):
        params = self._build_params(round_trip_efficiency=0.81)
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 10.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 100.0, "interval_hours": 1.0},
        ]

        result = run_bess_backtest_v1(params, intervals)
        eta = params.round_trip_efficiency ** 0.5
        first_row = result["timeline"][0]
        second_row = result["timeline"][1]

        expected_soc_after_first = (
            params.initial_soc_mwh
            + first_row["charge_mwh"] * eta
            - first_row["discharge_mwh"] / eta
        )
        expected_soc_after_second = (
            first_row["soc_mwh"]
            + second_row["charge_mwh"] * eta
            - second_row["discharge_mwh"] / eta
        )

        self.assertAlmostEqual(first_row["soc_mwh"], expected_soc_after_first, places=6)
        self.assertAlmostEqual(second_row["soc_mwh"], expected_soc_after_second, places=6)
        self.assertAlmostEqual(result["summary"]["soc_end_mwh"], params.initial_soc_mwh, places=6)

    def test_efficiency_reduces_discharge_relative_to_charge(self):
        efficient_params = self._build_params(round_trip_efficiency=1.0)
        lossy_params = self._build_params(round_trip_efficiency=0.64)
        intervals = [
            {"timestamp": "2025-01-01T00:00:00Z", "price": 5.0, "interval_hours": 1.0},
            {"timestamp": "2025-01-01T01:00:00Z", "price": 120.0, "interval_hours": 1.0},
        ]

        efficient = run_bess_backtest_v1(efficient_params, intervals)
        lossy = run_bess_backtest_v1(lossy_params, intervals)

        self.assertGreater(
            efficient["summary"]["discharge_throughput_mwh"],
            lossy["summary"]["discharge_throughput_mwh"],
        )
        self.assertGreater(
            efficient["summary"]["gross_revenue"],
            lossy["summary"]["gross_revenue"],
        )


if __name__ == "__main__":
    unittest.main()
