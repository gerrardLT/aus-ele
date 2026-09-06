// web/src/lib/urlState.js
// R3.1 可分享 URL 状态（2026-09-06）：把筛选器状态镜像进 query string，并从 URL 恢复。
//
// 这里只有纯函数 —— 不碰 window、不碰 React。原因不是洁癖：URL 语义是整个批次里最容易
// 「看起来对、实际错」的一块（保留未知参数、默认值不写入、刷新后状态一致），而它必须能在
// node:test 里跑（node:test 是本仓唯一硬阻断门）。DOM 侧的接线全在 hooks/useUrlFilterSync.js。
//
// 三条不可退让的性质，以及各自会怎么坏掉：
// 1. **未知参数必须原样保留**。/finland?window=7d 这类页面自带参数不该被筛选器同步抹掉；
//    抹掉的表现为「用户分享链接后对方看到的窗口不一样」，而我们完全不会收到报错。
// 2. **默认值不写进 URL**。写满六个参数会让「干净链接」变成 ?market=NEM&region=NSW1&...，
//    而序列化器 toQueryParams 本来就实现了「只输出非默认值」—— 所以这里复用它，
//    而不是另写一份「哪些算默认」的清单（两份清单一定会漂移）。
// 3. **URL 里的值必须过白名单**。链接是可以被人手改的：region=../../ 或一段 200 字符的
//    东西进 state 之后会被拼进 API query。这里按字符集与长度拦一道，不合法就当没这个参数。

/** query string 参数名 ↔ 筛选器 state 字段。参数名以 toQueryParams 的输出为准。 */
export const FILTER_URL_PARAMS = [
  { param: 'market', stateKey: 'market', kind: 'token' },
  { param: 'region', stateKey: 'region', kind: 'token' },
  { param: 'year', stateKey: 'year', kind: 'year' },
  { param: 'quarter', stateKey: 'quarter', kind: 'token' },
  { param: 'day_type', stateKey: 'dayType', kind: 'token' },
  { param: 'months', stateKey: 'months', kind: 'csv' },
];

/**
 * 恢复时的派发顺序：**region 必须最后**。
 *
 * filterReducer 里 `key === 'region'` 会顺带改写 market（WEM ↔ NEM）。所以一条被人手改成
 * `market=WEM&region=NSW1` 的自相矛盾链接，恢复完得到的是 market=NEM —— 即「reducer 的推导
 * 优先于 URL 里的字面值」。选这个方向而不是反过来，是因为反过来需要一个不受 reducer 改写
 * 的裸赋值分支，那条分支一旦存在就会被复用到别处，届时「market 由 region 决定」这句话作废。
 */
const RESTORE_ORDER = ['months', 'quarter', 'day_type', 'year', 'market', 'region'];

const TOKEN_RE = /^[A-Za-z0-9_,.-]{1,24}$/;
const YEAR_RE = /^\d{4}$/;

/** 供调用方使用的参数名列表（也是「URL 里哪些键归筛选器管」的唯一答案）。 */
export const OWNED_PARAMS = FILTER_URL_PARAMS.map((entry) => entry.param);

function byParam(param) {
  return FILTER_URL_PARAMS.find((entry) => entry.param === param) || null;
}

/** 解析 search（可带或不带前导 `?`）。解析失败一律当空串处理，绝不抛错。 */
function toSearchParams(search) {
  try {
    return new URLSearchParams(typeof search === 'string' ? search.replace(/^\?/, '') : '');
  } catch {
    return new URLSearchParams();
  }
}

function decodeValue(kind, raw) {
  if (typeof raw !== 'string' || raw === '') return null;
  if (kind === 'year') return YEAR_RE.test(raw) ? Number(raw) : null;
  if (kind === 'csv') {
    // months 的元素只能是 'ALL' 或 1..12：混进别的东西说明这条链接被手改过，整条丢弃。
    // 允许 'ALL' 与其它值混排没意义（toQueryParams 只在含非 ALL 值时才输出），所以两种
    // 形态各判一次，而不是「先按数字解析失败再试 ALL」。
    const items = raw.split(',').map((item) => item.trim()).filter(Boolean);
    if (!items.length || items.length > 13) return null;
    const allOnly = items.length === 1 && items[0] === 'ALL';
    const monthNumbers = items.every((item) => /^\d{1,2}$/.test(item) && Number(item) >= 1 && Number(item) <= 12);
    return allOnly || monthNumbers ? items : null;
  }
  return TOKEN_RE.test(raw) ? raw : null;
}

/**
 * URL → 待派发的筛选器补丁 `{ stateKey: value }`。
 * 只认识 OWNED_PARAMS；缺失、非法、空值一律不出现在结果里（而不是写成 undefined，
 * 那会把 state 里已有的值覆盖掉）。
 */
export function readUrlFilters(search) {
  const params = toSearchParams(search);
  const patch = {};
  const ordered = OWNED_PARAMS.slice().sort((a, b) => {
    return RESTORE_ORDER.indexOf(a) - RESTORE_ORDER.indexOf(b);
  });
  for (const param of ordered) {
    if (!params.has(param)) continue;
    const entry = byParam(param);
    const value = decodeValue(entry.kind, params.get(param));
    if (value !== null) patch[entry.stateKey] = value;
  }
  return patch;
}

/**
 * 补丁 → SET_FILTER 动作序列（调用方拿去**喂给真正的 reducer 重放**）。
 *
 * 为什么返回动作而不是直接返回新状态：reducer 里 `key === 'region'` 会顺带改写 market，
 * 这里若自己算一遍最终 state，就等于把「market 由 region 推导」这条规则抄了第二份 ——
 * 抄来的那份一定会漂移。所以本模块只负责「按什么顺序派发哪些键」（RESTORE_ORDER，有测试锁），
 * 落地交给 FilterContext 用真 reducer 重放，规则始终只有一份。
 *
 * 也刻意**不**在挂载后用 dispatch 做首屏恢复：那样在恢复落地前会先渲染一遍默认状态，
 * 而那一遍就触发写回 useEffect，把地址栏里的 ?region=WEM 当成「与默认值不同、需要重写」
 * 的内容覆盖掉 —— 表现是**用户刚把链接发出去，对方打开后筛选条件被抹平**。这个坑只在
 * 「从 URL 进来」这条路径上出现，也就是分享/书签这两条最不该坏的路径。
 */
export function filterPatchActions(patch) {
  return Object.entries(patch).map(([key, value]) => ({ type: 'SET_FILTER', key, value }));
}

/**
 * 筛选器 → query 参数。
 *
 * `serialize` 由调用方注入（FilterContext 里就是 toQueryParams 本身）：URL 序列化必须与
 * API query 用**同一个**函数，否则「分享出去的链接」和「页面实际请求」会出现两套口径 ——
 * 那种分歧的表现是用户说「我发给你的链接打开是对的，页面上却不对」，而两边各自都自洽。
 */
export function filtersToUrlParams(filters, serialize) {
  if (typeof serialize !== 'function' || !filters) return {};
  const produced = serialize(filters) || {};
  const out = {};
  for (const [key, value] of Object.entries(produced)) {
    const entry = byParam(key);
    if (!entry) continue; // 序列化器新增了 URL 不认识的名字：宁可不写，也不写错名字
    out[key] = Array.isArray(value) ? value.join(',') : String(value);
  }
  return out;
}

/**
 * 在既有 search 上套用参数：套入非默认值、删掉本轮变成默认值的键、**其余键原样保留**。
 * 返回不含前导 `?` 的串（空串表示「URL 里没有任何参数」）。
 */
export function mergeSearch(baseSearch, params) {
  const current = toSearchParams(baseSearch);
  const next = new URLSearchParams();
  // 先按原顺序抄一遍非自有键，避免同步筛选器时把 ?window=7d 顶到末尾（顺序变化会让
  // 「同一条链接两次复制得到两个不同字符串」，也就毁掉书签/分享的可比对性）。
  for (const [key, value] of current.entries()) {
    if (!OWNED_PARAMS.includes(key)) next.append(key, value);
  }
  for (const param of OWNED_PARAMS) {
    if (Object.prototype.hasOwnProperty.call(params || {}, param)) {
      next.set(param, params[param]);
    } else {
      next.delete(param);
    }
  }
  return next.toString();
}

/** 该不该动地址栏：完全等价时返回 false（无谓的 replaceState 会污染 performance.entries）。 */
export function shouldWriteSearch(baseSearch, params) {
  return mergeSearch(baseSearch, params) !== toSearchParams(baseSearch).toString();
}

/** 组装完整地址（pathname 不带 query）。search 为空时不留光秃秃的 `?`。 */
export function buildUrl(pathname, search) {
  const base = String(pathname || '/').split('?')[0];
  const qs = typeof search === 'string' ? search.replace(/^\?/, '') : '';
  return qs ? `${base}?${qs}` : base;
}
