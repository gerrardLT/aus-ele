import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('FingridSeriesChart tooltip references bucket statistics fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');
  for (const token of ['avg_value', 'peak_value', 'trough_value', 'sample_count', 'bucket_start', 'bucket_end']) {
    assert.match(source, new RegExp(token));
  }
});

test('FingridSeriesChart renders a visible loading indicator without dimming the whole chart', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');
  for (const token of ['if \\(loading\\)', "copy\\?\\.loadingChart \\|\\| 'Loading chart\\.{3}'"]) {
    assert.match(source, new RegExp(token));
  }
  assert.doesNotMatch(source, /absolute right-3 top-3/);
});

test('FingridSeriesChart renders the full series with a monotone stroke', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');
  for (const token of ['LineChart data={series}', 'type="monotone"']) {
    assert.match(source, new RegExp(token));
  }
  assert.doesNotMatch(source, /downsampleSeriesForChart/);
});

test('FingridSeriesChart uses the default Y axis domain', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/fingrid/FingridSeriesChart.jsx'), 'utf8');
  assert.match(source, /<YAxis \/>/);
  assert.doesNotMatch(source, /domain=\{/);
});
