import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager


class FingridStorageTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_fingrid_tables_store_catalog_series_and_sync_state(self):
        self.db.upsert_fingrid_dataset_catalog([
            {
                "dataset_id": "317",
                "dataset_code": "fcrn_hourly_market_price",
                "name": "FCR-N hourly market prices",
                "description": "FCR-N hourly reserve-capacity market price in Finland.",
                "unit": "EUR/MW",
                "frequency": "1h",
                "timezone": "Europe/Helsinki",
                "value_kind": "reserve_capacity_price",
                "source_url": "https://data.fingrid.fi/en/datasets/317",
                "enabled": 1,
                "metadata_json": {"market": "Fingrid", "product": "FCR-N"},
                "updated_at": "2026-04-23T00:00:00Z",
            }
        ])
        self.db.upsert_fingrid_timeseries([
            {
                "dataset_id": "317",
                "series_key": "fcrn_hourly_market_price",
                "timestamp_utc": "2026-01-01T00:00:00Z",
                "timestamp_local": "2026-01-01T02:00:00+02:00",
                "value": 12.5,
                "unit": "EUR/MW",
                "quality_flag": None,
                "source_updated_at": "2026-01-01T00:05:00Z",
                "ingested_at": "2026-04-23T00:00:00Z",
                "extra_json": {},
            },
            {
                "dataset_id": "317",
                "series_key": "fcrn_hourly_market_price",
                "timestamp_utc": "2026-01-01T01:00:00Z",
                "timestamp_local": "2026-01-01T03:00:00+02:00",
                "value": 13.5,
                "unit": "EUR/MW",
                "quality_flag": None,
                "source_updated_at": "2026-01-01T01:05:00Z",
                "ingested_at": "2026-04-23T00:00:00Z",
                "extra_json": {},
            },
        ])
        self.db.upsert_fingrid_sync_state(
            dataset_id="317",
            last_success_at="2026-04-23T00:10:00Z",
            last_attempt_at="2026-04-23T00:10:00Z",
            last_cursor="2026-01-01T01:00:00Z",
            last_synced_timestamp_utc="2026-01-01T01:00:00Z",
            sync_status="ok",
            last_error=None,
            backfill_started_at="2026-04-22T00:00:00Z",
            backfill_completed_at="2026-04-23T00:10:00Z",
        )

        datasets = self.db.fetch_fingrid_dataset_catalog()
        series = self.db.fetch_fingrid_series(dataset_id="317")
        status = self.db.fetch_fingrid_sync_state("317")
        coverage = self.db.fetch_fingrid_dataset_coverage("317")

        self.assertEqual(datasets[0]["dataset_id"], "317")
        self.assertEqual(series[0]["timestamp_utc"], "2026-01-01T00:00:00Z")
        self.assertEqual(status["sync_status"], "ok")
        self.assertEqual(coverage["record_count"], 2)
        self.assertEqual(coverage["coverage_start_utc"], "2026-01-01T00:00:00Z")
        self.assertEqual(coverage["coverage_end_utc"], "2026-01-01T01:00:00Z")
