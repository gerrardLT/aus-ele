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
