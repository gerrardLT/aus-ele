import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from fingrid.service import sync_dataset


class FakeFingridClient:
    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    def fetch_dataset_window(
        self,
        dataset_id: str,
        *,
        start_time_utc: str,
        end_time_utc: str,
        page_size: int = 20000,
        locale: str = "en",
    ) -> list[dict]:
        self.calls.append((dataset_id, start_time_utc, end_time_utc, page_size, locale))
        return self.payloads.pop(0)


class FingridServiceSyncTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_backfill_sync_writes_rows_and_state(self):
        client = FakeFingridClient([
            [
                {
                    "startTime": "2026-01-01T00:00:00Z",
                    "endTime": "2026-01-01T01:00:00Z",
                    "value": 11.0,
                },
                {
                    "startTime": "2026-01-01T01:00:00Z",
                    "endTime": "2026-01-01T02:00:00Z",
                    "value": 12.0,
                },
            ]
        ])

        result = sync_dataset(
            self.db,
            dataset_id="317",
            mode="backfill",
            start="2026-01-01T00:00:00Z",
            end="2026-01-31T00:00:00Z",
            client=client,
            ingested_at="2026-04-23T00:00:00Z",
        )

        self.assertEqual(result["records_upserted"], 2)
        self.assertEqual(result["windows_synced"], 1)
        status = self.db.fetch_fingrid_sync_state("317")
        self.assertEqual(status["sync_status"], "ok")
        self.assertEqual(status["last_synced_timestamp_utc"], "2026-01-01T01:00:00Z")
