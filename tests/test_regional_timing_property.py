"""
Property-based tests for RegionalTimingEngine.

Uses Hypothesis to verify universal correctness properties across
randomized valid inputs.

Requirements: 3.1, 3.2
"""

from __future__ import annotations

import json
import os
import sys
from datetime import date, datetime

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis.strategies import floats, integers, fixed_dictionaries

# Ensure backend is on path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from database import DatabaseManager
from models.capacity_models import CapacityDataLoader
from models.outlook_models import CoalRetirement, CoalRetirementSchedule
from engines.regional_timing_engine import RegionalTimingEngine, NEM_REGIONS


# ---------------------------------------------------------------------------
# Fixtures (reused from test_regional_timing_engine.py)
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Hypothesis Strategies
# ---------------------------------------------------------------------------

current_year = datetime.now().year

# target_year: current_year to current_year + 5
target_year_strategy = integers(min_value=current_year, max_value=current_year + 5)

# weights: each dimension weight is a float in [0, 1]
weights_strategy = fixed_dictionaries({
    "coal_retirement": floats(min_value=0.0, max_value=1.0),
    "pipeline_growth": floats(min_value=0.0, max_value=1.0),
    "renewable_penetration": floats(min_value=0.0, max_value=1.0),
    "revenue_trajectory": floats(min_value=0.0, max_value=1.0),
})


# ---------------------------------------------------------------------------
# Property 7: Regional scores have all dimensions in valid range
# Validates: Requirements 3.1
# ---------------------------------------------------------------------------


class TestProperty7RegionalDimensionsInRange:
    """Property 7: Regional scores have all dimensions in valid range.

    *For any* valid target_year and weight configuration, every region in the
    rankings output SHALL have exactly 4 dimension scores (coal_retirement,
    pipeline_growth, renewable_penetration, revenue_trajectory), each in the
    range [0.0, 1.0].

    **Validates: Requirements 3.1**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(target_year=target_year_strategy, weights=weights_strategy)
    def test_all_dimensions_present_and_in_valid_range(
        self, engine, target_year, weights
    ):
        """For any valid target_year and weights, all dimension scores are in [0, 1]."""
        result = engine.score_regions(target_year=target_year, weights=weights)

        expected_dims = {
            "coal_retirement",
            "pipeline_growth",
            "renewable_penetration",
            "revenue_trajectory",
        }

        # Must have exactly 5 NEM regions
        assert len(result.rankings) == 5

        for ranking in result.rankings:
            # Must have exactly 4 dimensions
            assert set(ranking.dimensions.keys()) == expected_dims, (
                f"Region {ranking.region} missing dimensions: "
                f"expected {expected_dims}, got {set(ranking.dimensions.keys())}"
            )

            # Each dimension score must be in [0.0, 1.0]
            for dim, score in ranking.dimensions.items():
                assert 0.0 <= score <= 1.0, (
                    f"Region {ranking.region}, dimension '{dim}' = {score} "
                    f"is outside valid range [0.0, 1.0] "
                    f"(target_year={target_year}, weights={weights})"
                )


# ---------------------------------------------------------------------------
# Property 8: Rankings are properly ordered
# Validates: Requirements 3.2
# ---------------------------------------------------------------------------


class TestProperty8RankingsProperlyOrdered:
    """Property 8: Rankings are properly ordered.

    *For any* valid RegionalTimingResponse, the rankings list SHALL be sorted
    by total_score in descending order, and rank values SHALL be sequential
    integers from 1 to N (where N is the number of regions).

    **Validates: Requirements 3.2**
    """

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(target_year=target_year_strategy, weights=weights_strategy)
    def test_rankings_sorted_by_total_score_descending(
        self, engine, target_year, weights
    ):
        """Rankings are sorted by total_score in descending order."""
        result = engine.score_regions(target_year=target_year, weights=weights)

        scores = [r.total_score for r in result.rankings]
        assert scores == sorted(scores, reverse=True), (
            f"Rankings not sorted descending: {scores} "
            f"(target_year={target_year}, weights={weights})"
        )

    @settings(max_examples=100, suppress_health_check=[HealthCheck.function_scoped_fixture])
    @given(target_year=target_year_strategy, weights=weights_strategy)
    def test_rank_values_are_sequential(self, engine, target_year, weights):
        """Rank values are sequential integers from 1 to N."""
        result = engine.score_regions(target_year=target_year, weights=weights)

        n = len(result.rankings)
        expected_ranks = list(range(1, n + 1))
        actual_ranks = [r.rank for r in result.rankings]

        assert actual_ranks == expected_ranks, (
            f"Ranks not sequential: expected {expected_ranks}, got {actual_ranks} "
            f"(target_year={target_year}, weights={weights})"
        )
