// web/src/lib/analytics.test.js
// R5.1/R5.3 前端采集的门（2026-09-06）。
//
// 最值得守住的三条，都是「默认看起来没事、出事才知道严重」的那类：
//   · flag 关闭时是否真的零副作用（不注入 script、不发请求）—— 这决定了「未告知即不采集」
//     这句法务承诺是不是真的；
//   · 回放遮蔽是否是不可绕过的硬门 —— 本平台界面里全是项目名与财务数字，录到就是泄露；
//   · 事件属性是否白名单化 —— 一旦有人把查询文本传进 props，用户输入就会长期留在第三方处。
// SDK 用注入 script 的方式加载（不是 import），所以这些断言都在假 doc + 假全局句柄上做。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  analyticsStatus,
  capture,
  identify,
  initAnalytics,
  isAnalyticsEnabled,
  isRecordingEnabled,
  resetAnalyticsForTest,
  resetIdentity,
} from './analytics.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, '..');
const WEB_ROOT = path.resolve(__dirname, '../..');
const MODULE_SOURCE = fs.readFileSync(path.join(__dirname, 'analytics.js'), 'utf8');

const ON = {
  VITE_ANALYTICS_ENABLED: 'true',
  VITE_ANALYTICS_SDK_URL: 'https://cdn.example.test/array.js',
  VITE_ANALYTICS_TOKEN: 'phc_public_demo',
  VITE_ANALYTICS_HOST: 'https://ingest.example.test',
};

function walk(dir, out = []) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const abs = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(abs, out);
    else out.push(abs);
  }
  return out;
}

function rel(abs) {
  return path.relative(SRC_ROOT, abs).split(path.sep).join('/');
}

/** 假 DOM：只记录被插入的标签，够用即可（不引 jsdom，为了 node --test 能直跑）。 */
function makeDoc() {
  const doc = {
    injected: [],
    createElement(tag) {
      const el = { tag, onload: null, onerror: null };
      return el;
    },
  };
  doc.head = { appendChild: (el) => doc.injected.push(el) };
  doc.body = { appendChild: (el) => doc.injected.push(el) };
  return doc;
}

/** 假 SDK 句柄：init/capture/identify/reset 全部记账，供断言核对。 */
function makeProvider() {
  const calls = { init: [], capture: [], identify: [], reset: 0 };
  const provider = {
    init: (token, opts) => calls.init.push([token, opts]),
    capture: (event, props) => calls.capture.push([event, props]),
    identify: (id, traits) => calls.identify.push([id, traits]),
    reset: () => { calls.reset += 1; },
  };
  return { provider, calls };
}

function withProvider(fn) {
  const { provider, calls } = makeProvider();
  globalThis.posthog = provider;
  try {
    return fn(calls);
  } finally {
    delete globalThis.posthog;
  }
}

test('disabled analytics produce zero side effects', () => {
  resetAnalyticsForTest();
  for (const env of [{}, undefined, { VITE_ANALYTICS_ENABLED: 'false' }, { VITE_ANALYTICS_ENABLED: '1' }]) {
    assert.equal(isAnalyticsEnabled(env), false, `关闭判据不成立：${JSON.stringify(env)}`);
    const doc = makeDoc();
    assert.equal(initAnalytics(env, { doc }), 'disabled');
    assert.deepEqual(doc.injected, [], '未启用时不得注入任何第三方 script');
    assert.equal(capture('page_view', { page: 'nem' }, env), false);
    assert.equal(identify('pr_1', null, env), false);
    assert.equal(resetIdentity(env), false);
    const status = analyticsStatus();
    assert.equal(status.queued, 0, '关闭态不应累积队列（内存里留着用户行为等于偷偷采集）');
    assert.equal(status.sent, 0);
  }
});

test('the SDK is never bundled into the entry chunk', () => {
  // Spec §156 的硬约束：未启用时页面上不该出现任何第三方代码，且 entry 体积不能被 SDK 吃掉。
  assert.doesNotMatch(MODULE_SOURCE, /^\s*import[^\n]*from\s*['"](posthog|@posthog|matomo|plausible)/m,
    'analytics.js 不得静态 import 分析 SDK');
  assert.ok(MODULE_SOURCE.includes("document.createElement('script')"), 'SDK 应通过 script 注入加载');
  const pkg = JSON.parse(fs.readFileSync(path.join(WEB_ROOT, 'package.json'), 'utf8'));
  const deps = { ...pkg.dependencies, ...pkg.devDependencies };
  for (const name of Object.keys(deps)) {
    assert.ok(!/posthog|matomo|plausible|amplitude|segment/i.test(name), `分析 SDK 不应成为 npm 依赖：${name}`);
  }
});

test('enabled but under-configed: nothing is sent and nothing throws', () => {
  resetAnalyticsForTest();
  const doc = makeDoc();
  // 只有开关、没有 URL/token —— 必须安静地不工作，而不是每次 capture 报错
  assert.equal(initAnalytics({ VITE_ANALYTICS_ENABLED: 'true' }, { doc }), 'unconfigured');
  assert.deepEqual(doc.injected, []);
  assert.equal(capture('page_view', { page: 'agent' }, { VITE_ANALYTICS_ENABLED: 'true' }), false);
  assert.equal(analyticsStatus().queued, 0, '半截配置下入队等于把用户行为长期留在内存里');
  // 配了 URL 缺 token 同理：半截配置不应发起跨域请求
  const doc2 = makeDoc();
  assert.equal(initAnalytics({ VITE_ANALYTICS_ENABLED: 'true', VITE_ANALYTICS_SDK_URL: ON.VITE_ANALYTICS_SDK_URL }, { doc: doc2 }), 'unconfigured');
  assert.deepEqual(doc2.injected, []);
});

test('init injects exactly one async script and honours masking at init time', () => {
  resetAnalyticsForTest();
  withProvider((calls) => {
    const doc = makeDoc();
    initAnalytics(ON, { doc });
    assert.equal(doc.injected.length, 1, 'init 必须幂等，只注入一个 script');
    initAnalytics(ON, { doc });
    assert.equal(doc.injected.length, 1);
    const [script] = doc.injected;
    assert.equal(script.src, ON.VITE_ANALYTICS_SDK_URL);
    assert.equal(script.async, true);
    script.onload();
    assert.equal(calls.init.length, 1);
    const [token, opts] = calls.init[0];
    assert.equal(token, ON.VITE_ANALYTICS_TOKEN);
    assert.equal(opts.api_host, ON.VITE_ANALYTICS_HOST);
    // capture_pageview 必须显式 false：默认值随 SDK 版本变动 = 静默扩采
    assert.equal(opts.capture_pageview, false);
    // 遮蔽参数在这里再声明一次：后台开了录制，前端不带遮蔽就不录
    assert.equal(opts.mask_all_text, false);
    assert.equal(opts.mask_all_inputs, false);
    assert.equal(opts.autocapture, false);
  });
  resetAnalyticsForTest();
});

test('session replay is refused unless both masking switches are on', () => {
  const base = { ...ON, VITE_ANALYTICS_SESSION_REPLAY: 'true' };
  assert.equal(isRecordingEnabled(base), false, '无遮蔽的回放必须被拒绝（Spec §159）');
  for (const partial of [
    { VITE_ANALYTICS_MASK_ALL_TEXT: 'true' },
    { VITE_ANALYTICS_MASK_ALL_INPUTS: 'true' },
  ]) {
    assert.equal(isRecordingEnabled({ ...base, ...partial }), false, `半个遮蔽开关不算遮蔽：${JSON.stringify(partial)}`);
  }
  const full = { ...base, VITE_ANALYTICS_MASK_ALL_TEXT: 'true', VITE_ANALYTICS_MASK_ALL_INPUTS: 'true' };
  assert.equal(isRecordingEnabled(full), true);
  // 父开关关掉，遮蔽齐全也不录
  assert.equal(isRecordingEnabled({ ...full, VITE_ANALYTICS_ENABLED: 'false' }), false);

  resetAnalyticsForTest();
  withProvider((calls) => {
    const doc = makeDoc();
    initAnalytics(full, { doc });
    doc.injected[0].onload();
    const [, opts] = calls.init[0];
    assert.equal(opts.autocapture, true);
    assert.equal(opts.mask_all_text, true);
    assert.equal(opts.mask_all_inputs, true);
  });
  resetAnalyticsForTest();
});

test('events raised before the SDK is ready are flushed once, in order', () => {
  resetAnalyticsForTest();
  withProvider((calls) => {
    const doc = makeDoc();
    initAnalytics(ON, { doc });
    // SDK 还没 onload：先入有界队列
    assert.equal(capture('agent_run_started', { market: 'NEM' }, ON), true);
    assert.equal(analyticsStatus().queued, 1);
    assert.equal(calls.capture.length, 0, '未就绪时不得直接调 provider');
    doc.injected[0].onload();
    assert.equal(analyticsStatus().queued, 0);
    assert.deepEqual(calls.capture.map((c) => c[0]), ['agent_run_started']);
    // 就绪后直发
    capture('agent_run_completed', { duration_s: 12 }, ON);
    assert.equal(calls.capture.length, 2);
    assert.equal(calls.capture[1][0], 'agent_run_completed');
  });
  resetAnalyticsForTest();
});

test('the pending queue is bounded and a failed load drops it', () => {
  resetAnalyticsForTest();
  const doc = makeDoc();
  initAnalytics(ON, { doc });
  for (let i = 0; i < 80; i += 1) capture(`evt_${i}`, { index: i }, ON);
  const status = analyticsStatus();
  assert.equal(status.queued, 50, '队列必须有上限，否则无限滚动的页面会吃光内存');
  assert.equal(status.dropped, 30);
  // 加载失败（广告拦截器是常态）：降级为不采集，不重试、不清空后重新膨胀
  withProvider(() => {
    doc.injected[0].onerror();
    assert.equal(analyticsStatus().status, 'unavailable');
    assert.equal(analyticsStatus().queued, 0);
    assert.equal(capture('evt_after_failure', null, ON), false);
  });
  resetAnalyticsForTest();
});

test('event properties are allowlisted: user content cannot ride along', () => {
  resetAnalyticsForTest();
  withProvider((calls) => {
    const doc = makeDoc();
    initAnalytics(ON, { doc });
    doc.injected[0].onload();
    const props = {
      market: 'NEM',                       // 留：枚举值
      plan: 'growth',                      // 留：枚举值
      runs: 3,                             // 留（数字）
      co_optimized: true,                  // 留（布尔）
      page_view_s: 12.5,                   // 留（数值型指标）
      query: 'Battery bidding strategy for Project Kohinoor',  // 丢：key 命中自由文本黑名单
      search_text: 'IRR',                                    // 丢
      project_name: 'Kohinoor South',                        // 丢（两段都命中）
      note: 'line1\nline2',                                  // 丢：key + 换行
      long_value: 'x'.repeat(200),                           // 丢：超长
      owner_email: 'a@b.test',                               // 丢：key 含 email
      nested: { a: 1 },                                      // 丢：非标量
      list: [1, 2],                                          // 丢：非标量
      'bad key!': 'x',                                       // 丢：key 含非法字符
      '': 'x',                                               // 丢：空 key
    };
    capture('search_performed', props, ON);
    const [, sent] = calls.capture[0];
    assert.deepEqual(Object.keys(sent).sort(), ['co_optimized', 'market', 'page_view_s', 'plan', 'runs']);
    for (const gone of ['query', 'search_text', 'project_name', 'note', 'long_value', 'owner_email',
      'nested', 'list', 'bad key!', '']) {
      assert.ok(!(gone in sent), `属性 ${gone} 应被丢弃`);
    }
  });
  resetAnalyticsForTest();
});

test('identity uses our principal id and never an email address', () => {
  resetAnalyticsForTest();
  withProvider((calls) => {
    const doc = makeDoc();
    initAnalytics(ON, { doc });
    doc.injected[0].onload();
    assert.equal(identify('user@example.com', null, ON), false, '含 @ 的标识必须被拒绝');
    assert.equal(identify('', null, ON), false);
    assert.equal(identify(null, null, ON), false);
    assert.equal(identify('pr_9f2c', { workspace_count: 2, email: 'leak@example.com' }, ON), true);
    assert.deepEqual(calls.identify, [['pr_9f2c', { workspace_count: 2 }]]);
    assert.equal(calls.identify[0][1].email, undefined, 'traits 同样走白名单');
    assert.equal(resetIdentity(ON), true);
    assert.equal(calls.reset, 1);
  });
  resetAnalyticsForTest();
});

test('capture never throws when the provider misbehaves', () => {
  resetAnalyticsForTest();
  globalThis.posthog = {
    init() { throw new Error('boom'); },
    capture() { throw new Error('boom'); },
  };
  try {
    const doc = makeDoc();
    initAnalytics(ON, { doc });
    assert.doesNotThrow(() => doc.injected[0].onload(), 'SDK 初始化异常不能冒到业务调用栈');
    assert.equal(analyticsStatus().status, 'ready');
    assert.equal(capture('page_view', { page: 'pricing' }, ON), false, 'provider 抛错时返回 false 而不是抛出');
  } finally {
    delete globalThis.posthog;
    resetAnalyticsForTest();
  }
});

test('onboarding is the only place step events are raised (single-point wiring)', () => {
  // Spec §156 要求采集挂在 onboarding.js 的状态写入处，而不是散在各页面：散了就会重复上报
  // 或漏报，而「激活」指标正是按步骤完成算的。这里锁住接入点的收敛性。
  const consumers = walk(SRC_ROOT)
    .filter((f) => /\.jsx?$/.test(f))
    .filter((f) => !f.endsWith('.test.js'))
    .filter((f) => !rel(f).includes('__tests__'))
    .filter((f) => rel(f) !== 'lib/analytics.js')
    .filter((f) => /(?:^|[^.\w])capture\s*\(\s*['"]/.test(fs.readFileSync(f, 'utf8').replace(/^\s*\/\/.*$/gm, '')))
    .map((f) => rel(f))
    .sort();
  assert.deepEqual(consumers, ['lib/onboarding.js', 'main.jsx'],
    '新增埋点位点必须谨慎：每多一处，就多一份「同一个事件被两条路径以不同口径上报」的风险');

  const onboarding = fs.readFileSync(path.join(SRC_ROOT, 'lib/onboarding.js'), 'utf8');
  assert.match(onboarding, /export function markOnboardingStep[\s\S]*?capture\('onboarding_step_completed'/,
    '步骤事件必须挂在状态写入之后（事件与状态同源）');
});
