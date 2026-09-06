// web/src/lib/workspaceSwitch.js
// R1.5 工作空间切换的纯逻辑层（2026-09-06）。
//
// 为什么把这部分从组件里抽出来：切换要改写 localStorage 里的认证记录，而记录形状由
// authStore 与 agentApi 共同消费。原先这段落地逻辑在 AuthContext 里已经复制过一份
// （``switchWorkspace`` 是 ``login`` 的复制粘贴），再加顶栏切换器就会是第三份 ——
// 三份实现必然分叉，而分叉的方向通常是「某一处忘了保留 workspaces」，表现为
// 用户切换工作空间后组织名消失或下拉框变空。抽成单函数 + node:test 把形状锁住。

// 本模块刻意**不调用** getApiBase()：它读 import.meta.env，在 node:test 里是 undefined。
// 与 accountNotices.js 同构 —— 由调用方把 apiBase 传进来，测试因此可以注入确定值。

/** 后端免密换签端点：POST /api/v1/account/workspaces/{id}/login-session。 */
export function loginSessionUrl(apiBase, workspaceId) {
  return `${apiBase}/v1/account/workspaces/${encodeURIComponent(workspaceId)}/login-session`;
}

/**
 * 把后端换签响应并入既有认证记录。
 *
 * 保留项是刻意的：``principal`` 与 ``workspaces`` 不来自换签响应（响应只有令牌），
 * 覆盖它们会让切换后「知道自己是谁」这条信息凭空丢失，用户只剩一个新 workspaceId。
 *
 * @param {object|null} current 现有 StoredAuth
 * @param {object} session 后端响应，需含 access_token / session_token / workspace_id
 * @param {number} [nowMs] 注入时钟，便于测试
 * @returns {object|null} 新的认证记录；输入不完整时返回 null（调用方据此不落盘）
 */
export function mergeSwitchedSession(current, session, nowMs = Date.now()) {
  if (!current || !session) return null;
  const { access_token: accessToken, session_token: sessionToken, workspace_id: workspaceId } = session;
  if (!accessToken || !sessionToken || !workspaceId) return null;
  return {
    ...current,
    accessToken,
    accessTokenExp: Math.floor(nowMs / 1000) + (session.access_token_expires_in || 3600),
    sessionToken,
    workspaceId,
    principal: current.principal || null,
    workspaces: current.workspaces || [],
  };
}

/**
 * 当前用户可切换到的工作空间（排除正在使用的那个）。
 *
 * 只有一条空间时返回空数组 —— 组件据此完全不渲染。顶栏放一个永远只有一项的下拉框
 * 不是「功能」，是噪音，而且会让人以为存在别的工作空间。
 */
export function switchableWorkspaces(auth) {
  const items = auth?.workspaces || [];
  if (items.length < 2) return [];
  return items.filter((w) => w.workspace_id && w.workspace_id !== auth.workspaceId);
}

/** 展示名：优先人类可读名称，退回 workspace_id 前缀（避免直接显示一串 UUID）。 */
export function workspaceLabel(workspace, zh = true) {
  const name = workspace?.name;
  if (name) return zh ? `${name}（${workspace.role || '—'}）` : `${name} (${workspace.role || '—'})`;
  const id = workspace?.workspace_id || '';
  if (!id) return zh ? '未命名空间' : 'Untitled';
  return zh ? `未命名空间 ${id.slice(0, 8)}` : `Untitled ${id.slice(0, 8)}`;
}
