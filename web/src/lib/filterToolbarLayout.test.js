import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('App keeps the selected single-line toolbar filter layout and removes preview mode switching', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /renderToolbarFilters/);
  assert.match(source, /\{renderToolbarFilters\(\)\}/);
  assert.match(source, /moreFiltersLabel/);
  assert.doesNotMatch(source, /filterLayoutMode/);
  assert.doesNotMatch(source, /renderFilterModeSwitcher/);
  assert.doesNotMatch(source, /renderChartFirstFilters/);
  assert.doesNotMatch(source, /renderFocusFilters/);
});
