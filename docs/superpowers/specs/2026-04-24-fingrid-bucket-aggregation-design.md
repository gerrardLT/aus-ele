# Fingrid Bucket Aggregation Design
> Date: 2026-04-24
> Status: draft
> Scope: Extend `/fingrid` aggregation from `raw / day / week / month` to `raw / 1h / 2h / 4h / day / week / month`, using natural time buckets and returning average, peak, and trough values for each bucket.

## 1. Goal

The `/fingrid` page currently supports:

- `raw`
- `day`
- `week`
- `month`

The user needs `1h / 2h / 4h` to become first-class aggregation modes, not a separate metric card and not a fixed "latest N hours" widget.

The desired behavior is:

- aggregation becomes a true filter dimension
- results stay linked to the current dataset, time window, timezone, chart, and export
- `2h / 4h` use natural bucket boundaries rather than rolling averages
- each aggregated bucket exposes:
  - average price
  - peak price
  - trough price

## 2. Non-Goals

This change does **not** include:

- `/fingrid` bilingual UI
- new Fingrid datasets
- changes to AEMO/NEM/WEM pages
- realtime "latest 1/2/4 hour" KPI cards outside the current filter flow
- investment/arbitrage analytics based on Fingrid buckets

## 3. User-Facing Behavior

### 3.1 Aggregation Options

Replace the current aggregation selector values with:

- `raw`
- `1h`
- `2h`
- `4h`
- `day`
- `week`
- `month`

`1h` is an explicit bucketed hourly mode. It is semantically close to `raw` for dataset `317`, but it stays valuable because:

- it preserves a consistent aggregation model for future datasets
- it gives a stable bucket label model
- it allows bucket statistics (`avg / peak / trough`) to use the same payload shape as `2h / 4h / day / week / month`

### 3.2 Natural Time Buckets

Bucket alignment is based on the currently selected timezone.

Examples in `Europe/Helsinki`:

- `2h`: `00:00-02:00`, `02:00-04:00`, `04:00-06:00`
- `4h`: `00:00-04:00`, `04:00-08:00`, `08:00-12:00`
- `day`: local calendar day
- `week`: local ISO week
- `month`: local calendar month

Examples in `UTC`:

- the same bucket widths apply, but boundaries align to UTC clock time

This must not be implemented as rolling windows.

### 3.3 Chart Semantics

For non-raw aggregations, the line chart will continue plotting a single numeric field:

- `value = avg_value`

Additional bucket statistics are still available in the same row:

- `avg_value`
- `peak_value`
- `trough_value`
- `bucket_start`
- `bucket_end`
- `sample_count`

The tooltip should display all three metrics for the hovered bucket.

### 3.4 Export Semantics

CSV export should include the richer bucket payload, not only the plotted average value.

At minimum, each exported row should include:

- `timestamp`
- `timestamp_utc`
- `bucket_start`
- `bucket_end`
- `value`
- `avg_value`
- `peak_value`
- `trough_value`
- `sample_count`
- `unit`

`value` remains as a compatibility alias for `avg_value`.

## 4. Root Cause in Current Design

The current `series` path was designed around a single aggregated number per bucket and previously applied `limit` too early against raw rows. That made long-range aggregate views truncate incorrectly.

That issue has already shown that Fingrid aggregation logic belongs on the backend, with a stable output contract. Extending aggregation on the frontend would repeat the same failure mode:

- limit mismatch
- timezone drift
- export mismatch
- duplicated logic across chart and summary consumers

Therefore, this feature should be implemented as a backend-first aggregation extension.

## 5. Backend Design

### 5.1 Aggregation Contract

`backend/fingrid/service.py`

Extend the supported aggregation enum to:

- `raw`
- `1h`
- `2h`
- `4h`
- `day`
- `week`
- `month`

The `series` payload shape should become:

```json
{
  "timestamp": "2026-04-24T00:00:00+03:00",
  "timestamp_utc": "2026-04-23T21:00:00Z",
  "bucket_start": "2026-04-24T00:00:00+03:00",
  "bucket_end": "2026-04-24T04:00:00+03:00",
  "value": 7.15,
  "avg_value": 7.15,
  "peak_value": 8.24,
  "trough_value": 6.31,
  "sample_count": 4,
  "unit": "EUR/MW"
}
```

For `raw`, each point still returns a single source record, but the shape should remain compatible:

- `bucket_start = timestamp_local`
- `bucket_end = timestamp_local`
- `avg_value = peak_value = trough_value = value`
- `sample_count = 1`

### 5.2 Bucket Key Logic

Add explicit bucketing for `1h / 2h / 4h`.

Recommended approach:

- parse each row timestamp in UTC
- convert to selected timezone
- floor the local time to the correct bucket boundary
- use that floored local datetime as the bucket key

For `2h`:

- hour becomes `hour - (hour % 2)`

For `4h`:

- hour becomes `hour - (hour % 4)`

This keeps alignment deterministic and compatible with DST transitions under the selected timezone.

### 5.3 Bucket Aggregation Logic

For each bucket, compute:

- `avg_value = mean(values)`
- `peak_value = max(values)`
- `trough_value = min(values)`
- `sample_count = len(values)`

The chart will read `value`, but `value` is only a compatibility alias:

- `value = avg_value`

### 5.4 Limit Handling

Limit rules should be:

- `raw`: apply limit directly to raw rows
- aggregated modes (`1h / 2h / 4h / day / week / month`): aggregate first, then apply limit to aggregated buckets

This preserves the full requested time span before truncation.

### 5.5 API Surface

`backend/server.py`

Update Fingrid endpoints to accept the extended aggregation set:

- `GET /api/fingrid/datasets/{dataset_id}/series`
- `GET /api/fingrid/datasets/{dataset_id}/export`

Pattern validation should become:

- `^(raw|1h|2h|4h|day|week|month)$`

## 6. Frontend Design

### 6.1 Selector

`web/src/components/fingrid/FingridHeader.jsx`

Replace the current aggregation options:

- `raw`
- `day`
- `week`
- `month`

with:

- `raw`
- `1h`
- `2h`
- `4h`
- `day`
- `week`
- `month`

### 6.2 Chart

`web/src/components/fingrid/FingridSeriesChart.jsx`

Continue plotting:

- `dataKey="value"`

Tooltip should render:

- average
- peak
- trough
- sample count
- bucket range

No chart type change is required in this iteration.

### 6.3 Export Link

`web/src/lib/fingridApi.js`

No structural URL change is needed beyond sending the expanded aggregation values. The frontend should continue passing the active aggregation to export.

## 7. Compatibility

To keep the page stable during rollout:

- retain `value` in series rows
- do not force all consumers to switch to `avg_value` immediately
- keep existing chart rendering logic working with minimal changes

This avoids a wider refactor across the Fingrid page.

## 8. Error Handling

If the backend receives an unsupported aggregation:

- return `400` via existing FastAPI validation

If a bucket receives no valid numeric samples:

- skip the bucket rather than emitting invalid numeric payloads

If the requested time range has no data:

- return an empty `series` array with the same query metadata structure as today

## 9. Testing

### 9.1 Backend Tests

Add or extend tests in `tests/test_fingrid_service.py` to cover:

- `2h` natural bucket alignment
- `4h` natural bucket alignment
- timezone-sensitive bucketing
- aggregated payload includes `avg_value / peak_value / trough_value / sample_count`
- `limit` is applied after aggregation
- `raw` remains backward compatible

### 9.2 Frontend Tests

Add or extend tests for:

- aggregation selector includes `1h / 2h / 4h`
- export URL still carries the selected aggregation
- tooltip or component source references the richer bucket fields

## 10. Implementation Order

1. Extend backend aggregation enum and bucket logic
2. Add failing backend tests for `2h / 4h` and post-aggregation limit behavior
3. Update series payload shape with avg/peak/trough fields
4. Update export to include the richer fields
5. Update frontend selector
6. Update chart tooltip
7. Run focused backend and frontend Fingrid tests

## 11. Risks

- DST edges may shift expected local bucket boundaries if bucket flooring is implemented against UTC instead of local time
- Export consumers may assume only `value` exists; therefore `value` must remain
- Future summary cards may want to reuse `1h / 2h / 4h`, but this design intentionally leaves summary semantics unchanged for now

## 12. Decision Summary

This feature will be implemented as a backend-first aggregation extension for `/fingrid`.

Key decisions:

- `1h / 2h / 4h` are aggregation modes, not standalone KPI widgets
- `2h / 4h` use natural local-time bucket boundaries
- each aggregated bucket returns average, peak, and trough values
- the line chart continues plotting the average
- export includes the richer bucket fields
- summary/distribution semantics stay unchanged in this iteration
