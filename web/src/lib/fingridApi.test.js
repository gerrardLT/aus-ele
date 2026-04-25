import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildFingridSeriesUrl,
  buildFingridSummaryUrl,
  buildFingridSyncUrl,
  normalizeFingridDatasetList,
} from './fingridApi.js';

test('buildFingridSeriesUrl encodes dataset and query controls', () => {
  const url = buildFingridSeriesUrl('http://127.0.0.1:8085/api', {
    datasetId: '317',
    start: '2026-01-01T00:00:00Z',
    end: '2026-01-02T00:00:00Z',
    tz: 'Europe/Helsinki',
    aggregation: 'day',
    limit: 200,
  });

  assert.match(url, /datasets\/317\/series/);
  assert.match(url, /aggregation=day/);
  assert.match(url, /tz=Europe%2FHelsinki/);
  assert.match(url, /limit=200/);
});

test('buildFingridSummaryUrl and buildFingridSyncUrl include dataset id', () => {
  assert.match(buildFingridSummaryUrl('http://127.0.0.1:8085/api', { datasetId: '317' }), /datasets\/317\/summary/);
  assert.match(buildFingridSyncUrl('http://127.0.0.1:8085/api', '317'), /datasets\/317\/sync/);
});

test('buildFingridSeriesUrl omits the limit parameter when limit is null', () => {
  const url = buildFingridSeriesUrl('http://127.0.0.1:8085/api', {
    datasetId: '317',
    aggregation: '4h',
    limit: null,
  });

  assert.doesNotMatch(url, /limit=/);
});

test('normalizeFingridDatasetList falls back to an empty array', () => {
  assert.deepEqual(normalizeFingridDatasetList({}), []);
  assert.equal(normalizeFingridDatasetList({ datasets: [{ dataset_id: '317' }] })[0].dataset_id, '317');
});
