import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildPresetWindow,
  buildHourlyProfile,
  formatFingridValue,
} from './fingridDataset.js';

test('buildPresetWindow returns bounded ISO timestamps', () => {
  const window = buildPresetWindow('30d', new Date('2026-04-23T00:00:00Z'));
  assert.equal(window.end, '2026-04-23T00:00:00.000Z');
  assert.match(window.start, /^2026-03-/);
});

test('buildHourlyProfile averages values by local hour', () => {
  const profile = buildHourlyProfile([
    { timestamp: '2026-01-01T02:00:00+02:00', value: 10 },
    { timestamp: '2026-01-02T02:00:00+02:00', value: 14 },
  ]);
  assert.deepEqual(profile, [{ hour: 2, avg_value: 12 }]);
});

test('formatFingridValue appends the dataset unit', () => {
  assert.equal(formatFingridValue(12.3456, 'EUR/MW'), '12.35 EUR/MW');
});
