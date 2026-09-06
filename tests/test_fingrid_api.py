import os
import inspect
import sys
import tempfile
import unittest
import zipfile
import io
import xml.etree.ElementTree as ET
from unittest import mock

from fastapi import BackgroundTasks, HTTPException

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
            with mock.patch(
                "server.fingrid_catalog.list_dataset_configs",
                return_value=[{"dataset_id": "317"}, {"dataset_id": "319"}],
            ):
                datasets = server.get_fingrid_datasets()

        self.assertEqual(datasets["datasets"][0]["dataset_id"], "317")
        self.assertEqual(datasets["datasets"][1]["dataset_id"], "319")

    def test_finland_market_model_route_returns_multi_source_payload(self):
        with mock.patch(
            "server.build_finland_market_model_payload",
            return_value={
                "country": "Finland",
                "market": "Finland",
                "model_status": "partial-live",
                "sources": [
                    {"source_key": "fingrid", "status": "live"},
                    {"source_key": "nord_pool", "status": "planned"},
                    {"source_key": "entsoe", "status": "planned"},
                ],
                "summary": {"live_dataset_count": 2},
                "metadata": {"market": "FINLAND"},
            },
        ):
            payload = server.get_finland_market_model()

        self.assertEqual(payload["country"], "Finland")
        self.assertEqual(payload["sources"][0]["source_key"], "fingrid")
        self.assertEqual(payload["summary"]["live_dataset_count"], 2)

    def test_load_env_file_populates_process_environment(self):
        handle, env_path = tempfile.mkstemp(suffix=".env")
        os.close(handle)
        try:
            with open(env_path, "w", encoding="utf-8") as env_file:
                env_file.write("FINGRID_API_KEY=test-from-env-file\n")

            with mock.patch.dict("server.os.environ", {}, clear=True):
                loaded_path = server._load_env_file(env_path)
                self.assertEqual(server.os.environ.get("FINGRID_API_KEY"), "test-from-env-file")

            self.assertEqual(str(loaded_path), env_path)
        finally:
            if os.path.exists(env_path):
                os.remove(env_path)

    @mock.patch("server.fingrid_service.sync_dataset")
    def test_manual_sync_route_queues_background_job(self, mock_sync):
        tasks = BackgroundTasks()
        with mock.patch.dict("server.os.environ", {"FINGRID_API_KEY": "test-key"}, clear=True):
            with mock.patch("server._try_acquire_job_lock", return_value=True, create=True):
                response = server.sync_fingrid_dataset("317", tasks, mode="incremental")

        self.assertEqual(response["status"], "accepted")
        self.assertEqual(response["dataset_id"], "317")
        self.assertEqual(len(tasks.tasks), 1)

    def test_manual_sync_route_rejects_when_market_sync_is_already_running(self):
        tasks = BackgroundTasks()

        with mock.patch("server._try_acquire_job_lock", return_value=False, create=True):
            with self.assertRaises(HTTPException) as ctx:
                server.sync_data(tasks)

        self.assertEqual(ctx.exception.status_code, 409)

    def test_manual_fingrid_sync_route_rejects_when_api_key_is_missing(self):
        tasks = BackgroundTasks()

        with mock.patch.dict("server.os.environ", {}, clear=True):
            with self.assertRaises(HTTPException) as ctx:
                server.sync_fingrid_dataset("317", tasks, mode="incremental")

        self.assertEqual(ctx.exception.status_code, 503)

    def test_run_sync_scrapers_uses_current_python_and_absolute_script_paths(self):
        with mock.patch("server.subprocess.run") as mock_run:
            server.run_sync_scrapers()

        self.assertEqual(mock_run.call_count, 4)

        commands = [call.args[0] for call in mock_run.call_args_list]
        for command in commands:
            self.assertEqual(command[0], sys.executable)
            self.assertTrue(os.path.isabs(command[1]))

        # PG 迁移后不再传 --db / --db-path：子进程靠 AUS_ELE_PG_* 环境变量连库，而 SQLite
        # 时代的 ``server.DB_PATH`` 全局已随迁移删除。这里显式断言「没有 --db」，是为了让
        # 「顺手加回去」这种回退在测试里当场失败，而不是悄悄把同步任务指回一个空库文件。
        for command in commands:
            self.assertNotIn("--db", command)
            self.assertNotIn("--db-path", command)
        self.assertIn("--start", commands[0])
        self.assertIn("--end", commands[0])
        self.assertIn("--days", commands[1])
        self.assertIn("--fcas", commands[2])
        self.assertIn("--days", commands[3])

    def test_database_system_lock_blocks_second_owner_until_release(self):
        self.assertTrue(self.db.acquire_system_lock("job:test", owner="one", ttl_seconds=60))
        self.assertFalse(self.db.acquire_system_lock("job:test", owner="two", ttl_seconds=60))
        self.assertTrue(self.db.release_system_lock("job:test", owner="one"))
        self.assertTrue(self.db.acquire_system_lock("job:test", owner="two", ttl_seconds=60))

    def test_series_route_uses_no_default_limit_when_query_param_is_missing(self):
        signature = inspect.signature(server.get_fingrid_dataset_series)
        self.assertIsNone(signature.parameters["limit"].default.default)

    def test_export_route_uses_no_default_limit_when_query_param_is_missing(self):
        signature = inspect.signature(server.export_fingrid_dataset_csv)
        self.assertIsNone(signature.parameters["limit"].default.default)

    def test_all_markets_export_route_uses_no_default_limit_when_query_param_is_missing(self):
        signature = inspect.signature(server.export_all_fingrid_datasets_csv)
        self.assertIsNone(signature.parameters["limit"].default.default)

    def test_all_markets_export_route_builds_xlsx_with_one_sheet_per_dataset(self):
        payloads = {
            "317": {
                "dataset": {
                    "dataset_id": "317",
                    "name": "FCR-N hourly market prices",
                    "unit": "EUR/MW",
                    "metadata_json": {"product": "FCR-N", "signal": "capacity_price"},
                },
                "series": [
                    {
                        "timestamp": "2026-01-01T00:00:00+02:00",
                        "timestamp_utc": "2025-12-31T22:00:00Z",
                        "bucket_start": "2026-01-01T00:00:00+02:00",
                        "bucket_end": "2026-01-01T01:00:00+02:00",
                        "value": 12.3,
                        "avg_value": 12.3,
                        "peak_value": 12.3,
                        "trough_value": 12.3,
                        "sample_count": 1,
                        "unit": "EUR/MW",
                    }
                ],
            },
            "319": {
                "dataset": {
                    "dataset_id": "319",
                    "name": "Imbalance price",
                    "unit": "EUR/MWh",
                    "metadata_json": {"product": "Imbalance", "signal": "settlement_price"},
                },
                "series": [
                    {
                        "timestamp": "2026-01-01T00:00:00+02:00",
                        "timestamp_utc": "2025-12-31T22:00:00Z",
                        "bucket_start": "2026-01-01T00:00:00+02:00",
                        "bucket_end": "2026-01-01T01:00:00+02:00",
                        "value": 101.2,
                        "avg_value": 101.2,
                        "peak_value": 101.2,
                        "trough_value": 101.2,
                        "sample_count": 1,
                        "unit": "EUR/MWh",
                    }
                ],
            },
        }

        with mock.patch(
            "server.fingrid_catalog.list_dataset_configs",
            return_value=[{"dataset_id": "317"}, {"dataset_id": "319"}],
        ):
            with mock.patch(
                "server.fingrid_service.get_dataset_series_payload",
                side_effect=lambda *args, **kwargs: payloads[kwargs["dataset_id"]],
            ):
                response = server.export_all_fingrid_datasets_csv(
                    start="2026-01-01T00:00:00Z",
                    end="2026-01-02T00:00:00Z",
                    aggregation="day",
                )

        self.assertEqual(
            response.media_type,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertIn('attachment; filename="fingrid-all-markets.xlsx"', response.headers["Content-Disposition"])

        archive = zipfile.ZipFile(io.BytesIO(response.body))
        workbook_xml = archive.read("xl/workbook.xml")
        root = ET.fromstring(workbook_xml)
        ns = {"main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
        sheet_names = [sheet.attrib["name"] for sheet in root.findall("main:sheets/main:sheet", ns)]

        self.assertEqual(sheet_names, ["317_FCR-N", "319_Imbalance"])

    def test_fingrid_status_route_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_fingrid_dataset_status("317", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_fingrid_series_route_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_fingrid_dataset_series("317", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_fingrid_summary_route_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_fingrid_dataset_summary("317", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_cors_defaults_to_localhost_origins_without_credentials(self):
        with mock.patch.dict("server.os.environ", {}, clear=True):
            self.assertEqual(
                server._cors_allow_origins(),
                ["http://127.0.0.1:5173", "http://localhost:5173"],
            )
            self.assertFalse(server._cors_allow_credentials())

    def test_cors_parses_explicit_origins_and_credentials_flag(self):
        with mock.patch.dict(
            "server.os.environ",
            {
                "AUS_ELE_CORS_ALLOW_ORIGINS": "https://example.com, https://app.example.com ",
                "AUS_ELE_CORS_ALLOW_CREDENTIALS": "true",
            },
            clear=True,
        ):
            self.assertEqual(
                server._cors_allow_origins(),
                ["https://example.com", "https://app.example.com"],
            )
            self.assertTrue(server._cors_allow_credentials())

    @mock.patch("server.os.environ", {"FINGRID_API_KEY": "test-key"})
    @mock.patch("server.fingrid_service.sync_dataset")
    def test_run_fingrid_hourly_sync_runs_incremental_sync_for_supported_datasets(
        self,
        mock_sync_dataset,
    ):
        result = server.run_fingrid_hourly_sync()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["datasets_synced"], len(server.FINGRID_HOURLY_DATASET_IDS))
        called_dataset_ids = [call.kwargs["dataset_id"] for call in mock_sync_dataset.call_args_list]
        self.assertEqual(called_dataset_ids, list(server.FINGRID_HOURLY_DATASET_IDS))

    @mock.patch("server.fingrid_service.sync_dataset")
    def test_run_fingrid_hourly_sync_skips_when_api_key_is_missing(self, mock_sync_dataset):
        with mock.patch.dict("server.os.environ", {}, clear=True):
            result = server.run_fingrid_hourly_sync()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_api_key")
        mock_sync_dataset.assert_not_called()

    @mock.patch("server.os.environ", {"FINGRID_API_KEY": "test-key"})
    @mock.patch("server.fingrid_service.sync_dataset", side_effect=RuntimeError("403 blocked by upstream"))
    def test_run_fingrid_dataset_sync_returns_structured_error_when_background_sync_fails(self, mock_sync_dataset):
        result = server.run_fingrid_dataset_sync("317", "incremental", lock_pre_acquired=True)

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["dataset_id"], "317")
        self.assertIn("403 blocked by upstream", result["detail"])
        mock_sync_dataset.assert_called_once_with(self.db, dataset_id="317", mode="incremental")

    @mock.patch("server.os.environ", {"FINGRID_API_KEY": "test-key"})
    @mock.patch("server.fingrid_service.sync_dataset", side_effect=RuntimeError("403 blocked by upstream"))
    def test_run_fingrid_hourly_sync_returns_structured_error_when_background_sync_fails(
        self,
        mock_sync_dataset,
    ):
        result = server.run_fingrid_hourly_sync()

        self.assertEqual(result["status"], "error")
        self.assertEqual(result["datasets_synced"], 0)
        self.assertIn("403 blocked by upstream", result["detail"])
        self.assertEqual(mock_sync_dataset.call_count, len(server.FINGRID_HOURLY_DATASET_IDS))

    @mock.patch("server.os.environ", {"FINGRID_API_KEY": "test-key"})
    @mock.patch("server.fingrid_service.sync_dataset")
    def test_run_fingrid_daily_sync_runs_incremental_sync_for_yearly_datasets(self, mock_sync_dataset):
        result = server.run_fingrid_daily_sync()

        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["datasets_synced"], len(server.FINGRID_DAILY_DATASET_IDS))
        called_dataset_ids = [call.kwargs["dataset_id"] for call in mock_sync_dataset.call_args_list]
        self.assertEqual(called_dataset_ids, list(server.FINGRID_DAILY_DATASET_IDS))

    @mock.patch("server.fingrid_service.sync_dataset")
    def test_run_fingrid_daily_sync_skips_when_api_key_is_missing(self, mock_sync_dataset):
        with mock.patch.dict("server.os.environ", {}, clear=True):
            result = server.run_fingrid_daily_sync()

        self.assertEqual(result["status"], "skipped")
        self.assertEqual(result["reason"], "missing_api_key")
        mock_sync_dataset.assert_not_called()
