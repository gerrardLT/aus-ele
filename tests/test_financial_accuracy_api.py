"""API integration tests for Financial Accuracy Modules.

Tests GET/POST endpoints, response format, and HTTP error codes using FastAPI TestClient.

Requirements: 15.1-15.6
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes.cost_structure_routes import router as cost_structure_router
from routes.forward_price_routes import router as forward_price_router


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def app():
    """Create a FastAPI app with cost structure and forward price routers."""
    app = FastAPI()
    app.include_router(cost_structure_router)
    app.include_router(forward_price_router)
    return app


@pytest.fixture
def client(app):
    """TestClient for the test app."""
    return TestClient(app)


# ---------------------------------------------------------------------------
# GET /api/cost-structure/{region} tests
# ---------------------------------------------------------------------------


class TestCostStructureAPI:
    """Test GET /api/cost-structure/{region} endpoint."""

    def test_get_cost_structure_nsw1_returns_200(self, client):
        """GET /api/cost-structure/NSW1 returns 200 with valid breakdown."""
        response = client.get("/api/cost-structure/NSW1")
        assert response.status_code == 200

        data = response.json()
        assert data["region"] == "NSW1"
        assert "total_fixed_costs" in data
        assert "total_variable_costs" in data
        assert "total_annual_cost" in data
        assert "line_items" in data
        assert "mlf_applied" in data
        assert isinstance(data["line_items"], list)
        assert len(data["line_items"]) > 0

        # Verify cost breakdown structure
        assert data["total_annual_cost"] == pytest.approx(
            data["total_fixed_costs"] + data["total_variable_costs"], rel=1e-6
        )

    def test_get_cost_structure_all_regions(self, client):
        """GET /api/cost-structure/{region} works for all supported regions."""
        regions = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"]
        for region in regions:
            response = client.get(f"/api/cost-structure/{region}")
            assert response.status_code == 200, f"Failed for region {region}"
            data = response.json()
            assert data["region"] == region

    def test_get_cost_structure_invalid_region_returns_422(self, client):
        """GET /api/cost-structure/INVALID returns 422."""
        response = client.get("/api/cost-structure/INVALID")
        assert response.status_code == 422

        data = response.json()
        assert "detail" in data

    def test_get_cost_structure_with_custom_params(self, client):
        """GET /api/cost-structure/SA1 with custom query params returns valid data."""
        response = client.get(
            "/api/cost-structure/SA1",
            params={
                "power_mw": 200.0,
                "duration_hours": 2.0,
                "annual_throughput_mwh": 100000.0,
                "connection_type": "distribution",
            },
        )
        assert response.status_code == 200

        data = response.json()
        assert data["region"] == "SA1"
        # Distribution-connected should have non-zero DUOS
        duos_items = [i for i in data["line_items"] if i["name"] == "DUOS"]
        assert len(duos_items) == 1

    def test_get_cost_structure_line_items_have_required_fields(self, client):
        """Each line item has name, fee_type, annual_amount, percentage_of_total."""
        response = client.get("/api/cost-structure/NSW1")
        assert response.status_code == 200

        data = response.json()
        for item in data["line_items"]:
            assert "name" in item
            assert "fee_type" in item
            assert "annual_amount" in item
            assert "percentage_of_total" in item
            assert item["fee_type"] in ("fixed", "variable")


# ---------------------------------------------------------------------------
# GET /api/forward-scenarios tests
# ---------------------------------------------------------------------------


class TestForwardScenariosAPI:
    """Test GET /api/forward-scenarios endpoint."""

    def test_get_forward_scenarios_returns_list_of_3(self, client):
        """GET /api/forward-scenarios returns list of 3 scenarios."""
        response = client.get("/api/forward-scenarios")
        assert response.status_code == 200

        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 3

        # Verify scenario types
        scenario_types = {s["scenario"] for s in data}
        assert scenario_types == {"central", "high", "low"}

    def test_get_forward_scenarios_structure(self, client):
        """Each scenario has required fields."""
        response = client.get("/api/forward-scenarios")
        assert response.status_code == 200

        data = response.json()
        for scenario in data:
            assert "scenario" in scenario
            assert "name" in scenario
            assert "description" in scenario
            assert "assumptions" in scenario
            assert isinstance(scenario["assumptions"], list)
            assert len(scenario["assumptions"]) > 0

    def test_get_forward_scenarios_by_region_sa1(self, client):
        """GET /api/forward-scenarios/SA1 returns ScenarioComparisonResult."""
        response = client.get("/api/forward-scenarios/SA1")
        assert response.status_code == 200

        data = response.json()
        assert data["region"] == "SA1"
        assert "central" in data
        assert "high" in data
        assert "low" in data

        # Verify each scenario projection structure
        for scenario_key in ("central", "high", "low"):
            projection = data[scenario_key]
            assert projection["region"] == "SA1"
            assert "annual_projections" in projection
            assert len(projection["annual_projections"]) == 20
            assert "total_revenue_per_mw" in projection
            assert "npv_per_mw" in projection

    def test_get_forward_scenarios_by_region_invalid_returns_422(self, client):
        """GET /api/forward-scenarios/INVALID returns 422."""
        response = client.get("/api/forward-scenarios/INVALID")
        assert response.status_code == 422

        data = response.json()
        assert "detail" in data

    def test_get_forward_scenarios_by_region_all_regions(self, client):
        """GET /api/forward-scenarios/{region} works for all supported regions."""
        regions = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1", "WEM"]
        for region in regions:
            response = client.get(f"/api/forward-scenarios/{region}")
            assert response.status_code == 200, f"Failed for region {region}"
            data = response.json()
            assert data["region"] == region

    def test_forward_scenario_annual_projections_structure(self, client):
        """Annual projections have required fields."""
        response = client.get("/api/forward-scenarios/NSW1")
        assert response.status_code == 200

        data = response.json()
        for annual in data["central"]["annual_projections"]:
            assert "year" in annual
            assert "estimated_revenue_per_mw" in annual
            assert "state_of_health" in annual
            assert "mean_spread" in annual
            assert "capture_rate" in annual
