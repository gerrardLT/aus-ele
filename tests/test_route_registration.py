"""
Tests for the route registration module and health endpoint.

Validates:
- register_all_routes loads all available modules
- Single module failure does not prevent other modules from loading
- /api/health reports degraded modules correctly
"""

import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Ensure backend is on the path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))


def _make_app() -> FastAPI:
    """Create a fresh FastAPI app for testing."""
    return FastAPI()


class TestRegisterAllRoutes:
    """Tests for register_all_routes function."""

    def test_registers_all_modules_successfully(self):
        """All placeholder modules have a router attribute and load without error."""
        import routes

        app = _make_app()
        degraded = routes.register_all_routes(app, degraded_modules=[])
        # All placeholder modules export a router, so none should be degraded
        assert degraded == []

    def test_single_module_failure_does_not_block_others(self):
        """If one module fails to import, the rest still register."""
        import importlib
        import routes

        app = _make_app()

        real_import = importlib.import_module

        def failing_import(name, *args, **kwargs):
            if name == "routes.price_routes":
                raise ImportError("Simulated import failure")
            return real_import(name, *args, **kwargs)

        with patch("importlib.import_module", side_effect=failing_import):
            degraded = routes.register_all_routes(app, degraded_modules=[])

        assert "routes.price_routes" in degraded
        # Only the one module should be degraded
        assert len(degraded) == 1

    def test_module_without_router_attribute_is_degraded(self):
        """A module that loads but has no 'router' attribute is marked degraded."""
        import routes

        app = _make_app()

        mock_module_no_router = MagicMock(spec=[])  # no 'router' attribute
        del mock_module_no_router.router  # ensure hasattr returns False

        def selective_import(name, *args, **kwargs):
            if name == "routes.admin_routes":
                return mock_module_no_router
            import importlib
            return importlib.__import__(name, *args, **kwargs)

        with patch("importlib.import_module") as mock_import:
            # Make all modules return a proper mock with router, except admin_routes
            normal_mock = MagicMock()
            normal_mock.router = MagicMock()

            def side_effect(name):
                if name == "routes.admin_routes":
                    m = MagicMock(spec=[])
                    # Explicitly remove router attribute
                    if hasattr(m, 'router'):
                        del m.router
                    return m
                m = MagicMock()
                m.router = MagicMock()
                return m

            mock_import.side_effect = side_effect
            degraded = routes.register_all_routes(app, degraded_modules=[])

        assert "routes.admin_routes" in degraded

    def test_degraded_modules_stored_in_module_state(self):
        """When no external list is provided, degraded modules are stored in module state."""
        import routes

        # Reset module state
        routes._degraded_modules = []

        app = _make_app()

        def failing_import(name):
            if name == "routes.finland_routes":
                raise RuntimeError("Simulated failure")
            m = MagicMock()
            m.router = MagicMock()
            return m

        with patch("importlib.import_module", side_effect=failing_import):
            routes.register_all_routes(app)

        assert "routes.finland_routes" in routes.get_degraded_modules()

    def test_get_degraded_modules_returns_copy(self):
        """get_degraded_modules returns a copy, not the internal list."""
        import routes

        routes._degraded_modules = ["routes.test_module"]
        result = routes.get_degraded_modules()
        result.append("should_not_appear")
        assert "should_not_appear" not in routes._degraded_modules


class TestHealthEndpoint:
    """Tests for the /api/health endpoint."""

    def _create_app_with_health(self, degraded: list[str] | None = None) -> FastAPI:
        """Create an app with the health route registered."""
        import routes
        from routes.health import router as health_router

        # Set module-level degraded state
        routes._degraded_modules = degraded if degraded is not None else []

        app = _make_app()
        app.include_router(health_router)
        return app

    def test_healthy_status_when_no_degraded_modules(self):
        """Health endpoint returns 'healthy' when all modules loaded."""
        app = self._create_app_with_health(degraded=[])
        client = TestClient(app)

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["degraded_modules"] == []

    def test_degraded_status_when_modules_failed(self):
        """Health endpoint returns 'degraded' with failed module list."""
        failed = ["routes.price_routes", "routes.finland_routes"]
        app = self._create_app_with_health(degraded=failed)
        client = TestClient(app)

        response = client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["degraded_modules"] == failed
