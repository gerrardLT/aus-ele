// 改名 / 重构集中自检靶（R0.2，2026-09-05 公测产品化改造）
//
// 用途：本文件不新增任何约束，只是把散落在各测试里的「读源码字面量断言」集中
// 复述一遍，作为品牌改名（天枢 / Dubhe）与结构重构前的单一自检入口。
//
// 为什么值得单独立一个靶：CI 里唯一硬阻断门是 `node --test src/lib/*.test.js`
// （见 .github/workflows/ci.yml），而后端 unittest / vitest / ESLint / 体积预算
// 全为 `|| echo` 非阻断。改 `backend/server.py` 的决策字符串、改 `translations.js`
// 结构、改 `index.css` token、改 `main.jsx` lazy 串，都会以「前端测试红」的形式
// 阻断发布，但报错点分散在 5 个文件里。此处集中列出，命中即知是哪一条锁链断了。
//
// 维护纪律：本文件的断言必须与来源测试保持同义。若来源测试改了，这里同步改；
// 若这里想加新断言，必须先确认它对应某个真实存在的来源测试，不得凭空收紧。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

const repoRoot = path.resolve(__dirname, '../../..');

function readSource(relativeFromRepoRoot) {
  return fs.readFileSync(path.join(repoRoot, relativeFromRepoRoot), 'utf8');
}

// ── 1. backend/server.py：P3 决策与 grade 语义 ────────────────────────────
// 来源：web/src/lib/aemoConvergence.test.js:33-40、web/src/lib/aemoDecisionClosure.test.js:13-27
// 含义：这两组断言把「契约字符串」锁死在后端 served 文本里。b3 死副本清理（2026-09-06）
//       后真源分布在 server.py 与 routes/*.py（Reserve Opportunity → fcas_routes、
//       Market Entry Readiness → investment_routes），扫描范围随真源扩成合集；
//       品牌改名绝不搬动这些字面量，后续拆分时跟随真源同步范围。
const SERVER_LOCKED_STRINGS = [
  'Reserve Opportunity',
  'Market Entry Readiness',
  'decision-grade',
  'preview_only',
  'recommendation_summary',
  'explanation_chain',
  'risk_boundary',
  'value_stream_coverage',
  'readiness_status',
];

test('renameGuard: backend served modules keep the 9 contract strings locked by frontend tests', () => {
  // b3（2026-09-06）：扫描范围从 server.py 单文件扩成 server.py + routes/*.py 合集，
  // 与 aemoConvergence 的同义迁移一致 —— 字符串必须存在于某个 served 模块。
  const backendRoot = path.join(repoRoot, 'backend');
  const targets = ['server.py',
    ...fs.readdirSync(path.join(backendRoot, 'routes')).filter((f) => f.endsWith('.py')).map((f) => `routes/${f}`)];
  const source = targets.map((rel) => fs.readFileSync(path.join(backendRoot, rel), 'utf8')).join('\n');
  for (const literal of SERVER_LOCKED_STRINGS) {
    assert.ok(
      source.includes(literal),
      `后端 served 模块（server.py + routes/）丢失了被前端测试锁死的字面量：${literal}（改名/拆分前先看 aemoConvergence.test.js 与 aemoDecisionClosure.test.js）`,
    );
  }
});

// ── 2. backend/agent/prompts.py：AEMO 作为数据源名必须保留 ────────────────
// 来源：tests/test_agent_orchestrator.py:548 断言 assertIn("AEMO", SYSTEM_PROMPT)
// 含义：品牌改名不得删光 AEMO 字样 —— 产品品牌名与数据源名必须区分（这也正是法务正解）。
test('renameGuard: agent system prompt still references AEMO as a data source name', () => {
  const source = readSource('backend/agent/prompts.py');
  assert.match(source, /AEMO/);
});

// ── 3. translations.js：字面语句结构不得重构 ──────────────────────────────
// 来源：web/src/lib/finlandBoard.test.js:740-750
// 含义：不能拆文件、不能改 `translations.zh.xxx = {` 的赋值形态、不能上 i18next。
test('renameGuard: translations.js keeps the assignment shape locked by finlandBoard', () => {
  const source = readSource('web/src/translations.js');
  assert.match(source, /translations\.zh\.nav = \{/);
  assert.match(source, /finland:/);
  assert.match(source, /translations\.zh\.finlandBoard = \{/);
  assert.match(source, /translations\.en\.finlandBoard = \{/);
  assert.match(source, /chartGallery/);
});

// ── 4. index.css：语义 token 与字体配对 ──────────────────────────────────
// 来源：web/src/lib/finlandBoard.test.js:680-696
// 含义：token 收敛只能「新增语义别名层映射到既有 token」，两套旧命名一律保留；
//       字体禁用 Inter / Playfair Display（注意 /Inter/ 是宽松匹配，含 "Interactive"
//       这类子串同样会让来源测试红 → 新增 CSS 注释与 class 名需避开该子串）。
test('renameGuard: index.css keeps semantic surface tokens and the locked font pairing', () => {
  const source = readSource('web/src/index.css');
  for (const token of ['--color-background:', '--color-panel:', '--color-surface:', '--color-surface-hover:']) {
    assert.ok(source.includes(token), `index.css 缺少语义 token：${token}`);
  }
  assert.match(source, /Archivo/);
  assert.match(source, /Source Serif 4/);
  assert.doesNotMatch(source, /Inter/);
  assert.doesNotMatch(source, /Playfair Display/);
});

// ── 5. main.jsx：入口 lazy 串与 Suspense 骨架 ────────────────────────────
// 来源：web/src/lib/mainEntryPerformance.test.js:10-19
// 含义：不引入 react-router 的决定性理由之一。新增页面只允许「三元链末尾加分支 +
//       新增 lazy import」，既有行零改动。
test('renameGuard: main entry still lazy-loads the four route root pages', () => {
  const source = readSource('web/src/main.jsx');
  for (const page of ['MarketPage', 'FinlandPage', 'FingridPage', 'DeveloperPortalPage']) {
    assert.ok(
      source.includes(`lazy(() => import('./pages/${page}.jsx'))`),
      `main.jsx 的 ${page} lazy 串被改动（mainEntryPerformance.test.js 会红）`,
    );
  }
  assert.match(source, /<Suspense fallback=\{<BootFallback \/>}/);
});

// ── 6. vite.config.js：manualChunks 分工 ─────────────────────────────────
// 来源：web/src/lib/viteChunking.test.js:10-18
// 含义：Storybook 不做的理由之一；新依赖不得挤进 entry chunk。
test('renameGuard: vite config keeps dedicated vendor manual chunks', () => {
  const source = readSource('web/vite.config.js');
  assert.match(source, /manualChunks\(id\)/);
  assert.match(source, /id\.includes\('recharts'\)/);
  assert.match(source, /return 'charts-vendor'/);
  assert.match(source, /id\.includes\('react'\) \|\| id\.includes\('scheduler'\)/);
  assert.match(source, /return 'react-vendor'/);
});

// ── 7. PricingPage：产品位主标题必须保留价值陈述 ──────────────────────────
// 来源：web/src/pages/__tests__/pricingPage.test.jsx:15-23（vitest，非阻断门，但 R2 改名会碰）
// 含义：改名后 h1 仍须含「储能市场进入」或「BESS Investment Decision Platform」之一；
//       section.rounded-2xl 恰好 3 个；li.flex 去空后 >9 个。这里只做源码级弱校验，
//       计数级断言留给 vitest（避免在 node:test 里跑 React 渲染）。
test('renameGuard: PricingPage hero copy still carries the value statement', () => {
  const source = readSource('web/src/pages/PricingPage.jsx');
  assert.ok(
    /储能市场进入/.test(source) || /BESS Investment Decision Platform/.test(source),
    'PricingPage 主标题丢失了 pricingPage.test.jsx 锁定的两者之一',
  );
  const sectionCount = source.match(/section className="rounded-2xl"/g) ?? [];
  assert.ok(sectionCount.length <= 3, 'PricingPage 的 rounded-2xl section 模板串不应超过 3 处');
});

// ── 8. FilterBar 相关：筛选标识符黑名单 ──────────────────────────────────
// 来源：web/src/lib/filterToolbarLayout.test.js:15-20
// 含义：新增筛选 UI 时禁止引入这 4 个标识符（它们被判定为「模式切换器反模式」）。
const FILTER_BANNED_IDENTIFIERS = [
  'filterLayoutMode',
  'renderFilterModeSwitcher',
  'renderChartFirstFilters',
  'renderFocusFilters',
];

test('renameGuard: filter layer does not introduce the 4 banned identifiers', () => {
  const files = ['web/src/contexts/FilterContext.jsx', 'web/src/components/FilterBar.jsx'];
  for (const file of files) {
    const source = readSource(file);
    for (const banned of FILTER_BANNED_IDENTIFIERS) {
      assert.ok(!source.includes(banned), `${file} 引入了被 filterToolbarLayout.test.js 禁止的 ${banned}`);
    }
  }
});

// ── 9. 既有文档路径：australiaDocsConsistency 锁定的 5 个文件 ─────────────
// 来源：web/src/lib/australiaDocsConsistency.test.js:12-36
// 含义：新增诊断/任务文档必须入新路径，不得移动或改名这 5 个既有文档；
//       其中 3 篇还被逐句断言（关键短语不得改写）。
test('renameGuard: docs referenced by australiaDocsConsistency still exist and keep locked phrases', () => {
  const locked = [
    'docs/strategy/澳洲首页重排与模块分层建议.md',
    'docs/strategy/澳洲市场垂直化定位与政策驱动改造总纲.md',
    'docs/strategy/政策影响矩阵与模块改造清单.md',
    'docs/strategy/竞品地图与差异化定位建议.md',
    'docs/architecture/项目全面解析总册.md',
  ];
  for (const doc of locked) {
    assert.ok(fs.existsSync(path.join(repoRoot, doc)), `被测试锁定的文档缺失：${doc}`);
  }

  const strategyDoc = readSource('docs/strategy/澳洲市场垂直化定位与政策驱动改造总纲.md');
  assert.ok(strategyDoc.includes('市场进入与收益判断工作台'), '总纲丢失了 finlandBoard 之外另一道锁：市场进入与收益判断工作台');
  assert.ok(
    !strategyDoc.includes('储能运营决策工作台'),
    '总纲出现了旧措辞「储能运营决策工作台」，australiaDocsConsistency 会红',
  );
});

// ── 10. 新增本轮文档：不得与上述锁定路径冲突 ──────────────────────────────
test('renameGuard: this round\'s strategy and task docs are registered in the right subdirectory', () => {
  assert.ok(
    fs.existsSync(path.join(repoRoot, 'docs/strategy/公测商业化缺口诊断与产品化路线-2026-09-05.md')),
    '交付0 诊断文档缺失（AGENTS.md 要求入 docs/strategy/，禁止放 docs/ 顶层）',
  );
  assert.ok(
    fs.existsSync(path.join(repoRoot, 'docs/tasks/任务记录-2026-09-05-产品化改造总体方案.md')),
    '本轮任务记录缺失（AGENTS.md 要求每轮实施进度落 docs/tasks/）',
  );
});
