// web/src/lib/rbac.test.js
// R1.6 权限镜像测试（node:test，唯一硬阻断门）。
//
// 锁两件事：
// 1. 判定语义：默认拒绝、无角色继承、未知形状不放大权限；
// 2. **与后端漂移**：直接读 backend/access_control.py 源码解析两个权限表，逐角色逐权限比对。
//    镜像层最坏的失败模式不是算错，而是后端加了一项权限、前端静默地永远不显示该入口 ——
//    那种 bug 没有报错、没有红测试，只有用户说「找不到导出按钮」。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import {
  ORGANIZATION_PERMISSIONS,
  WORKSPACE_PERMISSIONS,
  actorFromAuth,
  can,
  canAll,
  canInOrganization,
  canInWorkspace,
  needsProfileRefresh,
  normalizeActor,
  permissionsOf,
} from './rbac.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const BACKEND_SOURCE = path.resolve(__dirname, '../../../backend/access_control.py');

/** 解析 ``ROLE_PERMISSIONS = { "owner": {"a", "b"}, "viewer": set() }`` 形态的字面量。 */
function parseBackendTable(source, name) {
  const block = new RegExp(`${name} = \\{([\\s\\S]*?)\\n\\}`).exec(source);
  assert.ok(block, `backend/access_control.py 中找不到 ${name} 字面量 —— 后端改名了，前端镜像必须同步`);
  const table = {};
  for (const line of block[1].split('\n')) {
    const entry = /^\s*"([a-z_]+)":\s*(?:\{([^}]*)\}|set\(\))/.exec(line);
    if (!entry) continue;
    table[entry[1]] = new Set(
      (entry[2] || '')
        .split(',')
        .map((token) => token.trim().replace(/^"|"$/g, ''))
        .filter(Boolean),
    );
  }
  return table;
}

const backendSource = fs.readFileSync(BACKEND_SOURCE, 'utf8');
const backendWorkspaceTable = parseBackendTable(backendSource, 'ROLE_PERMISSIONS');
const backendOrgTable = parseBackendTable(backendSource, 'ORG_ROLE_PERMISSIONS');

function asNames(set) {
  return [...set].sort();
}

test('frontend permission tables match backend exactly', () => {
  for (const [label, frontend, backend] of [
    ['ROLE_PERMISSIONS', WORKSPACE_PERMISSIONS, backendWorkspaceTable],
    ['ORG_ROLE_PERMISSIONS', ORGANIZATION_PERMISSIONS, backendOrgTable],
  ]) {
    assert.deepEqual(Object.keys(frontend).sort(), Object.keys(backend).sort(), `${label}: 角色集合漂移`);
    for (const role of Object.keys(backend)) {
      assert.deepEqual(
        asNames(frontend[role]),
        asNames(backend[role]),
        `${label}[${role}]: 权限集合漂移`,
      );
    }
  }
});

test('backend uses only the five documented permission names', () => {
  // 拼错权限串是镜像层的头号静默故障：后端写 "export_data"、前端判 "export"，
  // 按钮就永久消失。把合法权限名固定成白名单，新增项必须在这里显式承认。
  const known = new Set(['org_manage', 'workspace_manage', 'member_manage', 'export', 'read_audit']);
  const observed = new Set([...asNames(backendWorkspaceTable.owner), ...asNames(backendOrgTable.org_owner)]);
  for (const table of [backendWorkspaceTable, backendOrgTable]) {
    for (const role of Object.keys(table)) {
      for (const permission of table[role]) {
        assert.ok(known.has(permission), `${role} 出现了未登记权限名 ${permission}`);
        observed.add(permission);
      }
    }
  }
  assert.equal(observed.size, 5);
});

test('viewer and org_member hold nothing, unknown roles default deny', () => {
  assert.deepEqual(permissionsOf({ role: 'viewer' }), []);
  assert.deepEqual(permissionsOf({ organizationRole: 'org_member' }), []);
  assert.equal(can({ role: 'superuser' }, 'export'), false);
  assert.equal(can(null, 'export'), false);
  assert.equal(can(undefined, 'export'), false);
  assert.equal(can({}, 'export'), false);
});

test('role hierarchy is NOT implied: owner passes only what backend lists', () => {
  // analyst 只有 export：它不能 manage members，尽管它在直觉上「比 viewer 高」。
  assert.equal(can({ role: 'analyst' }, 'export'), true);
  assert.equal(can({ role: 'analyst' }, 'member_manage'), false);
  assert.equal(can({ role: 'viewer' }, 'export'), false);
  // 反向对照：owner 确实持 member_manage，否则上面的 false 只是因为整表为空。
  assert.equal(can({ role: 'owner' }, 'member_manage'), true);
});

test('workspace and organization layers merge without either granting the other', () => {
  // 组织层 org_owner 含 org_manage，workspace 层除 owner 外都不含 —— 合并后应成立
  assert.equal(can({ role: 'viewer', organizationRole: 'org_owner' }, 'org_manage'), true);
  // 反之 workspace admin 拿不到 org_manage：后端 check_organization_permission 只看组织角色
  assert.equal(can({ role: 'admin' }, 'org_manage'), false);
});

test('layered predicates never imply each other (backend has no cross-layer grant)', () => {
  // 后端 check_workspace_permission 只读 workspace_membership.role，
  // check_organization_permission 只读 organization_membership.role，两层之间没有蕴含。
  // 用并集版 can() 去门控组织入口会让「ws owner + org_member」看到入口后必吃 403。
  const wsOwnerOrgMember = { workspaceRole: 'owner', organizationRole: 'org_member' };
  assert.equal(canInWorkspace(wsOwnerOrgMember, 'member_manage'), true);
  assert.equal(canInOrganization(wsOwnerOrgMember, 'member_manage'), false);
  assert.equal(can(wsOwnerOrgMember, 'member_manage'), true, '并集版仍为 true —— 所以才更需要分层版');

  const wsViewerOrgAdmin = { workspaceRole: 'viewer', organizationRole: 'org_admin' };
  assert.equal(canInWorkspace(wsViewerOrgAdmin, 'member_manage'), false);
  assert.equal(canInOrganization(wsViewerOrgAdmin, 'member_manage'), true);

  // can() 的定义就是两层并集；这条锁住它不会偷偷变成第三种语义。
  for (const actor of [wsOwnerOrgMember, wsViewerOrgAdmin, { workspaceRole: 'owner', organizationRole: 'org_owner' }]) {
    for (const permission of ['org_manage', 'workspace_manage', 'member_manage', 'export', 'read_audit']) {
      assert.equal(
        can(actor, permission),
        canInWorkspace(actor, permission) || canInOrganization(actor, permission),
        `can() 与分层并集不一致：${JSON.stringify(actor)} / ${permission}`,
      );
    }
  }
});

test('layered predicates reject malformed actors without throwing', () => {
  // 注意：裸字符串是**受支持**的 actor 简写（normalizeActor('analyst') → workspaceRole），
  // 所以这里只能用非法角色名，不能用字符串本身当「畸形输入」。
  for (const bad of [null, undefined, {}, 'superuser', { workspaceRole: 42 }, { workspaceRole: {} }]) {
    assert.equal(canInWorkspace(bad, 'export'), false, `默认拒绝被破坏：${JSON.stringify(bad)}`);
    assert.equal(canInOrganization(bad, 'export'), false);
  }
  // 分层版同样不认非法权限名（与 can() 同一道白名单）
  assert.equal(canInOrganization({ organizationRole: 'org_owner' }, 'owner_manage'), false);
});

test('accepts raw actor dicts as returned by the backend', () => {
  const actor = {
    membership: { role: 'admin' },
    organization_membership: { role: 'org_admin' },
  };
  assert.equal(can(actor, 'member_manage'), true);
  assert.equal(can(actor, 'org_manage'), false);
  assert.deepEqual(normalizeActor(actor), { workspaceRole: 'admin', organizationRole: 'org_admin' });
  assert.deepEqual(normalizeActor('analyst'), { workspaceRole: 'analyst', organizationRole: null });
});

test('blank or non-string permission never matches', () => {
  assert.equal(can({ role: 'owner' }, ''), false);
  assert.equal(can({ role: 'owner' }, null), false);
  assert.equal(can({ role: 'owner' }, undefined), false);
  assert.equal(can({ role: 'owner' }, 12), false);
});

test('canAll requires every permission', () => {
  assert.equal(canAll({ role: 'admin' }, ['member_manage', 'read_audit']), true);
  assert.equal(canAll({ role: 'admin' }, ['member_manage', 'org_manage']), false);
  assert.equal(canAll({ role: 'viewer' }, []), true, '空需求恒真：调用方用它表示「无额外要求」');
});

test('permissions are resolved per workspace, never as a personal maximum', () => {
  // 同一个人在两个空间角色不同：当前在 viewer 空间，就不能出现 owner 才看得到的入口。
  const auth = {
    accessToken: 't',
    workspaceId: 'ws_readonly',
    workspaces: [
      { workspace_id: 'ws_mine', name: 'Mine', role: 'owner', organization_role: 'org_owner' },
      { workspace_id: 'ws_readonly', name: 'Shared', role: 'viewer', organization_role: 'org_member' },
    ],
  };
  assert.equal(can(actorFromAuth(auth), 'member_manage'), false);
  // 正向对照：切到 owner 空间后同一函数必须放行，否则上面的 false 只是因为整条链路坏了
  assert.equal(can(actorFromAuth({ ...auth, workspaceId: 'ws_mine' }), 'member_manage'), true);
});

test('actor folds to deny-all when the current workspace is not in the list', () => {
  const actor = actorFromAuth({ accessToken: 't', workspaceId: 'ws_gone', workspaces: [] });
  assert.deepEqual(actor, { workspaceRole: null, organizationRole: null, organizationRoleKnown: false });
  assert.equal(can(actor, 'export'), false);
  assert.equal(can(actorFromAuth(null), 'export'), false);
});

test('stored sessions predating organization_role are flagged for one profile refresh', () => {
  const withOrg = {
    accessToken: 't',
    workspaceId: 'ws_a',
    workspaces: [{ workspace_id: 'ws_a', role: 'owner', organization_role: 'org_owner' }],
  };
  const legacy = {
    accessToken: 't',
    workspaceId: 'ws_a',
    workspaces: [{ workspace_id: 'ws_a', role: 'owner' }],
  };
  assert.equal(needsProfileRefresh(withOrg), false);
  assert.equal(needsProfileRefresh(legacy), true);
  // 显式 null 是「后端确认无组织成员关系」，属于已知，不该反复刷新
  assert.equal(needsProfileRefresh({ ...legacy, workspaces: [{ workspace_id: 'ws_a', role: 'owner', organization_role: null }] }), false);
  assert.equal(needsProfileRefresh(null), false);
  assert.equal(needsProfileRefresh({ workspaceId: 'ws_a', workspaces: [{ workspace_id: 'ws_a' }] }), false, '匿名态无需刷新');
});

// ---------------------------------------------------------------------------
// 下面是「镜像层有没有真的被用上」的常驻检查（2026-09-06）。
// 判单测自己绿没有意义：lib/rbac.js 可以完美镜像后端，而页面继续各自写 role === 'owner'
// —— 那种状态下这套权限层是死代码，漂移检测全绿但没人受益。
// ---------------------------------------------------------------------------

const APP_SRC = path.resolve(__dirname, '..');

/** 递归收集 web/src 下的应用源码（排除测试与本仓约定的 workspace 目录）。 */
function appSources(dir) {
  const found = [];
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (entry.name === 'node_modules' || entry.name === '__tests__') continue;
      found.push(...appSources(full));
    } else if (/\.jsx?$/.test(entry.name) && !/\.test\.jsx?$/.test(entry.name)) {
      found.push([path.relative(APP_SRC, full).replace(/\\/g, '/'), fs.readFileSync(full, 'utf8')]);
    }
  }
  return found;
}

const sources = appSources(APP_SRC);

test('pages gate workspace admin actions through rbac instead of ad-hoc role strings', () => {
  // 保留裸角色比较的地方逐条登记并写理由；新增项必须一起来一个理由。
  // 之所以不是「一律禁止」：AccountPage 的套餐下拉是 **owner 独有**，而 admin 同样持有
  // workspace_manage —— 换成权限名门控会当场给 admin 开出改套餐入口，那是行为变更，不是重构。
  const ROLE_LITERAL_ALLOWLIST = {
    'pages/AccountPage.jsx': 'owner-only 订阅切换：admin 持 workspace_manage 但不应改套餐',
  };
  const literal = /role\s*===\s*['"](?:owner|admin)['"]|role\s*!==\s*['"]owner['"]/g;
  const seen = new Set();
  for (const [file, source] of sources) {
    const hits = source.match(literal) || [];
    if (!hits.length) continue;
    seen.add(file);
    assert.ok(
      ROLE_LITERAL_ALLOWLIST[file],
      `${file} 里出现硬编码角色比较（${hits[0]}），改走 usePermissions/canInWorkspace`,
    );
  }
  // 死 allowlist 也要报：被登记的文件后来若已改走权限名，这条理由就该一起删掉，
  // 否则下一轮读到它的人会以为那里还有特例，特例清单只会越滚越大。
  for (const file of Object.keys(ROLE_LITERAL_ALLOWLIST)) {
    assert.ok(seen.has(file), `allowlist 里的 ${file} 已不再硬编码角色，请删除该登记`);
  }
});

test('permission names passed to rbac are ones the backend actually grants', () => {
  // 拼错权限名不会报错，只会让入口永久消失（can* 对未知名一律 false）。
  // 所以白名单要扫**调用点**，光校验 tables 挡不住 canInWorkspace('member_mangage')。
  const granted = new Set([
    'org_manage', 'workspace_manage', 'member_manage', 'export', 'read_audit',
  ]);
  const callSite = /\bcan(?:InWorkspace|InOrganization|All)?\s*\(\s*(?:'([a-z_]+)'|"([a-z_]+)")/g;
  let observed = 0;
  for (const [file, source] of sources) {
    callSite.lastIndex = 0;
    let match;
    while ((match = callSite.exec(source))) {
      const permission = match[1] || match[2];
      assert.ok(granted.has(permission), `${file}: 未登记的权限名 "${permission}" 会静默判 false`);
      observed += 1;
    }
  }
  assert.ok(observed >= 4, `调用点扫描没抓到预期数量的权限判定（${observed}）—— 正则或目录结构变了`);
});

test('the permission hook has live consumers', () => {
  // 反向锁死 hook 变回「有代码没读者」：只有确实被页面 import 才算接线完成。
  const consumers = sources
    .filter(([, source]) => /from\s+['"][^'"]*hooks\/usePermissions/.test(source))
    .map(([file]) => file);
  for (const expected of [
    'pages/MembersPage.jsx',
    'pages/ApiKeysPage.jsx',
    'pages/AlertRulesPage.jsx',
    'pages/ReportsPage.jsx',
  ]) {
    assert.ok(consumers.includes(expected), `${expected} 应经 usePermissions 取权限`);
  }
});

