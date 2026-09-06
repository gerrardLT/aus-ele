// web/src/lib/orgAdmin.test.js
// R1.4 组织管理页判据测试。
//
// 最有价值的一条是「读后端 org_routes.py 源码，把每个端点声明要求的组织权限抽出来，
// 与前端分段门控逐条比对」：前端门控错一次的后果是用户点进一个必然 403 的入口，
// 而这种错在纯前端测试里永远绿 —— 只有拿后端当参照物才抓得住。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ORG_INVITE_ROLES,
  ORG_SECTIONS,
  canManageOrganization,
  currentOrganization,
  describeOrgError,
  inviteAcceptEndpoint,
  inviteAcceptSessionReady,
  inviteScope,
  orgDomainVerificationUrl,
  orgInviteLink,
  organizationUrl,
  showOrgAdminEntry,
  visibleSections,
} from './orgAdmin.js';
import { ORGANIZATION_PERMISSIONS, WORKSPACE_PERMISSIONS } from './rbac.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ORG_ROUTES_SOURCE = fs.readFileSync(
  path.resolve(__dirname, '../../../backend/routes/org_routes.py'),
  'utf8'
);

const KNOWN_PERMISSIONS = new Set([
  'org_manage',
  'workspace_manage',
  'member_manage',
  'export',
  'read_audit',
]);

/** 从 org_routes.py 抽出 { '<method> <sub-path>': <permission> | null }。 */
function parseEndpointPermissions(source) {
  const decorator = /@router\.(get|post|put|delete)\(\s*"([^"]*)"/g;
  const hits = [...source.matchAll(decorator)];
  const table = {};
  hits.forEach((hit, index) => {
    const start = hit.index + hit[0].length;
    const end = index + 1 < hits.length ? hits[index + 1].index : source.length;
    const body = source.slice(start, end);
    const permission = /_require_org_permission\([^)]*?"([a-z_]+)"\s*\)/.exec(body);
    table[`${hit[1].toUpperCase()} ${hit[2]}`] = permission ? permission[1] : null;
  });
  return table;
}

const ENDPOINTS = parseEndpointPermissions(ORG_ROUTES_SOURCE);

test('org_routes source parses into a non-trivial endpoint/permission table', () => {
  const keys = Object.keys(ENDPOINTS);
  assert.ok(keys.length >= 12, `只解析出 ${keys.length} 个端点 —— 后端语法变了，本测试已失效`);
  const guarded = keys.filter((k) => ENDPOINTS[k]);
  assert.ok(guarded.length >= 6, '一个权限判定都没解析到，说明正则没匹配上');
});

test('every permission named in org_routes is one of the five known names', () => {
  for (const [endpoint, permission] of Object.entries(ENDPOINTS)) {
    if (permission === null) continue;
    assert.ok(
      KNOWN_PERMISSIONS.has(permission),
      `${endpoint} 要求未知权限名 "${permission}" —— 它不在后端 RBAC 表里，任何角色都拿不到`
    );
  }
});

test('frontend section gating covers exactly the permissions org_routes demands', () => {
  const requiredByBackend = new Set(Object.values(ENDPOINTS).filter(Boolean));
  const requiredByUi = new Set(ORG_SECTIONS.map((s) => s.permission).filter(Boolean));
  // 后端要求而前端没建模 → 那个能力在页面上没有对应门控，属于漏门。
  for (const permission of requiredByBackend) {
    assert.ok(requiredByUi.has(permission), `后端要求 ${permission}，前端 ORG_SECTIONS 未覆盖`);
  }
});

test('org endpoints are gated on the organization layer only', () => {
  // 后端语义：check_organization_permission 只读 organization_membership.role。
  // 这条断言锁住「前端不得用两层并集去门控组织入口」。
  const wsOwnerOnly = { workspaceRole: 'owner', organizationRole: 'org_member' };
  assert.deepEqual(visibleSections(wsOwnerOnly), ['overview']);
  assert.equal(canManageOrganization(wsOwnerOnly), false);

  // 正向对照一：同样的权限串在组织层授予时，段确实出现 —— 排除「永远只返回 overview」的假绿。
  assert.deepEqual(
    visibleSections({ workspaceRole: 'viewer', organizationRole: 'org_admin' }),
    ['overview', 'members', 'invites', 'workspaces', 'audit']
  );
  // 正向对照二：这个判别力之所以存在，是因为 ws owner 在工作空间层确实持有 member_manage。
  // 若哪天后端把它从 ws owner 移除，用并集门控就不会再出错，本测试的前提也随之消失。
  assert.ok(WORKSPACE_PERMISSIONS.owner.has('member_manage'));
});

test('org_owner is the only role that sees the domain section', () => {
  for (const role of Object.keys(ORGANIZATION_PERMISSIONS)) {
    const sections = visibleSections({ workspaceRole: null, organizationRole: role });
    assert.equal(
      sections.includes('domains'),
      ORGANIZATION_PERMISSIONS[role].has('org_manage'),
      `${role} 的域名段可见性与后端权限表不一致`
    );
  }
});

test('unknown or missing organization role degrades to overview only', () => {
  for (const actor of [
    {},
    { organizationRole: null },
    { organizationRole: 'org_something_invented' },
    { organizationRole: undefined, workspaceRole: undefined },
  ]) {
    assert.deepEqual(visibleSections(actor), ['overview'], `默认拒绝被破坏：${JSON.stringify(actor)}`);
    assert.equal(canManageOrganization(actor), false);
  }
});

test('currentOrganization reads the current workspace row, never a personal maximum', () => {
  const auth = {
    workspaceId: 'ws_b',
    workspaces: [
      { workspace_id: 'ws_a', organization_id: 'org_a', organization_role: 'org_owner', organization_name: 'A' },
      { workspace_id: 'ws_b', organization_id: 'org_b', organization_role: 'org_member', organization_name: 'B' },
    ],
  };
  const org = currentOrganization(auth);
  assert.equal(org.organizationId, 'org_b');
  assert.equal(org.organizationRole, 'org_member');
  assert.equal(org.organizationRoleKnown, true);

  // 当前空间不属于任何组织 → 整页无意义
  assert.equal(
    currentOrganization({ workspaceId: 'ws_x', workspaces: [{ workspace_id: 'ws_x' }] }),
    null
  );
  assert.equal(currentOrganization(null), null);
  assert.equal(currentOrganization({ workspaceId: 'missing', workspaces: [] }), null);
});

test('legacy StoredAuth without organization_role is flagged as unknown, not as "no role"', () => {
  // 真 org_owner 的老会话若被当成「无角色」，他会看到空页面且没有任何解释。
  const legacy = currentOrganization({
    workspaceId: 'ws_a',
    workspaces: [{ workspace_id: 'ws_a', organization_id: 'org_a', name: 'A' }],
  });
  assert.equal(legacy.organizationRole, null);
  assert.equal(legacy.organizationRoleKnown, false);
  // 显式 null 是「已知：确实没有组织角色」，与字段缺失不同。
  const explicit = currentOrganization({
    workspaceId: 'ws_a',
    workspaces: [{ workspace_id: 'ws_a', organization_id: 'org_a', organization_role: null }],
  });
  assert.equal(explicit.organizationRoleKnown, true);
});

test('invite link carries scope=org and the page reads it back', () => {
  assert.equal(orgInviteLink('https://x.test/', 'tok 1/2'), 'https://x.test/invite?token=tok%201%2F2&scope=org');
  assert.equal(inviteScope('?token=abc&scope=org'), 'org');
  assert.equal(inviteScope('?token=abc'), 'workspace');
  assert.equal(inviteScope(''), 'workspace');
  assert.equal(inviteScope(undefined), 'workspace');
  // scope=org 是字符串，任何其它值都不能把用户导到组织端点
  assert.equal(inviteScope('?scope=ORG'), 'workspace');
});

test('accepting an org invite logs in only when the backend hands back a landing point', () => {
  assert.equal(inviteAcceptEndpoint('/api', 'org'), '/api/v1/organizations/invites/accept');
  assert.equal(inviteAcceptEndpoint('/api', 'workspace'), '/api/v1/account/invites/accept');
  assert.equal(inviteAcceptEndpoint('/api', undefined), '/api/v1/account/invites/accept', '缺省必须是既有工作空间链路');

  // 判据取自响应而不是 scope：组织级邀请现在会补 workspace 成员身份，所以正常情形
  // 是可以自动登录的；「组织还没有任何工作空间」时才不行。写死 scope 会锁死旧行为。
  assert.equal(inviteAcceptSessionReady({ principal: { email: 'a@x' }, workspace: { workspace_id: 'ws1' } }), true);
  assert.equal(inviteAcceptSessionReady({ principal: { email: 'a@x' }, workspace_access_ready: false }), false);
  assert.equal(inviteAcceptSessionReady({ principal: {}, workspace: { workspace_id: 'ws1' } }), false);
  assert.equal(inviteAcceptSessionReady(null), false);
});

test('org admin entry shows for managers and for legacy sessions with an unknown role', () => {
  assert.equal(showOrgAdminEntry({ organizationRoleKnown: true, organizationRole: 'org_admin' }), true);
  assert.equal(showOrgAdminEntry({ organizationRoleKnown: true, organizationRole: 'org_owner' }), true);
  // 纯 org_member 进去什么也做不了，不该看到这个入口
  assert.equal(showOrgAdminEntry({ organizationRoleKnown: true, organizationRole: 'org_member' }), false);
  assert.equal(showOrgAdminEntry({ organizationRoleKnown: true, organizationRole: 'org_billing_viewer' }), false);
  // 角色未知（2026-09-06 前的老会话）必须放行：解释文字在页面里，门留在门外就永远看不到。
  assert.equal(showOrgAdminEntry({ organizationRoleKnown: false, organizationRole: null }), true);
  assert.equal(showOrgAdminEntry(null), false, '当前空间不属于任何组织时不放行');
});

test('the accept endpoint the frontend calls is one the backend really mounts', () => {
  // 前端拼出的路径必须出现在从后端源码解析出的端点表里 —— 否则这是一个 404 的表单。
  const url = inviteAcceptEndpoint('/api', 'org');
  const prefix = '/api/v1/organizations';
  assert.ok(url.startsWith(prefix), `组织端点前缀与已验证过的挂载点不一致：${url}`);
  const subPath = url.slice(prefix.length);
  assert.ok(Object.keys(ENDPOINTS).includes(`POST ${subPath}`), `后端 org_routes 里没有 POST ${subPath}`);
});

test('org invite role list never contains org_owner', () => {
  // 一封误发的邀请就能把组织送出去。owner 只能经 owner-transfer 产生。
  assert.ok(!ORG_INVITE_ROLES.includes('org_owner'));
  assert.deepEqual([...ORG_INVITE_ROLES].sort(), ['org_admin', 'org_billing_viewer', 'org_member'].sort());
});

test('url builders encode identifiers and match the mounted route shapes', () => {
  assert.equal(organizationUrl('/api', 'org 1'), '/api/v1/organizations/org%201');
  assert.equal(
    orgDomainVerificationUrl('/api', 'o1', 'd1', 'confirm'),
    '/api/v1/organizations/o1/domains/d1/verification/verify'
  );
  assert.equal(
    orgDomainVerificationUrl('/api', 'o1', 'd1', 'begin'),
    '/api/v1/organizations/o1/domains/d1/verification'
  );
});

test('403 wording tells the user the one thing they can act on', () => {
  assert.match(describeOrgError({ detail: 'Organization permission denied' }, 403, true), /切换/);
  assert.match(describeOrgError({}, 401, true), /登录/);
  assert.equal(describeOrgError({ detail: 'Invite has expired' }, 400, true), 'Invite has expired');
  assert.match(describeOrgError({}, 500, true), /Request failed \(500\)/);
});
