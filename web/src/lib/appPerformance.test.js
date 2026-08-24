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

test('heavy market modules are lazy-registered in ModuleRenderer so they mount on demand', () => {
  // 2026-08-20：App.jsx 的 DeferredSection 包裹已迁移为 ModuleRenderer 的 React.lazy 注册
  //（阶段 Tab 切换时才触发 import），归属文件同步更新
  const source = fs.readFileSync(path.resolve(__dirname, '../components/funnel/ModuleRenderer.jsx'), 'utf8');

  assert.match(source, /lazy\(/);

  for (const moduleName of [
    'GridForecast',
    'PeakAnalysis',
    'FcasAnalysis',
    'ChargingWindow',
    'CycleCost',
    'InvestmentAnalysis',
  ]) {
    const pattern = new RegExp(`${moduleName}: lazy\\(`);
    assert.match(source, pattern, `${moduleName} should be lazy-registered in ModuleRenderer`);
  }
});
