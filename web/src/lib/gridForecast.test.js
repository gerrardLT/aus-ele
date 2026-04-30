import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  buildGridForecastUrl,
  getForecastModeCopy,
  normalizeForecastResponse,
  getForecastCoverageCopy,
  getForecastContextItems,
  getForecastDriverLabel,
  getForecastSourceLabel,
  getForecastSectionCopy,
} from './gridForecast.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('buildGridForecastUrl includes market region horizon and optional as_of', () => {
  const url = buildGridForecastUrl('http://127.0.0.1:8085/api', {
    market: 'NEM',
    region: 'NSW1',
    horizon: '24h',
    asOf: '2026-04-15 09:00:00',
  });

  assert.match(url, /market=NEM/);
  assert.match(url, /region=NSW1/);
  assert.match(url, /horizon=24h/);
  assert.match(url, /as_of=2026-04-15/);
});

test('normalizeForecastResponse sorts future windows and preserves coverage metadata', () => {
  const normalized = normalizeForecastResponse({
    metadata: { market: 'NEM', coverage_quality: 'core_only', warnings: ['confidence_constrained'] },
    coverage: {
      source_status: { nem_predispatch: 'ok' },
      forward_points: 2,
    },
    market_context: {
      forward_price_max_aud_mwh: 420,
      forward_demand_peak_mw: 12900,
    },
    windows: [
      { start_time: '2026-04-15 18:00:00', end_time: '2026-04-15 20:00:00', window_type: 'discharge' },
      { start_time: '2026-04-15 11:00:00', end_time: '2026-04-15 13:00:00', window_type: 'charge' },
    ],
  });

  assert.equal(normalized.windows[0].window_type, 'charge');
  assert.deepEqual(normalized.metadata.warnings, ['confidence_constrained']);
  assert.equal(normalized.coverage.forward_points, 2);
  assert.equal(normalized.coverage.source_status.nem_predispatch, 'ok');
  assert.equal(normalized.marketContext.forward_price_max_aud_mwh, 420);
});

test('getForecastCoverageCopy returns Chinese copy for core-only WEM mode', () => {
  const copy = getForecastCoverageCopy('core_only', 'zh');
  assert.match(copy, /\u6838\u5fc3/);
});

test('getForecastContextItems exposes NEM forward price and demand signals', () => {
  const items = getForecastContextItems(
    normalizeForecastResponse({
      metadata: { market: 'NEM' },
      market_context: {
        recent_avg_price_aud_mwh: 50.5,
        forward_price_min_aud_mwh: -35,
        forward_price_max_aud_mwh: 420,
        forward_demand_peak_mw: 12900,
      },
    }),
    'en',
  );

  assert.ok(
    items.some((item) => item.key === 'forward_price_band' && /-35/.test(item.value) && /420/.test(item.value))
  );
  assert.ok(
    items.some(
      (item) => item.key === 'forward_demand_peak_mw' && item.value.replace(/\D/g, '').includes('12900')
    )
  );
});

test('localized labels exist for known sources and drivers', () => {
  assert.match(getForecastSourceLabel('nem_predispatch', 'en'), /Predispatch/i);
  assert.match(getForecastDriverLabel('predispatch_price_spike', 'zh'), /\u9884\u8c03\u5ea6/);
});

test('forecast copy exposes localized horizon and mode labels', () => {
  const zhCopy = getForecastSectionCopy('zh');
  const enCopy = getForecastSectionCopy('en');

  assert.equal(zhCopy.sectionLabel, '电网预测');
  assert.equal(zhCopy.signalDesk, '信号总览');
  assert.match(getForecastModeCopy('daily_regime_outlook', 'zh'), /日度/);
  assert.equal(enCopy.marketContext, 'Market Context');
  assert.match(getForecastModeCopy('structural_regime_outlook', 'en'), /Structural/i);
});

test('GridForecast component avoids hardcoded desk labels and mojibake copy', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/GridForecast.jsx'), 'utf8');

  assert.equal(source.includes('Signal Desk'), false);
  assert.equal(source.includes('Market Context'), false);
  assert.equal(source.includes('Grid Forecast'), false);
  assert.equal(source.includes("|| 'NEM'"), false);
  assert.equal(source.includes("|| '24h'"), false);
  assert.match(source, /sectionCopy\.horizon24h/);
  assert.match(source, /sectionCopy\.horizon7d/);
  assert.match(source, /sectionCopy\.horizon30d/);
});

test('app shell and translations avoid known mojibake fragments', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const translationsSource = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  for (const phrase of ['鐢电', '鍛ㄦ湡', '閲嶇疆', '姝ｅ湪', '鍌ㄨ兘', '鍏呯數']) {
    assert.equal(appSource.includes(phrase), false, `App should not contain "${phrase}"`);
    assert.equal(translationsSource.includes(phrase), false, `translations should not contain "${phrase}"`);
  }
});

test('translations source keeps high-visibility Chinese literals readable', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  assert.equal(source.includes("quarterSelect: '瀛"), false);
  assert.equal(source.includes("resetFilters: '閲"), false);
  assert.equal(source.includes("loading: '姝"), false);
  assert.equal(source.includes("peak: '宄"), false);
  assert.equal(source.includes("title: '鐗"), false);
  assert.equal(source.includes("stackTitle: '鏀"), false);
  assert.equal(source.includes("cwTitle: '鍏"), false);
  assert.equal(source.includes("ccTitle: '寰"), false);
});

test('translations include readable Chinese labels for core dashboard and developer portal copy', async () => {
  const { translations } = await import('../translations.js');

  assert.equal(translations.zh.nav.brand, 'AEMO 澳洲电网智能观测站');
  assert.equal(translations.zh.filters.yearSelect, '年份选择 (YEAR)');
  assert.equal(translations.zh.status.retry, '重新尝试');
  assert.equal(translations.zh.forecast.title, '澳洲电网预测');
  assert.equal(translations.zh.developerPortal.title, '开发者门户');
  assert.equal(translations.en.developerPortal.title, 'Developer Portal');
});

test('translations expose readable Chinese labels for high-visibility dashboard copy', async () => {
  const { translations } = await import('../translations.js');

  assert.equal(translations.zh.filters.quarterSelect, '季度周期 (QUARTER)');
  assert.equal(translations.zh.filters.resetFilters, '重置筛选');
  assert.equal(translations.zh.status.loading, '正在扫描数据归档...');
  assert.equal(translations.zh.summary_stats.peak, '峰值价格');
  assert.equal(translations.zh.advanced_metrics.title, '特殊量化与极值统计');
  assert.equal(translations.zh.stacking.stackTitle, '收入叠加分析');
  assert.equal(translations.zh.charging.cwTitle, '充电窗口雷达');
  assert.equal(translations.zh.cycleCost.ccTitle, '循环成本 vs 盈利性分析');
});

test('App uses readable localized labels for nav, sync, and month reset controls', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /t\.nav\.fingrid/);
  assert.match(source, /t\.nav\.developerPortal/);
  assert.match(source, /t\.nav\.sync/);
  assert.match(source, /t\.nav\.syncing/);
  assert.match(source, /t\.filters\.resetFilters/);
  assert.equal(source.includes('閼侯剙鍙'), false);
  assert.equal(source.includes('瀵偓閸欐垼'), false);
  assert.equal(source.includes('闁插秶鐤'), false);
});
