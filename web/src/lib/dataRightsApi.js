// web/src/lib/dataRightsApi.js
// R1.7 自助导出 / 账户删除的前端判据与端点表（纯函数，node:test 可覆盖）。
//
// 与 dataRights.js 的分工：那个模块只回答「隐私页第 5 条该说什么话」，这个模块回答
// 「账户中心该不该出现这个入口、点完之后是什么状态」。分开是因为两者的失效方式不同：
// 文案错了是不实陈述，状态判错是用户以为自己的删除请求没提交成功而反复点。
//
// 端点表按后端 routes/data_rights_routes.py 的真实路由逐条抄写，并由测试与后端源码
// 比对（见 dataRightsApi.test.js）—— 前端拼错一个路径的表现是「点了没反应」，
// 而没人会为此报 bug。

/** 后端 router 声明的完整前缀（与 routes/data_rights_routes.py 逐字一致，由测试比对）。 */
export const BACKEND_PREFIX = '/api/v1/account';

/**
 * 拼路径用的相对段。本仓约定 ``API_BASE``（getApiBase()）**已经带 '/api'**，
 * 所以直接 `API_BASE + BACKEND_PREFIX` 会得到 '/api/api/v1/...' —— 一个必然 404 的 URL。
 * 这里复用 apiBase.apiUrl 的幂等去重写法，而不是让调用方自己记得少写一段。
 */
export const ACCOUNT_PATH = BACKEND_PREFIX.replace(/^\/api(?=\/)/, '');

/** R1.7 端点表。apiBase 由调用方注入（本模块不碰 import.meta.env，便于 node 下测试）。 */
export function dataRightsEndpoints(apiBase) {
  return {
    exportSubmit: `${apiBase}${ACCOUNT_PATH}/export`,
    exportStatus: `${apiBase}${ACCOUNT_PATH}/export`,
    exportDownload: (exportId) => `${apiBase}${ACCOUNT_PATH}/export/${exportId}/download`,
    deletionSubmit: `${apiBase}${ACCOUNT_PATH}/delete`,
    deletionStatus: `${apiBase}${ACCOUNT_PATH}/delete`,
    deletionCancel: `${apiBase}${ACCOUNT_PATH}/delete/cancel`,
  };
}

/**
 * 「flag 说已上线」与「端点真的在线」是两个事实，必须都成立。
 *
 * 后端 route 模块走 ROUTE_MODULES 尾部追加 + 单模块 import 失败不阻断其余模块（Spec §234
 * 明确点名这是「静默不上线」风险源）。所以一个 404 是完全可能的状态，而那时隐私页若照
 * flag 写「可自助导出」，就又变回不实陈述 —— 这正是 R6.4 顺序约束要防的东西。
 */
export function endpointUnavailable(statusCode) {
  return statusCode === 404 || statusCode === 405;
}

/** 导出区间的 UI 状态。'unavailable' 会把整个入口收起来（含 flag 开着的情形）。 */
export function exportUiState({ flagOn, probeStatusCode, row }) {
  if (!flagOn) return 'disabled';
  if (endpointUnavailable(probeStatusCode)) return 'unavailable';
  if (!row) return 'idle';
  if (row.status === 'completed') return row.download_ready ? 'ready' : 'expired';
  if (row.status === 'failed') return 'failed';
  return 'inflight';
}

/** 提交导出后要不要开始轮询。'already_queued' 也要 —— 在先的那次同样会完成。 */
export function shouldPollExport(payload) {
  return ['queued', 'already_queued', 'running'].includes(payload?.status);
}

/** 删除区的 UI 状态；'executed' 之后账户已不存在，任何入口都不该再出现。 */
export function deletionUiState(row) {
  if (!row || row.status === 'none') return 'idle';
  if (row.status === 'pending') return 'pending';
  if (row.status === 'cancelled') return 'cancelled';
  return 'idle';
}

/**
 * 提交删除后是否必须立刻跳登录页。
 *
 * 后端受理成功的同时撤销了申请人全部会话与令牌（「我已要求删除」与「这个会话还能读我的
 * 数据」不能同时为真），所以下一个请求一定是 401。前端若不照这个位走，用户看到的就是一
 * 堵莫名其妙的登录墙，并且会当成失败重试 —— 这是本功能最容易被做坏的一处。
 */
export function mustReauthenticateAfterDeletion(payload) {
  return payload?.status === 'pending' && payload?.session_revoked === true;
}

/** 被「组织所有权」拦住时的可执行文案（后端 409 带 organizations 列表）。 */
export function ownershipBlockCopy(detail, zh = true) {
  const names = (detail?.organizations || [])
    .map((org) => org?.name || org?.organization_id)
    .filter(Boolean);
  if (!names.length) {
    return zh ? '请先移交组织所有权后再申请删除账户。' : 'Transfer organization ownership before deleting your account.';
  }
  const joined = names.join(zh ? '、' : ', ');
  return zh
    ? `你仍是组织「${joined}」的所有者，请先在「组织管理」中移交所有权，或解散该组织。`
    : `You are still the owner of ${joined}. Transfer ownership (or dissolve the organization) from Organization admin first.`;
}

/**
 * 宽限期倒计时（还剩几天）。缺字段或已过期一律回 null，让调用方走「不显示倒计时」分支
 * 而不是显示「剩余 NaN 天」—— 一个法律含义上的日期显示成 NaN 是很难看且很难解释的。
 */
export function graceDaysRemaining(row, nowMs = Date.now()) {
  const target = Date.parse(row?.scheduled_delete_at || '');
  if (!Number.isFinite(target) || !Number.isFinite(nowMs)) return null;
  const days = Math.ceil((target - nowMs) / 86_400_000);
  return days > 0 ? days : null;
}

/** 删除受理后跳登录页时带的唯一解释性 query 值（与 AccountPage 的跳转逐字一致）。 */
export const DELETION_PENDING_NOTICE = 'deletion_pending';

/**
 * 把登录页的 `?notice=` 值翻译成横幅文案。
 *
 * 为什么要单独有这一条：`LoginPage` 原本只在 SSO start 里**写** query string，全文从不
 * **读** `location.search`。删除受理成功后 `AccountPage` 会把人抛到
 * `/login?notice=deletion_pending`，不补这一段，用户撞上的就是一堵没有任何说明的登录墙
 * —— 而它会被人当成「我的账户已经被删了，但还能登录？还是登录坏了？」报回来。
 *
 * 未知值/空值一律回 `null`：凭空冒出一条横幅比不解释更糟。
 */
export function loginNoticeCopy(notice, zh = true) {
  if (notice !== DELETION_PENDING_NOTICE) return null;
  return zh
    ? '你的账户删除请求已排期，当前处于宽限期内。想撤销的话：登录一次，进入「账户中心 → 数据与隐私」点「撤销删除请求」。'
    : 'Your account deletion is scheduled and still within the grace period. To cancel it: sign in, open Account → Data & privacy, then choose Cancel deletion.';
}

/** 从 `location.search` 原始串取横幅文案。非法 search（如缺 '?'）当作无 notice。 */
export function readLoginNotice(search, zh = true) {
  if (typeof search !== 'string') return null;
  let params;
  try { params = new URLSearchParams(search); } catch { return null; }
  return loginNoticeCopy(params.get('notice'), zh);
}
