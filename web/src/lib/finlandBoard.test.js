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
  buildFinlandBoardDictionaryRows,
  buildFinlandBoardFieldCatalogUrl,
  buildFinlandBoardOverviewUrl,
  buildFinlandBoardReadinessUrl,
  buildFinlandBoardSelectedFields,
  buildFinlandBoardTableUrl,
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
    }),
    'http://127.0.0.1:8085/api/finland/board/table?view=capacity_hourly&start=2026-05-01T00%3A00%3A00Z&end=2026-05-02T00%3A00%3A00Z&tz=Europe%2FHelsinki',
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
    }),
    'http://127.0.0.1:8085/api/finland/board/chart?fields=fcrn_price&fields=spot_price&mode=compare&start=2026-05-01T00%3A00%3A00Z&end=2026-05-02T00%3A00%3A00Z&granularity=4h',
  );
});

test('buildFinlandBoardChartUrl omits a trailing query marker when all params are missing', () => {
  assert.equal(
    buildFinlandBoardChartUrl('http://127.0.0.1:8085/api'),
    'http://127.0.0.1:8085/api/finland/board/chart',
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
    }),
    {
      fields: ['spot_price_fi_eur_mwh'],
      mode: 'single',
      granularity: '1h',
    },
  );
  assert.deepEqual(
    buildFinlandBoardChartRequest({
      selectedFields: [
        { field_key: 'spot_price_fi_eur_mwh', granularity: '1h' },
        { field_key: 'imbalance_price_eur_mwh', granularity: '15m' },
      ],
      viewGranularity: 'day',
    }),
    {
      fields: ['spot_price_fi_eur_mwh', 'imbalance_price_eur_mwh'],
      mode: 'compare',
      granularity: 'day',
    },
  );
  assert.equal(buildFinlandBoardChartRequest({ selectedFields: [], viewGranularity: '1h' }), null);
});

test('main.jsx mounts a real FinlandPage import for the finland root page', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../main.jsx'), 'utf8');

  assert.match(source, /import FinlandPage from '\.\/pages\/FinlandPage\.jsx'/);
  assert.match(source, /rootPage === 'finland'/);
  assert.match(source, /<FinlandPage \/>/);
  assert.doesNotMatch(source, /const FinlandPage = App/);
});

test('FinlandPage uses board overview and readiness helpers with workspace shell components', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /fetchJson/);
  assert.match(source, /buildFinlandBoardOverviewUrl/);
  assert.match(source, /buildFinlandBoardReadinessUrl/);
  assert.match(source, /PageWorkspaceNav/);
  assert.match(source, /FinlandBoardHeader/);
  assert.match(source, /FinlandOverviewCards/);
  assert.match(source, /FinlandWorkbenchTabs/);
  assert.match(source, /FinlandDataTable/);
  assert.match(source, /FinlandLinkedChart/);
  assert.match(source, /FinlandFieldDetailPanel/);
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

test('FinlandPage tracks selected fields and wires real board payloads into the linked analysis shell', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /const \[selectedFieldIds,\s*setSelectedFieldIds\] = useState\(\[\]\)/);
  assert.match(source, /const selectedFields = useMemo\(/);
  assert.match(source, /const chartRequest = useMemo\(/);
  assert.match(source, /const overviewCards = useMemo\(/);
  assert.match(source, /const tableColumns = useMemo\(/);
  assert.match(source, /const tableRows = useMemo\(/);
  assert.match(source, /const selectedFields = useMemo\(/);
  assert.match(source, /<FinlandOverviewCards cards=\{overviewCards\} copy=\{copy\} \/>/);
  assert.match(source, /<FinlandDataTable[\s\S]*columns=\{tableColumns\}[\s\S]*rows=\{tableRows\}[\s\S]*selectedFieldIds=\{selectedFieldIds\}[\s\S]*onSelectField=\{setSelectedFieldIds\}/);
  assert.match(source, /<FinlandLinkedChart[\s\S]*chartRequest=\{chartRequest\}[\s\S]*selectedFields=\{selectedFields\}[\s\S]*copy=\{copy\.linkedChart\}/);
  assert.match(source, /<FinlandFieldDetailPanel[\s\S]*selectedFields=\{selectedFields\}[\s\S]*copy=\{\{[\s\S]*copy\.fieldDetailPanel/);
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

test('FinlandPage reads Task 7 labels from translation-backed copy instead of inline literals', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /copy\.task7/);
  assert.doesNotMatch(source, /Daily Split/);
  assert.doesNotMatch(source, /Field Dictionary/);
  assert.doesNotMatch(source, /Current view:/);
  assert.doesNotMatch(source, /No field catalog rows available\./);
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

test('app shell and translations include Finland navigation entry and localized board copy', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const translationsSource = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  assert.match(appSource, /href="\/finland"/);
  assert.match(appSource, /t\.nav\.finland/);
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
    '读取 overview 与 readiness 接口，先搭建工作台外壳，不进入表格联动和分析链路。',
  );
  assert.equal(translations.zh.finlandBoard.toggleLanguage, 'EN / 中');
  assert.equal(translations.en.finlandBoard.toggleLanguage, '中 / EN');
  assert.equal(translations.zh.finlandBoard.status.loading, '加载中');
  assert.equal(translations.zh.finlandBoard.errorTitle, 'Finland board 接口加载失败');
});
