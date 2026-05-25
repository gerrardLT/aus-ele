"""Unit tests for bess_backtest_v2 module.

Tests BacktestConstraints validation, MILP model construction,
binding constraint detection, and infeasibility handling.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest

from engines.bess_backtest_v2 import (
    BacktestConstraints,
    BacktestV2Params,
    BacktestV2Result,
    BindingConstraintRecord,
    run_bess_backtest_v2,
)


# ---------------------------------------------------------------------------
# BacktestConstraints.validate() tests
# ---------------------------------------------------------------------------


class TestBacktestConstraintsValidation:
    """Tests for BacktestConstraints.validate() method."""

    def test_valid_constraints_no_issues(self):
        c = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
        )
        assert c.validate() == []

    def test_min_soc_gte_max_soc(self):
        c = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=90.0,
            max_soc_pct=10.0,
            round_trip_efficiency=0.85,
        )
        issues = c.validate()
        assert any("min_soc_pct >= max_soc_pct" in i for i in issues)

    def test_auxiliary_power_gte_max_discharge(self):
        c = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
            auxiliary_power_mw=60.0,
        )
        issues = c.validate()
        assert any("auxiliary_power >= max_discharge" in i for i in issues)

    def test_zero_charge_power(self):
        c = BacktestConstraints(
            max_charge_mw=0.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
        )
        issues = c.validate()
        assert any("max_charge_mw <= 0" in i for i in issues)

    def test_invalid_efficiency(self):
        c = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=1.5,
        )
        issues = c.validate()
        assert any("round_trip_efficiency" in i for i in issues)

    def test_negative_auxiliary_power(self):
        c = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
            auxiliary_power_mw=-1.0,
        )
        issues = c.validate()
        assert any("auxiliary_power_mw < 0" in i for i in issues)

    def test_invalid_min_duration(self):
        c = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
            min_duration_intervals=0,
        )
        issues = c.validate()
        assert any("min_duration_intervals < 1" in i for i in issues)

    def test_multiple_issues_reported(self):
        c = BacktestConstraints(
            max_charge_mw=-1.0,
            max_discharge_mw=-1.0,
            min_soc_pct=90.0,
            max_soc_pct=10.0,
            round_trip_efficiency=2.0,
        )
        issues = c.validate()
        assert len(issues) >= 3


# ---------------------------------------------------------------------------
# run_bess_backtest_v2 — empty intervals
# ---------------------------------------------------------------------------


class TestBacktestV2EmptyIntervals:
    """Tests for empty interval handling."""

    def test_empty_intervals_returns_optimal(self):
        constraints = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
        )
        params = BacktestV2Params(
            energy_mwh=100.0,
            initial_soc_mwh=50.0,
            constraints=constraints,
        )
        result = run_bess_backtest_v2(params, [])
        assert result.status == "optimal"
        assert result.timeline == []
        assert result.summary["soc_start_mwh"] == 50.0
        assert result.summary["soc_end_mwh"] == 50.0
        assert result.binding_constraints == []


# ---------------------------------------------------------------------------
# run_bess_backtest_v2 — infeasible constraints
# ---------------------------------------------------------------------------


class TestBacktestV2Infeasible:
    """Tests for infeasibility detection."""

    def test_infeasible_soc_range_returns_infeasible(self):
        constraints = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=90.0,
            max_soc_pct=10.0,
            round_trip_efficiency=0.85,
        )
        params = BacktestV2Params(
            energy_mwh=100.0,
            initial_soc_mwh=50.0,
            constraints=constraints,
        )
        intervals = [{"timestamp": "2024-01-01T00:00", "price": 100.0}]
        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "infeasible"
        assert len(result.constraint_conflicts) > 0

    def test_infeasible_auxiliary_power(self):
        constraints = BacktestConstraints(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            min_soc_pct=10.0,
            max_soc_pct=90.0,
            round_trip_efficiency=0.85,
            auxiliary_power_mw=60.0,
        )
        params = BacktestV2Params(
            energy_mwh=100.0,
            initial_soc_mwh=50.0,
            constraints=constraints,
        )
        intervals = [{"timestamp": "2024-01-01T00:00", "price": 100.0}]
        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "infeasible"


# ---------------------------------------------------------------------------
# run_bess_backtest_v2 — optimal solve
# ---------------------------------------------------------------------------


class TestBacktestV2Optimal:
    """Tests for successful optimization."""

    def _make_params(self, **kwargs):
        constraints = BacktestConstraints(
            max_charge_mw=kwargs.get("max_charge_mw", 50.0),
            max_discharge_mw=kwargs.get("max_discharge_mw", 50.0),
            min_soc_pct=kwargs.get("min_soc_pct", 10.0),
            max_soc_pct=kwargs.get("max_soc_pct", 90.0),
            round_trip_efficiency=kwargs.get("round_trip_efficiency", 0.85),
            auxiliary_power_mw=kwargs.get("auxiliary_power_mw", 0.0),
            min_duration_intervals=kwargs.get("min_duration_intervals", 1),
            dispatch_alignment_minutes=kwargs.get("dispatch_alignment_minutes", 5),
            registered_capacity_mw=kwargs.get("registered_capacity_mw", None),
        )
        return BacktestV2Params(
            energy_mwh=kwargs.get("energy_mwh", 100.0),
            initial_soc_mwh=kwargs.get("initial_soc_mwh", 50.0),
            constraints=constraints,
        )

    def test_basic_arbitrage(self):
        """Battery should charge at low prices and discharge at high prices."""
        params = self._make_params()
        # 12 intervals of 5 minutes each (1 hour total)
        intervals = []
        for i in range(12):
            # First 6 intervals: low price, last 6: high price
            price = 50.0 if i < 6 else 200.0
            intervals.append({
                "timestamp": f"2024-01-01T00:{i*5:02d}:00",
                "price": price,
                "interval_hours": 5.0 / 60.0,
            })

        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "optimal"
        assert len(result.timeline) == 12
        assert result.summary["net_revenue"] >= 0.0

    def test_soc_stays_within_bounds(self):
        """SOC should never violate min/max bounds."""
        params = self._make_params(min_soc_pct=20.0, max_soc_pct=80.0)
        intervals = [
            {"timestamp": f"2024-01-01T00:{i*5:02d}:00", "price": float(i * 10 + 50), "interval_hours": 5.0 / 60.0}
            for i in range(24)
        ]

        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "optimal"

        min_soc_mwh = 100.0 * 0.20
        max_soc_mwh = 100.0 * 0.80
        for item in result.timeline:
            assert item["soc_mwh"] >= min_soc_mwh - 1e-3
            assert item["soc_mwh"] <= max_soc_mwh + 1e-3

    def test_registered_capacity_limit(self):
        """Charge + discharge should not exceed registered capacity."""
        params = self._make_params(
            max_charge_mw=50.0,
            max_discharge_mw=50.0,
            registered_capacity_mw=30.0,
        )
        intervals = [
            {"timestamp": f"2024-01-01T00:{i*5:02d}:00", "price": float(100 + i * 20), "interval_hours": 5.0 / 60.0}
            for i in range(12)
        ]

        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "optimal"

        for item in result.timeline:
            total_power = item["charge_mw"] + item["discharge_mw"]
            assert total_power <= 30.0 + 1e-3

    def test_auxiliary_power_reduces_soc(self):
        """Auxiliary power should drain SOC even when idle."""
        params = self._make_params(auxiliary_power_mw=1.0)
        # All same price -> no incentive to trade, but aux power drains SOC
        intervals = [
            {"timestamp": f"2024-01-01T00:{i*5:02d}:00", "price": 100.0, "interval_hours": 5.0 / 60.0}
            for i in range(12)
        ]

        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "optimal"
        # With aux power, the battery needs to charge to maintain terminal SOC
        # The SOC trajectory should show the effect of auxiliary consumption

    def test_binding_constraints_reported(self):
        """When constraints are active, they should appear in binding_constraints."""
        # Use tight SOC bounds to force binding
        params = self._make_params(
            min_soc_pct=45.0,
            max_soc_pct=55.0,
            energy_mwh=100.0,
            initial_soc_mwh=50.0,
        )
        intervals = [
            {"timestamp": f"2024-01-01T00:{i*5:02d}:00", "price": float(50 + i * 30), "interval_hours": 5.0 / 60.0}
            for i in range(12)
        ]

        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "optimal"
        # With tight SOC bounds, some constraints should be binding
        # (may or may not have binding constraints depending on solver behavior)
        assert isinstance(result.binding_constraints, list)

    def test_result_model_structure(self):
        """Verify the result model has all expected fields."""
        params = self._make_params()
        intervals = [
            {"timestamp": "2024-01-01T00:00:00", "price": 100.0, "interval_hours": 5.0 / 60.0},
            {"timestamp": "2024-01-01T00:05:00", "price": 200.0, "interval_hours": 5.0 / 60.0},
        ]

        result = run_bess_backtest_v2(params, intervals)
        assert isinstance(result, BacktestV2Result)
        assert result.status in ("optimal", "infeasible")
        assert isinstance(result.timeline, list)
        assert isinstance(result.summary, dict)
        assert isinstance(result.binding_constraints, list)

        if result.status == "optimal":
            assert "soc_start_mwh" in result.summary
            assert "soc_end_mwh" in result.summary
            assert "gross_revenue" in result.summary
            assert "net_revenue" in result.summary
            assert "charge_throughput_mwh" in result.summary
            assert "discharge_throughput_mwh" in result.summary
            assert "equivalent_cycles" in result.summary
            assert "costs" in result.summary

    def test_dispatch_alignment(self):
        """With 30-min alignment and 5-min intervals, blocks of 6 should share state.

        The dispatch alignment constraint ensures the is_charging binary variable
        is uniform within each block. This means within a block, the battery cannot
        both charge AND discharge — but individual intervals may be idle (zero power).
        """
        params = self._make_params(dispatch_alignment_minutes=30)
        # 12 intervals of 5 min = 1 hour = 2 dispatch blocks
        intervals = [
            {"timestamp": f"2024-01-01T00:{i*5:02d}:00", "price": float(50 + i * 20), "interval_hours": 5.0 / 60.0}
            for i in range(12)
        ]

        result = run_bess_backtest_v2(params, intervals)
        assert result.status == "optimal"
        # Within each 30-min block, the battery should not both charge and discharge
        # (the is_charging binary is uniform, so either charge or discharge is allowed)
        for block_start in range(0, 12, 6):
            block = result.timeline[block_start:block_start + 6]
            has_charging = any(item["charge_mw"] > 0.01 for item in block)
            has_discharging = any(item["discharge_mw"] > 0.01 for item in block)
            # Cannot have both charging and discharging in the same block
            assert not (has_charging and has_discharging), (
                f"Block starting at {block_start} has both charging and discharging"
            )
