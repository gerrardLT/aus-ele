// web/src/hooks/usePermissions.js
// R1.6 权限可见性 hook（2026-09-06）：把 lib/rbac.js 接到当前登录记录上。
//
// 判据全在 lib/rbac.js（有 node:test 与后端源码漂移检测）；这里只负责「读哪份状态」。
// 允许直接传入 AuthContext 的 auth：不在 AuthProvider 子树里的位置（顶栏、未来的 TopBar）
// 不传即可回落到 readAuth()，而在树里的调用方传进来才能跟着会话更新走。
//
// 依赖数组刻意是 [workspaceId, workspaces] 而不是 []：权限是**逐工作空间**的，切空间或
// 成员角色被改后必须重算。曾经写成 []，表现是「刚被降权的人仍然看到管理入口，直到刷新页面」
// —— 而原来那批页面是直接每次 render 从 auth 里查 role 的，所以 [] 是一次可见的回退。

import { useCallback, useMemo } from 'react';
import {
  actorFromAuth,
  can,
  canInOrganization,
  canInWorkspace,
  permissionsOf,
} from '../lib/rbac.js';
import { readAuth } from '../lib/authStore.js';

export function usePermissions(auth) {
  const source = auth || readAuth();
  const workspaceId = source?.workspaceId;
  const workspaces = source?.workspaces;
  const actor = useMemo(
    () => actorFromAuth({ workspaceId, workspaces }),
    [workspaceId, workspaces],
  );
  const check = useCallback((permission) => can(actor, permission), [actor]);
  // 分层版本才是日常该用的：后端 check_workspace_permission / check_organization_permission
  // 各读各的角色，用并集版 can() 去门控一个单层端点会造出「前端显示、后端 403」的分裂。
  const checkWorkspace = useCallback((permission) => canInWorkspace(actor, permission), [actor]);
  const checkOrganization = useCallback((permission) => canInOrganization(actor, permission), [actor]);
  return {
    actor,
    can: check,
    canInWorkspace: checkWorkspace,
    canInOrganization: checkOrganization,
    permissions: permissionsOf(actor),
  };
}
