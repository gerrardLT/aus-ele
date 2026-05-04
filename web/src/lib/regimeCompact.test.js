import test from 'node:test';
import assert from 'node:assert/strict';

import {
  formatRegimeName,
  getRegimeAccent,
  normalizeRegimeCompact,
  pickFirstAvailableRegimeCompact,
} from './regimeCompact.js';

test('normalizeRegimeCompact returns stable fallback shape for empty payloads', () => {
  const payload = normalizeRegimeCompact(null);

  assert.equal(payload.availability_status, 'unavailable');
  assert.equal(payload.primary_regime, null);
  assert.deepEqual(payload.active_regimes, []);
  assert.deepEqual(payload.regime_score_map, {});
  assert.deepEqual(payload.top_drivers, []);
  assert.deepEqual(payload.transition_hints, []);
  assert.deepEqual(payload.warnings, ['regime_layer_unavailable']);
});

test('normalizeRegimeCompact preserves compact contract arrays and maps', () => {
  const payload = normalizeRegimeCompact({
    availability_status: 'available',
    primary_regime: { regime: 'scarcity', score: 68.0, confidence: 0.74 },
    active_regimes: [{ regime: 'scarcity', score: 68.0, confidence: 0.74 }],
    regime_score_map: { scarcity: 68.0 },
    top_drivers: [{ headline: 'Load tightness signal 21.1', driver_type: 'load_tightness' }],
    transition_hints: ['Reserve stress can escalate into broader scarcity if shortfalls persist.'],
    warnings: [],
  });

  assert.equal(payload.availability_status, 'available');
  assert.equal(payload.primary_regime.regime, 'scarcity');
  assert.equal(payload.active_regimes.length, 1);
  assert.equal(payload.regime_score_map.scarcity, 68.0);
  assert.equal(payload.top_drivers[0].driver_type, 'load_tightness');
});

test('getRegimeAccent and formatRegimeName support compact presentation mapping', () => {
  const accent = getRegimeAccent('reserve_stress');
  const name = formatRegimeName('reserve_stress', {
    regimeNames: { reserve_stress: 'Reserve stress' },
  });

  assert.equal(accent.tone, 'reserve');
  assert.ok(accent.color);
  assert.equal(name, 'Reserve stress');
});

test('pickFirstAvailableRegimeCompact returns the first available compact candidate', () => {
  const unavailable = {
    availability_status: 'unavailable',
    warnings: ['regime_layer_unavailable'],
  };
  const available = {
    availability_status: 'available',
    primary_regime: { regime: 'oversupply', score: 72.2, confidence: 0.66 },
  };

  const picked = pickFirstAvailableRegimeCompact(null, unavailable, available);

  assert.equal(picked, available);
});

test('pickFirstAvailableRegimeCompact falls back to first truthy candidate when none are available', () => {
  const unavailable = {
    availability_status: 'unavailable',
    warnings: ['regime_layer_unavailable'],
  };
  const alsoUnavailable = {
    availability_status: 'unavailable',
    warnings: ['partial_window'],
  };

  const picked = pickFirstAvailableRegimeCompact(undefined, unavailable, alsoUnavailable);

  assert.equal(picked, unavailable);
});
