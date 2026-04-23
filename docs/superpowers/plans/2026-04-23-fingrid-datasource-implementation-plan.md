# Fingrid Datasource Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an extensible Fingrid data-source subsystem with dataset `317` live first, backed by SQLite storage, independent `/api/fingrid/...` endpoints, a standalone `/fingrid` page, manual sync, export, and lightweight analytics.

**Architecture:** Keep Fingrid isolated from the existing NEM/WEM `trading_price_*` path. Add a dataset-driven backend module under `backend/fingrid/`, three new SQLite tables in `DatabaseManager`, and a simple pathname-based frontend entry switch instead of introducing a router library. Fetch Fingrid data from `https://data.fingrid.fi/api/datasets/{dataset_id}/data` with an `x-api-key`, use a conservative `6.5s` request floor to stay under the current Fingrid rate cap, persist normalized UTC plus `Europe/Helsinki` timestamps, and compute aggregations in Python and JS so DST handling stays explicit.

**Tech Stack:** FastAPI, SQLite, `requests`, `zoneinfo`, `unittest`, React 19, Vite, Recharts, Node `--test`

---

## File Structure

**Create**

- `backend/fingrid/__init__.py`
- `backend/fingrid/catalog.py`
- `backend/fingrid/client.py`
- `backend/fingrid/schemas.py`
- `backend/fingrid/service.py`
- `backend/fingrid/export.py`
- `scrapers/fingrid_sync.py`
- `tests/test_fingrid_storage.py`
- `tests/test_fingrid_catalog.py`
- `tests/test_fingrid_client.py`
- `tests/test_fingrid_service.py`
- `tests/test_fingrid_api.py`
- `web/src/lib/fingridApi.js`
- `web/src/lib/fingridDataset.js`
- `web/src/lib/pageRouter.js`
- `web/src/lib/fingridApi.test.js`
- `web/src/lib/fingridDataset.test.js`
- `web/src/lib/pageRouter.test.js`
- `web/src/lib/fingridPage.test.js`
- `web/src/pages/FingridPage.jsx`
- `web/src/components/fingrid/FingridHeader.jsx`
- `web/src/components/fingrid/FingridSummaryCards.jsx`
- `web/src/components/fingrid/FingridSeriesChart.jsx`
- `web/src/components/fingrid/FingridDistributionPanel.jsx`
- `web/src/components/fingrid/FingridStatusPanel.jsx`

**Modify**

- `backend/database.py`
- `backend/server.py`
- `web/src/main.jsx`
- `README.md`

**Why this split**

- `backend/database.py` stays the single SQLite access layer, consistent with the current repo.
- `backend/fingrid/` isolates third-party API integration and Fingrid-specific business logic from existing AEMO modules.
- `web/src/lib/*.js` holds pure logic that the current Node test setup can cover without adding a new frontend test runner.
- `web/src/pages/FingridPage.jsx` and `web/src/components/fingrid/*` keep the new route independent from the current `App.jsx` workbench.

### Task 1: SQLite Storage Foundation

**Files:**
- Create: `tests/test_fingrid_storage.py`
- Modify: `backend/database.py`

- [ ] **Step 1: Write the failing storage test**

```python
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
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `python -m unittest tests.test_fingrid_storage -v`

Expected: `AttributeError` for missing `upsert_fingrid_dataset_catalog` / `upsert_fingrid_timeseries`.

- [ ] **Step 3: Add the minimal SQLite schema and accessors**

```python
# backend/database.py
class DatabaseManager:
    FINGRID_DATASET_TABLE = "fingrid_dataset_catalog"
    FINGRID_TIMESERIES_TABLE = "fingrid_timeseries"
    FINGRID_SYNC_STATE_TABLE = "fingrid_sync_state"

    def ensure_fingrid_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.FINGRID_DATASET_TABLE} (
                dataset_id TEXT PRIMARY KEY,
                dataset_code TEXT,
                name TEXT NOT NULL,
                description TEXT,
                unit TEXT NOT NULL,
                frequency TEXT NOT NULL,
                timezone TEXT NOT NULL,
                value_kind TEXT NOT NULL,
                source_url TEXT NOT NULL,
                enabled INTEGER NOT NULL DEFAULT 1,
                metadata_json TEXT NOT NULL DEFAULT '{{}}',
                updated_at TEXT NOT NULL
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.FINGRID_TIMESERIES_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_id TEXT NOT NULL,
                series_key TEXT NOT NULL,
                timestamp_utc TEXT NOT NULL,
                timestamp_local TEXT NOT NULL,
                value REAL,
                unit TEXT NOT NULL,
                quality_flag TEXT,
                source_updated_at TEXT,
                ingested_at TEXT NOT NULL,
                extra_json TEXT NOT NULL DEFAULT '{{}}',
                UNIQUE(dataset_id, series_key, timestamp_utc)
            )
        """)
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.FINGRID_SYNC_STATE_TABLE} (
                dataset_id TEXT PRIMARY KEY,
                last_success_at TEXT,
                last_attempt_at TEXT,
                last_cursor TEXT,
                last_synced_timestamp_utc TEXT,
                sync_status TEXT NOT NULL,
                last_error TEXT,
                backfill_started_at TEXT,
                backfill_completed_at TEXT
            )
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.FINGRID_TIMESERIES_TABLE}_dataset_time
            ON {self.FINGRID_TIMESERIES_TABLE} (dataset_id, timestamp_utc)
        """)
        cursor.execute(f"""
            CREATE INDEX IF NOT EXISTS idx_{self.FINGRID_TIMESERIES_TABLE}_dataset_series_time
            ON {self.FINGRID_TIMESERIES_TABLE} (dataset_id, series_key, timestamp_utc)
        """)
        conn.commit()

    def upsert_fingrid_dataset_catalog(self, records: list[dict]):
        if not records:
            return 0
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            conn.executemany(
                f"""
                INSERT INTO {self.FINGRID_DATASET_TABLE} (
                    dataset_id, dataset_code, name, description, unit, frequency, timezone,
                    value_kind, source_url, enabled, metadata_json, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    dataset_code=excluded.dataset_code,
                    name=excluded.name,
                    description=excluded.description,
                    unit=excluded.unit,
                    frequency=excluded.frequency,
                    timezone=excluded.timezone,
                    value_kind=excluded.value_kind,
                    source_url=excluded.source_url,
                    enabled=excluded.enabled,
                    metadata_json=excluded.metadata_json,
                    updated_at=excluded.updated_at
                """,
                [
                    (
                        record["dataset_id"],
                        record.get("dataset_code"),
                        record["name"],
                        record.get("description"),
                        record["unit"],
                        record["frequency"],
                        record["timezone"],
                        record["value_kind"],
                        record["source_url"],
                        int(record.get("enabled", 1)),
                        json.dumps(record.get("metadata_json") or {}),
                        record["updated_at"],
                    )
                    for record in records
                ],
            )
            conn.commit()
        return len(records)

    def upsert_fingrid_timeseries(self, records: list[dict]):
        if not records:
            return 0
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            conn.executemany(
                f"""
                INSERT INTO {self.FINGRID_TIMESERIES_TABLE} (
                    dataset_id, series_key, timestamp_utc, timestamp_local, value, unit,
                    quality_flag, source_updated_at, ingested_at, extra_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id, series_key, timestamp_utc) DO UPDATE SET
                    timestamp_local=excluded.timestamp_local,
                    value=excluded.value,
                    unit=excluded.unit,
                    quality_flag=excluded.quality_flag,
                    source_updated_at=excluded.source_updated_at,
                    ingested_at=excluded.ingested_at,
                    extra_json=excluded.extra_json
                """,
                [
                    (
                        record["dataset_id"],
                        record["series_key"],
                        record["timestamp_utc"],
                        record["timestamp_local"],
                        record.get("value"),
                        record["unit"],
                        record.get("quality_flag"),
                        record.get("source_updated_at"),
                        record["ingested_at"],
                        json.dumps(record.get("extra_json") or {}),
                    )
                    for record in records
                ],
            )
            conn.commit()
        return len(records)

    def upsert_fingrid_sync_state(self, *, dataset_id: str, last_success_at, last_attempt_at, last_cursor,
                                  last_synced_timestamp_utc, sync_status: str, last_error,
                                  backfill_started_at, backfill_completed_at):
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.FINGRID_SYNC_STATE_TABLE} (
                    dataset_id, last_success_at, last_attempt_at, last_cursor,
                    last_synced_timestamp_utc, sync_status, last_error,
                    backfill_started_at, backfill_completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(dataset_id) DO UPDATE SET
                    last_success_at=excluded.last_success_at,
                    last_attempt_at=excluded.last_attempt_at,
                    last_cursor=excluded.last_cursor,
                    last_synced_timestamp_utc=excluded.last_synced_timestamp_utc,
                    sync_status=excluded.sync_status,
                    last_error=excluded.last_error,
                    backfill_started_at=excluded.backfill_started_at,
                    backfill_completed_at=excluded.backfill_completed_at
                """,
                (
                    dataset_id, last_success_at, last_attempt_at, last_cursor,
                    last_synced_timestamp_utc, sync_status, last_error,
                    backfill_started_at, backfill_completed_at,
                ),
            )
            conn.commit()

    def fetch_fingrid_dataset_catalog(self, enabled_only: bool = True) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            query = f"SELECT dataset_id, dataset_code, name, description, unit, frequency, timezone, value_kind, source_url, enabled, metadata_json, updated_at FROM {self.FINGRID_DATASET_TABLE}"
            if enabled_only:
                query += " WHERE enabled = 1"
            query += " ORDER BY dataset_id ASC"
            cursor.execute(query)
            rows = cursor.fetchall()
        return [
            {
                "dataset_id": row[0],
                "dataset_code": row[1],
                "name": row[2],
                "description": row[3],
                "unit": row[4],
                "frequency": row[5],
                "timezone": row[6],
                "value_kind": row[7],
                "source_url": row[8],
                "enabled": row[9],
                "metadata_json": json.loads(row[10]),
                "updated_at": row[11],
            }
            for row in rows
        ]

    def fetch_fingrid_series(self, *, dataset_id: str, start_utc: str | None = None,
                             end_utc: str | None = None, limit: int | None = None) -> list[dict]:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            clauses = ["dataset_id = ?"]
            params = [dataset_id]
            if start_utc:
                clauses.append("timestamp_utc >= ?")
                params.append(start_utc)
            if end_utc:
                clauses.append("timestamp_utc <= ?")
                params.append(end_utc)
            query = f"""
                SELECT dataset_id, series_key, timestamp_utc, timestamp_local, value, unit,
                       quality_flag, source_updated_at, ingested_at, extra_json
                FROM {self.FINGRID_TIMESERIES_TABLE}
                WHERE {' AND '.join(clauses)}
                ORDER BY timestamp_utc ASC
            """
            if limit:
                query += " LIMIT ?"
                params.append(limit)
            cursor.execute(query, params)
            rows = cursor.fetchall()
        return [
            {
                "dataset_id": row[0],
                "series_key": row[1],
                "timestamp_utc": row[2],
                "timestamp_local": row[3],
                "value": row[4],
                "unit": row[5],
                "quality_flag": row[6],
                "source_updated_at": row[7],
                "ingested_at": row[8],
                "extra_json": json.loads(row[9]),
            }
            for row in rows
        ]

    def fetch_fingrid_sync_state(self, dataset_id: str) -> dict | None:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT dataset_id, last_success_at, last_attempt_at, last_cursor,
                       last_synced_timestamp_utc, sync_status, last_error,
                       backfill_started_at, backfill_completed_at
                FROM {self.FINGRID_SYNC_STATE_TABLE}
                WHERE dataset_id = ?
                """,
                (dataset_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {
            "dataset_id": row[0],
            "last_success_at": row[1],
            "last_attempt_at": row[2],
            "last_cursor": row[3],
            "last_synced_timestamp_utc": row[4],
            "sync_status": row[5],
            "last_error": row[6],
            "backfill_started_at": row[7],
            "backfill_completed_at": row[8],
        }

    def fetch_fingrid_dataset_coverage(self, dataset_id: str) -> dict:
        with self.get_connection() as conn:
            self.ensure_fingrid_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT MIN(timestamp_utc), MAX(timestamp_utc), COUNT(*)
                FROM {self.FINGRID_TIMESERIES_TABLE}
                WHERE dataset_id = ?
                """,
                (dataset_id,),
            )
            row = cursor.fetchone()
        return {
            "dataset_id": dataset_id,
            "coverage_start_utc": row[0],
            "coverage_end_utc": row[1],
            "record_count": row[2] or 0,
        }
```

- [ ] **Step 4: Run the storage test to verify it passes**

Run: `python -m unittest tests.test_fingrid_storage -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/database.py tests/test_fingrid_storage.py
git commit -m "feat: add Fingrid SQLite storage foundation"
```

### Task 2: Dataset Catalog And Row Normalization

**Files:**
- Create: `backend/fingrid/__init__.py`
- Create: `backend/fingrid/catalog.py`
- Create: `backend/fingrid/schemas.py`
- Create: `tests/test_fingrid_catalog.py`

- [ ] **Step 1: Write the failing catalog and normalization tests**

```python
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fingrid.catalog import get_dataset_config, list_dataset_configs
from fingrid.schemas import normalize_fingrid_row


class FingridCatalogTests(unittest.TestCase):
    def test_dataset_317_metadata_is_complete(self):
        dataset = get_dataset_config("317")

        self.assertEqual(dataset["dataset_id"], "317")
        self.assertEqual(dataset["unit"], "EUR/MW")
        self.assertEqual(dataset["timezone"], "Europe/Helsinki")
        self.assertEqual(dataset["value_kind"], "reserve_capacity_price")
        self.assertIn("month", dataset["supported_aggregations"])
        self.assertEqual(list_dataset_configs()[0]["dataset_id"], "317")

    def test_normalize_fingrid_row_accepts_startTime_shape(self):
        dataset = get_dataset_config("317")
        row = normalize_fingrid_row(
            dataset,
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-01T01:00:00Z",
                "value": 42.5,
                "updatedAt": "2026-01-01T00:05:00Z",
                "quality": "confirmed",
            },
            ingested_at="2026-04-23T00:00:00Z",
        )

        self.assertEqual(row["dataset_id"], "317")
        self.assertEqual(row["series_key"], "fcrn_hourly_market_price")
        self.assertEqual(row["timestamp_utc"], "2026-01-01T00:00:00Z")
        self.assertTrue(row["timestamp_local"].startswith("2026-01-01T02:00:00"))
        self.assertEqual(row["extra_json"]["end_time"], "2026-01-01T01:00:00Z")
```

- [ ] **Step 2: Run the catalog test to verify it fails**

Run: `python -m unittest tests.test_fingrid_catalog -v`

Expected: `ModuleNotFoundError: No module named 'fingrid'`

- [ ] **Step 3: Add the dataset registry and row normalizer**

```python
# backend/fingrid/__init__.py
from .catalog import get_dataset_config, list_dataset_configs

__all__ = [
    "get_dataset_config",
    "list_dataset_configs",
]
```

```python
# backend/fingrid/catalog.py
FINGRID_DATASETS = {
    "317": {
        "dataset_id": "317",
        "dataset_code": "fcrn_hourly_market_price",
        "name": "FCR-N hourly market prices",
        "description": "FCR-N hourly reserve-capacity market price in Finland.",
        "unit": "EUR/MW",
        "frequency": "1h",
        "timezone": "Europe/Helsinki",
        "value_kind": "reserve_capacity_price",
        "source_url": "https://data.fingrid.fi/en/datasets/317",
        "api_path": "/datasets/317/data",
        "series_key": "fcrn_hourly_market_price",
        "default_backfill_start": "2014-01-01T00:00:00Z",
        "default_incremental_lookback_days": 30,
        "supported_aggregations": ["raw", "hour", "day", "week", "month"],
        "metadata_json": {
            "market": "Fingrid",
            "product": "FCR-N",
        },
    }
}


def get_dataset_config(dataset_id: str) -> dict:
    if dataset_id not in FINGRID_DATASETS:
        raise KeyError(f"Unsupported Fingrid dataset: {dataset_id}")
    return dict(FINGRID_DATASETS[dataset_id])


def list_dataset_configs() -> list[dict]:
    return [dict(FINGRID_DATASETS[key]) for key in sorted(FINGRID_DATASETS)]
```

```python
# backend/fingrid/schemas.py
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def _parse_timestamp(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def normalize_fingrid_row(dataset: dict, raw_row: dict, *, ingested_at: str) -> dict:
    start_raw = raw_row.get("startTime") or raw_row.get("start_time")
    end_raw = raw_row.get("endTime") or raw_row.get("end_time")
    if not start_raw:
        raise ValueError("Missing startTime in Fingrid row")

    start_utc = _parse_timestamp(start_raw)
    local_tz = ZoneInfo(dataset["timezone"])
    local_dt = start_utc.astimezone(local_tz)

    return {
        "dataset_id": dataset["dataset_id"],
        "series_key": dataset["series_key"],
        "timestamp_utc": start_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "timestamp_local": local_dt.isoformat(),
        "value": raw_row.get("value"),
        "unit": dataset["unit"],
        "quality_flag": raw_row.get("quality") or raw_row.get("qualityFlag"),
        "source_updated_at": raw_row.get("updatedAt") or raw_row.get("updated_at"),
        "ingested_at": ingested_at,
        "extra_json": {
            "end_time": end_raw,
        },
    }
```

- [ ] **Step 4: Run the catalog test to verify it passes**

Run: `python -m unittest tests.test_fingrid_catalog -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/fingrid/__init__.py backend/fingrid/catalog.py backend/fingrid/schemas.py tests/test_fingrid_catalog.py
git commit -m "feat: add Fingrid dataset catalog and row normalization"
```

### Task 3: Fingrid API Client

**Files:**
- Create: `backend/fingrid/client.py`
- Create: `tests/test_fingrid_client.py`

- [ ] **Step 1: Write the failing client test**

```python
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fingrid.client import FingridClient


class FingridClientTests(unittest.TestCase):
    @mock.patch("fingrid.client.time.sleep")
    @mock.patch("fingrid.client.requests.Session.get")
    def test_fetch_dataset_window_uses_dataset_endpoint_and_headers(self, mock_get, mock_sleep):
        mock_response = mock.Mock()
        mock_response.raise_for_status.return_value = None
        mock_response.json.return_value = [
            {
                "startTime": "2026-01-01T00:00:00Z",
                "endTime": "2026-01-01T01:00:00Z",
                "value": 12.5,
            }
        ]
        mock_get.return_value = mock_response

        client = FingridClient(
            api_key="secret-key",
            base_url="https://data.fingrid.fi/api",
            request_interval_seconds=6.5,
            timeout_seconds=30,
        )
        rows = client.fetch_dataset_window(
            "317",
            start_time_utc="2026-01-01T00:00:00Z",
            end_time_utc="2026-01-31T23:00:00Z",
        )

        self.assertEqual(rows[0]["value"], 12.5)
        args, kwargs = mock_get.call_args
        self.assertEqual(args[0], "https://data.fingrid.fi/api/datasets/317/data")
        self.assertEqual(kwargs["headers"]["x-api-key"], "secret-key")
        self.assertEqual(kwargs["params"]["format"], "json")
        self.assertEqual(kwargs["params"]["sortBy"], "startTime")
        self.assertEqual(kwargs["params"]["sortOrder"], "asc")
        self.assertEqual(kwargs["params"]["pageSize"], 20000)
```

- [ ] **Step 2: Run the client test to verify it fails**

Run: `python -m unittest tests.test_fingrid_client -v`

Expected: `ModuleNotFoundError: No module named 'fingrid.client'`

- [ ] **Step 3: Implement the HTTP client with explicit throttling**

```python
# backend/fingrid/client.py
import os
import time
import requests


class FingridClient:
    def __init__(self, *, api_key: str | None = None, base_url: str | None = None,
                 request_interval_seconds: float | None = None, timeout_seconds: int | None = None):
        self.api_key = api_key or os.environ.get("FINGRID_API_KEY")
        if not self.api_key:
            raise ValueError("FINGRID_API_KEY is required")
        self.base_url = (base_url or os.environ.get("FINGRID_BASE_URL") or "https://data.fingrid.fi/api").rstrip("/")
        self.request_interval_seconds = float(
            request_interval_seconds
            if request_interval_seconds is not None
            else os.environ.get("FINGRID_REQUEST_INTERVAL_SECONDS", "6.5")
        )
        self.timeout_seconds = int(
            timeout_seconds if timeout_seconds is not None else os.environ.get("FINGRID_TIMEOUT_SECONDS", "30")
        )
        self.session = requests.Session()
        self._last_request_monotonic = 0.0

    def _throttle(self):
        elapsed = time.monotonic() - self._last_request_monotonic
        remaining = self.request_interval_seconds - elapsed
        if remaining > 0:
            time.sleep(remaining)

    def fetch_dataset_window(self, dataset_id: str, *, start_time_utc: str, end_time_utc: str,
                             page_size: int = 20000, locale: str = "en") -> list[dict]:
        self._throttle()
        response = self.session.get(
            f"{self.base_url}/datasets/{dataset_id}/data",
            headers={"x-api-key": self.api_key},
            params={
                "startTime": start_time_utc,
                "endTime": end_time_utc,
                "format": "json",
                "pageSize": page_size,
                "locale": locale,
                "sortBy": "startTime",
                "sortOrder": "asc",
            },
            timeout=self.timeout_seconds,
        )
        self._last_request_monotonic = time.monotonic()
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, list) else payload.get("data", [])
```

- [ ] **Step 4: Run the client test to verify it passes**

Run: `python -m unittest tests.test_fingrid_client -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/fingrid/client.py tests/test_fingrid_client.py
git commit -m "feat: add Fingrid API client"
```

### Task 4: Sync Orchestration And CLI

**Files:**
- Create: `backend/fingrid/service.py`
- Create: `scrapers/fingrid_sync.py`
- Create: `tests/test_fingrid_service.py`
- Modify: `backend/fingrid/__init__.py`

- [ ] **Step 1: Write the failing sync test**

```python
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

    def fetch_dataset_window(self, dataset_id: str, *, start_time_utc: str, end_time_utc: str,
                             page_size: int = 20000, locale: str = "en") -> list[dict]:
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
```

- [ ] **Step 2: Run the sync test to verify it fails**

Run: `python -m unittest tests.test_fingrid_service.FingridServiceSyncTests -v`

Expected: `ImportError` or missing `sync_dataset`

- [ ] **Step 3: Implement catalog seeding, monthly window building, and the CLI entrypoint**

```python
# backend/fingrid/service.py
from datetime import datetime, timedelta, timezone
from typing import Iterable

from .catalog import get_dataset_config, list_dataset_configs
from .client import FingridClient
from .schemas import normalize_fingrid_row


def _parse_utc(raw_value: str) -> datetime:
    return datetime.fromisoformat(raw_value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _format_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_dataset_catalog(db):
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    db.upsert_fingrid_dataset_catalog([
        {**dataset, "enabled": 1, "updated_at": now_utc}
        for dataset in list_dataset_configs()
    ])


def _month_windows(start_utc: datetime, end_utc: datetime) -> Iterable[tuple[datetime, datetime]]:
    cursor = start_utc
    while cursor < end_utc:
        if cursor.month == 12:
            next_month = cursor.replace(year=cursor.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0)
        else:
            next_month = cursor.replace(month=cursor.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0)
        window_end = min(next_month, end_utc)
        yield cursor, window_end
        cursor = window_end


def sync_dataset(db, *, dataset_id: str, mode: str, start: str | None = None, end: str | None = None,
                 client: FingridClient | None = None, ingested_at: str | None = None) -> dict:
    dataset = get_dataset_config(dataset_id)
    seed_dataset_catalog(db)
    client = client or FingridClient()
    now_utc = datetime.now(timezone.utc)
    ingested_at = ingested_at or _format_utc(now_utc)

    if mode == "backfill":
        start_utc = _parse_utc(start or dataset["default_backfill_start"])
    else:
        lookback_days = int(dataset["default_incremental_lookback_days"])
        start_utc = _parse_utc(start) if start else now_utc - timedelta(days=lookback_days)
    end_utc = _parse_utc(end) if end else now_utc

    db.upsert_fingrid_sync_state(
        dataset_id=dataset_id,
        last_success_at=None,
        last_attempt_at=_format_utc(now_utc),
        last_cursor=None,
        last_synced_timestamp_utc=None,
        sync_status="running",
        last_error=None,
        backfill_started_at=_format_utc(now_utc) if mode == "backfill" else None,
        backfill_completed_at=None,
    )

    records_upserted = 0
    last_timestamp_utc = None
    windows_synced = 0

    for window_start, window_end in _month_windows(start_utc, end_utc):
        raw_rows = client.fetch_dataset_window(
            dataset_id,
            start_time_utc=_format_utc(window_start),
            end_time_utc=_format_utc(window_end),
        )
        normalized_rows = [
            normalize_fingrid_row(dataset, row, ingested_at=ingested_at)
            for row in raw_rows
        ]
        db.upsert_fingrid_timeseries(normalized_rows)
        windows_synced += 1
        records_upserted += len(normalized_rows)
        if normalized_rows:
            last_timestamp_utc = normalized_rows[-1]["timestamp_utc"]

    db.upsert_fingrid_sync_state(
        dataset_id=dataset_id,
        last_success_at=_format_utc(now_utc),
        last_attempt_at=_format_utc(now_utc),
        last_cursor=last_timestamp_utc,
        last_synced_timestamp_utc=last_timestamp_utc,
        sync_status="ok",
        last_error=None,
        backfill_started_at=None,
        backfill_completed_at=_format_utc(now_utc) if mode == "backfill" else None,
    )
    return {
        "dataset_id": dataset_id,
        "mode": mode,
        "windows_synced": windows_synced,
        "records_upserted": records_upserted,
        "last_synced_timestamp_utc": last_timestamp_utc,
    }
```

```python
# scrapers/fingrid_sync.py
import argparse
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "../backend")))

from database import DatabaseManager
from fingrid.service import sync_dataset


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fingrid dataset sync")
    parser.add_argument("--dataset", required=True, help="Fingrid dataset id, for example 317")
    parser.add_argument("--mode", required=True, choices=["backfill", "incremental"])
    parser.add_argument("--start", help="Optional UTC ISO-8601 start")
    parser.add_argument("--end", help="Optional UTC ISO-8601 end")
    parser.add_argument("--db", default="../data/aemo_data.db")
    args = parser.parse_args()

    db = DatabaseManager(args.db)
    result = sync_dataset(
        db,
        dataset_id=args.dataset,
        mode=args.mode,
        start=args.start,
        end=args.end,
    )
    print(result)
```

```python
# backend/fingrid/__init__.py
from .catalog import get_dataset_config, list_dataset_configs
from .service import get_dataset_series_payload, get_dataset_status_payload, get_dataset_summary_payload, sync_dataset

__all__ = [
    "get_dataset_config",
    "list_dataset_configs",
    "get_dataset_series_payload",
    "get_dataset_status_payload",
    "get_dataset_summary_payload",
    "sync_dataset",
]
```

- [ ] **Step 4: Run the sync test to verify it passes**

Run: `python -m unittest tests.test_fingrid_service.FingridServiceSyncTests -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/fingrid/__init__.py backend/fingrid/service.py scrapers/fingrid_sync.py tests/test_fingrid_service.py
git commit -m "feat: add Fingrid sync orchestration"
```

### Task 5: Query, Aggregation, Summary, And CSV Export

**Files:**
- Modify: `backend/fingrid/service.py`
- Create: `backend/fingrid/export.py`
- Modify: `tests/test_fingrid_service.py`

- [ ] **Step 1: Extend the service test with query and summary expectations**

```python
from fingrid.export import build_fingrid_csv
from fingrid.service import get_dataset_series_payload, get_dataset_summary_payload

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
```

- [ ] **Step 2: Run the service test to verify it fails**

Run: `python -m unittest tests.test_fingrid_service -v`

Expected: missing `get_dataset_series_payload`, `get_dataset_summary_payload`, or `build_fingrid_csv`

- [ ] **Step 3: Add Python-side aggregation, summary payloads, and CSV generation**

```python
# backend/fingrid/export.py
import csv
import io


def build_fingrid_csv(series: list[dict]) -> str:
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=["timestamp", "timestamp_utc", "value", "unit"])
    writer.writeheader()
    for row in series:
        writer.writerow(
            {
                "timestamp": row["timestamp"],
                "timestamp_utc": row["timestamp_utc"],
                "value": row["value"],
                "unit": row["unit"],
            }
        )
    return buffer.getvalue()
```

```python
# backend/fingrid/service.py
from collections import defaultdict
from statistics import mean
from zoneinfo import ZoneInfo


def _bucket_key(local_dt, aggregation: str):
    if aggregation in {"raw", "hour"}:
        return local_dt.replace(minute=0, second=0, microsecond=0)
    if aggregation == "day":
        return local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
    if aggregation == "week":
        iso_year, iso_week, _ = local_dt.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if aggregation == "month":
        return local_dt.strftime("%Y-%m-01T00:00:00")
    raise ValueError(f"Unsupported aggregation: {aggregation}")


def _aggregate_rows(rows: list[dict], *, aggregation: str, tz_name: str) -> list[dict]:
    if aggregation == "raw":
        return [
            {
                "timestamp": row["timestamp_local"],
                "timestamp_utc": row["timestamp_utc"],
                "value": row["value"],
                "unit": row["unit"],
            }
            for row in rows
        ]

    tz = ZoneInfo(tz_name)
    buckets = defaultdict(list)
    for row in rows:
        utc_dt = _parse_utc(row["timestamp_utc"])
        local_dt = utc_dt.astimezone(tz)
        buckets[_bucket_key(local_dt, aggregation)].append(row["value"])

    items = []
    for key, values in sorted(buckets.items(), key=lambda item: str(item[0])):
        timestamp = key if isinstance(key, str) else key.isoformat()
        items.append(
            {
                "timestamp": timestamp,
                "timestamp_utc": timestamp,
                "value": round(mean(values), 4),
                "unit": rows[0]["unit"] if rows else "EUR/MW",
            }
        )
    return items


def _build_summary_kpis(rows: list[dict]) -> dict:
    values = [row["value"] for row in rows if row["value"] is not None]
    if not values:
        return {
            "latest_value": None,
            "latest_timestamp": None,
            "avg_24h": None,
            "avg_7d": None,
            "avg_30d": None,
            "min_value": None,
            "max_value": None,
        }
    latest = rows[-1]
    return {
        "latest_value": latest["value"],
        "latest_timestamp": latest["timestamp_utc"],
        "avg_24h": round(mean(values[-24:]), 4),
        "avg_7d": round(mean(values[-(24 * 7):]), 4),
        "avg_30d": round(mean(values[-(24 * 30):]), 4),
        "min_value": min(values),
        "max_value": max(values),
    }


def _hourly_profile(rows: list[dict], tz_name: str) -> list[dict]:
    tz = ZoneInfo(tz_name)
    buckets = defaultdict(list)
    for row in rows:
        local_dt = _parse_utc(row["timestamp_utc"]).astimezone(tz)
        buckets[local_dt.hour].append(row["value"])
    return [
        {"hour": hour, "avg_value": round(mean(values), 4)}
        for hour, values in sorted(buckets.items())
    ]


def _yearly_average_series(rows: list[dict], tz_name: str) -> list[dict]:
    tz = ZoneInfo(tz_name)
    buckets = defaultdict(list)
    for row in rows:
        local_dt = _parse_utc(row["timestamp_utc"]).astimezone(tz)
        buckets[local_dt.year].append(row["value"])
    return [
        {
            "timestamp": f"{year}-01-01T00:00:00",
            "timestamp_utc": f"{year}-01-01T00:00:00Z",
            "value": round(mean(values), 4),
            "unit": rows[0]["unit"] if rows else "EUR/MW",
        }
        for year, values in sorted(buckets.items())
    ]


def get_dataset_series_payload(db, *, dataset_id: str, start: str | None, end: str | None,
                               aggregation: str, tz: str, limit: int) -> dict:
    dataset = get_dataset_config(dataset_id)
    rows = db.fetch_fingrid_series(dataset_id=dataset_id, start_utc=start, end_utc=end, limit=limit)
    return {
        "dataset": dataset,
        "query": {"start": start, "end": end, "aggregation": aggregation, "tz": tz, "limit": limit},
        "series": _aggregate_rows(rows, aggregation=aggregation, tz_name=tz),
    }


def get_dataset_summary_payload(db, *, dataset_id: str, start: str | None, end: str | None) -> dict:
    dataset = get_dataset_config(dataset_id)
    rows = db.fetch_fingrid_series(dataset_id=dataset_id, start_utc=start, end_utc=end)
    return {
        "dataset": dataset,
        "window": {"start": start, "end": end},
        "kpis": _build_summary_kpis(rows),
        "monthly_average_series": _aggregate_rows(rows, aggregation="month", tz_name=dataset["timezone"]),
        "yearly_average_series": _yearly_average_series(rows, dataset["timezone"]),
        "hourly_profile": _hourly_profile(rows, dataset["timezone"]),
    }


def get_dataset_status_payload(db, *, dataset_id: str) -> dict:
    dataset = get_dataset_config(dataset_id)
    coverage = db.fetch_fingrid_dataset_coverage(dataset_id)
    sync_state = db.fetch_fingrid_sync_state(dataset_id) or {
        "dataset_id": dataset_id,
        "last_success_at": None,
        "last_attempt_at": None,
        "last_cursor": None,
        "last_synced_timestamp_utc": None,
        "sync_status": "idle",
        "last_error": None,
        "backfill_started_at": None,
        "backfill_completed_at": None,
    }
    return {
        "dataset": dataset,
        "status": {
            **sync_state,
            **coverage,
        },
    }
```

- [ ] **Step 4: Run the service test to verify it passes**

Run: `python -m unittest tests.test_fingrid_service -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/fingrid/service.py backend/fingrid/export.py tests/test_fingrid_service.py
git commit -m "feat: add Fingrid query summaries and export"
```

### Task 6: FastAPI Fingrid Endpoints

**Files:**
- Create: `tests/test_fingrid_api.py`
- Modify: `backend/server.py`

- [ ] **Step 1: Write the failing API test**

```python
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
```

- [ ] **Step 2: Run the API test to verify it fails**

Run: `python -m unittest tests.test_fingrid_api -v`

Expected: missing `get_fingrid_datasets` / `sync_fingrid_dataset`

- [ ] **Step 3: Add the Fingrid route group to the existing FastAPI server**

```python
# backend/server.py
from fastapi import Response

from fingrid import catalog as fingrid_catalog
from fingrid import service as fingrid_service
from fingrid.export import build_fingrid_csv


@app.get("/api/fingrid/datasets")
def get_fingrid_datasets():
    fingrid_service.seed_dataset_catalog(db)
    return {"datasets": fingrid_catalog.list_dataset_configs()}


@app.get("/api/fingrid/datasets/{dataset_id}/status")
def get_fingrid_dataset_status(dataset_id: str):
    try:
        return fingrid_service.get_dataset_status_payload(db, dataset_id=dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")


@app.post("/api/fingrid/datasets/{dataset_id}/sync")
def sync_fingrid_dataset(dataset_id: str, background_tasks: BackgroundTasks, mode: str = Query("incremental")):
    try:
        fingrid_catalog.get_dataset_config(dataset_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")
    background_tasks.add_task(fingrid_service.sync_dataset, db, dataset_id=dataset_id, mode=mode)
    return {"status": "accepted", "dataset_id": dataset_id, "mode": mode}


@app.get("/api/fingrid/datasets/{dataset_id}/series")
def get_fingrid_dataset_series(
    dataset_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    tz: str = Query("Europe/Helsinki"),
    aggregation: str = Query("raw", pattern="^(raw|hour|day|week|month)$"),
    limit: int = Query(5000),
):
    try:
        return fingrid_service.get_dataset_series_payload(
            db,
            dataset_id=dataset_id,
            start=start,
            end=end,
            aggregation=aggregation,
            tz=tz,
            limit=limit,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")


@app.get("/api/fingrid/datasets/{dataset_id}/summary")
def get_fingrid_dataset_summary(
    dataset_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
):
    try:
        return fingrid_service.get_dataset_summary_payload(db, dataset_id=dataset_id, start=start, end=end)
    except KeyError:
        raise HTTPException(status_code=404, detail="Unsupported Fingrid dataset")


@app.get("/api/fingrid/datasets/{dataset_id}/export")
def export_fingrid_dataset_csv(
    dataset_id: str,
    start: Optional[str] = Query(None),
    end: Optional[str] = Query(None),
    tz: str = Query("Europe/Helsinki"),
    aggregation: str = Query("raw", pattern="^(raw|hour|day|week|month)$"),
    limit: int = Query(5000),
):
    payload = fingrid_service.get_dataset_series_payload(
        db,
        dataset_id=dataset_id,
        start=start,
        end=end,
        aggregation=aggregation,
        tz=tz,
        limit=limit,
    )
    csv_text = build_fingrid_csv(payload["series"])
    return Response(
        content=csv_text,
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename=\"fingrid-{dataset_id}.csv\"'},
    )
```

- [ ] **Step 4: Run the API test to verify it passes**

Run: `python -m unittest tests.test_fingrid_api -v`

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add backend/server.py tests/test_fingrid_api.py
git commit -m "feat: add Fingrid API endpoints"
```

### Task 7: Frontend Data Utilities And Route Selection

**Files:**
- Create: `web/src/lib/fingridApi.js`
- Create: `web/src/lib/fingridDataset.js`
- Create: `web/src/lib/pageRouter.js`
- Create: `web/src/lib/fingridApi.test.js`
- Create: `web/src/lib/fingridDataset.test.js`
- Create: `web/src/lib/pageRouter.test.js`
- Modify: `web/src/main.jsx`

- [ ] **Step 1: Write the failing Node tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildFingridSeriesUrl,
  buildFingridSummaryUrl,
  buildFingridSyncUrl,
  normalizeFingridDatasetList,
} from './fingridApi.js';
import {
  buildPresetWindow,
  buildHourlyProfile,
  formatFingridValue,
} from './fingridDataset.js';
import { resolveRootPage } from './pageRouter.js';

test('buildFingridSeriesUrl encodes dataset and query controls', () => {
  const url = buildFingridSeriesUrl('http://127.0.0.1:8085/api', {
    datasetId: '317',
    start: '2026-01-01T00:00:00Z',
    end: '2026-01-02T00:00:00Z',
    tz: 'Europe/Helsinki',
    aggregation: 'day',
    limit: 200,
  });

  assert.match(url, /datasets\\/317\\/series/);
  assert.match(url, /aggregation=day/);
  assert.match(url, /tz=Europe%2FHelsinki/);
  assert.match(url, /limit=200/);
});

test('normalizeFingridDatasetList falls back to an empty array', () => {
  assert.deepEqual(normalizeFingridDatasetList({}), []);
  assert.equal(normalizeFingridDatasetList({ datasets: [{ dataset_id: '317' }] })[0].dataset_id, '317');
});

test('buildPresetWindow returns bounded ISO timestamps', () => {
  const window = buildPresetWindow('30d', new Date('2026-04-23T00:00:00Z'));
  assert.equal(window.end, '2026-04-23T00:00:00.000Z');
  assert.match(window.start, /^2026-03-/);
});

test('buildHourlyProfile averages values by local hour', () => {
  const profile = buildHourlyProfile([
    { timestamp: '2026-01-01T02:00:00+02:00', value: 10 },
    { timestamp: '2026-01-02T02:00:00+02:00', value: 14 },
  ]);
  assert.deepEqual(profile, [{ hour: 2, avg_value: 12 }]);
});

test('formatFingridValue appends the dataset unit', () => {
  assert.equal(formatFingridValue(12.3456, 'EUR/MW'), '12.35 EUR/MW');
});

test('resolveRootPage switches to the Fingrid page on /fingrid paths', () => {
  assert.equal(resolveRootPage('/fingrid'), 'fingrid');
  assert.equal(resolveRootPage('/fingrid/317'), 'fingrid');
  assert.equal(resolveRootPage('/'), 'aemo');
});
```

- [ ] **Step 2: Run the Node tests to verify they fail**

Run: `node --test web/src/lib/fingridApi.test.js web/src/lib/fingridDataset.test.js web/src/lib/pageRouter.test.js`

Expected: `ERR_MODULE_NOT_FOUND`

- [ ] **Step 3: Implement the pure helpers and the pathname switch**

```javascript
// web/src/lib/fingridApi.js
export function buildFingridSeriesUrl(apiBase, { datasetId, start, end, tz, aggregation, limit }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  if (aggregation) params.set('aggregation', aggregation);
  if (limit) params.set('limit', String(limit));
  return `${apiBase}/fingrid/datasets/${datasetId}/series?${params.toString()}`;
}

export function buildFingridSummaryUrl(apiBase, { datasetId, start, end }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  return `${apiBase}/fingrid/datasets/${datasetId}/summary?${params.toString()}`;
}

export function buildFingridStatusUrl(apiBase, datasetId) {
  return `${apiBase}/fingrid/datasets/${datasetId}/status`;
}

export function buildFingridSyncUrl(apiBase, datasetId, mode = 'incremental') {
  return `${apiBase}/fingrid/datasets/${datasetId}/sync?mode=${encodeURIComponent(mode)}`;
}

export function buildFingridExportUrl(apiBase, { datasetId, start, end, tz, aggregation, limit }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  if (aggregation) params.set('aggregation', aggregation);
  if (limit) params.set('limit', String(limit));
  return `${apiBase}/fingrid/datasets/${datasetId}/export?${params.toString()}`;
}

export function normalizeFingridDatasetList(payload = {}) {
  return Array.isArray(payload.datasets) ? payload.datasets : [];
}
```

```javascript
// web/src/lib/fingridDataset.js
const DAY_MS = 24 * 60 * 60 * 1000;

export function buildPresetWindow(preset, now = new Date()) {
  const endDate = new Date(now);
  const presetDays = {
    '7d': 7,
    '30d': 30,
    '90d': 90,
    '1y': 365,
  };
  if (preset === 'all') {
    return { start: null, end: endDate.toISOString() };
  }
  const days = presetDays[preset] ?? 30;
  const startDate = new Date(endDate.getTime() - (days * DAY_MS));
  return { start: startDate.toISOString(), end: endDate.toISOString() };
}

export function formatFingridValue(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return `n/a ${unit}`;
  }
  return `${Number(value).toFixed(2)} ${unit}`;
}

export function buildHourlyProfile(series = []) {
  const buckets = new Map();
  for (const point of series) {
    const timestamp = new Date(point.timestamp);
    const hour = timestamp.getHours();
    const values = buckets.get(hour) || [];
    values.push(Number(point.value));
    buckets.set(hour, values);
  }
  return [...buckets.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([hour, values]) => ({
      hour,
      avg_value: Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(4)),
    }));
}
```

```javascript
// web/src/lib/pageRouter.js
export function resolveRootPage(pathname = '/') {
  return pathname.startsWith('/fingrid') ? 'fingrid' : 'aemo';
}
```

```javascript
// web/src/main.jsx
import { StrictMode } from 'react';
import { createRoot } from 'react-dom/client';
import './index.css';
import App from './App.jsx';
import FingridPage from './pages/FingridPage.jsx';
import { resolveRootPage } from './lib/pageRouter';

const page = resolveRootPage(globalThis.location?.pathname || '/');
const RootPage = page === 'fingrid' ? FingridPage : App;

createRoot(document.getElementById('root')).render(
  <StrictMode>
    <RootPage />
  </StrictMode>,
);
```

- [ ] **Step 4: Run the Node tests to verify they pass**

Run: `node --test web/src/lib/fingridApi.test.js web/src/lib/fingridDataset.test.js web/src/lib/pageRouter.test.js`

Expected: all tests `pass`

- [ ] **Step 5: Commit**

```bash
git add web/src/lib/fingridApi.js web/src/lib/fingridDataset.js web/src/lib/pageRouter.js web/src/lib/fingridApi.test.js web/src/lib/fingridDataset.test.js web/src/lib/pageRouter.test.js web/src/main.jsx
git commit -m "feat: add Fingrid frontend data helpers"
```

### Task 8: Standalone Fingrid Page And Components

**Files:**
- Create: `web/src/lib/fingridPage.test.js`
- Create: `web/src/pages/FingridPage.jsx`
- Create: `web/src/components/fingrid/FingridHeader.jsx`
- Create: `web/src/components/fingrid/FingridSummaryCards.jsx`
- Create: `web/src/components/fingrid/FingridSeriesChart.jsx`
- Create: `web/src/components/fingrid/FingridDistributionPanel.jsx`
- Create: `web/src/components/fingrid/FingridStatusPanel.jsx`

- [ ] **Step 1: Write a failing smoke test that proves the route is isolated from NEM/WEM UI state**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('FingridPage uses dataset controls instead of NEM region filters', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /buildFingridSeriesUrl/);
  assert.match(source, /datasetId/);
  assert.equal(source.includes('selectedRegion'), false);
  assert.equal(source.includes('price-trend'), false);
});
```

- [ ] **Step 2: Run the smoke test to verify it fails**

Run: `node --test web/src/lib/fingridPage.test.js`

Expected: `ENOENT` for missing `web/src/pages/FingridPage.jsx`

- [ ] **Step 3: Implement the page, data fetch flow, and lightweight charts**

```javascript
// web/src/pages/FingridPage.jsx
import { useEffect, useMemo, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import {
  buildFingridSeriesUrl,
  buildFingridSummaryUrl,
  buildFingridStatusUrl,
  buildFingridSyncUrl,
  buildFingridExportUrl,
  normalizeFingridDatasetList,
} from '../lib/fingridApi';
import { buildPresetWindow } from '../lib/fingridDataset';
import FingridHeader from '../components/fingrid/FingridHeader';
import FingridSummaryCards from '../components/fingrid/FingridSummaryCards';
import FingridSeriesChart from '../components/fingrid/FingridSeriesChart';
import FingridDistributionPanel from '../components/fingrid/FingridDistributionPanel';
import FingridStatusPanel from '../components/fingrid/FingridStatusPanel';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';

export default function FingridPage() {
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetId] = useState('317');
  const [preset, setPreset] = useState('30d');
  const [aggregation, setAggregation] = useState('day');
  const [tz, setTz] = useState('Europe/Helsinki');
  const [seriesPayload, setSeriesPayload] = useState(null);
  const [summaryPayload, setSummaryPayload] = useState(null);
  const [statusPayload, setStatusPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    fetchJson(`${API_BASE}/fingrid/datasets`)
      .then((payload) => setDatasets(normalizeFingridDatasetList(payload)))
      .catch((err) => setError(String(err)));
  }, []);

  const timeWindow = useMemo(() => buildPresetWindow(preset), [preset]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      fetchJson(buildFingridSeriesUrl(API_BASE, { datasetId, ...timeWindow, tz, aggregation, limit: 5000 })),
      fetchJson(buildFingridSummaryUrl(API_BASE, { datasetId, ...timeWindow })),
      fetchJson(buildFingridStatusUrl(API_BASE, datasetId)),
    ])
      .then(([seriesData, summaryData, statusData]) => {
        if (cancelled) return;
        setSeriesPayload(seriesData);
        setSummaryPayload(summaryData);
        setStatusPayload(statusData);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError(String(err));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [datasetId, preset, aggregation, tz, timeWindow.start, timeWindow.end]);

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fetch(buildFingridSyncUrl(API_BASE, datasetId), { method: 'POST' });
      const statusData = await fetchJson(buildFingridStatusUrl(API_BASE, datasetId));
      setStatusPayload(statusData);
    } finally {
      setSyncing(false);
    }
  };

  const exportHref = buildFingridExportUrl(API_BASE, {
    datasetId,
    ...timeWindow,
    tz,
    aggregation,
    limit: 5000,
  });

  return (
    <main className="min-h-screen bg-[var(--color-background)] px-6 py-8 text-[var(--color-text)]">
      <div className="mx-auto grid max-w-7xl gap-6">
        <FingridHeader
          datasets={datasets}
          datasetId={datasetId}
          onDatasetChange={setDatasetId}
          preset={preset}
          onPresetChange={setPreset}
          aggregation={aggregation}
          onAggregationChange={setAggregation}
          tz={tz}
          onTimezoneChange={setTz}
          statusPayload={statusPayload}
          onSync={handleSync}
          syncing={syncing}
          exportHref={exportHref}
        />
        <FingridSummaryCards payload={summaryPayload} loading={loading} />
        <FingridSeriesChart payload={seriesPayload} loading={loading} error={error} />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
          <FingridDistributionPanel payload={summaryPayload} loading={loading} />
          <FingridStatusPanel payload={statusPayload} loading={loading} error={error} />
        </div>
      </div>
    </main>
  );
}
```

```javascript
// web/src/components/fingrid/FingridHeader.jsx
export default function FingridHeader(props) {
  const dataset = props.datasets.find((item) => item.dataset_id === props.datasetId) || {};
  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">Fingrid</div>
          <h1 className="mt-2 text-3xl font-serif">{dataset.name || 'Dataset 317'}</h1>
          <p className="mt-2 text-sm text-[var(--color-muted)]">{dataset.description}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs uppercase tracking-widest text-[var(--color-muted)]">
            <span>{dataset.dataset_id}</span>
            <span>{dataset.unit}</span>
            <span>{dataset.frequency}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <select value={props.datasetId} onChange={(event) => props.onDatasetChange(event.target.value)}>{props.datasets.map((item) => <option key={item.dataset_id} value={item.dataset_id}>{item.name}</option>)}</select>
          <select value={props.preset} onChange={(event) => props.onPresetChange(event.target.value)}>{['7d','30d','90d','1y','all'].map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={props.aggregation} onChange={(event) => props.onAggregationChange(event.target.value)}>{['raw','day','week','month'].map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <select value={props.tz} onChange={(event) => props.onTimezoneChange(event.target.value)}>{['Europe/Helsinki','UTC'].map((item) => <option key={item} value={item}>{item}</option>)}</select>
          <button onClick={props.onSync} disabled={props.syncing}>{props.syncing ? 'Syncing...' : 'Sync'}</button>
          <a href={props.exportHref}>Export CSV</a>
        </div>
      </div>
    </section>
  );
}
```

```javascript
// web/src/components/fingrid/FingridSummaryCards.jsx
import { formatFingridValue } from '../../lib/fingridDataset';

export default function FingridSummaryCards({ payload, loading }) {
  const kpis = payload?.kpis || {};
  const unit = payload?.dataset?.unit || 'EUR/MW';
  const cards = [
    ['Latest', kpis.latest_value],
    ['24h Avg', kpis.avg_24h],
    ['7d Avg', kpis.avg_7d],
    ['30d Avg', kpis.avg_30d],
    ['Min', kpis.min_value],
    ['Max', kpis.max_value],
  ];
  return (
    <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
      {cards.map(([label, value]) => (
        <div key={label} className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div className="text-[11px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
          <div className="mt-2 text-xl font-serif">{loading ? 'Loading...' : formatFingridValue(value, unit)}</div>
        </div>
      ))}
    </section>
  );
}
```

```javascript
// web/src/components/fingrid/FingridSeriesChart.jsx
import { Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';

export default function FingridSeriesChart({ payload, loading, error }) {
  if (loading) return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">Loading chart...</section>;
  if (error) return <section className="rounded border border-rose-200 bg-rose-50 p-6 text-rose-700">{error}</section>;
  const series = payload?.series || [];
  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">Time Series</div>
      <div className="h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" minTickGap={48} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="value" stroke="#0f766e" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
```

```javascript
// web/src/components/fingrid/FingridDistributionPanel.jsx
import { Bar, BarChart, ResponsiveContainer, Tooltip, XAxis, YAxis, CartesianGrid } from 'recharts';

export default function FingridDistributionPanel({ payload, loading }) {
  const monthly = payload?.monthly_average_series || [];
  const hourly = payload?.hourly_profile || [];
  if (loading) return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">Loading distributions...</section>;
  return (
    <section className="grid gap-6">
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">Monthly Average</div>
        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" minTickGap={36} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#0369a1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">Hourly Profile</div>
        <div className="h-[240px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hourly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="avg_value" fill="#7c3aed" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
```

```javascript
// web/src/components/fingrid/FingridStatusPanel.jsx
export default function FingridStatusPanel({ payload, loading, error }) {
  const status = payload?.status || {};
  if (loading) return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">Loading status...</section>;
  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="text-sm uppercase tracking-widest text-[var(--color-muted)]">Sync Status</div>
      <div className="mt-4 grid gap-3 text-sm">
        <div>Status: {status.sync_status || 'idle'}</div>
        <div>Last success: {status.last_success_at || 'n/a'}</div>
        <div>Coverage start: {status.coverage_start_utc || 'n/a'}</div>
        <div>Coverage end: {status.coverage_end_utc || 'n/a'}</div>
        <div>Records: {status.record_count || 0}</div>
        <div>Last error: {status.last_error || error || 'none'}</div>
      </div>
    </section>
  );
}
```

- [ ] **Step 4: Run the smoke test and build to verify the page is wired correctly**

Run: `node --test web/src/lib/fingridPage.test.js`

Expected: `pass`

Run: `cd web && npm run build`

Expected: `vite build` completes successfully

- [ ] **Step 5: Commit**

```bash
git add web/src/pages/FingridPage.jsx web/src/components/fingrid/FingridHeader.jsx web/src/components/fingrid/FingridSummaryCards.jsx web/src/components/fingrid/FingridSeriesChart.jsx web/src/components/fingrid/FingridDistributionPanel.jsx web/src/components/fingrid/FingridStatusPanel.jsx web/src/lib/fingridPage.test.js
git commit -m "feat: add standalone Fingrid analytics page"
```

### Task 9: README And End-To-End Verification

**Files:**
- Modify: `README.md`

- [ ] **Step 1: Add the new env vars, sync commands, and route to the README**

~~~md
## Fingrid Open Data

Set these environment variables before using the Fingrid endpoints or sync CLI:

```bash
set FINGRID_API_KEY=your-key-here
set FINGRID_BASE_URL=https://data.fingrid.fi/api
set FINGRID_REQUEST_INTERVAL_SECONDS=6.5
set FINGRID_TIMEOUT_SECONDS=30
set FINGRID_DEFAULT_BACKFILL_START=2014-01-01T00:00:00Z
set FINGRID_DEFAULT_INCREMENTAL_LOOKBACK_DAYS=30
```

Backfill dataset `317`:

```bash
python scrapers/fingrid_sync.py --dataset 317 --mode backfill
```

Incremental refresh:

```bash
python scrapers/fingrid_sync.py --dataset 317 --mode incremental
```

Frontend route:

```text
http://127.0.0.1:5173/fingrid
```
~~~

- [ ] **Step 2: Run the full backend verification**

Run: `python -m unittest tests.test_fingrid_storage tests.test_fingrid_catalog tests.test_fingrid_client tests.test_fingrid_service tests.test_fingrid_api -v`

Expected: all tests `OK`

- [ ] **Step 3: Run the full frontend verification**

Run: `node --test web/src/lib/fingridApi.test.js web/src/lib/fingridDataset.test.js web/src/lib/pageRouter.test.js web/src/lib/fingridPage.test.js`

Expected: all tests `pass`

Run: `cd web && npm run build`

Expected: build succeeds

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: document Fingrid datasource usage"
```

- [ ] **Step 5: Keep the commit history reviewable**

Stop here. Do not create an extra squashed commit yet; keep the per-task commits intact so the reviewer can inspect storage, client, API, and UI separately.

## Final Verification Checklist

- `python -m unittest discover -s tests -v`
- `python -m unittest backend.test_investment_api -v`
- `node --test web/src/lib/apiClient.test.js web/src/lib/eventOverlays.test.js web/src/lib/eventPanelPlacement.test.js web/src/lib/gridForecast.test.js web/src/lib/investmentAnalysis.test.js web/src/lib/fingridApi.test.js web/src/lib/fingridDataset.test.js web/src/lib/pageRouter.test.js web/src/lib/fingridPage.test.js`
- `cd web && npm run lint`
- `cd web && npm run build`

If any legacy test unrelated to Fingrid fails, fix it in a separate commit instead of folding it into the Fingrid feature branch.
