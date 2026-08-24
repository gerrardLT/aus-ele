import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

test('FilterBar keeps a single collapsible filter layout without preview mode switching', () => {
  // 2026-08-20：筛选工具条从 App.jsx 的 renderToolbarFilters 迁移到 FilterBar 组件，
  // 归属文件同步更新；继续禁止布局模式切换回潮
  const source = fs.readFileSync(path.resolve(__dirname, '../components/FilterBar.jsx'), 'utf8');

  assert.match(source, /useFilters/);
  assert.match(source, /translations\[lang\]\?\.filters/);
  assert.doesNotMatch(source, /filterLayoutMode/);
  assert.doesNotMatch(source, /renderFilterModeSwitcher/);
  assert.doesNotMatch(source, /renderChartFirstFilters/);
  assert.doesNotMatch(source, /renderFocusFilters/);
});
