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

    def test_model_governance_summary_route_returns_unified_governance_payload(self):
        self.db.set_last_update_time("2026-04-27 12:00:00")
        quality_rows = [
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "source_id": "aemo_nem_trading_price",
                "dataset_family": "settlement",
                "data_grade": "analytical",
                "quality_score": 0.99,
                "coverage_ratio": 1.0,
                "freshness_minutes": 10,
                "issues_json": [],
                "metadata_json": {"region_id": "NSW1"},
                "computed_at": "2026-04-27T12:00:00Z",
            },
            {
                "scope": "dataset",
                "market": "FINGRID",
                "dataset_key": "317",
                "source_id": "fingrid_dataset_317",
                "dataset_family": "reserve_requirement",
                "data_grade": "analytical-preview",
                "quality_score": 0.82,
                "coverage_ratio": 1.0,
                "freshness_minutes": 35,
                "issues_json": [
                    {
                        "issue_code": "resolution_mixture",
                        "severity": "warning",
                        "detail_json": {"resolution_minutes": [15, 60]},
                        "detected_at": "2026-04-27T12:00:00Z",
                    }
                ],
                "metadata_json": {"dataset_id": "317"},
                "computed_at": "2026-04-27T12:00:00Z",
            },
        ]
        with mock.patch("server.compute_quality_snapshots", return_value=quality_rows), \
             mock.patch(
                 "server.summarize_quality_snapshots",
                 return_value={"summary": {"market_count": 2, "snapshot_count": 2}, "markets": {}},
             ):
            payload = server.get_model_governance_summary()

        self.assertIn("freshness", payload)
        self.assertIn("quality", payload)
        self.assertIn("disclaimer", payload)
        self.assertIn("source_rows", payload)
        self.assertEqual(payload["disclaimer"]["investment_grade"], False)
        self.assertGreaterEqual(len(payload["source_rows"]), 2)
        self.assertEqual(payload["source_rows"][0]["source_id"], "aemo_nem_trading_price")
        self.assertEqual(payload["source_rows"][0]["dataset_family"], "settlement")
        self.assertEqual(payload["source_rows"][1]["source_id"], "fingrid_dataset_317")
        self.assertEqual(payload["source_rows"][1]["lineage"]["schema_mapping"], "map_fingrid_timeseries_row")
        self.assertEqual(payload["source_rows"][1]["issue_count"], 1)
        self.assertIn("models", payload["drift"])
        self.assertNotEqual(payload["drift"]["status"], "summary_only")
        self.assertIn(payload["drift"]["status"], {"available", "monitor", "elevated"})
        self.assertIn("quality-backed", payload["drift"]["reason"])
        self.assertEqual(len(payload["drift"]["models"]), 2)
        p2_model = next(model for model in payload["drift"]["models"] if model["model_key"] == "p2_forecast_layer")
        p3_model = next(model for model in payload["drift"]["models"] if model["model_key"] == "p3_bess_decision")
        self.assertIn(p2_model["status"], {"monitor", "elevated"})
        self.assertIn(p3_model["status"], {"monitor", "elevated"})
        self.assertEqual(p2_model["forecast_value_status"], "proxy_available")
        self.assertEqual(p3_model["forecast_value_status"], "available")
        self.assertEqual(payload["disclaimer"]["usage_scope"], "research_and_operational_support_only")
        self.assertEqual(payload["disclaimer"]["reason_code"], "non_investment_grade_governance_summary")

    def test_network_fees_route_returns_region_fee_mapping(self):
        response = self.client.get("/api/network-fees")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertIn("fees", payload)
        self.assertIsInstance(payload["fees"], dict)
        self.assertEqual(payload["fees"]["NSW1"], 45.0)
        self.assertEqual(payload["fees"]["WEM"], 40.0)

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
        self.assertIn("ModelGovernanceSummaryPayload", schema["paths"]["/api/model-governance/summary"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("P2ForecastLayerPayload", schema["paths"]["/api/p2/forecast-layer"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])
        self.assertIn("P3BessDecisionLayerPayload", schema["paths"]["/api/p3/bess/decision-layer"]["post"]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"])

    def test_business_auxiliary_routes_publish_openapi_schema_refs(self):
        schema = server.app.openapi()

        route_expectations = {
            ("/api/p0/datasets/load-actual", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/load-forecast", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/wind-forecast", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/wind-actual", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/solar-forecast", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/solar-actual", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/rooftop-pv", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/outage", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/interconnector-flow", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/reserve-requirement", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/reserve-shortfall", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/weather", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/unit-availability", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/settlement", "get"): "P0DatasetPayload",
            ("/api/p0/datasets/constraint", "get"): "P0DatasetPayload",
            ("/api/p1/regime-layer", "get"): "P1RegimeLayerPayload",
            ("/api/market-screening", "get"): "MarketScreeningPayload",
            ("/api/alerts/rules", "post"): "AlertRuleRecordPayload",
            ("/api/alerts/rules", "get"): "AlertRuleListPayload",
            ("/api/alerts/states", "get"): "AlertStateListPayload",
            ("/api/alerts/delivery-logs", "get"): "AlertDeliveryLogListPayload",
            ("/api/alerts/evaluate", "post"): "AlertEvaluationPayload",
            ("/api/reports/generate", "get"): "GeneratedReportPayload",
            ("/api/reports/jobs", "post"): "AcceptedJobActionPayload",
            ("/api/jobs", "get"): "JobListPayload",
            ("/api/jobs", "post"): "AcceptedJobActionPayload",
            ("/api/jobs/{job_id}", "get"): "JobDetailPayload",
            ("/api/jobs/{job_id}/events", "get"): "JobEventListPayload",
            ("/api/jobs/{job_id}/lineage", "get"): "JobLineagePayload",
            ("/api/jobs/run-next", "post"): "RunNextJobPayload",
            ("/api/grid-forecast/coverage", "get"): "GridForecastCoveragePayload",
            ("/api/sync_data", "post"): "AcceptedJobActionPayload",
            ("/api/fingrid/datasets", "get"): "FingridDatasetCatalogPayload",
            ("/api/finland/market-model", "get"): "FinlandMarketModelPayload",
            ("/api/years", "get"): "AvailableYearsPayload",
            ("/api/network-fees", "get"): "NetworkFeesPayload",
            ("/api/admin/external-api/billing-summary", "get"): "ExternalApiBillingSummaryPayload",
            ("/api/v1/developer/portal", "get"): "DeveloperPortalPayload",
        }

        for (route, method), model_name in route_expectations.items():
            route_schema = schema["paths"][route][method]["responses"]["200"]["content"]["application/json"]["schema"]["$ref"]
            self.assertIn(model_name, route_schema)
