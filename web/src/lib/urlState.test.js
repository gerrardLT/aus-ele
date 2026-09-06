// web/src/lib/urlState.test.js
// R3.1 URL 状态镜像的判据（2026-09-06）。
//
// 这一层是 R3 里唯一「错了不会被看见」的地方：URL 只有被分享出去、被别人在另一台机器上
// 打开时才会暴露问题，而我们自己的每一次点击都一切正常。所以断言全部围绕
// 「同一条 URL 进出两次必须等价」与「不属于筛选器的参数不得被改动」来写。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  FILTER_URL_PARAMS,
  OWNED_PARAMS,
  buildUrl,
  filterPatchActions,
  filtersToUrlParams,
  mergeSearch,
  readUrlFilters,
  shouldWriteSearch,
} from './urlState.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** 与 FilterContext.toQueryParams 完全同形的序列化器（测试里不复制业务判断，只复制口径）。 */
function serialize(filters) {
  const params = { market: filters.market, region: filters.region };
  if (filters.year != null) params.year = filters.year;
  if (filters.quarter !== 'ALL') params.quarter = filters.quarter;
  if (filters.dayType !== 'ALL') params.day_type = filters.dayType;
  if (filters.months.length && !(filters.months.length === 1 && filters.months[0] === 'ALL')) {
    params.months = filters.months.join(',');
  }
  return params;
}

test('url param table matches the vocabulary the query serializer actually produces', () => {
  // 漂移锁：URL 词表与 toQueryParams 能产出的键必须是同一套。两边不一致的表现是
  // 「URL 里写了 day_type，但同步逻辑不认识它」→ 参数被当成未知键永久留在地址栏，
  // 或者反过来「筛选器改了地址栏不动」。两种都只在分享链接时暴露。
  const source = fs.readFileSync(path.resolve(__dirname, '../contexts/FilterContext.jsx'), 'utf8');
  const body = /function toQueryParams\(filters\)\s*\{([\s\S]*?)\n\}/.exec(source);
  assert.ok(body, 'FilterContext 里找不到 toQueryParams —— 本测试的前提已变化，请同步改写而非删除');
  const produced = new Set();
  for (const m of body[1].matchAll(/\bparams\.([a-z_]+)\s*=/g)) produced.add(m[1]);
  for (const m of body[1].matchAll(/const params = \{([^}]*)\}/g)) {
    for (const pair of m[1].split(',')) {
      const key = pair.match(/^\s*([a-z_]+)\s*:/);
      if (key) produced.add(key[1]);
    }
  }
  assert.deepEqual(
    OWNED_PARAMS.slice().sort(),
    [...produced].sort(),
    '筛选器序列化口径与 URL 词表必须一致（新增筛选键时两处都要改）',
  );
  assert.equal(FILTER_URL_PARAMS.length, OWNED_PARAMS.length);
});

test('readUrlFilters decodes only whitelisted values', () => {
  assert.deepEqual(readUrlFilters('?market=WEM&region=WEM&year=2024&quarter=Q1&day_type=weekday&months=1,3'), {
    market: 'WEM', region: 'WEM', year: 2024, quarter: 'Q1', dayType: 'weekday', months: ['1', '3'],
  });
  assert.deepEqual(readUrlFilters('region=WEM'), { region: 'WEM' });
  // 前导 ? 可有可无
  assert.deepEqual(readUrlFilters('?year=2023'), readUrlFilters('year=2023'));
});

test('hand-edited url values are dropped instead of entering state', () => {
  // 这些值后续会被拼进 API query，必须在这里挡住：链接是可以被人手改的。
  const hostile = '?region=../../etc&year=99999999&quarter=<script>&months=1;DROP&day_type=' + 'a'.repeat(40);
  assert.deepEqual(readUrlFilters(hostile), {});
  assert.deepEqual(readUrlFilters('?year=202'), {});          // 三位数不是年份
  assert.deepEqual(readUrlFilters('?months=1,99'), {});       // 第 13 个月
  assert.deepEqual(readUrlFilters('?months=ALL'), { months: ['ALL'] });
  assert.deepEqual(readUrlFilters('?year=abc&region=NSW1'), { region: 'NSW1' });
  assert.doesNotThrow(() => readUrlFilters(undefined));
  assert.doesNotThrow(() => readUrlFilters('?%E4%B8'));       // 残缺百分号编码
});

test('absent and illegal params stay out of the patch rather than overwriting with undefined', () => {
  // 写成 { year: undefined } 会让调用方把 state 里已有的 year 覆盖掉 —— 表现是
  // 「从 /finland?window=7d 这类无筛选参数的链接进来后年份被清空」。
  const patch = readUrlFilters('?region=WEM');
  assert.ok(!('year' in patch));
  assert.ok(!('months' in patch));
});

test('restore order puts region last so the reducer derives market from it', () => {
  const actions = filterPatchActions(readUrlFilters('?market=NEM&region=WEM&year=2024'));
  const keys = actions.map((a) => a.key);
  assert.deepEqual(keys, ['year', 'market', 'region']);
  assert.equal(keys[keys.length - 1], 'region');
  assert.equal(actions.every((a) => a.type === 'SET_FILTER'), true, '只发既有 action 类型：本批次规定不动 filterReducer');
});

test('the patch carries the url value untouched (no second copy of the market rule)', () => {
  // urlState 不得自己推导 market：那条规则属于 filterReducer，抄第二份一定会漂移。
  const patch = readUrlFilters('?region=NSW1');
  assert.deepEqual(patch, { region: 'NSW1' });
  assert.ok(!('market' in patch));
});

test('filters to url params drops keys the url layer does not own', () => {
  const full = { market: 'NEM', region: 'NSW1', year: 2024, quarter: 'ALL', dayType: 'ALL', months: ['ALL'] };
  // 值一律成字符串：query 里不存在数字类型，year 的 Number 还原发生在 readUrlFilters。
  // 保留两端各自的一次转换，而不是让序列化器吐 number 再指望 URLSearchParams 认识它。
  const produced = filtersToUrlParams(full, (f) => ({ ...serialize(f), window: '7d' }));
  assert.deepEqual(produced, { market: 'NEM', region: 'NSW1', year: '2024' });
  assert.deepEqual(filtersToUrlParams(null, serialize), {});
  assert.deepEqual(filtersToUrlParams(full, null), {});
});

test('mergeSearch keeps foreign params in their original order', () => {
  // 顺序不是美观问题：同一条链接两次复制得到两个字符串，书签与「发给对方的链接」就不可比对。
  assert.equal(mergeSearch('?window=7d&tab=spread', { region: 'WEM' }), 'window=7d&tab=spread&region=WEM');
  // 本轮没出现的自有键要被删掉（用户把 region 改回默认值 → 地址栏该干净）；
  // 非自有键即使在 params 里被显式给了 undefined 也不许动（那不是筛选器的地盘）。
  assert.equal(mergeSearch('?region=NEM&window=7d', { window: undefined }), 'window=7d');
  assert.equal(mergeSearch('?year=2020&window=7d', { year: '2024' }), 'window=7d&year=2024');
  assert.equal(mergeSearch('?year=2020&window=7d', {}), 'window=7d');
});

test('should write search only when the address bar would actually change', () => {
  assert.equal(shouldWriteSearch('?region=WEM', { region: 'WEM' }), false);
  assert.equal(shouldWriteSearch('', {}), false);
  assert.equal(shouldWriteSearch('', { region: 'WEM' }), true);
  assert.equal(shouldWriteSearch('?region=WEM', {}), true);
});

test('a filter state round-trips through the url unchanged', () => {
  // 本批次真正的验收判据：非默认状态 → URL → 再解回来必须等价（默认值不进 URL 由
  // serialize 保证，所以「干净链接」保持干净）。
  for (const filters of [
    { market: 'NEM', region: 'NSW1', year: 2024, quarter: 'ALL', dayType: 'ALL', months: ['ALL'] },
    { market: 'WEM', region: 'WEM', year: 2023, quarter: 'Q2', dayType: 'weekday', months: ['1', '7'] },
    { market: 'NEM', region: 'QLD1', year: 2026, quarter: 'Q4', dayType: 'weekend', months: ['ALL'] },
  ]) {
    const search = mergeSearch('', filtersToUrlParams(filters, serialize));
    const patch = readUrlFilters(search);
    const rebuilt = { ...filters, ...patch };
    assert.equal(rebuilt.region, filters.region, `region 丢失：${search}`);
    assert.equal(rebuilt.year, filters.year, `year 丢失：${search}`);
    assert.deepEqual(rebuilt.months, filters.months, `months 丢失：${search}`);
    if (filters.months[0] === 'ALL') assert.ok(!search.includes('months='), '默认值不该写进 URL');
  }
});

test('buildUrl never leaves a bare question mark', () => {
  assert.equal(buildUrl('/', ''), '/');
  assert.equal(buildUrl('/finland', '?window=7d'), '/finland?window=7d');
  assert.equal(buildUrl('/finland?old=1', 'window=7d'), '/finland?window=7d');
  assert.equal(buildUrl(undefined, undefined), '/');
});
