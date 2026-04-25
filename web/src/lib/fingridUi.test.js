import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildFingridRequestLimit,
  buildFingridSummaryCards,
  localizeFingridDataset,
} from './fingridUi.js';

test('buildFingridRequestLimit removes the cap for all-window aggregated views', () => {
  assert.equal(buildFingridRequestLimit({ preset: 'all', aggregation: '4h' }), null);
  assert.equal(buildFingridRequestLimit({ preset: 'all', aggregation: 'day' }), null);
  assert.equal(buildFingridRequestLimit({ preset: 'custom', aggregation: '4h' }), null);
  assert.equal(buildFingridRequestLimit({ preset: 'all', aggregation: 'raw' }), 5000);
});

test('buildFingridSummaryCards exposes current bucket avg peak and trough metrics', () => {
  const cards = buildFingridSummaryCards({
    lang: 'zh',
    aggregation: '4h',
    summaryPayload: {
      dataset: { unit: 'EUR/MW' },
      kpis: {
        latest_value: 9.1,
        avg_24h: 8.4,
        avg_7d: 7.5,
        avg_30d: 6.8,
        min_value: 1.2,
        max_value: 14.5,
      },
    },
    seriesPayload: {
      series: [
        {
          avg_value: 8.0,
          peak_value: 11.0,
          trough_value: 5.0,
        },
      ],
    },
  });

  assert.deepEqual(
    cards.slice(0, 3).map((card) => [card.label, card.value]),
    [
      ['4H 平均', 8.0],
      ['4H 波峰', 11.0],
      ['4H 波谷', 5.0],
    ],
  );
});

test('localizeFingridDataset provides Chinese copy for dataset 317', () => {
  const localized = localizeFingridDataset(
    {
      dataset_id: '317',
      name: 'FCR-N hourly market prices',
      description: 'FCR-N hourly reserve-capacity market price in Finland.',
    },
    'zh',
  );

  assert.match(localized.name, /FCR-N/);
  assert.match(localized.description, /芬兰/);
});
