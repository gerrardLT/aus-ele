// web/src/lib/rbac.js
// R1.6 前端权限可见性（2026-09-06）：把后端 ROLE_PERMISSIONS / ORG_ROLE_PERMISSIONS
// 的判定镜像到前端，用于「该不该渲染这个入口」。
//
// 边界（务必守住，否则前端会变成第二套鉴权）：
// 1. 这里只做**可见性**，不做授权。后端每个端点仍各自 check_*_permission，前端
//    can() 返回 true 也可能拿到 403（例如令牌过期）。任何「因为 can() 通过所以不发请求」
//    的优化都是把安全决策搬进浏览器 —— 浏览器里的判定攻击者可控。
// 2. 不与后端共享一份数据，靠 rbac.test.js 读 backend/access_control.py 源码做**漂移检测**。
//    之所以能接受这份重复：两侧的语言运行时不同（Python 字典 vs 浏览器 ESM），
//    而 node:test 是本仓唯一硬阻断门，把它挂在这里比新增一个 codegen 步骤更可靠。
// 3. 语义与后端逐字对齐：**扁平集合，无角色继承**。后端 ``owner`` 之所以看起来覆盖
//    ``admin``，只是因为字典里把它显式写全了，而不是代码做了蕴含。前端若自行实现
//    「owner > admin」的层级，会在后端漏写一项时出现「前端显示、后端 403」的分裂。

export const WORKSPACE_PERMISSIONS = {
  owner: new Set(['org_manage', 'workspace_manage', 'member_manage', 'export', 'read_audit']),
  admin: new Set(['workspace_manage', 'member_manage', 'export', 'read_audit']),
  analyst: new Set(['export']),
  viewer: new Set(),
  exporter: new Set(['export']),
};

export const ORGANIZATION_PERMISSIONS = {
  org_owner: new Set(['org_manage', 'member_manage', 'workspace_manage', 'read_audit']),
  org_admin: new Set(['member_manage', 'workspace_manage', 'read_audit']),
  org_billing_viewer: new Set(),
  org_member: new Set(),
};

/** 未知角色一律空集 —— 与后端 ``.get(role, set())`` 同构：默认拒绝。 */
function permissionsForRole(table, role) {
  return table?.[role] || new Set();
}

/**
 * 把任意调用方形状归一为 { workspaceRole, organizationRole }。
 *
 * 接受三种输入：后端 actor 字典（含 membership / organization_membership）、
 * authStore 的 workspaces 条目（扁平 role 字段）、以及裸角色字符串。归一放在一处，
 * 是为了避免每个组件各自「兼容一下」—— 那会让「未知形状 → 静默无权限」的默认拒绝
 * 在某条分支上变成「未知形状 → 拿到别处的权限」。
 */
export function normalizeActor(actor) {
  if (!actor) return { workspaceRole: null, organizationRole: null };
  if (typeof actor === 'string') return { workspaceRole: actor, organizationRole: null };
  const membership = actor.membership || {};
  const orgMembership = actor.organization_membership || {};
  return {
    workspaceRole: membership.role ?? actor.workspaceRole ?? actor.role ?? null,
    organizationRole: orgMembership.role ?? actor.organizationRole ?? actor.orgRole ?? null,
  };
}

/** 该 actor 在当前 workspace 与 organization 两层合计持有的权限名列表。 */
export function permissionsOf(actor) {
  const { workspaceRole, organizationRole } = normalizeActor(actor);
  const merged = new Set([
    ...permissionsForRole(WORKSPACE_PERMISSIONS, workspaceRole),
    ...permissionsForRole(ORGANIZATION_PERMISSIONS, organizationRole),
  ]);
  return [...merged].sort();
}

/**
 * 判定 actor 是否持有 permission（**两层并集**：工作空间层或组织层任一授予即为真）。
 * 未知名（如拼错的权限串）一律 false。
 *
 * 之所以不抛错：抛错会让一个权限串拼错变成页面白屏，而静默 false 最多是入口不显示。
 * 拼错的高发面由 rbac.test.js 里的「权限名白名单」断言兜住，而不是靠运行时异常。
 *
 * 注意：跨层判定的界面（如「这个账户页有没有任何可管理的东西」）用这个；**层级专属的
 * 界面必须用下面的分层版本**，理由见 canInOrganization。
 */
export function can(actor, permission) {
  return canInWorkspace(actor, permission) || canInOrganization(actor, permission);
}

/** 仅工作空间层。对应后端 ``check_workspace_permission``（只读 membership.role）。 */
export function canInWorkspace(actor, permission) {
  const { workspaceRole } = normalizeActor(actor);
  return isPermissionName(permission) && permissionsForRole(WORKSPACE_PERMISSIONS, workspaceRole).has(permission);
}

/**
 * 仅组织层。对应后端 ``check_organization_permission``（只读 organization_membership.role）。
 *
 * 分层是**必须**的，不是风格问题：后端这两道判定各读各的角色，不存在跨层蕴含。
 * 若用并集版 ``can()`` 去门控组织管理入口，一个「ws owner + org_member」的人会看到
 * 成员名册入口（owner 在工作空间层持有 member_manage），点下去拿 403 —— 这正是
 * 「前端显示、后端拒绝」的分裂，比不显示更糟。
 */
export function canInOrganization(actor, permission) {
  const { organizationRole } = normalizeActor(actor);
  return isPermissionName(permission) && permissionsForRole(ORGANIZATION_PERMISSIONS, organizationRole).has(permission);
}

function isPermissionName(permission) {
  return typeof permission === 'string' && permission !== '';
}

/** 若干权限是否全部持有（对应后端「一个端点要求一项权限」的复合场景，如导出需 export）。 */
export function canAll(actor, permissions) {
  return (permissions || []).every((permission) => can(actor, permission));
}

/**
 * 从 authStore 的 StoredAuth 折出「当前工作空间」这一层的 actor。
 *
 * 权限是**逐工作空间**的：同一个人在 ws_a 是 owner、在 ws_b 可能是 viewer。取
 * ``auth.workspaces`` 里与 ``auth.workspaceId`` 对应的那一条，而不是「取最高角色」——
 * 后者会让用户在只读空间里看到写操作入口，点下去拿 403，比不显示更糟。
 *
 * 找不到对应条目（老会话、或 /me 尚未拉取）时返回 null 角色 → 全部默认拒绝。
 * 这是刻意的：宁可少显示入口，不可多显示。authStore 里缺 ``organization_role``
 * 属于同类情况，由 ``needsProfileRefresh`` 检出并触发一次 /me 重取。
 */
export function actorFromAuth(auth) {
  const list = auth?.workspaces || [];
  const current = list.find((w) => w && w.workspace_id === auth?.workspaceId) || null;
  return {
    workspaceRole: current?.role ?? null,
    organizationRole: current?.organization_role ?? null,
    organizationRoleKnown: Boolean(current) && typeof current.organization_role !== 'undefined',
  };
}

/** StoredAuth 是否需要重取 /me：有令牌、有当前空间，但缺组织角色（2026-09-06 之前签发的记录）。 */
export function needsProfileRefresh(auth) {
  if (!auth?.accessToken) return false;
  const current = (auth.workspaces || []).find((w) => w && w.workspace_id === auth.workspaceId);
  if (!current) return false;
  return typeof current.organization_role === 'undefined';
}

