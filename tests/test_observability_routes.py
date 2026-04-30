import os
import sys
import tempfile
import types
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


class ObservabilityRouteTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        server.db = self.db
        server.job_orchestrator.db = self.db
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        server.db = self.original_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_observability_status_route_returns_freshness_payload(self):
        self.db.set_last_update_time("2026-04-27 12:00:00")
        payload = server.get_observability_status()

        self.assertIn("sources", payload)
        self.assertIn("job_summary", payload)

    def test_job_lineage_route_returns_trace_payload(self):
        job = server.enqueue_report_generation_job(report_type="monthly_market_report", year=2025, region="NSW1", month="04")
        payload = server.get_job_lineage_route(job["job_id"])

        self.assertEqual(payload["trace"]["trace_id"], f"job:{job['job_id']}")
        self.assertEqual(payload["job"]["job_id"], job["job_id"])

    def test_observability_status_route_filters_job_summary_by_access_scope(self):
        org = server.create_organization_route(name="Acme")
        workspace_a = server.create_workspace_route(organization_id=org["organization_id"], name="A")
        workspace_b = server.create_workspace_route(organization_id=org["organization_id"], name="B")
        server.job_orchestrator.enqueue(
            "report_generate",
            payload={"workspace_id": workspace_a["workspace_id"], "organization_id": org["organization_id"]},
            queue_name="reports",
            source_key="reporting",
        )
        server.job_orchestrator.enqueue(
            "report_generate",
            payload={"workspace_id": workspace_b["workspace_id"], "organization_id": org["organization_id"]},
            queue_name="reports",
            source_key="reporting",
        )

        payload = server.get_observability_status(
            access_scope={
                "organization_id": org["organization_id"],
                "workspace_id": workspace_a["workspace_id"],
            }
        )

        self.assertEqual(payload["job_summary"]["queued"], 1)

    def test_observability_status_includes_telemetry_and_openlineage_health(self):
        with mock.patch("server.get_telemetry_status", return_value={"enabled": True, "configured": True, "exporter": "otlp", "metrics": {"enabled": True, "configured": True, "exporter": "otlp"}, "logs": {"correlation_enabled": True, "format": "json"}, "collection": {"mode": "partial", "centralized_signals": 2, "required_signals": 3}}), \
             mock.patch("server.get_openlineage_status", return_value={"enabled": True, "sink": "http", "endpoint": "https://lineage.example/api/v1/lineage"}):
            payload = server.get_observability_status()

        self.assertEqual(payload["telemetry"]["exporter"], "otlp")
        self.assertTrue(payload["telemetry"]["metrics"]["enabled"])
        self.assertTrue(payload["telemetry"]["logs"]["correlation_enabled"])
        self.assertEqual(payload["telemetry"]["collection"]["mode"], "partial")
        self.assertEqual(payload["openlineage"]["sink"], "http")
        self.assertTrue(payload["collector"]["propagation_standardized"])
        self.assertIn("lineage", payload["collector"]["signals"])

    def test_request_middleware_records_request_metric(self):
        with mock.patch("server.record_request_metric") as record_request_metric:
            response = self.client.get("/api/summary")

        self.assertEqual(response.status_code, 200)
        record_request_metric.assert_called_once_with(endpoint="/api/summary", method="GET")

    def test_auxiliary_routes_publish_openapi_schema_refs(self):
        schema = server.app.openapi()

        self.assertIn("DataQualitySummaryPayload", schema["paths"]["/api/data-quality/summary"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("DataQualityIssueRowsPayload", schema["paths"]["/api/data-quality/issues"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("ObservabilityStatusPayload", schema["paths"]["/api/observability/status"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])

    def test_business_auxiliary_routes_publish_openapi_schema_refs(self):
        schema = server.app.openapi()

        route_expectations = {
            ("/api/market-screening", "get"): "LooseObjectPayload",
            ("/api/alerts/rules", "post"): "LooseObjectPayload",
            ("/api/alerts/rules", "get"): "AlertRuleListPayload",
            ("/api/alerts/states", "get"): "AlertStateListPayload",
            ("/api/alerts/delivery-logs", "get"): "AlertDeliveryLogListPayload",
            ("/api/alerts/evaluate", "post"): "LooseObjectPayload",
            ("/api/reports/generate", "get"): "LooseObjectPayload",
            ("/api/reports/jobs", "post"): "AcceptedJobActionPayload",
            ("/api/jobs", "get"): "JobListPayload",
            ("/api/jobs", "post"): "AcceptedJobActionPayload",
            ("/api/jobs/{job_id}", "get"): "LooseObjectPayload",
            ("/api/jobs/{job_id}/events", "get"): "JobEventListPayload",
            ("/api/jobs/{job_id}/lineage", "get"): "LooseObjectPayload",
            ("/api/jobs/run-next", "post"): "RunNextJobPayload",
            ("/api/grid-forecast/coverage", "get"): "LooseObjectPayload",
            ("/api/sync_data", "post"): "AcceptedJobActionPayload",
            ("/api/fingrid/datasets", "get"): "FingridDatasetCatalogPayload",
            ("/api/finland/market-model", "get"): "LooseObjectPayload",
            ("/api/years", "get"): "AvailableYearsPayload",
            ("/api/network-fees", "get"): "NetworkFeesPayload",
            ("/api/admin/external-api/billing-summary", "get"): "LooseObjectPayload",
            ("/api/v1/developer/portal", "get"): "LooseObjectPayload",
        }

        for (route, method), model_name in route_expectations.items():
            route_schema = schema["paths"][route][method]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            self.assertIn(model_name, route_schema)
