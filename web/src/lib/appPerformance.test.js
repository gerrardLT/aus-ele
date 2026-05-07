import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { shouldActivateDeferredSection } from './sectionVisibility.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('shouldActivateDeferredSection only activates when section is visible and not already activated', () => {
  assert.equal(
    shouldActivateDeferredSection({
      isVisible: true,
      hasActivated: false,
    }),
    true,
  );

  assert.equal(
    shouldActivateDeferredSection({
      isVisible: false,
      hasActivated: false,
    }),
    false,
  );

  assert.equal(
    shouldActivateDeferredSection({
      isVisible: true,
      hasActivated: true,
    }),
    false,
  );
});

test('App gates heavy market sections behind deferred visibility mounts', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../App.jsx'), 'utf8');

  assert.match(source, /DeferredSection/);

  for (const moduleName of [
    'GridForecast',
    'PeakAnalysis',
    'FcasAnalysis',
    'BessSimulator',
    'RevenueStacking',
    'ChargingWindow',
    'CycleCost',
    'InvestmentAnalysis',
  ]) {
    const pattern = new RegExp(`<DeferredSection[\\s\\S]*?<${moduleName}[\\s\\S]*?<\\/DeferredSection>`);
    assert.match(source, pattern, `${moduleName} should not mount before its section becomes visible`);
  }
});
