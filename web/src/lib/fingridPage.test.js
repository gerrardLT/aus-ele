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

test('App exposes a navigation entry to the Fingrid page', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /\/fingrid/);
});
