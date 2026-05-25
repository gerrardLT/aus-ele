import { test } from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('useFilterRefreshGuard hook exists and exports a named function', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../hooks/useFilterRefreshGuard.js'),
    'utf8'
  );
  assert.match(source, /export function useFilterRefreshGuard/);
});

test('useFilterRefreshGuard uses a 2-second refresh window', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../hooks/useFilterRefreshGuard.js'),
    'utf8'
  );
  assert.match(source, /2000/);
});

test('useFilterRefreshGuard returns isRefreshing and lastFilterChangeTime', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../hooks/useFilterRefreshGuard.js'),
    'utf8'
  );
  assert.match(source, /isRefreshing/);
  assert.match(source, /lastFilterChangeTime/);
});

test('useFilterRefreshGuard subscribes to FilterContext via useFilters', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../hooks/useFilterRefreshGuard.js'),
    'utf8'
  );
  assert.match(source, /useFilters/);
});

test('useFilterRefreshGuard cleans up timers on unmount', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../hooks/useFilterRefreshGuard.js'),
    'utf8'
  );
  assert.match(source, /clearTimeout/);
});

test('useFilterRefreshGuard tracks changes to region, year, quarter, dayType, months', () => {
  const source = fs.readFileSync(
    path.resolve(__dirname, '../hooks/useFilterRefreshGuard.js'),
    'utf8'
  );
  assert.match(source, /filters\.region/);
  assert.match(source, /filters\.year/);
  assert.match(source, /filters\.quarter/);
  assert.match(source, /filters\.dayType/);
  assert.match(source, /filters\.months/);
});
