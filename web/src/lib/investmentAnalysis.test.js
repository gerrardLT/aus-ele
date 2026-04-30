import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  formatPercentageValue,
  getInvestmentCopy,
  shouldAutoRunInvestment,
} from './investmentAnalysis.js';
import { getDataGradeCaveat } from './resultMetadata.js';
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

test('formatPercentageValue renders percentages with two decimals and preserves empty values', () => {
  assert.equal(formatPercentageValue(12.3456), '12.35%');
  assert.equal(formatPercentageValue(0), '0.00%');
  assert.equal(formatPercentageValue(null), '-');
  assert.equal(formatPercentageValue(undefined), '-');
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

test('investment analysis source keeps Chinese defaults readable', () => {
  const source = fs.readFileSync(path.resolve(__dirname, './investmentAnalysis.js'), 'utf8');

  assert.equal(source.includes("title: '鎶"), false);
  assert.equal(source.includes("runAnalysis: '杩"), false);
  assert.equal(source.includes("storage: '鍌"), false);
  assert.equal(source.includes("discount: '鎶"), false);
  assert.equal(source.includes("lazyVisible: '鍙"), false);
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

test('InvestmentAnalysis avoids hardcoded secondary English labels for finance and diagnostics', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');

  for (const phrase of [
    'Project Finance',
    'Forecast Loss',
    'FCAS Activation',
    'Run Monte Carlo Simulation (P10/P50/P90)',
    'Debt Cap',
    'Levered IRR',
    'Equity Return',
    'Legacy fallback active',
    'Observed Backtest',
    'Backtest Trace',
    'Gross Energy Revenue',
    'Net Energy Revenue',
    'Observed Net Arbitrage',
    'Equivalent Cycles',
    'Methodology',
    'Driver Count',
    'Timeline Points',
    'Source Years',
    'No Standardized Backtest Coverage',
    'The requested years do not currently have standardized BESS backtest source data, so arbitrage baseline revenue is held at zero.',
    'P90 (Downside / Conservative)',
    'P50 (Base Case / Expected)',
    'P10 (Upside / Optimistic)',
  ]) {
    assert.equal(source.includes(phrase), false, `component should not hardcode "${phrase}"`);
  }

  assert.match(source, /copy\.tableHeaders\.arbitrage/);
  assert.match(source, /copy\.tableHeaders\.fcas/);
  assert.match(source, /copy\.tableHeaders\.capacity/);
  assert.match(source, /copy\.statuses\.hidden/);
  assert.match(source, /copy\.monteCarloLabels\.p90/);
  assert.match(source, /copy\.monteCarloLabels\.p50/);
  assert.match(source, /copy\.monteCarloLabels\.p10/);
  assert.equal(source.includes("|| 'FCAS Revenue Mode'"), false);
  assert.equal(source.includes("|| 'Auto'"), false);
  assert.equal(source.includes("|| 'Manual'"), false);
});

test('getDataGradeCaveat exposes WEM preview-grade warning copy', () => {
  assert.equal(getDataGradeCaveat('preview', 'en'), 'Preview only. Do not use for project finance.');
  assert.equal(getDataGradeCaveat('preview', 'zh'), '仅供预览，请勿用于项目融资。');
});

test('InvestmentAnalysis shows DataQualityBadge and preview caveat support', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');
  assert.match(source, /DataQualityBadge/);
  assert.match(source, /sectionMetadata/);
});

test('InvestmentAnalysis preserves lazy and error-state UI branches', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');
  assert.match(source, /lazyLoadNote/);
  assert.match(source, /setError/);
  assert.match(source, /copy\.statuses\.requestFailed/);
  assert.equal(source.includes("'Loading...'"), false);
});

test('InvestmentAnalysis consumes backtest observed and traceability fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');
  assert.match(source, /backtest_observed/);
  assert.match(source, /backtest_reference/);
  assert.match(source, /arbitrage_net_observed/);
  assert.match(source, /backtest_fallback_used/);
  assert.match(source, /no_standardized_backtest_data/);
});

test('InvestmentAnalysis cash-flow views consume structured backtest-driven fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/InvestmentAnalysis.jsx'), 'utf8');
  assert.match(source, /total_revenue/);
  assert.match(source, /cumulative_cash_flow/);
  assert.match(source, /revenue_arbitrage/);
  assert.match(source, /revenue_fcas/);
  assert.match(source, /revenue_capacity/);
});
