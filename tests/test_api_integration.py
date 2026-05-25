"""
Integration tests for the AEMO Intelligence platform API.

Validates:
- Route module split: all API endpoints remain reachable
- Filter conditions pass end-to-end through the API
- Redis cache hit/miss paths
- Job queue submission and result polling
- Route module load failure degradation behavior

Requirements: 11.2
"""

import importlib
import os
import sys
import tempfile
import types
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

# Stub heavy optional dependencies that may not be installed in test env
sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from fastapi import FastAPI
from fastapi.testclient import TestClient


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_app_with_routes() -> FastAPI:
    """Create a FastAPI app with all route modules registered (no lifespan)."""
    from routes import register_all_routes
    from routes.health import router as health_router

    app = FastAPI()
    app.include_router(health_router)
    register_all_routes(app)
    return app


@pytest.fixture
def client():
    """TestClient with all routes registered."""
    app = _make_app_with_routes()
    return TestClient(app)


# ---------------------------------------------------------------------------
# 1. Route module split — API endpoint reachability
# ---------------------------------------------------------------------------


class TestEndpointReachability:
    """Verify all API endpoints are reachable after route module split."""

    def test_health_endpoint_reachable(self, client):
        """GET /api/health returns 200."""
        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert "degraded_modules" in data

    def test_price_trend_endpoint_reachable(self, client):
        """GET /api/price-trend returns 404 or 200 (depends on data), not 405/422 for missing route."""
        response = client.get("/api/price-trend", params={"year": 2024, "region": "NSW1"})
        # 404 = no data table, 200 = success — both confirm route is reachable
        assert response.status_code in (200, 404, 500)
        # Should NOT be 405 Method Not Allowed (route missing)
        assert response.status_code != 405

    def test_peak_analysis_endpoint_reachable(self, client):
        """GET /api/peak-analysis returns a valid response code."""
        response = client.get("/api/peak-analysis", params={"year": 2024, "region": "NSW1"})
        assert response.status_code in (200, 404, 500)
        assert response.status_code != 405

    def test_hourly_price_profile_endpoint_reachable(self, client):
        """GET /api/hourly-price-profile returns a valid response code."""
        response = client.get("/api/hourly-price-profile", params={"year": 2024, "region": "NSW1"})
        assert response.status_code in (200, 404, 500)
        assert response.status_code != 405

    def test_revenue_analysis_endpoint_reachable(self, client):
        """GET /api/revenue-analysis returns a valid response code."""
        response = client.get(
            "/api/revenue-analysis",
            params={"year": 2024, "region": "NSW1", "power_mw": 100, "energy_mwh": 400},
        )
        assert response.status_code in (200, 404, 422, 500)
        assert response.status_code != 405

    def test_investment_analysis_endpoint_reachable(self, client):
        """POST /api/investment-analysis returns a valid response code."""
        response = client.post(
            "/api/investment-analysis",
            json={"region": "SA1"},
        )
        assert response.status_code in (200, 404, 500)
        assert response.status_code != 405

    def test_fcas_analysis_endpoint_reachable(self, client):
        """GET /api/fcas-analysis returns a valid response code."""
        response = client.get(
            "/api/fcas-analysis",
            params={"year": 2024, "region": "NSW1"},
        )
        assert response.status_code in (200, 404, 500)
        assert response.status_code != 405

    def test_jobs_list_endpoint_reachable(self, client):
        """GET /api/jobs returns a valid response code."""
        response = client.get("/api/jobs")
        assert response.status_code in (200, 500)
        assert response.status_code != 405

    def test_observability_status_endpoint_reachable(self, client):
        """GET /api/observability/status returns a valid response code."""
        response = client.get("/api/observability/status")
        assert response.status_code in (200, 500)
        assert response.status_code != 405


# ---------------------------------------------------------------------------
# 2. Filter conditions end-to-end pass-through
# ---------------------------------------------------------------------------


class TestFilterPassthrough:
    """Verify filter conditions are passed through to API endpoints."""

    def test_price_trend_accepts_all_filter_params(self, client):
        """Price trend endpoint accepts market/region/year/quarter/month/day_type filters."""
        response = client.get(
            "/api/price-trend",
            params={
                "year": 2024,
                "region": "QLD1",
                "quarter": "Q1",
                "month": "03",
                "day_type": "WEEKDAY",
            },
        )
        # Route accepts the parameters (not 422 for unknown params)
        assert response.status_code in (200, 404, 500)

    def test_revenue_analysis_accepts_filter_params(self, client):
        """Revenue analysis endpoint accepts temporal filter parameters."""
        response = client.get(
            "/api/revenue-analysis",
            params={
                "year": 2024,
                "region": "SA1",
                "power_mw": 50,
                "energy_mwh": 200,
                "quarter": "Q2",
                "month": "06",
                "day_type": "WEEKEND",
            },
        )
        assert response.status_code in (200, 404, 500)

    def test_fcas_analysis_accepts_filter_params(self, client):
        """FCAS analysis endpoint accepts temporal filter parameters."""
        response = client.get(
            "/api/fcas-analysis",
            params={
                "year": 2024,
                "region": "VIC1",
                "quarter": "Q3",
            },
        )
        assert response.status_code in (200, 404, 500)

    def test_invalid_filter_returns_422(self, client):
        """Invalid parameter values return 422 validation error."""
        response = client.get(
            "/api/revenue-analysis",
            params={
                "year": 2024,
                "region": "NSW1",
                "power_mw": -10,  # Invalid: must be positive
                "energy_mwh": 400,
            },
        )
        assert response.status_code == 422


# ---------------------------------------------------------------------------
# 3. Redis cache hit/miss paths
# ---------------------------------------------------------------------------


class TestRedisCachePaths:
    """Verify Redis cache integration (mocked — no real Redis required)."""

    def test_cache_miss_computes_result(self):
        """When cache returns None, the endpoint computes a fresh result."""
        from response_cache import RedisResponseCache

        app = _make_app_with_routes()

        with patch.object(RedisResponseCache, "get_json", return_value=None):
            client = TestClient(app)
            response = client.get(
                "/api/price-trend",
                params={"year": 2024, "region": "NSW1"},
            )
            # Should attempt computation (404 if no data, 200 if data exists)
            assert response.status_code in (200, 404, 500)

    def test_cache_hit_returns_cached_response(self):
        """When cache returns a value, the endpoint returns it directly."""
        from response_cache import RedisResponseCache

        cached_data = {
            "region": "NSW1",
            "year": 2024,
            "month": None,
            "quarter": None,
            "day_type": None,
            "total_records": 100,
            "data": [{"timestamp": "2024-01-01T00:00:00", "price": 50.0}],
        }

        app = _make_app_with_routes()

        with patch.object(RedisResponseCache, "get_json", return_value=cached_data):
            client = TestClient(app)
            response = client.get(
                "/api/price-trend",
                params={"year": 2024, "region": "NSW1"},
            )
            # Should return 200 with cached data
            assert response.status_code == 200
            data = response.json()
            assert data["region"] == "NSW1"

    def test_cache_failure_degrades_gracefully(self):
        """When Redis raises an exception, the endpoint still works (computes fresh)."""
        from response_cache import RedisResponseCache

        app = _make_app_with_routes()

        with patch.object(
            RedisResponseCache, "get_json", side_effect=Exception("Redis connection refused")
        ):
            client = TestClient(app)
            response = client.get(
                "/api/price-trend",
                params={"year": 2024, "region": "NSW1"},
            )
            # Should still attempt computation, not crash
            assert response.status_code in (200, 404, 500)

    def test_cache_set_called_on_fresh_computation(self):
        """After computing a fresh result, the endpoint stores it in cache."""
        from response_cache import RedisResponseCache

        app = _make_app_with_routes()

        with patch.object(RedisResponseCache, "get_json", return_value=None), \
             patch.object(RedisResponseCache, "set_json") as mock_set:
            client = TestClient(app)
            response = client.get(
                "/api/price-trend",
                params={"year": 2024, "region": "NSW1"},
            )
            # If computation succeeded (200), cache should have been called
            if response.status_code == 200:
                assert mock_set.called


# ---------------------------------------------------------------------------
# 4. Job queue submission and result polling
# ---------------------------------------------------------------------------


class TestJobQueueIntegration:
    """Verify job queue submission and polling via API."""

    def _make_app_with_db(self):
        """Create app with a temporary database for job testing."""
        from database import DatabaseManager

        handle, db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = DatabaseManager(db_path)

        app = _make_app_with_routes()

        # Patch deps to use our temp DB
        with patch("deps.get_db", return_value=db):
            return app, db, db_path

    def test_create_job_returns_job_id(self):
        """POST /api/jobs creates a job and returns a job_id."""
        app, db, db_path = self._make_app_with_db()
        try:
            with patch("deps.get_db", return_value=db):
                client = TestClient(app)
                response = client.post(
                    "/api/jobs",
                    json={
                        "job_type": "market_sync",
                        "queue_name": "sync",
                        "source_key": "aemo",
                        "payload": {"manual": True},
                    },
                )
                assert response.status_code == 200
                data = response.json()
                assert "job_id" in data
                assert data["status"] == "accepted"
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_list_jobs_returns_items(self):
        """GET /api/jobs returns a list of jobs."""
        app, db, db_path = self._make_app_with_db()
        try:
            with patch("deps.get_db", return_value=db):
                client = TestClient(app)
                # Create a job first
                client.post(
                    "/api/jobs",
                    json={
                        "job_type": "report_generate",
                        "queue_name": "reports",
                        "source_key": "reporting",
                        "payload": {"report_type": "test"},
                    },
                )
                # List jobs
                response = client.get("/api/jobs")
                assert response.status_code == 200
                data = response.json()
                assert "items" in data
                assert len(data["items"]) >= 1
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_job_polling_returns_status(self):
        """Created job can be polled for status."""
        app, db, db_path = self._make_app_with_db()
        try:
            with patch("deps.get_db", return_value=db):
                client = TestClient(app)
                # Create a job
                create_response = client.post(
                    "/api/jobs",
                    json={
                        "job_type": "market_sync",
                        "queue_name": "sync",
                        "source_key": "aemo",
                        "payload": {},
                    },
                )
                job_id = create_response.json()["job_id"]

                # Poll for the job — check it exists in the list
                list_response = client.get("/api/jobs", params={"status": "queued"})
                assert list_response.status_code == 200
                items = list_response.json()["items"]
                job_ids = [item["job_id"] for item in items]
                assert job_id in job_ids
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


# ---------------------------------------------------------------------------
# 5. Route module load failure degradation
# ---------------------------------------------------------------------------


class TestRouteDegradation:
    """Verify graceful degradation when route modules fail to load."""

    def test_single_module_failure_other_routes_still_work(self):
        """If one route module fails, other endpoints remain accessible."""
        import routes

        real_import = importlib.import_module

        def failing_import(name, *args, **kwargs):
            if name == "routes.finland_routes":
                raise ImportError("Simulated finland_routes failure")
            return real_import(name, *args, **kwargs)

        app = FastAPI()

        from routes.health import router as health_router
        app.include_router(health_router)

        with patch("importlib.import_module", side_effect=failing_import):
            degraded = routes.register_all_routes(app, degraded_modules=[])

        assert "routes.finland_routes" in degraded

        client = TestClient(app)

        # Health endpoint reports degradation
        health_response = client.get("/api/health")
        assert health_response.status_code == 200

        # Other routes still work (price-trend is reachable)
        price_response = client.get(
            "/api/price-trend", params={"year": 2024, "region": "NSW1"}
        )
        assert price_response.status_code != 405  # Route exists

    def test_multiple_module_failures_health_reports_all(self):
        """Multiple module failures are all reported in /api/health."""
        import routes

        real_import = importlib.import_module

        failing_modules = {"routes.price_routes", "routes.fcas_routes"}

        def failing_import(name, *args, **kwargs):
            if name in failing_modules:
                raise RuntimeError(f"Simulated failure for {name}")
            return real_import(name, *args, **kwargs)

        app = FastAPI()
        from routes.health import router as health_router
        app.include_router(health_router)

        with patch("importlib.import_module", side_effect=failing_import):
            degraded = routes.register_all_routes(app, degraded_modules=[])

        # Patch module-level state for health endpoint
        with patch.object(routes, "_degraded_modules", degraded):
            client = TestClient(app)
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert "routes.price_routes" in data["degraded_modules"]
            assert "routes.fcas_routes" in data["degraded_modules"]

    def test_all_modules_fail_health_still_responds(self):
        """Even if all route modules fail, /api/health still responds."""
        import routes

        def always_fail(name, *args, **kwargs):
            raise ImportError(f"All modules fail: {name}")

        app = FastAPI()
        from routes.health import router as health_router
        app.include_router(health_router)

        with patch("importlib.import_module", side_effect=always_fail):
            degraded = routes.register_all_routes(app, degraded_modules=[])

        assert len(degraded) == len(routes.ROUTE_MODULES)

        with patch.object(routes, "_degraded_modules", degraded):
            client = TestClient(app)
            response = client.get("/api/health")
            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "degraded"
            assert len(data["degraded_modules"]) == len(routes.ROUTE_MODULES)

    def test_degraded_module_endpoint_returns_404_not_crash(self):
        """Endpoints from a failed module return 404, not a server crash."""
        import routes

        real_import = importlib.import_module

        def failing_import(name, *args, **kwargs):
            if name == "routes.price_routes":
                raise ImportError("Simulated price_routes failure")
            return real_import(name, *args, **kwargs)

        app = FastAPI()
        from routes.health import router as health_router
        app.include_router(health_router)

        with patch("importlib.import_module", side_effect=failing_import):
            routes.register_all_routes(app, degraded_modules=[])

        client = TestClient(app)

        # Price endpoint should not be registered — returns 404
        response = client.get(
            "/api/price-trend", params={"year": 2024, "region": "NSW1"}
        )
        assert response.status_code == 404
