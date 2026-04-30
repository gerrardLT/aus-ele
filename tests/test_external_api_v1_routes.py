import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

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
        self.original_db = server.db
        server.db = self.db
        server.job_orchestrator.db = self.db
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
        usage_rows = self.db.fetch_external_api_usage(client_id="client-1")
        self.assertEqual(len(usage_rows), 1)

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
        self.assertEqual(payload["data"]["billing"]["totals"]["request_units"], 250)
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
