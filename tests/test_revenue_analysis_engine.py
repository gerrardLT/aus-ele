"""Unit tests for RevenueAnalysisEngine — revenue calculation formula verification."""

import unittest
from math import sqrt

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.revenue_analysis_engine import RevenueAnalysisEngine
from engines.exceptions import DimensionMismatchError


class RevenueAnalysisEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = RevenueAnalysisEngine()

    # --- Basic revenue calculation ---

    def test_positive_price_generates_revenue(self):
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0
        )
        self.assertGreater(result.gross_revenue, 0.0)

    def test_zero_price_generates_no_revenue(self):
        prices = [{"price": 0.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0
        )
        self.assertAlmostEqual(result.gross_revenue, 0.0)

    def test_negative_price_generates_no_revenue(self):
        prices = [{"price": -50.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0
        )
        self.assertAlmostEqual(result.gross_revenue, 0.0)

    def test_revenue_formula_with_perfect_efficiency(self):
        # With RTE=1.0, one_way_eff=1.0
        # max_discharge_mwh = min(1.0 * 1.0, 2.0) = 1.0
        # discharge_mwh = 1.0 * 1.0 = 1.0
        # gross = 1.0 * 100 = 100.0
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0
        )
        self.assertAlmostEqual(result.gross_revenue, 100.0)

    def test_revenue_formula_with_efficiency_loss(self):
        # RTE=0.81, one_way_eff = sqrt(0.81) = 0.9
        # max_discharge_mwh = min(1.0 * 1.0, 2.0) = 1.0
        # discharge_mwh = 1.0 * 0.9 = 0.9
        # gross = 0.9 * 100 = 90.0
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=0.81
        )
        self.assertAlmostEqual(result.gross_revenue, 90.0)

    def test_power_limits_discharge(self):
        # power_mw=0.5, interval_hours=1.0 -> max_discharge = 0.5 MWh
        # With RTE=1.0: discharge_mwh = 0.5, gross = 0.5 * 200 = 100
        prices = [{"price": 200.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=0.5, energy_mwh=10.0, round_trip_efficiency=1.0
        )
        self.assertAlmostEqual(result.gross_revenue, 100.0)

    def test_energy_limits_discharge(self):
        # power_mw=10.0, interval_hours=1.0 -> power limit = 10 MWh
        # energy_mwh=0.5 -> energy limit = 0.5 MWh (binding)
        # With RTE=1.0: discharge_mwh = 0.5, gross = 0.5 * 200 = 100
        prices = [{"price": 200.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=10.0, energy_mwh=0.5, round_trip_efficiency=1.0
        )
        self.assertAlmostEqual(result.gross_revenue, 100.0)

    # --- Network fees ---

    def test_network_fees_reduce_net_revenue(self):
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result_no_fee = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            network_fee_per_mwh=0.0,
        )
        result_with_fee = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            network_fee_per_mwh=10.0,
        )
        self.assertGreater(result_no_fee.net_revenue, result_with_fee.net_revenue)

    def test_network_fee_calculation(self):
        # discharge_mwh = 1.0 (RTE=1.0, power=1, interval=1h, energy=2)
        # network_fee = 1.0 * 5.0 = 5.0
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            network_fee_per_mwh=5.0,
        )
        self.assertAlmostEqual(result.costs["network_fees"], 5.0)

    # --- Degradation rate ---

    def test_degradation_rate_reduces_effective_capacity(self):
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result_no_deg = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            degradation_rate=None,
        )
        result_with_deg = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            degradation_rate=0.10,
        )
        # With degradation, effective capacity is reduced, so gross revenue may differ
        # Also degradation cost is applied
        self.assertGreater(result_no_deg.net_revenue, result_with_deg.net_revenue)

    def test_degradation_cost_in_costs_dict(self):
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            degradation_rate=0.05,
        )
        self.assertGreater(result.costs["degradation"], 0.0)

    def test_no_degradation_cost_when_rate_is_none(self):
        prices = [{"price": 100.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=1.0,
            degradation_rate=None,
        )
        self.assertAlmostEqual(result.costs["degradation"], 0.0)

    # --- Metadata ---

    def test_metadata_unit_is_dollar(self):
        prices = [{"price": 50.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=2.0, round_trip_efficiency=0.9
        )
        self.assertEqual(result.metadata.unit, "$")

    # --- Dimension validation ---

    def test_validate_input_dimensions_rejects_price_statistics(self):
        input_data = {"metadata": {"unit": "$/MWh"}, "statistics": {"mean": 50.0}}
        with self.assertRaises(DimensionMismatchError) as ctx:
            self.engine.validate_input_dimensions(input_data)
        self.assertEqual(ctx.exception.received_unit, "$/MWh")
        self.assertEqual(ctx.exception.expected_unit, "raw_price_series")

    def test_validate_input_dimensions_accepts_raw_data(self):
        input_data = {"prices": [{"price": 50.0}]}
        # Should not raise
        self.engine.validate_input_dimensions(input_data)

    def test_validate_input_dimensions_accepts_dollar_unit(self):
        input_data = {"metadata": {"unit": "$"}, "total_revenue": 1000.0}
        # Should not raise — only $/MWh is rejected
        self.engine.validate_input_dimensions(input_data)

    # --- Multiple intervals ---

    def test_multiple_intervals_accumulate_revenue(self):
        prices = [
            {"price": 100.0, "interval_hours": 1.0},
            {"price": 200.0, "interval_hours": 1.0},
        ]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=5.0, round_trip_efficiency=1.0
        )
        # Each interval: discharge = min(1*1, 5) = 1 MWh
        # Interval 1: 1 * 100 = 100, Interval 2: 1 * 200 = 200
        # Total gross = 300
        self.assertAlmostEqual(result.gross_revenue, 300.0)

    def test_default_interval_hours(self):
        # Default interval_hours is 5/60 = 0.0833...
        prices = [{"price": 120.0}]
        result = self.engine.calculate(
            prices, power_mw=1.0, energy_mwh=10.0, round_trip_efficiency=1.0
        )
        expected_discharge = min(1.0 * (5.0 / 60.0), 10.0)
        expected_gross = expected_discharge * 120.0
        self.assertAlmostEqual(result.gross_revenue, expected_gross, places=4)

    # --- Summary fields ---

    def test_summary_contains_input_parameters(self):
        prices = [{"price": 50.0, "interval_hours": 1.0}]
        result = self.engine.calculate(
            prices, power_mw=2.0, energy_mwh=4.0, round_trip_efficiency=0.85,
            degradation_rate=0.02, network_fee_per_mwh=3.0,
        )
        self.assertAlmostEqual(result.summary["power_mw"], 2.0)
        self.assertAlmostEqual(result.summary["energy_mwh"], 4.0)
        self.assertAlmostEqual(result.summary["round_trip_efficiency"], 0.85)
        self.assertAlmostEqual(result.summary["degradation_rate"], 0.02)
        self.assertAlmostEqual(result.summary["network_fee_per_mwh"], 3.0)


if __name__ == "__main__":
    unittest.main()
