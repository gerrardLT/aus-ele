import os
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
