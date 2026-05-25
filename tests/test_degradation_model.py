"""Unit tests for DegradationModel — capacity degradation calculations and boundary conditions."""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.degradation_model import DegradationModel


class DegradationModelFactoryTests(unittest.TestCase):
    """Tests for DegradationModel.from_user_input() factory method."""

    def test_user_linear_model_created_with_valid_rate(self):
        model = DegradationModel.from_user_input(0.05)
        self.assertEqual(model.model_type, "user-linear")
        self.assertAlmostEqual(model.annual_rate, 0.05)

    def test_user_linear_model_with_zero_rate(self):
        model = DegradationModel.from_user_input(0.0)
        self.assertEqual(model.model_type, "user-linear")
        self.assertAlmostEqual(model.annual_rate, 0.0)

    def test_user_linear_model_with_max_rate(self):
        model = DegradationModel.from_user_input(0.15)
        self.assertEqual(model.model_type, "user-linear")
        self.assertAlmostEqual(model.annual_rate, 0.15)

    def test_dual_factor_default_when_none(self):
        model = DegradationModel.from_user_input(None)
        self.assertEqual(model.model_type, "dual-factor-default")
        self.assertIsNone(model.annual_rate)
        self.assertAlmostEqual(model.parameters["calendar"], 0.015)
        self.assertAlmostEqual(model.parameters["cyclic_per_cycle"], 0.0000333)

    def test_raises_for_negative_rate(self):
        with self.assertRaises(ValueError) as ctx:
            DegradationModel.from_user_input(-0.01)
        self.assertIn("between 0 and 0.15", str(ctx.exception))

    def test_raises_for_rate_above_max(self):
        with self.assertRaises(ValueError) as ctx:
            DegradationModel.from_user_input(0.16)
        self.assertIn("between 0 and 0.15", str(ctx.exception))

    def test_raises_for_large_rate(self):
        with self.assertRaises(ValueError):
            DegradationModel.from_user_input(1.0)


class DegradationModelUserLinearTests(unittest.TestCase):
    """Tests for user-linear capacity_at_year calculations."""

    def test_year_zero_is_full_capacity(self):
        model = DegradationModel.from_user_input(0.05)
        self.assertAlmostEqual(model.capacity_at_year(0, cycles_per_year=365), 1.0)

    def test_year_one_linear_degradation(self):
        model = DegradationModel.from_user_input(0.05)
        # After 1 year: 1.0 - 0.05 * 1 = 0.95
        self.assertAlmostEqual(model.capacity_at_year(1, cycles_per_year=365), 0.95)

    def test_year_ten_linear_degradation(self):
        model = DegradationModel.from_user_input(0.03)
        # After 10 years: 1.0 - 0.03 * 10 = 0.70
        self.assertAlmostEqual(model.capacity_at_year(10, cycles_per_year=365), 0.70)

    def test_capacity_never_goes_below_zero(self):
        model = DegradationModel.from_user_input(0.10)
        # After 15 years: 1.0 - 0.10 * 15 = -0.5 -> clamped to 0.0
        self.assertAlmostEqual(model.capacity_at_year(15, cycles_per_year=365), 0.0)

    def test_zero_rate_means_no_degradation(self):
        model = DegradationModel.from_user_input(0.0)
        self.assertAlmostEqual(model.capacity_at_year(20, cycles_per_year=500), 1.0)

    def test_linear_model_ignores_cycles_per_year(self):
        model = DegradationModel.from_user_input(0.05)
        # Linear model only uses annual_rate * year, not cycles
        cap_low_cycles = model.capacity_at_year(5, cycles_per_year=100)
        cap_high_cycles = model.capacity_at_year(5, cycles_per_year=1000)
        self.assertAlmostEqual(cap_low_cycles, cap_high_cycles)


class DegradationModelDualFactorTests(unittest.TestCase):
    """Tests for dual-factor-default capacity_at_year calculations."""

    def test_year_zero_is_full_capacity(self):
        model = DegradationModel.from_user_input(None)
        self.assertAlmostEqual(model.capacity_at_year(0, cycles_per_year=365), 1.0)

    def test_calendar_degradation_only(self):
        model = DegradationModel.from_user_input(None)
        # With 0 cycles: only calendar loss = 0.015 * year
        cap = model.capacity_at_year(1, cycles_per_year=0)
        self.assertAlmostEqual(cap, 1.0 - 0.015)

    def test_cyclic_degradation_contribution(self):
        model = DegradationModel.from_user_input(None)
        # With 365 cycles/year, year 1:
        # calendar_loss = 0.015 * 1 = 0.015
        # cyclic_loss = 0.0000333 * 365 * 1 = 0.012155
        # total = 1.0 - 0.015 - 0.012155 = 0.972845
        cap = model.capacity_at_year(1, cycles_per_year=365)
        expected = 1.0 - 0.015 - (0.0000333 * 365 * 1)
        self.assertAlmostEqual(cap, expected, places=5)

    def test_more_cycles_means_more_degradation(self):
        model = DegradationModel.from_user_input(None)
        cap_low = model.capacity_at_year(5, cycles_per_year=100)
        cap_high = model.capacity_at_year(5, cycles_per_year=500)
        self.assertGreater(cap_low, cap_high)

    def test_dual_factor_capacity_never_below_zero(self):
        model = DegradationModel.from_user_input(None)
        # Very high cycles over many years should clamp to 0
        cap = model.capacity_at_year(100, cycles_per_year=10000)
        self.assertAlmostEqual(cap, 0.0)

    def test_dual_factor_year_20_typical_usage(self):
        model = DegradationModel.from_user_input(None)
        # Typical BESS: ~365 cycles/year, 20 years
        # calendar_loss = 0.015 * 20 = 0.30
        # cyclic_loss = 0.0000333 * 365 * 20 = 0.24309
        # total loss = 0.54309 -> capacity = 0.45691
        cap = model.capacity_at_year(20, cycles_per_year=365)
        expected = 1.0 - (0.015 * 20) - (0.0000333 * 365 * 20)
        self.assertAlmostEqual(cap, expected, places=4)

    def test_monotonically_decreasing_over_years(self):
        model = DegradationModel.from_user_input(None)
        capacities = [model.capacity_at_year(y, cycles_per_year=365) for y in range(20)]
        for i in range(1, len(capacities)):
            self.assertLessEqual(capacities[i], capacities[i - 1])


class DegradationModelEdgeCasesTests(unittest.TestCase):
    """Edge case and boundary condition tests."""

    def test_boundary_rate_just_below_max(self):
        model = DegradationModel.from_user_input(0.149999)
        self.assertEqual(model.model_type, "user-linear")

    def test_boundary_rate_at_exact_zero(self):
        model = DegradationModel.from_user_input(0.0)
        self.assertEqual(model.model_type, "user-linear")
        self.assertAlmostEqual(model.capacity_at_year(100, cycles_per_year=1000), 1.0)

    def test_capacity_at_year_zero_always_one(self):
        for rate in [0.0, 0.05, 0.10, 0.15]:
            model = DegradationModel.from_user_input(rate)
            self.assertAlmostEqual(model.capacity_at_year(0, cycles_per_year=365), 1.0)

    def test_dual_factor_with_zero_cycles(self):
        model = DegradationModel.from_user_input(None)
        # Only calendar degradation applies
        cap_y5 = model.capacity_at_year(5, cycles_per_year=0)
        expected = 1.0 - 0.015 * 5
        self.assertAlmostEqual(cap_y5, expected)


if __name__ == "__main__":
    unittest.main()
