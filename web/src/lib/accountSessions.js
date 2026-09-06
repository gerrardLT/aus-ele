// web/src/lib/accountSessions.js
// R1.3 会话面板的纯判据层（2026-09-06）。
//
// 后端 ``GET /api/v1/account/sessions`` 的 SQL 只过滤 ``revoked = 0``，**不过滤
// ``expires_at``** —— 到期但尚未被清理的会话仍会返回。若前端照原样打上「活跃会话」
// 标题并列出条数，会同时犯两种错：
//   1. 用户以为自己被别人多端登录（虚惊），而那会话其实早就不能用了；
//   2. 反过来，用户以为「登出其他设备」清掉了 3 个设备，实际只清掉了还活着的那 1 个。
// 账户安全类 UI 上，计数失真比没有计数更糟 —— 它给出的是一种虚假的安全感。
// 因此这里按 expires_at 重新分类，且把「已到期」显式画出来而不是静默丢弃
// （静默丢弃会让用户以为后端在撒谎，而撒谎的只是标题）。

// 与 accountNotices.js 同构：本模块**不调用** getApiBase()（它读 import.meta.env，
// 在 node:test 下是 undefined），apiBase 一律由调用方组件传入。

export const AUTH_METHOD_LABELS = {
  password: { zh: '密码', en: 'Password' },
  oidc: { zh: '企业 SSO', en: 'SSO' },
  google: { zh: 'Google', en: 'Google' },
  github: { zh: 'GitHub', en: 'GitHub' },
  web_session: { zh: '匿名浏览', en: 'Anonymous' },
};

/** 会话列表端点。apiBase 必填（见文件头注释）。 */
export function sessionsUrl(apiBase) {
  return `${apiBase}/v1/account/sessions`;
}

/** 后端只实现了「保留当前、吊销其余」，没有单条吊销端点 —— 面板因此不给单行删除按钮。 */
export function revokeOthersUrl(apiBase) {
  return `${apiBase}/v1/account/sessions/revoke-others`;
}

function toMillis(value) {
  if (!value) return null;
  const parsed = Date.parse(value);
  return Number.isNaN(parsed) ? null : parsed;
}

/** 缺 expires_at 视为「未知有效期」→ 保守当作仍活跃（后端签发时总会带上，缺失多为老数据）。 */
function statusOf(session, currentSessionId, nowMs) {
  if (currentSessionId && session.session_id === currentSessionId) return 'current';
  const expiresAt = toMillis(session.expires_at);
  if (expiresAt !== null && expiresAt <= nowMs) return 'expired';
  return 'active';
}

/**
 * 把后端返回的会话列表整理成可渲染行。
 *
 * @param {object} body 后端响应：{items, current_session_id}
 * @param {Array} workspaces authStore 里的工作空间清单，用于把 id 翻成人类可读名
 * @param {number} nowMs 注入时钟
 */
export function partitionSessions(body, workspaces = [], nowMs = Date.now()) {
  const currentSessionId = body?.current_session_id || null;
  const nameById = new Map(workspaces.map((w) => [w.workspace_id, w.name || w.workspace_id]));
  const rows = (body?.items || []).map((session) => ({
    sessionId: session.session_id,
    workspaceId: session.workspace_id || null,
    workspaceName: nameById.get(session.workspace_id) || session.workspace_id || null,
    authMethod: session.auth_method || 'password',
    createdAt: session.created_at || null,
    lastSeenAt: session.last_seen_at || null,
    expiresAt: session.expires_at || null,
    status: statusOf(session, currentSessionId, nowMs),
  }));
  // 当前会话置顶，其余按最近活动倒序：用户找的是「我在这台设备上」和「那个我没登录过的」。
  const rank = { current: 0, active: 1, expired: 2 };
  rows.sort((a, b) => {
    if (rank[a.status] !== rank[b.status]) return rank[a.status] - rank[b.status];
    return String(b.lastSeenAt || b.createdAt || '').localeCompare(String(a.lastSeenAt || a.createdAt || ''));
  });
  return rows;
}

/** 是否值得显示「登出其他设备」：存在至少一个仍活着的其他会话。 */
export function canRevokeOthers(rows) {
  return rows.some((row) => row.status === 'active');
}

/** 活的会话数（含当前）—— 面板标题用这个数，而不是后端返回的原始条数。 */
export function liveSessionCount(rows) {
  return rows.filter((row) => row.status === 'current' || row.status === 'active').length;
}

export function methodLabel(authMethod, zh = true) {
  const entry = AUTH_METHOD_LABELS[authMethod];
  if (entry) return zh ? entry.zh : entry.en;
  return authMethod || '—';
}

/** ISO → 「YYYY-MM-DD HH:mm」；无值给占位符，避免渲染出 1970 年这种误导性时间。 */
export function formatStamp(value, zh = true) {
  if (!value) return zh ? '未知' : 'unknown';
  const normalized = String(value).slice(0, 16).replace('T', ' ');
  return normalized.length < 10 ? value : normalized;
}
