// web/src/lib/orgAdmin.js
// R1.4 组织自助管理页的判据层（2026-09-06）。
//
// 为什么把这块逻辑单独拎出来：node:test 是本仓唯一硬阻断门，而它跑不到 JSX 里。
// 「哪个角色能看见哪一段」「邀请链接长什么样」一旦写进组件，就只能靠人眼评审 ——
// 恰恰是这两条判据决定用户会不会点下去拿 403。组件只负责渲染这里的结论。
//
// 与 rbac.js 的分工：rbac.js 镜像后端权限表；本模块决定**每一段 UI 要求哪一项权限**，
// 并且一律用分层版本（canInOrganization），因为后端 check_organization_permission 只读
// organization_membership.role，工作空间角色对组织端点没有任何影响。

import { canInOrganization } from './rbac.js';

/** 后端 org_routes 的 INVITABLE_ORG_ROLES 镜像；不含 org_owner（owner 只能靠移交产生）。 */
export const ORG_INVITE_ROLES = Object.freeze(['org_admin', 'org_billing_viewer', 'org_member']);

/** 页面分段 → 进入该段所需的**组织层**权限。null 表示任何组织成员可见。 */
export const ORG_SECTIONS = Object.freeze([
  { id: 'overview', permission: null },
  { id: 'members', permission: 'member_manage' },
  { id: 'invites', permission: 'member_manage' },
  { id: 'workspaces', permission: 'workspace_manage' },
  { id: 'domains', permission: 'org_manage' },
  { id: 'audit', permission: 'read_audit' },
]);

/**
 * 取「当前工作空间所属组织」这一条。
 *
 * 刻意不做「在我所属的多个组织里挑权限最高的那个」：页面显示的是当前空间的组织，
 * 顶栏切换空间就是切换组织。取最高角色会让用户在 A 组织看见 B 组织的管理入口。
 */
export function currentOrganization(auth) {
  const list = auth?.workspaces || [];
  const current = list.find((w) => w && w.workspace_id === auth?.workspaceId) || null;
  if (!current?.organization_id) return null;
  return {
    organizationId: current.organization_id,
    organizationName: current.organization_name || null,
    organizationRole: current.organization_role ?? null,
    // 老会话（2026-09-06 前签发的 StoredAuth）没有这个字段。区分「确实无组织角色」与
    // 「还不知道」：后者要提示重新登录，否则真 org_owner 会以为功能坏了。
    organizationRoleKnown: typeof current.organization_role !== 'undefined',
  };
}

/** 该 actor 能看见的分段 id 列表。未知/空角色只剩 overview —— 默认拒绝。 */
export function visibleSections(actor) {
  return ORG_SECTIONS.filter((section) =>
    section.permission === null ? true : canInOrganization(actor, section.permission)
  ).map((section) => section.id);
}

/** 是否值得为这个人渲染「组织管理」入口（纯 org_member/billing_viewer 进去什么也做不了）。 */
export function canManageOrganization(actor) {
  return ['member_manage', 'workspace_manage', 'org_manage', 'read_audit'].some((permission) =>
    canInOrganization(actor, permission)
  );
}

/**
 * 账户中心要不要出现「组织管理」这个 tab。入参是 currentOrganization() 的结果。
 *
 * 两个条件取或：持有任一组织管理权限（正常情形），或组织角色**未知**（2026-09-06 前的
 * 老会话）。后者必须放行 —— 唯一能解释「为什么我的组织入口不见了」的那句话写在页面里，
 * 而门留在门外，用户就永远看不到它。
 */
export function showOrgAdminEntry(org) {
  if (!org) return false;
  if (!org.organizationRoleKnown) return true;
  return canManageOrganization({ organizationRole: org.organizationRole });
}

// ---------------------------------------------------------------------------
// 端点 URL（apiBase 必填：getApiBase() 读 import.meta.env，在纯 node 下会抛）
// ---------------------------------------------------------------------------

export function organizationsUrl(apiBase) {
  return `${apiBase}/v1/organizations`;
}

export function organizationUrl(apiBase, organizationId) {
  return `${organizationsUrl(apiBase)}/${encodeURIComponent(organizationId)}`;
}

export function orgMembersUrl(apiBase, organizationId) {
  return `${organizationUrl(apiBase, organizationId)}/members`;
}

export function orgMemberActionUrl(apiBase, organizationId, principalId, action) {
  return `${orgMembersUrl(apiBase, organizationId)}/${encodeURIComponent(principalId)}/${action}`;
}

export function orgOwnerTransferUrl(apiBase, organizationId) {
  return `${organizationUrl(apiBase, organizationId)}/owner-transfer`;
}

export function orgInvitesUrl(apiBase, organizationId) {
  return `${organizationUrl(apiBase, organizationId)}/invites`;
}

export function orgInviteActionUrl(apiBase, organizationId, inviteId, action) {
  return `${orgInvitesUrl(apiBase, organizationId)}/${encodeURIComponent(inviteId)}/${action}`;
}

export function orgDomainsUrl(apiBase, organizationId) {
  return `${organizationUrl(apiBase, organizationId)}/domains`;
}

export function orgDomainVerificationUrl(apiBase, organizationId, domainId, stage) {
  const suffix = stage === 'confirm' ? '/verification/verify' : '/verification';
  return `${orgDomainsUrl(apiBase, organizationId)}/${encodeURIComponent(domainId)}${suffix}`;
}

export function orgAuditLogsUrl(apiBase, organizationId) {
  return `${organizationUrl(apiBase, organizationId)}/audit-logs`;
}

export function orgWorkspacesUrl(apiBase, organizationId) {
  return `${organizationUrl(apiBase, organizationId)}/workspaces`;
}

// ---------------------------------------------------------------------------
// 邀请链接
// ---------------------------------------------------------------------------

/**
 * 组织级邀请链接。
 *
 * 为什么带 scope=org：/invite 页原先只认工作空间级邀请（POST /v1/account/invites/accept），
 * 组织级邀请要走 /v1/organizations/invites/accept。复用同一个页面 + 一个 query 判别位，
 * 比新增一条根路由便宜，且不动 main.jsx 那串被测试锁死的 lazy/三元结构。
 *
 * 诚实标注：token 进 URL 意味着它会出现在浏览器历史、Referer 与访问日志里。邀请链接
 * 本质上是「持有即授权」的 bearer 凭据，这一点无法靠前端消除 —— 缓解手段在后端：
 * 一次性接受（status 变 accepted 即失效）+ 可撤销 + 按 token+IP 限流。既有工作空间级
 * 邀请链接同形（account_routes 的 invite_url_path），此处不引入新暴露面。
 */
export function orgInviteLink(origin, inviteToken) {
  const base = String(origin || '').replace(/\/+$/, '');
  return `${base}/invite?token=${encodeURIComponent(inviteToken)}&scope=org`;
}

/** 从 location.search 判读邀请接受流程的层级。缺省按工作空间级（保持既有链接行为）。 */
export function inviteScope(search) {
  try {
    return new URLSearchParams(search || '').get('scope') === 'org' ? 'org' : 'workspace';
  } catch {
    return 'workspace';
  }
}

/**
 * 邀请接受端点。两条链路的请求体同名（invite_token/display_name/password），差别只在层级。
 */
export function inviteAcceptEndpoint(apiBase, scope) {
  return scope === 'org'
    ? `${organizationsUrl(apiBase)}/invites/accept`
    : `${apiBase}/v1/account/invites/accept`;
}

/**
 * 接受邀请的后端响应里是否含「可自动登录的落地点」。
 *
 * 判据取自响应而不是 scope：组织级邀请现在会补一个 workspace 成员身份（否则受邀者登录
 * 必吃 401），但当该组织一个工作空间都没有时无从补起 —— 那种情况下邀请本身是成功的，
 * 只是进不去。用 scope 硬编码「组织级不能自动登录」会把一个已修好的链路锁死在旧行为上。
 */
export function inviteAcceptSessionReady(payload) {
  return Boolean(payload?.principal?.email && payload?.workspace?.workspace_id);
}

/**
 * 把后端 detail 归一为一句人话。
 *
 * 403 单列：本组织的 403 意味着「你看到的入口本该被门控掉」，多半是当前工作空间所属
 * 组织与预期不符（组织角色逐空间判定），所以提示里带一句切换空间 —— 这是用户唯一能
 * 自己做的补救。401 则是令牌过期/被吊销，非成员访问他组织也走这个码。
 */
export function describeOrgError(payload, status, zh) {
  const detail = String((payload && payload.detail) || `Request failed (${status})`);
  if (status === 403) {
    return zh ? `权限不足（${detail}）。组织角色按当前工作空间判定，若不是你想要的组织，请先在顶栏切换。` : `Permission denied (${detail}).`;
  }
  if (status === 401) {
    return zh ? '登录状态已失效，或你不是该组织成员。请重新登录/切换组织后重试。' : 'Session expired, or you are not a member of this organization.';
  }
  return detail;
}
