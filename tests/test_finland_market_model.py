import os
import tempfile
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from finland_market_model import build_finland_market_model_payload


class FinlandMarketModelTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_finland_market_model_exposes_multi_source_structure(self):
        self.db.upsert_fingrid_dataset_catalog(
            [
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
                    "updated_at": "2026-04-27T00:00:00Z",
                },
                {
                    "dataset_id": "319",
                    "dataset_code": "imbalance_price",
                    "name": "Imbalance price",
                    "description": "Imbalance price in Finland.",
                    "unit": "EUR/MWh",
                    "frequency": "1h+",
                    "timezone": "Europe/Helsinki",
                    "value_kind": "imbalance_price",
                    "source_url": "https://data.fingrid.fi/en/datasets/319",
                    "enabled": 1,
                    "metadata_json": {"market": "Fingrid", "product": "Imbalance"},
                    "updated_at": "2026-04-27T00:00:00Z",
                },
            ]
        )
        self.db.upsert_fingrid_timeseries(
            [
                {
                    "dataset_id": "317",
                    "series_key": "fcrn_hourly_market_price",
                    "timestamp_utc": "2026-01-01T00:00:00Z",
                    "timestamp_local": "2026-01-01T02:00:00+02:00",
                    "value": 16.5,
                    "unit": "EUR/MW",
                    "quality_flag": "confirmed",
                    "source_updated_at": "2026-01-01T00:10:00Z",
                    "ingested_at": "2026-04-27T00:00:00Z",
                    "extra_json": {},
                },
                {
                    "dataset_id": "319",
                    "series_key": "imbalance_price",
                    "timestamp_utc": "2026-01-01T00:00:00Z",
                    "timestamp_local": "2026-01-01T02:00:00+02:00",
                    "value": 88.2,
                    "unit": "EUR/MWh",
                    "quality_flag": "confirmed",
                    "source_updated_at": "2026-01-01T00:10:00Z",
                    "ingested_at": "2026-04-27T00:00:00Z",
                    "extra_json": {},
                },
            ]
        )
        self.db.upsert_fingrid_sync_state(
            dataset_id="317",
            last_success_at="2026-04-27T00:05:00Z",
            last_attempt_at="2026-04-27T00:05:00Z",
            last_cursor="2026-01-01T00:00:00Z",
            last_synced_timestamp_utc="2026-01-01T00:00:00Z",
            sync_status="ok",
            last_error=None,
            backfill_started_at="2026-04-27T00:00:00Z",
            backfill_completed_at="2026-04-27T00:05:00Z",
        )
        self.db.upsert_fingrid_sync_state(
            dataset_id="319",
            last_success_at="2026-04-27T00:06:00Z",
            last_attempt_at="2026-04-27T00:06:00Z",
            last_cursor="2026-01-01T00:00:00Z",
            last_synced_timestamp_utc="2026-01-01T00:00:00Z",
            sync_status="ok",
            last_error=None,
            backfill_started_at="2026-04-27T00:00:00Z",
            backfill_completed_at="2026-04-27T00:06:00Z",
        )

        payload = build_finland_market_model_payload(self.db)

        self.assertEqual(payload["country"], "Finland")
        self.assertEqual(payload["market"], "Finland")
        self.assertEqual(payload["model_status"], "partial-live")
        self.assertEqual([source["source_key"] for source in payload["sources"]], ["fingrid", "nord_pool", "entsoe"])
        self.assertEqual(payload["sources"][0]["status"], "live")
        self.assertEqual(payload["sources"][1]["status"], "planned")
        self.assertEqual(payload["sources"][2]["status"], "planned")
        self.assertEqual(payload["summary"]["live_dataset_count"], 2)
        self.assertEqual(sorted(payload["summary"]["live_signal_keys"]), ["imbalance_price", "reserve_capacity_price"])
        self.assertEqual(
            sorted(signal["dataset_id"] for signal in payload["live_signals"]),
            ["317", "319"],
        )
        self.assertEqual(payload["metadata"]["market"], "FINLAND")
        self.assertIn("planned_external_sources", payload["metadata"]["warnings"])

    def test_finland_market_model_exposes_external_source_integration_readiness(self):
        payload = build_finland_market_model_payload(self.db)

        nord_pool = next(source for source in payload["sources"] if source["source_key"] == "nord_pool")
        entsoe = next(source for source in payload["sources"] if source["source_key"] == "entsoe")

        self.assertEqual(nord_pool["integration"]["auth_mode"], "subscription_api_account")
        self.assertFalse(nord_pool["integration"]["configured"])
        self.assertEqual(nord_pool["integration"]["readiness"], "credentials_required")
        self.assertEqual(entsoe["integration"]["auth_mode"], "security_token")
        self.assertFalse(entsoe["integration"]["configured"])
        self.assertEqual(entsoe["integration"]["readiness"], "credentials_required")
        self.assertEqual(payload["summary"]["configured_external_source_count"], 0)

    def test_finland_market_model_marks_external_sources_configured_when_env_present(self):
        with mock.patch.dict(
            os.environ,
            {
                "NORDPOOL_API_BASE_URL": "https://data-api.nordpoolgroup.com",
                "NORDPOOL_API_KEY": "np-test",
                "ENTSOE_API_BASE_URL": "https://web-api.tp.entsoe.eu/api",
                "ENTSOE_SECURITY_TOKEN": "entsoe-test",
            },
            clear=False,
        ):
            payload = build_finland_market_model_payload(self.db)

        nord_pool = next(source for source in payload["sources"] if source["source_key"] == "nord_pool")
        entsoe = next(source for source in payload["sources"] if source["source_key"] == "entsoe")

        self.assertEqual(nord_pool["status"], "configured")
        self.assertTrue(nord_pool["integration"]["configured"])
        self.assertEqual(nord_pool["integration"]["readiness"], "configured")
        self.assertEqual(entsoe["status"], "configured")
        self.assertTrue(entsoe["integration"]["configured"])
        self.assertEqual(entsoe["integration"]["readiness"], "configured")
        self.assertEqual(payload["summary"]["configured_external_source_count"], 2)

    def test_finland_market_model_uses_nordpool_live_dataset_when_available(self):
        with mock.patch.dict(
            os.environ,
            {
                "NORDPOOL_API_BASE_URL": "https://data-api.nordpoolgroup.com",
                "NORDPOOL_API_KEY": "np-test",
            },
            clear=False,
        ):
            with mock.patch(
                "finland_market_model.fetch_nordpool_finland_day_ahead_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "nordpool_day_ahead_fi",
                        "dataset_code": "prices_area_fi",
                        "name": "Finland day-ahead prices",
                        "unit": "EUR/MWh",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 24,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_price": 55.0,
                        "average_price": 47.2,
                    },
                },
            ), mock.patch(
                "finland_market_model.fetch_nordpool_finland_intraday_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "nordpool_intraday_fi",
                        "dataset_code": "intraday_trades_delivery_fi",
                        "name": "Finland intraday trades",
                        "unit": "EUR/MWh",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 36,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_price": 53.0,
                        "average_price": 48.1,
                        "total_volume_mwh": 420.0,
                    },
                },
            ):
                payload = build_finland_market_model_payload(self.db)

        nord_pool = next(source for source in payload["sources"] if source["source_key"] == "nord_pool")
        self.assertEqual(nord_pool["status"], "live")
        self.assertEqual(nord_pool["datasets"][0]["dataset_id"], "nordpool_day_ahead_fi")
        self.assertEqual(nord_pool["datasets"][1]["dataset_id"], "nordpool_intraday_fi")

    def test_finland_market_model_uses_entsoe_live_dataset_when_available(self):
        with mock.patch.dict(
            os.environ,
            {
                "ENTSOE_API_BASE_URL": "https://web-api.tp.entsoe.eu/api",
                "ENTSOE_SECURITY_TOKEN": "entsoe-test",
            },
            clear=False,
        ):
            with mock.patch(
                "finland_market_model.fetch_finland_day_ahead_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "entsoe_day_ahead_fi",
                        "dataset_code": "A44_A01_FI",
                        "name": "Finland day-ahead prices",
                        "unit": "EUR/MWh",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 24,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_price": 55.0,
                        "average_price": 47.2,
                    },
                },
            ), mock.patch(
                "finland_market_model.fetch_finland_total_load_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "entsoe_total_load_fi",
                        "dataset_code": "A65_A16_FI",
                        "name": "Finland total load",
                        "unit": "MW",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 24,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_load_mw": 8100.0,
                        "average_load_mw": 7450.0,
                    },
                },
            ), mock.patch(
                "finland_market_model.fetch_finland_generation_mix_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "entsoe_generation_mix_fi",
                        "dataset_code": "A75_A16_FI",
                        "name": "Finland generation mix",
                        "unit": "MW",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 48,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_total_generation_mw": 5550.0,
                        "production_type_count": 2,
                        "top_production_type": "B16",
                    },
                },
            ), mock.patch(
                "finland_market_model.fetch_finland_cross_border_flow_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "entsoe_cross_border_flow_fi",
                        "dataset_code": "A11_FI_BORDERS",
                        "name": "Finland cross-border physical flows",
                        "unit": "MW",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 48,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_total_flow_mw": 2090.0,
                        "border_count": 2,
                        "largest_border": "EE",
                    },
                },
            ), mock.patch(
                "finland_market_model.fetch_finland_generation_forecast_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "entsoe_generation_forecast_fi",
                        "dataset_code": "A71_A01_FI",
                        "name": "Finland generation forecast",
                        "unit": "MW",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 24,
                        "coverage_start_utc": "2026-04-28T00:00:00Z",
                        "coverage_end_utc": "2026-04-28T23:00:00Z",
                    },
                    "summary": {
                        "latest_generation_forecast_mw": 7800.0,
                        "average_generation_forecast_mw": 7700.0,
                    },
                },
            ):
                payload = build_finland_market_model_payload(self.db)

        entsoe = next(source for source in payload["sources"] if source["source_key"] == "entsoe")
        self.assertEqual(entsoe["status"], "live")
        self.assertEqual(entsoe["datasets"][0]["dataset_id"], "entsoe_day_ahead_fi")
        self.assertEqual(entsoe["datasets"][1]["dataset_id"], "entsoe_total_load_fi")
        self.assertEqual(entsoe["datasets"][2]["dataset_id"], "entsoe_generation_mix_fi")
        self.assertEqual(entsoe["datasets"][3]["dataset_id"], "entsoe_cross_border_flow_fi")
        self.assertEqual(entsoe["datasets"][4]["dataset_id"], "entsoe_generation_forecast_fi")
        self.assertEqual(payload["summary"]["live_source_count"], 2)
