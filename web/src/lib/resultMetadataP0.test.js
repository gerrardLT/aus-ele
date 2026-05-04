import test from 'node:test';
import assert from 'node:assert/strict';

import { formatDatasetFamilyLabel, getResultMetadata } from './resultMetadata.js';

test('reads dataset family and lineage from metadata payload', () => {
  const metadata = getResultMetadata({
    metadata: {
      dataset_family: 'load_actual',
      observation_kind: 'actual',
      grade: 'preview',
      lineage: { source_id: 'aemo_nem_operational_demand' },
    },
  });

  assert.equal(metadata.dataset_family, 'load_actual');
  assert.equal(metadata.observation_kind, 'actual');
  assert.equal(metadata.lineage.source_id, 'aemo_nem_operational_demand');
});

test('formats dataset family labels without hardcoding page-specific copy', () => {
  assert.equal(formatDatasetFamilyLabel('load_actual', 'en'), 'Load Actual');
  assert.equal(formatDatasetFamilyLabel('load_actual', 'zh'), '负荷实绩');
});

test('formats renewable dataset family labels for p0 fundamentals', () => {
  assert.equal(formatDatasetFamilyLabel('wind_forecast', 'en'), 'Wind Forecast');
  assert.equal(formatDatasetFamilyLabel('wind_actual', 'en'), 'Wind Actual');
  assert.equal(formatDatasetFamilyLabel('solar_forecast', 'en'), 'Solar Forecast');
  assert.equal(formatDatasetFamilyLabel('solar_actual', 'en'), 'Solar Actual');
  assert.equal(formatDatasetFamilyLabel('rooftop_pv', 'en'), 'Rooftop PV');
});

test('formats grid state and reserve dataset family labels', () => {
  assert.equal(formatDatasetFamilyLabel('outage', 'en'), 'Outage');
  assert.equal(formatDatasetFamilyLabel('interconnector_flow', 'en'), 'Interconnector Flow');
  assert.equal(formatDatasetFamilyLabel('reserve_requirement', 'en'), 'Reserve Requirement');
  assert.equal(formatDatasetFamilyLabel('reserve_shortfall', 'en'), 'Reserve Shortfall');
});

test('formats weather and unit availability labels', () => {
  assert.equal(formatDatasetFamilyLabel('weather', 'en'), 'Weather');
  assert.equal(formatDatasetFamilyLabel('unit_availability', 'en'), 'Unit Availability');
});

test('formats p2 forecast layer labels', () => {
  assert.equal(formatDatasetFamilyLabel('forecast_layer', 'en'), 'Forecast Layer');
  assert.equal(formatDatasetFamilyLabel('forecast_layer', 'zh'), '预测层');
});

test('formats p3 bess decision layer labels', () => {
  assert.equal(formatDatasetFamilyLabel('bess_decision_layer', 'en'), 'BESS Decision Layer');
  assert.equal(formatDatasetFamilyLabel('bess_decision_layer', 'zh'), '储能决策层');
});
