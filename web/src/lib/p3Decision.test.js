import test from 'node:test';
import assert from 'node:assert/strict';

import { buildP3DecisionUrl, normalizeP3DecisionPayload } from './p3Decision.js';

test('buildP3DecisionUrl targets p3 decision route', () => {
  const url = buildP3DecisionUrl('http://127.0.0.1:8085/api');
  assert.equal(url, 'http://127.0.0.1:8085/api/p3/bess/decision-layer');
});

test('normalizeP3DecisionPayload keeps strategy bundle and metadata', () => {
  const payload = normalizeP3DecisionPayload({
    market: 'NEM',
    region: 'NSW1',
    decision_summary: { recommended_strategy: 'forecast_driven_dispatch' },
    strategy_bundle: {
      forecast_driven_dispatch: { net_revenue: 180.5 },
    },
    revenue_attribution: { timing_alpha: 12.5 },
    forecast_context: { horizon: '24h' },
    source_backtest: { timeline_points: 4, cycle_summary: { equivalent_cycles: 2.0 } },
    governance: {
      freshness: { status: 'fresh' },
      drift: { status: 'monitor' },
      disclaimer: { usage_scope: 'research_and_operational_support_only' },
      lineage: { source_id: 'p3_bess_decision_layer' },
    },
    metadata: { dataset_family: 'bess_decision_layer' },
  });

  assert.equal(payload.market, 'NEM');
  assert.equal(payload.forecastContext.horizon, '24h');
  assert.equal(payload.decisionSummary.recommended_strategy, 'forecast_driven_dispatch');
  assert.equal(payload.strategyBundle.forecast_driven_dispatch.net_revenue, 180.5);
  assert.equal(payload.sourceBacktest.timeline_points, 4);
  assert.equal(payload.governance.freshness.status, 'fresh');
  assert.equal(payload.governance.lineage.source_id, 'p3_bess_decision_layer');
  assert.equal(payload.metadata.dataset_family, 'bess_decision_layer');
});
