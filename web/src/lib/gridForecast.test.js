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

  for (const phrase of ['Signal Desk', 'Market Context', '娣?', '鐢?']) {
    assert.equal(source.includes(phrase), false, `component should not contain "${phrase}"`);
  }
});

test('app shell and translations avoid known mojibake fragments', () => {
  const appSource = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  const translationsSource = fs.readFileSync(path.resolve(__dirname, '../translations.js'), 'utf8');

  for (const phrase of ['甯', '鍚', '璇', '鈻?', '鉁?', '鉂?']) {
    assert.equal(appSource.includes(phrase), false, `App should not contain "${phrase}"`);
    assert.equal(translationsSource.includes(phrase), false, `translations should not contain "${phrase}"`);
  }
});
