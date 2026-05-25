import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('App demotes secondary outlook analytics and re-homes reserve and revenue modules under BESS Decision', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const outlookStart = source.indexOf('id="stage-24h-outlook"');
  const outlookEnd = source.indexOf('id="stage-bess-decision"');
  const outlookSection = source.slice(outlookStart, outlookEnd);
  const bessSection = source.slice(outlookEnd);

  assert.match(source, /id="sec-outlook-secondary"/);
  assert.match(source, /id="sec-bess-supporting"/);
  assert.match(source, /id="sec-bess-diagnostics"/);
  assert.match(outlookSection, /<GridForecast/);
  assert.match(outlookSection, /id="sec-outlook-secondary"[\s\S]*?<PeakAnalysis/);
  assert.match(outlookSection, /id="sec-outlook-secondary"[\s\S]*?<ChargingWindow/);
  assert.doesNotMatch(outlookSection, /<FcasAnalysis/);
  assert.doesNotMatch(outlookSection, /<RevenueStacking/);
  assert.match(bessSection, /<FcasAnalysis/);
  assert.match(bessSection, /<RevenueStacking/);
  assert.match(bessSection, /<BessSimulator/);
  assert.match(bessSection, /<CycleCost/);
});

test('App keeps the conclusion stage primary and elevates investment into a supporting readiness view', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const investmentSource = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');
  const bessStart = appSource.indexOf('id="stage-bess-decision"');
  const bessSection = appSource.slice(bessStart);

  assert.match(bessSection, /<P3BessDecisionPanel/);
  assert.match(bessSection, /<InvestmentAnalysis[\s\S]*showDecisionPanel=\{false\}/);
  assert.ok(bessSection.indexOf('<P3BessDecisionPanel') < bessSection.indexOf('<InvestmentAnalysis'));
  assert.doesNotMatch(investmentSource, /<P3BessDecisionPanel[\s\S]*initialPayload=\{result\?\.p3_decision \|\| null\}/);
});

test('conclusion stage reads in conclusion order: primary conclusion, readiness support, then revenue and reserve evidence', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const translationSource = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');
  const bessStart = appSource.indexOf('id="stage-bess-decision"');
  const bessSection = appSource.slice(bessStart);

  assert.match(translationSource, /bessSupportingTitle: 'Revenue And Reserve Support'/);
  assert.match(translationSource, /bessCapitalTitle: 'Project Returns'/);
  assert.ok(bessSection.indexOf('id="sec-decision"') < bessSection.indexOf('id="sec-investment"'));
  assert.ok(bessSection.indexOf('id="sec-investment"') < bessSection.indexOf('id="sec-bess-supporting"'));
});

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
