import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('App keeps the AEMO home page converged into three primary stages while allowing product-facing labels to shift', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /id="stage-current-market"/);
  assert.match(source, /id="stage-24h-outlook"/);
  assert.match(source, /id="stage-bess-decision"/);
  assert.match(source, /t\.appShell\.stageCurrentMarket/);
  assert.match(source, /t\.appShell\.stage24hOutlook/);
  assert.match(source, /t\.appShell\.stageBessDecision/);
  assert.doesNotMatch(source, /id="stage-opportunities"/);
  assert.doesNotMatch(source, /id="stage-investment"/);
});

test('App removes Market Screening from the top-level AEMO homepage flow and nests investment under BESS Decision', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.doesNotMatch(source, /<MarketScreening/);
  assert.match(source, /<PageSection[\s\S]*?id="stage-bess-decision"[\s\S]*?<InvestmentAnalysis/);
});

test('translations expose the new current-market, 24h outlook, and BESS decision shell copy in both languages', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  assert.match(source, /stageCurrentMarket/);
  assert.match(source, /stage24hOutlook/);
  assert.match(source, /stageBessDecision/);
  assert.match(source, /reserveOpportunityTitle/);
  assert.match(source, /investmentReadinessTitle/);
  assert.match(source, /previewOnly/);
});

test('result metadata supports decision-grade labels alongside preview and analytical grades', async () => {
  const { formatDataGradeLabel, getDataGradeTone, getDataGradeCaveat } = await import('./resultMetadata.js');

  assert.equal(formatDataGradeLabel('decision-grade', 'zh'), '决策级');
  assert.equal(formatDataGradeLabel('decision-grade', 'en'), 'Decision Grade');
  assert.equal(getDataGradeTone('decision-grade'), 'success');
  assert.match(getDataGradeCaveat('decision-grade', 'en'), /decision-grade/i);
});

test('backend descriptions and metadata text frame FCAS as reserve opportunity and investment as market-entry readiness', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../../../backend/server.py'), 'utf8');

  assert.match(source, /Reserve Opportunity/);
  assert.match(source, /Market Entry Readiness/);
  assert.match(source, /decision-grade/);
  assert.match(source, /preview_only/);
});
