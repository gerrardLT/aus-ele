"""Property-based tests for aggregation API endpoints.

Feature: information-architecture-redesign

Uses Hypothesis to verify structural correctness properties of the
market-summary and stage-summary aggregation endpoints.

Tests:
- Property 7: Market-summary API response contract
- Property 4: Stage conclusion response structure
- Property 8: Partial results graceful degradation
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from tests.support import stub_optional_dep

# Stub heavy optional dependencies that may not be installed in test env
stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.aggregation_routes import (
    DataUnavailableError,
    KpiMetric,
    StageSummaryData,
    router,
)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_STAGES = [
    "market-opportunity",
    "opportunity-identification",
    "revenue-estimation",
    "investment-decision",
]

STAGE_REGISTRY_KEYS = [
    "market_opportunity",
    "opportunity_identification",
    "revenue_estimation",
    "investment_decision",
]

REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app() -> FastAPI:
    """Create a FastAPI app with the aggregation router."""
    app = FastAPI()
    app.include_router(router)
    return app


_APP = _make_app()


def _mock_stage_data() -> StageSummaryData:
    """Create a valid StageSummaryData with 3 KPIs for testing."""
    return StageSummaryData(
        summary_text="测试阶段摘要：市场存在显著套利机会",
        sentiment="positive",
        kpis=[
            KpiMetric(label="平均日价差", value=45.2, unit="$/MWh", sentiment="positive"),
            KpiMetric(label="最大日价差", value=312.5, unit="$/MWh", sentiment="positive"),
            KpiMetric(label="负电价占比", value=8.3, unit="%", sentiment="neutral"),
        ],
    )


def _mock_cache():
    """Create a mock cache that always misses."""
    cache = MagicMock()
    cache.get_json.return_value = None
    cache.set_json.return_value = None
    return cache


# ---------------------------------------------------------------------------
# Property 7: Market-summary API response contract
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    market=st.sampled_from(["NEM", "WEM"]),
    region=st.sampled_from(REGIONS),
    year=st.integers(min_value=2020, max_value=2026),
    bess_power_mw=st.floats(min_value=50.0, max_value=500.0, allow_nan=False, allow_infinity=False),
    bess_duration_hours=st.floats(min_value=1.0, max_value=8.0, allow_nan=False, allow_infinity=False),
    bess_efficiency=st.floats(min_value=0.7, max_value=0.95, allow_nan=False, allow_infinity=False),
)
def test_property_7_market_summary_response_contract(
    market, region, year, bess_power_mw, bess_duration_hours, bess_efficiency,
):
    """Feature: information-architecture-redesign, Property 7: Market-summary API response contract

    For any valid combination of market, region, year, and bess_params, the
    /api/market-summary/{market}/{region} endpoint returns a response containing
    all required fields: stages dict with 4 keys, overall_rating, metadata with
    standard contract fields, bess_params, market, region, and year.

    **Validates: Requirements 6.3, 6.4**
    """
    mock_cache = _mock_cache()

    # Mock STAGE_COMPUTERS to return valid data for all stages
    mock_computers = MagicMock()
    mock_computers.items.return_value = [
        (key, lambda m, r, y, p, _key=key: _mock_stage_data())
        for key in STAGE_REGISTRY_KEYS
    ]

    with patch("routes.aggregation_routes.get_cache", return_value=mock_cache), \
         patch("routes.aggregation_routes.STAGE_COMPUTERS", mock_computers):
        client = TestClient(_APP)
        response = client.get(
            f"/api/market-summary/{market}/{region}",
            params={
                "year": year,
                "bess_power_mw": bess_power_mw,
                "bess_duration_hours": bess_duration_hours,
                "bess_efficiency": bess_efficiency,
            },
        )

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )

    data = response.json()

    # Top-level required fields
    assert data["market"] == market.upper()
    assert data["region"] == region
    assert data["year"] == year

    # bess_params object
    assert "bess_params" in data
    bess = data["bess_params"]
    assert "power_mw" in bess
    assert "duration_hours" in bess
    assert "round_trip_efficiency" in bess
    assert bess["power_mw"] == pytest.approx(bess_power_mw, rel=1e-4)
    assert bess["duration_hours"] == pytest.approx(bess_duration_hours, rel=1e-4)
    assert bess["round_trip_efficiency"] == pytest.approx(bess_efficiency, rel=1e-4)

    # stages dict with all 4 keys
    assert "stages" in data
    stages = data["stages"]
    assert isinstance(stages, dict)
    for key in STAGE_REGISTRY_KEYS:
        assert key in stages, f"Missing stage key: {key}"
        stage = stages[key]
        assert stage is not None, f"Stage {key} should not be None when mocked"
        assert "summary_text" in stage
        assert "sentiment" in stage
        assert "kpis" in stage
        assert stage["sentiment"] in ("positive", "negative", "neutral")

    # overall_rating
    assert "overall_rating" in data
    assert data["overall_rating"] in (
        "strong_opportunity",
        "moderate_opportunity",
        "weak_opportunity",
        "unfavorable",
    )

    # metadata with standard contract fields
    assert "metadata" in data
    metadata = data["metadata"]
    assert metadata["market"] == market.upper()
    assert metadata["region_or_zone"] == region
    assert "timezone" in metadata
    assert "currency" in metadata
    assert metadata["currency"] == "AUD"
    assert "data_grade" in metadata
    assert "freshness" in metadata
    assert "source_version" in metadata

    # warnings is a list (may be empty when all stages succeed)
    assert "warnings" in data
    assert isinstance(data["warnings"], list)


# ---------------------------------------------------------------------------
# Property 4: Stage conclusion response structure
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    stage_id=st.sampled_from(VALID_STAGES),
    region=st.sampled_from(REGIONS),
)
def test_property_4_stage_conclusion_response_structure(stage_id, region):
    """Feature: information-architecture-redesign, Property 4: Stage conclusion response structure

    For any valid stage-summary API response, the response contains a non-empty
    summary_text string and a kpis array with length between 2 and 4 inclusive,
    where each KPI object contains label, value, unit, and sentiment fields.

    **Validates: Requirements 3.2, 3.3**
    """
    mock_cache = _mock_cache()

    # Mock STAGE_COMPUTERS.get to return a compute function
    mock_computers = MagicMock()
    mock_computers.get.return_value = lambda m, r, y, p: _mock_stage_data()

    with patch("routes.aggregation_routes.get_cache", return_value=mock_cache), \
         patch("routes.aggregation_routes.STAGE_COMPUTERS", mock_computers):
        client = TestClient(_APP)
        response = client.get(f"/api/stage-summary/NEM/{region}/{stage_id}")

    assert response.status_code == 200, (
        f"Expected 200, got {response.status_code}: {response.text[:200]}"
    )

    data = response.json()

    # summary_text must be non-empty
    assert "summary_text" in data
    assert isinstance(data["summary_text"], str)
    assert len(data["summary_text"]) > 0, "summary_text must be non-empty"

    # kpis array with 2-4 items
    assert "kpis" in data
    kpis = data["kpis"]
    assert isinstance(kpis, list)
    assert 2 <= len(kpis) <= 4, (
        f"kpis must have 2-4 items, got {len(kpis)}"
    )

    # Each KPI has required fields
    valid_sentiments = {"positive", "negative", "neutral", "warning"}
    for i, kpi in enumerate(kpis):
        assert "label" in kpi, f"KPI {i} missing 'label'"
        assert "value" in kpi, f"KPI {i} missing 'value'"
        assert "unit" in kpi, f"KPI {i} missing 'unit'"
        assert "sentiment" in kpi, f"KPI {i} missing 'sentiment'"
        assert kpi["sentiment"] in valid_sentiments, (
            f"KPI {i} sentiment '{kpi['sentiment']}' not in {valid_sentiments}"
        )

    # sentiment field at response level
    assert "sentiment" in data
    assert data["sentiment"] in ("positive", "negative", "neutral")


# ---------------------------------------------------------------------------
# Property 8: Partial results graceful degradation
# ---------------------------------------------------------------------------


@settings(
    max_examples=100,
    deadline=None,
    suppress_health_check=[HealthCheck.function_scoped_fixture],
)
@given(
    failing_stages=st.sets(
        st.sampled_from(STAGE_REGISTRY_KEYS),
        min_size=1,
        max_size=3,
    ),
)
def test_property_8_partial_results_graceful_degradation(failing_stages):
    """Feature: information-architecture-redesign, Property 8: Partial results graceful degradation

    When one or more underlying data sources are unavailable, the market-summary
    API returns HTTP 200 with partial results for available stages and a non-empty
    warnings array identifying the unavailable metrics.

    **Validates: Requirements 6.5**
    """
    mock_cache = _mock_cache()

    # Build stage computers: some succeed, some raise DataUnavailableError
    def _make_compute_fn(stage_key):
        if stage_key in failing_stages:
            def _fail(market, region, year, params):
                raise DataUnavailableError(
                    f"No data available for {stage_key}",
                    metric_name=f"{stage_key}_metric",
                )
            return _fail
        else:
            return lambda m, r, y, p: _mock_stage_data()

    mock_computers = MagicMock()
    mock_computers.items.return_value = [
        (key, _make_compute_fn(key))
        for key in STAGE_REGISTRY_KEYS
    ]

    with patch("routes.aggregation_routes.get_cache", return_value=mock_cache), \
         patch("routes.aggregation_routes.STAGE_COMPUTERS", mock_computers):
        client = TestClient(_APP)
        response = client.get(
            "/api/market-summary/NEM/NSW1",
            params={"year": 2024},
        )

    # Must return HTTP 200 even with failures
    assert response.status_code == 200, (
        f"Expected 200 with partial results, got {response.status_code}: "
        f"{response.text[:200]}"
    )

    data = response.json()

    # warnings must be non-empty when stages fail
    assert "warnings" in data
    warnings = data["warnings"]
    assert isinstance(warnings, list)
    assert len(warnings) > 0, (
        f"Expected non-empty warnings for failing stages {failing_stages}"
    )

    # Each warning identifies the stage and reason
    for warning in warnings:
        assert "stage" in warning
        assert "reason" in warning
        assert "severity" in warning
        assert warning["severity"] in ("degraded", "error")

    # Failed stages should be None in the response
    stages = data["stages"]
    for stage_key in failing_stages:
        assert stages[stage_key] is None, (
            f"Failed stage '{stage_key}' should be None, got {stages[stage_key]}"
        )

    # Successful stages should have data
    successful_stages = set(STAGE_REGISTRY_KEYS) - failing_stages
    for stage_key in successful_stages:
        assert stages[stage_key] is not None, (
            f"Successful stage '{stage_key}' should not be None"
        )

    # Response still has all required top-level fields
    assert "overall_rating" in data
    assert "metadata" in data
    assert "bess_params" in data
