// web/src/lib/r3NavGuards.test.js
// R3（URL 可分享 / SPA 导航 / ⌘K / 移动抽屉）的结构守卫（2026-09-06）。
//
// 为什么这一批要的是「读源码断言」而不是渲染测试：R3 最容易坏掉的三件事都不是行为，
// 而是**结构前提**——
// 1. CommandPalette 一旦被谁顺手改成静态 import，面板照常工作、测试照常绿，只有入口
//    体积悄悄涨上去（预算只剩 6%）。只有查 import 形态才能拦住。
// 2. 抽屉/面板各自抄一份导航表，今天看不出问题，等侧边栏加一个页面就是「手机上少一项」。
// 3. nginx 的 SPA fallback 是深链能打开的前提；它是部署文件，不在任何前端测试的视野里，
//    被改掉的表现是「刷新 /finland 出 404」而本地 dev server 一切正常。
//
// 另有两条是被既有断言反向约束的：analytics.test.js:303 锁死 capture 的消费者集合，
// 以及 Spec §126 规定 filterReducer/initialState/toQueryParams 一律不动。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC = path.resolve(__dirname, '..');            // web/src
const WEB = path.resolve(SRC, '..');                  // web
const REPO = path.resolve(WEB, '..');                 // 仓库根（deploy/、backend/ 在这里）

function readSrc(...segments) {
  return fs.readFileSync(path.join(SRC, ...segments), 'utf8');
}

function readRepo(...segments) {
  return fs.readFileSync(path.join(REPO, ...segments), 'utf8');
}

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
      walk(full, out);
    } else if (/\.jsx?$/.test(entry.name)) {
      out.push(full);
    }
  }
  return out;
}

const ALL_SRC = walk(SRC);

test('command palette is reachable only through a dynamic import', () => {
  // Spec §129「必须动态 import（不进 entry chunk）」。静态 import 的表现不是报错而是体积上涨，
  // 所以这里查的是全部 src，而不是只看 AppChrome 一处 —— 任何人随时都能再加一条。
  const statics = [];
  for (const file of ALL_SRC) {
    const source = fs.readFileSync(file, 'utf8');
    for (const m of source.matchAll(/^\s*import[^;\n]*?from\s+['"]([^'"]*CommandPalette(?:\.jsx)?)['"]/gm)) {
      statics.push(`${path.relative(REPO, file)} -> ${m[1]}`);
    }
  }
  assert.deepEqual(statics, [], `CommandPalette 被静态 import：${statics.join('; ')}`);
  assert.match(readSrc('components', 'AppChrome.jsx'), /lazy\(\(\)\s*=>\s*import\(['"]\.\/CommandPalette\.jsx['"]\)\)/);
});

test('app chrome stays out of the entry chunk', () => {
  // 抽屉本身很小，但它静态引入 SidebarNavigation（framer-motion）。一旦 main.jsx 改成静态
  // import，motion 就会进入首屏关键路径 —— 而入口预算是本站最紧的约束。
  const main = readSrc('main.jsx');
  assert.doesNotMatch(main, /^\s*import\s+\S+\s+from\s+['"]\.\/components\/AppChrome\.jsx['"]/m);
  assert.match(main, /const AppChrome = lazy\(\(\)\s*=>\s*import\(['"]\.\/components\/AppChrome\.jsx['"]\)\)/);
});

test('new r3 chrome does not emit analytics events', () => {
  // analytics.test.js:303 断言 capture 的消费者集合恰好是 ['lib/onboarding.js','main.jsx']。
  // 面板/抽屉里加埋点会把那个集合撑破（硬门直接红），更要紧的是会给同一页面制造第二份事件。
  for (const file of ['components/AppChrome.jsx', 'components/CommandPalette.jsx', 'components/MobileNavDrawer.jsx', 'lib/apiIndex.js', 'lib/routeStore.js', 'lib/urlState.js']) {
    assert.doesNotMatch(readSrc(...file.split('/')), /\bcapture\(/, `${file} 不得调用 capture()`);
    assert.doesNotMatch(readSrc(...file.split('/')), /\bidentify\(/, `${file} 不得调用 identify()`);
  }
});

test('page_view is emitted from the route subscription, not from a mount effect', () => {
  // R3.3 之前 page_view 挂在页面挂载上；变成 SPA 之后挂载只发生一次，
  // 表现为「PV 永远只有首页那一条」，而所有页面组件看起来都正常。
  const main = readSrc('main.jsx');
  assert.match(main, /subscribeRoute|useRoute\(\)/, 'main.jsx 必须订阅路由变化');
  assert.match(main, /capture\('page_view'/);
  assert.match(main, /key=\{route\.page\}/, '切页必须重挂载，否则页面级 useEffect 不重跑');
});

test('the drawer and the palette reuse the sidebar nav table instead of copying it', () => {
  // 导航表出现第二份的结局是可以预见的：侧边栏加一个页面，抽屉里少一个，而不会有任何测试红。
  for (const file of ['components/MobileNavDrawer.jsx', 'components/CommandPalette.jsx']) {
    const source = readSrc(...file.split('/'));
    assert.match(source, /import\s*\{[^}]*\bnavItems\b[^}]*\}\s*from\s*'\.\/SidebarNavigation\.jsx'/, `${file} 必须复用 navItems`);
    // 自己列页面路径 = 抄了第二份表
    const ownTable = [...source.matchAll(/path:\s*['"]\/[a-z-]+['"]/g)].map((m) => m[0]);
    assert.deepEqual(ownTable, [], `${file} 里出现自造的导航路径：${ownTable.join(', ')}`);
  }
});

test('sidebar links keep real hrefs so removing the onClick is a full rollback', () => {
  // Spec §128：只加 onClick 拦截，保留 <a href>。若哪天有人把 href 换成 href="#" + onClick
  // 跳转，flag 关掉就等于导航全废 —— 回滚语义必须是「删掉增强，原行为完整」。
  const sidebar = readSrc('components', 'SidebarNavigation.jsx');
  assert.match(sidebar, /href=\{(?:item\.path|href|entry\.path)\}/);
  assert.doesNotMatch(sidebar, /href="#"/, '占位 href 会让禁用 JS 与关 flag 两种情况同时失效');
  // §130：不得改断点（finlandBoard.test.js:698-702 锁触控尺寸与 focus-visible）
  assert.match(sidebar, /max-\[1100px\]:hidden/, '侧边栏断点必须保持原样');
});

test('mobile drawer is the mirror-image breakpoint and keeps a11y basics', () => {
  const drawer = readSrc('components', 'MobileNavDrawer.jsx');
  // 与侧边栏互斥：两者若在同一断点同时可见，会同时出现两个「菜单」入口。
  assert.match(drawer, /min-\[1100px\]:hidden/);
  for (const needle of ['role="dialog"', 'aria-modal', 'aria-label', 'aria-expanded', 'aria-controls', 'Escape', 'focus-visible:outline']) {
    assert.ok(drawer.includes(needle), `抽屉缺少可达性基线：${needle}`);
  }
  // 44px 命中区：与 SidebarNavigation 被锁死的触控规格同一档
  assert.match(drawer, /min-h-\[44px\]/);
  assert.match(drawer, /min-w-\[44px\]/);
});

test('url sync writes with replaceState and restores through dispatch', () => {
  const hook = readSrc('hooks', 'useUrlFilterSync.js');
  // pushState 会让「每点一个筛选器就多一条历史记录」，后退键于是变成踩雷。
  // 只查调用形态：注释里本来就该留着「不是 pushState」这句话。
  assert.match(hook, /replaceState\s*\?\.\(/);
  assert.doesNotMatch(hook, /pushState\s*(\?\.)?\(/, '筛选器同步不得新增历史记录');
  // 恢复必须喂给真 reducer：setFilter 会绕开 region→market 推导，抄出第二份规则。
  assert.match(hook, /dispatch\s*\?\.\(action\)/);
  assert.doesNotMatch(hook, /setFilter\s*\(/, '不得用 setFilter 恢复 URL 状态');
  // flag 必须是参数而不是条件调用 hook —— 后者违反 React hook 顺序硬约束，直接崩。
  assert.match(hook, /enabled\s*=\s*true/);
});

test('spa navigation hands the click back to the browser when it declines', () => {
  // 渐进增强的定义：增强判定不该接手时，原行为必须完整可用。
  // 所以判据不是「不许 preventDefault」（接管成功时不 preventDefault 就会双跳），
  // 而是「必须且只能在接管成功后」—— 无条件 preventDefault 是这里唯一真正危险的写法。
  const sidebar = readSrc('components', 'SidebarNavigation.jsx');
  const body = /export function interceptNavClick\(event, href\)\s*\{([\s\S]*?)\n\}/.exec(sidebar);
  assert.ok(body, '找不到 interceptNavClick —— 本测试的前提已变化，请同步改写而非删除');
  assert.match(body[1], /shouldInterceptClick/);
  assert.match(body[1], /if\s*\(\s*navigateRoute\([^)]*\)\s*\)\s*event\.preventDefault\(\)/, 'preventDefault 必须以接管成功为条件');
  assert.doesNotMatch(body[1], /^\s*event\.preventDefault\(\)/m, '不得出现无条件的 preventDefault');
});

test('the openapi index is served under /api because nginx and vite only forward that prefix', () => {
  // 判据：deploy/nginx/default.conf 只有 `location /api/` 代理后端，`location /` 是 SPA fallback。
  // 用 FastAPI 自带的 /openapi.json 会得到 index.html → JSON.parse 抛错 → 面板只剩页面项，
  // 属于「功能缺失但不报错」最难发现的那一类。
  const nginx = readRepo('deploy', 'nginx', 'default.conf');
  assert.match(nginx, /location\s+\/api\//);
  assert.match(nginx, /try_files\s+\$uri\s+\$uri\/\s+\/index\.html;/);
  const health = readRepo('backend', 'routes', 'health.py');
  assert.match(health, /@router\.get\("\/api\/openapi\.json"\)/, '后端必须显式挂这条路由');
  // 前端不得绕过派生函数自己拼串：那样 base 配置一改就会出现「页面能用、面板搜到的端点 404」
  const palette = readSrc('components', 'CommandPalette.jsx');
  assert.match(palette, /openapiIndexUrl\(/, '索引 URL 必须由 openapiIndexUrl() 从 apiBase 派生');
  assert.doesNotMatch(palette, /['"`][^'"`]*openapi\.json['"`]/, '不得出现硬编码的 openapi.json 字面量');
});

test('r3 flags default to off so every piece of new ui is a zero-code rollback', () => {
  // Spec §160：flag 前置，作为 R3/R4/R5 全部新 UI 的回滚开关。
  const flags = readSrc('lib', 'flags.js');
  for (const key of ['urlFilters', 'spaNav', 'commandPalette', 'mobileNavDrawer']) {
    const block = new RegExp(`${key}:\\s*\\{[\\s\\S]*?\\}`).exec(flags);
    assert.ok(block, `flag ${key} 不存在`);
    assert.match(block[0], /default:\s*false/, `flag ${key} 必须默认关闭`);
    assert.match(block[0], /envKey:\s*'VITE_[A-Z_]+_UI'/, `flag ${key} 缺 envKey`);
  }
});

test('the filter layer contract that r3.1 forbids touching is still intact', () => {
  // Spec §126：filterReducer / initialState / toQueryParams 一律不动，URL 层只复用它们。
  const ctx = readSrc('contexts', 'FilterContext.jsx');
  for (const name of ['function filterReducer(', 'const initialState', 'function toQueryParams(']) {
    const count = ctx.split(name).length - 1;
    assert.equal(count, 1, `${name} 必须仍是唯一一份`);
  }
  // 新代码不得往 FilterContext 里塞第二套筛选状态（走 useUrlFilterSync）
  assert.match(ctx, /useUrlFilterSync|URL_STATE_ENABLED/);
});

test('no second answer for the app language', () => {
  // 既有三个页面各自有 `const [lang, setLang]` 形态并被 finlandPage.test.js:96-107 锁死，
  // 所以新代码走 lib/appLang.js 读，而不是去重构那些页面。
  const appLang = readSrc('lib', 'appLang.js');
  assert.match(appLang, /export function readAppLang/);
  assert.match(appLang, /app_lang/, '必须复用既有 localStorage 键（legalReachability.test.js 已披露它）');
  const chrome = readSrc('components', 'AppChrome.jsx');
  assert.match(chrome, /readAppLang/);
});
