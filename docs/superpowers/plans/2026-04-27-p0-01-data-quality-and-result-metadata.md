# P0-01 Data Quality And Result Metadata Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 涓哄綋鍓嶅垎鏋愬瀷 API 寤虹珛缁熶竴缁撴灉鍏冩暟鎹绾﹀拰 Data Quality Center v1锛岃鏍稿績缁撴灉甯︿笂 `data_grade`銆乣data_quality_score`銆乣coverage`銆乣freshness`銆乣source_version`銆乣methodology_version` 绛夊瓧娈碉紝骞舵彁渚涘彲鏌ヨ鐨勬暟鎹川閲忔憳瑕佹帴鍙ｃ€?
**Architecture:** 鍚庣鏂板涓€涓交閲忔暟鎹川閲忓眰锛岃礋璐ｈ绠楀拰缂撳瓨 NEM/WEM/Fingrid 鐨勮川閲忓揩鐓э紱鍚屾椂鏂板缁熶竴 metadata builder锛屾妸鐜版湁鍒嗘瀽鎺ュ彛鐨勫搷搴斿寘瑁呬负 `{ data, metadata }` 鎴栧湪鏃㈡湁 payload 涓ˉ `metadata` 瀛楁銆傚墠绔厛鍋氭渶灏忓睍绀哄眰锛屽湪婢虫床涓诲伐浣滃彴鍜?Fingrid 椤甸潰鏄惧紡灞曠ず data grade 涓庤川閲忔憳瑕侊紝涓嶆敼鍙樼幇鏈夐〉闈富缁撴瀯銆?
**Tech Stack:** FastAPI, SQLite, Python unittest, React, node:test

---

## 鏂囦欢缁撴瀯

### 鏂板鏂囦欢

- `backend/result_metadata.py`
  - 缁熶竴鏋勫缓鎺ュ彛 metadata
- `backend/data_quality.py`
  - 鏁版嵁璐ㄩ噺蹇収璁＄畻涓庢憳瑕佹煡璇?- `tests/test_result_metadata.py`
  - metadata 濂戠害娴嬭瘯
- `tests/test_data_quality.py`
  - 鏁版嵁璐ㄩ噺璁＄畻涓庢帴鍙ｆ祴璇?- `web/src/components/DataQualityBadge.jsx`
  - 缁熶竴灞曠ず `data_grade`銆乣data_quality_score`
- `web/src/lib/resultMetadata.js`
  - 鍓嶇 metadata 璇诲彇涓庢牸寮忓寲
- `web/src/lib/resultMetadata.test.js`
  - 鍓嶇 metadata 宸ュ叿娴嬭瘯

### 淇敼鏂囦欢

- `backend/database.py`
  - 鏂板鏁版嵁璐ㄩ噺琛ㄤ笌璇诲啓鏂规硶
- `backend/server.py`
  - 鎸傛帴 metadata builder
  - 鏂板 `/api/data-quality/*` 鎺ュ彛
  - 涓轰富鍒嗘瀽鎺ュ彛杩斿洖 metadata
- `tests/test_fingrid_api.py`
  - 琛?Fingrid metadata 涓?data-quality 璺敱娴嬭瘯
- `web/src/App.jsx`
  - 涓诲伐浣滃彴 metadata 灞曠ず
- `web/src/pages/FingridPage.jsx`
  - Fingrid metadata / 璐ㄩ噺鎻愮ず灞曠ず
- `web/src/components/RevenueStacking.jsx`
  - WEM preview / grade 灞曠ず缁熶竴鎺?metadata
- `docs/椤圭洰鍏ㄩ潰瑙ｆ瀽鎬诲唽.md`
  - 琛ュ厖 data quality / metadata 绔犺妭
- `README.md`
  - 琛ュ厖鏂扮殑 API 鍜岄獙璇佸懡浠?
---

### Task 1: 寤虹珛鍚庣 metadata 濂戠害

**Files:**
- Create: `backend/result_metadata.py`
- Modify: `backend/server.py`
- Test: `tests/test_result_metadata.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇曪紝閿佸畾 metadata 鍩烘湰濂戠害**

```python
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from result_metadata import build_result_metadata


class ResultMetadataTests(unittest.TestCase):
    def test_build_result_metadata_returns_required_fields(self):
        payload = build_result_metadata(
            market="NEM",
            region_or_zone="NSW1",
            timezone="Australia/Sydney",
            currency="AUD",
            unit="AUD/MWh",
            interval_minutes=5,
            data_grade="analytical",
            data_quality_score=0.94,
            coverage={"expected_intervals": 288, "actual_intervals": 288, "coverage_ratio": 1.0},
            freshness={"lag_minutes": 15, "last_updated_at": "2026-04-27T00:15:00Z"},
            source_name="AEMO",
            source_version="2026-04-27",
            methodology_version="price_trend_v1",
            warnings=[],
        )

        self.assertEqual(payload["market"], "NEM")
        self.assertEqual(payload["region_or_zone"], "NSW1")
        self.assertEqual(payload["currency"], "AUD")
        self.assertEqual(payload["unit"], "AUD/MWh")
        self.assertEqual(payload["data_grade"], "analytical")
        self.assertIn("coverage", payload)
        self.assertIn("freshness", payload)
        self.assertIn("methodology_version", payload)
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

Run: `python -m unittest tests.test_result_metadata -v`  
Expected: `ModuleNotFoundError: No module named 'result_metadata'`

- [x] **Step 3: 鐢ㄦ渶灏忓疄鐜拌ˉ metadata builder**

```python
# backend/result_metadata.py
from __future__ import annotations

from typing import Any


def build_result_metadata(
    *,
    market: str,
    region_or_zone: str,
    timezone: str,
    currency: str,
    unit: str,
    interval_minutes: int | None,
    data_grade: str,
    data_quality_score: float | None,
    coverage: dict[str, Any] | None,
    freshness: dict[str, Any] | None,
    source_name: str,
    source_version: str,
    methodology_version: str,
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "market": market,
        "region_or_zone": region_or_zone,
        "timezone": timezone,
        "currency": currency,
        "unit": unit,
        "interval_minutes": interval_minutes,
        "data_grade": data_grade,
        "data_quality_score": data_quality_score,
        "coverage": coverage or {},
        "freshness": freshness or {},
        "source_name": source_name,
        "source_version": source_version,
        "methodology_version": methodology_version,
        "warnings": warnings or [],
    }
```

- [x] **Step 4: 鍦?`server.py` 涓帴鍏?import锛屼笉鏀瑰彉琛屼负**

```python
# backend/server.py
from result_metadata import build_result_metadata
```

Run: `python -m unittest tests.test_result_metadata -v`  
Expected: `OK`

- [x] **Step 5: 鎻愪氦**

```bash
git add backend/result_metadata.py backend/server.py tests/test_result_metadata.py
git commit -m "feat: add result metadata contract helper"
```

---

### Task 2: 澧炲姞鏁版嵁璐ㄩ噺琛ㄥ拰 SQLite 璇诲啓鑳藉姏

**Files:**
- Modify: `backend/database.py`
- Test: `tests/test_data_quality.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇曪紝閿佸畾鏁版嵁璐ㄩ噺蹇収琛ㄨ鍐?*

```python
import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager


class DataQualityStorageTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_upsert_and_fetch_market_quality_snapshot(self):
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

        rows = self.db.fetch_data_quality_snapshots(scope="market", market="NEM")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["data_grade"], "analytical")
        self.assertEqual(rows[0]["quality_score"], 0.95)
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

Run: `python -m unittest tests.test_data_quality.DataQualityStorageTests -v`  
Expected: `AttributeError: 'DatabaseManager' object has no attribute 'upsert_data_quality_snapshot'`

- [x] **Step 3: 鍦?`database.py` 涓坊鍔犺〃鍜岃鍐欐柟娉?*

```python
# backend/database.py
class DatabaseManager:
    DATA_QUALITY_SNAPSHOT_TABLE = "data_quality_snapshot"
    DATA_QUALITY_ISSUE_TABLE = "data_quality_issue"

    def ensure_data_quality_tables(self, conn: sqlite3.Connection):
        cursor = conn.cursor()
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.DATA_QUALITY_SNAPSHOT_TABLE} (
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
        cursor.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.DATA_QUALITY_ISSUE_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                scope TEXT NOT NULL,
                market TEXT NOT NULL,
                dataset_key TEXT NOT NULL,
                issue_code TEXT NOT NULL,
                severity TEXT NOT NULL,
                detail_json TEXT NOT NULL DEFAULT '{{}}',
                detected_at TEXT NOT NULL
            )
            """
        )
        conn.commit()

    def upsert_data_quality_snapshot(self, record: dict):
        with self.get_connection() as conn:
            self.ensure_data_quality_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.DATA_QUALITY_SNAPSHOT_TABLE} (
                    scope, market, dataset_key, data_grade, quality_score,
                    coverage_ratio, freshness_minutes, issues_json, metadata_json, computed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(scope, market, dataset_key) DO UPDATE SET
                    data_grade=excluded.data_grade,
                    quality_score=excluded.quality_score,
                    coverage_ratio=excluded.coverage_ratio,
                    freshness_minutes=excluded.freshness_minutes,
                    issues_json=excluded.issues_json,
                    metadata_json=excluded.metadata_json,
                    computed_at=excluded.computed_at
                """,
                (
                    record["scope"],
                    record["market"],
                    record["dataset_key"],
                    record["data_grade"],
                    record["quality_score"],
                    record["coverage_ratio"],
                    record["freshness_minutes"],
                    json.dumps(record["issues_json"], ensure_ascii=False),
                    json.dumps(record["metadata_json"], ensure_ascii=False),
                    record["computed_at"],
                ),
            )
            conn.commit()

    def fetch_data_quality_snapshots(self, *, scope: str | None = None, market: str | None = None):
        with self.get_connection() as conn:
            self.ensure_data_quality_tables(conn)
            conn.row_factory = sqlite3.Row
            query = f"SELECT * FROM {self.DATA_QUALITY_SNAPSHOT_TABLE} WHERE 1=1"
            params = []
            if scope:
                query += " AND scope = ?"
                params.append(scope)
            if market:
                query += " AND market = ?"
                params.append(market)
            query += " ORDER BY market, dataset_key"
            rows = conn.execute(query, params).fetchall()
            return [
                {
                    **dict(row),
                    "issues_json": json.loads(row["issues_json"]),
                    "metadata_json": json.loads(row["metadata_json"]),
                }
                for row in rows
            ]
```

- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

Run: `python -m unittest tests.test_data_quality.DataQualityStorageTests -v`  
Expected: `OK`

- [x] **Step 5: 鎻愪氦**

```bash
git add backend/database.py tests/test_data_quality.py
git commit -m "feat: add sqlite data quality snapshot storage"
```

---

### Task 3: 瀹炵幇 Data Quality Center v1 璁＄畻灞?
**Files:**
- Create: `backend/data_quality.py`
- Modify: `backend/database.py`
- Test: `tests/test_data_quality.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇曪紝閿佸畾 NEM / Fingrid 璐ㄩ噺鎽樿璁＄畻**

```python
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from data_quality import summarize_quality_snapshots


class DataQualitySummaryTests(unittest.TestCase):
    def test_summarize_quality_snapshots_groups_by_market(self):
        payload = summarize_quality_snapshots(
            [
                {
                    "scope": "market",
                    "market": "NEM",
                    "dataset_key": "trading_price_2026:NSW1",
                    "data_grade": "analytical",
                    "quality_score": 0.95,
                    "coverage_ratio": 1.0,
                    "freshness_minutes": 10,
                    "issues_json": [],
                    "metadata_json": {},
                    "computed_at": "2026-04-27T00:10:00Z",
                },
                {
                    "scope": "dataset",
                    "market": "FINGRID",
                    "dataset_key": "317",
                    "data_grade": "analytical-preview",
                    "quality_score": 0.82,
                    "coverage_ratio": 0.9,
                    "freshness_minutes": 120,
                    "issues_json": ["stale_source"],
                    "metadata_json": {},
                    "computed_at": "2026-04-27T00:10:00Z",
                },
            ]
        )

        self.assertEqual(payload["summary"]["market_count"], 2)
        self.assertEqual(payload["markets"]["NEM"]["average_quality_score"], 0.95)
        self.assertEqual(payload["markets"]["FINGRID"]["issue_count"], 1)
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

Run: `python -m unittest tests.test_data_quality.DataQualitySummaryTests -v`  
Expected: `ModuleNotFoundError: No module named 'data_quality'`

- [x] **Step 3: 瀹炵幇鏈€灏忚绠楀眰**

```python
# backend/data_quality.py
from __future__ import annotations

from statistics import mean


def summarize_quality_snapshots(rows: list[dict]) -> dict:
    markets = {}
    for row in rows:
        market = row["market"]
        bucket = markets.setdefault(
            market,
            {"rows": [], "issue_count": 0, "grades": set(), "freshness_minutes": []},
        )
        bucket["rows"].append(row)
        bucket["issue_count"] += len(row.get("issues_json", []))
        bucket["grades"].add(row["data_grade"])
        if row.get("freshness_minutes") is not None:
            bucket["freshness_minutes"].append(row["freshness_minutes"])

    normalized_markets = {}
    for market, bucket in markets.items():
        scores = [row["quality_score"] for row in bucket["rows"] if row.get("quality_score") is not None]
        normalized_markets[market] = {
            "dataset_count": len(bucket["rows"]),
            "average_quality_score": round(mean(scores), 4) if scores else None,
            "issue_count": bucket["issue_count"],
            "data_grades": sorted(bucket["grades"]),
            "max_freshness_minutes": max(bucket["freshness_minutes"]) if bucket["freshness_minutes"] else None,
        }

    return {
        "summary": {
            "market_count": len(normalized_markets),
            "snapshot_count": len(rows),
        },
        "markets": normalized_markets,
    }
```

- [x] **Step 4: 鍔犲叆 NEM / WEM / Fingrid 璐ㄩ噺蹇収璁＄畻鍏ュ彛**

```python
# backend/data_quality.py
def compute_quality_snapshots(db) -> list[dict]:
    rows = []
    rows.extend(_compute_nem_snapshots(db))
    rows.extend(_compute_wem_snapshots(db))
    rows.extend(_compute_fingrid_snapshots(db))
    return rows
```

Run: `python -m unittest tests.test_data_quality -v`  
Expected: summary tests pass, snapshot tests still pass

- [x] **Step 5: 鎻愪氦**

```bash
git add backend/data_quality.py backend/database.py tests/test_data_quality.py
git commit -m "feat: add data quality summary service"
```

---

### Task 4: 澧炲姞 `/api/data-quality/*` 鎺ュ彛

**Files:**
- Modify: `backend/server.py`
- Test: `tests/test_data_quality.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇曪紝閿佸畾鏂扮殑 data-quality 璺敱**

```python
import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server


class DataQualityApiTests(unittest.TestCase):
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

    def test_data_quality_summary_route_returns_structured_payload(self):
        self.db.upsert_data_quality_snapshot(
            {
                "scope": "market",
                "market": "NEM",
                "dataset_key": "trading_price_2026:NSW1",
                "data_grade": "analytical",
                "quality_score": 0.95,
                "coverage_ratio": 1.0,
                "freshness_minutes": 5,
                "issues_json": [],
                "metadata_json": {"expected_intervals": 288, "actual_intervals": 288},
                "computed_at": "2026-04-27T00:10:00Z",
            }
        )

        payload = server.get_data_quality_summary()
        self.assertEqual(payload["summary"]["market_count"], 1)
        self.assertEqual(payload["markets"]["NEM"]["dataset_count"], 1)
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

Run: `python -m unittest tests.test_data_quality.DataQualityApiTests -v`  
Expected: `AttributeError: module 'server' has no attribute 'get_data_quality_summary'`

- [x] **Step 3: 鍦?`server.py` 涓鍔犺矾鐢卞拰璁＄畻鍒锋柊鍏ュ彛**

```python
# backend/server.py
import data_quality


@app.post("/api/data-quality/refresh")
def refresh_data_quality():
    snapshots = data_quality.compute_quality_snapshots(db)
    for snapshot in snapshots:
        db.upsert_data_quality_snapshot(snapshot)
    return {"status": "ok", "snapshots_refreshed": len(snapshots)}


@app.get("/api/data-quality/summary")
def get_data_quality_summary():
    rows = db.fetch_data_quality_snapshots()
    return data_quality.summarize_quality_snapshots(rows)


@app.get("/api/data-quality/markets")
def get_data_quality_markets():
    rows = db.fetch_data_quality_snapshots(scope="market")
    return {"items": rows}


@app.get("/api/data-quality/issues")
def get_data_quality_issues(market: Optional[str] = Query(None)):
    rows = db.fetch_data_quality_snapshots(market=market)
    issues = []
    for row in rows:
        for code in row.get("issues_json", []):
            issues.append(
                {
                    "market": row["market"],
                    "dataset_key": row["dataset_key"],
                    "issue_code": code,
                    "data_grade": row["data_grade"],
                    "computed_at": row["computed_at"],
                }
            )
    return {"items": issues}
```

- [x] **Step 4: 杩愯娴嬭瘯纭閫氳繃**

Run: `python -m unittest tests.test_data_quality -v`  
Expected: `OK`

- [x] **Step 5: 鎻愪氦**

```bash
git add backend/server.py tests/test_data_quality.py
git commit -m "feat: add data quality api routes"
```

---

### Task 5: 涓轰富鎺ュ彛琛?metadata 杈撳嚭

**Files:**
- Modify: `backend/server.py`
- Modify: `tests/test_fingrid_api.py`
- Test: `tests/test_result_metadata.py`

- [x] **Step 1: 鍐欏け璐ユ祴璇曪紝閿佸畾 price-trend 涓?Fingrid status 鐨?metadata**

```python
import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


class ApiMetadataIntegrationTests(unittest.TestCase):
    @mock.patch("server.db.fetch_all", return_value=[("2026-04-01 00:00:00", 55.0)])
    @mock.patch("server.db.get_last_update_time", return_value="2026-04-27 00:10:00")
    def test_price_trend_response_contains_metadata(self, mock_updated_at, mock_rows):
        payload = server.get_price_trend(year=2026, region="NSW1", limit=1500)
        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical")
        self.assertEqual(payload["metadata"]["currency"], "AUD")

    def test_fingrid_status_contains_data_grade(self):
        with mock.patch("server.fingrid_service.get_dataset_status_payload") as mock_status:
            mock_status.return_value = {"status": {"dataset_id": "317"}}
            payload = server.get_fingrid_dataset_status("317")
        self.assertIn("metadata", payload)
        self.assertEqual(payload["metadata"]["data_grade"], "analytical-preview")
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

Run: `python -m unittest tests.test_result_metadata.ApiMetadataIntegrationTests -v`  
Expected: assertions fail because `metadata` key is missing

- [x] **Step 3: 缁欎富鎺ュ彛鎸?metadata**

```python
# backend/server.py
def _attach_price_trend_metadata(payload: dict, *, region: str) -> dict:
    payload["metadata"] = build_result_metadata(
        market="NEM" if region != "WEM" else "WEM",
        region_or_zone=region,
        timezone="Australia/Sydney" if region != "WEM" else "Australia/Perth",
        currency="AUD",
        unit="AUD/MWh",
        interval_minutes=5 if region != "WEM" else 15,
        data_grade="analytical" if region != "WEM" else "preview",
        data_quality_score=None,
        coverage={},
        freshness={"last_updated_at": _market_data_version()},
        source_name="AEMO",
        source_version=_market_data_version(),
        methodology_version="price_trend_v1",
        warnings=[],
    )
    return payload


def _attach_fingrid_metadata(payload: dict, dataset_id: str) -> dict:
    payload["metadata"] = build_result_metadata(
        market="FINGRID",
        region_or_zone=dataset_id,
        timezone="Europe/Helsinki",
        currency="EUR",
        unit=payload.get("status", {}).get("unit", "unknown"),
        interval_minutes=None,
        data_grade="analytical-preview",
        data_quality_score=None,
        coverage={},
        freshness={},
        source_name="Fingrid",
        source_version="fingrid_open_data_v1",
        methodology_version="fingrid_status_v1",
        warnings=[],
    )
    return payload
```

- [x] **Step 4: 鍦?`get_price_trend` 鍜?Fingrid 鐘舵€佹帴鍙ｄ腑璋冪敤**

```python
# backend/server.py
result = {...existing payload...}
return _attach_price_trend_metadata(result, region=region)


payload = fingrid_service.get_dataset_status_payload(db, dataset_id=dataset_id)
return _attach_fingrid_metadata(payload, dataset_id)
```

Run: `python -m unittest tests.test_result_metadata tests.test_fingrid_api -v`  
Expected: metadata integration tests pass, existing Fingrid tests remain green

- [x] **Step 5: 鎻愪氦**

```bash
git add backend/server.py tests/test_result_metadata.py tests/test_fingrid_api.py
git commit -m "feat: attach metadata to core analysis responses"
```

---

### Task 6: 鍓嶇灞曠ず data grade 涓庤川閲忔憳瑕?
**Files:**
- Create: `web/src/components/DataQualityBadge.jsx`
- Create: `web/src/lib/resultMetadata.js`
- Test: `web/src/lib/resultMetadata.test.js`
- Modify: `web/src/App.jsx`
- Modify: `web/src/pages/FingridPage.jsx`

- [x] **Step 1: 鍐欏け璐ユ祴璇曪紝閿佸畾鍓嶇 metadata 璇诲彇閫昏緫**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';

import { getResultMetadata, getDataGradeTone } from './resultMetadata.js';

test('getResultMetadata returns stable defaults when metadata is missing', () => {
  const payload = getResultMetadata({});
  assert.equal(payload.data_grade, 'unknown');
  assert.equal(payload.currency, '');
  assert.deepEqual(payload.warnings, []);
});

test('getDataGradeTone maps preview-like grades to warning tone', () => {
  assert.equal(getDataGradeTone('preview'), 'warning');
  assert.equal(getDataGradeTone('analytical-preview'), 'warning');
  assert.equal(getDataGradeTone('analytical'), 'success');
});
```

- [x] **Step 2: 杩愯娴嬭瘯纭澶辫触**

Run: `cd web && node --test src/lib/resultMetadata.test.js`  
Expected: `Cannot find module './resultMetadata.js'`

- [x] **Step 3: 瀹炵幇鍓嶇 metadata 宸ュ叿涓庡睍绀虹粍浠?*

```javascript
// web/src/lib/resultMetadata.js
export function getResultMetadata(payload = {}) {
  const metadata = payload?.metadata || {};
  return {
    data_grade: metadata.data_grade || 'unknown',
    data_quality_score: metadata.data_quality_score ?? null,
    currency: metadata.currency || '',
    unit: metadata.unit || '',
    warnings: metadata.warnings || [],
  };
}

export function getDataGradeTone(grade = 'unknown') {
  if (grade === 'analytical') return 'success';
  if (grade === 'preview' || grade === 'analytical-preview') return 'warning';
  return 'neutral';
}
```

```jsx
// web/src/components/DataQualityBadge.jsx
import { getDataGradeTone } from '../lib/resultMetadata';

export default function DataQualityBadge({ metadata }) {
  const tone = getDataGradeTone(metadata?.data_grade);
  const toneClass =
    tone === 'success'
      ? 'border-emerald-500/30 text-emerald-300'
      : tone === 'warning'
        ? 'border-amber-500/30 text-amber-300'
        : 'border-slate-500/30 text-slate-300';

  return (
    <div className={`inline-flex items-center gap-2 rounded-md border px-2 py-1 text-xs ${toneClass}`}>
      <span>{metadata?.data_grade || 'unknown'}</span>
      {metadata?.data_quality_score != null ? <span>{metadata.data_quality_score}</span> : null}
    </div>
  );
}
```

- [x] **Step 4: 鍦ㄤ富宸ヤ綔鍙颁笌 Fingrid 椤甸潰鎺ュ叆**

```jsx
// web/src/App.jsx
import DataQualityBadge from './components/DataQualityBadge';
import { getResultMetadata } from './lib/resultMetadata';

const chartMetadata = getResultMetadata(chartData);

<div className="mt-3 flex items-center gap-3">
  <DataQualityBadge metadata={chartMetadata} />
</div>
```

```jsx
// web/src/pages/FingridPage.jsx
import DataQualityBadge from '../components/DataQualityBadge';
import { getResultMetadata } from '../lib/resultMetadata';

const statusMetadata = getResultMetadata(statusPayload);

<DataQualityBadge metadata={statusMetadata} />
```

Run: `cd web && node --test src/lib/resultMetadata.test.js src/lib/apiClient.test.js`  
Expected: `ok`

- [x] **Step 5: 鎻愪氦**

```bash
git add web/src/components/DataQualityBadge.jsx web/src/lib/resultMetadata.js web/src/lib/resultMetadata.test.js web/src/App.jsx web/src/pages/FingridPage.jsx
git commit -m "feat: show metadata grade and quality badges in frontend"
```

---

### Task 7: 鏂囨。銆侀獙璇佷笌鏀跺熬

**Files:**
- Modify: `docs/椤圭洰鍏ㄩ潰瑙ｆ瀽鎬诲唽.md`
- Modify: `README.md`

- [x] **Step 1: 鏇存柊 README 鐨?API 璇存槑**

```md
## Data Quality

New endpoints:

- `GET /api/data-quality/summary`
- `GET /api/data-quality/markets`
- `GET /api/data-quality/issues`
- `POST /api/data-quality/refresh`

Core analysis responses now include a `metadata` object with:

- `data_grade`
- `data_quality_score`
- `coverage`
- `freshness`
- `source_version`
- `methodology_version`
```

- [x] **Step 2: 鏇存柊鎬诲唽鏂囨。**

```md
### Data Quality Center v1

- 鏂板鏁版嵁璐ㄩ噺蹇収琛ㄤ笌闂琛?- 涓诲垎鏋愭帴鍙ｅ紑濮嬭繑鍥炵粺涓€ metadata
- WEM slim 鏄庣‘鏍囨敞涓?`preview`
- Fingrid 褰撳墠椤垫槑纭爣娉ㄤ负 `analytical-preview`
```

- [x] **Step 3: 杩愯鍚庣楠岃瘉**

Run: `python -m unittest discover -s tests -p "test_*.py"`  
Expected: all backend tests pass

- [x] **Step 4: 杩愯鍓嶇楠岃瘉**

Run: `cd web && node --test src/lib/*.test.js`  
Expected: all frontend library tests pass

Run: `cd web && npm run build`  
Expected: build succeeds

- [x] **Step 5: 鎻愪氦**

```bash
git add README.md docs/椤圭洰鍏ㄩ潰瑙ｆ瀽鎬诲唽.md
git commit -m "docs: document data quality center and metadata contract"
```

---

## Self-Review

### Spec coverage

- 缁熶竴缁撴灉鍏冩暟鎹绾︼細Task 1, Task 5
- Data Quality Center v1锛歍ask 2, Task 3, Task 4
- WEM / Fingrid 鏁版嵁绛夌骇鏄惧紡鍖栵細Task 5, Task 6, Task 7
- 鍓嶅悗绔渶灏忓睍绀洪棴鐜細Task 5, Task 6
- 鑷姩鍖栭獙璇侊細Task 2, Task 3, Task 4, Task 6, Task 7

### Placeholder scan

- 鏃?`TODO` / `TBD`
- 鎵€鏈変换鍔″寘鍚叿浣撴枃浠惰矾寰勩€佹祴璇曞懡浠ゃ€侀鏈熺粨鏋?
### Type consistency

- 鍚庣缁熶竴浣跨敤 `metadata`
- 绛夌骇瀛楁缁熶竴浣跨敤 `data_grade`
- 璐ㄩ噺瀛楁缁熶竴浣跨敤 `data_quality_score`
- 鐗堟湰瀛楁缁熶竴浣跨敤 `source_version`銆乣methodology_version`

---

Plan complete and saved to `docs/superpowers/plans/2026-04-27-p0-01-data-quality-and-result-metadata.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

Which approach?

