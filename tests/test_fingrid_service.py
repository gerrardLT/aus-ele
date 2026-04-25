import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone

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
        self.assertEqual(
            csv_text.splitlines()[0],
            "timestamp,timestamp_utc,bucket_start,bucket_end,value,avg_value,peak_value,trough_value,sample_count,unit",
        )

    def test_day_aggregation_applies_limit_after_aggregation(self):
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

        start_utc = datetime(2025, 1, 1, tzinfo=timezone.utc)
        hours = 24 * 300
        records = []
        for offset in range(hours):
            point_utc = start_utc + timedelta(hours=offset)
            local_time = point_utc.astimezone(timezone(timedelta(hours=2)))
            records.append(
                {
                    "dataset_id": "317",
                    "series_key": "fcrn_hourly_market_price",
                    "timestamp_utc": point_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "timestamp_local": local_time.isoformat(),
                    "value": float(offset % 24),
                    "unit": "EUR/MW",
                    "quality_flag": None,
                    "source_updated_at": None,
                    "ingested_at": "2026-04-23T00:00:00Z",
                    "extra_json": {},
                }
            )
        self.db.upsert_fingrid_timeseries(records)

        payload = get_dataset_series_payload(
            self.db,
            dataset_id="317",
            start="2025-01-01T00:00:00Z",
            end="2025-10-28T23:00:00Z",
            aggregation="day",
            tz="Europe/Helsinki",
            limit=5000,
        )

        self.assertEqual(len(payload["series"]), 301)
        self.assertEqual(payload["series"][0]["timestamp"], "2025-01-01T00:00:00+02:00")
        self.assertEqual(payload["series"][-1]["timestamp"], "2025-10-28T00:00:00+02:00")

    def test_raw_series_exposes_hour_interval_boundaries(self):
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
                "updated_at": "2026-04-24T00:00:00Z",
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
                "ingested_at": "2026-04-24T00:00:00Z",
                "extra_json": {},
            }
        ])

        payload = get_dataset_series_payload(
            self.db,
            dataset_id="317",
            start="2026-01-01T00:00:00Z",
            end="2026-01-01T01:00:00Z",
            aggregation="raw",
            tz="Europe/Helsinki",
            limit=5000,
        )

        row = payload["series"][0]
        self.assertEqual(row["bucket_start"], "2026-01-01T02:00:00+02:00")
        self.assertEqual(row["bucket_end"], "2026-01-01T03:00:00+02:00")
        self.assertEqual(row["avg_value"], 10.0)
        self.assertEqual(row["peak_value"], 10.0)
        self.assertEqual(row["trough_value"], 10.0)
        self.assertEqual(row["sample_count"], 1)

    def test_two_hour_aggregation_uses_local_bucket_boundaries(self):
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
                "updated_at": "2026-04-24T00:00:00Z",
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
                "ingested_at": "2026-04-24T00:00:00Z",
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
                "ingested_at": "2026-04-24T00:00:00Z",
                "extra_json": {},
            },
            {
                "dataset_id": "317",
                "series_key": "fcrn_hourly_market_price",
                "timestamp_utc": "2026-01-01T02:00:00Z",
                "timestamp_local": "2026-01-01T04:00:00+02:00",
                "value": 18.0,
                "unit": "EUR/MW",
                "quality_flag": None,
                "source_updated_at": None,
                "ingested_at": "2026-04-24T00:00:00Z",
                "extra_json": {},
            },
        ])

        payload = get_dataset_series_payload(
            self.db,
            dataset_id="317",
            start="2026-01-01T00:00:00Z",
            end="2026-01-01T03:00:00Z",
            aggregation="2h",
            tz="Europe/Helsinki",
            limit=5000,
        )

        self.assertEqual([row["timestamp"] for row in payload["series"]], [
            "2026-01-01T02:00:00+02:00",
            "2026-01-01T04:00:00+02:00",
        ])
        self.assertEqual(payload["series"][0]["avg_value"], 12.0)
        self.assertEqual(payload["series"][0]["peak_value"], 14.0)
        self.assertEqual(payload["series"][0]["trough_value"], 10.0)
        self.assertEqual(payload["series"][0]["sample_count"], 2)
        self.assertEqual(payload["series"][0]["value"], 12.0)
        self.assertEqual(payload["series"][0]["bucket_start"], "2026-01-01T02:00:00+02:00")
        self.assertEqual(payload["series"][0]["bucket_end"], "2026-01-01T04:00:00+02:00")

    def test_four_hour_aggregation_returns_bucket_metrics(self):
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
                "updated_at": "2026-04-24T00:00:00Z",
            }
        ])
        records = []
        for timestamp_utc, timestamp_local, value in [
            ("2025-12-31T22:00:00Z", "2026-01-01T00:00:00+02:00", 5.0),
            ("2025-12-31T23:00:00Z", "2026-01-01T01:00:00+02:00", 9.0),
            ("2026-01-01T00:00:00Z", "2026-01-01T02:00:00+02:00", 7.0),
            ("2026-01-01T01:00:00Z", "2026-01-01T03:00:00+02:00", 11.0),
        ]:
            records.append(
                {
                    "dataset_id": "317",
                    "series_key": "fcrn_hourly_market_price",
                    "timestamp_utc": timestamp_utc,
                    "timestamp_local": timestamp_local,
                    "value": value,
                    "unit": "EUR/MW",
                    "quality_flag": None,
                    "source_updated_at": None,
                    "ingested_at": "2026-04-24T00:00:00Z",
                    "extra_json": {},
                }
            )
        self.db.upsert_fingrid_timeseries(records)

        payload = get_dataset_series_payload(
            self.db,
            dataset_id="317",
            start="2025-12-31T22:00:00Z",
            end="2026-01-01T02:00:00Z",
            aggregation="4h",
            tz="Europe/Helsinki",
            limit=5000,
        )

        row = payload["series"][0]
        self.assertEqual(row["timestamp"], "2026-01-01T00:00:00+02:00")
        self.assertEqual(row["bucket_start"], "2026-01-01T00:00:00+02:00")
        self.assertEqual(row["bucket_end"], "2026-01-01T04:00:00+02:00")
        self.assertEqual(row["avg_value"], 8.0)
        self.assertEqual(row["peak_value"], 11.0)
        self.assertEqual(row["trough_value"], 5.0)
        self.assertEqual(row["sample_count"], 4)

    def test_export_includes_bucket_statistics_columns(self):
        csv_text = build_fingrid_csv(
            [
                {
                    "timestamp": "2026-01-01T00:00:00+02:00",
                    "timestamp_utc": "2025-12-31T22:00:00Z",
                    "bucket_start": "2026-01-01T00:00:00+02:00",
                    "bucket_end": "2026-01-01T02:00:00+02:00",
                    "value": 12.0,
                    "avg_value": 12.0,
                    "peak_value": 14.0,
                    "trough_value": 10.0,
                    "sample_count": 2,
                    "unit": "EUR/MW",
                }
            ]
        )

        lines = csv_text.splitlines()
        self.assertEqual(
            lines[0],
            "timestamp,timestamp_utc,bucket_start,bucket_end,value,avg_value,peak_value,trough_value,sample_count,unit",
        )
        self.assertIn("2026-01-01T02:00:00+02:00", lines[1])
        self.assertIn(",14.0,10.0,2,EUR/MW", lines[1])
