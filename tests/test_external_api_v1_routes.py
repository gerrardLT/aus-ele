import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths, reset_pg_tables

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


class ExternalApiV1RouteTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        # All DatabaseManagers share one PG database, so usage/client rows seeded
        # by previous runs leak in and break count/quota assertions. Reset them.
        reset_pg_tables(self.db, "external_api_usage", "external_api_client")
        self.original_db = server.db
        server.db = self.db
        server.job_orchestrator.db = self.db
        self.client = TestClient(server.app)
        self.db.upsert_organization(
            {
                "organization_id": "org_ext",
                "name": "External Org",
                "created_at": "2026-04-27T00:00:00Z",
                "updated_at": "2026-04-27T00:00:00Z",
            }
        )
        self.db.upsert_workspace(
            {
                "workspace_id": "ws_ext",
                "organization_id": "org_ext",
                "name": "External Workspace",
                "created_at": "2026-04-27T00:00:00Z",
                "updated_at": "2026-04-27T00:00:00Z",
            }
        )
        server.seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Test Client",
            plan="internal",
            organization_id="org_ext",
            workspace_id="ws_ext",
        )
        server.seed_external_api_client(
            self.db,
            client_id="starter-client",
            api_key="starter-key",
            client_name="Starter Client",
            plan="starter",
            organization_id="org_ext",
            workspace_id="ws_ext",
        )

    def tearDown(self):
        server.db = self.original_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_v1_prices_route_requires_api_key(self):
        with self.assertRaises(Exception) as exc_info:
            server.get_v1_prices(year=2025, region="NSW1", x_api_key=None, offset=0, limit=2)
        self.assertEqual(exc_info.exception.status_code, 401)
        self.assertEqual(exc_info.exception.detail["code"], "missing_api_key")
        self.assertEqual(exc_info.exception.detail["message"], "Missing API key")

    def test_v1_prices_route_returns_structured_error_for_invalid_api_key(self):
        with self.assertRaises(Exception) as exc_info:
            server.get_v1_prices(year=2025, region="NSW1", x_api_key="bad-key", offset=0, limit=2)
        self.assertEqual(exc_info.exception.status_code, 401)
        self.assertEqual(exc_info.exception.detail["code"], "invalid_api_key")
        self.assertEqual(exc_info.exception.detail["message"], "Invalid API key")

    def test_v1_prices_route_wraps_paginated_response_and_logs_usage(self):
        with mock.patch(
            "server.get_price_trend",
            return_value={
                "region": "NSW1",
                "year": 2025,
                "total_points": 5,
                "returned_points": 5,
                "data": [{"ts": 1}, {"ts": 2}, {"ts": 3}, {"ts": 4}, {"ts": 5}],
                "metadata": {"market": "NEM"},
                "regime_layer": {
                    "primary_regime": {"regime": "scarcity", "score": 67.0, "confidence": 0.74},
                    "active_regimes": [{"regime": "scarcity", "score": 67.0, "confidence": 0.74}],
                    "regime_score_map": {"scarcity": 67.0},
                    "drivers": [],
                    "transition_hints": [],
                    "metadata": {"dataset_family": "regime_layer"},
                },
                "regime_compact": {
                    "availability_status": "available",
                    "primary_regime": {"regime": "scarcity", "score": 67.0, "confidence": 0.74},
                    "active_regimes": [{"regime": "scarcity", "score": 67.0, "confidence": 0.74}],
                    "regime_score_map": {"scarcity": 67.0},
                    "top_drivers": [],
                    "transition_hints": [],
                    "warnings": [],
                },
            },
        ):
            payload = server.get_v1_prices(year=2025, region="NSW1", x_api_key="test-key", offset=1, limit=2)

        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(len(payload["data"]["items"]), 2)
        self.assertEqual(payload["pagination"]["offset"], 1)
        self.assertEqual(payload["pagination"]["next_offset"], 3)
        self.assertIn("trace_id", payload["meta"])
        self.assertEqual(payload["meta"]["quota"]["plan"], "internal")
        self.assertEqual(payload["meta"]["lineage"]["methodology_version"], None)
        self.assertEqual(payload["meta"]["workspace_id"], "ws_ext")
        self.assertEqual(payload["data"]["regime_layer"]["primary_regime"]["regime"], "scarcity")
        self.assertEqual(payload["data"]["regime_compact"]["primary_regime"]["regime"], "scarcity")
        usage_rows = self.db.fetch_external_api_usage(client_id="client-1")
        self.assertEqual(len(usage_rows), 1)

    def test_v1_events_route_preserves_regime_layer_from_internal_payload(self):
        with mock.patch(
            "server.get_event_overlays",
            return_value={
                "events": [{"event_id": "evt-1"}, {"event_id": "evt-2"}],
                "states": [{"state_id": "state-1"}],
                "metadata": {"market": "NEM", "methodology_version": "event_overlays_v1"},
                "regime_layer": {
                    "primary_regime": {"regime": "negative_price", "score": 74.0, "confidence": 0.81},
                    "active_regimes": [{"regime": "negative_price", "score": 74.0, "confidence": 0.81}],
                    "regime_score_map": {"negative_price": 74.0, "oversupply": 62.0},
                    "drivers": [{"headline": "Negative interval ratio elevated"}],
                    "transition_hints": ["Oversupply can deepen if rooftop PV remains elevated."],
                    "metadata": {"dataset_family": "regime_layer"},
                },
                "regime_compact": {
                    "availability_status": "available",
                    "primary_regime": {"regime": "negative_price", "score": 74.0, "confidence": 0.81},
                    "active_regimes": [{"regime": "negative_price", "score": 74.0, "confidence": 0.81}],
                    "regime_score_map": {"negative_price": 74.0, "oversupply": 62.0},
                    "top_drivers": [{"headline": "Negative interval ratio elevated", "driver_type": "price_shape"}],
                    "transition_hints": ["Oversupply can deepen if rooftop PV remains elevated."],
                    "warnings": [],
                },
            },
        ):
            payload = server.get_v1_events(
                year=2025,
                region="NSW1",
                market="NEM",
                x_api_key="test-key",
                offset=0,
                limit=1,
            )

        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(len(payload["data"]["items"]), 1)
        self.assertEqual(payload["data"]["regime_layer"]["primary_regime"]["regime"], "negative_price")
        self.assertEqual(payload["data"]["regime_layer"]["metadata"]["dataset_family"], "regime_layer")
        self.assertEqual(payload["data"]["regime_compact"]["primary_regime"]["regime"], "negative_price")
        self.assertEqual(payload["meta"]["lineage"]["methodology_version"], "event_overlays_v1")

    def test_v1_fcas_route_preserves_regime_layer_from_internal_payload(self):
        with mock.patch(
            "server.get_fcas_analysis",
            return_value={
                "region": "NSW1",
                "year": 2025,
                "summary": {"total_avg_fcas_price": 21.5},
                "service_breakdown": [],
                "hourly": [],
                "data": [{"period": "2025-01-01", "raise6sec_rrp": 12.0}],
                "metadata": {"market": "NEM", "methodology_version": "fcas_analysis_v1"},
                "regime_layer": {
                    "primary_regime": {"regime": "reserve_stress", "score": 78.0, "confidence": 0.8},
                    "active_regimes": [{"regime": "reserve_stress", "score": 78.0, "confidence": 0.8}],
                    "regime_score_map": {"reserve_stress": 78.0},
                    "drivers": [{"headline": "Reserve shortfall signal elevated"}],
                    "transition_hints": ["Reserve stress can escalate into broader scarcity if shortfalls persist."],
                    "metadata": {"dataset_family": "regime_layer"},
                },
                "regime_compact": {
                    "availability_status": "available",
                    "primary_regime": {"regime": "reserve_stress", "score": 78.0, "confidence": 0.8},
                    "active_regimes": [{"regime": "reserve_stress", "score": 78.0, "confidence": 0.8}],
                    "regime_score_map": {"reserve_stress": 78.0},
                    "top_drivers": [{"headline": "Reserve shortfall signal elevated", "driver_type": "reserve_shortfall"}],
                    "transition_hints": ["Reserve stress can escalate into broader scarcity if shortfalls persist."],
                    "warnings": [],
                },
            },
        ):
            payload = server.get_v1_fcas(
                year=2025,
                region="NSW1",
                aggregation="daily",
                capacity_mw=100,
                x_api_key="test-key",
                offset=0,
                limit=1,
            )

        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(len(payload["data"]["items"]), 1)
        self.assertEqual(payload["data"]["summary"]["regime_layer"]["primary_regime"]["regime"], "reserve_stress")
        self.assertEqual(payload["data"]["summary"]["regime_layer"]["metadata"]["dataset_family"], "regime_layer")
        self.assertEqual(payload["data"]["summary"]["regime_compact"]["primary_regime"]["regime"], "reserve_stress")
        self.assertEqual(payload["meta"]["lineage"]["methodology_version"], "fcas_analysis_v1")

    def test_v1_prices_route_returns_quota_exceeded_error_when_plan_limit_is_hit(self):
        for _ in range(10):
            server.meter_external_api_usage(
                self.db,
                client_id="starter-client",
                endpoint="/api/v1/prices",
                http_method="GET",
                status_code=200,
                request_units=100,
                latency_ms=20,
                api_version="v1",
            )

        with mock.patch(
            "server.get_price_trend",
            return_value={
                "region": "NSW1",
                "year": 2025,
                "total_points": 1,
                "returned_points": 1,
                "data": [{"ts": 1}],
                "metadata": {"market": "NEM"},
            },
        ):
            with self.assertRaises(Exception) as exc_info:
                server.get_v1_prices(year=2025, region="NSW1", x_api_key="starter-key", offset=0, limit=2)

        self.assertEqual(exc_info.exception.status_code, 429)
        self.assertEqual(exc_info.exception.detail["code"], "quota_exceeded")

    def test_v1_status_route_returns_sla_payload(self):
        with mock.patch("server.get_current_trace_id", return_value="0123456789abcdef0123456789abcdef"):
            payload = server.get_v1_status(x_api_key="test-key")
        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(payload["endpoint"], "status")
        self.assertIn("status", payload["data"])
        self.assertEqual(payload["meta"]["trace_id"], "0123456789abcdef0123456789abcdef")
        self.assertEqual(payload["meta"]["organization_id"], "org_ext")

    def test_v1_report_job_uses_client_workspace_scope(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_ext",
            organization_id="org_ext",
        )

        self.assertEqual(job["payload_json"]["workspace_id"], "ws_ext")
        self.assertEqual(job["payload_json"]["organization_id"], "org_ext")

    def test_v1_developer_portal_route_returns_client_profile_quota_summary_and_ledger(self):
        server.meter_external_api_usage(
            self.db,
            client_id="starter-client",
            endpoint="/api/v1/prices",
            http_method="GET",
            status_code=200,
            request_units=250,
            latency_ms=20,
            api_version="v1",
        )

        payload = server.get_v1_developer_portal(x_api_key="starter-key")

        self.assertEqual(payload["api_version"], "v1")
        self.assertEqual(payload["endpoint"], "developer/portal")
        self.assertEqual(payload["data"]["client"]["client_id"], "starter-client")
        self.assertEqual(payload["data"]["quota"]["daily_unit_limit"], 1000)
        # 250 explicit units above + 1 unit metered by the developer-portal call
        # itself (_metered_v1_call reserves quota before building the billing
        # summary), so the billing total is 251.
        self.assertEqual(payload["data"]["billing"]["totals"]["request_units"], 251)
        self.assertEqual(payload["data"]["ledger"]["items"][0]["client_id"], "starter-client")

    def test_v1_query_path_uses_shared_scope_guard(self):
        self.db.upsert_workspace_policy(
            {
                "workspace_id": "ws_ext",
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        scope = server._build_client_access_scope(
            {
                "organization_id": "org_ext",
                "workspace_id": "ws_ext",
            }
        )
        server._assert_scope_allows_internal_query(scope, region="NSW1", market="NEM")

    def test_v1_prices_openapi_publishes_structured_error_schema(self):
        schema = server.app.openapi()
        responses = schema["paths"]["/api/v1/prices"]["get"]["responses"]

        self.assertIn("ExternalApiErrorPayload", responses["401"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("ExternalApiErrorPayload", responses["403"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("ExternalApiErrorPayload", responses["404"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("ExternalApiErrorPayload", responses["500"]["content"]["application/json"]["schema"]["$ref"])

    def test_v1_routes_share_structured_error_schema_matrix(self):
        schema = server.app.openapi()
        routes = [
            ("/api/v1/status", "get"),
            ("/api/v1/prices", "get"),
            ("/api/v1/events", "get"),
            ("/api/v1/fcas", "get"),
            ("/api/v1/bess/backtests", "post"),
            ("/api/v1/investment/scenarios", "post"),
            ("/api/v1/data-quality", "get"),
            ("/api/v1/developer/portal", "get"),
            ("/api/v1/jobs", "get"),
            ("/api/v1/jobs/{job_id}", "get"),
            ("/api/v1/jobs/{job_id}/lineage", "get"),
        ]

        for route, method in routes:
            responses = schema["paths"][route][method]["responses"]
            for status_code in ("401", "403", "404", "500"):
                self.assertIn("ExternalApiErrorPayload", responses[status_code]["content"]["application/json"]["schema"]["$ref"])

    def test_admin_external_api_billing_summary_route_returns_usage_totals_and_quota(self):
        server.meter_external_api_usage(
            self.db,
            client_id="starter-client",
            endpoint="/api/v1/prices",
            http_method="GET",
            status_code=200,
            request_units=250,
            latency_ms=20,
            api_version="v1",
        )

        payload = server.get_external_api_billing_summary_route(client_id="starter-client", limit=10)

        self.assertEqual(payload["totals"]["request_units"], 250)
        self.assertEqual(payload["items"][0]["client_id"], "starter-client")
        self.assertEqual(payload["items"][0]["quota"]["daily_unit_limit"], 1000)
        self.assertEqual(payload["ledger"]["items"][0]["request_units"], 250)

    def test_finland_board_overview_route_returns_cards(self):
        payload = {
            "cards": [{"field_key": "fcr_n_price_eur_mw", "value": 12.5}],
            "window": {"start": "2026-04-01T00:00:00Z", "end": "2026-04-02T00:00:00Z"},
            "generated_at_utc": "2026-04-02T01:00:00Z",
        }

        with mock.patch("server.build_finland_board_overview_payload", return_value=payload) as builder:
            response = self.client.get(
                "/api/finland/board/overview",
                params={
                    "start": "2026-04-01T00:00:00Z",
                    "end": "2026-04-02T00:00:00Z",
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["cards"][0]["field_key"], "fcr_n_price_eur_mw")
        builder.assert_called_once_with(
            self.db,
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
        )

    def test_finland_board_table_route_supports_capacity_hourly(self):
        payload = {
            "view": "capacity_hourly",
            "title": "capacity_1h",
            "granularity": "1h",
            "timezone": "Europe/Helsinki",
            "columns": [{"field_key": "spot_price_fi_eur_mwh"}],
            "rows": [{"timestamp_helsinki": "2026-04-01T03:00:00+03:00", "spot_price_fi_eur_mwh": 75.0}],
        }

        with mock.patch("server.build_finland_board_table_payload", return_value=payload) as builder:
            response = self.client.get(
                "/api/finland/board/table",
                params={
                    "view": "capacity_hourly",
                    "start": "2026-04-01T00:00:00Z",
                    "end": "2026-04-02T00:00:00Z",
                    "tz": "Europe/Helsinki",
                    "limit": 300,
                },
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["view"], "capacity_hourly")
        self.assertEqual(result["rows"][0]["spot_price_fi_eur_mwh"], 75.0)
        builder.assert_called_once_with(
            self.db,
            view="capacity_hourly",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            tz="Europe/Helsinki",
            limit=300,
        )

    def test_finland_board_chart_route_supports_spread(self):
        payload = {
            "mode": "spread",
            "granularity": "1h",
            "series": [
                {
                    "field_key": "imbalance_price_eur_mwh-minus-spot_price_fi_eur_mwh",
                    "points": [{"timestamp_utc": "2026-04-01T00:00:00Z", "value": 30.0}],
                }
            ],
            "window": {"start": "2026-04-01T00:00:00Z", "end": "2026-04-02T00:00:00Z"},
        }

        with mock.patch("server.build_finland_board_chart_payload", return_value=payload) as builder:
            response = self.client.get(
                "/api/finland/board/chart",
                params=[
                    ("fields", "imbalance_price_eur_mwh"),
                    ("fields", "spot_price_fi_eur_mwh"),
                    ("mode", "spread"),
                    ("start", "2026-04-01T00:00:00Z"),
                    ("end", "2026-04-02T00:00:00Z"),
                    ("granularity", "hour"),
                    ("limit_points", "240"),
                ],
            )

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["mode"], "spread")
        self.assertEqual(result["series"][0]["points"][0]["value"], 30.0)
        builder.assert_called_once_with(
            self.db,
            fields=["imbalance_price_eur_mwh", "spot_price_fi_eur_mwh"],
            mode="spread",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            granularity="hour",
            limit_points=240,
        )

    def test_finland_board_field_catalog_route_returns_items(self):
        payload = {
            "items": [
                {
                    "field_key": "spot_price_fi_eur_mwh",
                    "label": "Finland Spot Price",
                    "source_type": "external_join",
                }
            ]
        }

        with mock.patch("server.build_finland_board_field_catalog_rows", return_value=payload["items"]) as builder:
            response = self.client.get("/api/finland/board/field-catalog")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["items"][0]["field_key"], "spot_price_fi_eur_mwh")
        self.assertEqual(result["items"][0]["source_type"], "external_join")
        builder.assert_called_once_with()

    def test_finland_board_readiness_route_returns_sources_without_seed_side_effect(self):
        market_model_payload = {
            "summary": {"live_source_count": 1, "configured_external_source_count": 1},
            "sources": [{"source_key": "fingrid", "status": "live"}],
            "metadata": {"warnings": ["planned_external_sources"]},
        }
        readiness_payload = {
            "summary": {"live_source_count": 1, "configured_external_source_count": 1, "field_count": 2},
            "sources": [{"source_key": "fingrid", "status": "live"}],
            "warnings": ["planned_external_sources"],
        }

        with mock.patch("server.build_finland_market_model_payload", return_value=market_model_payload) as model_builder:
            with mock.patch("server.build_finland_board_readiness_payload", return_value=readiness_payload) as readiness_builder:
                with mock.patch("server.fingrid_service.seed_dataset_catalog") as seed_catalog:
                    response = self.client.get("/api/finland/board/readiness")

        self.assertEqual(response.status_code, 200)
        result = response.json()
        self.assertEqual(result["summary"]["field_count"], 2)
        self.assertEqual(result["sources"][0]["source_key"], "fingrid")
        seed_catalog.assert_not_called()
        model_builder.assert_called_once_with(self.db)
        readiness_builder.assert_called_once_with(self.db, market_model_payload=market_model_payload)

    def test_finland_board_table_route_maps_unknown_view_to_404(self):
        with mock.patch("server.build_finland_board_table_payload", side_effect=KeyError("Unsupported Finland board view: nope")):
            response = self.client.get("/api/finland/board/table", params={"view": "nope"})

        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["detail"], "Unsupported Finland board view: nope")
