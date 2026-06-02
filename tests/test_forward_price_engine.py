"""Unit tests for Forward Price Scenario Engine.

Tests scenario definitions, region coverage, data file loading,
and past-date event exclusion with warning.

Requirements: 9.1-9.5, 14.5, 14.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import json
import logging
import tempfile
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest

from engines.forward_price_engine import (
    BASE_SPREAD_PARAMS,
    ForwardPriceEngine,
    SUPPORTED_REGIONS,
    DATA_DIR,
)
from models.forward_price_models import (
    EventType,
    ScenarioType,
)
from models.financial_params import BatterySpecs


# ---------------------------------------------------------------------------
# Scenario Definitions Tests
# ---------------------------------------------------------------------------


class TestScenarioDefinitions:
    """Test scenario definitions (Central/High/Low) and their assumptions."""

    def test_get_scenarios_returns_three(self):
        """get_scenarios() returns exactly 3 scenario definitions."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        scenarios = engine.get_scenarios()
        assert len(scenarios) == 3

    def test_central_scenario_defined(self):
        """Central scenario is defined with correct type and name."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        scenarios = engine.get_scenarios()
        central = next(s for s in scenarios if s.scenario == ScenarioType.CENTRAL)
        assert central.name == "Central"
        assert "ISP central" in central.description.lower() or "central" in central.description.lower()
        assert len(central.assumptions) > 0

    def test_high_scenario_defined(self):
        """High scenario is defined with accelerated coal retirement assumptions."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        scenarios = engine.get_scenarios()
        high = next(s for s in scenarios if s.scenario == ScenarioType.HIGH)
        assert high.name == "High"
        assert len(high.assumptions) > 0
        # High scenario should mention accelerated coal or slower BESS
        assumptions_text = " ".join(high.assumptions).lower()
        assert "coal" in assumptions_text or "earlier" in assumptions_text

    def test_low_scenario_defined(self):
        """Low scenario is defined with coal extension and faster BESS assumptions."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        scenarios = engine.get_scenarios()
        low = next(s for s in scenarios if s.scenario == ScenarioType.LOW)
        assert low.name == "Low"
        assert len(low.assumptions) > 0
        # Low scenario should mention coal extension or faster BESS
        assumptions_text = " ".join(low.assumptions).lower()
        assert "coal" in assumptions_text or "faster" in assumptions_text

    def test_scenario_types_are_distinct(self):
        """All three scenarios have distinct ScenarioType values."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        scenarios = engine.get_scenarios()
        types = [s.scenario for s in scenarios]
        assert len(set(types)) == 3
        assert ScenarioType.CENTRAL in types
        assert ScenarioType.HIGH in types
        assert ScenarioType.LOW in types


# ---------------------------------------------------------------------------
# Region Coverage Tests
# ---------------------------------------------------------------------------


class TestRegionCoverage:
    """Test that all 6 regions are supported."""

    def test_all_six_regions_supported(self):
        """SUPPORTED_REGIONS contains all 6 NEM + WEM regions."""
        expected_regions = {"NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"}
        assert set(SUPPORTED_REGIONS) == expected_regions

    def test_base_spread_params_for_all_regions(self):
        """BASE_SPREAD_PARAMS has entries for all 6 regions."""
        for region in ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"]:
            assert region in BASE_SPREAD_PARAMS
            params = BASE_SPREAD_PARAMS[region]
            assert "mean_spread" in params
            assert "std_dev" in params
            assert "spike_frequency" in params

    def test_price_distribution_for_all_regions(self):
        """calculate_price_distribution works for all 6 regions."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        target_year = date.today().year + 5

        for region in SUPPORTED_REGIONS:
            dist = engine.calculate_price_distribution(
                region=region,
                scenario=ScenarioType.CENTRAL,
                year=target_year,
                bess_capacity_ratio=0.1,
            )
            assert dist.region == region
            assert dist.mean_spread > 0

    def test_invalid_region_raises_error(self):
        """Invalid region raises ValueError."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()

        with pytest.raises(ValueError, match="not supported"):
            engine.calculate_price_distribution(
                region="INVALID",
                scenario=ScenarioType.CENTRAL,
                year=2030,
                bess_capacity_ratio=0.1,
            )


# ---------------------------------------------------------------------------
# Data File Loading Tests
# ---------------------------------------------------------------------------


class TestDataFileLoading:
    """Test data file loading and missing file error handling."""

    def test_missing_coal_retirement_file_raises_error(self):
        """Missing coal_retirement_schedule.json raises FileNotFoundError."""
        with patch(
            "engines.forward_price_engine.DATA_DIR",
            Path(tempfile.mkdtemp()),
        ):
            # Create only capacity_data.json (not coal file)
            tmp_dir = Path(tempfile.mkdtemp())
            with patch("engines.forward_price_engine.DATA_DIR", tmp_dir):
                with pytest.raises(FileNotFoundError, match="coal_retirement_schedule"):
                    ForwardPriceEngine()

    def test_missing_capacity_data_file_raises_error(self):
        """Missing capacity_data.json raises FileNotFoundError."""
        tmp_dir = Path(tempfile.mkdtemp())
        # Create coal file but not capacity file
        coal_data = {
            "metadata": {"last_updated": str(date.today())},
            "retirements": [],
        }
        coal_path = tmp_dir / "coal_retirement_schedule.json"
        with open(coal_path, "w") as f:
            json.dump(coal_data, f)

        with patch("engines.forward_price_engine.DATA_DIR", tmp_dir):
            with pytest.raises(FileNotFoundError, match="capacity_data"):
                ForwardPriceEngine()

    def test_loads_successfully_with_valid_data_files(self):
        """Engine loads successfully when both data files exist with valid data."""
        tmp_dir = Path(tempfile.mkdtemp())

        coal_data = {
            "metadata": {"last_updated": str(date.today())},
            "retirements": [
                {
                    "plant_name": "Test Coal Plant",
                    "region": "NSW1",
                    "expected_closure_date": str(date.today() + timedelta(days=365 * 3)),
                    "capacity_mw": 1000.0,
                    "volatility_impact_estimate": 0.1,
                    "confidence": "confirmed",
                }
            ],
        }
        capacity_data = {
            "projects": [
                {
                    "project_name": "Test BESS",
                    "region": "NSW1",
                    "expected_commissioning_date": str(date.today() + timedelta(days=365 * 2)),
                    "capacity_mw": 200.0,
                    "status": "committed",
                }
            ],
        }

        with open(tmp_dir / "coal_retirement_schedule.json", "w") as f:
            json.dump(coal_data, f)
        with open(tmp_dir / "capacity_data.json", "w") as f:
            json.dump(capacity_data, f)

        with patch("engines.forward_price_engine.DATA_DIR", tmp_dir):
            engine = ForwardPriceEngine()
            assert len(engine.event_registry.events) >= 1


# ---------------------------------------------------------------------------
# Past-Date Event Exclusion Tests
# ---------------------------------------------------------------------------


class TestPastDateEventExclusion:
    """Test past-date event exclusion with warning."""

    def test_past_date_coal_event_excluded(self, caplog):
        """Coal retirement events with past dates are excluded and logged."""
        tmp_dir = Path(tempfile.mkdtemp())

        past_date = str(date.today() - timedelta(days=365))
        future_date = str(date.today() + timedelta(days=365 * 3))

        coal_data = {
            "metadata": {"last_updated": str(date.today())},
            "retirements": [
                {
                    "plant_name": "Past Coal Plant",
                    "region": "NSW1",
                    "expected_closure_date": past_date,
                    "capacity_mw": 500.0,
                    "volatility_impact_estimate": 0.15,
                    "confidence": "confirmed",
                },
                {
                    "plant_name": "Future Coal Plant",
                    "region": "NSW1",
                    "expected_closure_date": future_date,
                    "capacity_mw": 800.0,
                    "volatility_impact_estimate": 0.2,
                    "confidence": "announced",
                },
            ],
        }
        capacity_data = {"projects": []}

        with open(tmp_dir / "coal_retirement_schedule.json", "w") as f:
            json.dump(coal_data, f)
        with open(tmp_dir / "capacity_data.json", "w") as f:
            json.dump(capacity_data, f)

        with patch("engines.forward_price_engine.DATA_DIR", tmp_dir):
            with caplog.at_level(logging.WARNING):
                engine = ForwardPriceEngine()

        # Only future event should be in registry
        coal_events = [
            e for e in engine.event_registry.events
            if e.event_type == EventType.COAL_CLOSURE
        ]
        assert len(coal_events) == 1
        assert coal_events[0].name == "Future Coal Plant"

        # Warning should have been logged for past event
        assert "Past Coal Plant" in caplog.text
        assert "past date" in caplog.text.lower() or "excluding" in caplog.text.lower()

    def test_past_date_bess_event_excluded(self, caplog):
        """BESS commissioning events with past dates are excluded and logged."""
        tmp_dir = Path(tempfile.mkdtemp())

        past_date = str(date.today() - timedelta(days=100))
        future_date = str(date.today() + timedelta(days=365 * 2))

        coal_data = {
            "metadata": {"last_updated": str(date.today())},
            "retirements": [],
        }
        capacity_data = {
            "projects": [
                {
                    "project_name": "Past BESS",
                    "region": "SA1",
                    "expected_commissioning_date": past_date,
                    "capacity_mw": 100.0,
                    "status": "registered",
                },
                {
                    "project_name": "Future BESS",
                    "region": "SA1",
                    "expected_commissioning_date": future_date,
                    "capacity_mw": 300.0,
                    "status": "committed",
                },
            ],
        }

        with open(tmp_dir / "coal_retirement_schedule.json", "w") as f:
            json.dump(coal_data, f)
        with open(tmp_dir / "capacity_data.json", "w") as f:
            json.dump(capacity_data, f)

        with patch("engines.forward_price_engine.DATA_DIR", tmp_dir):
            with caplog.at_level(logging.WARNING):
                engine = ForwardPriceEngine()

        # Only future BESS event should be in registry
        bess_events = [
            e for e in engine.event_registry.events
            if e.event_type == EventType.BESS_COMMISSIONING
        ]
        assert len(bess_events) == 1
        assert bess_events[0].name == "Future BESS"

        # Warning should have been logged
        assert "Past BESS" in caplog.text


# ---------------------------------------------------------------------------
# Dynamic Peak Demand Tests (Req 5)
# ---------------------------------------------------------------------------


class TestDynamicPeakDemand:
    """Test _get_dynamic_peak_demand method."""

    def _make_engine(self):
        """Create engine without full initialization."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()
        engine._calibrated_spreads = {}
        return engine

    def test_base_year_returns_static_value(self):
        """At base year 2025, dynamic demand equals static PEAK_DEMAND."""
        engine = self._make_engine()
        from engines.forward_price_engine import PEAK_DEMAND

        for region, base_demand in PEAK_DEMAND.items():
            result = engine._get_dynamic_peak_demand(region, 2025)
            assert result == base_demand

    def test_growth_formula_correct(self):
        """Dynamic demand follows compound growth formula."""
        engine = self._make_engine()
        from engines.forward_price_engine import PEAK_DEMAND

        region = "NSW1"
        base = PEAK_DEMAND[region]
        rate = 0.025
        year = 2030
        expected = base * ((1.0 + rate) ** (year - 2025))
        result = engine._get_dynamic_peak_demand(region, year, rate)
        assert abs(result - expected) < 0.01

    def test_not_below_static_value(self):
        """Dynamic demand never goes below static PEAK_DEMAND (even for year < 2025)."""
        engine = self._make_engine()
        from engines.forward_price_engine import PEAK_DEMAND

        region = "SA1"
        base = PEAK_DEMAND[region]
        # Year before base year would produce value < base without the floor
        result = engine._get_dynamic_peak_demand(region, 2020, 0.025)
        assert result >= base

    def test_invalid_growth_rate_uses_default(self):
        """Growth rate outside [0.0, 0.10] falls back to default 0.025."""
        engine = self._make_engine()
        from engines.forward_price_engine import PEAK_DEMAND, DEMAND_GROWTH_RATE, REGIONAL_DEMAND_GROWTH_RATE

        region = "QLD1"
        base = PEAK_DEMAND[region]
        year = 2035

        # Negative rate → use default → then use regional rate for QLD1
        result_neg = engine._get_dynamic_peak_demand(region, year, -0.01)
        regional_rate = REGIONAL_DEMAND_GROWTH_RATE.get(region, DEMAND_GROWTH_RATE)
        expected_default = base * ((1.0 + regional_rate) ** (year - 2025))
        assert abs(result_neg - expected_default) < 0.01

        # Rate > 0.10 → use default → then use regional rate for QLD1
        result_high = engine._get_dynamic_peak_demand(region, year, 0.15)
        assert abs(result_high - expected_default) < 0.01

    def test_zero_growth_rate_valid(self):
        """Growth rate of 0.0 is valid and returns static value."""
        engine = self._make_engine()
        from engines.forward_price_engine import PEAK_DEMAND

        region = "VIC1"
        base = PEAK_DEMAND[region]
        result = engine._get_dynamic_peak_demand(region, 2040, 0.0)
        assert result == base

    def test_max_growth_rate_valid(self):
        """Growth rate of 0.10 is valid (boundary)."""
        engine = self._make_engine()
        from engines.forward_price_engine import PEAK_DEMAND

        region = "TAS1"
        base = PEAK_DEMAND[region]
        year = 2030
        expected = base * ((1.0 + 0.10) ** (year - 2025))
        result = engine._get_dynamic_peak_demand(region, year, 0.10)
        assert abs(result - expected) < 0.01

    def test_monotonically_increasing_with_year(self):
        """Dynamic demand increases with year for positive growth rate."""
        engine = self._make_engine()
        prev = 0.0
        for year in range(2025, 2050):
            result = engine._get_dynamic_peak_demand("NSW1", year, 0.03)
            assert result >= prev
            prev = result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _empty_registry():
    """Create an empty EventRegistry for isolated tests."""
    from models.forward_price_models import EventRegistry

    return EventRegistry(events=[], last_updated=date.today())


# ---------------------------------------------------------------------------
# Duration Efficiency Tests (Req 7)
# ---------------------------------------------------------------------------


class TestComputeDurationEfficiency:
    """Tests for _compute_duration_efficiency method."""

    def _make_engine(self):
        """Create engine instance without full initialization."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()
        engine._calibrated_spreads = {}
        return engine

    def test_duration_2h(self):
        """2h BESS: factor = 2^0.85 ≈ 1.81 (Req 7.4)."""
        engine = self._make_engine()
        result = engine._compute_duration_efficiency(2.0)
        assert abs(result - 2.0 ** 0.85) < 1e-10

    def test_duration_4h(self):
        """4h BESS: factor = 4^0.85 ≈ 3.28 (Req 7.4)."""
        engine = self._make_engine()
        result = engine._compute_duration_efficiency(4.0)
        assert abs(result - 4.0 ** 0.85) < 1e-10

    def test_duration_8h(self):
        """8h BESS: factor = 8^0.85 ≈ 5.93 (Req 7.4)."""
        engine = self._make_engine()
        result = engine._compute_duration_efficiency(8.0)
        assert abs(result - 8.0 ** 0.85) < 1e-10

    def test_duration_12h_boundary(self):
        """12h is the boundary: factor = 12^0.85 (Req 7.1)."""
        engine = self._make_engine()
        result = engine._compute_duration_efficiency(12.0)
        assert abs(result - 12.0 ** 0.85) < 1e-10

    def test_duration_above_12h(self):
        """Duration > 12h uses reduced gamma: 12^0.85 × (d/12)^0.75 (Req 7.5)."""
        engine = self._make_engine()
        result = engine._compute_duration_efficiency(24.0)
        expected = (12.0 ** 0.85) * ((24.0 / 12.0) ** 0.75)
        assert abs(result - expected) < 1e-10

    def test_duration_zero_raises_valueerror(self):
        """duration_hours = 0 raises ValueError."""
        engine = self._make_engine()
        with pytest.raises(ValueError, match="must be greater than 0"):
            engine._compute_duration_efficiency(0.0)

    def test_duration_negative_raises_valueerror(self):
        """duration_hours < 0 raises ValueError."""
        engine = self._make_engine()
        with pytest.raises(ValueError, match="must be greater than 0"):
            engine._compute_duration_efficiency(-1.0)

    def test_monotonically_increasing(self):
        """Factor is monotonically increasing across the boundary (Req 7.3)."""
        engine = self._make_engine()
        durations = [0.5, 1.0, 2.0, 4.0, 8.0, 12.0, 16.0, 24.0]
        factors = [engine._compute_duration_efficiency(d) for d in durations]
        for i in range(len(factors) - 1):
            assert factors[i] < factors[i + 1], (
                f"Not monotonically increasing: f({durations[i]})={factors[i]} "
                f">= f({durations[i+1]})={factors[i+1]}"
            )

    def test_continuity_at_12h(self):
        """Factor is continuous at the 12h boundary."""
        engine = self._make_engine()
        # Approach from below
        below = engine._compute_duration_efficiency(12.0)
        # Approach from above (just above 12)
        above = engine._compute_duration_efficiency(12.0 + 1e-10)
        # Should be essentially equal (continuous)
        assert abs(below - above) < 1e-6


class TestApplyPipelineRealization:
    """Test _apply_pipeline_realization method (Req 4)."""

    def _make_engine(self):
        """Create engine without full initialization."""
        engine = ForwardPriceEngine.__new__(ForwardPriceEngine)
        engine.event_registry = _empty_registry()
        engine._calibrated_spreads = {}
        return engine

    def test_registered_status(self):
        """Registered projects get 100% realization rate."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(100.0, "registered")
        assert result == 100.0

    def test_construction_status(self):
        """Construction projects get 95% realization rate."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(100.0, "construction")
        assert result == 95.0

    def test_committed_status(self):
        """Committed projects get 90% realization rate."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(100.0, "committed")
        assert result == 90.0

    def test_proposed_status(self):
        """Proposed projects get 50% realization rate."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(100.0, "proposed")
        assert result == 50.0

    def test_speculated_status(self):
        """Speculated projects get 20% realization rate."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(100.0, "speculated")
        assert result == 20.0

    def test_unknown_status_uses_default(self, caplog):
        """Unknown status uses 20% default realization rate and logs warning."""
        engine = self._make_engine()
        import logging

        with caplog.at_level(logging.WARNING):
            result = engine._apply_pipeline_realization(100.0, "unknown_status")
        assert result == 20.0
        assert "Unknown project status" in caplog.text
        assert "unknown_status" in caplog.text

    def test_empty_status_uses_default(self, caplog):
        """Empty string status uses 20% default realization rate."""
        engine = self._make_engine()
        import logging

        with caplog.at_level(logging.WARNING):
            result = engine._apply_pipeline_realization(200.0, "")
        assert result == 40.0  # 200 * 0.20

    def test_zero_capacity(self):
        """Zero capacity returns zero regardless of status."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(0.0, "registered")
        assert result == 0.0

    def test_large_capacity(self):
        """Large capacity values are handled correctly."""
        engine = self._make_engine()
        result = engine._apply_pipeline_realization(5000.0, "proposed")
        assert result == 2500.0
