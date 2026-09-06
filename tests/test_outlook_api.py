"""Property-based and integration tests for Investment Outlook API routes.

Feature: investment-outlook-scenarios

Task 8.2 - Property 11: API responses contain standard metadata
    For any successful API response from any of the 4 outlook endpoints,
    the response SHALL contain a 'metadata' object with non-empty fields:
    market, region, timezone, currency, and methodology_version.

Task 8.3 - API integration tests
    Uses FastAPI TestClient to test 4 endpoints' normal and error responses.
    Tests invalid region returns 400 + INVALID_REGION.
    Tests invalid market returns 400 + INVALID_MARKET.

**Validates: Requirements 5.4, 5.5**
"""

import os
import sys
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from tests.support import stub_optional_dep

# Stub heavy optional dependencies that may not be installed in test env
stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from hypothesis import given, settings, HealthCheck
from hypothesis import strategies as st

from fastapi import FastAPI
from fastapi.testclient import TestClient

from exceptions import MarketModuleError
from routes import _register_market_module_error_handler
from routes.outlook_routes import router, NEM_REGIONS


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

METADATA_REQUIRED_KEYS = {"market", "region", "timezone", "currency", "methodology_version"}


def _build_metadata(region: str = "NSW1") -> dict:
    """Build a standard metadata dict for mocked responses."""
    return {
        "market": "NEM",
        "region": region,
        "timezone": "Australia/Sydney",
        "currency": "AUD",
        "methodology_version": "1.0",
    }


def _mock_cannibalization_response(region: str = "NSW1"):
    """Build a mock CannibalizationResponse-like dict."""
    from models.outlook_models import (
        CannibalizationResponse,
        DilutionPoint,
        YearlyProjection,
        MarketExample,
    )

    return CannibalizationResponse(
        metadata=_build_metadata(region),
        region=region,
        alpha=0.6,
        base_capacity_mw=500.0,
        base_revenue_per_mw=150000.0,
        dilution_curve=[
            DilutionPoint(capacity_mw=500, revenue_per_mw=150000, dilution_pct=0.0),
            DilutionPoint(capacity_mw=1000, revenue_per_mw=98000, dilution_pct=34.7),
        ],
        yearly_projections=[
            YearlyProjection(
                year=2025,
                projected_capacity_mw=700,
                projected_revenue_per_mw=120000,
                dilution_pct=20.0,
                new_projects=["Project A"],
            ),
        ],
        current_dilution_pct=20.0,
        warning_triggered=False,
        market_examples=[
            MarketExample(
                region="QLD1",
                description="QLD revenue declined",
                data_year=2024,
                actual_value=73000,
                label="actual",
            )
        ],
        conclusion="Revenue dilution is moderate.",
    )


def _mock_fcas_collapse_response(region: str = "NEM-wide"):
    """Build a mock FcasCollapseResponse-like dict."""
    from models.outlook_models import (
        FcasCollapseResponse,
        FcasServiceResult,
        MarketExample,
    )

    return FcasCollapseResponse(
        metadata=_build_metadata(region),
        region=region,
        year=2025,
        beta=1.5,
        services=[
            FcasServiceResult(
                service_name="raise6sec",
                supply_mw=800,
                demand_mw=200,
                supply_demand_ratio=4.0,
                classification="collapsed",
                price_ceiling_per_mwh=0.0,
            ),
        ],
        total_fcas_ceiling_per_mw_year=15000.0,
        historical_trajectory=[{"year": 2020, "total_fcas_revenue_per_mw": 384000}],
        market_examples=[
            MarketExample(
                region="NEM-wide",
                description="FCAS revenue declined",
                data_year=2025,
                actual_value=11000,
                label="actual",
            )
        ],
        conclusion="Maximum realistic FCAS revenue: $15k/MW/yr.",
    )


def _mock_regional_timing_response():
    """Build a mock RegionalTimingResponse-like dict."""
    from models.outlook_models import (
        RegionalTimingResponse,
        RegionTimingScore,
        MarketExample,
    )

    return RegionalTimingResponse(
        metadata=_build_metadata("NEM-wide"),
        target_year=2026,
        weights_used={
            "coal_retirement": 0.30,
            "pipeline_growth": 0.25,
            "renewable_penetration": 0.20,
            "revenue_trajectory": 0.25,
        },
        rankings=[
            RegionTimingScore(
                region="VIC1",
                rank=1,
                total_score=0.78,
                dimensions={
                    "coal_retirement": 0.9,
                    "pipeline_growth": 0.6,
                    "renewable_penetration": 0.7,
                    "revenue_trajectory": 0.8,
                },
                key_events=["Yallourn closure 2028"],
            ),
            RegionTimingScore(
                region="NSW1",
                rank=2,
                total_score=0.65,
                dimensions={
                    "coal_retirement": 0.8,
                    "pipeline_growth": 0.5,
                    "renewable_penetration": 0.6,
                    "revenue_trajectory": 0.7,
                },
                key_events=["Eraring closure 2027"],
            ),
        ],
        coal_data_available=True,
        market_examples=[
            MarketExample(
                region="SA1",
                description="SA outperformed after coal closure",
                data_year=2023,
                actual_value=40.0,
                label="actual",
            )
        ],
        conclusion="VIC is projected to be the most attractive region.",
    )


def _mock_merchant_risk_response(region: str = "NSW1"):
    """Build a mock MerchantRiskResponse-like dict."""
    from models.outlook_models import (
        MerchantRiskResponse,
        RevenueDistribution,
        MarketExample,
    )

    return MerchantRiskResponse(
        metadata=_build_metadata(region),
        region=region,
        power_mw=100.0,
        duration_hours=4.0,
        n_simulations=1000,
        distribution=RevenueDistribution(
            p10=45000,
            p50=95000,
            p90=180000,
            mean=100000,
            std=35000,
            min_observed=30000,
            max_observed=220000,
        ),
        histogram_bins=[
            {"bin_start": 30000, "bin_end": 60000, "count": 100, "frequency": 0.1},
            {"bin_start": 60000, "bin_end": 90000, "count": 300, "frequency": 0.3},
        ],
        min_contract_coverage_pct=40.0,
        contract_revenue_needed=80000.0,
        bankability_met=True,
        historical_revenue_range={"min": 45000, "max": 180000, "years_used": 3},
        years_of_data=3,
        data_warning=None,
        market_examples=[
            MarketExample(
                region="NSW1",
                description="NSW merchant revenue range",
                data_year=2024,
                actual_value=95000,
                label="actual",
            )
        ],
        conclusion="With P90 at $180k/MW/yr, bankability is met.",
    )


def _create_test_app() -> FastAPI:
    """Create a FastAPI app with the outlook router and error handler."""
    app = FastAPI()
    app.include_router(router)
    _register_market_module_error_handler(app)
    return app


@pytest.fixture
def client():
    """TestClient with outlook routes and error handler registered."""
    app = _create_test_app()
    return TestClient(app, raise_server_exceptions=False)


# ---------------------------------------------------------------------------
# Property 11: API responses contain standard metadata
# ---------------------------------------------------------------------------


class TestProperty11ApiMetadata:
    """Property 11: API responses contain standard metadata.

    For any successful API response from any of the 4 outlook endpoints,
    the response SHALL contain a 'metadata' object with non-empty fields:
    market, region, timezone, currency, and methodology_version.

    **Validates: Requirements 5.4**
    """

    @given(region=st.sampled_from(NEM_REGIONS))
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_cannibalization_metadata_property(self, region: str):
        """Property 11: Cannibalization endpoint returns standard metadata.

        Feature: investment-outlook-scenarios, Property 11: API responses contain standard metadata
        **Validates: Requirements 5.4**
        """
        mock_response = _mock_cannibalization_response(region)

        app = _create_test_app()

        with patch(
            "routes.outlook_routes.CannibalizationEngine",
            create=True,
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.simulate.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes._capacity_loader"):
                # Patch the engine import inside the route handler
                with patch(
                    "engines.cannibalization_engine.CannibalizationEngine",
                    MockEngine,
                ):
                    client = TestClient(app, raise_server_exceptions=False)
                    response = client.get(
                        "/api/v1/outlook/cannibalization",
                        params={"market": "NEM", "region": region},
                    )

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "metadata" in data, "Response missing 'metadata' key"
        metadata = data["metadata"]

        for key in METADATA_REQUIRED_KEYS:
            assert key in metadata, f"metadata missing key '{key}'"
            assert metadata[key] != "", f"metadata['{key}'] is empty"
            assert metadata[key] is not None, f"metadata['{key}'] is None"

    @given(region=st.sampled_from(NEM_REGIONS + ["NEM-wide"]))
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_fcas_collapse_metadata_property(self, region: str):
        """Property 11: FCAS collapse endpoint returns standard metadata.

        Feature: investment-outlook-scenarios, Property 11: API responses contain standard metadata
        **Validates: Requirements 5.4**
        """
        mock_response = _mock_fcas_collapse_response(region)

        app = _create_test_app()

        with patch(
            "engines.fcas_collapse_engine.FcasCollapseEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.forecast.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()):
                client = TestClient(app, raise_server_exceptions=False)
                response = client.get(
                    "/api/v1/outlook/fcas-collapse",
                    params={"market": "NEM", "region": region},
                )

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "metadata" in data, "Response missing 'metadata' key"
        metadata = data["metadata"]

        for key in METADATA_REQUIRED_KEYS:
            assert key in metadata, f"metadata missing key '{key}'"
            assert metadata[key] != "", f"metadata['{key}'] is empty"
            assert metadata[key] is not None, f"metadata['{key}'] is None"

    @given(target_year=st.integers(min_value=2024, max_value=2035))
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_regional_timing_metadata_property(self, target_year: int):
        """Property 11: Regional timing endpoint returns standard metadata.

        Feature: investment-outlook-scenarios, Property 11: API responses contain standard metadata
        **Validates: Requirements 5.4**
        """
        mock_response = _mock_regional_timing_response()

        app = _create_test_app()

        with patch(
            "engines.regional_timing_engine.RegionalTimingEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.score_regions.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()), \
                 patch("routes.outlook_routes._load_coal_retirement_schedule", return_value=None), \
                 patch("routes.outlook_routes._capacity_loader"):
                client = TestClient(app, raise_server_exceptions=False)
                response = client.get(
                    "/api/v1/outlook/regional-timing",
                    params={"market": "NEM", "target_year": target_year},
                )

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "metadata" in data, "Response missing 'metadata' key"
        metadata = data["metadata"]

        for key in METADATA_REQUIRED_KEYS:
            assert key in metadata, f"metadata missing key '{key}'"
            assert metadata[key] != "", f"metadata['{key}'] is empty"
            assert metadata[key] is not None, f"metadata['{key}'] is None"

    @given(region=st.sampled_from(NEM_REGIONS))
    @settings(
        max_examples=100,
        deadline=None,
        suppress_health_check=[HealthCheck.function_scoped_fixture],
    )
    def test_merchant_risk_metadata_property(self, region: str):
        """Property 11: Merchant risk endpoint returns standard metadata.

        Feature: investment-outlook-scenarios, Property 11: API responses contain standard metadata
        **Validates: Requirements 5.4**
        """
        mock_response = _mock_merchant_risk_response(region)

        app = _create_test_app()

        with patch(
            "engines.merchant_risk_engine.MerchantRiskEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.simulate.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()):
                client = TestClient(app, raise_server_exceptions=False)
                response = client.post(
                    "/api/v1/outlook/merchant-risk",
                    json={
                        "market": "NEM",
                        "region": region,
                        "power_mw": 100,
                        "duration_hours": 4,
                        "n_simulations": 100,
                    },
                )

        assert response.status_code == 200, f"Got {response.status_code}: {response.text}"
        data = response.json()
        assert "metadata" in data, "Response missing 'metadata' key"
        metadata = data["metadata"]

        for key in METADATA_REQUIRED_KEYS:
            assert key in metadata, f"metadata missing key '{key}'"
            assert metadata[key] != "", f"metadata['{key}'] is empty"
            assert metadata[key] is not None, f"metadata['{key}'] is None"


# ---------------------------------------------------------------------------
# Task 8.3: API Integration Tests
# ---------------------------------------------------------------------------


class TestOutlookApiIntegration:
    """Integration tests for the 4 outlook API endpoints.

    Tests normal responses and error responses using FastAPI TestClient.

    **Validates: Requirements 5.5**
    """

    # ------------------------------------------------------------------
    # Cannibalization endpoint
    # ------------------------------------------------------------------

    def test_cannibalization_valid_request_returns_200(self, client):
        """GET /api/v1/outlook/cannibalization with valid params returns 200.

        **Validates: Requirements 5.5**
        """
        mock_response = _mock_cannibalization_response("NSW1")

        with patch(
            "engines.cannibalization_engine.CannibalizationEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.simulate.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes._capacity_loader"):
                response = client.get(
                    "/api/v1/outlook/cannibalization",
                    params={"market": "NEM", "region": "NSW1", "alpha": 0.6},
                )

        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert data["region"] == "NSW1"

    def test_cannibalization_invalid_region_returns_400(self, client):
        """GET /api/v1/outlook/cannibalization with invalid region returns 400 + INVALID_REGION.

        **Validates: Requirements 5.5**
        """
        response = client.get(
            "/api/v1/outlook/cannibalization",
            params={"market": "NEM", "region": "INVALID"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_REGION"
        assert "message" in data
        assert "suggested_action" in data

    def test_cannibalization_invalid_market_returns_400(self, client):
        """GET /api/v1/outlook/cannibalization with invalid market returns 400 + INVALID_MARKET.

        **Validates: Requirements 5.5**
        """
        response = client.get(
            "/api/v1/outlook/cannibalization",
            params={"market": "INVALID", "region": "NSW1"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_MARKET"
        assert "message" in data
        assert "suggested_action" in data

    # ------------------------------------------------------------------
    # FCAS Collapse endpoint
    # ------------------------------------------------------------------

    def test_fcas_collapse_valid_request_returns_200(self, client):
        """GET /api/v1/outlook/fcas-collapse with valid params returns 200.

        **Validates: Requirements 5.5**
        """
        mock_response = _mock_fcas_collapse_response("NEM-wide")

        with patch(
            "engines.fcas_collapse_engine.FcasCollapseEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.forecast.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()):
                response = client.get(
                    "/api/v1/outlook/fcas-collapse",
                    params={"market": "NEM", "region": "NEM-wide", "year": 2025},
                )

        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert data["region"] == "NEM-wide"

    def test_fcas_collapse_invalid_region_returns_400(self, client):
        """GET /api/v1/outlook/fcas-collapse with invalid region returns 400 + INVALID_REGION.

        **Validates: Requirements 5.5**
        """
        response = client.get(
            "/api/v1/outlook/fcas-collapse",
            params={"market": "NEM", "region": "INVALID"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_REGION"

    def test_fcas_collapse_invalid_market_returns_400(self, client):
        """GET /api/v1/outlook/fcas-collapse with invalid market returns 400 + INVALID_MARKET.

        **Validates: Requirements 5.5**
        """
        response = client.get(
            "/api/v1/outlook/fcas-collapse",
            params={"market": "INVALID", "region": "NEM-wide"},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_MARKET"

    # ------------------------------------------------------------------
    # Regional Timing endpoint
    # ------------------------------------------------------------------

    def test_regional_timing_valid_request_returns_200(self, client):
        """GET /api/v1/outlook/regional-timing with valid params returns 200.

        **Validates: Requirements 5.5**
        """
        mock_response = _mock_regional_timing_response()

        with patch(
            "engines.regional_timing_engine.RegionalTimingEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.score_regions.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()), \
                 patch("routes.outlook_routes._load_coal_retirement_schedule", return_value=None), \
                 patch("routes.outlook_routes._capacity_loader"):
                response = client.get(
                    "/api/v1/outlook/regional-timing",
                    params={"market": "NEM", "target_year": 2026},
                )

        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert data["target_year"] == 2026

    def test_regional_timing_invalid_market_returns_400(self, client):
        """GET /api/v1/outlook/regional-timing with invalid market returns 400 + INVALID_MARKET.

        **Validates: Requirements 5.5**
        """
        response = client.get(
            "/api/v1/outlook/regional-timing",
            params={"market": "INVALID", "target_year": 2026},
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_MARKET"

    # ------------------------------------------------------------------
    # Merchant Risk endpoint
    # ------------------------------------------------------------------

    def test_merchant_risk_valid_request_returns_200(self, client):
        """POST /api/v1/outlook/merchant-risk with valid body returns 200.

        **Validates: Requirements 5.5**
        """
        mock_response = _mock_merchant_risk_response("NSW1")

        with patch(
            "engines.merchant_risk_engine.MerchantRiskEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.simulate.return_value = mock_response
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()):
                response = client.post(
                    "/api/v1/outlook/merchant-risk",
                    json={
                        "market": "NEM",
                        "region": "NSW1",
                        "power_mw": 100,
                        "duration_hours": 4,
                        "n_simulations": 100,
                    },
                )

        assert response.status_code == 200
        data = response.json()
        assert "metadata" in data
        assert data["region"] == "NSW1"

    def test_merchant_risk_invalid_region_returns_400(self, client):
        """POST /api/v1/outlook/merchant-risk with invalid region returns 400 + INVALID_REGION.

        **Validates: Requirements 5.5**
        """
        response = client.post(
            "/api/v1/outlook/merchant-risk",
            json={
                "market": "NEM",
                "region": "INVALID",
                "power_mw": 100,
                "duration_hours": 4,
                "n_simulations": 100,
            },
        )

        assert response.status_code == 400
        data = response.json()
        assert data["error_code"] == "INVALID_REGION"

    def test_merchant_risk_invalid_market_returns_422(self, client):
        """POST /api/v1/outlook/merchant-risk with invalid market returns 422.

        The MerchantRiskRequest model uses Literal["NEM"] for market,
        so Pydantic rejects invalid values with 422 before route validation.

        **Validates: Requirements 5.5**
        """
        response = client.post(
            "/api/v1/outlook/merchant-risk",
            json={
                "market": "INVALID",
                "region": "NSW1",
                "power_mw": 100,
                "duration_hours": 4,
                "n_simulations": 100,
            },
        )

        # Pydantic validates Literal["NEM"] before our custom _validate_market runs
        assert response.status_code == 422
        data = response.json()
        assert "detail" in data

    # ------------------------------------------------------------------
    # Degraded response tests (missing data)
    # ------------------------------------------------------------------

    def test_cannibalization_engine_failure_returns_structured_error(self, client):
        """When engine raises an exception, returns structured error response.

        **Validates: Requirements 5.5**
        """
        with patch(
            "engines.cannibalization_engine.CannibalizationEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.simulate.side_effect = Exception("No capacity data")
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes._capacity_loader"):
                response = client.get(
                    "/api/v1/outlook/cannibalization",
                    params={"market": "NEM", "region": "NSW1"},
                )

        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "CANNIBALIZATION_ENGINE_FAILURE"
        assert "message" in data
        assert "suggested_action" in data

    def test_fcas_collapse_engine_failure_returns_structured_error(self, client):
        """When FCAS engine raises an exception, returns structured error response.

        **Validates: Requirements 5.5**
        """
        with patch(
            "engines.fcas_collapse_engine.FcasCollapseEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.forecast.side_effect = Exception("No FCAS data")
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()):
                response = client.get(
                    "/api/v1/outlook/fcas-collapse",
                    params={"market": "NEM", "region": "NEM-wide"},
                )

        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "FCAS_COLLAPSE_ENGINE_FAILURE"
        assert "message" in data
        assert "suggested_action" in data

    def test_merchant_risk_engine_failure_returns_structured_error(self, client):
        """When merchant risk engine raises an exception, returns structured error response.

        **Validates: Requirements 5.5**
        """
        with patch(
            "engines.merchant_risk_engine.MerchantRiskEngine",
        ) as MockEngine:
            mock_engine_instance = MagicMock()
            mock_engine_instance.simulate.side_effect = Exception("Insufficient history")
            MockEngine.return_value = mock_engine_instance

            with patch("routes.outlook_routes.get_db", return_value=MagicMock()):
                response = client.post(
                    "/api/v1/outlook/merchant-risk",
                    json={
                        "market": "NEM",
                        "region": "NSW1",
                        "power_mw": 100,
                        "duration_hours": 4,
                        "n_simulations": 100,
                    },
                )

        assert response.status_code == 500
        data = response.json()
        assert data["error_code"] == "MERCHANT_RISK_ENGINE_FAILURE"
        assert "message" in data
        assert "suggested_action" in data
