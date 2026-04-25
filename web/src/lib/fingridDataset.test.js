import test from 'node:test';
import assert from 'node:assert/strict';

import {
  downsampleSeriesForChart,
  buildFingridTimeWindow,
  buildPresetWindow,
  getCustomDateRangeValidationCode,
  buildHourlyProfile,
  formatFingridValue,
} from './fingridDataset.js';

test('buildPresetWindow returns bounded ISO timestamps', () => {
  const window = buildPresetWindow('30d', new Date('2026-04-23T00:00:00Z'));
  assert.equal(window.end, '2026-04-23T00:00:00.000Z');
  assert.match(window.start, /^2026-03-/);
});

test('buildFingridTimeWindow converts custom date ranges using the selected timezone', () => {
  const window = buildFingridTimeWindow({
    preset: 'custom',
    customStartDate: '2026-04-01',
    customEndDate: '2026-04-03',
    tz: 'Europe/Helsinki',
  });

  assert.equal(window.start, '2026-03-31T21:00:00.000Z');
  assert.equal(window.end, '2026-04-03T21:00:00.000Z');
});

test('getCustomDateRangeValidationCode validates missing and descending custom ranges', () => {
  assert.equal(getCustomDateRangeValidationCode({ preset: 'custom', customStartDate: '', customEndDate: '' }), 'missing_custom_dates');
  assert.equal(
    getCustomDateRangeValidationCode({
      preset: 'custom',
      customStartDate: '2026-04-03',
      customEndDate: '2026-04-01',
    }),
    'invalid_custom_range',
  );
  assert.equal(
    getCustomDateRangeValidationCode({
      preset: 'custom',
      customStartDate: '2026-04-01',
      customEndDate: '2026-04-03',
    }),
    null,
  );
});

test('buildHourlyProfile averages values by local hour', () => {
  const profile = buildHourlyProfile([
    { timestamp: '2026-01-01T02:00:00+02:00', value: 10 },
    { timestamp: '2026-01-02T02:00:00+02:00', value: 14 },
  ]);
  assert.deepEqual(profile, [{ hour: 2, avg_value: 12 }]);
});

test('downsampleSeriesForChart caps point count and preserves endpoints', () => {
  const series = Array.from({ length: 1000 }, (_, index) => ({
    timestamp: `2026-01-${String((index % 28) + 1).padStart(2, '0')}T00:00:00+02:00-${index}`,
    value: index % 17 === 0 ? 200 - index : index,
  }));

  const downsampled = downsampleSeriesForChart(series, 120);

  assert.ok(downsampled.length <= 122);
  assert.deepEqual(downsampled[0], series[0]);
  assert.deepEqual(downsampled[downsampled.length - 1], series[series.length - 1]);
});

test('downsampleSeriesForChart preserves coverage and total sample count across chart buckets', () => {
  const pattern = [50, 0, 100, 50, 50, 50];
  const series = Array.from({ length: 24 }, (_, index) => ({
    timestamp: `2026-01-01T00:00:00+02:00-${index}`,
    timestamp_utc: `2026-01-01T00:00:00Z-${index}`,
    bucket_start: `start-${index}`,
    bucket_end: `end-${index}`,
    value: pattern[index % pattern.length],
    avg_value: pattern[index % pattern.length],
    peak_value: pattern[index % pattern.length],
    trough_value: pattern[index % pattern.length],
    sample_count: 1,
  }));

  const downsampled = downsampleSeriesForChart(series, 16);
  const totalSamples = downsampled.reduce((sum, point) => sum + Number(point.sample_count ?? 1), 0);

  assert.equal(downsampled[0].timestamp, series[0].timestamp);
  assert.equal(downsampled[1].bucket_start, series[1].bucket_start);
  assert.equal(downsampled[downsampled.length - 2].bucket_end, series[series.length - 2].bucket_end);
  assert.equal(downsampled[downsampled.length - 1].timestamp, series[series.length - 1].timestamp);
  assert.equal(totalSamples, series.length);
});

test('downsampleSeriesForChart aggregates interior buckets instead of keeping only extremes', () => {
  const series = [
    { timestamp: 't0', timestamp_utc: '2026-01-01T00:00:00Z', bucket_start: 't0', bucket_end: 't0', value: 10, avg_value: 10, peak_value: 10, trough_value: 10, sample_count: 1 },
    { timestamp: 't1', timestamp_utc: '2026-01-01T01:00:00Z', bucket_start: 't1', bucket_end: 't1', value: 0, avg_value: 0, peak_value: 0, trough_value: 0, sample_count: 1 },
    { timestamp: 't2', timestamp_utc: '2026-01-01T02:00:00Z', bucket_start: 't2', bucket_end: 't2', value: 100, avg_value: 100, peak_value: 100, trough_value: 100, sample_count: 1 },
    { timestamp: 't3', timestamp_utc: '2026-01-01T03:00:00Z', bucket_start: 't3', bucket_end: 't3', value: 0, avg_value: 0, peak_value: 0, trough_value: 0, sample_count: 1 },
    { timestamp: 't4', timestamp_utc: '2026-01-01T04:00:00Z', bucket_start: 't4', bucket_end: 't4', value: 50, avg_value: 50, peak_value: 50, trough_value: 50, sample_count: 1 },
    { timestamp: 't5', timestamp_utc: '2026-01-01T05:00:00Z', bucket_start: 't5', bucket_end: 't5', value: 50, avg_value: 50, peak_value: 50, trough_value: 50, sample_count: 1 },
    { timestamp: 't6', timestamp_utc: '2026-01-01T06:00:00Z', bucket_start: 't6', bucket_end: 't6', value: 50, avg_value: 50, peak_value: 50, trough_value: 50, sample_count: 1 },
    { timestamp: 't7', timestamp_utc: '2026-01-01T07:00:00Z', bucket_start: 't7', bucket_end: 't7', value: 40, avg_value: 40, peak_value: 40, trough_value: 40, sample_count: 1 },
  ];

  const downsampled = downsampleSeriesForChart(series, 4);

  assert.equal(downsampled.length, 4);
  assert.deepEqual(downsampled[0], series[0]);
  assert.deepEqual(downsampled[3], series[7]);
  assert.deepEqual(downsampled[1], {
    timestamp: 't2',
    timestamp_utc: '2026-01-01T02:00:00Z',
    bucket_start: 't1',
    bucket_end: 't3',
    value: 33.3333,
    avg_value: 33.3333,
    peak_value: 100,
    trough_value: 0,
    sample_count: 3,
    unit: undefined,
  });
  assert.deepEqual(downsampled[2], {
    timestamp: 't5',
    timestamp_utc: '2026-01-01T05:00:00Z',
    bucket_start: 't4',
    bucket_end: 't6',
    value: 50,
    avg_value: 50,
    peak_value: 50,
    trough_value: 50,
    sample_count: 3,
    unit: undefined,
  });
});

test('formatFingridValue appends the dataset unit', () => {
  assert.equal(formatFingridValue(12.3456, 'EUR/MW'), '12.35 EUR/MW');
});
