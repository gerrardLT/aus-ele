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
  assert.equal(source.includes('selectedRegion'), false);
  assert.equal(source.includes('price-trend'), false);
});

test('FingridPage exposes raw 1h 2h 4h day week month aggregation options', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  for (const token of ['raw', '1h', '2h', '4h', 'day', 'week', 'month']) {
    assert.match(source, new RegExp(`'${token}'`));
  }
});

test('FingridPage exposes a custom date-range mode with date inputs', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridHeader.jsx'), 'utf8');
  assert.match(source, /'custom'/);
  assert.match(source, /type="date"/);
});

test('FingridPage wires language state and dynamic request limits', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /const \[lang, setLang\]/);
  assert.match(source, /buildFingridRequestLimit/);
});

test('FingridPage polls Fingrid status and refreshes datasets when sync metadata changes', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /AUTO_REFRESH_STATUS_INTERVAL_MS/);
  assert.match(source, /setInterval/);
  assert.match(source, /buildFingridStatusUrl/);
  assert.match(source, /refreshNonce/);
});

test('FingridPage loads Finland market model context instead of behaving like a single-dataset-only product', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /finlandMarketModel/);
  assert.match(source, /\/finland\/market-model/);
  assert.match(source, /Nord Pool/);
  assert.match(source, /ENTSO-E/);
});

test('FingridPage checks manual sync HTTP status before treating the request as successful', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /syncResponse/);
  assert.match(source, /!syncResponse\.ok/);
});

test('FingridPage treats backend running state as an active sync and handles 409 responses explicitly', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  assert.match(source, /statusPayload\?\.\s*status\?\.\s*sync_status === 'running'/);
  assert.match(source, /syncResponse\.status === 409/);
});

test('App exposes a navigation entry to the Fingrid page', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /\/fingrid/);
});

test('FingridPage and Fingrid UI copy avoid mojibake and centralize Finland market-model copy', () => {
  const pageSource = fs.readFileSync(path.resolve(__dirname, '../pages/FingridPage.jsx'), 'utf8');
  const uiSource = fs.readFileSync(path.resolve(__dirname, './fingridUi.js'), 'utf8');

  assert.match(pageSource, /const marketModelCopy = copy\.marketModel \|\| \{\};/);
  assert.match(pageSource, /marketModelCopy\.title/);
  assert.match(pageSource, /marketModelCopy\.subtitle/);
  assert.match(pageSource, /marketModelCopy\.description/);
  assert.match(pageSource, /marketModelCopy\.modelStatus/);
  assert.match(pageSource, /marketModelCopy\.liveDatasets/);
  assert.match(pageSource, /marketModelCopy\.liveSignals/);
  assert.match(pageSource, /marketModelCopy\.noSignals/);
  assert.match(pageSource, /marketModelCopy\.plannedNordPool/);
  assert.match(pageSource, /marketModelCopy\.plannedEntsoe/);
  assert.match(uiSource, /Fingrid \\u82ac\\u5170\\u7535\\u7f51/);

  for (const phrase of ['鑺叞', '褰撳墠', '妯″瀷', '鍦ㄧ嚎']) {
    assert.equal(pageSource.includes(phrase), false, `FingridPage should not contain "${phrase}"`);
    assert.equal(uiSource.includes(phrase), false, `fingridUi should not contain "${phrase}"`);
  }
});
