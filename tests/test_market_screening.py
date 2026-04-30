import os
import tempfile
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from data_quality import compute_quality_snapshots
from database import DatabaseManager
import server
from fastapi import HTTPException


class MarketScreeningApiTests(unittest.TestCase):
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

    def test_market_screening_returns_ranked_items_for_nem_wem_and_finland(self):
        self.db.batch_insert(
            [
                {
                    "settlement_date": "2025-01-01 00:00:00",
                    "region_id": "NSW1",
                    "rrp_aud_mwh": 20.0,
                    "raise1sec_rrp": 80.0,
                    "raise6sec_rrp": 20.0,
                    "raise60sec_rrp": 0.0,
                    "raise5min_rrp": 0.0,
                    "raisereg_rrp": 0.0,
                    "lower1sec_rrp": 5.0,
                    "lower6sec_rrp": 0.0,
                    "lower60sec_rrp": 0.0,
                    "lower5min_rrp": 0.0,
                    "lowerreg_rrp": 0.0,
                },
                {
                    "settlement_date": "2025-01-01 00:05:00",
                    "region_id": "NSW1",
                    "rrp_aud_mwh": 220.0,
                    "raise1sec_rrp": 120.0,
                    "raise6sec_rrp": 40.0,
                    "raise60sec_rrp": 0.0,
                    "raise5min_rrp": 0.0,
                    "raisereg_rrp": 0.0,
                    "lower1sec_rrp": 5.0,
                    "lower6sec_rrp": 0.0,
                    "lower60sec_rrp": 0.0,
                    "lower5min_rrp": 0.0,
                    "lowerreg_rrp": 0.0,
                },
            ]
        )

        with self.db.get_connection() as conn:
            self.db.ensure_wem_ess_tables(conn)
            self.db.ensure_fingrid_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.db.WEM_ESS_MARKET_TABLE} (
                    dispatch_interval, energy_price, regulation_raise_price, regulation_lower_price,
                    contingency_raise_price, contingency_lower_price, rocof_price,
                    available_regulation_raise, available_regulation_lower,
                    available_contingency_raise, available_contingency_lower, available_rocof,
                    in_service_regulation_raise, in_service_regulation_lower,
                    in_service_contingency_raise, in_service_contingency_lower, in_service_rocof,
                    requirement_regulation_raise, requirement_regulation_lower,
                    requirement_contingency_raise, requirement_contingency_lower, requirement_rocof,
                    shortfall_regulation_raise, shortfall_regulation_lower,
                    shortfall_contingency_raise, shortfall_contingency_lower, shortfall_rocof,
                    dispatch_total_regulation_raise, dispatch_total_regulation_lower,
                    dispatch_total_contingency_raise, dispatch_total_contingency_lower, dispatch_total_rocof,
                    capped_regulation_raise, capped_regulation_lower, capped_contingency_raise,
                    capped_contingency_lower, capped_rocof
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "2025-01-01 08:00:00", 95.0, 15.0, 11.0, 6.0, 4.0, 3.0,
                    435.0, 437.0, 329.0, 331.0, 5966.0,
                    979.0, 979.0, 980.0, 1055.0, 12124.0,
                    110.0, 110.0, 258.0, 72.0, 12124.0,
                    3.0, 0.0, 4.0, 0.0, 0.0,
                    110.0, 110.0, 268.0, 72.0, 12124.0,
                    1, 0, 0, 0, 0,
                ),
            )
            conn.execute(
                f"""
                INSERT INTO {self.db.FINGRID_TIMESERIES_TABLE} (
                    dataset_id, series_key, timestamp_utc, timestamp_local, value, unit,
                    quality_flag, source_updated_at, ingested_at, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "317",
                    "fcrn_hourly_market_price",
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T02:00:00+02:00",
                    42.5,
                    "EUR/MW",
                    "confirmed",
                    "2025-01-01T00:05:00Z",
                    "2026-04-27T00:00:00Z",
                    '{"end_time":"2025-01-01T01:00:00Z"}',
                ),
            )
            conn.execute(
                f"""
                INSERT INTO {self.db.FINGRID_SYNC_STATE_TABLE} (
                    dataset_id, last_success_at, last_attempt_at, last_cursor,
                    last_synced_timestamp_utc, sync_status, last_error, backfill_started_at, backfill_completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "317",
                    "2026-04-27T00:00:00Z",
                    "2026-04-27T00:00:00Z",
                    "2025-01-01T00:00:00Z",
                    "2025-01-01T00:00:00Z",
                    "ok",
                    None,
                    None,
                    None,
                ),
            )
            conn.commit()

        snapshots = compute_quality_snapshots(self.db)
        self.db.replace_data_quality_snapshots(snapshots)

        payload = server.get_market_screening(year=2025)

        self.assertIn("items", payload)
        self.assertGreaterEqual(len(payload["items"]), 3)
        self.assertEqual(payload["items"][0]["rank"], 1)
        keys = {item["candidate_key"] for item in payload["items"]}
        self.assertIn("NEM:NSW1", keys)
        self.assertIn("WEM:WEM", keys)
        self.assertIn("FINGRID:FI", keys)

        first = payload["items"][0]
        self.assertIn("overall_score", first)
        self.assertIn("spread_score", first)
        self.assertIn("volatility_score", first)
        self.assertIn("storage_fit_score", first)
        self.assertIn("fcas_or_ess_opportunity_score", first)
        self.assertIn("grid_risk_score", first)
        self.assertIn("revenue_concentration_score", first)
        self.assertIn("data_quality_score", first)
        self.assertIn("metadata", payload)

    def test_market_screening_filters_items_by_access_scope(self):
        self.db.batch_insert(
            [
                {
                    "settlement_date": "2025-01-01 00:00:00",
                    "region_id": "NSW1",
                    "rrp_aud_mwh": 20.0,
                    "raise1sec_rrp": 80.0,
                    "raise6sec_rrp": 20.0,
                    "raise60sec_rrp": 0.0,
                    "raise5min_rrp": 0.0,
                    "raisereg_rrp": 0.0,
                    "lower1sec_rrp": 5.0,
                    "lower6sec_rrp": 0.0,
                    "lower60sec_rrp": 0.0,
                    "lower5min_rrp": 0.0,
                    "lowerreg_rrp": 0.0,
                }
            ]
        )
        snapshots = compute_quality_snapshots(self.db)
        self.db.replace_data_quality_snapshots(snapshots)

        payload = server.get_market_screening(
            year=2025,
            access_scope={
                "organization_id": "org_a",
                "workspace_id": "ws_a",
                "allowed_regions": ["NSW1"],
                "allowed_markets": ["NEM"],
            },
        )

        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["candidate_key"], "NEM:NSW1")

    def test_market_screening_uses_entsoe_day_ahead_context_for_finland_when_configured(self):
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
                }
            ]
        )
        self.db.upsert_fingrid_timeseries(
            [
                {
                    "dataset_id": "317",
                    "series_key": "fcrn_hourly_market_price",
                    "timestamp_utc": "2025-01-01T00:00:00Z",
                    "timestamp_local": "2025-01-01T02:00:00+02:00",
                    "value": 42.5,
                    "unit": "EUR/MW",
                    "quality_flag": "confirmed",
                    "source_updated_at": "2025-01-01T00:05:00Z",
                    "ingested_at": "2026-04-27T00:00:00Z",
                    "extra_json": {},
                }
            ]
        )
        snapshots = compute_quality_snapshots(self.db)
        self.db.replace_data_quality_snapshots(snapshots)

        with mock.patch.dict("os.environ", {"ENTSOE_SECURITY_TOKEN": "entsoe-test"}, clear=False):
            with mock.patch(
                "market_screening.fetch_finland_day_ahead_summary",
                return_value={
                    "dataset": {
                        "dataset_id": "entsoe_day_ahead_fi",
                        "dataset_code": "A44_A01_FI",
                        "name": "Finland day-ahead prices",
                        "unit": "EUR/MWh",
                        "frequency": "1h",
                        "status": "live",
                        "record_count": 24,
                        "coverage_start_utc": "2025-01-01T00:00:00Z",
                        "coverage_end_utc": "2025-01-01T23:00:00Z",
                    },
                    "summary": {
                        "latest_price": 55.0,
                        "average_price": 47.2,
                    },
                    "series": [
                        {"timestamp_utc": "2025-01-01T00:00:00Z", "price": 30.0},
                        {"timestamp_utc": "2025-01-01T01:00:00Z", "price": 64.4},
                    ],
                },
            ):
                payload = server.get_market_screening(year=2025)

        finland_item = next(item for item in payload["items"] if item["candidate_key"] == "FINGRID:FI")
        self.assertEqual(finland_item["supporting_metrics"]["source_stack"], "fingrid+entsoe")
        self.assertEqual(finland_item["supporting_metrics"]["spot_avg_price"], 47.2)
        self.assertIn("multi_source_preview", finland_item["caveats"])


if __name__ == "__main__":
    unittest.main()
