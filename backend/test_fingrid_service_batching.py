import os
import sys
import unittest
from datetime import datetime, timezone

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from backend.fingrid import service as fingrid_service


class _FakeDb:
    def __init__(self):
        self.upsert_batch_sizes = []

    def fetch_fingrid_sync_state(self, dataset_id):
        return {}

    def upsert_fingrid_sync_state(self, **kwargs):
        return None

    def upsert_fingrid_timeseries(self, records):
        self.upsert_batch_sizes.append(len(records))
        return len(records)

    def upsert_fingrid_dataset_catalog(self, records):
        return len(records)


class _FakeClient:
    def __init__(self, rows):
        self.rows = rows

    def fetch_dataset_window(self, dataset_id, **kwargs):
        return list(self.rows)


class FingridServiceBatchingTests(unittest.TestCase):
    def test_sync_dataset_upserts_large_windows_in_batches(self):
        fake_db = _FakeDb()
        raw_rows = [
            {
                "startTime": f"2025-01-01T{index % 24:02d}:00:00Z",
                "endTime": f"2025-01-01T{(index + 1) % 24:02d}:00:00Z",
                "value": index,
                "updatedAt": "2025-01-02T00:00:00Z",
            }
            for index in range(2505)
        ]

        original_get_dataset_config = fingrid_service.get_dataset_config
        original_seed_dataset_catalog = fingrid_service.seed_dataset_catalog
        try:
            fingrid_service.get_dataset_config = lambda dataset_id: {
                "dataset_id": dataset_id,
                "series_key": "test-series",
                "timezone": "UTC",
                "unit": "MW",
                "default_backfill_start": "2025-01-01T00:00:00Z",
                "default_incremental_lookback_days": 30,
            }
            fingrid_service.seed_dataset_catalog = lambda db: None

            result = fingrid_service.sync_dataset(
                fake_db,
                dataset_id="317",
                mode="incremental",
                start="2025-01-01T00:00:00Z",
                end="2025-01-15T00:00:00Z",
                client=_FakeClient(raw_rows),
                ingested_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            )
        finally:
            fingrid_service.get_dataset_config = original_get_dataset_config
            fingrid_service.seed_dataset_catalog = original_seed_dataset_catalog

        self.assertEqual(result["records_upserted"], 2505)
        self.assertEqual(fake_db.upsert_batch_sizes, [1000, 1000, 505])


if __name__ == "__main__":
    unittest.main()
