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
