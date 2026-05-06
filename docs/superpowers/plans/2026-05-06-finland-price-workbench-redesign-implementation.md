# Finland Price Workbench Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the Finland board from a table-first surface into a price-first workbench with a default primary reserve price, a dominant main chart, a compact supporting comparison rail, and a de-emphasized verification table.

**Architecture:** Keep the current Finland API contracts and page shell, but refactor the `/finland` route into a layered workbench. The page will derive summary metrics from existing chart/table payloads, add a dedicated primary price selection model, and promote analysis into the main visual center while preserving the table and dictionary as support layers.

**Tech Stack:** React, Vite, Tailwind utility classes, Recharts, existing Finland API helpers, Node built-in test runner, Python unittest for backend route/service verification.

---

## File Structure

### Existing files to modify

- `web/src/pages/FinlandPage.jsx`
  - Recompose page layout around a price-first workbench.
  - Introduce default primary price state and primary chart selection flow.
- `web/src/lib/finlandApi.js`
  - Add helpers for primary price defaults, summary metric derivation, and supporting rail request construction.
- `web/src/lib/finlandBoard.test.js`
  - Add test coverage for the new frontend helper contracts.
- `web/src/components/finland/FinlandLinkedChart.jsx`
  - Narrow this component to the main chart use case or replace it with a cleaner contract if split.
- `web/src/components/finland/FinlandDataTable.jsx`
  - De-emphasize the verification table presentation and keep field selection behavior.
- `web/src/translations.js`
  - Add translation-backed copy for the new workbench sections and metric labels.

### New files to create

- `web/src/components/finland/FinlandPrimaryPriceWorkbench.jsx`
  - Orchestrates the summary strip, primary selector, main chart, and support rail.
- `web/src/components/finland/FinlandPriceSummaryStrip.jsx`
  - Displays latest, high, low, average, volatility, and spread cues for the selected price.
- `web/src/components/finland/FinlandPrimaryPriceSelector.jsx`
  - Compact field selector for the main price focus.
- `web/src/components/finland/FinlandComparisonRail.jsx`
  - Renders compact support charts for spot, imbalance, and procured volume.

### Existing backend files to verify, but not necessarily change

- `backend/server.py`
- `backend/finland_board_service.py`

These should only change if the existing chart/table payloads prove insufficient during implementation. The plan assumes we can derive summary metrics client-side first.

---

### Task 1: Lock the frontend helper contract for the new price-first workbench

**Files:**
- Modify: `web/src/lib/finlandApi.js`
- Modify: `web/src/lib/finlandBoard.test.js`

- [ ] **Step 1: Write the failing frontend helper tests**

Add tests covering:
- default primary field fallback
- summary metric derivation from chart/table rows
- supporting rail field mapping for each primary price
- single-primary chart request behavior

```js
test('getDefaultFinlandPrimaryPriceField returns FCR-N capacity price', () => {
  assert.equal(getDefaultFinlandPrimaryPriceField(), 'fcr_n_price_eur_mw');
});

test('buildFinlandPrimaryPriceSummary derives latest high low mean and spread cues', () => {
  const rows = [
    { timestamp_helsinki: '2026-05-01T01:00:00+03:00', fcr_n_price_eur_mw: 10, spot_price_fi_eur_mwh: 52 },
    { timestamp_helsinki: '2026-05-01T02:00:00+03:00', fcr_n_price_eur_mw: 18, spot_price_fi_eur_mwh: 55 },
    { timestamp_helsinki: '2026-05-01T03:00:00+03:00', fcr_n_price_eur_mw: 14, spot_price_fi_eur_mwh: 50 },
  ];

  assert.deepEqual(
    buildFinlandPrimaryPriceSummary({ primaryFieldKey: 'fcr_n_price_eur_mw', tableRows: rows }),
    {
      latestValue: 14,
      highValue: 18,
      lowValue: 10,
      meanValue: 14,
      spreadVsSpotLatest: -36,
      volatilityLabel: 'medium',
    },
  );
});

test('buildFinlandComparisonRailRequest maps reserve price focus to support fields', () => {
  assert.deepEqual(
    buildFinlandComparisonRailRequest({ primaryFieldKey: 'fcr_d_up_price_eur_mw', granularity: '1h' }),
    {
      fields: ['spot_price_fi_eur_mwh', 'imbalance_price_eur_mwh', 'fcr_d_up_volume_mw'],
      mode: 'compare',
      granularity: '1h',
      limitPoints: 240,
    },
  );
});
```

- [ ] **Step 2: Run the frontend helper tests to verify they fail**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: FAIL with missing exports such as `getDefaultFinlandPrimaryPriceField` and `buildFinlandPrimaryPriceSummary`

- [ ] **Step 3: Implement the minimal helper functions in `finlandApi.js`**

Add focused exports rather than burying this logic inside the page:

```js
const DEFAULT_FINLAND_PRIMARY_PRICE_FIELD = 'fcr_n_price_eur_mw';

export function getDefaultFinlandPrimaryPriceField() {
  return DEFAULT_FINLAND_PRIMARY_PRICE_FIELD;
}

export function buildFinlandPrimaryPriceSummary({ primaryFieldKey, tableRows = [] } = {}) {
  const values = tableRows
    .map((row) => row?.[primaryFieldKey])
    .filter((value) => value !== null && value !== undefined)
    .map(Number);

  const latestValue = values.at(-1) ?? null;
  const highValue = values.length ? Math.max(...values) : null;
  const lowValue = values.length ? Math.min(...values) : null;
  const meanValue = values.length
    ? Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(2))
    : null;

  const latestRow = tableRows.at(-1) || {};
  const spotValue = latestRow.spot_price_fi_eur_mwh ?? null;
  const spreadVsSpotLatest = latestValue !== null && spotValue !== null
    ? Number((latestValue - spotValue).toFixed(2))
    : null;

  let volatilityLabel = 'low';
  if (highValue !== null && lowValue !== null && (highValue - lowValue) >= 10) {
    volatilityLabel = 'high';
  } else if (highValue !== null && lowValue !== null && (highValue - lowValue) >= 4) {
    volatilityLabel = 'medium';
  }

  return { latestValue, highValue, lowValue, meanValue, spreadVsSpotLatest, volatilityLabel };
}

export function buildFinlandComparisonRailRequest({ primaryFieldKey, granularity, limitPoints = 240 } = {}) {
  const volumeFieldMap = {
    fcr_n_price_eur_mw: 'fcr_n_volume_mw',
    fcr_d_up_price_eur_mw: 'fcr_d_up_volume_mw',
    fcr_d_down_price_eur_mw: 'fcr_d_down_volume_mw',
  };

  return {
    fields: ['spot_price_fi_eur_mwh', 'imbalance_price_eur_mwh', volumeFieldMap[primaryFieldKey]].filter(Boolean),
    mode: 'compare',
    granularity: granularity || '1h',
    limitPoints,
  };
}
```

- [ ] **Step 4: Run the frontend helper tests to verify they pass**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: PASS

- [ ] **Step 5: Commit the helper contract**

```bash
git add web/src/lib/finlandApi.js web/src/lib/finlandBoard.test.js
git commit -m "feat: add finland price workbench helper contracts"
```

---

### Task 2: Add translation-backed copy and primary workbench components

**Files:**
- Create: `web/src/components/finland/FinlandPrimaryPriceSelector.jsx`
- Create: `web/src/components/finland/FinlandPriceSummaryStrip.jsx`
- Create: `web/src/components/finland/FinlandComparisonRail.jsx`
- Create: `web/src/components/finland/FinlandPrimaryPriceWorkbench.jsx`
- Modify: `web/src/translations.js`

- [ ] **Step 1: Write the failing component/text tests**

Extend `web/src/lib/finlandBoard.test.js` to assert:
- translation keys exist for primary selector, summary strip, comparison rail
- `FinlandPage.jsx` references those translation-backed sections

```js
test('Finland translations expose price workbench labels', () => {
  const boardCopy = translations.zh.finlandBoard;
  assert.ok(boardCopy.priceWorkbench);
  assert.equal(boardCopy.priceWorkbench.primaryFieldLabel.length > 0, true);
  assert.equal(boardCopy.priceWorkbench.summary.latest.length > 0, true);
  assert.equal(boardCopy.priceWorkbench.comparison.title.length > 0, true);
});

test('FinlandPage uses price workbench shell components', () => {
  const source = fs.readFileSync(path.join(__dirname, '../pages/FinlandPage.jsx'), 'utf8');
  assert.match(source, /FinlandPrimaryPriceWorkbench/);
  assert.match(source, /priceWorkbench/);
});
```

- [ ] **Step 2: Run the frontend test file to verify it fails**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: FAIL because translation keys and component references are missing

- [ ] **Step 3: Add translation-backed copy and create the new components**

Add a compact copy structure to `translations.js`:

```js
priceWorkbench: {
  eyebrow: 'Price Workbench',
  title: 'Reserve Price Focus',
  primaryFieldLabel: 'Primary price',
  summary: {
    latest: 'Latest',
    high: 'High',
    low: 'Low',
    average: 'Average',
    volatility: 'Volatility',
    spreadVsSpot: 'Spread vs Spot',
  },
  comparison: {
    title: 'Support Rail',
    description: 'Spot, imbalance, and procured volume explain the main move.',
  },
}
```

Create lightweight focused components:

```jsx
export default function FinlandPrimaryPriceSelector({ options = [], value, onChange, label }) {
  return (
    <section className="grid gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {label}
      </div>
      <div className="flex flex-wrap gap-2">
        {options.map((option) => {
          const active = option.value === value;
          return (
            <button
              key={option.value}
              type="button"
              onClick={() => onChange(option.value)}
              className={active ? 'rounded-full bg-[var(--color-inverted)] px-3 py-2 text-sm text-[var(--color-inverted-text)]' : 'rounded-full border border-[var(--color-border)] px-3 py-2 text-sm text-[var(--color-text)]'}
            >
              {option.label}
            </button>
          );
        })}
      </div>
    </section>
  );
}
```

```jsx
export default function FinlandPriceSummaryStrip({ items = [] }) {
  return (
    <section className="grid gap-3 md:grid-cols-6">
      {items.map((item) => (
        <article key={item.key} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
          <div className="text-[11px] uppercase tracking-[0.14em] text-[var(--color-muted)]">{item.label}</div>
          <div className="mt-2 text-xl font-semibold text-[var(--color-text)]">{item.value}</div>
        </article>
      ))}
    </section>
  );
}
```

- [ ] **Step 4: Run the frontend tests to verify the new copy/component contract passes**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: PASS

- [ ] **Step 5: Commit the new workbench building blocks**

```bash
git add web/src/components/finland/FinlandPrimaryPriceSelector.jsx web/src/components/finland/FinlandPriceSummaryStrip.jsx web/src/components/finland/FinlandComparisonRail.jsx web/src/components/finland/FinlandPrimaryPriceWorkbench.jsx web/src/translations.js web/src/lib/finlandBoard.test.js
git commit -m "feat: scaffold finland price workbench components"
```

---

### Task 3: Recompose `FinlandPage` so the workbench becomes the visual center

**Files:**
- Modify: `web/src/pages/FinlandPage.jsx`
- Modify: `web/src/components/finland/FinlandDataTable.jsx`

- [ ] **Step 1: Write the failing page-structure tests**

Extend `web/src/lib/finlandBoard.test.js` to assert:
- `FinlandPage` initializes a default primary price field
- `FinlandPrimaryPriceWorkbench` appears before the data table
- analysis is no longer the only place the chart exists

```js
test('FinlandPage initializes a default primary price field for the workbench', () => {
  const source = fs.readFileSync(path.join(__dirname, '../pages/FinlandPage.jsx'), 'utf8');
  assert.match(source, /getDefaultFinlandPrimaryPriceField/);
  assert.match(source, /const \\[primaryFieldKey, setPrimaryFieldKey\\]/);
});

test('FinlandPage renders the price workbench above the verification table', () => {
  const source = fs.readFileSync(path.join(__dirname, '../pages/FinlandPage.jsx'), 'utf8');
  const workbenchIndex = source.indexOf('FinlandPrimaryPriceWorkbench');
  const tableIndex = source.indexOf('FinlandDataTable');
  assert.equal(workbenchIndex < tableIndex, true);
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: `node --test web/src/lib/finlandBoard.test.js web/src/lib/pageRouter.test.js`

Expected: FAIL because the page does not yet initialize `primaryFieldKey` or render the new workbench

- [ ] **Step 3: Refactor `FinlandPage` and tone down the table**

Update page state and composition:

```jsx
const [primaryFieldKey, setPrimaryFieldKey] = useState(() => getDefaultFinlandPrimaryPriceField());

const primaryFieldOptions = useMemo(
  () => tableColumns
    .filter((column) => /price/i.test(column.field_key))
    .map((column) => ({ value: column.field_key, label: column.label })),
  [tableColumns],
);

const primarySummary = useMemo(
  () => buildFinlandPrimaryPriceSummary({ primaryFieldKey, tableRows }),
  [primaryFieldKey, tableRows],
);

const comparisonRailRequest = useMemo(
  () => buildFinlandComparisonRailRequest({
    primaryFieldKey,
    granularity: tablePayload?.granularity,
    limitPoints: BOARD_CHART_LIMIT_POINTS,
  }),
  [primaryFieldKey, tablePayload],
);
```

Render structure:

```jsx
<FinlandPrimaryPriceWorkbench
  apiBase={API_BASE}
  primaryFieldKey={primaryFieldKey}
  onPrimaryFieldChange={setPrimaryFieldKey}
  primaryFieldOptions={primaryFieldOptions}
  summary={primarySummary}
  mainChartRequest={{
    fields: [primaryFieldKey],
    mode: 'single',
    granularity: tablePayload?.granularity || '1h',
    limitPoints: BOARD_CHART_LIMIT_POINTS,
  }}
  comparisonRailRequest={comparisonRailRequest}
  selectedField={selectedFields.find((field) => field.field_key === primaryFieldKey) || null}
  copy={copy.priceWorkbench}
/>

<FinlandDataTable className="opacity-90" ... />
```

Tone down the table header treatment so it reads as a verification layer rather than the hero:

```jsx
<section className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)]/86">
```

- [ ] **Step 4: Run the frontend tests to verify the page composition passes**

Run: `node --test web/src/lib/finlandBoard.test.js web/src/lib/pageRouter.test.js`

Expected: PASS

- [ ] **Step 5: Commit the page composition shift**

```bash
git add web/src/pages/FinlandPage.jsx web/src/components/finland/FinlandDataTable.jsx web/src/lib/finlandBoard.test.js
git commit -m "feat: promote finland price workbench above verification table"
```

---

### Task 4: Implement the main chart and support rail presentation

**Files:**
- Modify: `web/src/components/finland/FinlandLinkedChart.jsx`
- Modify: `web/src/components/finland/FinlandComparisonRail.jsx`
- Modify: `web/src/components/finland/FinlandPrimaryPriceWorkbench.jsx`
- Modify: `web/src/components/finland/FinlandFieldDetailPanel.jsx`

- [ ] **Step 1: Write the failing UI contract tests**

Extend `web/src/lib/finlandBoard.test.js` to assert:
- main chart remains single-series for the primary field
- comparison rail uses support fields
- field detail panel remains available but secondary

```js
test('Finland price workbench separates main chart from support rail requests', () => {
  assert.deepEqual(
    buildFinlandBoardChartRequest({
      selectedFields: [{ field_key: 'fcr_n_price_eur_mw', granularity: '1h' }],
      viewGranularity: '1h',
      limitPoints: 240,
    }),
    {
      fields: ['fcr_n_price_eur_mw'],
      mode: 'single',
      granularity: '1h',
      limitPoints: 240,
    },
  );
});
```

- [ ] **Step 2: Run the frontend tests to verify they fail**

Run: `node --test web/src/lib/finlandBoard.test.js`

Expected: FAIL if the workbench and comparison rail have not yet adopted the new contract

- [ ] **Step 3: Implement the main chart and support rail rendering**

Keep the main chart visually dominant:

```jsx
<div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_22rem]">
  <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
    <FinlandLinkedChart
      apiBase={apiBase}
      chartRequest={mainChartRequest}
      selectedFields={selectedField ? [selectedField] : []}
      copy={copy.mainChart}
    />
  </section>
  <FinlandFieldDetailPanel
    selectedFields={selectedField ? [selectedField] : []}
    copy={copy.fieldDetailPanel}
  />
</div>

<FinlandComparisonRail
  apiBase={apiBase}
  chartRequest={comparisonRailRequest}
  copy={copy.comparison}
/>
```

For the comparison rail, prefer compact strips over another full-height chart:

```jsx
<section className="grid gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4 md:grid-cols-3">
  {series.map((item) => (
    <article key={item.field_key} className="rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]/50 p-3">
      <div className="text-xs uppercase tracking-[0.12em] text-[var(--color-muted)]">{item.label}</div>
      <div className="mt-3 h-24">{/* compact line chart */}</div>
    </article>
  ))}
</section>
```

- [ ] **Step 4: Run the frontend tests and a local page smoke check**

Run:
- `node --test web/src/lib/finlandBoard.test.js web/src/lib/pageRouter.test.js`
- `python - <<'PY'\nimport requests\nprint(requests.get('http://127.0.0.1:5173/finland', timeout=30).status_code)\nPY`

Expected:
- Tests: PASS
- HTTP status: `200`

- [ ] **Step 5: Commit the chart hierarchy implementation**

```bash
git add web/src/components/finland/FinlandLinkedChart.jsx web/src/components/finland/FinlandComparisonRail.jsx web/src/components/finland/FinlandPrimaryPriceWorkbench.jsx web/src/components/finland/FinlandFieldDetailPanel.jsx web/src/lib/finlandBoard.test.js
git commit -m "feat: redesign finland chart hierarchy around primary price focus"
```

---

### Task 5: Run live QA and performance verification against `/finland`

**Files:**
- Modify if needed: `web/src/pages/FinlandPage.jsx`
- Modify if needed: `web/src/components/finland/*.jsx`
- Evidence only: `backend-live.out.log`, `backend-live.err.log`, `web-live.out.log`, `web-live.err.log`

- [ ] **Step 1: Write the live QA checklist into the plan execution notes**

Use this runtime checklist:

```text
1. Capacity tab loads with a visible price-focused workbench before the table.
2. Default primary field is FCR-N Capacity Price.
3. Main chart renders exactly one primary series.
4. Support rail renders spot, imbalance, and mapped procured volume.
5. Daily tab still switches to daily_capacity and daily_activation correctly.
6. Table remains available below the workbench.
7. No console errors, no 4xx/5xx API responses.
8. No Recharts width/height warnings.
```

- [ ] **Step 2: Run browser QA with Playwright**

Run:

```bash
node - <<'NODE'
const { chromium } = require('./.tmp-playwright/node_modules/playwright');
(async() => {
  const browser = await chromium.launch({ headless: true, executablePath: `${process.env.USERPROFILE}\\AppData\\Local\\ms-playwright\\chromium-1169\\chrome-win\\chrome.exe` });
  const page = await browser.newPage({ viewport: { width: 1440, height: 1100 } });
  const consoleEvents = [];
  const badResponses = [];
  page.on('console', msg => consoleEvents.push(msg.text()));
  page.on('response', res => {
    if (res.url().includes('/api/') && res.status() >= 400) badResponses.push([res.url(), res.status()]);
  });
  await page.goto('http://127.0.0.1:5173/finland', { waitUntil: 'networkidle', timeout: 120000 });
  await page.screenshot({ path: 'artifacts-finland-price-workbench.png' });
  console.log(JSON.stringify({
    consoleEvents,
    badResponses,
    chartCount: await page.locator('svg.recharts-surface').count(),
    rows: await page.locator('table tbody tr').count(),
  }, null, 2));
  await browser.close();
})();
NODE
```

Expected:
- `badResponses: []`
- `chartCount >= 2` after the comparison rail is added
- `rows > 0`
- no width/height warnings in `consoleEvents`

- [ ] **Step 3: Fix any visual or runtime regressions uncovered by QA**

Only make narrow fixes tied to the checklist. Typical acceptable fixes:

```jsx
<section className="min-w-0">
```

```js
const safeRows = Array.isArray(rows) ? rows : [];
```

```jsx
{hasData ? <LineChart ... /> : <div className="grid h-24 place-items-center">No data</div>}
```

- [ ] **Step 4: Re-run the QA commands to verify all checks pass**

Run:
- `node --test web/src/lib/finlandBoard.test.js web/src/lib/pageRouter.test.js`
- the Playwright QA script from Step 2

Expected: PASS with no console warnings/errors and no failed API responses

- [ ] **Step 5: Commit the final QA cleanup**

```bash
git add web/src/pages/FinlandPage.jsx web/src/components/finland web/src/lib/finlandApi.js web/src/lib/finlandBoard.test.js web/src/translations.js
git commit -m "feat: ship finland price-first workbench redesign"
```

---

## Spec Coverage Check

This plan covers the spec requirements as follows:

- price-first main visual center: Tasks 2, 3, 4
- default `FCR-N Capacity Price`: Tasks 1, 3
- summary strip with latest/high/low/average/volatility/spread: Tasks 1, 2, 3
- main price chart dominance: Tasks 3, 4
- support rail with spot/imbalance/volume: Tasks 1, 4
- de-emphasized verification table: Task 3
- translation-backed copy: Task 2
- stable loading/runtime verification: Task 5

No uncovered spec sections remain.

## Placeholder Scan

Checked for `TBD`, `TODO`, "appropriate error handling", and undefined tasks. None remain. All tasks include file paths, commands, and concrete code targets.

## Type Consistency Check

Planned helper names are consistent across tasks:

- `getDefaultFinlandPrimaryPriceField`
- `buildFinlandPrimaryPriceSummary`
- `buildFinlandComparisonRailRequest`
- `FinlandPrimaryPriceWorkbench`
- `primaryFieldKey`

These names are reused consistently in the page, helper, and test tasks.
