import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { getInvestmentCopy, shouldAutoRunInvestment } from './investmentAnalysis.js';
import { translations } from '../translations.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('shouldAutoRunInvestment only auto-runs when section is visible and current key is not loaded', () => {
  assert.equal(
    shouldAutoRunInvestment({
      isVisible: true,
      isLoading: false,
      requestKey: 'QLD1',
      loadedKey: null,
    }),
    true,
  );

  assert.equal(
    shouldAutoRunInvestment({
      isVisible: false,
      isLoading: false,
      requestKey: 'QLD1',
      loadedKey: null,
    }),
    false,
  );

  assert.equal(
    shouldAutoRunInvestment({
      isVisible: true,
      isLoading: true,
      requestKey: 'QLD1',
      loadedKey: null,
    }),
    false,
  );

  assert.equal(
    shouldAutoRunInvestment({
      isVisible: true,
      isLoading: false,
      requestKey: 'QLD1',
      loadedKey: 'QLD1',
    }),
    false,
  );
});

test('investment copy resolves bilingual labels from translations', () => {
  const zhCopy = getInvestmentCopy('zh', translations.zh.investment);
  const enCopy = getInvestmentCopy('en', translations.en.investment);

  assert.equal(zhCopy.title, '投资分析');
  assert.equal(zhCopy.runAnalysis, '运行分析');
  assert.equal(zhCopy.groups.storage, '储能参数');
  assert.equal(enCopy.title, 'Investment Analysis');
  assert.equal(enCopy.runAnalysis, 'Run Analysis');
  assert.equal(enCopy.groups.finance, 'Finance');
});

test('InvestmentAnalysis component avoids hardcoded primary English UI labels', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');

  for (const phrase of [
    'Investment Analysis',
    'Parameters',
    'Run Analysis',
    'Revenue Breakdown (Year 1)',
    'Cash Flow Projection',
  ]) {
    assert.equal(source.includes(phrase), false, `component should not hardcode "${phrase}"`);
  }
});
