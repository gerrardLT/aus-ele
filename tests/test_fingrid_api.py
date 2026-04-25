import os
import inspect
import tempfile
import unittest
from unittest import mock

from fastapi import BackgroundTasks

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server


class FingridApiTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        server.db = self.db

    def tearDown(self):
        server.db = self.original_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_dataset_list_and_status_return_payloads(self):
        with mock.patch("server.fingrid_service.seed_dataset_catalog") as seed_catalog:
            seed_catalog.side_effect = lambda db: None
            with mock.patch("server.fingrid_catalog.list_dataset_configs", return_value=[{"dataset_id": "317"}]):
                datasets = server.get_fingrid_datasets()

        self.assertEqual(datasets["datasets"][0]["dataset_id"], "317")

    @mock.patch("server.fingrid_service.sync_dataset")
    def test_manual_sync_route_queues_background_job(self, mock_sync):
        tasks = BackgroundTasks()
        response = server.sync_fingrid_dataset("317", tasks, mode="incremental")

        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["dataset_id"], "317")
        self.assertEqual(len(tasks.tasks), 1)

    def test_series_route_uses_no_default_limit_when_query_param_is_missing(self):
        signature = inspect.signature(server.get_fingrid_dataset_series)
        self.assertIsNone(signature.parameters["limit"].default.default)

    def test_export_route_uses_no_default_limit_when_query_param_is_missing(self):
        signature = inspect.signature(server.export_fingrid_dataset_csv)
        self.assertIsNone(signature.parameters["limit"].default.default)

    @mock.patch("server.os.environ", {"FINGRID_API_KEY": "test-key"})
    @mock.patch("server.fingrid_service.sync_dataset")
    @mock.patch("server.fingrid_catalog.list_dataset_configs", return_value=[{"dataset_id": "317"}])
    def test_run_fingrid_hourly_sync_runs_incremental_sync_for_supported_datasets(
        self,
        mock_list_configs,
        mock_sync_dataset,
    ):
        result = server.run_fingrid_hourly_sync()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["datasets_synced"], 1)
        mock_sync_dataset.assert_called_once_with(self.db, dataset_id="317", mode="incremental")

    @mock.patch("server.fingrid_service.sync_dataset")
    def test_run_fingrid_hourly_sync_skips_when_api_key_is_missing(self, mock_sync_dataset):
        with mock.patch.dict("server.os.environ", {}, clear=True):
            result = server.run_fingrid_hourly_sync()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_api_key")
        mock_sync_dataset.assert_not_called()
