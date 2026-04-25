# Fingrid Bucket Aggregation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend `/fingrid` so aggregation supports `raw / 1h / 2h / 4h / day / week / month`, using natural timezone-aligned buckets and returning average, peak, and trough values for each bucket.

**Architecture:** Keep aggregation backend-first. The backend owns bucket alignment, `avg/peak/trough/sample_count` calculation, post-aggregation limiting, and CSV export shape. The frontend only exposes the new selector values and renders richer tooltip content while continuing to plot `value` as the average alias.

**Tech Stack:** FastAPI, SQLite, Python `unittest`, React, Recharts, Node `node:test`

---

### Task 1: Extend Backend Aggregation Tests

**Files:**
- Modify: `tests/test_fingrid_service.py`
- Test: `tests/test_fingrid_service.py`

- [ ] **Step 1: Write the failing backend tests for `2h` and `4h` bucket aggregation**

Add these tests near the existing `FingridServiceSyncTests` aggregation coverage:

```python
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
    ```

- [ ] **Step 2: Run the new tests to verify they fail**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest `
  tests.test_fingrid_service.FingridServiceSyncTests.test_two_hour_aggregation_uses_local_bucket_boundaries `
  tests.test_fingrid_service.FingridServiceSyncTests.test_four_hour_aggregation_returns_bucket_metrics -v
```

Expected: `FAIL` because aggregation `"2h"` and `"4h"` are not implemented and the richer payload fields do not exist yet.

- [ ] **Step 3: Write the minimal backend support in `backend/fingrid/service.py`**

Add these helpers and shape changes:

```python
from datetime import datetime, timedelta, timezone


def _bucket_window(local_dt, aggregation: str):
    if aggregation == "1h":
        start = local_dt.replace(minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=1)
        return start, end
    if aggregation == "2h":
        start = local_dt.replace(hour=local_dt.hour - (local_dt.hour % 2), minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=2)
        return start, end
    if aggregation == "4h":
        start = local_dt.replace(hour=local_dt.hour - (local_dt.hour % 4), minute=0, second=0, microsecond=0)
        end = start + timedelta(hours=4)
        return start, end
    if aggregation == "day":
        start = local_dt.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=1)
        return start, end
    if aggregation == "week":
        start = (local_dt - timedelta(days=local_dt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=7)
        return start, end
    if aggregation == "month":
        start = local_dt.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        if start.month == 12:
            end = start.replace(year=start.year + 1, month=1)
        else:
            end = start.replace(month=start.month + 1)
        return start, end
    raise ValueError(f"Unsupported aggregation: {aggregation}")


def _bucket_label(bucket_start, aggregation: str):
    if aggregation == "week":
        iso_year, iso_week, _ = bucket_start.isocalendar()
        return f"{iso_year}-W{iso_week:02d}"
    if aggregation == "month":
        return bucket_start.strftime("%Y-%m-01T00:00:00")
    return bucket_start.isoformat()
```

Then update `_aggregate_rows()` so aggregated rows look like:

```python
    if aggregation == "raw":
        return [
            {
                "timestamp": row["timestamp_local"],
                "timestamp_utc": row["timestamp_utc"],
                "bucket_start": row["timestamp_local"],
                "bucket_end": row["timestamp_local"],
                "value": row["value"],
                "avg_value": row["value"],
                "peak_value": row["value"],
                "trough_value": row["value"],
                "sample_count": 1,
                "unit": row["unit"],
            }
            for row in rows
        ]

    buckets = defaultdict(list)
    for row in rows:
        utc_dt = _parse_utc(row["timestamp_utc"])
        local_dt = utc_dt.astimezone(tz)
        bucket_start, bucket_end = _bucket_window(local_dt, aggregation)
        buckets[(bucket_start, bucket_end)].append(row["value"])

    items = []
    for (bucket_start, bucket_end), values in sorted(buckets.items(), key=lambda item: item[0][0]):
        avg_value = round(mean(values), 4)
        peak_value = round(max(values), 4)
        trough_value = round(min(values), 4)
        items.append(
            {
                "timestamp": _bucket_label(bucket_start, aggregation),
                "timestamp_utc": bucket_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "bucket_start": bucket_start.isoformat(),
                "bucket_end": bucket_end.isoformat(),
                "value": avg_value,
                "avg_value": avg_value,
                "peak_value": peak_value,
                "trough_value": trough_value,
                "sample_count": len(values),
                "unit": rows[0]["unit"] if rows else "EUR/MW",
            }
        )
```

Also update `get_dataset_series_payload()` so post-aggregation limiting still applies to:

- `1h`
- `2h`
- `4h`
- `day`
- `week`
- `month`

- [ ] **Step 4: Re-run the backend tests and verify they pass**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest `
  tests.test_fingrid_service.FingridServiceSyncTests.test_two_hour_aggregation_uses_local_bucket_boundaries `
  tests.test_fingrid_service.FingridServiceSyncTests.test_four_hour_aggregation_returns_bucket_metrics -v
```

Expected: `OK`

- [ ] **Step 5: Commit**

```powershell
git add tests/test_fingrid_service.py backend/fingrid/service.py
git commit -m "feat: add Fingrid 2h and 4h bucket aggregation"
```

### Task 2: Extend Backend Route Validation and Export Shape

**Files:**
- Modify: `backend/server.py`
- Modify: `backend/fingrid/export.py`
- Modify: `tests/test_fingrid_service.py`
- Test: `tests/test_fingrid_service.py`

- [ ] **Step 1: Write the failing export test for richer bucket fields**

Append this test to `tests/test_fingrid_service.py`:

```python
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
```

- [ ] **Step 2: Run the export test to verify it fails**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest `
  tests.test_fingrid_service.FingridServiceSyncTests.test_export_includes_bucket_statistics_columns -v
```

Expected: `FAIL` because the CSV header still only includes `timestamp,timestamp_utc,value,unit`.

- [ ] **Step 3: Update export field order and API validation**

In `backend/fingrid/export.py`, change the CSV writer to:

```python
def build_fingrid_csv(series: list[dict]) -> str:
    buffer = io.StringIO()
    fieldnames = [
        "timestamp",
        "timestamp_utc",
        "bucket_start",
        "bucket_end",
        "value",
        "avg_value",
        "peak_value",
        "trough_value",
        "sample_count",
        "unit",
    ]
    writer = csv.DictWriter(buffer, fieldnames=fieldnames)
    writer.writeheader()
    for row in series:
        writer.writerow({key: row.get(key) for key in fieldnames})
    return buffer.getvalue()
```

In `backend/server.py`, update both Fingrid aggregation query validators:

```python
aggregation: str = Query("raw", pattern="^(raw|1h|2h|4h|day|week|month)$")
```

- [ ] **Step 4: Run the focused export test, then the full Fingrid backend test file**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest `
  tests.test_fingrid_service.FingridServiceSyncTests.test_export_includes_bucket_statistics_columns -v

& .\.venv\Scripts\python.exe -m unittest tests.test_fingrid_service -v
```

Expected: both commands return `OK`

- [ ] **Step 5: Commit**

```powershell
git add backend/server.py backend/fingrid/export.py tests/test_fingrid_service.py
git commit -m "feat: export Fingrid bucket statistics"
```

### Task 3: Add Frontend Tests for New Aggregation Options and Tooltip Fields

**Files:**
- Modify: `web/src/lib/fingridPage.test.js`
- Create: `web/src/lib/fingridSeriesChart.test.js`
- Test: `web/src/lib/fingridPage.test.js`
- Test: `web/src/lib/fingridSeriesChart.test.js`

- [ ] **Step 1: Write the failing frontend tests**

Update `web/src/lib/fingridPage.test.js`:

```javascript
test('FingridPage exposes raw 1h 2h 4h day week month aggregation options', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  for (const token of ['raw', '1h', '2h', '4h', 'day', 'week', 'month']) {
    assert.match(source, new RegExp(`'${token}'`));
  }
});
```

Create `web/src/lib/fingridSeriesChart.test.js`:

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('FingridSeriesChart tooltip references bucket statistics fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');
  for (const token of ['avg_value', 'peak_value', 'trough_value', 'sample_count', 'bucket_start', 'bucket_end']) {
    assert.match(source, new RegExp(token));
  }
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run:

```powershell
node --test web\src\lib\fingridPage.test.js web\src\lib\fingridSeriesChart.test.js
```

Expected: `FAIL` because `FingridHeader.jsx` does not include `1h / 2h / 4h`, and `FingridSeriesChart.jsx` does not reference the bucket statistic fields.

- [ ] **Step 3: Update the selector list in `FingridHeader.jsx`**

Replace the current aggregation options with:

```jsx
{['raw', '1h', '2h', '4h', 'day', 'week', 'month'].map((item) => (
  <option key={item} value={item}>
    {item}
  </option>
))}
```

- [ ] **Step 4: Re-run the selector test only**

Run:

```powershell
node --test web\src\lib\fingridPage.test.js
```

Expected: `OK`

- [ ] **Step 5: Commit**

```powershell
git add web/src/components/fingrid/FingridHeader.jsx web/src/lib/fingridPage.test.js web/src/lib/fingridSeriesChart.test.js
git commit -m "feat: add Fingrid bucket aggregation selector options"
```

### Task 4: Implement Frontend Tooltip Support for avg/peak/trough Buckets

**Files:**
- Modify: `web/src/components/fingrid/FingridSeriesChart.jsx`
- Test: `web/src/lib/fingridSeriesChart.test.js`

- [ ] **Step 1: Write the minimal tooltip implementation**

Replace the bare `<Tooltip />` usage with an explicit tooltip component:

```jsx
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

function FingridSeriesTooltip({ active, payload, label }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload || {};
  return (
    <div className="rounded border border-[var(--color-border)] bg-white p-3 text-sm shadow-lg">
      <div className="font-medium text-[var(--color-text)]">{label}</div>
      <div className="mt-2 text-[var(--color-text)]">Average: {point.avg_value ?? point.value}</div>
      <div className="text-[var(--color-text)]">Peak: {point.peak_value ?? point.value}</div>
      <div className="text-[var(--color-text)]">Trough: {point.trough_value ?? point.value}</div>
      <div className="text-[var(--color-text)]">Samples: {point.sample_count ?? 1}</div>
      <div className="text-[var(--color-muted)]">Start: {point.bucket_start ?? point.timestamp}</div>
      <div className="text-[var(--color-muted)]">End: {point.bucket_end ?? point.timestamp}</div>
    </div>
  );
}
```

Then wire it here:

```jsx
<Tooltip content={<FingridSeriesTooltip />} />
```

- [ ] **Step 2: Run the tooltip test to verify it passes**

Run:

```powershell
node --test web\src\lib\fingridSeriesChart.test.js
```

Expected: `OK`

- [ ] **Step 3: Run the focused frontend Fingrid test suite**

Run:

```powershell
node --test `
  web\src\lib\fingridApi.test.js `
  web\src\lib\fingridDataset.test.js `
  web\src\lib\fingridPage.test.js `
  web\src\lib\fingridSeriesChart.test.js
```

Expected: `OK`

- [ ] **Step 4: Manually verify the `/fingrid` UI**

Run the app:

```powershell
cd G:\project\aus-ele\backend
& ..\.venv\Scripts\python.exe -m uvicorn server:app --host 0.0.0.0 --port 8085 --reload
```

```powershell
cd G:\project\aus-ele\web
npm run dev
```

Check:

- aggregation dropdown shows `raw / 1h / 2h / 4h / day / week / month`
- `2h` and `4h` return visibly coarser bucket counts than `raw`
- tooltip shows average, peak, trough, sample count, and bucket range
- export download includes `bucket_start / bucket_end / avg_value / peak_value / trough_value / sample_count`

- [ ] **Step 5: Commit**

```powershell
git add web/src/components/fingrid/FingridSeriesChart.jsx web/src/lib/fingridSeriesChart.test.js
git commit -m "feat: show Fingrid bucket statistics in chart tooltip"
```

### Task 5: Final Regression Sweep

**Files:**
- Modify: none
- Test: `tests/test_fingrid_service.py`
- Test: `tests/test_fingrid_storage.py`
- Test: `tests/test_fingrid_catalog.py`
- Test: `web/src/lib/fingridApi.test.js`
- Test: `web/src/lib/fingridDataset.test.js`
- Test: `web/src/lib/fingridPage.test.js`
- Test: `web/src/lib/fingridSeriesChart.test.js`

- [ ] **Step 1: Run the full Fingrid backend regression suite**

Run:

```powershell
& .\.venv\Scripts\python.exe -m unittest `
  tests.test_fingrid_service `
  tests.test_fingrid_storage `
  tests.test_fingrid_catalog -v
```

Expected: `OK`

- [ ] **Step 2: Run the full Fingrid frontend regression suite**

Run:

```powershell
node --test `
  web\src\lib\fingridApi.test.js `
  web\src\lib\fingridDataset.test.js `
  web\src\lib\fingridPage.test.js `
  web\src\lib\fingridSeriesChart.test.js
```

Expected: `OK`

- [ ] **Step 3: Record the manual verification results in the change summary**

Use this checklist in the final notes:

```text
- Selector exposes raw / 1h / 2h / 4h / day / week / month
- 2h and 4h use timezone-aligned natural buckets
- Chart continues plotting averages
- Tooltip shows avg / peak / trough / sample count / bucket range
- CSV export includes the richer bucket fields
```

- [ ] **Step 4: Confirm the worktree is clean after the task commits**

```powershell
git status --short
```

Expected: no uncommitted changes related to this feature remain.

- [ ] **Step 5: Stop any local dev servers started for verification**

Run:

```powershell
Get-Process | Where-Object { $_.ProcessName -like '*python*' -or $_.ProcessName -like '*node*' }
```

Expected: terminate only the processes started for this task if they are still running.
