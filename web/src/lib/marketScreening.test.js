import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('App mounts a Market Screening section', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');
  assert.match(source, /MarketScreening/);
  assert.match(source, /sec-screening/);
});

test('MarketScreening component consumes ranked screening fields', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/MarketScreening.jsx'), 'utf8');
  assert.match(source, /overall_score/);
  assert.match(source, /spread_score/);
  assert.match(source, /fcas_or_ess_opportunity_score/);
  assert.match(source, /data_quality_score/);
});

test('MarketScreening centralizes localized copy and avoids inline lang branches', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../components/MarketScreening.jsx'), 'utf8');
  assert.match(source, /const copy = /);
  assert.equal(source.includes("lang === 'zh'"), false);
  assert.equal(source.includes('甯傚満'), false);
  assert.equal(source.includes('褰撳墠'), false);
});
