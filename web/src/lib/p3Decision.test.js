import test from 'node:test';
import assert from 'node:assert/strict';

import {
  buildP3DecisionUrl,
  formatDecisionActionLabel,
  formatDecisionErrorGrade,
  formatDecisionCalibrationGrade,
  formatDecisionUsageScope,
  normalizeP3DecisionPayload,
} from './p3Decision.js';

test('buildP3DecisionUrl targets p3 decision route', () => {
  const url = buildP3DecisionUrl('http://127.0.0.1:8085/api');
  assert.equal(url, 'http://127.0.0.1:8085/api/p3/bess/decision-layer');
});

test('normalizeP3DecisionPayload keeps strategy bundle and metadata', () => {
  const payload = normalizeP3DecisionPayload({
    market: 'NEM',
    region: 'NSW1',
    market_design_context: 'NEM energy-plus-FCAS market view',
    value_stream_coverage: ['energy_arbitrage', 'reserve_proxy'],
    capacity_revenue_in_scope: false,
    benchmark_family: 'australia_bess_entry_v1',
    readiness_status: 'screenable',
    conclusion_scope: 'NEM entry view',
    coverage_mode: 'decision-support',
    regulatory_scope: 'NEM',
    result_type: 'investment_conclusion',
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
  assert.equal(payload.marketDesignContext, 'NEM energy-plus-FCAS market view');
  assert.deepEqual(payload.valueStreamCoverage, ['energy_arbitrage', 'reserve_proxy']);
  assert.equal(payload.capacityRevenueInScope, false);
  assert.equal(payload.benchmarkFamily, 'australia_bess_entry_v1');
  assert.equal(payload.readinessStatus, 'screenable');
  assert.equal(payload.conclusionScope, 'NEM entry view');
  assert.equal(payload.coverageMode, 'decision-support');
  assert.equal(payload.regulatoryScope, 'NEM');
  assert.equal(payload.resultType, 'investment_conclusion');
});

test('p3 decision helpers translate model enums into business-readable labels', () => {
  assert.equal(formatDecisionActionLabel('forecast_driven_dispatch', 'en'), 'Outlook-backed entry case');
  assert.equal(formatDecisionActionLabel('rule_based_dispatch', 'zh'), '保守回退判断');
  assert.equal(formatDecisionCalibrationGrade('mixed', 'en'), 'Usable with caution');
  assert.equal(formatDecisionCalibrationGrade('poor', 'zh'), '校准偏弱');
  assert.equal(formatDecisionErrorGrade('moderate_error', 'en'), 'Normal forecast error');
  assert.equal(formatDecisionErrorGrade('high_error', 'zh'), '误差偏高');
  assert.equal(formatDecisionUsageScope('decision-grade', 'en'), 'Suitable for investment review');
  assert.equal(formatDecisionUsageScope('preview/core-only', 'zh'), '适合方向判断');
});
