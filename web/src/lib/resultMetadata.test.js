import test from 'node:test';
import assert from 'node:assert/strict';

import {
  formatDataGradeLabel,
  formatFreshnessLabel,
  formatMetadataUnitLabel,
  getDataGradeTone,
  getResultMetadata,
} from './resultMetadata.js';

test('getResultMetadata returns stable defaults when metadata is missing', () => {
  const metadata = getResultMetadata({});
  assert.equal(metadata.data_grade, 'unknown');
  assert.equal(metadata.currency, '');
  assert.equal(metadata.interval_minutes, null);
  assert.deepEqual(metadata.freshness, {});
  assert.deepEqual(metadata.warnings, []);
});

test('getResultMetadata reads known metadata fields', () => {
  const metadata = getResultMetadata({
    metadata: {
      market: 'NEM',
      region_or_zone: 'NSW1',
      timezone: 'Australia/Sydney',
      currency: 'AUD',
      unit: 'AUD/MWh',
      interval_minutes: 5,
      data_grade: 'analytical',
      data_quality_score: 0.94,
      source_name: 'AEMO',
      source_version: '2026-04-27 00:10:00',
      methodology_version: 'price_trend_v1',
      freshness: { last_updated_at: '2026-04-27 00:10:00' },
      warnings: ['sample'],
    },
  });

  assert.equal(metadata.market, 'NEM');
  assert.equal(metadata.region_or_zone, 'NSW1');
  assert.equal(metadata.timezone, 'Australia/Sydney');
  assert.equal(metadata.currency, 'AUD');
  assert.equal(metadata.unit, 'AUD/MWh');
  assert.equal(metadata.interval_minutes, 5);
  assert.equal(metadata.data_grade, 'analytical');
  assert.equal(metadata.data_quality_score, 0.94);
  assert.equal(metadata.source_name, 'AEMO');
  assert.equal(metadata.source_version, '2026-04-27 00:10:00');
  assert.equal(metadata.methodology_version, 'price_trend_v1');
  assert.deepEqual(metadata.freshness, { last_updated_at: '2026-04-27 00:10:00' });
  assert.deepEqual(metadata.warnings, ['sample']);
});

test('getDataGradeTone maps preview-like grades to warning tone', () => {
  assert.equal(getDataGradeTone('preview'), 'warning');
  assert.equal(getDataGradeTone('analytical-preview'), 'warning');
  assert.equal(getDataGradeTone('analytical'), 'success');
  assert.equal(getDataGradeTone('unknown'), 'neutral');
});

test('formatDataGradeLabel returns user-facing bilingual labels', () => {
  assert.equal(formatDataGradeLabel('analytical', 'zh'), '分析级');
  assert.equal(formatDataGradeLabel('preview', 'zh'), '预览级');
  assert.equal(formatDataGradeLabel('analytical-preview', 'en'), 'Analytical Preview');
  assert.equal(formatDataGradeLabel('unknown', 'en'), 'Unknown');
});

test('formatMetadataUnitLabel avoids duplicated currency and unit output', () => {
  assert.equal(formatMetadataUnitLabel({ currency: 'AUD', unit: 'AUD/MWh' }), 'AUD/MWh');
  assert.equal(formatMetadataUnitLabel({ currency: 'EUR', unit: 'EUR/MW' }), 'EUR/MW');
  assert.equal(formatMetadataUnitLabel({ currency: 'AUD', unit: '' }), 'AUD');
});

test('formatFreshnessLabel returns friendly fallback and timestamp text', () => {
  assert.equal(formatFreshnessLabel({}, 'zh'), '暂无更新时间');
  assert.equal(
    formatFreshnessLabel({ last_updated_at: '2026-04-27 00:10:00' }, 'en'),
    'Updated 2026-04-27 00:10:00',
  );
});
