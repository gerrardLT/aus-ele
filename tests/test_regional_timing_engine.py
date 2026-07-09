"""
Unit tests for RegionalTimingEngine.

Tests the core scoring logic, dimension calculations, and graceful degradation.
Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7, 3.8
"""

from __future__ import annotations

import json
import tempfile
import os
import sys
from datetime import date, datetime
from pathlib import Path
from unittest import mock

import pytest

pytestmark = pytest.mark.xfail(reason="SQLite removed; needs PG test fixtures", run=False)

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import DatabaseManager
from models.capacity_models import CapacityDataLoader
from models.outlook_models import CoalRetirement, CoalRetirementSchedule
from engines.regional_timing_engine import RegionalTimingEngine, NEM_REGIONS


@pytest.fixture
def tmp_db(tmp_path):
    """Create a temporary SQLite database with price data."""
    db_path = str(tmp_path / "test.db")
    db = DatabaseManager(db_path=db_path)

    year = datetime.now().year
    table_name = f"trading_price_{year}"

    with db.get_connection() as conn:
        conn.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL
            )
        """)

        # Insert sample price data for each region
        rows = []
        for region in NEM_REGIONS:
            for day in range(1, 31):
                for hour in range(24):
                    ts = f"{year}-01-{day:02d} {hour:02d}:00:00"
                    # SA1 has more negative prices (higher renewable penetration)
                    if region == "SA1" and hour >= 10 and hour <= 14:
                        price = -20.0
                    elif region == "VIC1" and hour == 12:
                        price = -5.0
                    else:
                        price = 50.0 + hour * 5.0 - (10.0 if hour < 6 else 0.0)
                    rows.append((ts, region, price))

        conn.executemany(
            f"INSERT INTO {table_name} (settlement_date, region_id, rrp_aud_mwh) VALUES (?, ?, ?)",
            rows,
        )
        conn.commit()

    return db


@pytest.fixture
def capacity_data_file(tmp_path):
    """Create a temporary capacity_data.json."""
    data = {
        "metadata": {
            "last_updated": "2025-06-15T10:30:00+10:00",
            "source": "Test",
            "version": 1,
        },
        "projects": [
            {
                "region": "NSW1",
                "project_name": "Test Battery NSW",
                "capacity_mw": 200,
                "duration_hours": 2,
                "status": "registered",
                "expected_commissioning_date": "2023-01-01",
            },
            {
                "region": "NSW1",
                "project_name": "Pipeline NSW 1",
                "capacity_mw": 500,
                "duration_hours": 4,
                "status": "committed",
                "expected_commissioning_date": f"{datetime.now().year + 1}-06-01",
            },
            {
                "region": "SA1",
                "project_name": "Hornsdale",
                "capacity_mw": 150,
                "duration_hours": 1.3,
                "status": "registered",
                "expected_commissioning_date": "2020-09-01",
            },
            {
                "region": "VIC1",
                "project_name": "VBB",
                "capacity_mw": 300,
                "duration_hours": 2,
                "status": "registered",
                "expected_commissioning_date": "2021-12-01",
            },
            {
                "region": "VIC1",
                "project_name": "Pipeline VIC 1",
                "capacity_mw": 400,
                "duration_hours": 4,
                "status": "construction",
                "expected_commissioning_date": f"{datetime.now().year + 2}-01-01",
            },
            {
                "region": "QLD1",
                "project_name": "QLD Battery",
                "capacity_mw": 100,
                "duration_hours": 2,
                "status": "registered",
                "expected_commissioning_date": "2022-06-01",
            },
            {
                "region": "TAS1",
                "project_name": "TAS Battery",
                "capacity_mw": 50,
                "duration_hours": 2,
                "status": "registered",
                "expected_commissioning_date": "2023-01-01",
            },
        ],
    }
    path = tmp_path / "capacity_data.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return path


@pytest.fixture
def coal_schedule():
    """Create a test coal retirement schedule."""
    return CoalRetirementSchedule(
        metadata={"last_updated": "2025-01-15", "source": "Test"},
        retirements=[
            CoalRetirement(
                plant_name="Eraring",
                region="NSW1",
                capacity_mw=2880,
                fuel_type="black_coal",
                expected_closure_date=date(2027, 8, 1),
                confidence="confirmed",
                volatility_impact_estimate=0.40,
            ),
            CoalRetirement(
                plant_name="Yallourn",
                region="VIC1",
                capacity_mw=1480,
                fuel_type="brown_coal",
                expected_closure_date=date(2028, 6, 30),
                confidence="confirmed",
                volatility_impact_estimate=0.35,
            ),
            CoalRetirement(
                plant_name="Callide B",
                region="QLD1",
                capacity_mw=700,
                fuel_type="black_coal",
                expected_closure_date=date(2028, 12, 31),
                confidence="announced",
                volatility_impact_estimate=0.20,
            ),
        ],
    )


@pytest.fixture
def engine(tmp_db, capacity_data_file, coal_schedule):
    """Create a RegionalTimingEngine with test dependencies."""
    loader = CapacityDataLoader(
        data_path=capacity_data_file,
        backup_path=capacity_data_file,
    )
    return RegionalTimingEngine(
        db=tmp_db,
        capacity_loader=loader,
        coal_schedule=coal_schedule,
    )


class TestRegionalTimingEngine:
    """Tests for RegionalTimingEngine core functionality."""

    def test_score_regions_returns_all_nem_regions(self, engine):
        """All 5 NEM regions should be scored."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)

        assert len(result.rankings) == 5
        regions_in_result = {r.region for r in result.rankings}
        assert regions_in_result == set(NEM_REGIONS)

    def test_rankings_are_sorted_descending(self, engine):
        """Rankings should be sorted by total_score descending."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)

        scores = [r.total_score for r in result.rankings]
        assert scores == sorted(scores, reverse=True)

    def test_ranks_are_sequential(self, engine):
        """Rank values should be 1, 2, 3, 4, 5."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)

        ranks = [r.rank for r in result.rankings]
        assert ranks == [1, 2, 3, 4, 5]

    def test_dimensions_all_present_and_valid(self, engine):
        """Each region should have 4 dimension scores in [0, 1]."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)

        expected_dims = {"coal_retirement", "pipeline_growth", "renewable_penetration", "revenue_trajectory"}

        for ranking in result.rankings:
            assert set(ranking.dimensions.keys()) == expected_dims
            for dim, score in ranking.dimensions.items():
                assert 0.0 <= score <= 1.0, (
                    f"{ranking.region} {dim} = {score} out of range"
                )

    def test_coal_data_available_flag(self, engine):
        """coal_data_available should be True when schedule is provided."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)
        assert result.coal_data_available is True

    def test_degraded_mode_without_coal_data(self, tmp_db, capacity_data_file):
        """Engine should work without coal schedule (degraded mode)."""
        loader = CapacityDataLoader(
            data_path=capacity_data_file,
            backup_path=capacity_data_file,
        )
        engine = RegionalTimingEngine(
            db=tmp_db,
            capacity_loader=loader,
            coal_schedule=None,
        )

        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)

        assert result.coal_data_available is False
        assert len(result.rankings) == 5

        # All coal_retirement scores should be 0
        for ranking in result.rankings:
            assert ranking.dimensions["coal_retirement"] == 0.0

    def test_metadata_fields(self, engine):
        """Response metadata should contain required fields."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)

        assert result.metadata["market"] == "NEM"
        assert result.metadata["currency"] == "AUD"
        assert "methodology_version" in result.metadata
        assert "timezone" in result.metadata

    def test_target_year_clamping(self, engine):
        """Target year should be clamped to valid range."""
        current_year = datetime.now().year

        # Too far in the past
        result = engine.score_regions(target_year=2020)
        assert result.target_year == current_year

        # Too far in the future
        result = engine.score_regions(target_year=current_year + 10)
        assert result.target_year == current_year + 5

    def test_conclusion_not_empty(self, engine):
        """Conclusion should be a non-empty string."""
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year)
        assert len(result.conclusion) > 0

    def test_weights_used_in_response(self, engine):
        """Custom weights should be reflected in the response."""
        custom_weights = {
            "coal_retirement": 0.5,
            "pipeline_growth": 0.2,
            "renewable_penetration": 0.1,
            "revenue_trajectory": 0.2,
        }
        target_year = datetime.now().year + 2
        result = engine.score_regions(target_year=target_year, weights=custom_weights)

        assert result.weights_used["coal_retirement"] == 0.5


class TestCoalRetirementImpact:
    """Tests for estimate_coal_retirement_impact method."""

    def test_nsw_has_high_coal_impact(self, engine):
        """NSW should have high coal retirement impact (Eraring 2880MW)."""
        score = engine.estimate_coal_retirement_impact("NSW1", datetime.now().year + 3)
        assert score > 0.3  # Eraring alone: 2880 * 0.4 = 1152 / 2000 = 0.576

    def test_tas_has_zero_coal_impact(self, engine):
        """TAS has no coal plants, should score 0."""
        score = engine.estimate_coal_retirement_impact("TAS1", datetime.now().year + 3)
        assert score == 0.0

    def test_score_bounded_0_to_1(self, engine):
        """Coal impact score should always be in [0, 1]."""
        for region in NEM_REGIONS:
            score = engine.estimate_coal_retirement_impact(region, 2035)
            assert 0.0 <= score <= 1.0


class TestPipelineGrowth:
    """Tests for project_pipeline_growth method."""

    def test_nsw_has_pipeline_growth(self, engine):
        """NSW with 500MW pipeline on 200MW base should show growth."""
        rate = engine.project_pipeline_growth("NSW1", years_forward=3)
        assert rate > 0.0

    def test_tas_has_low_growth(self, engine):
        """TAS with no pipeline projects should have low growth."""
        rate = engine.project_pipeline_growth("TAS1", years_forward=3)
        assert rate >= 0.0

    def test_growth_rate_non_negative(self, engine):
        """Growth rate should never be negative."""
        for region in NEM_REGIONS:
            rate = engine.project_pipeline_growth(region, years_forward=3)
            assert rate >= 0.0
