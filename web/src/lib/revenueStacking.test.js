import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { getDataGradeCaveat, getPreviewModeLabel } from './resultMetadata.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('getPreviewModeLabel localizes WEM preview labels', () => {
  assert.equal(getPreviewModeLabel('single_day_preview', 'zh'), '单日预览');
  assert.equal(getPreviewModeLabel('multi_day_preview', 'en'), 'Multi-day Preview');
  assert.equal(getPreviewModeLabel('', 'en'), 'Preview');
});

test('getDataGradeCaveat explains preview-grade limitations', () => {
  assert.equal(getDataGradeCaveat('preview', 'zh'), '仅供预览，请勿用于项目融资。');
  assert.equal(getDataGradeCaveat('analytical-preview', 'en'), 'Analytical preview only. Do not use for project finance.');
});

test('RevenueStacking uses DataQualityBadge for WEM preview-grade signalling', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');
  assert.match(source, /import DataQualityBadge from '\.\.\/components\/DataQualityBadge'|import DataQualityBadge from '\.\/DataQualityBadge'/);
  assert.match(source, /<DataQualityBadge metadata=\{sectionMetadata\} lang=\{lang\}/);
});

test('RevenueStacking preserves WEM preview empty-state branches', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');
  assert.match(source, /t\.stackNoPreviewData/);
  assert.match(source, /t\.stackNoOverlap/);
  assert.match(source, /t\.noData/);
});

test('RevenueStacking centralizes preview and summary copy through translation keys', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/RevenueStacking.jsx'), 'utf8');
  assert.match(source, /t\.stackLegacyFallback/);
  assert.match(source, /t\.stackPreviewNotInvestmentGrade/);
  assert.match(source, /t\.stackSummaryPeriods/);
  assert.match(source, /t\.stackSummaryArbitrageBase/);
  assert.match(source, /t\.stackSummaryFcasLayers/);
  assert.match(source, /t\.stackSummaryCombined/);
  assert.match(source, /t\.stackPreviewMode/);
  assert.match(source, /t\.stackPreviewDate/);
  assert.match(source, /t\.stackPreviewCombined/);
  assert.equal(source.includes("lang === 'zh'"), false);
});
