import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('FcasAnalysis uses DataQualityBadge for WEM preview-grade signalling', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');
  assert.match(source, /DataQualityBadge/);
  assert.match(source, /sectionMetadata/);
  assert.match(source, /previewCaveat/);
});

test('FcasAnalysis preserves empty-state and no-data branches', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');
  assert.match(source, /t\.fcasNoData/);
  assert.match(source, /t\.noData/);
});

test('FcasAnalysis surfaces incremental revenue viability fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');
  assert.match(source, /net_incremental_revenue_k/);
  assert.match(source, /opportunity_cost_k/);
  assert.match(source, /viable_service_count/);
  assert.match(source, /incremental_revenue_positive/);
});

test('FcasAnalysis exposes WEM preview scoring signals', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');
  assert.match(source, /scarcity_score/);
  assert.match(source, /opportunity_score/);
  assert.match(source, /quality_score/);
  assert.match(source, /preview_caveat/);
});

test('FcasAnalysis centralizes preview and viability copy through translation keys', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FcasAnalysis.jsx'), 'utf8');
  assert.match(source, /t\.fcasPreviewNotInvestmentGrade/);
  assert.match(source, /t\.fcasViabilityPositive/);
  assert.match(source, /t\.fcasViabilityNegative/);
  assert.equal(source.includes("lang === 'zh'"), false);
});
