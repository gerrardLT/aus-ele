// web/src/lib/methodologyReachability.test.js
// 方法论白皮书「可达 + 陈述仍然为真」门（R6.1，2026-09-06），模式同 legalReachability。
//
// 定价页 Pro 套餐承诺了「方法论白皮书」，而这句话此前没有出处 —— 产品里不存在这份
// 东西。本门锁两类回归：
// 1. 承诺悬空：定价页必须含 /methodology 入口，路由必须真的解析到白皮书页；
// 2. 陈述漂移：白皮书页是 docs/architecture/NEM-BESS收益基准方法论.md 的对外转述，
//    后端实现（benchmark_engine / benchmark_routes / assumptions_registry）才是事实。
//    页面的 methodology_version、coverage_mode、caveat 四条、参考资产三参数全部对着
//    真源核对 —— 改了实现没改白皮书，或改了白皮书没改实现，都在这里变红，而不是
//    等用户拿着页面口径去质疑 API 输出。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { resolveRoute } from './pageRouter.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const SRC_ROOT = path.resolve(__dirname, '..');
const BACKEND_ROOT = path.resolve(__dirname, '../../../backend');
const DATA_ROOT = path.resolve(__dirname, '../../../data');

const PAGE_SOURCE = fs.readFileSync(path.resolve(SRC_ROOT, 'pages/MethodologyPage.jsx'), 'utf8');
const PRICING_SOURCE = fs.readFileSync(path.resolve(SRC_ROOT, 'pages/PricingPage.jsx'), 'utf8');
const ENGINE_SOURCE = fs.readFileSync(path.resolve(BACKEND_ROOT, 'engines/benchmark_engine.py'), 'utf8');
const BENCH_ROUTES_SOURCE = fs.readFileSync(path.resolve(BACKEND_ROOT, 'routes/benchmark_routes.py'), 'utf8');
const REGISTRY = JSON.parse(fs.readFileSync(path.resolve(DATA_ROOT, 'assumptions_registry.json'), 'utf8'));

test('/methodology resolves through the router and legacy routes stay put', () => {
  assert.equal(resolveRoute('/methodology').page, 'methodology');
  // pageRouter 第 2 层的硬约束：新增分支不得改变已有 URL 的归属页。
  assert.equal(resolveRoute('/legal/terms').page, 'legal');
  assert.equal(resolveRoute('/pricing').page, 'pricing');
  assert.equal(resolveRoute('/').page, 'aemo');
});

test('the promised whitepaper is reachable from the page that promises it', () => {
  assert.ok(PRICING_SOURCE.includes('href="/methodology"'),
    '定价页承诺了「方法论白皮书」但缺少 /methodology 入口 —— 承诺再次悬空');
  assert.ok(PAGE_SOURCE.includes('bess_benchmark_v1'), '白皮书页必须标明 methodology_version');
});

test('the version quoted on the page is the version the benchmark API serves', () => {
  const backendVersion = /methodology_version="([^"]+)"/.exec(BENCH_ROUTES_SOURCE)?.[1];
  assert.ok(backendVersion, 'benchmark_routes.py 找不到 methodology_version —— 真源被改名/移除');
  assert.ok(PAGE_SOURCE.includes(backendVersion),
    `白皮书页声称的版本与后端不一致：后端现在是 ${backendVersion}`);
  // meta 行与第 7 节各出现一次；只出现一次说明有一处被改成了别的口径。
  assert.ok((PAGE_SOURCE.match(/bess_benchmark_v1/g) || []).length >= 2,
    '版本号应同时出现在页面 meta 与「版本与维护」一节，两处必须同源');
});

test('the four caveats on the page are verbatim BENCHMARK_CAVEATS from the engine', () => {
  const block = /BENCHMARK_CAVEATS = \[([\s\S]*?)\]/.exec(ENGINE_SOURCE)?.[1];
  assert.ok(block, 'benchmark_engine.py 找不到 BENCHMARK_CAVEATS —— 真源被改名/移除');
  const backendCaveats = [...block.matchAll(/"([^"]+)"/g)].map((m) => m[1]);
  assert.equal(backendCaveats.length, 4, `BENCHMARK_CAVEATS 应为四条，实际 ${backendCaveats.length}`);
  // 页面侧的 CAVEATS 常量必须与后端逐字一致（含顺序）—— caveat 不是可以意译的文案，
  // 它同时出现在每次 API 输出里，两个口径并存时用户无法判断哪个是准的。
  const pageBlock = /const CAVEATS = \[([\s\S]*?)\];/.exec(PAGE_SOURCE)?.[1];
  assert.ok(pageBlock, 'MethodologyPage 的 CAVEATS 常量被移走/改名，上面的逐字断言会失效');
  const pageCaveats = [...pageBlock.matchAll(/'[^']+'/g)].map((m) => m[0].slice(1, -1));
  assert.deepEqual(pageCaveats, backendCaveats);
});

test('the coverage_mode quoted on the page matches the implementation', () => {
  const backendMode = /BENCHMARK_COVERAGE_MODE = "([^"]+)"/.exec(ENGINE_SOURCE)?.[1];
  assert.ok(backendMode, 'benchmark_engine.py 找不到 BENCHMARK_COVERAGE_MODE');
  assert.ok(PAGE_SOURCE.includes(backendMode),
    `白皮书页的 coverage_mode 与后端不一致：后端现在是 ${backendMode}`);
});

test('reference asset parameters on the page match the assumptions registry', () => {
  const entry = (REGISTRY.assumptions || []).find((a) => a.id === 'benchmark_reference_battery');
  assert.ok(entry, '假设登记表缺少 benchmark_reference_battery —— 参数真源被移动');
  const { power_mw, energy_mwh, round_trip_efficiency } = entry.value || {};
  // 页面第 2 节的三个数与登记表逐值核对：登记表改了页面没改，对外就是说错参数。
  assert.ok(PAGE_SOURCE.includes(`${power_mw} MW`), `页面缺少功率 ${power_mw} MW`);
  assert.ok(PAGE_SOURCE.includes(`${energy_mwh} MWh`), `页面缺少容量 ${energy_mwh} MWh`);
  assert.ok(PAGE_SOURCE.includes(`RTE ${round_trip_efficiency}`), `页面缺少 RTE ${round_trip_efficiency}`);
});
