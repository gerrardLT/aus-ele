"""
Unit tests for aggregation routes — stage-summary endpoint and Redis caching.

Validates:
- Task 1.2: GET /api/stage-summary/{market}/{region}/{stage_id} endpoint
- Task 1.3: Redis cache-aside pattern for aggregation endpoints

Requirements: 6.2, 7.1, 7.2
"""

import hashlib
import sys
import types
from unittest.mock import MagicMock, patch

import pytest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

# Stub heavy optional dependencies
sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.aggregation_routes import (
    CACHE_SCOPE_MARKET_SUMMARY,
    CACHE_SCOPE_STAGE_SUMMARY,
    CACHE_TTL_SECONDS,
    VALID_STAGE_IDS,
    StageSummaryData,
    KpiMetric,
    _build_cache_key,
    router,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a FastAPI app with only the aggregation router."""
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    """TestClient for the aggregation router."""
    return TestClient(app)


def _mock_stage_data(stage_id: str = "market_opportunity") -> StageSummaryData:
    """Create a mock StageSummaryData for testing."""
    return StageSummaryData(
        summary_text="Test summary for stage",
        sentiment="positive",
        kpis=[
            KpiMetric(label="Test KPI 1", value=42.0, unit="$/MWh", sentiment="positive"),
            KpiMetric(label="Test KPI 2", value=10.5, unit="%", sentiment="neutral"),
        ],
    )


# ---------------------------------------------------------------------------
# Task 1.2: Stage-summary endpoint tests
# ---------------------------------------------------------------------------


class TestStageSummaryEndpoint:
    """Tests for GET /api/stage-summary/{market}/{region}/{stage_id}."""

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_valid_stage_id_returns_200(self, mock_computers, mock_get_cache, client):
        """Valid stage_id returns 200 with correct response structure."""
        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_computers.__contains__ = lambda self, key: key == "market_opportunity"
        mock_computers.get = MagicMock(
            return_value=lambda market, region, year, params: _mock_stage_data()
        )
        mock_computers.items = MagicMock(return_value=[])

        response = client.get("/api/stage-summary/NEM/NSW1/market-opportunity")
        assert response.status_code == 200

        data = response.json()
        assert data["stage_id"] == "market-opportunity"
        assert data["market"] == "NEM"
        assert data["region"] == "NSW1"
        assert data["summary_text"] == "Test summary for stage"
        assert data["sentiment"] == "positive"
        assert len(data["kpis"]) == 2
        assert data["warnings"] == []

    def test_invalid_stage_id_returns_422(self, client):
        """Invalid stage_id returns 422 with error detail."""
        response = client.get("/api/stage-summary/NEM/NSW1/invalid-stage")
        assert response.status_code == 422
        data = response.json()
        assert "invalid-stage" in data["detail"].lower() or "Invalid stage_id" in data["detail"]

    @pytest.mark.parametrize("stage_id", sorted(VALID_STAGE_IDS))
    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_all_valid_stage_ids_accepted(self, mock_computers, mock_get_cache, stage_id, client):
        """All four valid stage IDs are accepted by the endpoint."""
        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        registry_key = stage_id.replace("-", "_")
        mock_computers.get = MagicMock(
            return_value=lambda market, region, year, params: _mock_stage_data(registry_key)
        )

        response = client.get(f"/api/stage-summary/NEM/NSW1/{stage_id}")
        assert response.status_code == 200
        assert response.json()["stage_id"] == stage_id

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_response_contains_metadata(self, mock_computers, mock_get_cache, client):
        """Response includes metadata object with required fields."""
        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_computers.get = MagicMock(
            return_value=lambda market, region, year, params: _mock_stage_data()
        )

        response = client.get("/api/stage-summary/NEM/NSW1/market-opportunity")
        data = response.json()

        assert "metadata" in data
        metadata = data["metadata"]
        assert metadata["market"] == "NEM"
        assert metadata["region_or_zone"] == "NSW1"
        assert "timezone" in metadata
        assert "currency" in metadata
        assert metadata["methodology_version"] == "stage_summary_v1"

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_kpis_have_required_fields(self, mock_computers, mock_get_cache, client):
        """Each KPI in the response has label, value, unit, and sentiment."""
        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        mock_computers.get = MagicMock(
            return_value=lambda market, region, year, params: _mock_stage_data()
        )

        response = client.get("/api/stage-summary/NEM/NSW1/market-opportunity")
        data = response.json()

        for kpi in data["kpis"]:
            assert "label" in kpi
            assert "value" in kpi
            assert "unit" in kpi
            assert "sentiment" in kpi
            assert kpi["sentiment"] in ("positive", "negative", "neutral", "warning")

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_data_unavailable_returns_200_with_warnings(self, mock_computers, mock_get_cache, client):
        """When stage computation fails, returns 200 with warnings."""
        from routes.aggregation_routes import DataUnavailableError

        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        def raise_unavailable(market, region, year, params):
            raise DataUnavailableError("No data for test", metric_name="test_metric")

        mock_computers.get = MagicMock(return_value=raise_unavailable)

        response = client.get("/api/stage-summary/NEM/NSW1/market-opportunity")
        assert response.status_code == 200

        data = response.json()
        assert data["summary_text"] == "数据暂不可用"
        assert data["sentiment"] == "neutral"
        assert data["kpis"] == []
        assert len(data["warnings"]) == 1
        assert data["warnings"][0]["stage"] == "market-opportunity"
        assert data["warnings"][0]["severity"] == "degraded"


# ---------------------------------------------------------------------------
# Task 1.3: Redis caching tests
# ---------------------------------------------------------------------------


class TestCacheKeyGeneration:
    """Tests for _build_cache_key helper."""

    def test_cache_key_deterministic(self):
        """Same parameters produce the same cache key."""
        key1 = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87)
        key2 = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87)
        assert key1 == key2

    def test_cache_key_varies_with_params(self):
        """Different parameters produce different cache keys."""
        key1 = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87)
        key2 = _build_cache_key("NEM", "NSW1", 2025, 200.0, 4.0, 0.87)
        assert key1 != key2

    def test_cache_key_includes_stage_id(self):
        """Stage-specific cache key includes stage_id."""
        key_market = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87)
        key_stage = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87, stage_id="market-opportunity")
        assert key_market != key_stage
        assert "stage-summary" in key_stage
        assert "market-summary" in key_market

    def test_cache_key_format(self):
        """Cache key follows expected format."""
        key = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87)
        assert key.startswith("market-summary:NEM:NSW1:2025:")

        key_stage = _build_cache_key("NEM", "NSW1", 2025, 100.0, 4.0, 0.87, stage_id="revenue-estimation")
        assert key_stage.startswith("stage-summary:NEM:NSW1:2025:revenue-estimation:")


class TestCacheIntegration:
    """Tests for cache-aside pattern in aggregation endpoints."""

    @patch("routes.aggregation_routes.get_cache")
    def test_market_summary_cache_hit_returns_cached(self, mock_get_cache, client):
        """Market-summary returns cached response on cache hit."""
        cached_response = {
            "market": "NEM",
            "region": "NSW1",
            "year": 2025,
            "bess_params": {"power_mw": 100.0, "duration_hours": 4.0, "round_trip_efficiency": 0.87},
            "stages": {
                "market_opportunity": {"summary_text": "Cached", "sentiment": "positive", "kpis": [
                    {"label": "Test", "value": 1.0, "unit": "$", "sentiment": "positive"},
                    {"label": "Test2", "value": 2.0, "unit": "$", "sentiment": "neutral"},
                ]},
                "opportunity_identification": None,
                "revenue_estimation": None,
                "investment_decision": None,
            },
            "overall_rating": "weak_opportunity",
            "metadata": {"market": "NEM", "region_or_zone": "NSW1", "timezone": "Australia/Sydney",
                         "currency": "AUD", "data_grade": "analytical",
                         "freshness": {"last_updated_at": "2025-01-01T00:00:00Z"},
                         "source_version": "2025-01-01T00:00:00Z",
                         "methodology_version": "market_summary_v1"},
            "warnings": [],
        }

        mock_cache = MagicMock()
        mock_cache.get_json.return_value = cached_response
        mock_get_cache.return_value = mock_cache

        response = client.get("/api/market-summary/NEM/NSW1", params={"year": 2025})
        assert response.status_code == 200
        data = response.json()
        assert data["stages"]["market_opportunity"]["summary_text"] == "Cached"

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_market_summary_stores_in_cache_on_success(self, mock_computers, mock_get_cache, client):
        """Market-summary stores result in cache when no warnings."""
        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        # Mock all stage computers to return data
        mock_computers.items = MagicMock(return_value=[
            ("market_opportunity", lambda m, r, y, p: _mock_stage_data()),
            ("opportunity_identification", lambda m, r, y, p: _mock_stage_data()),
            ("revenue_estimation", lambda m, r, y, p: _mock_stage_data()),
            ("investment_decision", lambda m, r, y, p: _mock_stage_data()),
        ])

        response = client.get("/api/market-summary/NEM/NSW1", params={"year": 2025})
        assert response.status_code == 200

        # Verify cache.set_json was called
        mock_cache.set_json.assert_called_once()
        call_args = mock_cache.set_json.call_args
        assert call_args[0][0] == CACHE_SCOPE_MARKET_SUMMARY
        assert call_args[0][3] == CACHE_TTL_SECONDS

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_market_summary_does_not_cache_partial_results(self, mock_computers, mock_get_cache, client):
        """Market-summary does NOT cache responses with warnings."""
        from routes.aggregation_routes import DataUnavailableError

        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        def raise_for_one(market, region, year, params):
            raise DataUnavailableError("No data", metric_name="test")

        mock_computers.items = MagicMock(return_value=[
            ("market_opportunity", lambda m, r, y, p: _mock_stage_data()),
            ("opportunity_identification", raise_for_one),
            ("revenue_estimation", lambda m, r, y, p: _mock_stage_data()),
            ("investment_decision", lambda m, r, y, p: _mock_stage_data()),
        ])

        response = client.get("/api/market-summary/NEM/NSW1", params={"year": 2025})
        assert response.status_code == 200
        assert len(response.json()["warnings"]) > 0

        # Cache should NOT be written
        mock_cache.set_json.assert_not_called()

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_stage_summary_cache_hit(self, mock_computers, mock_get_cache, client):
        """Stage-summary returns cached response on cache hit."""
        cached_response = {
            "stage_id": "market-opportunity",
            "market": "NEM",
            "region": "NSW1",
            "summary_text": "Cached stage",
            "sentiment": "positive",
            "kpis": [
                {"label": "KPI", "value": 99.0, "unit": "$", "sentiment": "positive"},
                {"label": "KPI2", "value": 5.0, "unit": "%", "sentiment": "neutral"},
            ],
            "metadata": {"market": "NEM", "region_or_zone": "NSW1", "timezone": "Australia/Sydney",
                         "currency": "AUD", "data_grade": "analytical",
                         "freshness": {"last_updated_at": "2025-01-01T00:00:00Z"},
                         "source_version": "2025-01-01T00:00:00Z",
                         "methodology_version": "stage_summary_v1"},
            "warnings": [],
        }

        mock_cache = MagicMock()
        mock_cache.get_json.return_value = cached_response
        mock_get_cache.return_value = mock_cache

        response = client.get("/api/stage-summary/NEM/NSW1/market-opportunity")
        assert response.status_code == 200
        assert response.json()["summary_text"] == "Cached stage"

    @patch("routes.aggregation_routes.get_cache")
    @patch("routes.aggregation_routes.STAGE_COMPUTERS")
    def test_stage_summary_does_not_cache_on_warnings(self, mock_computers, mock_get_cache, client):
        """Stage-summary does NOT cache responses with warnings."""
        from routes.aggregation_routes import DataUnavailableError

        mock_cache = MagicMock()
        mock_cache.get_json.return_value = None
        mock_get_cache.return_value = mock_cache

        def raise_unavailable(market, region, year, params):
            raise DataUnavailableError("No data", metric_name="test")

        mock_computers.get = MagicMock(return_value=raise_unavailable)

        response = client.get("/api/stage-summary/NEM/NSW1/market-opportunity")
        assert response.status_code == 200
        assert len(response.json()["warnings"]) > 0

        # Cache should NOT be written
        mock_cache.set_json.assert_not_called()

    def test_cache_ttl_is_6_hours(self):
        """Cache TTL constant is 6 hours (21600 seconds)."""
        assert CACHE_TTL_SECONDS == 6 * 60 * 60
        assert CACHE_TTL_SECONDS == 21600
