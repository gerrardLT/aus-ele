// web/src/lib/flags.js
// 统一 feature flag 层（R5.4，2026-09-06）。Spec 把它排在 R3 之前，理由不是洁癖：
// R3–R6 要上一批「改变默认界面」的东西（URL 状态化、⌘K、项目库、图表外壳、埋点、控制台），
// 每一项都可能让既有工作流出问题。没有 flag 层时，回滚一次 = 发一次版；有了它，回滚 = 改一个
// 环境变量重启。这是公测期唯一现实的「零代码回滚」手段。
//
// 三条判据（与 dataRights.js 同源，这里收口成一份）：
// 1. **只认字面量 'true'**。拼错的配置（"1"/"yes"/"TRUE "）一律退到默认值，而不是「看起来像
//    开就算开」—— 运维改错一个字符的后果应当是功能没上，而不是功能意外上了。
// 2. **默认值全 false**：新 UI 一律「不显式打开就不存在」。公测期默认开的只能是已经验收过的东西。
// 3. **flag 必须有读者**。声明了却没人读的 flag 比没有 flag 更糟：它让人以为存在一个开关，
//    出事时去拧它，而拧它什么都不会发生。`flagsGuard.test.js` 会扫全库把死 flag 挑出来。
//
// 与后端的边界：后端另有 `backend/env_flags.py`（AUS_ELE_* 控制端点是否在线）。两侧独立的
// 原因是它们控制的是不同的东西 —— 后端关掉端点，前端这边对应的文案/入口必须自己收起
// （隐私页第 5 条就是这么做的，见 dataRights.js）。**翻后端 flag 而不翻前端 flag 是安全的
// （入口在但功能 404，会被发现）；反过来翻前端不翻后端是不安全的（承诺一个不存在的功能）。**
// 所以顺序纪律永远是「后端先发 → 前端再开」。

/** flag 注册表：env 键、默认值、控制什么、关掉时用户会看到什么。 */
export const FLAG_DEFS = Object.freeze({
  dataRights: {
    envKey: 'VITE_DATA_RIGHTS_UI',
    default: false,
    controls: '账户中心「数据与隐私」tab（自助导出/删除）+ 隐私页第 5 条的措辞',
    offState: 'tab 消失，隐私页改说人工申请渠道',
  },
  // R3 四项新界面各占一位。判据是同一条：这些都在改「既有工作流的默认行为」，
  // 公测期必须能在不发版的前提下退回改造前的表现。
  urlFilters: {
    envKey: 'VITE_URL_STATE_UI',
    default: false,
    controls: 'R3.1 筛选器状态与地址栏 query 的双向镜像（含从 URL 恢复首屏状态）',
    offState: 'URL 里不再出现 market/region/year 等参数，带参数的旧链接退化为默认筛选（不报错）',
  },
  spaNav: {
    envKey: 'VITE_SPA_NAV_UI',
    default: false,
    controls: 'R3.3 侧边栏/移动抽屉链接的 SPA 接管（<a href> 仍在，只是点击时不整页刷新）',
    offState: '点击导航一律走浏览器原生整页跳转 —— 即 R3 之前的行为',
  },
  commandPalette: {
    envKey: 'VITE_COMMAND_PALETTE_UI',
    default: false,
    controls: 'R3.4 ⌘K / Ctrl+K 命令面板（面板本体动态 import，API 索引取自 /openapi.json）',
    offState: '不注册快捷键，按下 ⌘K 无任何反应，也不发起 openapi 请求',
  },
  mobileNavDrawer: {
    envKey: 'VITE_MOBILE_NAV_UI',
    default: false,
    controls: 'R3.5 ≤1100px 的左下☰抽屉导航（补上侧边栏隐藏后手机上无页面导航的空洞）',
    offState: '无抽屉，窄视口只剩 PageShell 顶部那条横向导航兜底',
  },
  analytics: {
    envKey: 'VITE_ANALYTICS_ENABLED',
    default: false,
    controls: '前端事件采集（lib/analytics.js）是否加载第三方 SDK 并发出任何网络请求',
    offState: '零网络请求、零 SDK 加载；capture() 变成 no-op',
  },
  sessionReplay: {
    envKey: 'VITE_ANALYTICS_SESSION_REPLAY',
    default: false,
    controls: '会话回放录制',
    offState: '不注册任何 DOM 观察者',
    requires: ['analytics'],
  },
  replayMaskAllText: {
    envKey: 'VITE_ANALYTICS_MASK_ALL_TEXT',
    default: false,
    controls: '回放全文本遮蔽（Spec §159：开启回放的前置条件，不可后补）',
    offState: '遮蔽关闭 → 即使 sessionReplay=true 也不录制',
    requires: ['analytics'],
  },
  replayMaskAllInputs: {
    envKey: 'VITE_ANALYTICS_MASK_ALL_INPUTS',
    default: false,
    controls: '回放输入框遮蔽（同上，与 replayMaskAllText 同时为真才允许录制）',
    offState: '遮蔽关闭 → 即使 sessionReplay=true 也不录制',
    requires: ['analytics'],
  },
});

/** 注册表里的稳定名字列表（控制台页据此渲染开关清单）。 */
export const FLAG_NAMES = Object.freeze(Object.keys(FLAG_DEFS));

function readRaw(env, def) {
  const value = typeof env?.[def.envKey] === 'string' ? env[def.envKey].trim() : undefined;
  if (value === 'true') return true;
  if (value === 'false') return false;
  return def.default;
}

/**
 * 单个 flag 的当前值。依赖它的 flag 未开时，本 flag 视为关闭（`requires` 是硬约束而不是文档）。
 */
export function isFlagEnabled(env, name) {
  const def = FLAG_DEFS[name];
  if (!def) return false; // 未注册的名字一律「关」：拼错 flag 名不该点亮任何功能
  if (!readRaw(env, def)) return false;
  for (const dep of def.requires || []) {
    if (!isFlagEnabled(env, dep)) return false;
  }
  return true;
}

/** 全部 flag 的取值快照（管理员控制台 / 排障用）。raw 保留原始字符串，便于看出拼写错误。 */
export function flagsSnapshot(env) {
  return FLAG_NAMES.map((name) => {
    const def = FLAG_DEFS[name];
    return {
      name,
      envKey: def.envKey,
      raw: env?.[def.envKey] ?? null,
      enabled: isFlagEnabled(env, name),
      default: def.default,
      controls: def.controls,
      offState: def.offState,
    };
  });
}

/** 配置里出现过的、不在注册表内的 VITE_ 开关串（防止有人新加 flag 却忘了登记）。 */
export function unregisteredFlagKeys(env) {
  const registered = new Set(FLAG_NAMES.map((n) => FLAG_DEFS[n].envKey));
  return Object.keys(env || {})
    .filter((key) => /^VITE_[A-Z0-9_]*(ENABLED|UI|REPLAY|FLAG)/.test(key) && !registered.has(key));
}
