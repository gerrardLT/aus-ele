"""Property-based tests for API contract backward compatibility.

Feature: platform-optimization, Property 10: API 契约向后兼容

Uses Hypothesis to verify that random valid API request parameters produce
responses with consistent structure (same HTTP status codes, same JSON field
sets). This ensures the route module split preserves the original API contract.

**Validates: Requirements 4.3**
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from tests.support import stub_optional_dep

# Stub heavy optional dependencies that may not be installed in test env
stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

import sqlite3
import tempfile
from contextlib import contextmanager
from unittest.mock import patch, MagicMock

import pytest
from hypothesis import given, settings, assume, HealthCheck, Phase
from hypothesis import strategies as st

from fastapi import FastAPI
from fastapi.testclient import TestClient
pytestmark = pytest.mark.xfail(reason="SQLite removed; needs PG test fixtures", run=False)


# ---------------------------------------------------------------------------
# Test database setup — lightweight in-memory SQLite with price data
# ---------------------------------------------------------------------------


def _create_test_db_path() -> str:
    """Create a temporary SQLite database with minimal price data for testing."""
    handle, db_path = tempfile.mkstemp(suffix=".db")
    os.close(handle)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create trading_price tables for years 2023 and 2024
    for year in (2023, 2024):
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS trading_price_{year} (
                settlement_date TEXT,
                region_id TEXT,
                rrp_aud_mwh REAL
            )
        """)
        # Insert sample data for multiple regions
        regions = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
        for region in regions:
            for month in range(1, 13):
                for day in range(1, 4):  # 3 days per month
                    for hour in range(0, 24, 6):  # 4 intervals per day
                        ts = f"{year}-{month:02d}-{day:02d}T{hour:02d}:00:00"
                        price = 50.0 + (hour * 2.5) + (month * 0.5)
                        cursor.execute(
                            f"INSERT INTO trading_price_{year} VALUES (?, ?, ?)",
                            (ts, region, price),
                        )

    # Create FCAS table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fcas_prices_2024 (
            settlement_date TEXT,
            region_id TEXT,
            raise1sec_rrp REAL,
            raise6sec_rrp REAL,
            raise60sec_rrp REAL,
            raise5min_rrp REAL,
            raisereg_rrp REAL,
            lower1sec_rrp REAL,
            lower6sec_rrp REAL,
            lower60sec_rrp REAL,
            lower5min_rrp REAL,
            lowerreg_rrp REAL
        )
    """)
    for region in ["NSW1", "QLD1", "VIC1", "SA1"]:
        for day in range(1, 4):
            for hour in range(0, 24, 6):
                ts = f"2024-01-{day:02d}T{hour:02d}:00:00"
                values = [ts, region] + [5.0 + hour * 0.5] * 10
                cursor.execute(
                    "INSERT INTO fcas_prices_2024 VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    values,
                )

    # Create system_status table for data version tracking
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS system_status (
            key TEXT PRIMARY KEY,
            value TEXT
        )
    """)
    cursor.execute(
        "INSERT INTO system_status VALUES ('last_update_time', '2024-01-15T10:00:00Z')"
    )

    conn.commit()
    conn.close()
    return db_path


# ---------------------------------------------------------------------------
# App factory with mocked DB
# ---------------------------------------------------------------------------


def _make_test_app(db_path: str) -> FastAPI:
    """Create a FastAPI app with routes registered, using a test database."""
    from database import DatabaseManager
    from routes import register_all_routes
    from routes.health import router as health_router

    db = DatabaseManager(db_path)

    app = FastAPI()
    app.include_router(health_router)

    with patch("deps.get_db", return_value=db), \
         patch("deps.get_cache") as mock_cache:
        # Mock cache to always miss (forces computation path)
        cache_instance = MagicMock()
        cache_instance.get_json.return_value = None
        cache_instance.set_json.return_value = None
        mock_cache.return_value = cache_instance

        register_all_routes(app)

    return app, db


# ---------------------------------------------------------------------------
# Module-level fixtures (shared across all property tests)
# ---------------------------------------------------------------------------

_TEST_DB_PATH = _create_test_db_path()
_APP, _DB = _make_test_app(_TEST_DB_PATH)


def _get_client() -> TestClient:
    """Get a TestClient with mocked deps for each request."""
    cache_instance = MagicMock()
    cache_instance.get_json.return_value = None
    cache_instance.set_json.return_value = None

    # Patch deps at request time
    with patch("deps.get_db", return_value=_DB), \
         patch("deps.get_cache", return_value=cache_instance):
        return TestClient(_APP)


# ---------------------------------------------------------------------------
# Hypothesis strategies for valid API parameters
# ---------------------------------------------------------------------------

# Valid regions in the system
region_strategy = st.sampled_from(["NSW1", "QLD1", "VIC1", "SA1", "TAS1"])

# Valid years that have data in our test DB
year_strategy = st.sampled_from([2023, 2024])

# Optional month filter
month_strategy = st.one_of(st.none(), st.sampled_from(["01", "03", "06", "09", "12"]))

# Optional quarter filter
quarter_strategy = st.one_of(st.none(), st.sampled_from(["Q1", "Q2", "Q3", "Q4"]))

# Optional day type filter
day_type_strategy = st.one_of(st.none(), st.sampled_from(["WEEKDAY", "WEEKEND"]))

# Battery parameters for revenue analysis
power_mw_strategy = st.floats(min_value=1.0, max_value=500.0, allow_nan=False, allow_infinity=False)
energy_mwh_strategy = st.floats(min_value=1.0, max_value=2000.0, allow_nan=False, allow_infinity=False)
efficiency_strategy = st.floats(min_value=0.5, max_value=0.99, allow_nan=False, allow_infinity=False)

# Limit parameter for price-trend
limit_strategy = st.one_of(st.none(), st.integers(min_value=10, max_value=5000))


# ---------------------------------------------------------------------------
# Expected response field sets (the contract)
# ---------------------------------------------------------------------------

PRICE_TREND_EXPECTED_FIELDS = {
    "region", "year", "month", "total_points", "returned_points",
    "stats", "advanced_stats", "hourly_distribution", "data", "metadata",
}

PEAK_ANALYSIS_EXPECTED_FIELDS = {
    "region", "year", "aggregation", "network_fee",
    "data", "summary", "metadata",
}

REVENUE_ANALYSIS_EXPECTED_FIELDS = {
    "region", "year", "total_revenue", "gross_revenue", "net_revenue",
    "costs", "summary", "metadata",
}

HEALTH_EXPECTED_FIELDS = {"status", "degraded_modules"}


# ---------------------------------------------------------------------------
# Property 10: API 契约向后兼容 — Price Trend endpoint
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    year=year_strategy,
    region=region_strategy,
    month=month_strategy,
    quarter=quarter_strategy,
    day_type=day_type_strategy,
    limit=limit_strategy,
)
def test_property_10_price_trend_contract_stability(
    year, region, month, quarter, day_type, limit,
):
    """Feature: platform-optimization, Property 10: API 契约向后兼容

    For any valid combination of price-trend API parameters, the response
    must return HTTP 200 with a consistent JSON field set matching the
    established contract.

    **Validates: Requirements 4.3**
    """
    # month and quarter are mutually exclusive in practice; pick one
    if month is not None and quarter is not None:
        quarter = None

    params = {"year": year, "region": region}
    if month is not None:
        params["month"] = month
    if quarter is not None:
        params["quarter"] = quarter
    if day_type is not None:
        params["day_type"] = day_type
    if limit is not None:
        params["limit"] = limit

    cache_mock = MagicMock()
    cache_mock.get_json.return_value = None
    cache_mock.set_json.return_value = None

    with patch("deps.get_db", return_value=_DB), \
         patch("deps.get_cache", return_value=cache_mock), \
         patch("routes.price_routes.get_cache", return_value=cache_mock), \
         patch("routes.price_routes.get_db", return_value=_DB):
        client = TestClient(_APP)
        response = client.get("/api/price-trend", params=params)

    assert response.status_code == 200, (
        f"Expected 200 for valid params {params}, got {response.status_code}: "
        f"{response.text[:200]}"
    )

    data = response.json()
    actual_fields = set(data.keys())

    # The response must contain all expected contract fields
    missing = PRICE_TREND_EXPECTED_FIELDS - actual_fields
    assert not missing, (
        f"Price-trend response missing contract fields: {missing}. "
        f"Params: {params}, actual fields: {actual_fields}"
    )

    # Verify field types are consistent
    assert isinstance(data["region"], str)
    assert isinstance(data["year"], int)
    assert isinstance(data["total_points"], int)
    assert isinstance(data["returned_points"], int)
    assert isinstance(data["stats"], dict)
    assert isinstance(data["advanced_stats"], dict)
    assert isinstance(data["hourly_distribution"], list)
    assert isinstance(data["data"], list)
    assert isinstance(data["metadata"], dict)

    # Stats sub-fields contract
    stats_fields = {"min", "max", "avg"}
    assert stats_fields.issubset(set(data["stats"].keys())), (
        f"Stats missing fields: {stats_fields - set(data['stats'].keys())}"
    )


# ---------------------------------------------------------------------------
# Property 10: API 契約向后兼容 — Peak Analysis endpoint
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    year=year_strategy,
    region=region_strategy,
    aggregation=st.sampled_from(["daily", "weekly", "monthly", "yearly"]),
    month=month_strategy,
    quarter=quarter_strategy,
    day_type=day_type_strategy,
)
def test_property_10_peak_analysis_contract_stability(
    year, region, aggregation, month, quarter, day_type,
):
    """Feature: platform-optimization, Property 10: API 契约向后兼容

    For any valid combination of peak-analysis API parameters, the response
    must return HTTP 200 with a consistent JSON field set.

    **Validates: Requirements 4.3**
    """
    if month is not None and quarter is not None:
        quarter = None

    params = {"year": year, "region": region, "aggregation": aggregation}
    if month is not None:
        params["month"] = month
    if quarter is not None:
        params["quarter"] = quarter
    if day_type is not None:
        params["day_type"] = day_type

    cache_mock = MagicMock()
    cache_mock.get_json.return_value = None
    cache_mock.set_json.return_value = None

    with patch("deps.get_db", return_value=_DB), \
         patch("deps.get_cache", return_value=cache_mock), \
         patch("routes.price_routes.get_cache", return_value=cache_mock), \
         patch("routes.price_routes.get_db", return_value=_DB):
        client = TestClient(_APP)
        response = client.get("/api/peak-analysis", params=params)

    assert response.status_code == 200, (
        f"Expected 200 for valid params {params}, got {response.status_code}: "
        f"{response.text[:200]}"
    )

    data = response.json()
    actual_fields = set(data.keys())

    # The response must contain all expected contract fields
    missing = PEAK_ANALYSIS_EXPECTED_FIELDS - actual_fields
    assert not missing, (
        f"Peak-analysis response missing contract fields: {missing}. "
        f"Params: {params}, actual fields: {actual_fields}"
    )

    # Verify field types
    assert isinstance(data["region"], str)
    assert isinstance(data["year"], int)
    assert isinstance(data["aggregation"], str)
    assert isinstance(data["network_fee"], (int, float))
    assert isinstance(data["data"], list)
    assert isinstance(data["summary"], dict)
    assert isinstance(data["metadata"], dict)


# ---------------------------------------------------------------------------
# Property 10: API 契约向后兼容 — Revenue Analysis endpoint
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(
    year=year_strategy,
    region=region_strategy,
    power_mw=power_mw_strategy,
    energy_mwh=energy_mwh_strategy,
    efficiency=efficiency_strategy,
    month=month_strategy,
    quarter=quarter_strategy,
    day_type=day_type_strategy,
)
def test_property_10_revenue_analysis_contract_stability(
    year, region, power_mw, energy_mwh, efficiency, month, quarter, day_type,
):
    """Feature: platform-optimization, Property 10: API 契约向后兼容

    For any valid combination of revenue-analysis API parameters, the response
    must return HTTP 200 with a consistent JSON field set.

    **Validates: Requirements 4.3**
    """
    if month is not None and quarter is not None:
        quarter = None

    params = {
        "year": year,
        "region": region,
        "power_mw": power_mw,
        "energy_mwh": energy_mwh,
        "efficiency": efficiency,
    }
    if month is not None:
        params["month"] = month
    if quarter is not None:
        params["quarter"] = quarter
    if day_type is not None:
        params["day_type"] = day_type

    cache_mock = MagicMock()
    cache_mock.get_json.return_value = None
    cache_mock.set_json.return_value = None

    with patch("deps.get_db", return_value=_DB), \
         patch("deps.get_cache", return_value=cache_mock), \
         patch("routes.revenue_routes.get_cache", return_value=cache_mock), \
         patch("routes.revenue_routes.get_db", return_value=_DB):
        client = TestClient(_APP)
        response = client.get("/api/revenue-analysis", params=params)

    assert response.status_code == 200, (
        f"Expected 200 for valid params {params}, got {response.status_code}: "
        f"{response.text[:200]}"
    )

    data = response.json()
    actual_fields = set(data.keys())

    # The response must contain all expected contract fields
    missing = REVENUE_ANALYSIS_EXPECTED_FIELDS - actual_fields
    assert not missing, (
        f"Revenue-analysis response missing contract fields: {missing}. "
        f"Params: {params}, actual fields: {actual_fields}"
    )

    # Verify field types
    assert isinstance(data["region"], str)
    assert isinstance(data["year"], int)
    assert isinstance(data["total_revenue"], (int, float))
    assert isinstance(data["gross_revenue"], (int, float))
    assert isinstance(data["net_revenue"], (int, float))
    assert isinstance(data["costs"], dict)
    assert isinstance(data["summary"], dict)
    assert isinstance(data["metadata"], dict)

    # Metadata must contain unit field with value "$"
    assert "unit" in data["metadata"], "metadata must contain 'unit' field"
    assert data["metadata"]["unit"] == "$", (
        f"Revenue metadata unit must be '$', got '{data['metadata']['unit']}'"
    )


# ---------------------------------------------------------------------------
# Property 10: API 契约向后兼容 — Health endpoint
# ---------------------------------------------------------------------------


@settings(max_examples=200, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st.just(None))  # Health has no parameters; run 200 times for stability
def test_property_10_health_contract_stability(_):
    """Feature: platform-optimization, Property 10: API 契约向后兼容

    The /api/health endpoint must always return HTTP 200 with consistent
    field structure regardless of system state.

    **Validates: Requirements 4.3**
    """
    cache_mock = MagicMock()
    cache_mock.get_json.return_value = None
    cache_mock.set_json.return_value = None

    with patch("deps.get_db", return_value=_DB), \
         patch("deps.get_cache", return_value=cache_mock):
        client = TestClient(_APP)
        response = client.get("/api/health")

    assert response.status_code == 200

    data = response.json()
    actual_fields = set(data.keys())

    missing = HEALTH_EXPECTED_FIELDS - actual_fields
    assert not missing, (
        f"Health response missing contract fields: {missing}. "
        f"Actual fields: {actual_fields}"
    )

    assert isinstance(data["status"], str)
    assert isinstance(data["degraded_modules"], list)
    assert data["status"] in ("healthy", "degraded")


# ---------------------------------------------------------------------------
# Cleanup
# ---------------------------------------------------------------------------


def teardown_module():
    """Clean up temporary test database."""
    try:
        os.remove(_TEST_DB_PATH)
    except OSError:
        pass
