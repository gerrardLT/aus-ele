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
# Helpers
# ---------------------------------------------------------------------------


def _empty_registry():
    """Create an empty EventRegistry for isolated tests."""
    from models.forward_price_models import EventRegistry

    return EventRegistry(events=[], last_updated=date.today())
