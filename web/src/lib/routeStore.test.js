// web/src/lib/routeStore.test.js
// R3.3 SPA 导航状态源（2026-09-06）。
//
// 这里最值得测的两件事都是「静默失效」型的：
// 1. 快照引用不稳定 → useSyncExternalStore 无限重渲染（表现为页面卡死，而不是报错）。
// 2. 拦截判据从 DOM 读 `.href` → 拿到绝对 URL → 判「不是站内」→ 永远不接管，
//    而失效现象只是「点了整页刷新」，看起来一切正常。下面专门有一条测这个方向。

import test from 'node:test';
import assert from 'node:assert/strict';

import {
  getRouteSnapshot,
  isInternalHref,
  navigateRoute,
  resetRouteForTests,
  shouldInterceptClick,
  subscribeRoute,
  syncRouteFromLocation,
} from './routeStore.js';

function fakeHistory() {
  const calls = [];
  return {
    calls,
    pushState(state, title, url) { calls.push({ kind: 'push', url }); },
    replaceState(state, title, url) { calls.push({ kind: 'replace', url }); },
  };
}

test('only single-slash root-relative hrefs count as internal', () => {
  assert.equal(isInternalHref('/wem'), true);
  assert.equal(isInternalHref('/'), true);
  // 协议相对 URL 以 / 开头但不是站内路径：接管它等于把外链伪装成内链
  assert.equal(isInternalHref('//evil.example/'), false);
  assert.equal(isInternalHref('https://evil.example/'), false);
  assert.equal(isInternalHref('wem'), false);
  assert.equal(isInternalHref(''), false);
  assert.equal(isInternalHref(undefined), false);
  assert.equal(isInternalHref(42), false);
});

test('click interception is limited to plain left clicks without modifiers', () => {
  const base = { button: 0, currentTarget: { getAttribute: () => null } };
  assert.equal(shouldInterceptClick(base, '/wem'), true);
  assert.equal(shouldInterceptClick({ ...base, metaKey: true }, '/wem'), false, 'Cmd+点击的意图是新标签打开');
  assert.equal(shouldInterceptClick({ ...base, ctrlKey: true }, '/wem'), false);
  assert.equal(shouldInterceptClick({ ...base, shiftKey: true }, '/wem'), false);
  assert.equal(shouldInterceptClick({ ...base, altKey: true }, '/wem'), false);
  assert.equal(shouldInterceptClick({ ...base, button: 1 }, '/wem'), false, '中键同理');
  assert.equal(shouldInterceptClick({ ...base, defaultPrevented: true }, '/wem'), false);
  assert.equal(shouldInterceptClick(null, '/wem'), false);
  const withTarget = { ...base, currentTarget: { getAttribute: (name) => (name === 'target' ? '_blank' : null) } };
  assert.equal(shouldInterceptClick(withTarget, '/wem'), false, '带 target 的链接不得被接管');
});

test('the href judgement uses the caller string, not the resolved DOM property', () => {
  // 这是本文件存在的主要理由：`anchor.href` 是浏览器解析后的绝对 URL。
  // 若判据从 DOM 读，则 `/wem` 变成 `http://host/wem`，startsWith('/') 为 false，
  // 整个 SPA 导航静默失效。currentTarget 这里刻意只提供 getAttribute('href') 的绝对形态。
  const anchor = { getAttribute: (name) => (name === 'href' ? 'http://localhost/wem' : null), href: 'http://localhost/wem' };
  assert.equal(shouldInterceptClick({ button: 0, currentTarget: anchor }, '/wem'), true);
});

test('navigate route writes the query verbatim and reports takeover', () => {
  const history = fakeHistory();
  const previousHistory = globalThis.history;
  globalThis.history = history;
  try {
    assert.equal(navigateRoute('/finland?window=7d'), true);
    assert.equal(history.calls.at(-1).url, '/finland?window=7d');
    // 重复键不得被折叠：Object.fromEntries 只留最后一个，重建 URL 会静默丢数据
    assert.equal(navigateRoute('/reports?tag=a&tag=b'), true);
    assert.equal(history.calls.at(-1).url, '/reports?tag=a&tag=b');
    assert.equal(navigateRoute('https://evil.example/x'), false, '外链不接管');
    assert.equal(navigateRoute('//evil.example/x'), false);
    assert.equal(history.calls.length, 2, '接管失败时不得留下 history 记录');
    assert.equal(navigateRoute('/wem', { replace: true }), true);
    assert.equal(history.calls.at(-1).kind, 'replace');
  } finally {
    globalThis.history = previousHistory;
    resetRouteForTests('/');
  }
});

test('a throwing history api hands the click back to the browser', () => {
  const previousHistory = globalThis.history;
  globalThis.history = { pushState() { throw new Error('SecurityError'); }, replaceState() { throw new Error('SecurityError'); } };
  try {
    assert.equal(navigateRoute('/agent'), false);
  } finally {
    globalThis.history = previousHistory;
  }
});

test('the snapshot object reference is stable until the location really changes', () => {
  // useSyncExternalStore 每帧比对快照；返回新对象等于无限重渲染。
  resetRouteForTests('/finland?window=7d');
  const first = getRouteSnapshot();
  assert.equal(getRouteSnapshot(), first, '同一位置必须返回同一引用');
  resetRouteForTests('/finland?window=7d');
  assert.equal(getRouteSnapshot().href, '/finland');
  assert.deepEqual(getRouteSnapshot().params, { window: '7d' });
});

test('subscribers are notified and one throwing subscriber cannot block the others', () => {
  resetRouteForTests('/');
  const previousHistory = globalThis.history;
  globalThis.history = fakeHistory();
  const seen = [];
  try {
    const unsubscribeA = subscribeRoute(() => { throw new Error('bad subscriber'); });
    subscribeRoute(() => seen.push('b'));
    const changed = navigateRoute('/agent');
    assert.equal(changed, true);
    assert.deepEqual(seen, ['b'], '一个订阅者抛错不得影响其它订阅者');
    unsubscribeA();
    unsubscribeA();  // 重复退订必须无害
  } finally {
    globalThis.history = previousHistory;
    resetRouteForTests('/');
  }
});

test('popstate resync reads the live location', () => {
  const previousLocation = globalThis.location;
  const previousHistory = globalThis.history;
  globalThis.location = { pathname: '/fingrid/317', search: '' };
  globalThis.history = fakeHistory();
  try {
    syncRouteFromLocation();
    assert.equal(getRouteSnapshot().page, 'fingrid');
    assert.deepEqual(getRouteSnapshot().params, { id: '317' });
  } finally {
    globalThis.location = previousLocation;
    globalThis.history = previousHistory;
    resetRouteForTests('/');
  }
});
