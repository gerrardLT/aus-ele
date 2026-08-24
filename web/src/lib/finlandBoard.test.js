import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  FINLAND_DAILY_BOARD_VIEWS,
  FINLAND_PRIMARY_BOARD_TABS,
  buildFinlandBoardChartUrl,
  buildFinlandBoardChartRequest,
  buildFinlandComparisonRailRequest,
  buildFinlandBoardDictionaryRows,
  buildFinlandBoardFieldCatalogUrl,
  buildFinlandBoardOverviewUrl,
  buildFinlandBoardReadinessUrl,
  buildFinlandPrimaryPriceOptions,
  buildFinlandBoardSelectedFields,
  buildFinlandPrimaryPriceSummary,
  buildFinlandBoardTableUrl,
  getDefaultFinlandPrimaryPriceField,
  getFinlandDictionaryTargetView,
  getFinlandBoardOverviewCards,
  getFinlandBoardTableColumns,
  getFinlandBoardTableRows,
  normalizeFinlandDictionaryJumpTarget,
  resolveFinlandBoardView,
} from './finlandApi.js';
import { translations } from '../translations.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

test('buildFinlandBoardOverviewUrl includes optional time filters', () => {
  assert.equal(
    buildFinlandBoardOverviewUrl('http://127.0.0.1:8085/api', {
      start: '2026-05-01T00:00:00Z',
      end: '2026-05-02T00:00:00Z',
    }),
    'http://127.0.0.1:8085/api/finland/board/overview?start=2026-05-01T00%3A00%3A00Z&end=2026-05-02T00%3A00%3A00Z',
  );
});

test('buildFinlandBoardOverviewUrl omits a trailing query marker when filters are missing', () => {
  assert.equal(
    buildFinlandBoardOverviewUrl('http://127.0.0.1:8085/api'),
    'http://127.0.0.1:8085/api/finland/board/overview',
  );
});

test('buildFinlandBoardTableUrl encodes expected query params', () => {
  assert.equal(
    buildFinlandBoardTableUrl('http://127.0.0.1:8085/api', {
      view: 'capacity_hourly',
      start: '2026-05-01T00:00:00Z',
      end: '2026-05-02T00:00:00Z',
      tz: 'Europe/Helsinki',
      limit: 240,
    }),
    'http://127.0.0.1:8085/api/finland/board/table?view=capacity_hourly&start=2026-05-01T00%3A00%3A00Z&end=2026-05-02T00%3A00%3A00Z&tz=Europe%2FHelsinki&limit=240',
  );
});

test('buildFinlandBoardTableUrl omits undefined params and bare trailing query markers', () => {
  assert.equal(
    buildFinlandBoardTableUrl('http://127.0.0.1:8085/api'),
    'http://127.0.0.1:8085/api/finland/board/table',
  );
  assert.equal(
    buildFinlandBoardTableUrl('http://127.0.0.1:8085/api', {
      tz: 'Europe/Helsinki',
    }),
    'http://127.0.0.1:8085/api/finland/board/table?tz=Europe%2FHelsinki',
  );
});

test('Finland board view helpers resolve daily tabs and dictionary jumps to backend view keys', () => {
  assert.deepEqual(FINLAND_DAILY_BOARD_VIEWS, ['daily_capacity', 'daily_activation']);
  assert.deepEqual(FINLAND_PRIMARY_BOARD_TABS, ['capacity_hourly', 'activation_15m', 'daily']);
  assert.equal(resolveFinlandBoardView('daily', 'daily_activation'), 'daily_activation');
  assert.equal(resolveFinlandBoardView('capacity_hourly', 'daily_capacity'), 'capacity_hourly');
  assert.equal(getFinlandDictionaryTargetView('afrr_act_up_eur_mwh', '15m'), 'activation_15m');
  assert.equal(getFinlandDictionaryTargetView('mfrr_act_down_eur_mwh', 'day'), 'daily_activation');
  assert.equal(getFinlandDictionaryTargetView('fcr_n_price_eur_mw', '1h'), 'capacity_hourly');
  assert.equal(normalizeFinlandDictionaryJumpTarget('daily_activation'), 'daily');
  assert.equal(normalizeFinlandDictionaryJumpTarget('activation_15m'), 'activation_15m');
  assert.equal(normalizeFinlandDictionaryJumpTarget('field_dictionary'), 'capacity_hourly');
  assert.equal(normalizeFinlandDictionaryJumpTarget('nope'), 'capacity_hourly');
});

test('buildFinlandBoardChartUrl encodes repeated fields and chart controls', () => {
  assert.equal(
    buildFinlandBoardChartUrl('http://127.0.0.1:8085/api', {
      fields: ['fcrn_price', 'spot_price'],
      mode: 'compare',
      start: '2026-05-01T00:00:00Z',
      end: '2026-05-02T00:00:00Z',
      granularity: '4h',
      limitPoints: 180,
    }),
    'http://127.0.0.1:8085/api/finland/board/chart?fields=fcrn_price&fields=spot_price&mode=compare&start=2026-05-01T00%3A00%3A00Z&end=2026-05-02T00%3A00%3A00Z&granularity=4h&limit_points=180',
  );
});

test('buildFinlandBoardChartUrl omits a trailing query marker when all params are missing', () => {
  assert.equal(
    buildFinlandBoardChartUrl('http://127.0.0.1:8085/api'),
    'http://127.0.0.1:8085/api/finland/board/chart',
  );
});

test('Finland primary price helpers expose the default field and a stable summary contract', () => {
  assert.equal(getDefaultFinlandPrimaryPriceField(), 'fcr_n_price_eur_mw');

  assert.deepEqual(
    buildFinlandPrimaryPriceSummary({
      primaryFieldKey: 'fcr_n_price_eur_mw',
      tableRows: [
        {
          timestamp_helsinki: '2026-05-01T00:00:00+03:00',
          fcr_n_price_eur_mw: null,
          spot_price_fi_eur_mwh: 48,
        },
        {
          timestamp_helsinki: '2026-05-01T01:00:00+03:00',
          fcr_n_price_eur_mw: 10,
          spot_price_fi_eur_mwh: 50,
        },
        {
          timestamp_helsinki: '2026-05-01T02:00:00+03:00',
          fcr_n_price_eur_mw: 20,
          spot_price_fi_eur_mwh: 55,
        },
        {
          timestamp_helsinki: '2026-05-01T03:00:00+03:00',
          fcr_n_price_eur_mw: 30,
          spot_price_fi_eur_mwh: 70,
        },
      ],
    }),
    {
      latestValue: 30,
      highValue: 30,
      lowValue: 10,
      meanValue: 20,
      spreadVsSpotLatest: -40,
      volatilityBand: 'high',
    },
  );

  assert.deepEqual(
    buildFinlandPrimaryPriceSummary({
      primaryFieldKey: 'fcr_n_price_eur_mw',
      tableRows: [{ fcr_n_price_eur_mw: null, spot_price_fi_eur_mwh: null }],
    }),
    {
      latestValue: null,
      highValue: null,
      lowValue: null,
      meanValue: null,
      spreadVsSpotLatest: null,
      volatilityBand: 'no_data',
    },
  );
});

test('buildFinlandPrimaryPriceSummary aligns latest spread to the latest valid primary row', () => {
  assert.deepEqual(
    buildFinlandPrimaryPriceSummary({
      primaryFieldKey: 'fcr_n_price_eur_mw',
      tableRows: [
        {
          timestamp_helsinki: '2026-05-01T01:00:00+03:00',
          fcr_n_price_eur_mw: 12,
          spot_price_fi_eur_mwh: 50,
        },
        {
          timestamp_helsinki: '2026-05-01T02:00:00+03:00',
          fcr_n_price_eur_mw: 25,
          spot_price_fi_eur_mwh: null,
        },
        {
          timestamp_helsinki: '2026-05-01T03:00:00+03:00',
          fcr_n_price_eur_mw: null,
          spot_price_fi_eur_mwh: 80,
        },
      ],
    }),
    {
      latestValue: 25,
      highValue: 25,
      lowValue: 12,
      meanValue: 18.5,
      spreadVsSpotLatest: null,
      volatilityBand: 'medium',
    },
  );
});

test('buildFinlandPrimaryPriceOptions keeps reserve price choices domain-aware per board view', () => {
  const fieldCatalogItems = [
    { field_key: 'fcr_n_price_eur_mw', label: 'FCR-N Capacity Price', unit: 'EUR/MW', category: 'capacity' },
    { field_key: 'afrr_cap_up_eur_mw', label: 'aFRR Capacity Up Price', unit: 'EUR/MW', category: 'capacity' },
    { field_key: 'afrr_act_up_eur_mwh', label: 'aFRR Activation Up Price', unit: 'EUR/MWh', category: 'activation' },
    { field_key: 'spot_price_fi_eur_mwh', label: 'Finland Spot Price', unit: 'EUR/MWh', category: 'spot' },
    { field_key: 'fcr_n_volume_mw', label: 'FCR-N Volume', unit: 'MW', category: 'capacity' },
  ];

  assert.deepEqual(
    buildFinlandPrimaryPriceOptions(fieldCatalogItems, { boardView: 'capacity_hourly' }).map((item) => item.field_key),
    ['fcr_n_price_eur_mw', 'afrr_cap_up_eur_mw'],
  );
  assert.deepEqual(
    buildFinlandPrimaryPriceOptions(fieldCatalogItems, { boardView: 'activation_15m' }).map((item) => item.field_key),
    ['afrr_act_up_eur_mwh'],
  );
  assert.deepEqual(
    buildFinlandPrimaryPriceOptions(fieldCatalogItems, { boardView: 'field_dictionary' }).map((item) => item.field_key),
    ['fcr_n_price_eur_mw', 'afrr_act_up_eur_mwh', 'afrr_cap_up_eur_mw'],
  );
});

test('buildFinlandComparisonRailRequest maps reserve prices onto volume support fields and spot context', () => {
  assert.deepEqual(
    buildFinlandComparisonRailRequest({
      primaryFieldKey: 'fcr_n_price_eur_mw',
      granularity: '1h',
    }),
    {
      fields: ['fcr_n_price_eur_mw', 'fcr_n_volume_mw', 'spot_price_fi_eur_mwh'],
      mode: 'compare',
      granularity: '1h',
      limitPoints: 240,
    },
  );

  assert.deepEqual(
    buildFinlandComparisonRailRequest({
      primaryFieldKey: 'afrr_cap_up_eur_mw',
      granularity: 'day',
      limitPoints: 96,
    }),
    {
      fields: ['afrr_cap_up_eur_mw', 'afrr_cap_up_volume_mw', 'spot_price_fi_eur_mwh'],
      mode: 'compare',
      granularity: 'day',
      limitPoints: 96,
    },
  );

  assert.deepEqual(
    buildFinlandComparisonRailRequest({
      primaryFieldKey: 'unknown_price_field',
      granularity: '1h',
      limitPoints: 48,
    }),
    {
      fields: ['unknown_price_field', 'spot_price_fi_eur_mwh'],
      mode: 'compare',
      granularity: '1h',
      limitPoints: 48,
    },
  );
});

test('buildFinlandBoardFieldCatalogUrl and buildFinlandBoardReadinessUrl target board endpoints', () => {
  assert.equal(
    buildFinlandBoardFieldCatalogUrl('http://127.0.0.1:8085/api'),
    'http://127.0.0.1:8085/api/finland/board/field-catalog',
  );
  assert.equal(
    buildFinlandBoardReadinessUrl('http://127.0.0.1:8085/api'),
    'http://127.0.0.1:8085/api/finland/board/readiness',
  );
});

test('Finland board helpers preserve backend overview cards and tabular payload shape', () => {
  const overviewCards = [
    { field_key: 'fcr_n_price_eur_mw', label: 'FCR-N Capacity Price', value: 12.5 },
    { field_key: 'join_completeness', label: 'Join Completeness And Freshness', value: 100.0 },
  ];
  const tablePayload = {
    columns: [
      { field_key: 'timestamp_helsinki', label: 'Time (Europe/Helsinki)', source_type: 'derived' },
      { field_key: 'spot_price_fi_eur_mwh', label: 'Finland Spot Price', unit: 'EUR/MWh', source_type: 'external_join' },
    ],
    rows: [
      { timestamp_helsinki: '2026-04-01T03:00:00+03:00', spot_price_fi_eur_mwh: 75.0 },
    ],
  };

  assert.deepEqual(getFinlandBoardOverviewCards({ cards: overviewCards }), overviewCards);
  assert.deepEqual(getFinlandBoardOverviewCards({ cards: null }), []);
  assert.deepEqual(getFinlandBoardTableColumns(tablePayload), tablePayload.columns);
  assert.deepEqual(getFinlandBoardTableRows(tablePayload), tablePayload.rows);
});

test('Finland board helpers derive dictionary jumps, selected field details, and chart requests from real contracts', () => {
  const fieldCatalogItems = [
    {
      field_key: 'spot_price_fi_eur_mwh',
      label: 'Finland Spot Price',
      unit: 'EUR/MWh',
      granularity: '1h',
      source_name: 'Nord Pool',
      source_dataset_id: 'nordpool_day_ahead_fi',
      source_type: 'external_join',
      category: 'spot',
      methodology_note: 'Joined day-ahead price series.',
    },
    {
      field_key: 'imbalance_price_eur_mwh',
      label: 'Imbalance Settlement Price',
      unit: 'EUR/MWh',
      granularity: '15m',
      source_name: 'Fingrid',
      source_dataset_id: '319',
      source_type: 'live',
      category: 'balancing',
      methodology_note: 'Settlement reference price.',
    },
  ];
  const tablePayload = {
    granularity: '1h',
    columns: [
      {
        field_key: 'timestamp_helsinki',
        label: 'Time (Europe/Helsinki)',
        source_name: 'Derived',
        source_type: 'derived',
        category: 'time',
        granularity: 'display',
      },
      {
        field_key: 'spot_price_fi_eur_mwh',
        label: 'Finland Spot Price',
        unit: 'EUR/MWh',
        source_name: 'Nord Pool',
        source_type: 'external_join',
        category: 'spot',
        granularity: '1h',
      },
    ],
    rows: [
      { timestamp_helsinki: '2026-04-01T03:00:00+03:00', spot_price_fi_eur_mwh: 75.0 },
      { timestamp_helsinki: '2026-04-01T04:00:00+03:00', spot_price_fi_eur_mwh: 82.0 },
    ],
  };

  assert.deepEqual(buildFinlandBoardDictionaryRows(fieldCatalogItems), [
    {
      ...fieldCatalogItems[0],
      preferredView: 'capacity_hourly',
    },
    {
      ...fieldCatalogItems[1],
      preferredView: 'activation_15m',
    },
  ]);

  assert.deepEqual(
    buildFinlandBoardSelectedFields({
      selectedFieldIds: ['spot_price_fi_eur_mwh', 'imbalance_price_eur_mwh'],
      tablePayload,
      fieldCatalogItems,
    }),
    [
      {
        field_key: 'spot_price_fi_eur_mwh',
        id: 'spot_price_fi_eur_mwh',
        label: 'Finland Spot Price',
        unit: 'EUR/MWh',
        source_name: 'Nord Pool',
        source_dataset_id: 'nordpool_day_ahead_fi',
        source_type: 'external_join',
        category: 'spot',
        granularity: '1h',
        methodology_note: 'Joined day-ahead price series.',
        latestValue: 82.0,
      },
      {
        field_key: 'imbalance_price_eur_mwh',
        id: 'imbalance_price_eur_mwh',
        label: 'Imbalance Settlement Price',
        unit: 'EUR/MWh',
        source_name: 'Fingrid',
        source_dataset_id: '319',
        source_type: 'live',
        category: 'balancing',
        granularity: '15m',
        methodology_note: 'Settlement reference price.',
        latestValue: null,
      },
    ],
  );

  assert.deepEqual(
    buildFinlandBoardChartRequest({
      selectedFields: [{ field_key: 'spot_price_fi_eur_mwh', granularity: '1h' }],
      viewGranularity: '1h',
      limitPoints: 240,
    }),
    {
      fields: ['spot_price_fi_eur_mwh'],
      mode: 'single',
      granularity: '1h',
      limitPoints: 240,
    },
  );
  assert.deepEqual(
    buildFinlandBoardChartRequest({
      selectedFields: [
        { field_key: 'spot_price_fi_eur_mwh', granularity: '1h' },
        { field_key: 'imbalance_price_eur_mwh', granularity: '15m' },
      ],
      viewGranularity: 'day',
      limitPoints: 240,
    }),
    {
      fields: ['spot_price_fi_eur_mwh', 'imbalance_price_eur_mwh'],
      mode: 'compare',
      granularity: 'day',
      limitPoints: 240,
    },
  );
  assert.equal(buildFinlandBoardChartRequest({ selectedFields: [], viewGranularity: '1h' }), null);
});

test('main.jsx mounts a real FinlandPage import for the finland root page', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../main.jsx'), 'utf8');

  // 2026-08-20：main.jsx 已改为 React.lazy 按需加载页面
  assert.match(source, /const FinlandPage = lazy\(\(\) => import\('\.\/pages\/FinlandPage\.jsx'\)\)/);
  assert.match(source, /rootPage === 'finland'/);
  assert.match(source, /<FinlandPage \/>/);
  assert.doesNotMatch(source, /const FinlandPage = App/);
});

test('frontend pages use shared api base resolution instead of hard-coded dev origins', () => {
  const finlandSource = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');
  const fingridSource = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  const portalSource = fs.readFileSync(path.resolve(__dirname, '../pages/DeveloperPortalPage.jsx'), 'utf8');
  // 2026-08-20：App.jsx 已移除；市场主页的 api base 收口由 MarketPage 承接
  const marketSource = fs.readFileSync(path.resolve(__dirname, '../pages/MarketPage.jsx'), 'utf8');
  const apiBaseSource = fs.readFileSync(path.resolve(__dirname, './apiBase.js'), 'utf8');

  assert.match(finlandSource, /getApiBase/);
  assert.match(fingridSource, /getApiBase/);
  assert.match(portalSource, /getApiBase/);
  assert.match(marketSource, /apiUrl|getApiBase/);
  assert.match(apiBaseSource, /return '\/api'/);
});

test('FinlandPage uses board overview and readiness helpers with workspace shell components', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /fetchJson/);
  assert.match(source, /buildFinlandBoardOverviewUrl/);
  assert.match(source, /buildFinlandBoardReadinessUrl/);
  assert.match(source, /className="mx-auto grid grid-cols-1 max-w-7xl gap-6"/);
  assert.match(source, /PageWorkspaceNav/);
  assert.match(source, /FinlandBoardHeader/);
  assert.match(source, /FinlandOverviewCards/);
  assert.match(source, /FinlandWorkbenchTabs/);
  assert.match(source, /FinlandDataTable/);
  assert.match(source, /FinlandPrimaryPriceWorkbench/);
  assert.match(source, /Promise\.all\(\s*\[/);
  assert.match(source, /headerMetrics=/);
});

test('FinlandPage supports daily segmented modes and real board payload state', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /const \[dailyMode,\s*setDailyMode\] = useState\('daily_capacity'\)/);
  assert.match(source, /daily_activation/);
  assert.match(source, /buildFinlandBoardTableUrl/);
  assert.match(source, /buildFinlandBoardFieldCatalogUrl/);
  assert.match(source, /const \[tablePayload,\s*setTablePayload\] = useState\(null\)/);
  assert.match(source, /const \[fieldCatalogPayload,\s*setFieldCatalogPayload\] = useState\(null\)/);
  assert.match(source, /activeTab === 'daily' \? dailyMode : activeTab/);
  assert.match(source, /fetchJson\(buildFinlandBoardTableUrl\(API_BASE,\s*\{[\s\S]*view:\s*activeBoardView/);
  assert.match(source, /fetchJson\(buildFinlandBoardFieldCatalogUrl\(API_BASE\)\)/);
});

test('FinlandPage wires dictionary jumps back into primary tabs and field selection', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /const handleDictionaryJump = \(fieldKey,\s*preferredView\) =>/);
  assert.match(source, /normalizeFinlandDictionaryJumpTarget/);
  assert.match(source, /const nextActiveTab = normalizeFinlandDictionaryJumpTarget\(preferredView\)/);
  assert.match(source, /setActiveTab\(nextActiveTab\)/);
  assert.match(source, /setSelectedFieldIds\(\[fieldKey\]\)/);
  assert.match(source, /onDictionaryJump=\{handleDictionaryJump\}/);
  assert.doesNotMatch(source, /setActiveTab\(preferredView/);
});

test('FinlandPage promotes a dedicated primary field state into the workbench shell', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /const \[primaryFieldKey,\s*setPrimaryFieldKey\] = useState\(\(\) => getDefaultFinlandPrimaryPriceField\(\)\)/);
  assert.match(source, /const primaryPriceOptions = useMemo\(/);
  assert.match(source, /const primaryPriceSummary = useMemo\(/);
  assert.match(source, /const mainChartRequest = useMemo\(/);
  assert.match(source, /const comparisonChartRequest = useMemo\(/);
  assert.match(source, /const primarySelectedField = useMemo\(/);
  assert.match(source, /const \[selectedFieldIds,\s*setSelectedFieldIds\] = useState\(\[\]\)/);
  assert.match(source, /const overviewCards = useMemo\(/);
  assert.match(source, /const tableColumns = useMemo\(/);
  assert.match(source, /const tableRows = useMemo\(/);
  assert.match(source, /FinlandSeriesGallery/);
  assert.match(source, /<FinlandOverviewCards cards=\{overviewCards\} copy=\{copy\} \/>/);
  assert.match(source, /<FinlandSeriesGallery[\s\S]*columns=\{tableColumns\}[\s\S]*rows=\{tableRows\}/);
  assert.match(source, /<FinlandDataTable[\s\S]*columns=\{tableColumns\}[\s\S]*rows=\{tableRows\}[\s\S]*selectedFieldIds=\{selectedFieldIds\}[\s\S]*onSelectField=\{setSelectedFieldIds\}/);
  assert.match(source, /<FinlandPrimaryPriceWorkbench[\s\S]*selectedFieldKey=\{effectivePrimaryFieldKey\}[\s\S]*onSelectField=\{setPrimaryFieldKey\}/);
  assert.match(source, /mainChartRequest=\{mainChartRequest\}/);
  assert.match(source, /comparisonChartRequest=\{comparisonChartRequest\}/);
  assert.match(source, /selectedField=\{primarySelectedField\}/);
  assert.doesNotMatch(source, /buildOverviewCards/);
  assert.doesNotMatch(source, /buildFieldDescriptors/);
});

test('Finland workbench components rely on page-owned copy and real board contracts', () => {
  const tableSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandDataTable.jsx'), 'utf8');
  const chartSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandLinkedChart.jsx'), 'utf8');
  const detailSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandFieldDetailPanel.jsx'), 'utf8');

  assert.match(tableSource, /columns = \[\]/);
  assert.match(tableSource, /rows = \[\]/);
  assert.match(tableSource, /columns\.map/);
  assert.match(tableSource, /rows\.map/);
  assert.match(tableSource, /onSelectField/);
  assert.match(tableSource, /selectedFieldIds/);
  assert.match(tableSource, /sticky top-0/);
  assert.match(tableSource, /sticky left-0/);
  assert.match(tableSource, /column\.field_key/);
  assert.match(tableSource, /row\?\.\[column\.field_key\]/);
  assert.doesNotMatch(tableSource, /DEFAULT_COPY/);
  assert.match(chartSource, /fetchJson/);
  assert.match(chartSource, /buildFinlandBoardChartUrl/);
  assert.match(chartSource, /chartRequest/);
  assert.match(chartSource, /payload\?\.series/);
  assert.match(chartSource, /selectedFields/);
  assert.doesNotMatch(chartSource, /DEFAULT_COPY/);
  assert.match(detailSource, /selectedFields/);
  assert.match(detailSource, /selectedFields\.map/);
  assert.match(detailSource, /field\.methodology_note/);
  assert.match(detailSource, /field\.source_dataset_id/);
  assert.doesNotMatch(detailSource, /DEFAULT_COPY/);
});

test('FinlandWorkbenchTabs exposes a daily segmented control and dictionary jump surface', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandWorkbenchTabs.jsx'), 'utf8');

  assert.match(source, /dailyModes/);
  assert.match(source, /daily_capacity/);
  assert.match(source, /daily_activation/);
  assert.match(source, /onDailyModeChange/);
  assert.match(source, /onDictionaryJump/);
});

test('Finland translations include table, chart, and detail shell copy owned by the page', () => {
  assert.equal(translations.en.finlandBoard.tableShell.columns.field, 'Field');
  assert.equal(translations.en.finlandBoard.tableShell.columns.unit, 'Unit');
  assert.equal(translations.en.finlandBoard.linkedChart.emptyTitle, 'No fields selected');
  assert.equal(translations.en.finlandBoard.linkedChart.loading, 'Loading linked chart...');
  assert.equal(translations.en.finlandBoard.fieldDetailPanel.labels.source, 'Source');
  assert.equal(translations.en.finlandBoard.fieldDetailPanel.labels.methodology, 'Methodology');
  assert.equal(translations.en.finlandBoard.task7.dailyModesLabel, 'Daily Split');
  assert.equal(translations.en.finlandBoard.task7.tabs.capacity.label, 'Capacity 1H');
  assert.equal(translations.en.finlandBoard.task7.dictionary.jumpLabel, 'Jump');
  assert.equal(translations.en.finlandBoard.task7.tableDescriptionPrefix, 'Current view:');
  assert.ok(translations.zh.finlandBoard.task7);
});

test('Finland translations include primary price workbench copy in both languages', () => {
  assert.equal(translations.en.finlandBoard.priceWorkbench.eyebrow, 'Primary Price Workbench');
  assert.equal(translations.en.finlandBoard.priceWorkbench.selector.label, 'Primary series');
  assert.equal(translations.en.finlandBoard.priceWorkbench.summary.latestLabel, 'Latest');
  assert.equal(translations.en.finlandBoard.priceWorkbench.comparison.title, 'Comparison Rail');
  assert.equal(translations.en.finlandBoard.priceWorkbench.summary.volatilityValues.high, 'High');
  assert.equal(translations.en.finlandBoard.priceWorkbench.summary.volatilityValues.no_data, 'No Data');

  assert.equal(translations.zh.finlandBoard.priceWorkbench.eyebrow, '主价格工作台');
  assert.equal(translations.zh.finlandBoard.priceWorkbench.selector.label, '主序列');
  assert.equal(translations.zh.finlandBoard.priceWorkbench.summary.latestLabel, '最新');
  assert.equal(translations.zh.finlandBoard.priceWorkbench.summary.volatilityValues.medium, '中');
  assert.equal(translations.zh.finlandBoard.priceWorkbench.comparison.title, '对比轨道');
});

test('FinlandPage reads Task 7 labels from translation-backed copy instead of inline literals', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /copy\.task7/);
  assert.doesNotMatch(source, /Daily Split/);
  assert.doesNotMatch(source, /Field Dictionary/);
  assert.doesNotMatch(source, /Current view:/);
  assert.doesNotMatch(source, /No field catalog rows available\./);
});

test('FinlandPage references the primary price workbench and translation-backed workbench copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /FinlandPrimaryPriceWorkbench/);
  assert.match(source, /priceWorkbench/);
  assert.match(source, /buildFinlandPrimaryPriceOptions/);
  assert.match(source, /buildFinlandPrimaryPriceSummary/);
  assert.match(source, /buildFinlandComparisonRailRequest/);
  assert.match(source, /selectedFieldKey=\{effectivePrimaryFieldKey\}/);
  assert.match(source, /summary=\{primaryPriceSummary\}/);
  assert.match(source, /comparisonItems=\{comparisonItems\}/);
});

test('FinlandPage renders the primary workbench before the verification table', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');
  const galleryIndex = source.indexOf('<FinlandSeriesGallery');
  const workbenchIndex = source.indexOf('<FinlandPrimaryPriceWorkbench');
  const tableIndex = source.indexOf('<FinlandDataTable');

  assert.equal(galleryIndex > -1, true);
  assert.equal(workbenchIndex > -1, true);
  assert.equal(tableIndex > -1, true);
  assert.equal(galleryIndex < tableIndex, true);
  assert.equal(workbenchIndex < tableIndex, true);
});

test('Finland primary price workbench scaffolds exist as focused components', () => {
  const selectorSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandPrimaryPriceSelector.jsx'), 'utf8');
  const summarySource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandPriceSummaryStrip.jsx'), 'utf8');
  const railSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandComparisonRail.jsx'), 'utf8');
  const workbenchSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandPrimaryPriceWorkbench.jsx'), 'utf8');

  assert.match(selectorSource, /copy/);
  assert.match(selectorSource, /option\.field_key/);
  assert.match(selectorSource, /onChange\?\.\(option\.field_key\)/);
  assert.match(summarySource, /copy/);
  assert.match(summarySource, /volatilityBand/);
  assert.match(summarySource, /volatilityValues/);
  assert.match(railSource, /copy/);
  assert.match(railSource, /buildFinlandBoardChartUrl/);
  assert.match(railSource, /useMeasuredElement/);
  assert.match(railSource, /LineChart width=\{chartFrameSize\.width\} height=\{chartFrameSize\.height\}/);
  assert.match(railSource, /seriesCards/);
  assert.match(railSource, /item\.description \|\| item\.unit \|\| item\.field_key/);
  assert.match(workbenchSource, /FinlandPrimaryPriceSelector/);
  assert.match(workbenchSource, /FinlandPriceSummaryStrip/);
  assert.match(workbenchSource, /FinlandComparisonRail/);
  assert.match(workbenchSource, /FinlandLinkedChart/);
  assert.match(workbenchSource, /FinlandFieldDetailPanel/);
  assert.match(workbenchSource, /copy\.selector/);
  assert.match(workbenchSource, /copy\.summary/);
  assert.match(workbenchSource, /copy\.comparison/);
});

test('finland primary workbench keeps the linked chart as the visual anchor', () => {
  const workbenchSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandPrimaryPriceWorkbench.jsx'), 'utf8');
  const chartIndex = workbenchSource.indexOf('<FinlandLinkedChart');
  const selectorIndex = workbenchSource.indexOf('<FinlandPrimaryPriceSelector');

  assert.equal(chartIndex > -1, true);
  assert.equal(selectorIndex > -1, true);
  assert.equal(chartIndex < selectorIndex, true);
  assert.match(workbenchSource, /xl:grid-cols-\[minmax\(0,1\.85fr\)_minmax\(18rem,0\.95fr\)\]/);
});

test('Finland board components expose overview and workbench shell structure with page-owned header metrics', () => {
  const headerSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandBoardHeader.jsx'), 'utf8');
  const cardsSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandOverviewCards.jsx'), 'utf8');
  const tabsSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandWorkbenchTabs.jsx'), 'utf8');

  assert.match(headerSource, /copy\./);
  assert.match(headerSource, /headerMetrics/);
  assert.doesNotMatch(headerSource, /overviewPayload,/);
  assert.doesNotMatch(headerSource, /readinessPayload,/);
  assert.doesNotMatch(headerSource, /Object\.keys/);
  assert.match(cardsSource, /cards\.map/);
  assert.match(tabsSource, /tabs\.map/);
  assert.match(tabsSource, /aria-selected/);
  assert.match(tabsSource, /panelCopy\./);
});

test('finland board theme exposes semantic surface aliases for workspace pages', () => {
  const themeSource = fs.readFileSync(path.resolve(__dirname, '../index.css'), 'utf8');

  assert.match(themeSource, /--color-background:/);
  assert.match(themeSource, /--color-panel:/);
  assert.match(themeSource, /--color-surface:/);
  assert.match(themeSource, /--color-surface-hover:/);
});

test('finland board typography avoids the default inter-playfair pairing', () => {
  const themeSource = fs.readFileSync(path.resolve(__dirname, '../index.css'), 'utf8');

  assert.match(themeSource, /Archivo/);
  assert.match(themeSource, /Source Serif 4/);
  assert.doesNotMatch(themeSource, /Inter/);
  assert.doesNotMatch(themeSource, /Playfair Display/);
});

test('finland board controls expose focus-visible feedback and touch-safe sizes', () => {
  const navSource = fs.readFileSync(path.resolve(__dirname, '../components/PageWorkspaceNav.jsx'), 'utf8');
  const tabsSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandWorkbenchTabs.jsx'), 'utf8');
  const selectorSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandPrimaryPriceSelector.jsx'), 'utf8');
  const tableSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandDataTable.jsx'), 'utf8');

  assert.match(navSource, /min-h-\[44px\]/);
  assert.match(navSource, /focus-visible:/);
  assert.match(tabsSource, /min-h-\[44px\]/);
  assert.match(tabsSource, /focus-visible:/);
  assert.match(selectorSource, /min-h-\[44px\]/);
  assert.match(selectorSource, /focus-visible:/);
  assert.match(tableSource, /tabular-nums/);
});

test('finland chart-first gallery turns current board columns into visual cards', () => {
  const gallerySource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandSeriesGallery.jsx'), 'utf8');
  const translationsSource = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  assert.match(gallerySource, /isFinlandBoardSelectableColumn/);
  assert.match(gallerySource, /LineChart/);
  assert.match(gallerySource, /columns = \[\]/);
  assert.match(gallerySource, /rows = \[\]/);
  assert.match(gallerySource, /selectedFieldIds/);
  assert.match(gallerySource, /onPromoteField/);
  assert.match(gallerySource, /tabular-nums/);
  assert.match(translationsSource, /chartGallery/);
});

test('finland board hero and workbench avoid hard-coded dark cinematic gradients', () => {
  const headerSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandBoardHeader.jsx'), 'utf8');
  const workbenchSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandPrimaryPriceWorkbench.jsx'), 'utf8');
  const cardsSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandOverviewCards.jsx'), 'utf8');
  const comparisonSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandComparisonRail.jsx'), 'utf8');

  assert.doesNotMatch(headerSource, /linear-gradient\(135deg,rgba\(9,14,28,0\.96\),rgba\(15,32,47,0\.92\)_42%,rgba\(110,43,22,0\.78\)\)/);
  assert.doesNotMatch(headerSource, /radial-gradient\(circle_at_top_right,rgba\(251,191,36,0\.24\),transparent_30%\)/);
  assert.doesNotMatch(workbenchSource, /linear-gradient\(180deg,rgba\(9,15,25,0\.96\),rgba\(11,20,29,0\.94\)\)/);
  assert.doesNotMatch(cardsSource, /linear-gradient\(180deg,rgba\(11,17,28,0\.98\),rgba\(17,27,44,0\.86\)\)/);
  assert.doesNotMatch(comparisonSource, /rgba\(11,19,31,0\.82\)|rgba\(11,19,31,0\.78\)/);
});

test('app shell and translations include Finland navigation entry and localized board copy', () => {
  // 2026-08-20：Finland 导航入口从 App.jsx 迁移到 SidebarNavigation
  const sidebarSource = fs.readFileSync(path.resolve(__dirname, '../components/SidebarNavigation.jsx'), 'utf8');
  const translationsSource = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  assert.match(sidebarSource, /path: '\/finland'/);
  assert.match(translationsSource, /translations\.zh\.nav = \{/);
  assert.match(translationsSource, /finland:/);
  assert.match(translationsSource, /translations\.zh\.finlandBoard = \{/);
  assert.match(translationsSource, /translations\.en\.finlandBoard = \{/);
});

test('Finland translations keep readable zh copy and correct language toggles', () => {
  assert.equal(translations.zh.nav.finland, '芬兰市场看板');
  assert.equal(translations.en.nav.finland, 'Finland Board');
  assert.equal(translations.zh.finlandBoard.title, '芬兰市场看板');
  assert.equal(
    translations.zh.finlandBoard.subtitle,
    '芬兰电力市场实时看板：储备价格、就绪状态与联动分析。',
  );
  assert.equal(translations.zh.finlandBoard.toggleLanguage, 'EN / 中');
  assert.equal(translations.en.finlandBoard.toggleLanguage, '中 / EN');
  assert.equal(translations.zh.finlandBoard.status.loading, '加载中');
  assert.equal(translations.zh.finlandBoard.errorTitle, 'Finland board 接口加载失败');
});
