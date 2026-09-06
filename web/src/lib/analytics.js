// web/src/lib/analytics.js
// 前端事件采集与会话回放接入（R5.1/R5.3，2026-09-06）。
//
// 接入形态取 Spec §154 的选项 (a)：公测期先用托管版分析服务，主 compose 零改动。
// 决定性理由是资源而不是偏好：`ci.yml` 的 deploy 校验按**四服务** running 判定，往主
// compose 加分析栈的 5 个服务会让 120s 验证失败并触发回滚门控；而现有 mem_limit 合计约
// 4.5GB，分析栈自身就要 ≥4GB，同机共存必然 OOM。
//
// 三条硬约束（都写在代码里，不只是注释）：
//
// 1. **SDK 必须动态加载，绝不进 entry chunk**。本模块不 `import` 任何分析 SDK —— 一是
//    entry 体积会被 `check_bundle_budget.mjs` 挡下（850KB 预算），二是**未启用时页面上不
//    该出现任何第三方代码**。改为按 env 给的 URL 注入 script 标签：没配 URL = 不联网。
// 2. **flag 关闭时零副作用**：不建队列、不注入 script、不发请求、不抛错。`capture()` 在
//    关闭态返回 false，调用方无需判断。
// 3. **回放必须遮蔽先行**（Spec §159，不可后补）。本平台展示的是投资决策数据，回放里泄露
//    客户项目名与财务数字的代价远高于回放本身的价值 —— 所以 `mask_all_text` 与
//    `mask_all_inputs` 任一为假时，即使 `sessionReplay=true` 也**拒绝**开启录制。
//
// 数据出境的披露义务：分析服务是在线子处理者，启用前必须先在 `/legal/dpa` 第 4 条与
// `/legal/cookies` 第 7 条点名（那两条现在写的都是「未启用，启用前会先公示」）。
// 翻 `VITE_ANALYTICS_ENABLED` 之前请先改法务文本，不要反过来。

import { isFlagEnabled } from './flags.js';

/** 非 flag 的配置项（密钥/端点），与开关分离，避免把 token 当成布尔位。 */
export const ANALYTICS_CONFIG_ENV = Object.freeze({
  sdkUrl: 'VITE_ANALYTICS_SDK_URL',
  token: 'VITE_ANALYTICS_TOKEN',
  host: 'VITE_ANALYTICS_HOST',
});

/** 未 init 前的事件队列上限：页面无限操作而 SDK 一直加载失败时，不能无限吃内存。 */
const MAX_QUEUE = 50;

let state = { status: 'idle', queued: [], sent: 0, dropped: 0 };

function config(env, key) {
  const value = env?.[ANALYTICS_CONFIG_ENV[key]];
  return typeof value === 'string' && value.trim() ? value.trim() : null;
}

export function isAnalyticsEnabled(env) {
  return isFlagEnabled(env, 'analytics');
}

/**
 * 会话回放是否允许开启。遮蔽不齐全 = 不允许，没有「先录再补遮蔽」这条路。
 */
export function isRecordingEnabled(env) {
  if (!isAnalyticsEnabled(env)) return false;
  if (!isFlagEnabled(env, 'sessionReplay')) return false;
  return isFlagEnabled(env, 'replayMaskAllText') && isFlagEnabled(env, 'replayMaskAllInputs');
}

/** 供测试与控制台读取的内部状态（不含任何用户数据）。 */
export function analyticsStatus() {
  return { ...state, queued: state.queued.length };
}

/** 测试用：清掉模块级状态。生产代码不调用。 */
export function resetAnalyticsForTest() {
  state = { status: 'idle', queued: [], sent: 0, dropped: 0 };
}

function globalScope() {
  return typeof globalThis !== 'undefined' ? globalThis : null;
}

/** 第三方 SDK 注入后的全局句柄（不同 SDK 用不同名字，逐个探测）。 */
function providerHandle() {
  const scope = globalScope();
  if (!scope) return null;
  const candidate = scope.posthog || scope.__analytics;
  return candidate && typeof candidate.capture === 'function' ? candidate : null;
}

/**
 * 初始化（幂等）。关闭态或未配 URL 时什么都不做，返回状态字符串给调用方记日志。
 *
 * `doc` 形参存在只为了可测性：node 环境没有 document，测试传一个假对象即可断言「未启用时
 * 一个 script 标签都没被插入」。
 */
export function initAnalytics(env, { doc } = {}) {
  if (!isAnalyticsEnabled(env)) return 'disabled';
  const sdkUrl = config(env, 'sdkUrl');
  const token = config(env, 'token');
  if (!sdkUrl || !token) {
    // 开关打开但缺配置：不发请求，也不报错。状态记成 unconfigured，是为了让 capture()
    // 停止入队 —— 半截配置下永远不会有任何东西来消费队列，继续攒等于把用户行为长期留在内存里。
    state = { ...state, status: 'unconfigured', queued: [] };
    return 'unconfigured';
  }
  if (state.status === 'ready' || state.status === 'loading') return state.status;
  const document = doc || (typeof globalThis !== 'undefined' ? globalThis.document : null);
  if (!document || typeof document.createElement !== 'function') return 'no-dom';

  state = { ...state, status: 'loading' };
  const script = document.createElement('script');
  script.async = true;
  script.src = sdkUrl;
  script.onload = () => {
    const provider = providerHandle();
    if (provider && typeof provider.init === 'function' && !provider.__started) {
      try {
        provider.init(token, {
          api_host: config(env, 'host') || undefined,
          // 遮蔽在这里再声明一次：即使有人在分析后台开了录制，前端不带遮蔽参数就不录。
          // 后台开关与前端开关谁都不信对方，两边都要独立成立。
          mask_all_text: isFlagEnabled(env, 'replayMaskAllText'),
          mask_all_inputs: isFlagEnabled(env, 'replayMaskAllInputs'),
          capture_pageview: false, // 页面浏览由调用方显式 capture，避免默认值变动带来静默扩采
          autocapture: isRecordingEnabled(env),
        });
        provider.__started = true;
      } catch { /* 采集失败绝不影响业务交互 */ }
    }
    state = { ...state, status: 'ready' };
    flush();
  };
  script.onerror = () => {
    // SDK 被广告拦截器或网络问题挡掉是常态：降级为「不采集」，不重试、不排队膨胀。
    state = { ...state, status: 'unavailable', queued: [] };
  };
  try {
    document.head ? document.head.appendChild(script) : document.body?.appendChild(script);
  } catch {
    state = { ...state, status: 'unavailable' };
  }
  return state.status;
}

function flush() {
  const provider = providerHandle();
  if (!provider || state.status !== 'ready') return;
  const pending = state.queued;
  state = { ...state, queued: [] };
  for (const [event, props] of pending) {
    try {
      provider.capture(event, props);
      state = { ...state, sent: state.sent + 1 };
    } catch { /* 单条失败丢弃即可 */ }
  }
}

/**
 * 记一个事件。关闭态是纯 no-op；开启但未就绪时入有界队列。
 *
 * 事件名一律 snake_case 且不含用户输入内容 —— 属性里只放标识符与枚举值，**永远不放查询
 * 文本、项目名、财务数字**。这条不是风格问题：事件名与属性会被第三方分析服务长期留存并可
 * 被其员工访问，而用户在站内输入的正是投资决策内容本身。
 */
export function capture(event, props = null, env = undefined) {
  if (!isAnalyticsEnabled(env)) return false;
  if (typeof event !== 'string' || !event) return false;
  const safeProps = sanitizeProps(props);
  const provider = providerHandle();
  if (provider && state.status === 'ready') {
    try {
      provider.capture(event, safeProps);
      state = { ...state, sent: state.sent + 1 };
      return true;
    } catch {
      return false;
    }
  }
  if (state.status === 'unavailable' || state.status === 'unconfigured') return false;
  if (state.queued.length >= MAX_QUEUE) {
    state = { ...state, dropped: state.dropped + 1 };
    return false;
  }
  state = { ...state, queued: [...state.queued, [event, safeProps]] };
  return true;
}

/** 关联身份。传的是我方 principal_id（不含邮箱），且只做一次性 identify。 */
export function identify(principalId, traits = null, env = undefined) {
  if (!isAnalyticsEnabled(env)) return false;
  if (typeof principalId !== 'string' || !principalId || principalId.includes('@')) return false;
  const provider = providerHandle();
  if (!provider || typeof provider.identify !== 'function' || state.status !== 'ready') return false;
  try {
    provider.identify(principalId, sanitizeProps(traits));
    return true;
  } catch {
    return false;
  }
}

/** 退出登录时切断身份，避免同一浏览器会话把两个人的行为串起来。 */
export function resetIdentity(env = undefined) {
  if (!isAnalyticsEnabled(env)) return false;
  const provider = providerHandle();
  if (!provider || typeof provider.reset !== 'function') return false;
  try {
    provider.reset();
    return true;
  } catch {
    return false;
  }
}

const ALLOWED_VALUE = /^[\w .:/+#-]{0,120}$/;

/**
 * 看起来会装自由文本或业务数字的 key，直接拒收。
 *
 * 光靠值的字符集挡不住用户输入 —— 一段搜索词和一个合法枚举值在字符层面没有区别。所以判据
 * 只能落在 key 上：把「这个字段名的用途就是说不出手的用户内容」列成黑名单，让误传变成
 * 「上报了个空属性」而不是「把项目名送进了第三方」。这不是完备防线（换个 key 名照样能传），
 * 它防的是最常见的那种事故：调用方顺手多传了一个字段。
 */
const DENIED_KEY = /(?:^|_)(?:q|query|search|text|note|comment|remark|prompt|email|name|title|project|client|customer|revenue|cost|amount|price|irr|npv|token|secret|url|path|raw)(?:$|_)/;

/**
 * 属性白名单化：短 key + 「标量 + 无换行 + 长度受限 + 不含 @」的值，其余丢弃。
 * 与其指望调用方别把用户输入传进来，不如让传了也进不去。
 */
function sanitizeProps(props) {
  if (!props || typeof props !== 'object') return {};
  const out = {};
  for (const [key, value] of Object.entries(props)) {
    if (!/^[\w.]{1,40}$/.test(key)) continue;
    if (DENIED_KEY.test(key)) continue;
    if (typeof value === 'boolean' || typeof value === 'number') {
      out[key] = value;
    } else if (typeof value === 'string' && !value.includes('@') && ALLOWED_VALUE.test(value)) {
      out[key] = value;
    }
  }
  return out;
}
