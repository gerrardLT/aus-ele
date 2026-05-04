import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildFinlandBoardChartUrl,
  buildFinlandBoardFieldCatalogUrl,
  buildFinlandBoardOverviewUrl,
  buildFinlandBoardReadinessUrl,
  buildFinlandBoardTableUrl,
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

test('FinlandPage tracks selected fields and wires them into the linked analysis shell', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FinlandPage.jsx'), 'utf8');

  assert.match(source, /const \[selectedFields,\s*setSelectedFields\] = useState\(\[\]\)/);
  assert.match(source, /<FinlandDataTable[\s\S]*onSelectField=\{setSelectedFields\}/);
  assert.match(source, /<FinlandLinkedChart[\s\S]*selectedFields=\{selectedFields\}/);
  assert.match(source, /<FinlandFieldDetailPanel[\s\S]*selectedFields=\{selectedFields\}/);
});

test('Finland workbench components expose selection and linked-shell contracts', () => {
  const tableSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandDataTable.jsx'), 'utf8');
  const chartSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandLinkedChart.jsx'), 'utf8');
  const detailSource = fs.readFileSync(path.resolve(__dirname, '../components/finland/FinlandFieldDetailPanel.jsx'), 'utf8');

  assert.match(tableSource, /onSelectField/);
  assert.match(tableSource, /selectedFields/);
  assert.match(tableSource, /sticky top-0/);
  assert.match(tableSource, /sticky left-0/);
  assert.match(chartSource, /selectedFields/);
  assert.match(chartSource, /selectedFields\.length/);
  assert.match(detailSource, /selectedFields/);
  assert.match(detailSource, /selectedFields\.map/);
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
