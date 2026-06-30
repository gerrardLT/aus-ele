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
  assert.match(source, /className="mx-auto grid grid-cols-1 max-w-7xl gap-8"/);
  assert.equal(source.includes('selectedRegion'), false);
  assert.match(source, /FingridHourlyBoard/);
  assert.match(source, /FingridYearlyPlanBoard/);
});

test('PageSection supports hiding the section divider and header for chart-first hero areas', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/PageSection.jsx'), 'utf8');
  assert.match(source, /showHeader = true/);
  assert.match(source, /showDivider = true/);
  assert.match(source, /showDivider/);
  assert.match(source, /border-t border-\[var\(--color-border\)\] pt-8/);
  assert.match(source, /scroll-mt-24/);
  assert.match(source, /showHeader \? \(/);
});

test('FingridPage exposes raw 1h 2h 4h day week month aggregation options', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  assert.match(source, /aggregationOptions\.map/);
});

test('FingridPage exposes a custom date-range mode with date inputs', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  assert.match(source, /'custom'/);
  assert.match(source, /type="date"/);
});

test('FingridHeader groups actions and filters into stable responsive layout blocks', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  assert.match(source, /data-testid="fingrid-header-actions"/);
  assert.match(source, /data-testid="fingrid-header-filters"/);
  assert.match(source, /toolbarOnly = false/);
  assert.match(source, /if \(toolbarOnly\)/);
  assert.match(source, /useCompactLayout \? 'xl:grid-cols-1' : 'xl:grid-cols-\[minmax\(0,1fr\)_minmax\(360px,0\.95fr\)\]'/);
  assert.match(source, /useCompactLayout \? 'grid-cols-1 sm:grid-cols-2' : 'sm:grid-cols-2 xl:grid-cols-4'/);
  assert.match(source, /min-h-\[44px\]/);
  assert.match(source, /copy\.exportAllMarketsCsv/);
  assert.match(source, /compactLayout = false/);
  assert.match(source, /const useCompactLayout = compactLayout \|\| isYearlyPlanBoard;/);
  assert.equal(source.includes('flex max-w-4xl flex-wrap gap-2'), false);
});

test('FingridHeader treats the market switcher as a grouped dataset selector with context copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  assert.match(source, /aria-label=\{copy\.datasetSelectorLabel\}/);
  assert.match(source, /copy\.controlsTitle/);
  assert.match(source, /<optgroup/);
  assert.match(source, /copy\.datasetGroups/);
  assert.match(source, /copy\.datasetContextTitle/);
  assert.match(source, /copy\.yearlyDatasetNotice/);
  assert.match(source, /copy\.yearlyDatasetAutoWindowNotice/);
  assert.match(source, /copy\.hourlyDatasetNotice/);
});

test('FingridPage auto-adjusts yearly-plan datasets away from short windows and intraday aggregations', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /selectedDataset\.groupKey === 'yearly_plans'/);
  assert.match(source, /preset !== 'all' && preset !== '1y' && preset !== 'custom'/);
  assert.match(source, /setPreset\('1y'\)/);
  assert.match(source, /setAggregation\(supportedAggregations\.has\('month'\) \? 'month'/);
  assert.match(source, /selectedDataset\?\.groupKey === 'yearly_plans' \? \['1y', 'all', 'custom'\]/);
});

test('FingridPage splits hourly and yearly datasets into separate boards', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /import FingridHourlyBoard from '\.\.\/components\/fingrid\/FingridHourlyBoard';/);
  assert.match(source, /import FingridYearlyPlanBoard from '\.\.\/components\/fingrid\/FingridYearlyPlanBoard';/);
  assert.match(source, /selectedDataset\?\.groupKey === 'yearly_plans' \?/);
  assert.match(source, /<FingridYearlyPlanBoard/);
  assert.match(source, /<FingridHourlyBoard/);
  assert.match(source, /mode="hero"/);
  assert.match(source, /mode="details"/);
});

test('Fingrid all-markets export is positioned as workbook export rather than flat CSV', () => {
  const source = fs.readFileSync(path.resolve(__dirname, './fingridUi.js'), 'utf8');
  assert.match(source, /exportAllMarketsCsv/);
  assert.match(source, /Export All Markets Excel/);
});

test('FingridPage wires language state and dynamic request limits', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /const \[lang, setLang\]/);
  assert.match(source, /buildFingridRequestLimit/);
  assert.match(source, /buildFingridAllMarketsExportUrl/);
  assert.match(source, /import PageSection from '\.\.\/components\/PageSection';/);
  assert.match(source, /copy\.toggleLanguage/);
  assert.match(source, /copy\.toggleLanguageAriaLabel/);
  assert.match(source, /id="fingrid-workspace-shell"/);
  assert.match(source, /const toolbar = \(/);
  assert.match(source, /toolbarOnly/);
  assert.match(source, /mode="hero"/);
  assert.match(source, /mode="details"/);
  assert.match(source, /onClick=\{\(\) => setLang\(\(current\) => \(current === 'zh' \? 'en' : 'zh'\)\)\}/);
});

test('Fingrid yearly-plan board keeps the main chart ahead of overview cards', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridYearlyPlanBoard.jsx'), 'utf8');
  const chartIndex = source.indexOf('id="yearly-plan-series"');
  const overviewIndex = source.indexOf('id="yearly-plan-board"');

  assert.notEqual(chartIndex, -1);
  assert.notEqual(overviewIndex, -1);
  assert.ok(chartIndex < overviewIndex);
});

test('FingridPage polls Fingrid status and refreshes datasets when sync metadata changes', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /AUTO_REFRESH_STATUS_INTERVAL_MS/);
  assert.match(source, /setInterval/);
  assert.match(source, /buildFingridStatusUrl/);
  assert.match(source, /refreshNonce/);
});

test('FingridPage loads Finland market model context instead of behaving like a single-dataset-only product', () => {
  const pageSource = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  const hourlyBoardSource = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHourlyBoard.jsx'), 'utf8');
  const yearlyBoardSource = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridYearlyPlanBoard.jsx'), 'utf8');
  assert.match(pageSource, /marketModelCopy/);
  assert.match(pageSource, /controls=\{toolbar\}/);
  assert.match(hourlyBoardSource, /marketModelCopy\.noSignals/);
  assert.match(hourlyBoardSource, /controls = null/);
  assert.match(hourlyBoardSource, /mode = 'full'/);
  assert.match(hourlyBoardSource, /const showHero = mode === 'full' \|\| mode === 'hero';/);
  assert.match(hourlyBoardSource, /const showDetails = mode === 'full' \|\| mode === 'details';/);
  assert.match(hourlyBoardSource, /controls \? <div className="flex justify-end">\{controls\}<\/div> : null/);
  assert.match(hourlyBoardSource, /showHeader=\{false\}/);
  assert.match(hourlyBoardSource, /showDivider=\{false\}/);
  assert.match(yearlyBoardSource, /showHeader=\{false\}/);
  assert.match(yearlyBoardSource, /showDivider=\{false\}/);
  assert.match(hourlyBoardSource, /<FingridSummaryCards[\s\S]*compact/);
  assert.match(hourlyBoardSource, /FingridStatusPanel payload=\{statusPayload\} loading=\{loading\} error=\{error\} copy=\{copy\} lang=\{lang\}(?!\s*compact)/);
  const summaryIndex = hourlyBoardSource.indexOf('<FingridSummaryCards');
  const statusIndex = hourlyBoardSource.indexOf('<FingridStatusPanel');
  const chartIndex = hourlyBoardSource.indexOf('<FingridSeriesChart');
  assert.ok(summaryIndex !== -1 && statusIndex !== -1 && chartIndex !== -1);
  assert.ok(summaryIndex < chartIndex);
  assert.ok(chartIndex < statusIndex);
});

test('Fingrid status panel supports compact sync cards for chart-adjacent placement', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridStatusPanel.jsx'), 'utf8');
  assert.match(source, /compact = false/);
  assert.match(source, /if \(compact\)/);
  assert.match(source, /md:grid-cols-2 xl:grid-cols-3/);
});

test('FingridPage no longer exposes a manual Fingrid sync action', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.doesNotMatch(source, /buildFingridSyncUrl/);
  assert.doesNotMatch(source, /handleSync/);
});

test('FingridPage still polls backend sync status for passive refreshes', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /buildFingridStatusUrl/);
  assert.match(source, /refreshNonce/);
});

test('App exposes a navigation entry to the Fingrid page', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /\/fingrid/);
});

test('FingridPage and Fingrid UI copy avoid mojibake and centralize Finland market-model copy', () => {
  const pageSource = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  const hourlyBoardSource = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHourlyBoard.jsx'), 'utf8');
  const uiSource = fs.readFileSync(path.resolve(__dirname, './fingridUi.js'), 'utf8');

  assert.match(pageSource, /const marketModelCopy = copy\.marketModel \|\| \{\};/);
  assert.match(hourlyBoardSource, /marketModelCopy\.noSignals/);
  assert.match(uiSource, /Fingrid \\u82ac\\u5170\\u7535\\u7f51/);
  assert.match(uiSource, /Nord Pool/);
  assert.match(uiSource, /ENTSO-E/);

  for (const phrase of ['鑺叞', '褰撳墠', '妯″瀷', '鍦ㄧ嚎']) {
    assert.equal(pageSource.includes(phrase), false, `FingridPage should not contain "${phrase}"`);
    assert.equal(uiSource.includes(phrase), false, `fingridUi should not contain "${phrase}"`);
  }
});
