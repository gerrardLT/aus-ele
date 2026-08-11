import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const docsRoot = path.resolve(__dirname, '../../../docs');

// docs 归类（2026-08-11）：策略类入 strategy/，总册入 architecture/
const australiaDocs = [
  'strategy/澳洲首页重排与模块分层建议.md',
  'strategy/澳洲市场垂直化定位与政策驱动改造总纲.md',
  'strategy/政策影响矩阵与模块改造清单.md',
  'strategy/竞品地图与差异化定位建议.md',
  'architecture/项目全面解析总册.md',
];

test('Australia strategy docs align on the market-entry narrative', () => {
  for (const file of australiaDocs) {
    const source = fs.readFileSync(path.join(docsRoot, file), 'utf8');
    assert.equal(source.includes('储能运营决策工作台'), false, `${file} should not keep the old operating-decision workbench phrasing`);
  }
});

test('Australia strategy docs expose the new homepage chain and WEM asymmetry', () => {
  const homepageDoc = fs.readFileSync(path.join(docsRoot, 'strategy/澳洲首页重排与模块分层建议.md'), 'utf8');
  const strategyDoc = fs.readFileSync(path.join(docsRoot, 'strategy/澳洲市场垂直化定位与政策驱动改造总纲.md'), 'utf8');
  const policyDoc = fs.readFileSync(path.join(docsRoot, 'strategy/政策影响矩阵与模块改造清单.md'), 'utf8');

  assert.match(homepageDoc, /Current Market -> Forward Opportunity Outlook -> Market Entry Conclusion/);
  assert.match(strategyDoc, /市场进入与收益判断工作台/);
  assert.match(strategyDoc, /只有 `Current Market \/ Forward Opportunity Outlook \/ Market Entry Conclusion` 是一级核心/);
  assert.match(policyDoc, /WEM 不应被当作 NEM 的轻量镜像/);
  assert.match(policyDoc, /core-only \/ preview \/ capacity not included/);
});
