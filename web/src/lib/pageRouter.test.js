import test from 'node:test';
import assert from 'node:assert/strict';

import { resolveRootPage, resolveRoute } from './pageRouter.js';

test('resolveRootPage switches to the Fingrid page on /fingrid paths', () => {
  assert.equal(resolveRootPage('/fingrid'), 'fingrid');
  assert.equal(resolveRootPage('/fingrid/317'), 'fingrid');
  assert.equal(resolveRootPage('/'), 'aemo');
});

test('resolveRootPage switches to the Finland page on /finland paths', () => {
  assert.equal(resolveRootPage('/finland'), 'finland');
  assert.equal(resolveRootPage('/finland?window=7d'), 'finland');
  assert.equal(resolveRootPage('/finland/board'), 'finland');
});

// R1.1（2026-09-06）：自助注册与邮箱验证落地页。上面两组断言一行未动 ——
// 新分支一律插在兜底 return 'aemo' 之前，旧链接零失效。
test('resolveRootPage switches to the registration pages on /register and /verify-email', () => {
  assert.equal(resolveRootPage('/register'), 'register');
  assert.equal(resolveRootPage('/verify-email?token=abc'), 'verifyEmail');
  // /reset 属找回密码链路，不能被 /register 前缀抢走（两者只差一个字母）
  assert.equal(resolveRootPage('/reset'), 'forgot');
  assert.equal(resolveRootPage('/login'), 'login');
});

// ---------------------------------------------------------------------------
// R3.2（2026-09-06）：新增 resolveRoute 一层结构化解析。
// 上面三组断言一行未动 —— 本层的兜底仍然是 resolveRootPage 连同它那句 return 'aemo'，
// 所以「已有 URL 的归属页不得改变」是本节第一位的判据（旧链接零失效是硬约束）。
// ---------------------------------------------------------------------------

test('resolveRoute delegates page ownership to resolveRootPage for every branch', () => {
  for (const path of ['/', '/wem', '/finland', '/fingrid', '/developer', '/agent', '/account', '/legal', '/reports', '/help', '/pricing', '/nope']) {
    assert.equal(resolveRoute(path).page, resolveRootPage(path), `归属页与 resolveRootPage 分歧：${path}`);
  }
  // 兜底：未知路径必须仍然落 aemo，而不是 null/404 —— 否则任何旧链接都成白屏
  assert.equal(resolveRoute('/definitely-not-a-page').page, 'aemo');
});

test('resolveRoute splits an embedded query out of the pathname', () => {
  // 调用方可能把整串 location 塞进来（既有 resolveRootPage('/finland?window=7d') 就是这么用的），
  // 所以这里必须自己切分：href 带 query 会让「当前页」判断与 SPA 拦截同时错。
  const route = resolveRoute('/finland?window=7d');
  assert.equal(route.page, 'finland');
  assert.equal(route.href, '/finland');
  assert.deepEqual(route.params, { window: '7d' });
});

test('resolveRoute keeps unknown query keys instead of dropping them', () => {
  // 「一处解析、各页挑自己认识的键」的前提：未知键原样带着。
  // 若在这里过滤，/finland?window=7d 这类页面自带参数会在同步筛选器时被抹掉。
  const route = resolveRoute('/wem', '?region=WEM&custom=keep%20me&flag');
  assert.equal(route.params.custom, 'keep me');
  assert.equal(route.params.flag, '');
  assert.equal(route.params.region, 'WEM');
});

test('resolveRoute exposes in-page sections only from a whitelist', () => {
  assert.equal(resolveRoute('/account/privacy').section, 'privacy');
  assert.equal(resolveRoute('/account/privacy', '?tab=x').section, 'privacy');
  assert.equal(resolveRoute('/legal/dpa').section, 'dpa');
  // 未知子路径不得凭空造一个 tab：回落到该页默认视图（null）比造空页好
  assert.equal(resolveRoute('/account/nonexistent-tab').section, null);
  // fingrid 的第二段是资源 id 而非段落，两件事不混在一起
  assert.equal(resolveRoute('/fingrid/317').section, null);
});

test('account bare path defaults to the overview section', () => {
  assert.equal(resolveRoute('/account').section, 'overview');
  assert.equal(resolveRoute('/legal').section, null, 'legal 没有「默认文档」这回事，交由页面自己选');
});

test('fingrid series id comes from the path and loses to an explicit query', () => {
  assert.deepEqual(resolveRoute('/fingrid/317').params, { id: '317' });
  // query 显式给了 id 时不再从路径补：否则会出现「地址栏写着 ?id=12 却打到 317」
  assert.equal(resolveRoute('/fingrid/317', '?id=12').params.id, '12');
  assert.equal(resolveRoute('/fingrid', '?id=8').params.id, '8');
  assert.equal(resolveRoute('/fingrid').params.id, undefined);
});

test('resolveRoute survives hostile and empty input without throwing', () => {
  for (const input of [undefined, null, '', '/', 'nope', '//evil.example']) {
    assert.doesNotThrow(() => resolveRoute(input), `输入：${JSON.stringify(input)}`);
  }
  // 残缺百分号编码不会让 URLSearchParams 抛错，而是产出一个乱码键（实测 '%%%bad' → {'%%?d':''}）。
  // 这里不假装能过滤它 —— 判据是「乱码键不得伪装成任何已知键」，各页只挑自己认识的名字。
  const route = resolveRoute('/x', '%%%bad');
  assert.equal(route.page, 'aemo');
  for (const key of ['id', 'tab', 'market', 'region', 'year']) {
    assert.ok(!(key in route.params), `残缺编码不得产出已知键 ${key}`);
  }
  assert.equal(resolveRoute('/fingrid', '%%%bad').params.id, undefined);
});
