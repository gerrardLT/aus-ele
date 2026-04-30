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


class JobQueueRouteTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_orchestrator_db = server.job_orchestrator.db
        server.db = self.db
        server.job_orchestrator.db = self.db

    def tearDown(self):
        server.db = self.original_db
        server.job_orchestrator.db = self.original_orchestrator_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_sync_data_route_enqueues_market_sync_job(self):
        response = server.sync_data()

        self.assertEqual(response["status"], "accepted")
        self.assertTrue(response["job_id"])
        job = self.db.fetch_job(response["job_id"])
        self.assertEqual(job["job_type"], "market_sync")
        self.assertEqual(job["status"], "queued")

    def test_fingrid_sync_route_enqueues_job(self):
        with mock.patch.dict("server.os.environ", {"FINGRID_API_KEY": "test-key"}, clear=True):
            response = server.sync_fingrid_dataset("317", mode="incremental")

        self.assertEqual(response["status"], "accepted")
        job = self.db.fetch_job(response["job_id"])
        self.assertEqual(job["job_type"], "fingrid_dataset_sync")
        self.assertEqual(job["payload_json"]["dataset_id"], "317")

    def test_job_routes_support_list_cancel_and_retry(self):
        created = server.create_job_route(
            server.JobCreateRequest(
                job_type="report_generate",
                queue_name="reports",
                source_key="reporting",
                payload={"report_type": "monthly_market_report", "year": 2025, "region": "NSW1"},
            )
        )

        listed = server.list_jobs_route(status=None, queue_name=None, limit=100)
        self.assertEqual(len(listed["items"]), 1)

        job_id = created["job_id"]
        self.assertEqual(server.get_job_route(job_id)["job_id"], job_id)

        cancel_response = server.cancel_job_route(job_id)
        self.assertEqual(cancel_response["status"], "accepted")
        self.assertEqual(self.db.fetch_job(job_id)["status"], "cancelled")

        retry_response = server.retry_job_route(job_id)
        self.assertEqual(retry_response["status"], "accepted")
        self.assertEqual(self.db.fetch_job(job_id)["status"], "queued")

    def test_run_next_job_route_can_be_scoped_to_workspace(self):
        org = server.create_organization_route(name="Acme")
        workspace_a = server.create_workspace_route(organization_id=org["organization_id"], name="A")
        workspace_b = server.create_workspace_route(organization_id=org["organization_id"], name="B")

        job_a = server.create_job_route(
            server.JobCreateRequest(
                job_type="report_generate",
                queue_name="reports",
                source_key="reporting",
                payload={"report_type": "monthly_market_report", "workspace_id": workspace_a["workspace_id"], "organization_id": org["organization_id"]},
            )
        )
        server.create_job_route(
            server.JobCreateRequest(
                job_type="report_generate",
                queue_name="reports",
                source_key="reporting",
                payload={"report_type": "monthly_market_report", "workspace_id": workspace_b["workspace_id"], "organization_id": org["organization_id"]},
            )
        )

        result = server.run_next_job_route(
            access_scope={"organization_id": org["organization_id"], "workspace_id": workspace_a["workspace_id"]}
        )

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["job_id"], job_a["job_id"])

    def test_run_next_job_route_can_be_filtered_by_queue_names(self):
        sync_job = server.create_job_route(
            server.JobCreateRequest(
                job_type="market_sync",
                queue_name="sync",
                source_key="aemo",
                payload={"manual": True},
            )
        )
        report_job = server.create_job_route(
            server.JobCreateRequest(
                job_type="report_generate",
                queue_name="reports",
                source_key="reporting",
                payload={"report_type": "monthly_market_report", "year": 2025, "region": "NSW1"},
            )
        )

        result = server.run_next_job_route(queue_names="reports")

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["result"]["job_id"], report_job["job_id"])
        self.assertEqual(self.db.fetch_job(sync_job["job_id"])["status"], "queued")

    def test_job_worker_queue_names_can_be_parsed_from_env(self):
        with mock.patch.dict("server.os.environ", {"AUS_ELE_JOB_WORKER_QUEUES": "sync,reports , backtests"}, clear=False):
            self.assertEqual(server._job_worker_queue_names(), ["sync", "reports", "backtests"])

    def test_job_worker_service_forwards_queue_names_to_orchestrator(self):
        orchestrator = mock.Mock()
        orchestrator.run_once.return_value = None
        worker = server.JobWorkerService(orchestrator, queue_names=["reports"])
        worker.stop_event = mock.Mock()
        worker.stop_event.is_set.side_effect = [False, True]
        worker.stop_event.wait.return_value = None

        worker._run_loop()

        orchestrator.run_once.assert_called_once_with(queue_names=["reports"])
