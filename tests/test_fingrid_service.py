import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from fingrid.export import build_fingrid_csv
from fingrid.service import get_dataset_series_payload, get_dataset_summary_payload, sync_dataset


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

    def test_summary_and_day_aggregation_use_helsinki_time(self):
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
                "value": 10.0,
                "unit": "EUR/MW",
                "quality_flag": None,
                "source_updated_at": None,
                "ingested_at": "2026-04-23T00:00:00Z",
                "extra_json": {},
            },
            {
                "dataset_id": "317",
                "series_key": "fcrn_hourly_market_price",
                "timestamp_utc": "2026-01-01T01:00:00Z",
                "timestamp_local": "2026-01-01T03:00:00+02:00",
                "value": 14.0,
                "unit": "EUR/MW",
                "quality_flag": None,
                "source_updated_at": None,
                "ingested_at": "2026-04-23T00:00:00Z",
                "extra_json": {},
            },
        ])

        series_payload = get_dataset_series_payload(
            self.db,
            dataset_id="317",
            start="2026-01-01T00:00:00Z",
            end="2026-01-02T00:00:00Z",
            aggregation="day",
            tz="Europe/Helsinki",
            limit=5000,
        )
        summary_payload = get_dataset_summary_payload(
            self.db,
            dataset_id="317",
            start="2026-01-01T00:00:00Z",
            end="2026-01-02T00:00:00Z",
        )
        csv_text = build_fingrid_csv(series_payload["series"])

        self.assertEqual(series_payload["series"][0]["value"], 12.0)
        self.assertEqual(summary_payload["kpis"]["latest_value"], 14.0)
        self.assertEqual(summary_payload["kpis"]["avg_24h"], 12.0)
        self.assertEqual(csv_text.splitlines()[0], "timestamp,timestamp_utc,value,unit")
