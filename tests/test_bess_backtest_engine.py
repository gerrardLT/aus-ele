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

    def _two_flat_days(self, low_price: float, high_price: float) -> list[dict]:
        """48 hourly intervals: day 1 flat-low, day 2 flat-high.

        There is no *intraday* spread on either day, so a myopic 24h rolling
        window captures nothing, while a full-horizon perfect-foresight solve
        can charge cheaply on day 1 and discharge into day 2's high price.
        """
        intervals = []
        for hour in range(24):
            intervals.append(
                {"timestamp": f"2025-01-01T{hour:02d}:00:00Z", "price": low_price, "interval_hours": 1.0}
            )
        for hour in range(24):
            intervals.append(
                {"timestamp": f"2025-01-02T{hour:02d}:00:00Z", "price": high_price, "interval_hours": 1.0}
            )
        return intervals

    def test_reports_window_count_and_foresight_hours(self):
        params = self._build_params()
        intervals = self._two_flat_days(50.0, 200.0)

        rolling = run_bess_backtest_v1(params, intervals, window_hours=24.0)
        perfect = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        self.assertEqual(rolling["summary"]["foresight_window_hours"], 24.0)
        self.assertEqual(rolling["summary"]["lookahead_hours"], 24.0)
        self.assertEqual(rolling["summary"]["window_count"], 2)
        self.assertEqual(perfect["summary"]["window_count"], 1)

    def test_mpc_captures_arbitrage_within_lookahead(self):
        params = self._build_params()
        intervals = self._two_flat_days(50.0, 200.0)

        # With a 24h lookahead the operator sees the whole 2-day horizon, so the
        # receding-horizon result should match perfect foresight and never
        # exhibit the naive-window "liquidate at boundary" loss.
        rolling = run_bess_backtest_v1(params, intervals, window_hours=24.0)
        perfect = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        self.assertGreater(rolling["summary"]["net_revenue"], 0.0)
        self.assertAlmostEqual(
            rolling["summary"]["net_revenue"],
            perfect["summary"]["net_revenue"],
            places=3,
        )

    def test_arbitrage_beyond_lookahead_relies_on_perfect_foresight_bound(self):
        # Limited foresight can never *beat* perfect foresight; on real
        # volatile price histories with binding cycle/degradation limits it
        # falls short, producing the empirical "% of perfect foresight"
        # haircut. On simple monotone toy horizons MPC's chained lookahead can
        # match perfect foresight, so the invariant we assert here is the
        # fundamental upper bound (see test_rolling_net_revenue_never_exceeds
        # _perfect_foresight for the volatile-price case).
        params = self._build_params()
        intervals = (
            [{"timestamp": f"2025-01-01T{h:02d}:00:00Z", "price": 30.0, "interval_hours": 1.0} for h in range(24)]
            + [{"timestamp": f"2025-01-02T{h:02d}:00:00Z", "price": 80.0, "interval_hours": 1.0} for h in range(24)]
            + [{"timestamp": f"2025-01-03T{h:02d}:00:00Z", "price": 300.0, "interval_hours": 1.0} for h in range(24)]
        )

        rolling = run_bess_backtest_v1(params, intervals, window_hours=24.0, lookahead_hours=24.0)
        perfect = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        self.assertLessEqual(
            rolling["summary"]["net_revenue"],
            perfect["summary"]["net_revenue"] + 1e-6,
        )

    def test_rolling_horizon_is_energy_neutral(self):
        params = self._build_params(round_trip_efficiency=0.85)
        intervals = self._two_flat_days(50.0, 200.0)

        rolling = run_bess_backtest_v1(params, intervals, window_hours=24.0)

        self.assertAlmostEqual(
            rolling["summary"]["soc_end_mwh"], params.initial_soc_mwh, places=6
        )

    def test_rolling_net_revenue_never_exceeds_perfect_foresight(self):
        params = self._build_params(round_trip_efficiency=0.88)
        intervals = [
            {"timestamp": f"2025-01-0{1 + hour // 24}T{hour % 24:02d}:00:00Z",
             "price": 20.0 + (hour % 12) * 25.0, "interval_hours": 1.0}
            for hour in range(72)
        ]

        rolling = run_bess_backtest_v1(params, intervals, window_hours=24.0)
        perfect = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        # Limited foresight can never beat perfect foresight on the same prices.
        self.assertLessEqual(
            rolling["summary"]["net_revenue"],
            perfect["summary"]["net_revenue"] + 1e-6,
        )


class BessBacktestMergedConstraintTests(unittest.TestCase):
    """Coverage for the V2-derived constraints merged into the V1 engine."""

    def _build_params(self, **overrides):
        payload = {
            "market": "NEM",
            "region": "NSW1",
            "year": 2025,
            "power_mw": 1.0,
            "energy_mwh": 2.0,
            "duration_hours": 2.0,
            "round_trip_efficiency": 0.9,
            "max_cycles_per_day": 10.0,
        }
        payload.update(overrides)
        return BessBacktestParams(**payload)

    def _spread_day(self) -> list[dict]:
        """24 hourly intervals with a clear low/high arbitrage spread."""
        return [
            {
                "timestamp": f"2025-01-01T{h:02d}:00:00Z",
                "price": 20.0 if h < 12 else 200.0,
                "interval_hours": 1.0,
            }
            for h in range(24)
        ]

    def test_defaults_match_explicit_symmetric_limits(self):
        # Leaving the new fields unset must reproduce the original LP behaviour
        # exactly (zero regression), equal to explicitly restating power_mw.
        base = self._build_params()
        explicit = self._build_params(max_charge_mw=1.0, max_discharge_mw=1.0)
        intervals = self._spread_day()

        base_result = run_bess_backtest_v1(base, intervals, window_hours=0.0)
        explicit_result = run_bess_backtest_v1(explicit, intervals, window_hours=0.0)

        self.assertAlmostEqual(
            base_result["summary"]["net_revenue"],
            explicit_result["summary"]["net_revenue"],
            places=6,
        )

    def test_independent_discharge_limit_caps_power(self):
        params = self._build_params(max_discharge_mw=0.4)
        intervals = self._spread_day()

        result = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        for row in result["timeline"]:
            self.assertLessEqual(row["discharge_mw"], 0.4 + 1e-6)

    def test_independent_charge_limit_caps_power(self):
        params = self._build_params(max_charge_mw=0.3)
        intervals = self._spread_day()

        result = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        for row in result["timeline"]:
            self.assertLessEqual(row["charge_mw"], 0.3 + 1e-6)

    def test_registered_capacity_caps_combined_power(self):
        params = self._build_params(registered_capacity_mw=0.5)
        intervals = self._spread_day()

        result = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        for row in result["timeline"]:
            self.assertLessEqual(
                row["charge_mw"] + row["discharge_mw"], 0.5 + 1e-6
            )

    def test_auxiliary_power_forces_net_import_to_stay_neutral(self):
        # With a parasitic load and a flat price (no arbitrage incentive) the
        # battery must still import energy to hold its terminal SoC neutral,
        # so charge throughput must exceed discharge throughput.
        params = self._build_params(auxiliary_power_mw=0.05)
        intervals = [
            {"timestamp": f"2025-01-01T{h:02d}:00:00Z", "price": 50.0, "interval_hours": 1.0}
            for h in range(24)
        ]

        result = run_bess_backtest_v1(params, intervals, window_hours=0.0)

        summary = result["summary"]
        self.assertGreater(
            summary["charge_throughput_mwh"],
            summary["discharge_throughput_mwh"] + 1e-6,
        )

    def test_min_duration_engages_milp_and_cannot_beat_unconstrained(self):
        # Requiring a minimum hold duration removes flexibility, so revenue can
        # never exceed the unconstrained LP optimum on the same prices.
        intervals = [
            {
                "timestamp": f"2025-01-01T{h:02d}:00:00Z",
                "price": 20.0 if h % 2 == 0 else 200.0,
                "interval_hours": 1.0,
            }
            for h in range(24)
        ]
        unconstrained = run_bess_backtest_v1(
            self._build_params(), intervals, window_hours=0.0
        )
        constrained = run_bess_backtest_v1(
            self._build_params(min_duration_intervals=3), intervals, window_hours=0.0
        )

        self.assertLessEqual(
            constrained["summary"]["net_revenue"],
            unconstrained["summary"]["net_revenue"] + 1e-6,
        )
        # MILP path still returns an energy-neutral, in-bounds solution.
        self.assertAlmostEqual(
            constrained["summary"]["soc_end_mwh"],
            self._build_params().initial_soc_mwh,
            places=4,
        )

    def test_dispatch_alignment_keeps_block_state_uniform(self):
        # A 120-minute alignment over 60-minute intervals groups pairs of
        # intervals; within a pair the battery cannot both charge and discharge.
        params = self._build_params(dispatch_alignment_minutes=120)
        intervals = [
            {
                "timestamp": f"2025-01-01T{h:02d}:00:00Z",
                "price": 20.0 if h < 12 else 200.0,
                "interval_hours": 1.0,
            }
            for h in range(24)
        ]

        result = run_bess_backtest_v1(params, intervals, window_hours=0.0)
        timeline = result["timeline"]

        for block_start in range(0, len(timeline), 2):
            block = timeline[block_start:block_start + 2]
            charging = any(r["charge_mw"] > 1e-6 for r in block)
            discharging = any(r["discharge_mw"] > 1e-6 for r in block)
            self.assertFalse(
                charging and discharging,
                msg=f"block at {block_start} both charged and discharged",
            )

    # --- S1: availability derate (B1) --------------------------------------
    def _daily_intervals(self, days: int = 1):
        intervals = []
        for d in range(days):
            for h in range(24):
                intervals.append(
                    {
                        "timestamp": f"2025-01-{d + 1:02d}T{h:02d}:00:00Z",
                        "price": 20.0 if h < 12 else 200.0,
                        "interval_hours": 1.0,
                    }
                )
        return intervals

    def test_availability_100pct_is_zero_regression(self):
        params = self._build_params()
        intervals = self._daily_intervals()

        result = run_bess_backtest_v1(params, intervals)

        # Default availability is 100% -> figures must be unchanged and the
        # legacy "not applied" warning must be gone.
        self.assertTrue(result["summary"]["availability_applied"])
        self.assertEqual(result["summary"]["availability_pct"], 100.0)
        self.assertNotIn("availability_pct_not_applied_yet", result["summary"]["warnings"])

    def test_availability_scales_revenue_and_throughput_proportionally(self):
        full = self._build_params(availability_pct=100.0)
        derated = self._build_params(availability_pct=90.0)
        intervals = self._daily_intervals()

        full_res = run_bess_backtest_v1(full, intervals)["summary"]
        derated_res = run_bess_backtest_v1(derated, intervals)["summary"]

        factor = 0.9
        for key in ("gross_revenue", "net_revenue", "charge_throughput_mwh", "discharge_throughput_mwh", "equivalent_cycles"):
            self.assertAlmostEqual(derated_res[key], full_res[key] * factor, places=6)
        for cost_key in ("network_fees", "degradation", "variable_om"):
            self.assertAlmostEqual(
                derated_res["costs"][cost_key], full_res["costs"][cost_key] * factor, places=6
            )

    def test_availability_monotonic_in_revenue(self):
        intervals = self._daily_intervals()
        prev = None
        for pct in (100.0, 80.0, 50.0):
            net = run_bess_backtest_v1(
                self._build_params(availability_pct=pct), intervals
            )["summary"]["net_revenue"]
            if prev is not None:
                self.assertLessEqual(net, prev + 1e-9)
            prev = net

    # --- S1: % of perfect foresight (B4) -----------------------------------
    def test_pct_of_perfect_foresight_absent_by_default(self):
        params = self._build_params()
        result = run_bess_backtest_v1(params, self._daily_intervals())
        self.assertIsNone(result["summary"]["pct_of_perfect_foresight"])

    def test_pct_of_perfect_foresight_in_unit_interval(self):
        params = self._build_params(round_trip_efficiency=0.9)
        # Two days so the receding-horizon (12h window) result is a strict
        # subset of the single-window perfect-foresight optimum.
        intervals = self._daily_intervals(days=2)

        result = run_bess_backtest_v1(
            params, intervals, window_hours=12.0, compute_perfect_foresight_benchmark=True
        )
        pct = result["summary"]["pct_of_perfect_foresight"]

        self.assertIsNotNone(pct)
        self.assertGreater(pct, 0.0)
        self.assertLessEqual(pct, 1.0 + 1e-6)


if __name__ == "__main__":
    unittest.main()
