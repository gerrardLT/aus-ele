import os
import sys
import tempfile
import types
import unittest

from fastapi.testclient import TestClient

from tests.support import ensure_repo_import_paths, reset_pg_tables

ensure_repo_import_paths()

import data_quality
from data_quality import compute_quality_snapshots, summarize_quality_snapshots
from database import DatabaseManager


class DataQualityStorageTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        # Shared PG database: clear snapshots/issues leaked from previous runs.
        reset_pg_tables(self.db, "data_quality_snapshot", "data_quality_issue")

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_upsert_and_fetch_market_quality_snapshot(self):
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "source_id": "aemo_nem_trading_price",
                "dataset_family": "settlement",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "coverage_ratio": 1.0,
                "freshness_minutes": 10,
                "issues_json": [],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 288},
                "computed_at": "2026-04-27T00:10:00Z",
            }
        )
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "source_id": "aemo_nem_trading_price",
                "dataset_family": "settlement",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "coverage_ratio": 0.99,
                "freshness_minutes": 12,
                "issues_json": ["stale_source"],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 285},
                "computed_at": "2026-04-27T00:12:00Z",
            }
        )
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "source_id": "aemo_nem_trading_price",
                "dataset_family": "settlement",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "coverage_ratio": 0.98,
                "freshness_minutes": 13,
                "issues_json": [
                    {
                        "issue_code": None,
                        "severity": None,
                        "detail_json": None,
                        "detected_at": None,
                    },
                    {
                        "issue_code": "coverage_gap",
                        "severity": "warning",
                        "detail_json": {"missing_intervals": 3},
                        "detected_at": "2026-04-27T00:13:00Z",
                    },
                ],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 282},
                "computed_at": "2026-04-27T00:13:00Z",
            }
        )

        rows = self.db.fetch_data_quality_snapshots(scope="market", market="NEM")

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data_grade"], "analytical")
        self.assertEqual(rows[0]["quality_score"], 0.95)
        self.assertEqual(rows[0]["coverage_ratio"], 0.98)
        self.assertEqual(rows[0]["freshness_minutes"], 13.0)
        self.assertEqual(rows[0]["source_id"], "aemo_nem_trading_price")
        self.assertEqual(rows[0]["dataset_family"], "settlement")
        self.assertEqual(
            rows[0]["issues_json"],
            [
                {
                    "issue_code": None,
                    "severity": None,
                    "detail_json": None,
                    "detected_at": None,
                },
                {
                    "issue_code": "coverage_gap",
                    "severity": "warning",
                    "detail_json": {"missing_intervals": 3},
                    "detected_at": "2026-04-27T00:13:00Z",
                },
            ],
        )
        self.assertEqual(
            rows[0]["metadata_json"],
            {"expected_intervals": 288, "actual_intervals": 282},
        )
        self.assertEqual(rows[0]["computed_at"], "2026-04-27T00:13:00Z")

        with self.db.get_connection() as conn:
            issue_rows = conn.execute(
                f"""
                SELECT scope, market, dataset_key, issue_code, severity, detail_json, detected_at
                FROM {self.db.DATA_QUALITY_ISSUE_TABLE}
                ORDER BY issue_code ASC
                """
            ).fetchall()

        self.assertEqual(len(issue_rows), 2)
        self.assertEqual(issue_rows[0][0], "market")
        self.assertEqual(issue_rows[0][1], "NEM")
        self.assertEqual(issue_rows[0][2], "trading_price_2026:NSW1")
        self.assertEqual(issue_rows[0][3], "coverage_gap")
        self.assertEqual(issue_rows[0][4], "warning")
        self.assertEqual(issue_rows[0][5], '{"missing_intervals": 3}')
        self.assertEqual(issue_rows[0][6], "2026-04-27T00:13:00Z")

        self.assertEqual(issue_rows[1][0], "market")
        self.assertEqual(issue_rows[1][1], "NEM")
        self.assertEqual(issue_rows[1][2], "trading_price_2026:NSW1")
        self.assertEqual(issue_rows[1][3], "unknown")
        self.assertEqual(issue_rows[1][4], "info")
        self.assertEqual(issue_rows[1][5], "{}")
        self.assertEqual(issue_rows[1][6], "2026-04-27T00:13:00Z")

    def test_ensure_data_quality_tables_migrates_source_identity_columns(self):
        with self.db.get_connection() as conn:
            conn.execute(
                f"""
                CREATE TABLE {self.db.DATA_QUALITY_SNAPSHOT_TABLE} (
                    scope TEXT NOT NULL,
                    market TEXT NOT NULL,
                    dataset_key TEXT NOT NULL,
                    data_grade TEXT NOT NULL,
                    quality_score REAL,
                    coverage_ratio REAL,
                    freshness_minutes REAL,
                    issues_json TEXT NOT NULL DEFAULT '[]',
                    metadata_json TEXT NOT NULL DEFAULT '{{}}',
                    computed_at TEXT NOT NULL,
                    PRIMARY KEY (scope, market, dataset_key)
                )
                """
            )
            self.db.ensure_data_quality_tables(conn)
            columns = [
                row[1]
                for row in conn.execute(
                    f"PRAGMA table_info({self.db.DATA_QUALITY_SNAPSHOT_TABLE})"
                ).fetchall()
            ]

        self.assertIn("source_id", columns)
        self.assertIn("dataset_family", columns)

    def test_replace_data_quality_snapshots_is_transactional(self):
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "existing",
                "data_grade": "analytical",
                "quality_score": 0.9,
                "coverage_ratio": 1.0,
                "freshness_minutes": 5,
                "issues_json": [],
                "metadata_json": {},
                "computed_at": "2026-04-27T00:00:00Z",
            }
        )

        snapshots = [
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "replacement",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "coverage_ratio": 1.0,
                "freshness_minutes": 10,
                "issues_json": [],
                "metadata_json": {},
                "computed_at": "2026-04-27T00:10:00Z",
            },
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "broken",
                "quality_score": 0.5,
                "coverage_ratio": 0.5,
                "freshness_minutes": 20,
                "issues_json": [],
                "metadata_json": {},
                "computed_at": "2026-04-27T00:20:00Z",
            },
        ]

        with self.assertRaises(KeyError):
            self.db.replace_data_quality_snapshots(snapshots)

        rows = self.db.fetch_data_quality_snapshots(scope="market", market="NEM")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["dataset_key"], "existing")

    def test_replace_data_quality_snapshots_removes_stale_snapshots_and_issues(self):
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "stale_dataset",
                "data_grade": "estimated",
                "quality_score": 0.6,
                "coverage_ratio": 0.8,
                "freshness_minutes": 45,
                "issues_json": [
                    {
                        "issue_code": "stale_source",
                        "severity": "warning",
                        "detail_json": {"source": "legacy_feed"},
                        "detected_at": "2026-04-27T00:45:00Z",
                    }
                ],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 230},
                "computed_at": "2026-04-27T00:45:00Z",
            }
        )
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "WEM",
                "dataset_key": "surviving_dataset",
                "data_grade": "analytical",
                "quality_score": 0.97,
                "coverage_ratio": 1.0,
                "freshness_minutes": 5,
                "issues_json": [],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 288},
                "computed_at": "2026-04-27T00:05:00Z",
            }
        )

        replaced = self.db.replace_data_quality_snapshots(
            [
                {
                    "scope": "market",
                    "market": "WEM",
                    "dataset_key": "surviving_dataset",
                    "data_grade": "analytical",
                    "quality_score": 0.98,
                    "coverage_ratio": 1.0,
                    "freshness_minutes": 4,
                    "issues_json": [],
                    "metadata_json": {"expected_intervals": 288, "actual_intervals": 288},
                    "computed_at": "2026-04-27T00:04:00Z",
                }
            ]
        )

        self.assertEqual(replaced, 1)
        snapshot_rows = self.db.fetch_data_quality_snapshots(scope="market")
        issue_rows = self.db.fetch_data_quality_issues(scope="market")

        self.assertEqual(
            [(row["market"], row["dataset_key"]) for row in snapshot_rows],
            [("WEM", "surviving_dataset")],
        )
        self.assertEqual(issue_rows, [])

    def test_upsert_and_fetch_aemo_source_sync_state(self):
        self.db.upsert_aemo_source_sync_state(
            source_id="aemo_nem_weather",
            last_success_at="2026-05-01T00:10:00Z",
            last_attempt_at="2026-05-01T00:10:00Z",
            sync_status="degraded",
            last_error="anonymous ftp timeout",
            detail={"provider": "open_meteo_api", "fallback_used": True},
        )

        row = self.db.fetch_aemo_source_sync_state("aemo_nem_weather")
        all_rows = self.db.fetch_aemo_source_sync_states()

        self.assertIsNotNone(row)
        self.assertEqual(row["source_id"], "aemo_nem_weather")
        self.assertEqual(row["sync_status"], "degraded")
        self.assertEqual(row["last_error"], "anonymous ftp timeout")
        self.assertEqual(row["detail_json"]["provider"], "open_meteo_api")
        self.assertEqual(len(all_rows), 1)
        self.assertEqual(all_rows[0]["source_id"], "aemo_nem_weather")


class DataQualitySummaryTests(unittest.TestCase):
    def test_summarize_quality_snapshots_groups_by_market(self):
        rows = [
            {
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "freshness_minutes": 10,
                "issues_json": [],
            },
            {
                "market": "NEM",
                "dataset_key": "trading_price_2026:QLD1",
                "data_grade": "estimated",
                "quality_score": 0.85,
                "freshness_minutes": 30,
                "issues_json": [],
            },
            {
                "market": "NEM",
                "dataset_key": "trading_price_2026:SA1",
                "data_grade": "analytical",
                "quality_score": 1.05,
                "freshness_minutes": 20,
                "issues_json": [],
            },
            {
                "market": "FINGRID",
                "dataset_key": "fi_price",
                "data_grade": "estimated",
                "quality_score": 0.8,
                "freshness_minutes": 45,
                "issues_json": ["stale_source"],
            },
        ]

        summary = summarize_quality_snapshots(rows)

        self.assertEqual(summary["summary"]["market_count"], 2)
        self.assertEqual(summary["summary"]["snapshot_count"], 4)
        self.assertEqual(summary["markets"]["NEM"]["dataset_count"], 3)
        self.assertEqual(summary["markets"]["NEM"]["average_quality_score"], 0.95)
        self.assertEqual(
            summary["markets"]["NEM"]["data_grades"],
            ["analytical", "estimated"],
        )
        self.assertEqual(summary["markets"]["NEM"]["max_freshness_minutes"], 30)
        self.assertEqual(summary["markets"]["FINGRID"]["issue_count"], 1)

    def test_compute_quality_snapshots_raises_when_all_collectors_unimplemented(self):
        original_collectors = (
            data_quality._compute_nem_snapshots,
            data_quality._compute_wem_snapshots,
            data_quality._compute_aemo_source_snapshots,
            data_quality._compute_fingrid_snapshots,
        )
        data_quality._compute_nem_snapshots = lambda db: None
        data_quality._compute_wem_snapshots = lambda db: None
        data_quality._compute_aemo_source_snapshots = lambda db: None
        data_quality._compute_fingrid_snapshots = lambda db: None

        try:
            with self.assertRaises(NotImplementedError):
                compute_quality_snapshots(db=None)
        finally:
            (
                data_quality._compute_nem_snapshots,
                data_quality._compute_wem_snapshots,
                data_quality._compute_aemo_source_snapshots,
                data_quality._compute_fingrid_snapshots,
            ) = original_collectors

    def test_compute_quality_snapshots_accepts_empty_list_from_implemented_collector(self):
        original_collectors = (
            data_quality._compute_nem_snapshots,
            data_quality._compute_wem_snapshots,
            data_quality._compute_aemo_source_snapshots,
            data_quality._compute_fingrid_snapshots,
        )
        data_quality._compute_nem_snapshots = lambda db: []
        data_quality._compute_wem_snapshots = lambda db: None
        data_quality._compute_aemo_source_snapshots = lambda db: None
        data_quality._compute_fingrid_snapshots = lambda db: None

        try:
            self.assertEqual(compute_quality_snapshots(db=None), [])
        finally:
            (
                data_quality._compute_nem_snapshots,
                data_quality._compute_wem_snapshots,
                data_quality._compute_aemo_source_snapshots,
                data_quality._compute_fingrid_snapshots,
            ) = original_collectors

    def test_compute_quality_snapshots_collects_minimal_market_rows(self):
        handle, db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = DatabaseManager(db_path)

        try:
            with db.get_connection() as conn:
                db.ensure_wem_ess_tables(conn)
                db.ensure_fingrid_tables(conn)
                conn.execute(
                    """
                    CREATE TABLE trading_price_2026 (
                        settlement_date TEXT NOT NULL,
                        region_id TEXT NOT NULL,
                        rrp_aud_mwh REAL
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO trading_price_2026 (settlement_date, region_id, rrp_aud_mwh)
                    VALUES
                    ('2026-04-27 00:00:00', 'NSW1', 55.0),
                    ('2026-04-27 00:05:00', 'NSW1', 57.0),
                    ('2026-04-27 00:00:00', 'WEM', 80.0)
                    """
                )
                conn.execute(
                    f"""
                    INSERT INTO {db.WEM_ESS_MARKET_TABLE} (dispatch_interval, energy_price)
                    VALUES ('2026-04-27 00:00:00', 90.0)
                    """
                )
                conn.execute(
                    f"""
                    INSERT INTO {db.FINGRID_SYNC_STATE_TABLE} (
                        dataset_id, last_success_at, last_attempt_at, last_cursor,
                        last_synced_timestamp_utc, sync_status, last_error,
                        backfill_started_at, backfill_completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "317",
                        "2026-04-27T00:10:00Z",
                        "2026-04-27T00:10:00Z",
                        None,
                        "2026-04-27T00:00:00Z",
                        "ok",
                        None,
                        None,
                        None,
                    ),
                )
                conn.execute(
                    f"""
                    INSERT INTO {db.FINGRID_TIMESERIES_TABLE} (
                        dataset_id, series_key, timestamp_utc, timestamp_local, value,
                        unit, quality_flag, source_updated_at, ingested_at, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "317",
                        "main",
                        "2026-04-27T00:00:00Z",
                        "2026-04-27T03:00:00+03:00",
                        8.1,
                        "EUR/MW",
                        None,
                        "2026-04-27T00:00:00Z",
                        "2026-04-27T00:10:00Z",
                        "{}",
                    ),
                )
                conn.commit()

            db.set_last_update_time("2026-04-27 00:10:00")

            rows = compute_quality_snapshots(db)
            by_market = {row["market"]: row for row in rows}

            self.assertIn("NEM", by_market)
            self.assertIn("WEM", by_market)
            self.assertIn("FINGRID", by_market)
            self.assertEqual(by_market["NEM"]["data_grade"], "analytical")
            self.assertEqual(by_market["WEM"]["data_grade"], "preview")
            self.assertEqual(by_market["FINGRID"]["data_grade"], "analytical-preview")
            self.assertEqual(by_market["FINGRID"]["metadata_json"]["record_count"], 1)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_compute_quality_snapshots_preserves_dst_aware_fingrid_coverage_timestamps(self):
        handle, db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = DatabaseManager(db_path)

        try:
            with db.get_connection() as conn:
                db.ensure_fingrid_tables(conn)
                conn.execute(
                    f"""
                    INSERT INTO {db.FINGRID_SYNC_STATE_TABLE} (
                        dataset_id, last_success_at, last_attempt_at, last_cursor,
                        last_synced_timestamp_utc, sync_status, last_error,
                        backfill_started_at, backfill_completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "317",
                        "2026-10-25T01:30:00Z",
                        "2026-10-25T01:30:00Z",
                        None,
                        "2026-10-25T01:00:00Z",
                        "ok",
                        None,
                        None,
                        None,
                    ),
                )
                conn.executemany(
                    f"""
                    INSERT INTO {db.FINGRID_TIMESERIES_TABLE} (
                        dataset_id, series_key, timestamp_utc, timestamp_local, value,
                        unit, quality_flag, source_updated_at, ingested_at, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "317",
                            "main",
                            "2026-10-25T00:00:00Z",
                            "2026-10-25T03:00:00+03:00",
                            8.0,
                            "EUR/MW",
                            None,
                            "2026-10-25T00:00:00Z",
                            "2026-10-25T01:30:00Z",
                            "{}",
                        ),
                        (
                            "317",
                            "main",
                            "2026-10-25T01:00:00Z",
                            "2026-10-25T03:00:00+02:00",
                            8.1,
                            "EUR/MW",
                            None,
                            "2026-10-25T01:00:00Z",
                            "2026-10-25T01:30:00Z",
                            "{}",
                        ),
                    ],
                )
                conn.commit()

            rows = compute_quality_snapshots(db)
            fingrid_row = next(row for row in rows if row["market"] == "FINGRID")

            self.assertEqual(fingrid_row["metadata_json"]["coverage_start_utc"], "2026-10-25T00:00:00Z")
            self.assertEqual(fingrid_row["metadata_json"]["coverage_end_utc"], "2026-10-25T01:00:00Z")
            self.assertEqual(fingrid_row["metadata_json"]["record_count"], 2)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_compute_quality_snapshots_flags_fingrid_resolution_mixture(self):
        handle, db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = DatabaseManager(db_path)

        try:
            with db.get_connection() as conn:
                db.ensure_fingrid_tables(conn)
                conn.execute(
                    f"""
                    INSERT INTO {db.FINGRID_SYNC_STATE_TABLE} (
                        dataset_id, last_success_at, last_attempt_at, last_cursor,
                        last_synced_timestamp_utc, sync_status, last_error,
                        backfill_started_at, backfill_completed_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "317",
                        "2026-04-27T00:10:00Z",
                        "2026-04-27T00:10:00Z",
                        None,
                        "2026-04-27T00:00:00Z",
                        "ok",
                        None,
                        None,
                        None,
                    ),
                )
                conn.executemany(
                    f"""
                    INSERT INTO {db.FINGRID_TIMESERIES_TABLE} (
                        dataset_id, series_key, timestamp_utc, timestamp_local, value,
                        unit, quality_flag, source_updated_at, ingested_at, extra_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    [
                        (
                            "317",
                            "main",
                            "2026-04-27T00:00:00Z",
                            "2026-04-27T03:00:00+03:00",
                            8.0,
                            "EUR/MW",
                            None,
                            "2026-04-27T00:00:00Z",
                            "2026-04-27T00:10:00Z",
                            "{}",
                        ),
                        (
                            "317",
                            "main",
                            "2026-04-27T00:15:00Z",
                            "2026-04-27T03:15:00+03:00",
                            8.2,
                            "EUR/MW",
                            None,
                            "2026-04-27T00:15:00Z",
                            "2026-04-27T00:10:00Z",
                            "{}",
                        ),
                        (
                            "317",
                            "main",
                            "2026-04-27T01:00:00Z",
                            "2026-04-27T04:00:00+03:00",
                            8.3,
                            "EUR/MW",
                            None,
                            "2026-04-27T01:00:00Z",
                            "2026-04-27T00:10:00Z",
                            "{}",
                        ),
                    ],
                )
                conn.commit()

            rows = compute_quality_snapshots(db)
            fingrid_row = next(row for row in rows if row["market"] == "FINGRID")

            issue_codes = {item["issue_code"] for item in fingrid_row["issues_json"]}
            self.assertIn("resolution_mixture", issue_codes)
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_compute_quality_snapshots_includes_aemo_source_governance_rows(self):
        handle, db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        db = DatabaseManager(db_path)

        try:
            with db.get_connection() as conn:
                db.ensure_aemo_source_sync_table(conn)
                conn.execute(
                    """
                    CREATE TABLE bom_weather_observation (
                        region_id TEXT NOT NULL,
                        station_name TEXT NOT NULL,
                        observation_time_utc TEXT NOT NULL,
                        observation_time_local TEXT,
                        air_temperature_c REAL,
                        wind_speed_mps REAL,
                        cloud_cover_pct REAL,
                        apparent_temperature_c REAL,
                        relative_humidity_pct REAL,
                        rainfall_mm REAL,
                        pressure_hpa REAL,
                        source_file TEXT NOT NULL,
                        PRIMARY KEY (region_id, observation_time_utc)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE pdpasa_duid_availability (
                        run_datetime TEXT NOT NULL,
                        duid TEXT NOT NULL,
                        interval_datetime TEXT NOT NULL,
                        generation_max_availability REAL,
                        generation_pasa_availability REAL,
                        generation_recall_period REAL,
                        load_max_availability REAL,
                        load_pasa_availability REAL,
                        load_recall_period REAL,
                        lastchanged TEXT,
                        source_file TEXT NOT NULL,
                        PRIMARY KEY (run_datetime, duid, interval_datetime)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE wem_reserve_shortfall_snapshot (
                        interval_start_utc TEXT NOT NULL,
                        interval_end_utc TEXT NOT NULL,
                        reserve_service TEXT NOT NULL,
                        shortfall_mw REAL NOT NULL,
                        severity TEXT NOT NULL,
                        source_table TEXT NOT NULL,
                        source_interval TEXT NOT NULL,
                        PRIMARY KEY (interval_start_utc, reserve_service)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE operational_demand_actual_hh (
                        region_id TEXT NOT NULL,
                        interval_datetime TEXT NOT NULL,
                        operational_demand REAL,
                        operational_demand_adjustment REAL,
                        wdr_estimate REAL,
                        lastchanged TEXT,
                        source_file TEXT NOT NULL,
                        PRIMARY KEY (region_id, interval_datetime)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE operational_demand_forecast_hh (
                        region_id TEXT NOT NULL,
                        interval_datetime TEXT NOT NULL,
                        load_date TEXT NOT NULL,
                        operational_demand_poe10 REAL,
                        operational_demand_poe50 REAL,
                        operational_demand_poe90 REAL,
                        lastchanged TEXT,
                        source_file TEXT NOT NULL,
                        PRIMARY KEY (region_id, interval_datetime, load_date)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE rooftop_pv_actual_measurement (
                        region_id TEXT NOT NULL,
                        interval_datetime TEXT NOT NULL,
                        power REAL,
                        qi REAL,
                        source_type TEXT,
                        lastchanged TEXT,
                        source_file TEXT NOT NULL,
                        PRIMARY KEY (region_id, interval_datetime)
                    )
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE dispatch_interconnector_flow (
                        interconnector_id TEXT NOT NULL,
                        settlement_date TEXT NOT NULL,
                        from_regionid TEXT NOT NULL,
                        to_regionid TEXT NOT NULL,
                        mwflow REAL,
                        meteredmwflow REAL,
                        source_file TEXT NOT NULL,
                        PRIMARY KEY (interconnector_id, settlement_date)
                    )
                    """
                )
                conn.execute(
                    """
                    INSERT INTO bom_weather_observation (
                        region_id, station_name, observation_time_utc, observation_time_local,
                        air_temperature_c, wind_speed_mps, cloud_cover_pct, apparent_temperature_c,
                        relative_humidity_pct, rainfall_mm, pressure_hpa, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "QLD1",
                        "Brisbane",
                        "2026-05-01T00:00:00Z",
                        "2026-05-01T10:00:00+10:00",
                        24.0,
                        5.0,
                        30.0,
                        25.0,
                        60.0,
                        0.0,
                        1012.0,
                        "open_meteo_api",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO pdpasa_duid_availability (
                        run_datetime, duid, interval_datetime, generation_max_availability,
                        generation_pasa_availability, generation_recall_period, load_max_availability,
                        load_pasa_availability, load_recall_period, lastchanged, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-05-01 00:00:00",
                        "BAT1",
                        "2026-05-01 04:00:00",
                        100.0,
                        95.0,
                        0.0,
                        0.0,
                        0.0,
                        0.0,
                        "2026-05-01 00:00:00",
                        "PDPASA_20260501.zip",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO wem_reserve_shortfall_snapshot (
                        interval_start_utc, interval_end_utc, reserve_service, shortfall_mw,
                        severity, source_table, source_interval
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "2026-05-01T00:00:00Z",
                        "2026-05-01T00:05:00Z",
                        "REGULATION_RAISE",
                        12.0,
                        "market_shortfall",
                        "wem_ess_market_price",
                        "2026-05-01 00:00:00",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO operational_demand_actual_hh (
                        region_id, interval_datetime, operational_demand, operational_demand_adjustment,
                        wdr_estimate, lastchanged, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "NSW1",
                        "2026/05/01 00:00:00",
                        8000.0,
                        0.0,
                        0.0,
                        "2026-05-01 00:00:00",
                        "PUBLIC_ACTUAL_OPERATIONAL_DEMAND.zip",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO operational_demand_forecast_hh (
                        region_id, interval_datetime, load_date, operational_demand_poe10,
                        operational_demand_poe50, operational_demand_poe90, lastchanged, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "NSW1",
                        "2026/05/01 00:30:00",
                        "2026/05/01 00:00:00",
                        7800.0,
                        8000.0,
                        8200.0,
                        "2026-05-01 00:00:00",
                        "PUBLIC_FORECAST_OPERATIONAL_DEMAND.zip",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO rooftop_pv_actual_measurement (
                        region_id, interval_datetime, power, qi, source_type, lastchanged, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "SA1",
                        "2026/05/01 00:00:00",
                        1200.0,
                        1.0,
                        "MEASUREMENT",
                        "2026-05-01 00:00:00",
                        "PUBLIC_ROOFTOP_PV_ACTUAL.zip",
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO dispatch_interconnector_flow (
                        interconnector_id, settlement_date, from_regionid, to_regionid, mwflow, meteredmwflow, source_file
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "NSW1-QLD1",
                        "2026-05-01 00:00:00",
                        "NSW1",
                        "QLD1",
                        150.0,
                        149.0,
                        "PUBLIC_DISPATCHIS.zip",
                    ),
                )
                conn.commit()

            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_weather",
                last_success_at="2026-05-01T00:10:00Z",
                last_attempt_at="2026-05-01T00:10:00Z",
                sync_status="degraded",
                last_error=None,
                detail={"provider": "open_meteo_api", "fallback_used": True},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_load_actual",
                last_success_at="2026-05-01T00:05:00Z",
                last_attempt_at="2026-05-01T00:05:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_load_forecast",
                last_success_at="2026-05-01T00:06:00Z",
                last_attempt_at="2026-05-01T00:06:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_rooftop_pv",
                last_success_at="2026-05-01T00:07:00Z",
                last_attempt_at="2026-05-01T00:07:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_interconnector_flow",
                last_success_at="2026-05-01T00:08:00Z",
                last_attempt_at="2026-05-01T00:08:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_wind_actual",
                last_success_at="2026-05-01T00:09:00Z",
                last_attempt_at="2026-05-01T00:09:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1, "metric": "ss_wind_clearedmw"},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_solar_actual",
                last_success_at="2026-05-01T00:10:00Z",
                last_attempt_at="2026-05-01T00:10:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1, "metric": "ss_solar_clearedmw"},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_nem_unit_availability",
                last_success_at="2026-05-01T00:12:00Z",
                last_attempt_at="2026-05-01T00:12:00Z",
                sync_status="ok",
                last_error=None,
                detail={"row_count": 1},
            )
            db.upsert_aemo_source_sync_state(
                source_id="aemo_wem_reserve_shortfall",
                last_success_at="2026-05-01T00:15:00Z",
                last_attempt_at="2026-05-01T00:15:00Z",
                sync_status="ok",
                last_error=None,
                detail={"derived_from": "wem_ess_market_price"},
            )

            rows = compute_quality_snapshots(db)
            keyed = {row["source_id"]: row for row in rows if row.get("source_id")}

            self.assertIn("aemo_nem_weather", keyed)
            self.assertIn("aemo_nem_load_actual", keyed)
            self.assertIn("aemo_nem_load_forecast", keyed)
            self.assertIn("aemo_nem_rooftop_pv", keyed)
            self.assertIn("aemo_nem_interconnector_flow", keyed)
            self.assertIn("aemo_nem_unit_availability", keyed)
            self.assertIn("aemo_wem_reserve_shortfall", keyed)
            self.assertEqual(keyed["aemo_nem_weather"]["dataset_family"], "weather")
            self.assertEqual(keyed["aemo_nem_weather"]["market"], "NEM")
            self.assertEqual(keyed["aemo_nem_weather"]["data_grade"], "analytical-preview")
            weather_issue_codes = {item["issue_code"] for item in keyed["aemo_nem_weather"]["issues_json"]}
            self.assertIn("sync_not_ok", weather_issue_codes)
            self.assertEqual(keyed["aemo_nem_load_actual"]["dataset_family"], "load_actual")
            self.assertEqual(keyed["aemo_nem_load_forecast"]["dataset_family"], "load_forecast")
            self.assertEqual(keyed["aemo_nem_rooftop_pv"]["dataset_family"], "rooftop_pv")
            self.assertEqual(keyed["aemo_nem_interconnector_flow"]["dataset_family"], "interconnector_flow")
            self.assertEqual(keyed["aemo_nem_unit_availability"]["dataset_family"], "unit_availability")
            wind_actual_issue_codes = {item["issue_code"] for item in keyed["aemo_nem_wind_actual"]["issues_json"]}
            solar_actual_issue_codes = {item["issue_code"] for item in keyed["aemo_nem_solar_actual"]["issues_json"]}
            self.assertIn("actual_proxy_source", wind_actual_issue_codes)
            self.assertIn("actual_proxy_source", solar_actual_issue_codes)
            self.assertEqual(keyed["aemo_wem_reserve_shortfall"]["market"], "WEM")
            self.assertEqual(
                keyed["aemo_wem_reserve_shortfall"]["metadata_json"]["coverage_end"],
                "2026-05-01T00:05:00Z",
            )
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)


class DataQualityApiTests(unittest.TestCase):
    @staticmethod
    def _ensure_test_pulp_stub():
        sys.modules.pop("pulp", None)
        sys.modules["pulp"] = types.ModuleType("pulp")

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        # Shared PG database: clear snapshots/issues leaked from previous runs.
        reset_pg_tables(self.db, "data_quality_snapshot", "data_quality_issue")
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "coverage_ratio": 1.0,
                "freshness_minutes": 10,
                "issues_json": [],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 288},
                "computed_at": "2026-04-27T00:10:00Z",
            }
        )
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "WEM",
                "dataset_key": "balancing_price_2026:WEM",
                "data_grade": "estimated",
                "quality_score": 0.8,
                "coverage_ratio": 0.95,
                "freshness_minutes": 25,
                "issues_json": [
                    {
                        "issue_code": "stale_source",
                        "severity": "warning",
                        "detail_json": {"source": "wem_feed"},
                        "detected_at": "2026-04-27T00:25:00Z",
                    }
                ],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 275},
                "computed_at": "2026-04-27T00:25:00Z",
            }
        )

        self.original_scheduler_flag = os.environ.get("AUS_ELE_ENABLE_SCHEDULER")
        os.environ["AUS_ELE_ENABLE_SCHEDULER"] = "0"

        self._ensure_test_pulp_stub()
        import server

        self.server = server
        self.original_db = server.db
        server.db = self.db
        self.client = TestClient(server.app)

    def tearDown(self):
        self.client.close()
        self.server.db = self.original_db

        if self.original_scheduler_flag is None:
            os.environ.pop("AUS_ELE_ENABLE_SCHEDULER", None)
        else:
            os.environ["AUS_ELE_ENABLE_SCHEDULER"] = self.original_scheduler_flag

        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_data_quality_summary_route_returns_structured_payload(self):
        response = self.client.get("/api/data-quality/summary")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["summary"]["market_count"], 2)
        self.assertEqual(payload["markets"]["NEM"]["dataset_count"], 1)

    def test_data_quality_refresh_route_translates_not_implemented(self):
        original_compute_quality_snapshots = self.server.compute_quality_snapshots
        self.server.compute_quality_snapshots = lambda db: (_ for _ in ()).throw(
            NotImplementedError("collectors unavailable")
        )

        try:
            response = self.client.post("/api/data-quality/refresh")
        finally:
            self.server.compute_quality_snapshots = original_compute_quality_snapshots

        self.assertEqual(response.status_code, 501)
        self.assertEqual(response.json()["detail"], "collectors unavailable")

    def test_data_quality_refresh_route_persists_computed_snapshots(self):
        original_compute_quality_snapshots = self.server.compute_quality_snapshots
        snapshots = [
            {
                "scope": "dataset",
                "market": "NEM",
                "dataset_key": "bom_weather_observation",
                "source_id": "aemo_nem_weather",
                "dataset_family": "weather",
                "data_grade": "analytical-preview",
                "quality_score": 0.83,
                "coverage_ratio": 1.0,
                "freshness_minutes": 15,
                "issues_json": [],
                "metadata_json": {"row_count": 12},
                "computed_at": "2026-05-01T00:15:00Z",
            }
        ]
        self.server.compute_quality_snapshots = lambda db: snapshots

        try:
            response = self.client.post("/api/data-quality/refresh")
        finally:
            self.server.compute_quality_snapshots = original_compute_quality_snapshots

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "ok")
        self.assertEqual(response.json()["snapshots_refreshed"], 1)
        rows = self.db.fetch_data_quality_snapshots(scope="dataset", market="NEM")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source_id"], "aemo_nem_weather")

    def test_data_quality_markets_route_returns_market_rows(self):
        response = self.client.get("/api/data-quality/markets")

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 2)
        self.assertEqual(payload["items"][0]["market"], "NEM")
        self.assertEqual(payload["items"][1]["market"], "WEM")

    def test_data_quality_issues_route_returns_filtered_normalized_rows(self):
        response = self.client.get("/api/data-quality/issues", params={"market": "WEM"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["market"], "WEM")
        self.assertEqual(payload["items"][0]["issue_code"], "stale_source")
        self.assertEqual(payload["items"][0]["severity"], "warning")
        self.assertEqual(payload["items"][0]["detail_json"], {"source": "wem_feed"})
