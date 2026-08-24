import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 2026-08-20：旧 App.jsx 阶段外壳（stage-24h-outlook / stage-bess-decision 等）已随漏斗化重构移除，
// 对应死断言删除；模块挂载现由 ModuleRenderer + marketConfig 测试覆盖。

test('P3 decision copy and backend contract expose conclusion, readiness, and scope semantics', () => {
  const p3Source = fs.readFileSync(path.resolve(__dirname, './p3Decision.js'), 'utf8');
  const backendSource = fs.readFileSync(path.resolve(__dirname, '../../../backend/server.py'), 'utf8');
  const panelSource = fs.readFileSync(path.resolve(__dirname, '../components/P3BessDecisionPanel.jsx'), 'utf8');

  assert.match(p3Source, /recommendationSummary/);
  assert.match(p3Source, /explanationChain/);
  assert.match(p3Source, /riskBoundary/);
  assert.match(p3Source, /readinessStatus/);
  assert.match(p3Source, /conclusionScope/);
  assert.match(backendSource, /recommendation_summary/);
  assert.match(backendSource, /explanation_chain/);
  assert.match(backendSource, /risk_boundary/);
  assert.match(backendSource, /value_stream_coverage/);
  assert.match(backendSource, /readiness_status/);
  assert.match(panelSource, /copy\.recommendationSummary/);
  assert.match(panelSource, /copy\.explanationChain/);
  assert.match(panelSource, /copy\.riskBoundary/);
  assert.match(panelSource, /copy\.readinessStatus/);
});
