# Finland Market Board Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a new `/finland` analysis-first market board that aggregates Finland reserve, activation, imbalance, and spot context into one business-facing workspace while keeping `/fingrid` as the source-level page.

**Architecture:** Add a board-oriented Finland aggregation layer in the backend, expose it through `/api/finland/board/*`, and build a dedicated frontend route and page shell that consume board contracts instead of raw dataset ids. Reuse the existing Finland market-model and Fingrid infrastructure for readiness, provenance, and source coverage, but keep joining and view assembly on the backend.

**Tech Stack:** FastAPI, Pydantic, SQLite-backed `DatabaseManager`, existing Finland/Fingrid service modules, React, Vite, existing `fetchJson` API client helpers, `node:test`, `unittest`

---

## File Structure

### Backend

- Create: `backend/finland_board_service.py`
  - Build overview payloads, table views, chart series, readiness summaries, and field catalog rows for the new Finland board.
- Create: `backend/finland_board_contracts.py`
  - Centralize field registry, view definitions, labels, units, source metadata, and helper formatters used by the service and frontend-facing payloads.
- Modify: `backend/server.py`
  - Add Pydantic response models and route handlers for `/api/finland/board/*`.
- Modify: `backend/finland_market_model.py`
  - Reuse or extract readiness/status pieces so the board endpoints do not duplicate source-health logic inconsistently.
- Create: `tests/test_finland_board_service.py`
  - Unit coverage for field catalog, overview cards, table shaping, spot joins, and chart/spread behavior.
- Modify: `tests/test_external_api_v1_routes.py`
  - Add FastAPI route tests for the new board endpoints.

### Frontend

- Create: `web/src/lib/finlandApi.js`
  - URL builders and normalizers for the new board endpoints.
- Create: `web/src/lib/finlandBoard.test.js`
  - Focused helper and page-state tests for Finland route/API builders and board view behavior.
- Modify: `web/src/lib/pageRouter.js`
  - Route `/finland` to a new root page key.
- Modify: `web/src/lib/pageRouter.test.js`
  - Add `/finland` route assertions without regressing `/fingrid` and `/developer`.
- Modify: `web/src/main.jsx`
  - Mount `FinlandPage` on the new root page key.
- Create: `web/src/pages/FinlandPage.jsx`
  - Top-level Finland market board page.
- Create: `web/src/components/finland/FinlandBoardHeader.jsx`
  - Overview strip with source status, time controls, freshness, and summary actions.
- Create: `web/src/components/finland/FinlandOverviewCards.jsx`
  - Six-card overview grid.
- Create: `web/src/components/finland/FinlandWorkbenchTabs.jsx`
  - Primary tab bar and daily segmented-control wrapper.
- Create: `web/src/components/finland/FinlandDataTable.jsx`
  - Sticky, selectable, column-configurable data table.
- Create: `web/src/components/finland/FinlandLinkedChart.jsx`
  - Single/compare/spread trend chart.
- Create: `web/src/components/finland/FinlandFieldDetailPanel.jsx`
  - Right-side provenance and methodology panel.
- Modify: `web/src/translations.js`
  - Add Finland page labels through existing translation/default-text patterns.
- Modify: `web/src/App.jsx`
  - Add a nav entry pointing to `/finland`.

### Docs

- Modify: `docs/API响应契约说明.md`
  - Document new `/api/finland/board/*` response contracts after implementation.

## Task 1: Define Finland Board Field Registry And View Contracts

**Files:**
- Create: `backend/finland_board_contracts.py`
- Create: `tests/test_finland_board_service.py`

- [ ] **Step 1: Write the failing contract-registry tests**

```python
import unittest

from finland_board_contracts import (
    FINLAND_BOARD_FIELDS,
    FINLAND_BOARD_VIEWS,
    get_finland_board_field,
    get_finland_board_view,
)


class FinlandBoardContractTests(unittest.TestCase):
    def test_capacity_view_declares_expected_columns(self):
        view = get_finland_board_view("capacity_hourly")
        self.assertEqual(
            view["columns"],
            [
                "timestamp_helsinki",
                "fcr_n_price_eur_mw",
                "fcr_d_up_price_eur_mw",
                "fcr_d_down_price_eur_mw",
                "afrr_cap_up_eur_mw",
                "afrr_cap_down_eur_mw",
                "mfrr_cap_up_eur_mw",
                "mfrr_cap_down_eur_mw",
                "spot_price_fi_eur_mwh",
            ],
        )

    def test_spot_field_is_marked_as_external_join(self):
        field = get_finland_board_field("spot_price_fi_eur_mwh")
        self.assertEqual(field["source_type"], "external_join")
        self.assertEqual(field["granularity"], "1h")

    def test_unknown_view_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_finland_board_view("unknown")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `python -m unittest tests.test_finland_board_service.FinlandBoardContractTests -v`

Expected: `ImportError` or `ModuleNotFoundError` because `finland_board_contracts.py` does not exist yet.

- [ ] **Step 3: Write the minimal field-registry implementation**

```python
from __future__ import annotations

FINLAND_BOARD_FIELDS = {
    "timestamp_helsinki": {
        "field_key": "timestamp_helsinki",
        "label": "Time (Europe/Helsinki)",
        "unit": None,
        "granularity": "display",
        "source_name": "derived",
        "source_dataset_id": None,
        "source_type": "derived",
        "category": "time",
        "methodology_note": "Localized display timestamp.",
    },
    "fcr_n_price_eur_mw": {
        "field_key": "fcr_n_price_eur_mw",
        "label": "FCR-N Capacity Price",
        "unit": "EUR/MW",
        "granularity": "1h",
        "source_name": "Fingrid",
        "source_dataset_id": "317",
        "source_type": "live",
        "category": "capacity",
        "methodology_note": "Hourly reserve-capacity price.",
    },
    "spot_price_fi_eur_mwh": {
        "field_key": "spot_price_fi_eur_mwh",
        "label": "Finland Spot Price",
        "unit": "EUR/MWh",
        "granularity": "1h",
        "source_name": "Nord Pool",
        "source_dataset_id": "day_ahead_finland",
        "source_type": "external_join",
        "category": "spot",
        "methodology_note": "Joined Finland spot reference price.",
    },
}

FINLAND_BOARD_VIEWS = {
    "capacity_hourly": {
        "view_key": "capacity_hourly",
        "title": "capacity_1h",
        "columns": [
            "timestamp_helsinki",
            "fcr_n_price_eur_mw",
            "fcr_d_up_price_eur_mw",
            "fcr_d_down_price_eur_mw",
            "afrr_cap_up_eur_mw",
            "afrr_cap_down_eur_mw",
            "mfrr_cap_up_eur_mw",
            "mfrr_cap_down_eur_mw",
            "spot_price_fi_eur_mwh",
        ],
    },
}


def get_finland_board_field(field_key: str) -> dict:
    if field_key not in FINLAND_BOARD_FIELDS:
        raise KeyError(f"Unsupported Finland board field: {field_key}")
    return FINLAND_BOARD_FIELDS[field_key]


def get_finland_board_view(view_key: str) -> dict:
    if view_key not in FINLAND_BOARD_VIEWS:
        raise KeyError(f"Unsupported Finland board view: {view_key}")
    return FINLAND_BOARD_VIEWS[view_key]
```

- [ ] **Step 4: Expand the registry to cover all board views used by the spec**

```python
FINLAND_BOARD_VIEWS.update(
    {
        "activation_15m": {
            "view_key": "activation_15m",
            "title": "activation_settlement_15m",
            "columns": [
                "timestamp_helsinki",
                "afrr_act_up_eur_mwh",
                "afrr_act_down_eur_mwh",
                "mfrr_act_up_eur_mwh",
                "mfrr_act_down_eur_mwh",
                "imbalance_price_eur_mwh",
                "spot_price_fi_eur_mwh",
            ],
        },
        "daily_capacity": {
            "view_key": "daily_capacity",
            "title": "daily_averages",
            "columns": [
                "date",
                "fcr_n_price_eur_mw",
                "fcr_d_up_price_eur_mw",
                "fcr_d_down_price_eur_mw",
                "afrr_cap_up_eur_mw",
                "afrr_cap_down_eur_mw",
                "mfrr_cap_up_eur_mw",
                "mfrr_cap_down_eur_mw",
                "spot_price_fi_eur_mwh",
            ],
        },
        "daily_activation": {
            "view_key": "daily_activation",
            "title": "daily_averages",
            "columns": [
                "date",
                "afrr_act_up_eur_mwh",
                "afrr_act_down_eur_mwh",
                "mfrr_act_up_eur_mwh",
                "mfrr_act_down_eur_mwh",
                "imbalance_price_eur_mwh",
                "spot_price_fi_eur_mwh",
            ],
        },
        "summary": {"view_key": "summary", "title": "summary_stats", "columns": []},
        "dictionary": {"view_key": "dictionary", "title": "field_dictionary", "columns": []},
    }
)
```

- [ ] **Step 5: Run the contract test to verify it passes**

Run: `python -m unittest tests.test_finland_board_service.FinlandBoardContractTests -v`

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add backend/finland_board_contracts.py tests/test_finland_board_service.py
git commit -m "feat: add Finland board field registry"
```

## Task 2: Build Backend Finland Board Service

**Files:**
- Create: `backend/finland_board_service.py`
- Create: `tests/test_finland_board_service.py`
- Modify: `backend/finland_market_model.py`

- [ ] **Step 1: Write the failing service tests for overview, table joins, and chart spread**

```python
import unittest

from finland_board_service import (
    build_finland_board_chart_payload,
    build_finland_board_overview_payload,
    build_finland_board_table_payload,
)


class StubDatabase:
    def fetch_fingrid_dataset_coverage(self, dataset_id):
        return {"coverage_end_utc": "2026-04-02T00:00:00Z", "record_count": 24}

    def fetch_fingrid_sync_state(self, dataset_id):
        return {"sync_status": "ok"}


class FinlandBoardServiceTests(unittest.TestCase):
    def test_overview_contains_six_cards(self):
        payload = build_finland_board_overview_payload(StubDatabase(), start="2026-04-01T00:00:00Z", end="2026-04-02T00:00:00Z")
        self.assertEqual(len(payload["cards"]), 6)

    def test_capacity_table_returns_spot_join_column(self):
        payload = build_finland_board_table_payload(StubDatabase(), view="capacity_hourly", start="2026-04-01T00:00:00Z", end="2026-04-02T00:00:00Z", tz="Europe/Helsinki")
        self.assertIn("spot_price_fi_eur_mwh", [column["field_key"] for column in payload["columns"]])

    def test_spread_chart_returns_difference_series(self):
        payload = build_finland_board_chart_payload(
            StubDatabase(),
            fields=["imbalance_price_eur_mwh", "spot_price_fi_eur_mwh"],
            mode="spread",
            start="2026-04-01T00:00:00Z",
            end="2026-04-02T00:00:00Z",
            granularity="hour",
        )
        self.assertEqual(payload["mode"], "spread")
        self.assertEqual(payload["series"][0]["field_key"], "imbalance_price_eur_mwh-minus-spot_price_fi_eur_mwh")
```

- [ ] **Step 2: Run the service tests to verify they fail**

Run: `python -m unittest tests.test_finland_board_service.FinlandBoardServiceTests -v`

Expected: `ImportError` because `finland_board_service.py` does not exist.

- [ ] **Step 3: Write the minimal Finland board service shell**

```python
from __future__ import annotations

from finland_board_contracts import FINLAND_BOARD_FIELDS, get_finland_board_view


def build_finland_board_overview_payload(db, start: str | None, end: str | None) -> dict:
    return {
        "window": {"start": start, "end": end},
        "cards": [
            {"card_key": "fcr_n_avg", "label": "FCR-N Capacity Avg", "value": None, "unit": "EUR/MW"},
            {"card_key": "afrr_act_avg", "label": "aFRR Activation Avg", "value": None, "unit": "EUR/MWh"},
            {"card_key": "mfrr_act_avg", "label": "mFRR Activation Avg", "value": None, "unit": "EUR/MWh"},
            {"card_key": "imbalance_avg", "label": "Imbalance Avg", "value": None, "unit": "EUR/MWh"},
            {"card_key": "spot_avg", "label": "Spot Avg", "value": None, "unit": "EUR/MWh"},
            {"card_key": "freshness", "label": "Join Completeness", "value": None, "unit": None},
        ],
        "sources": [],
        "metadata": {},
    }


def build_finland_board_table_payload(db, view: str, start: str | None, end: str | None, tz: str) -> dict:
    view_config = get_finland_board_view(view)
    columns = [FINLAND_BOARD_FIELDS[field_key] | {"field_key": field_key} for field_key in view_config["columns"]]
    return {"view": view, "columns": columns, "rows": [], "metadata": {"tz": tz}, "warnings": []}


def build_finland_board_chart_payload(db, fields: list[str], mode: str, start: str | None, end: str | None, granularity: str) -> dict:
    field_key = f"{fields[0]}-minus-{fields[1]}" if mode == "spread" and len(fields) == 2 else fields[0]
    return {"mode": mode, "granularity": granularity, "series": [{"field_key": field_key, "points": []}], "metadata": {}}
```

- [ ] **Step 4: Add real helper seams for field catalog rows, source readiness reuse, and join warnings**

```python
def build_finland_field_catalog_rows() -> list[dict]:
    rows = []
    for field_key, field in FINLAND_BOARD_FIELDS.items():
        if field.get("category") == "time":
            continue
        rows.append(
            {
                "field_key": field_key,
                "category": field["category"],
                "label": field["label"],
                "unit": field["unit"],
                "granularity": field["granularity"],
                "source_name": field["source_name"],
                "source_dataset_id": field["source_dataset_id"],
                "source_type": field["source_type"],
                "methodology_note": field["methodology_note"],
            }
        )
    return rows


def build_finland_board_readiness_payload(db, market_model_payload: dict) -> dict:
    return {
        "status": market_model_payload.get("status", "partial"),
        "sources": market_model_payload.get("sources", []),
        "warnings": market_model_payload.get("warnings", []),
    }
```

- [ ] **Step 5: Replace placeholder cards and rows with deterministic in-memory fixture assembly in the tests first**

```python
class StubDatabase:
    def fetch_finland_board_series(self, field_key, start=None, end=None):
        fixtures = {
            "fcr_n_price_eur_mw": [
                {"timestamp_helsinki": "2026-04-01T03:00:00+03:00", "value": 7.68},
                {"timestamp_helsinki": "2026-04-01T04:00:00+03:00", "value": 7.43},
            ],
            "spot_price_fi_eur_mwh": [
                {"timestamp_helsinki": "2026-04-01T03:00:00+03:00", "value": 17.54},
                {"timestamp_helsinki": "2026-04-01T04:00:00+03:00", "value": 16.99},
            ],
            "imbalance_price_eur_mwh": [
                {"timestamp_helsinki": "2026-04-01T03:00:00+03:00", "value": -13.85},
                {"timestamp_helsinki": "2026-04-01T04:00:00+03:00", "value": 80.0},
            ],
        }
        return fixtures.get(field_key, [])
```

- [ ] **Step 6: Implement table joining, daily rollups, summary rows, and spread chart logic**

```python
from collections import defaultdict
from statistics import mean, median


def _join_rows_by_timestamp(series_by_field: dict[str, list[dict]]) -> list[dict]:
    joined = defaultdict(dict)
    for field_key, rows in series_by_field.items():
        for row in rows:
            ts = row["timestamp_helsinki"]
            joined[ts]["timestamp_helsinki"] = ts
            joined[ts][field_key] = row["value"]
    return [joined[key] for key in sorted(joined)]


def _build_summary_rows(series_by_field: dict[str, list[dict]]) -> list[dict]:
    rows = []
    for field_key, points in series_by_field.items():
        values = [point["value"] for point in points if point.get("value") is not None]
        if not values:
            continue
        rows.append(
            {
                "field_key": field_key,
                "valid_record_count": len(values),
                "mean": round(mean(values), 4),
                "median": round(median(values), 4),
                "max": round(max(values), 4),
                "min": round(min(values), 4),
            }
        )
    return rows
```

- [ ] **Step 7: Run the backend unit file to verify the service passes**

Run: `python -m unittest tests.test_finland_board_service -v`

Expected: `OK`

- [ ] **Step 8: Commit**

```bash
git add backend/finland_board_service.py backend/finland_market_model.py tests/test_finland_board_service.py
git commit -m "feat: add Finland board service"
```

## Task 3: Expose `/api/finland/board/*` Routes In FastAPI

**Files:**
- Modify: `backend/server.py`
- Modify: `tests/test_external_api_v1_routes.py`

- [ ] **Step 1: Write failing FastAPI route tests**

```python
def test_finland_board_overview_route_returns_cards(client):
    response = client.get("/api/finland/board/overview")
    assert response.status_code == 200
    payload = response.json()
    assert "cards" in payload
    assert len(payload["cards"]) == 6


def test_finland_board_table_route_supports_capacity_view(client):
    response = client.get(
        "/api/finland/board/table",
        params={"view": "capacity_hourly", "tz": "Europe/Helsinki"},
    )
    assert response.status_code == 200
    payload = response.json()
    assert payload["view"] == "capacity_hourly"
    assert payload["columns"][0]["field_key"] == "timestamp_helsinki"


def test_finland_board_chart_route_supports_spread_mode(client):
    response = client.get(
        "/api/finland/board/chart",
        params={
            "fields": ["imbalance_price_eur_mwh", "spot_price_fi_eur_mwh"],
            "mode": "spread",
            "granularity": "hour",
        },
    )
    assert response.status_code == 200
    assert response.json()["mode"] == "spread"
```

- [ ] **Step 2: Run the FastAPI tests to verify they fail**

Run: `python -m unittest tests.test_external_api_v1_routes -v`

Expected: `404` for the new `/api/finland/board/*` routes.

- [ ] **Step 3: Add Pydantic payload models for board endpoints**

```python
class FinlandBoardOverviewPayload(BaseModel):
    cards: list[dict] = Field(default_factory=list)
    sources: list[dict] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class FinlandBoardTablePayload(BaseModel):
    view: str
    columns: list[dict[str, Any]] = Field(default_factory=list)
    rows: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class FinlandBoardChartPayload(BaseModel):
    mode: str
    granularity: str
    series: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class FinlandBoardFieldCatalogPayload(BaseModel):
    items: list[dict[str, Any]] = Field(default_factory=list)


class FinlandBoardReadinessPayload(BaseModel):
    status: str
    sources: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Add the new route handlers**

```python
@app.get("/api/finland/board/overview", response_model=FinlandBoardOverviewPayload)
def get_finland_board_overview(
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
):
    return build_finland_board_overview_payload(db, start=start, end=end)


@app.get("/api/finland/board/table", response_model=FinlandBoardTablePayload)
def get_finland_board_table(
    view: str = Query(...),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    tz: str = Query(default="Europe/Helsinki"),
):
    return build_finland_board_table_payload(db, view=view, start=start, end=end, tz=tz)


@app.get("/api/finland/board/chart", response_model=FinlandBoardChartPayload)
def get_finland_board_chart(
    fields: list[str] = Query(...),
    mode: str = Query(default="single"),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    granularity: str = Query(default="raw"),
):
    return build_finland_board_chart_payload(db, fields=fields, mode=mode, start=start, end=end, granularity=granularity)
```

- [ ] **Step 5: Add field-catalog and readiness routes**

```python
@app.get("/api/finland/board/field-catalog", response_model=FinlandBoardFieldCatalogPayload)
def get_finland_board_field_catalog():
    return {"items": build_finland_field_catalog_rows()}


@app.get("/api/finland/board/readiness", response_model=FinlandBoardReadinessPayload)
def get_finland_board_readiness():
    market_model_payload = build_finland_market_model_payload(db)
    return build_finland_board_readiness_payload(db, market_model_payload)
```

- [ ] **Step 6: Run the FastAPI route tests again**

Run: `python -m unittest tests.test_external_api_v1_routes -v`

Expected: `OK`

- [ ] **Step 7: Commit**

```bash
git add backend/server.py tests/test_external_api_v1_routes.py
git commit -m "feat: add Finland board API routes"
```

## Task 4: Add Frontend Finland Routing And API Helpers

**Files:**
- Create: `web/src/lib/finlandApi.js`
- Create: `web/src/lib/finlandBoard.test.js`
- Modify: `web/src/lib/pageRouter.js`
- Modify: `web/src/lib/pageRouter.test.js`
- Modify: `web/src/main.jsx`

- [ ] **Step 1: Write the failing frontend route and helper tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveRootPage } from './pageRouter.js';
import { buildFinlandBoardOverviewUrl, buildFinlandBoardTableUrl } from './finlandApi.js';

test('resolveRootPage switches to Finland on /finland paths', () => {
  assert.equal(resolveRootPage('/finland'), 'finland');
  assert.equal(resolveRootPage('/finland?window=7d'), 'finland');
});

test('buildFinlandBoardTableUrl encodes view and timezone', () => {
  const url = buildFinlandBoardTableUrl('http://127.0.0.1:8085/api', {
    view: 'capacity_hourly',
    tz: 'Europe/Helsinki',
  });
  assert.equal(
    url,
    'http://127.0.0.1:8085/api/finland/board/table?view=capacity_hourly&tz=Europe%2FHelsinki'
  );
});
```

- [ ] **Step 2: Run the frontend helper tests to verify they fail**

Run: `node --test web/src/lib/pageRouter.test.js web/src/lib/finlandBoard.test.js`

Expected: failure because `/finland` is unsupported and `finlandApi.js` does not exist.

- [ ] **Step 3: Add Finland API URL builders**

```javascript
export function buildFinlandBoardOverviewUrl(apiBase, { start, end } = {}) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const suffix = params.toString();
  return `${apiBase}/finland/board/overview${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardTableUrl(apiBase, { view, start, end, tz } = {}) {
  const params = new URLSearchParams();
  params.set('view', view);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  return `${apiBase}/finland/board/table?${params.toString()}`;
}
```

- [ ] **Step 4: Update root-page resolution and mounting**

```javascript
export function resolveRootPage(pathname = '/') {
  if (pathname.startsWith('/finland')) {
    return 'finland';
  }
  if (pathname.startsWith('/fingrid')) {
    return 'fingrid';
  }
  if (pathname.startsWith('/developer')) {
    return 'developer';
  }
  return 'aemo';
}
```

```javascript
import FinlandPage from './pages/FinlandPage.jsx';

const rootElement = rootPage === 'finland'
  ? <FinlandPage />
  : rootPage === 'fingrid'
    ? <FingridPage />
    : rootPage === 'developer'
      ? <DeveloperPortalPage />
      : <App />;
```

- [ ] **Step 5: Run the frontend helper tests again**

Run: `node --test web/src/lib/pageRouter.test.js web/src/lib/finlandBoard.test.js`

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add web/src/lib/finlandApi.js web/src/lib/finlandBoard.test.js web/src/lib/pageRouter.js web/src/lib/pageRouter.test.js web/src/main.jsx
git commit -m "feat: add Finland route and API helpers"
```

## Task 5: Build The Finland Page Shell, Overview, And Navigation

**Files:**
- Create: `web/src/pages/FinlandPage.jsx`
- Create: `web/src/components/finland/FinlandBoardHeader.jsx`
- Create: `web/src/components/finland/FinlandOverviewCards.jsx`
- Create: `web/src/components/finland/FinlandWorkbenchTabs.jsx`
- Modify: `web/src/App.jsx`
- Modify: `web/src/translations.js`
- Create: `web/src/lib/finlandBoard.test.js`

- [ ] **Step 1: Write a failing page-shell test**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';

test('FinlandPage fetches overview and renders workbench tabs', () => {
  const source = fs.readFileSync(path.resolve('web/src/pages/FinlandPage.jsx'), 'utf8');
  assert.match(source, /buildFinlandBoardOverviewUrl/);
  assert.match(source, /FinlandWorkbenchTabs/);
  assert.match(source, /capacity_hourly/);
});
```

- [ ] **Step 2: Run the page-shell test to verify it fails**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: `ENOENT` because `FinlandPage.jsx` and Finland components do not exist yet.

- [ ] **Step 3: Add translation copy and top-nav link**

```javascript
translations.zh.nav = {
  ...translations.zh.nav,
  finland: '芬兰市场',
};

translations.en.nav = {
  ...translations.en.nav,
  finland: 'Finland',
};
```

```jsx
{ key: 'finland', href: '/finland', label: t.nav.finland || 'Finland' }
```

- [ ] **Step 4: Create the minimal page shell and overview fetch logic**

```jsx
import { useEffect, useMemo, useState } from 'react';
import PageWorkspaceNav from '../components/PageWorkspaceNav';
import PageSection from '../components/PageSection';
import { fetchJson } from '../lib/apiClient';
import {
  buildFinlandBoardOverviewUrl,
  buildFinlandBoardReadinessUrl,
} from '../lib/finlandApi';
import FinlandBoardHeader from '../components/finland/FinlandBoardHeader';
import FinlandOverviewCards from '../components/finland/FinlandOverviewCards';
import FinlandWorkbenchTabs from '../components/finland/FinlandWorkbenchTabs';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';

export default function FinlandPage() {
  const [overviewPayload, setOverviewPayload] = useState(null);
  const [readinessPayload, setReadinessPayload] = useState(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      fetchJson(buildFinlandBoardOverviewUrl(API_BASE)),
      fetchJson(buildFinlandBoardReadinessUrl(API_BASE)),
    ]).then(([overview, readiness]) => {
      setOverviewPayload(overview);
      setReadinessPayload(readiness);
      setLoading(false);
    });
  }, []);

  return (
    <main className="min-h-screen bg-[var(--color-background)] px-6 py-8 text-[var(--color-text)]">
      <div className="mx-auto grid max-w-7xl gap-6">
        <PageWorkspaceNav
          brand="Finland Market Board"
          subtitle="Finland reserve, balancing, and spot readout"
          current="finland"
          links={[
            { key: 'home', href: '/', label: 'Australia Market' },
            { key: 'finland', href: '/finland', label: 'Finland' },
            { key: 'fingrid', href: '/fingrid', label: 'Fingrid' },
          ]}
          title="Finland Market Board"
        />
        <FinlandBoardHeader readinessPayload={readinessPayload} loading={loading} />
        <FinlandOverviewCards overviewPayload={overviewPayload} loading={loading} />
        <PageSection title="Workbench">
          <FinlandWorkbenchTabs />
        </PageSection>
      </div>
    </main>
  );
}
```

- [ ] **Step 5: Implement simple header, cards, and tabs components**

```jsx
export default function FinlandWorkbenchTabs({ activeTab = 'capacity_hourly', onTabChange = () => {} }) {
  const tabs = [
    ['capacity_hourly', 'capacity_1h'],
    ['activation_15m', 'activation_settlement_15m'],
    ['daily_capacity', 'daily_averages'],
    ['summary', 'summary_stats'],
    ['dictionary', 'field_dictionary'],
  ];
  return (
    <div className="flex flex-wrap gap-2">
      {tabs.map(([value, label]) => (
        <button
          key={value}
          onClick={() => onTabChange(value)}
          className={value === activeTab ? 'rounded bg-[var(--color-inverted)] px-3 py-2 text-[var(--color-inverted-text)]' : 'rounded border border-[var(--color-border)] px-3 py-2'}
        >
          {label}
        </button>
      ))}
    </div>
  );
}
```

- [ ] **Step 6: Run the page-shell test again**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add web/src/pages/FinlandPage.jsx web/src/components/finland/FinlandBoardHeader.jsx web/src/components/finland/FinlandOverviewCards.jsx web/src/components/finland/FinlandWorkbenchTabs.jsx web/src/App.jsx web/src/translations.js web/src/lib/finlandBoard.test.js
git commit -m "feat: add Finland market board shell"
```

## Task 6: Build The Finland Workbench Table And Linked Analysis Components

**Files:**
- Create: `web/src/components/finland/FinlandDataTable.jsx`
- Create: `web/src/components/finland/FinlandLinkedChart.jsx`
- Create: `web/src/components/finland/FinlandFieldDetailPanel.jsx`
- Modify: `web/src/pages/FinlandPage.jsx`
- Create: `web/src/lib/finlandBoard.test.js`

- [ ] **Step 1: Write failing tests for table selection and linked chart props**

```javascript
test('FinlandPage tracks selected fields for linked analysis', () => {
  const source = fs.readFileSync(path.resolve('web/src/pages/FinlandPage.jsx'), 'utf8');
  assert.match(source, /selectedFields/);
  assert.match(source, /FinlandLinkedChart/);
  assert.match(source, /FinlandFieldDetailPanel/);
});

test('FinlandDataTable accepts onSelectField callback', () => {
  const source = fs.readFileSync(path.resolve('web/src/components/finland/FinlandDataTable.jsx'), 'utf8');
  assert.match(source, /onSelectField/);
  assert.match(source, /sticky/);
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: missing component files or missing callback wiring.

- [ ] **Step 3: Create the selectable table component**

```jsx
export default function FinlandDataTable({
  columns = [],
  rows = [],
  selectedFields = [],
  onSelectField = () => {},
}) {
  return (
    <div className="overflow-auto rounded border border-[var(--color-border)] bg-[var(--color-surface)]">
      <table className="min-w-full border-separate border-spacing-0 text-sm">
        <thead className="sticky top-0 bg-[var(--color-surface)]">
          <tr>
            {columns.map((column, index) => (
              <th
                key={column.field_key}
                className={index === 0 ? 'sticky left-0 bg-[var(--color-surface)] px-3 py-2 text-left' : 'px-3 py-2 text-left'}
              >
                <button type="button" onClick={() => onSelectField(column.field_key)}>
                  {column.label || column.field_key}
                </button>
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row, rowIndex) => (
            <tr key={rowIndex}>
              {columns.map((column, index) => (
                <td
                  key={`${rowIndex}-${column.field_key}`}
                  className={index === 0 ? 'sticky left-0 bg-[var(--color-surface)] px-3 py-2' : 'px-3 py-2'}
                >
                  {row[column.field_key] ?? '-'}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
```

- [ ] **Step 4: Create linked chart and field-detail placeholders with correct interfaces**

```jsx
export default function FinlandLinkedChart({ mode = 'single', payload = null, selectedFields = [] }) {
  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-sm font-medium">Linked Chart</div>
      <div className="mt-2 text-xs text-[var(--color-muted)]">{mode}: {selectedFields.join(', ') || 'none'}</div>
      <pre className="mt-3 overflow-auto text-xs">{JSON.stringify(payload, null, 2)}</pre>
    </section>
  );
}
```

```jsx
export default function FinlandFieldDetailPanel({ field = null }) {
  if (!field) {
    return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">Select a field.</section>;
  }
  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-sm font-medium">{field.label}</div>
      <div className="mt-2 text-xs text-[var(--color-muted)]">{field.source_name} · {field.source_type} · {field.granularity}</div>
      <div className="mt-3 text-sm">{field.methodology_note}</div>
    </section>
  );
}
```

- [ ] **Step 5: Wire selection state, table fetches, and bottom linked analysis into `FinlandPage.jsx`**

```jsx
const [activeView, setActiveView] = useState('capacity_hourly');
const [tablePayload, setTablePayload] = useState(null);
const [chartPayload, setChartPayload] = useState(null);
const [fieldCatalogPayload, setFieldCatalogPayload] = useState(null);
const [selectedFields, setSelectedFields] = useState(['spot_price_fi_eur_mwh', 'imbalance_price_eur_mwh']);

const handleSelectField = (fieldKey) => {
  setSelectedFields((current) => {
    if (current.includes(fieldKey)) return current;
    if (current.length < 2) return [...current, fieldKey];
    return [current[1], fieldKey];
  });
};
```

- [ ] **Step 6: Run the frontend test file again**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: `ok`

- [ ] **Step 7: Commit**

```bash
git add web/src/components/finland/FinlandDataTable.jsx web/src/components/finland/FinlandLinkedChart.jsx web/src/components/finland/FinlandFieldDetailPanel.jsx web/src/pages/FinlandPage.jsx web/src/lib/finlandBoard.test.js
git commit -m "feat: add Finland workbench table and linked analysis"
```

## Task 7: Connect Real Board Views, Daily Modes, And Source Dictionary

**Files:**
- Modify: `web/src/pages/FinlandPage.jsx`
- Modify: `web/src/components/finland/FinlandWorkbenchTabs.jsx`
- Modify: `web/src/lib/finlandApi.js`
- Modify: `web/src/lib/finlandBoard.test.js`

- [ ] **Step 1: Write a failing test for daily segmented modes and dictionary navigation**

```javascript
test('FinlandPage supports daily segmented modes and dictionary tab state', () => {
  const source = fs.readFileSync(path.resolve('web/src/pages/FinlandPage.jsx'), 'utf8');
  assert.match(source, /dailyMode/);
  assert.match(source, /field_dictionary/);
  assert.match(source, /daily_capacity/);
  assert.match(source, /daily_activation/);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: missing `dailyMode` state or missing tab handling.

- [ ] **Step 3: Add daily segmented-control state and backend view mapping**

```jsx
const [dailyMode, setDailyMode] = useState('daily_capacity');

const effectiveView = activeView === 'daily_averages' ? dailyMode : activeView;

useEffect(() => {
  Promise.all([
    fetchJson(buildFinlandBoardTableUrl(API_BASE, { view: effectiveView, tz })),
    fetchJson(buildFinlandBoardFieldCatalogUrl(API_BASE)),
  ]).then(([tableData, catalogData]) => {
    setTablePayload(tableData);
    setFieldCatalogPayload(catalogData);
  });
}, [effectiveView, tz]);
```

- [ ] **Step 4: Add dictionary-tab row jump behavior**

```jsx
const handleDictionaryJump = (fieldKey, preferredView) => {
  setActiveView(preferredView);
  setSelectedFields([fieldKey]);
};
```

- [ ] **Step 5: Run the frontend test again**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: `ok`

- [ ] **Step 6: Commit**

```bash
git add web/src/pages/FinlandPage.jsx web/src/components/finland/FinlandWorkbenchTabs.jsx web/src/lib/finlandApi.js web/src/lib/finlandBoard.test.js
git commit -m "feat: connect Finland daily views and dictionary navigation"
```

## Task 8: Update API Contract Docs And Run Focused Regression

**Files:**
- Modify: `docs/API响应契约说明.md`
- Modify: `tests/test_external_api_v1_routes.py`
- Modify: `web/src/lib/finlandBoard.test.js`

- [ ] **Step 1: Add the new board routes to the API contract doc**

```markdown
## Finland Board

- `GET /api/finland/board/overview`
  - summary cards, source freshness, completeness
- `GET /api/finland/board/table`
  - `view=capacity_hourly|activation_15m|daily_capacity|daily_activation|summary|dictionary`
- `GET /api/finland/board/chart`
  - `fields`, `mode`, `granularity`
- `GET /api/finland/board/field-catalog`
  - field dictionary rows
- `GET /api/finland/board/readiness`
  - source-health summary for board consumers
```

- [ ] **Step 2: Run the focused backend regression**

Run: `python -m unittest tests.test_finland_board_service tests.test_external_api_v1_routes -v`

Expected: `OK`

- [ ] **Step 3: Run the focused frontend regression**

Run: `node --test web/src/lib/pageRouter.test.js web/src/lib/finlandBoard.test.js`

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add docs/API响应契约说明.md tests/test_finland_board_service.py tests/test_external_api_v1_routes.py web/src/lib/pageRouter.test.js web/src/lib/finlandBoard.test.js
git commit -m "docs: add Finland board API contracts"
```

## Self-Review

### Spec coverage

- New `/finland` route: covered in Task 4 and Task 5
- Overview + workbench + linked analysis structure: covered in Task 5 and Task 6
- Five primary board views: covered in Task 1, Task 2, and Task 7
- `/api/finland/board/*` contracts: covered in Task 3
- `/fingrid` remains source-level page: preserved by Task 4 route logic and no replacement work
- Field dictionary and methodology/source provenance: covered in Task 1, Task 2, and Task 7

### Placeholder scan

- No `TODO`, `TBD`, or “implement later” placeholders remain.
- All tasks include explicit files, code, commands, and expected outcomes.

### Type consistency

- Backend board view keys are normalized to:
  - `capacity_hourly`
  - `activation_15m`
  - `daily_capacity`
  - `daily_activation`
  - `summary`
  - `dictionary`
- Frontend route key is normalized to `finland`
- Selected field identifiers use the same field keys across contracts, chart, and detail panel.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-05-03-finland-market-board-implementation.md`. Two execution options:

**1. Subagent-Driven (recommended)** - I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** - Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
