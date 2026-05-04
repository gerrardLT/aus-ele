import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildForecastLayerUrl,
  normalizeForecastResponse,
} from './gridForecast.js';

test('buildForecastLayerUrl points to p2 forecast-layer route', () => {
  const url = buildForecastLayerUrl('http://127.0.0.1:8085/api', {
    market: 'NEM',
    region: 'NSW1',
    horizon: '24h',
  });

  assert.equal(
    url,
    'http://127.0.0.1:8085/api/p2/forecast-layer?market=NEM&region=NSW1&horizon=24h',
  );
});

test('normalizeForecastResponse keeps baseline forecast diagnostics block', () => {
  const payload = normalizeForecastResponse({
    metadata: { forecast_mode: 'hybrid_signal_calibrated' },
    summary: { grid_stress_score: 81 },
    windows: [{ start_time: '2026-04-15T12:00:00Z', window_type: 'charge' }],
    baseline_forecast: {
      probabilities: {
        negative_price_duration_intervals: 2,
        negative_price_duration_hours: 1,
        duration_method: 'window_probability_scan_v1',
      },
      evaluation: {
        diagnostics: {
          status: 'available',
          error_grade: 'moderate_error',
          primary_gap_domain: 'coverage',
        },
      },
    },
  });

  assert.equal(payload.summary.grid_stress_score, 81);
  assert.equal(payload.windows.length, 1);
  assert.equal(payload.baselineForecast.probabilities.duration_method, 'window_probability_scan_v1');
  assert.equal(payload.baselineForecast.evaluation.diagnostics.status, 'available');
  assert.equal(payload.baselineForecast.evaluation.diagnostics.primary_gap_domain, 'coverage');
});

test('normalizeForecastResponse keeps governance payload for p4 workbench visibility', () => {
  const payload = normalizeForecastResponse({
    metadata: { forecast_mode: 'hybrid_signal_calibrated' },
    governance: {
      freshness: { status: 'fresh' },
      drift: { status: 'monitor' },
      forecast_value_attribution: {
        status: 'proxy_available',
        method: 'backtest_error_proxy_v1',
        overall_information_value_index: 0.71,
      },
      disclaimer: { usage_scope: 'research_and_operational_support_only' },
      lineage: { source_id: 'p2_forecast_layer' },
    },
  });

  assert.equal(payload.governance.freshness.status, 'fresh');
  assert.equal(payload.governance.drift.status, 'monitor');
  assert.equal(payload.governance.forecast_value_attribution.status, 'proxy_available');
  assert.equal(payload.governance.forecast_value_attribution.method, 'backtest_error_proxy_v1');
  assert.equal(payload.governance.lineage.source_id, 'p2_forecast_layer');
});
