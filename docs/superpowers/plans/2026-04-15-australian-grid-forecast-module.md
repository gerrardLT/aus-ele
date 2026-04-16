# Australian Grid Forecast Module Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a standalone Australian grid forecast module that predicts near-future grid stress, price-risk, FCAS opportunity, and storage charge/discharge windows without pretending to be an investment-grade revenue engine.

**Architecture:** Add a dedicated backend forecast engine with SQLite snapshot caching and two public endpoints, then mount a new independent frontend section for forecast results. Reuse existing market history and event tables, add a small official-source adapter for NEM predispatch, and keep all display copy translated through shared frontend translation helpers.

**Tech Stack:** FastAPI, SQLite, Python `unittest`, existing `requests`-based backend sync patterns, React 19, Vite, existing `fetchJson` helper, `node --test`, Recharts, Framer Motion.

---

## File Map

**Create:**

- `grid_forecast.py`
  - Forecast orchestration, NEM predispatch adapter, WEM core-mode builder, feature scoring, snapshot-cache usage.
- `tests/test_grid_forecast.py`
  - Backend TDD coverage for snapshot caching, NEM scoring, WEM core coverage, and route wrappers.
- `web/src/lib/gridForecast.js`
  - Pure frontend helpers: URL builders, response normalization, coverage/disclaimer copy mapping.
- `web/src/lib/gridForecast.test.js`
  - `node:test` coverage for pure forecast helpers.
- `web/src/components/GridForecast.jsx`
  - Forecast container with horizon toggle, fetch lifecycle, loading/error/empty states.
- `web/src/components/GridForecastSummaryCards.jsx`
  - Summary score cards for stress/risk/opportunity outputs.
- `web/src/components/GridForecastTimeline.jsx`
  - Future-window timeline / chart rendering.
- `web/src/components/GridForecastDrivers.jsx`
  - Driver/evidence list with source links and forecast disclaimers.

**Modify:**

- `database.py`
  - Add forecast snapshot and sync-state tables plus read/write helpers.
- `server.py`
  - Add `/api/grid-forecast` and `/api/grid-forecast/coverage` routes; keep route handlers thin by delegating to `grid_forecast.py`.
- `web/src/App.jsx`
  - Add a single independent `GridForecast` section and TOC item; remove the top-level `EventContextPanel` from the overview shell.
- `web/src/translations.js`
  - Add `forecast` translation subtree and section labels; do not hardcode forecast strings in JSX.
- `web/src/lib/eventPanelPlacement.test.js`
  - Convert the placement regression test so the app shell no longer mounts `EventContextPanel`, and mounts `GridForecast` exactly once.

**Leave alone unless blocked:**

- `grid_events.py`
  - Keep as supporting evidence/input only.
- Existing analysis components (`PeakAnalysis`, `FcasAnalysis`, `RevenueStacking`, `CycleCost`, `InvestmentAnalysis`)
  - Do not inject full forecast UI into them.

## Task 1: Add Forecast Snapshot Storage

**Files:**

- Modify: `database.py`
- Create: `tests/test_grid_forecast.py`

- [ ] **Step 1: Write the failing storage test**

```python
class GridForecastStorageTests(unittest.TestCase):
    def test_snapshot_round_trip(self):
        payload = {
            "metadata": {
                "market": "NEM",
                "region": "NSW1",
                "horizon": "24h",
                "coverage_quality": "full",
            },
            "summary": {"grid_stress_score": 78},
            "windows": [],
            "drivers": [],
        }

        self.db.upsert_grid_forecast_snapshot(
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of_bucket="2026-04-15 09:00:00",
            issued_at="2026-04-15 09:02:00",
            expires_at="2026-04-15 10:00:00",
            coverage_quality="full",
            response_payload=payload,
        )

        row = self.db.fetch_grid_forecast_snapshot(
            market="NEM",
            region="NSW1",
            horizon="24h",
            as_of_bucket="2026-04-15 09:00:00",
        )

        self.assertEqual(row["coverage_quality"], "full")
        self.assertEqual(row["response"]["summary"]["grid_stress_score"], 78)
```

- [ ] **Step 2: Run the storage test and verify it fails**

Run: `python -m unittest tests.test_grid_forecast.GridForecastStorageTests.test_snapshot_round_trip -v`

Expected: FAIL with `AttributeError` because the forecast snapshot helpers do not exist yet.

- [ ] **Step 3: Implement the minimal SQLite storage helpers**

```python
CREATE TABLE IF NOT EXISTS grid_forecast_snapshot (
    market TEXT NOT NULL,
    region TEXT NOT NULL,
    horizon TEXT NOT NULL,
    as_of_bucket TEXT NOT NULL,
    issued_at TEXT NOT NULL,
    expires_at TEXT NOT NULL,
    coverage_quality TEXT NOT NULL,
    response_json TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (market, region, horizon, as_of_bucket)
)

CREATE TABLE IF NOT EXISTS grid_forecast_sync_state (
    source TEXT PRIMARY KEY,
    last_success_at TEXT,
    last_attempt_at TEXT,
    sync_status TEXT NOT NULL,
    detail_json TEXT NOT NULL DEFAULT '{}'
)

def upsert_grid_forecast_snapshot(...):
    ...

def fetch_grid_forecast_snapshot(...):
    ...

def upsert_grid_forecast_sync_state(...):
    ...
```

- [ ] **Step 4: Run the storage test again**

Run: `python -m unittest tests.test_grid_forecast.GridForecastStorageTests.test_snapshot_round_trip -v`

Expected: PASS

- [ ] **Step 5: Commit only the storage files**

```bash
git add database.py tests/test_grid_forecast.py
git commit -m "feat: add grid forecast snapshot storage"
```

## Task 2: Build the Forecast Engine

**Files:**

- Create: `grid_forecast.py`
- Modify: `tests/test_grid_forecast.py`

- [ ] **Step 1: Write failing backend forecast tests**

```python
@mock.patch("grid_forecast.fetch_nem_predispatch_window")
def test_nem_24h_forecast_uses_predispatch_and_event_signals(self, mock_p5):
    mock_p5.return_value = [
        {"time": "2026-04-15 12:00:00", "price": -35.0, "demand_mw": 8900},
        {"time": "2026-04-15 18:00:00", "price": 420.0, "demand_mw": 12900},
    ]
    seed_recent_nem_history(self.db, region="NSW1")
    seed_event_state(self.db, region="NSW1", state_type="reserve_tightness", severity="high")

    result = grid_forecast.get_grid_forecast_response(
        self.db,
        market="NEM",
        region="NSW1",
        horizon="24h",
        as_of="2026-04-15 09:07:00",
    )

    self.assertEqual(result["metadata"]["forecast_mode"], "hybrid_signal_calibrated")
    self.assertEqual(result["metadata"]["coverage_quality"], "full")
    self.assertGreaterEqual(result["summary"]["price_spike_risk_score"], 70)
    self.assertGreaterEqual(result["summary"]["negative_price_risk_score"], 40)
    self.assertIn("reserve_tightness", result["summary"]["driver_tags"])

def test_wem_forecast_returns_core_only_and_not_investment_grade(self):
    seed_wem_slim_history(self.db)
    seed_event_state(self.db, region="WEM", state_type="network_stress", severity="medium", market="WEM")

    result = grid_forecast.get_grid_forecast_response(
        self.db,
        market="WEM",
        region="WEM",
        horizon="7d",
        as_of="2026-04-15 09:07:00",
    )

    self.assertEqual(result["metadata"]["coverage_quality"], "core_only")
    self.assertEqual(result["metadata"]["investment_grade"], False)
    self.assertIn("confidence_constrained", result["metadata"]["warnings"])

@mock.patch("grid_forecast.fetch_nem_predispatch_window")
def test_cache_hit_skips_upstream_fetch(self, mock_p5):
    mock_p5.return_value = [{"time": "2026-04-15 12:00:00", "price": 120.0, "demand_mw": 9500}]
    seed_recent_nem_history(self.db, region="NSW1")

    grid_forecast.get_grid_forecast_response(self.db, "NEM", "NSW1", "24h", "2026-04-15 09:07:00")
    grid_forecast.get_grid_forecast_response(self.db, "NEM", "NSW1", "24h", "2026-04-15 09:20:00")

    self.assertEqual(mock_p5.call_count, 1)
```

- [ ] **Step 2: Run the backend forecast tests and verify they fail**

Run: `python -m unittest tests.test_grid_forecast.GridForecastEngineTests -v`

Expected: FAIL because `grid_forecast.py` and the orchestration functions do not exist yet.

- [ ] **Step 3: Implement the minimal forecast engine**

```python
def build_as_of_bucket(as_of: str, horizon: str) -> str:
    # 24h -> hourly bucket, 7d/30d -> daily bucket
    ...

def fetch_nem_predispatch_window(region: str, as_of: str) -> list[dict]:
    # Download and parse the latest official AEMO predispatch window for the target region.
    ...

def build_recent_market_features(db, market: str, region: str, as_of: str) -> dict:
    # Use trading_price_* or wem_ess_* tables to compute recent regime and FCAS/constraint context.
    ...

def build_event_features(db, market: str, region: str, as_of: str, horizon: str) -> dict:
    # Reuse grid_event_state as explanatory future drivers when the state overlaps the forward window.
    ...

def score_forecast_windows(...):
    return {
        "summary": {...},
        "windows": [...],
        "drivers": [...],
        "metadata": {...},
    }

def get_grid_forecast_response(db, market: str, region: str, horizon: str, as_of: str | None = None) -> dict:
    cached = db.fetch_grid_forecast_snapshot(...)
    if cached and cached["expires_at"] > current_time:
        return cached["response"]
    response = build_nem_forecast(...) if market == "NEM" else build_wem_core_forecast(...)
    db.upsert_grid_forecast_snapshot(...)
    return response

def get_grid_forecast_coverage(db, market: str, region: str, horizon: str, as_of: str | None = None) -> dict:
    ...
```

Implementation rules for this task:

- NEM `24h` must use official predispatch if available.
- NEM `7d/30d` must fall back to history + events + outage/weather-derived drivers without pretending to have precise point forecasts.
- WEM must always set `coverage_quality="core_only"` in MVP.
- Return codes and structured flags, not long language-specific prose.

- [ ] **Step 4: Run the backend forecast tests again**

Run: `python -m unittest tests.test_grid_forecast.GridForecastEngineTests -v`

Expected: PASS

- [ ] **Step 5: Commit the engine slice**

```bash
git add grid_forecast.py tests/test_grid_forecast.py database.py
git commit -m "feat: add standalone grid forecast engine"
```

## Task 3: Wire the FastAPI Endpoints

**Files:**

- Modify: `server.py`
- Modify: `tests/test_grid_forecast.py`

- [ ] **Step 1: Write failing route-wrapper tests**

```python
def test_grid_forecast_route_delegates_to_engine(self):
    fake = {
        "metadata": {"coverage_quality": "full", "forecast_mode": "hybrid_signal_calibrated"},
        "summary": {"grid_stress_score": 81},
        "windows": [],
        "drivers": [],
    }
    with patched_server_db(self.db), mock.patch("grid_forecast.get_grid_forecast_response", return_value=fake):
        result = server.get_grid_forecast(market="NEM", region="NSW1", horizon="24h", as_of=None)
    self.assertEqual(result["summary"]["grid_stress_score"], 81)

def test_grid_forecast_coverage_route_delegates_to_engine(self):
    fake = {"coverage_quality": "core_only", "sources_used": ["event_state", "wem_ess_slim"]}
    with patched_server_db(self.db), mock.patch("grid_forecast.get_grid_forecast_coverage", return_value=fake):
        result = server.get_grid_forecast_coverage(market="WEM", region="WEM", horizon="7d", as_of=None)
    self.assertEqual(result["coverage_quality"], "core_only")
```

- [ ] **Step 2: Run the route tests and verify they fail**

Run: `python -m unittest tests.test_grid_forecast.GridForecastRouteTests -v`

Expected: FAIL because the route functions do not exist yet.

- [ ] **Step 3: Add the thin FastAPI route wrappers**

```python
@app.get("/api/grid-forecast")
def get_grid_forecast(
    market: str = Query(...),
    region: str = Query(...),
    horizon: str = Query(..., pattern="^(24h|7d|30d)$"),
    as_of: Optional[str] = Query(None),
):
    return grid_forecast.get_grid_forecast_response(db, market=market, region=region, horizon=horizon, as_of=as_of)

@app.get("/api/grid-forecast/coverage")
def get_grid_forecast_coverage(
    market: str = Query(...),
    region: str = Query(...),
    horizon: str = Query(..., pattern="^(24h|7d|30d)$"),
    as_of: Optional[str] = Query(None),
):
    return grid_forecast.get_grid_forecast_coverage(db, market=market, region=region, horizon=horizon, as_of=as_of)
```

Keep the handlers thin. Do not paste forecast logic into `server.py`.

- [ ] **Step 4: Run the route tests again**

Run: `python -m unittest tests.test_grid_forecast.GridForecastRouteTests -v`

Expected: PASS

- [ ] **Step 5: Commit the API slice**

```bash
git add server.py tests/test_grid_forecast.py
git commit -m "feat: expose grid forecast API routes"
```

## Task 4: Add Frontend Forecast Helpers and Copy

**Files:**

- Create: `web/src/lib/gridForecast.js`
- Create: `web/src/lib/gridForecast.test.js`
- Modify: `web/src/translations.js`

- [ ] **Step 1: Write failing frontend helper tests**

```javascript
import test from 'node:test';
import assert from 'node:assert/strict';
import {
  buildGridForecastUrl,
  normalizeForecastResponse,
  getForecastCoverageCopy,
} from './gridForecast.js';

test('buildGridForecastUrl includes market region horizon and optional as_of', () => {
  const url = buildGridForecastUrl('http://127.0.0.1:8085/api', {
    market: 'NEM',
    region: 'NSW1',
    horizon: '24h',
    asOf: '2026-04-15 09:00:00',
  });

  assert.match(url, /market=NEM/);
  assert.match(url, /region=NSW1/);
  assert.match(url, /horizon=24h/);
  assert.match(url, /as_of=2026-04-15/);
});

test('normalizeForecastResponse sorts future windows and preserves warnings', () => {
  const normalized = normalizeForecastResponse({
    metadata: { coverage_quality: 'core_only', warnings: ['confidence_constrained'] },
    windows: [
      { start_time: '2026-04-15 18:00:00', end_time: '2026-04-15 20:00:00', window_type: 'discharge' },
      { start_time: '2026-04-15 11:00:00', end_time: '2026-04-15 13:00:00', window_type: 'charge' },
    ],
  });

  assert.equal(normalized.windows[0].window_type, 'charge');
  assert.deepEqual(normalized.metadata.warnings, ['confidence_constrained']);
});

test('getForecastCoverageCopy returns Chinese copy for core-only WEM mode', () => {
  const copy = getForecastCoverageCopy('core_only', 'zh');
  assert.match(copy, /核心/);
});
```

- [ ] **Step 2: Run the frontend helper tests and verify they fail**

Run: `node --test web/src/lib/gridForecast.test.js`

Expected: FAIL because the helper module does not exist yet.

- [ ] **Step 3: Implement the helper module and translation keys**

```javascript
export function buildGridForecastUrl(apiBase, { market, region, horizon, asOf }) {
  const params = new URLSearchParams({ market, region, horizon });
  if (asOf) params.set('as_of', asOf);
  return `${apiBase}/grid-forecast?${params.toString()}`;
}

export function normalizeForecastResponse(payload = {}) {
  const windows = [...(payload.windows || [])].sort((a, b) =>
    String(a.start_time).localeCompare(String(b.start_time))
  );

  return {
    metadata: payload.metadata || {},
    summary: payload.summary || {},
    windows,
    drivers: payload.drivers || [],
  };
}

export function getForecastCoverageCopy(coverageQuality, locale = 'en') {
  ...
}
```

Add a `forecast` subtree in `translations.js` for:

- section title/subtitle
- horizon labels
- card labels
- driver/evidence labels
- coverage labels
- warnings/disclaimers
- “standalone forecast module” description

- [ ] **Step 4: Run the frontend helper tests again**

Run: `node --test web/src/lib/gridForecast.test.js`

Expected: PASS

- [ ] **Step 5: Commit the frontend helper slice**

```bash
git add web/src/lib/gridForecast.js web/src/lib/gridForecast.test.js web/src/translations.js
git commit -m "feat: add grid forecast frontend helpers and copy"
```

## Task 5: Build the Independent Forecast UI and Replace the Old App-Shell Explanation Panel

**Files:**

- Create: `web/src/components/GridForecast.jsx`
- Create: `web/src/components/GridForecastSummaryCards.jsx`
- Create: `web/src/components/GridForecastTimeline.jsx`
- Create: `web/src/components/GridForecastDrivers.jsx`
- Modify: `web/src/App.jsx`
- Modify: `web/src/lib/eventPanelPlacement.test.js`

- [ ] **Step 1: Write the failing placement regression test**

```javascript
test('app mounts one standalone GridForecast section and no top-level EventContextPanel', () => {
  const appSource = fs.readFileSync(appPath, 'utf8');

  assert.equal(countOccurrences(appSource, /<GridForecast\b/g), 1);
  assert.equal(countOccurrences(appSource, /<EventContextPanel\b/g), 0);
});
```

- [ ] **Step 2: Run the placement test and verify it fails**

Run: `node --test web/src/lib/eventPanelPlacement.test.js`

Expected: FAIL because `App.jsx` still mounts `EventContextPanel` and does not mount `GridForecast`.

- [ ] **Step 3: Implement the independent forecast UI**

```jsx
export default function GridForecast({ apiBase, region, year, locale }) {
  const market = region === 'WEM' ? 'WEM' : 'NEM';
  const [horizon, setHorizon] = useState('24h');
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  useEffect(() => {
    const controller = new AbortController();
    setLoading(true);
    fetchJson(
      buildGridForecastUrl(apiBase, { market, region, horizon }),
      { signal: controller.signal }
    )
      .then((data) => setPayload(normalizeForecastResponse(data)))
      .catch((err) => {
        if (err?.name !== 'AbortError') setError(err);
      })
      .finally(() => setLoading(false));
    return () => controller.abort();
  }, [apiBase, market, region, horizon]);

  return (
    <section>
      <GridForecastSummaryCards ... />
      <GridForecastTimeline ... />
      <GridForecastDrivers ... />
    </section>
  );
}
```

App-shell rules for this task:

- Add `sec-forecast` to the TOC and active-section tracking.
- Mount `GridForecast` exactly once as its own section.
- Remove `EventContextPanel` import and top-level usage from `App.jsx`.
- Keep lightweight event overlays on `PriceChart` only; do not re-add explanation panels under analysis charts.
- Forecast module should ignore `month / quarter / day_type` because it is forward-looking, not a historical slice view.

- [ ] **Step 4: Run the placement test and the new forecast helper tests**

Run: `node --test web/src/lib/gridForecast.test.js web/src/lib/eventPanelPlacement.test.js`

Expected: PASS

- [ ] **Step 5: Commit the UI slice**

```bash
git add web/src/components/GridForecast.jsx web/src/components/GridForecastSummaryCards.jsx web/src/components/GridForecastTimeline.jsx web/src/components/GridForecastDrivers.jsx web/src/App.jsx web/src/lib/eventPanelPlacement.test.js
git commit -m "feat: add standalone grid forecast module UI"
```

## Task 6: Run Full Verification and Fix Any Regressions Before Claiming Completion

**Files:**

- Modify as needed: only files touched in Tasks 1-5

- [ ] **Step 1: Run the backend suite that covers the new forecast work plus existing business logic**

Run: `python -m unittest tests.test_grid_forecast tests.test_non_engineering_fixes tests.test_event_overlays -v`

Expected: PASS with `0 failures` and `0 errors`

- [ ] **Step 2: Run the frontend logic tests**

Run: `node --test web/src/lib/gridForecast.test.js web/src/lib/apiClient.test.js web/src/lib/investmentAnalysis.test.js web/src/lib/eventOverlays.test.js web/src/lib/eventPanelPlacement.test.js`

Expected: PASS

- [ ] **Step 3: Run the production build**

Run: `npm run build`

Expected: exit code `0`

- [ ] **Step 4: Manual smoke-check the new module locally**

Run backend: `python server.py`

Run frontend: `npm run dev`

Manual checks:

- Select `NSW1` and confirm the new `Grid Forecast` section appears once.
- Confirm horizon toggle updates only the forecast module.
- Confirm `WEM` shows `core-only` / non-investment-grade warning.
- Confirm Chinese and English labels both render correctly.
- Confirm old top-level event explanation panel is gone.

- [ ] **Step 5: Create the final focused commit**

```bash
git add database.py grid_forecast.py server.py tests/test_grid_forecast.py web/src/App.jsx web/src/translations.js web/src/lib/gridForecast.js web/src/lib/gridForecast.test.js web/src/lib/eventPanelPlacement.test.js web/src/components/GridForecast.jsx web/src/components/GridForecastSummaryCards.jsx web/src/components/GridForecastTimeline.jsx web/src/components/GridForecastDrivers.jsx
git commit -m "feat: ship standalone australian grid forecast module"
```

## Notes for the Implementer

- The current worktree is dirty. Stage only the files listed in each task and do not scoop unrelated changes into forecast commits.
- Keep forecast response objects code-like and language-neutral; let the frontend translate labels and warnings.
- WEM honesty matters more than symmetry. If a signal is thin, downgrade confidence and keep the `core_only` label.
- Do not thread the new forecast engine into `InvestmentAnalysis` or `BessSimulator` in this implementation slice.
- If the official NEM predispatch source shape is awkward, encapsulate the parsing entirely inside `grid_forecast.py`; do not leak parsing details into routes or JSX.
