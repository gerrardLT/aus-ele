"""Unit tests for rainflow cycle counting and DoD-dependent battery degradation.

Covers the P1 degradation rework:
- rainflow.count_cycles (ASTM E1049) on synthetic signals
- rainflow.dod_severity_from_soc severity normalisation
- BatteryModel multiplicative SoH accumulation, knee-point acceleration,
  DoD-severity scaling, and the de-hardcoded marginal degradation cost.
"""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.rainflow import count_cycles, dod_severity_from_soc
from engines.battery_model import BatteryModel
from models.financial_params import BatterySpecs


class RainflowCountingTests(unittest.TestCase):
    def test_empty_and_flat_series_yield_no_cycles(self):
        self.assertEqual(count_cycles([]), [])
        self.assertEqual(count_cycles([5.0, 5.0, 5.0]), [])

    def test_single_full_cycle(self):
        # A symmetric triangle repeated: 0 -> 2 -> 0 -> 2 -> 0
        cycles = count_cycles([0.0, 2.0, 0.0, 2.0, 0.0])
        total = sum(count for _, count in cycles)
        # Total counted cycles (full + half) should conserve reversals.
        self.assertGreater(total, 0.0)
        # The dominant range should be 2.0.
        self.assertTrue(any(abs(rng - 2.0) < 1e-9 for rng, _ in cycles))

    def test_deep_cycle_has_larger_range_than_shallow(self):
        deep = count_cycles([0.0, 10.0, 0.0])
        shallow = count_cycles([0.0, 1.0, 0.0])
        self.assertGreater(max(r for r, _ in deep), max(r for r, _ in shallow))


class DoDSeverityTests(unittest.TestCase):
    def test_zero_capacity_returns_neutral(self):
        self.assertEqual(dod_severity_from_soc([0.0, 1.0], 0.0), (0.0, 1.0))

    def test_full_depth_cycles_have_severity_one(self):
        # Full-depth cycling between 0 and capacity → severity == 1.0.
        cap = 10.0
        _, severity = dod_severity_from_soc([0.0, cap, 0.0, cap, 0.0], cap)
        self.assertAlmostEqual(severity, 1.0, places=6)

    def test_shallow_cycles_have_severity_below_one(self):
        # Shallow cycling (10% DoD) with exponent b>1 → severity < 1.0.
        cap = 10.0
        _, severity = dod_severity_from_soc([0.0, 1.0, 0.0, 1.0, 0.0], cap, non_linear_factor=1.2)
        self.assertLess(severity, 1.0)
        self.assertGreater(severity, 0.0)

    def test_throughput_counts_equivalent_full_cycles(self):
        cap = 10.0
        throughput, _ = dod_severity_from_soc([0.0, cap, 0.0, cap, 0.0], cap)
        # Two full-depth charge/discharge swings ≈ 2 equivalent full cycles.
        self.assertGreater(throughput, 0.0)


class BatteryModelDegradationTests(unittest.TestCase):
    def _specs(self, **overrides) -> BatterySpecs:
        base = dict(
            power_mw=100.0,
            duration_hours=4.0,
            calendar_degradation_rate=0.015,
            base_cycle_degradation_rate=0.00003,
        )
        base.update(overrides)
        return BatterySpecs(**base)

    def test_calculate_degradation_scales_with_dod_severity(self):
        model = BatteryModel(self._specs())
        deep = model.calculate_degradation(300.0, year=1, dod_severity=1.0)
        shallow = model.calculate_degradation(300.0, year=1, dod_severity=0.5)
        # Shallow cycling degrades less than full-depth for equal throughput.
        self.assertGreater(deep, shallow)

    def test_calculate_degradation_no_hardcoded_double(self):
        specs = self._specs()
        model = BatteryModel(specs)
        deg = model.calculate_degradation(100.0, year=1, dod_severity=1.0)
        expected = specs.calendar_degradation_rate + 100.0 * specs.base_cycle_degradation_rate * 1.0
        self.assertAlmostEqual(deg, expected)

    def test_marginal_cost_removes_hardcoded_factor(self):
        specs = self._specs()
        model = BatteryModel(specs)
        cost = model.get_marginal_cost_of_degradation(300.0, dod_severity=1.0)
        expected = 300.0 * 1000 * specs.base_cycle_degradation_rate * 1.0
        self.assertAlmostEqual(cost, expected)

    def test_soh_accumulates_multiplicatively_and_monotonic(self):
        model = BatteryModel(self._specs())
        soh_history, _ = model.simulate_lifetime([365.0] * 10, project_life_years=10)
        for i in range(1, len(soh_history)):
            self.assertLessEqual(soh_history[i], soh_history[i - 1])
        self.assertLess(soh_history[0], 1.0)

    def test_knee_point_accelerates_degradation(self):
        # A high knee_acceleration_factor should push end-of-life SoH lower
        # than a neutral (1.0) factor once below the knee point.
        cycles = [1500.0] * 20
        base = BatteryModel(self._specs(knee_point_soh=0.7, knee_acceleration_factor=1.0))
        kneed = BatteryModel(self._specs(knee_point_soh=0.7, knee_acceleration_factor=2.0))
        soh_base, _ = base.simulate_lifetime(cycles, project_life_years=20)
        soh_kneed, _ = kneed.simulate_lifetime(cycles, project_life_years=20)
        # At least one late year is strictly lower under acceleration.
        self.assertTrue(any(k < b for k, b in zip(soh_kneed, soh_base)))

    def test_higher_dod_severity_history_lowers_soh(self):
        model = BatteryModel(self._specs())
        cycles = [365.0] * 10
        low = model.simulate_lifetime(cycles, 10, dod_severity_history=[0.5] * 10)[0]
        high = model.simulate_lifetime(cycles, 10, dod_severity_history=[1.0] * 10)[0]
        self.assertLess(high[-1], low[-1])


if __name__ == "__main__":
    unittest.main()
