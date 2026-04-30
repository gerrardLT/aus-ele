import os
import tempfile
import unittest
from unittest import mock
import json

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from job_framework import JobOrchestrator, JobRegistry
from lineage import build_job_lineage_payload, build_source_freshness_payload
from openlineage_support import build_openlineage_run_event, emit_openlineage_event
from storage_lake import LocalArtifactLake


class LineageTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.tmpdir = tempfile.TemporaryDirectory()
        self.lake = LocalArtifactLake(self.tmpdir.name)

    def tearDown(self):
        self.tmpdir.cleanup()
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_build_source_freshness_payload_reports_market_and_job_state(self):
        self.db.set_last_update_time("2026-04-27 12:00:00")

        payload = build_source_freshness_payload(self.db)

        self.assertIn("sources", payload)
        self.assertIn("job_summary", payload)
        self.assertEqual(payload["sources"][0]["source_key"], "market_core")

    def test_build_job_lineage_payload_exposes_job_trace_artifact_and_events(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok", "report_type": "monthly_market_report"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={"report_type": "monthly_market_report"},
            queue_name="reports",
            source_key="reporting",
        )
        orchestrator.run_once()

        payload = build_job_lineage_payload(self.db, job["job_id"])

        self.assertEqual(payload["job"]["job_id"], job["job_id"])
        self.assertEqual(payload["trace"]["trace_id"], f"job:{job['job_id']}")
        self.assertTrue(payload["artifacts"]["result_artifact_path"])
        self.assertGreaterEqual(len(payload["events"]), 3)
        self.assertIn("workspace_scope", payload["artifacts"])

    def test_build_job_lineage_payload_exposes_otel_trace_id_when_recorded(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={"report_type": "monthly_market_report"},
            queue_name="reports",
            source_key="reporting",
        )
        with mock.patch("job_framework.telemetry.get_current_trace_id", return_value="0123456789abcdef0123456789abcdef"), \
             mock.patch("job_framework.telemetry.start_span") as start_span:
            from contextlib import nullcontext
            start_span.return_value = nullcontext()
            orchestrator.run_once()

        payload = build_job_lineage_payload(self.db, job["job_id"])

        self.assertEqual(payload["trace"]["otel_trace_id"], "0123456789abcdef0123456789abcdef")

    def test_build_job_lineage_payload_exposes_parent_otel_trace_id_when_recorded(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={
                "report_type": "monthly_market_report",
                "_trace_context": {
                    "traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"
                },
            },
            queue_name="reports",
            source_key="reporting",
        )
        with mock.patch("job_framework.telemetry.extract_trace_context", return_value="parent-context"), \
             mock.patch("job_framework.telemetry.start_span") as start_span, \
             mock.patch("job_framework.telemetry.get_current_trace_id", return_value="fedcba9876543210fedcba9876543210"):
            from contextlib import nullcontext
            start_span.return_value = nullcontext()
            orchestrator.run_once()

        payload = build_job_lineage_payload(self.db, job["job_id"])

        self.assertEqual(
            payload["trace"]["parent_otel_trace_id"],
            "0123456789abcdef0123456789abcdef",
        )

    def test_build_openlineage_run_event_produces_run_event_shape(self):
        job = {
            "job_id": "job-1",
            "job_type": "report_generate",
            "queue_name": "reports",
            "source_key": "reporting",
            "organization_id": "org_1",
            "workspace_id": "ws_1",
            "payload_json": {},
        }

        event = build_openlineage_run_event(
            job,
            event_type="START",
            event_time="2026-04-28T00:00:00Z",
            producer="https://aus-ele.local/backend",
            otel_trace_id="0123456789abcdef0123456789abcdef",
        )

        self.assertEqual(event["eventType"], "START")
        self.assertEqual(event["run"]["runId"], "job-1")
        self.assertEqual(event["job"]["name"], "report_generate")
        self.assertEqual(event["job"]["namespace"], "aus-ele/reporting/reports")
        self.assertEqual(
            event["run"]["facets"]["processing_engine"]["name"],
            "aus-ele-job-orchestrator",
        )

    def test_build_job_lineage_payload_exposes_openlineage_events(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={"report_type": "monthly_market_report"},
            queue_name="reports",
            source_key="reporting",
        )
        with mock.patch("job_framework.openlineage_support._openlineage_enabled", return_value=True):
            orchestrator.run_once()

        payload = build_job_lineage_payload(self.db, job["job_id"])

        self.assertGreaterEqual(len(payload["openlineage"]["events"]), 2)
        self.assertEqual(payload["openlineage"]["events"][0]["run"]["runId"], job["job_id"])

    def test_emit_openlineage_event_can_write_jsonl_sink(self):
        event = build_openlineage_run_event(
            {
                "job_id": "job-2",
                "job_type": "market_sync",
                "queue_name": "sync",
                "source_key": "aemo",
            },
            event_type="START",
            event_time="2026-04-28T00:00:00Z",
        )
        output_path = os.path.join(self.tmpdir.name, "openlineage-events.jsonl")

        with mock.patch.dict(
            os.environ,
            {
                "AUS_ELE_OPENLINEAGE_ENABLED": "true",
                "AUS_ELE_OPENLINEAGE_SINK": "file",
                "AUS_ELE_OPENLINEAGE_FILE_PATH": output_path,
            },
            clear=False,
        ):
            emit_openlineage_event(event)

        with open(output_path, "r", encoding="utf-8") as handle:
            lines = [json.loads(line) for line in handle if line.strip()]
        self.assertEqual(len(lines), 1)
        self.assertEqual(lines[0]["run"]["runId"], "job-2")

    def test_emit_openlineage_event_can_post_http_sink(self):
        event = build_openlineage_run_event(
            {
                "job_id": "job-3",
                "job_type": "market_sync",
                "queue_name": "sync",
                "source_key": "aemo",
            },
            event_type="COMPLETE",
            event_time="2026-04-28T00:00:00Z",
        )

        response = mock.Mock()
        response.status_code = 202
        response.raise_for_status.return_value = None
        with mock.patch.dict(
            os.environ,
            {
                "AUS_ELE_OPENLINEAGE_ENABLED": "true",
                "AUS_ELE_OPENLINEAGE_SINK": "http",
                "AUS_ELE_OPENLINEAGE_ENDPOINT": "https://lineage.example/api/v1/lineage",
            },
            clear=False,
        ), mock.patch("openlineage_support.requests.post", return_value=response) as post, \
             mock.patch("openlineage_support.telemetry.build_trace_headers", return_value={"traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"}):
            result = emit_openlineage_event(event)

        self.assertTrue(result["emitted"])
        self.assertEqual(result["sink"], "http")
        post.assert_called_once()
        self.assertEqual(
            post.call_args.kwargs["headers"]["traceparent"],
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        )
