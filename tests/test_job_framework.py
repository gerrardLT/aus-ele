import os
import tempfile
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from job_framework import JobOrchestrator, JobRegistry
from storage_lake import LocalArtifactLake


class JobFrameworkTests(unittest.TestCase):
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

    def test_job_run_tracks_progress_audit_and_result_artifact(self):
        registry = JobRegistry()

        def handler(job, context):
            context.set_progress(45, "halfway")
            return {"status": "ok", "rows": 12}

        registry.register("report_generate", handler)
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={"report_type": "monthly_market_report"},
            queue_name="reports",
            source_key="reporting",
        )

        result = orchestrator.run_once()
        job_state = self.db.fetch_job(job["job_id"])
        events = self.db.list_job_events(job["job_id"])

        self.assertEqual(result["status"], "succeeded")
        self.assertEqual(job_state["status"], "succeeded")
        self.assertEqual(job_state["progress_pct"], 100)
        self.assertEqual(job_state["progress_message"], "completed")
        self.assertEqual(job_state["result_json"]["status"], "ok")
        self.assertTrue(job_state["artifact_path"])
        self.assertEqual([event["event_type"] for event in events], ["queued", "running", "progress", "succeeded"])

    def test_cancel_queued_job_marks_it_cancelled_before_execution(self):
        registry = JobRegistry()
        registry.register("fingrid_dataset_sync", lambda job, context: {"status": "unexpected"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "fingrid_dataset_sync",
            payload={"dataset_id": "319", "mode": "incremental"},
            queue_name="sync",
            source_key="fingrid",
        )

        self.assertTrue(self.db.cancel_job(job["job_id"]))
        self.assertIsNone(orchestrator.run_once())

        job_state = self.db.fetch_job(job["job_id"])
        events = self.db.list_job_events(job["job_id"])
        self.assertEqual(job_state["status"], "cancelled")
        self.assertEqual(events[-1]["event_type"], "cancelled")

    def test_retry_policy_requeues_then_succeeds(self):
        attempts = {"count": 0}
        registry = JobRegistry()

        def flaky_handler(job, context):
            attempts["count"] += 1
            if attempts["count"] == 1:
                raise RuntimeError("temporary upstream failure")
            return {"status": "ok", "attempts": attempts["count"]}

        registry.register("market_sync", flaky_handler)
        orchestrator = JobOrchestrator(
            self.db,
            registry=registry,
            lake=self.lake,
            worker_id="worker-1",
            retry_delays_seconds=[0, 0],
        )
        job = orchestrator.enqueue(
            "market_sync",
            payload={"manual": True},
            queue_name="sync",
            source_key="aemo",
            max_attempts=2,
        )

        first = orchestrator.run_once()
        second = orchestrator.run_once()
        job_state = self.db.fetch_job(job["job_id"])
        events = self.db.list_job_events(job["job_id"])

        self.assertEqual(first["status"], "retry_waiting")
        self.assertEqual(second["status"], "succeeded")
        self.assertEqual(job_state["status"], "succeeded")
        self.assertEqual(job_state["attempt_count"], 2)
        self.assertIn("retry_waiting", [event["event_type"] for event in events])

    def test_same_source_rate_limit_defers_second_job_without_blocking_other_source(self):
        registry = JobRegistry()
        registry.register("fingrid_dataset_sync", lambda job, context: {"status": "ok", "job_id": job["job_id"]})
        registry.register("report_generate", lambda job, context: {"status": "ok", "job_id": job["job_id"]})
        orchestrator = JobOrchestrator(
            self.db,
            registry=registry,
            lake=self.lake,
            worker_id="worker-1",
            source_rate_limits={"fingrid": 300},
        )

        first = orchestrator.enqueue("fingrid_dataset_sync", payload={"dataset_id": "317"}, queue_name="sync", source_key="fingrid")
        second = orchestrator.enqueue("fingrid_dataset_sync", payload={"dataset_id": "319"}, queue_name="sync", source_key="fingrid")
        third = orchestrator.enqueue("report_generate", payload={"report_type": "monthly_market_report"}, queue_name="reports", source_key="reporting")

        run1 = orchestrator.run_once()
        run2 = orchestrator.run_once()

        second_state = self.db.fetch_job(second["job_id"])
        third_state = self.db.fetch_job(third["job_id"])

        self.assertEqual(run1["job_id"], first["job_id"])
        self.assertEqual(run2["job_id"], third["job_id"])
        self.assertEqual(second_state["status"], "queued")
        self.assertEqual(third_state["status"], "succeeded")

    def test_run_once_can_be_restricted_to_specific_queue_names(self):
        registry = JobRegistry()
        registry.register("fingrid_dataset_sync", lambda job, context: {"status": "ok", "job_id": job["job_id"]})
        registry.register("report_generate", lambda job, context: {"status": "ok", "job_id": job["job_id"]})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")

        sync_job = orchestrator.enqueue("fingrid_dataset_sync", payload={"dataset_id": "317"}, queue_name="sync", source_key="fingrid")
        report_job = orchestrator.enqueue("report_generate", payload={"report_type": "monthly_market_report"}, queue_name="reports", source_key="reporting")

        result = orchestrator.run_once(queue_names=["reports"])

        self.assertEqual(result["job_id"], report_job["job_id"])
        self.assertEqual(self.db.fetch_job(sync_job["job_id"])["status"], "queued")
        self.assertEqual(self.db.fetch_job(report_job["job_id"])["status"], "succeeded")

    def test_run_once_scoped_can_combine_workspace_scope_and_queue_filter(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok", "job_id": job["job_id"]})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")

        wrong_queue = orchestrator.enqueue(
            "report_generate",
            payload={"workspace_id": "ws-1", "organization_id": "org-1"},
            queue_name="sync",
            source_key="reporting",
        )
        right_queue = orchestrator.enqueue(
            "report_generate",
            payload={"workspace_id": "ws-1", "organization_id": "org-1"},
            queue_name="reports",
            source_key="reporting",
        )

        result = orchestrator.run_once_scoped(
            organization_id="org-1",
            workspace_id="ws-1",
            queue_names=["reports"],
        )

        self.assertEqual(result["job_id"], right_queue["job_id"])
        self.assertEqual(self.db.fetch_job(wrong_queue["job_id"])["status"], "queued")
        self.assertEqual(self.db.fetch_job(right_queue["job_id"])["status"], "succeeded")

    def test_job_artifact_path_is_partitioned_by_workspace_scope(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok", "job_id": job["job_id"]})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={
                "report_type": "monthly_market_report",
                "workspace_id": "ws_scope",
                "organization_id": "org_scope",
            },
            queue_name="reports",
            source_key="reporting",
        )

        orchestrator.run_once()
        job_state = self.db.fetch_job(job["job_id"])

        self.assertIn("workspace=ws_scope", job_state["artifact_path"])

    def test_job_run_records_otel_trace_id_when_available(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        job = orchestrator.enqueue(
            "report_generate",
            payload={"report_type": "monthly_market_report"},
            queue_name="reports",
            source_key="reporting",
        )

        with mock.patch("job_framework.telemetry.get_current_trace_id", return_value="oteltrace1234abcdefoteltrace1234ab"), \
             mock.patch("job_framework.telemetry.start_span") as start_span:
            from contextlib import nullcontext
            start_span.return_value = nullcontext()
            orchestrator.run_once()

        events = self.db.list_job_events(job["job_id"])
        succeeded = [event for event in events if event["event_type"] == "succeeded"][0]
        self.assertEqual(
            succeeded["detail_json"]["otel_trace_id"],
            "oteltrace1234abcdefoteltrace1234ab",
        )

    def test_enqueue_captures_current_trace_context_in_payload(self):
        registry = JobRegistry()
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")

        with mock.patch(
            "job_framework.telemetry.serialize_current_trace_context",
            return_value={"traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"},
        ):
            job = orchestrator.enqueue(
                "report_generate",
                payload={"report_type": "monthly_market_report"},
                queue_name="reports",
                source_key="reporting",
            )

        self.assertEqual(
            job["payload_json"]["_trace_context"]["traceparent"],
            "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01",
        )

    def test_job_run_restores_parent_trace_context_for_span(self):
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

        with mock.patch("job_framework.telemetry.extract_trace_context", return_value="parent-context") as extract_trace_context, \
             mock.patch("job_framework.telemetry.start_span") as start_span, \
             mock.patch("job_framework.telemetry.get_current_trace_id", return_value="fedcba9876543210fedcba9876543210"):
            from contextlib import nullcontext
            start_span.return_value = nullcontext()
            orchestrator.run_once()

        extract_trace_context.assert_called_once_with(
            {"traceparent": "00-0123456789abcdef0123456789abcdef-0123456789abcdef-01"}
        )
        start_span.assert_called_once()
        self.assertEqual(start_span.call_args.kwargs["parent_context"], "parent-context")
        events = self.db.list_job_events(job["job_id"])
        running = [event for event in events if event["event_type"] == "running"][0]
        self.assertEqual(
            running["detail_json"]["parent_otel_trace_id"],
            "0123456789abcdef0123456789abcdef",
        )

    def test_job_run_records_success_metric(self):
        registry = JobRegistry()
        registry.register("report_generate", lambda job, context: {"status": "ok"})
        orchestrator = JobOrchestrator(self.db, registry=registry, lake=self.lake, worker_id="worker-1")
        orchestrator.enqueue(
            "report_generate",
            payload={"report_type": "monthly_market_report"},
            queue_name="reports",
            source_key="reporting",
        )

        with mock.patch("job_framework.telemetry.record_job_metric") as record_job_metric:
            orchestrator.run_once()

        record_job_metric.assert_called_once_with(job_type="report_generate", status="succeeded")

    def test_job_run_records_retry_waiting_metric(self):
        registry = JobRegistry()

        def flaky_handler(job, context):
            raise RuntimeError("temporary upstream failure")

        registry.register("market_sync", flaky_handler)
        orchestrator = JobOrchestrator(
            self.db,
            registry=registry,
            lake=self.lake,
            worker_id="worker-1",
            retry_delays_seconds=[0],
        )
        orchestrator.enqueue(
            "market_sync",
            payload={"manual": True},
            queue_name="sync",
            source_key="aemo",
            max_attempts=2,
        )

        with mock.patch("job_framework.telemetry.record_job_metric") as record_job_metric:
            orchestrator.run_once()

        record_job_metric.assert_called_once_with(job_type="market_sync", status="retry_waiting")

    def test_job_run_records_failed_metric(self):
        registry = JobRegistry()

        def failing_handler(job, context):
            raise RuntimeError("permanent upstream failure")

        registry.register("market_sync", failing_handler)
        orchestrator = JobOrchestrator(
            self.db,
            registry=registry,
            lake=self.lake,
            worker_id="worker-1",
            retry_delays_seconds=[0],
        )
        orchestrator.enqueue(
            "market_sync",
            payload={"manual": True},
            queue_name="sync",
            source_key="aemo",
            max_attempts=1,
        )

        with mock.patch("job_framework.telemetry.record_job_metric") as record_job_metric:
            orchestrator.run_once()

        record_job_metric.assert_called_once_with(job_type="market_sync", status="failed")
