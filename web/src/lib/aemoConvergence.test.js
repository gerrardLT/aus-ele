import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

// 2026-08-20：旧 App.jsx 三阶段外壳已随漏斗化重构移除（stage-current-market 等），
// 对应死断言删除；阶段结构现由 marketConfig.test.js / dynamicRendering.test.js 覆盖。

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
