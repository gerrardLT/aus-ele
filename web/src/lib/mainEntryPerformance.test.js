import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('main entry lazy-loads route root pages behind Suspense', () => {
  const source = fs.readFileSync(path.resolve(__dirname, '../main.jsx'), 'utf8');

  // 2026-08-20：App.jsx 单体已拆分为按路由 lazy 页面（漏斗化重构），断言同步更新
  assert.match(source, /lazy\(\(\) => import\('\.\/pages\/MarketPage\.jsx'\)\)/);
  assert.match(source, /lazy\(\(\) => import\('\.\/pages\/FinlandPage\.jsx'\)\)/);
  assert.match(source, /lazy\(\(\) => import\('\.\/pages\/FingridPage\.jsx'\)\)/);
  assert.match(source, /lazy\(\(\) => import\('\.\/pages\/DeveloperPortalPage\.jsx'\)\)/);
  assert.match(source, /<Suspense fallback=\{<BootFallback \/>}/);
});
