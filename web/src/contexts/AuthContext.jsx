// web/src/contexts/AuthContext.jsx
// 认证上下文（P0 账户中心，2026-08-13）：登录/受邀注册/登出/当前用户。
// 持久化经 authStore（localStorage），agentApi 从同一存储读用户 token。

import { createContext, useCallback, useContext, useEffect, useState } from 'react';
import { getApiBase } from '../lib/apiBase.js';
import { clearAuth, getValidAccessToken, readAuth, tryRefreshToken, writeAuth } from '../lib/authStore.js';
import { inviteAcceptEndpoint, inviteAcceptSessionReady } from '../lib/orgAdmin.js';
import { needsProfileRefresh } from '../lib/rbac.js';
import { identify, resetIdentity } from '../lib/analytics.js';

const API_BASE = getApiBase();
const AuthContext = createContext(null);
const APP_ENV = import.meta.env || {};

function readLangIsZh() {
  try { return (globalThis.localStorage?.getItem('app_lang') || 'zh') === 'zh'; } catch { return true; }
}

function sessionToAuth(sessionData) {
  return {
    accessToken: sessionData.access_token,
    accessTokenExp: Math.floor(Date.now() / 1000) + (sessionData.access_token_expires_in || 3600),
    sessionToken: sessionData.session_token,
    workspaceId: sessionData.workspace_id,
    principal: null,
    workspaces: [],
  };
}

async function fetchMe(accessToken) {
  const res = await fetch(`${API_BASE}/v1/account/me`, {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
  if (!res.ok) return null;
  return res.json();
}

export function AuthProvider({ children }) {
  const [auth, setAuth] = useState(() => readAuth());

  /**
   * 把一个「后端已签发的会话」落地为本地登录态。
   *
   * 密码登录、邀请接受、注册、社交回调四条链路的后端响应形状本来就相同（``/register``
   * 刻意复用 login 的返回形状），因此这里只留一份落地实现。多份实现必然分叉 —— 上一版
   * ``switchWorkspace`` 就已经是 ``login`` 的复制粘贴，再加社交链路会是第三份。
   *
   * @param {object} sessionData 需含 access_token / session_token / workspace_id
   */
  const adoptSession = useCallback(async (sessionData) => {
    if (!sessionData?.access_token || !sessionData?.session_token || !sessionData?.workspace_id) {
      return { ok: false, error: readLangIsZh() ? '会话信息不完整' : 'Incomplete session response' };
    }
    const next = sessionToAuth(sessionData);
    const me = await fetchMe(next.accessToken);
    if (me) {
      next.principal = me.principal;
      next.workspaces = me.workspaces || [];
    }
    writeAuth(next);
    setAuth(next);
    // 关联身份只在「拿到 /me 之后」做一次：用 principal_id 而不是邮箱，第三方分析服务里
    // 因此永远不出现可直接联系到人的标识（R5.1 / /legal/dpa 第 4 条的口径）。
    if (next.principal?.principal_id) {
      identify(next.principal.principal_id, { workspace_count: next.workspaces.length }, APP_ENV);
    }
    // 字段缺失时必须回 null（未知），不能回 false（未验证）：/me 目前不返回
    // email_verified_at，写死 Boolean(...) 会让每个已登录用户都被判成「未验证」——
    // 那是一句谎话，而下游的横幅靠这个位决定是否催人去验证邮箱。
    const verifiedField = next.principal?.email_verified_at;
    return {
      ok: true,
      emailVerified: typeof verifiedField === 'undefined' ? null : Boolean(verifiedField),
    };
  }, []);

  /** 登录（workspace 可缺省，后端自动取首个所属）。网络错误统一兜底，表单不会卡死。 */
  const login = useCallback(async (email, password, workspaceId) => {
    try {
      const res = await fetch(`${API_BASE}/v1/account/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email, password, workspace_id: workspaceId || undefined }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return { ok: false, status: res.status, error: err.detail || `Login failed (${res.status})` };
      }
      return await adoptSession(await res.json());
    } catch {
      return { ok: false, error: readLangIsZh() ? '网络错误，请稍后重试' : 'Network error, please retry' };
    }
  }, [adoptSession]);

  /**
   * 接受邀请（注册）：成功后自动登录。网络错误统一兜底。
   *
   * `scope` 取 'workspace' | 'org'（R1.4，2026-09-06）。两条链路只在这里留**一份**实现：
   * 请求体字段同名、落地动作同为「拿 email+password 换会话」，分成两个函数就会分叉 ——
   * 本仓已经为此付过学费（switchWorkspace 曾是 login 的复制粘贴）。
   */
  const acceptInvite = useCallback(async (inviteToken, displayName, password, scope = 'workspace') => {
    try {
      // JSON body 端点（密码不进 URL，代码审查修复 2026-08-13）
      const res = await fetch(inviteAcceptEndpoint(API_BASE, scope), {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_token: inviteToken, display_name: displayName, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return { ok: false, status: res.status, error: err.detail || `Invite accept failed (${res.status})` };
      }
      const accepted = await res.json();
      // 判据取自 lib（有 node:test），不在这里再写一遍「什么算能落地」——
      // 两处判据迟早会分叉，而分叉的表现是「一处自动登录、另一处停在原地」。
      if (!inviteAcceptSessionReady(accepted)) {
        // 邀请已被后端接受（成员关系已建立），只是没有可登录的落地点：组织级邀请在
        // 「该组织还没有任何工作空间」时会走到这里。报「失败」是错的 —— 用户会重复
        // 点接受并撞上「邀请无效」；必须让页面明确说「去登录」。
        return {
          ok: false,
          acceptedNoWorkspace: true,
          email: accepted?.principal?.email || null,
          error: accepted?.workspace_access_ready === false
            ? 'organization has no workspace yet'
            : 'Invite response incomplete',
        };
      }
      return login(accepted.principal.email, password, accepted.workspace.workspace_id);
    } catch {
      return { ok: false, error: readLangIsZh() ? '网络错误，请稍后重试' : 'Network error, please retry' };
    }
  }, [login]);

  const logout = useCallback(async () => {
    const stored = readAuth();
    try {
      if (stored?.sessionToken) {
        await fetch(`${API_BASE}/auth/logout`, {
          method: 'POST',
          headers: { 'X-Session-Token': stored.sessionToken },
        });
      }
    } catch {
      /* 登出尽力而为 */
    }
    clearAuth();
    setAuth(null);
    // 登出必须切断分析侧身份，否则同一浏览器上换的人会被并进前一个人的时间线。
    resetIdentity(APP_ENV);
  }, []);

  /** 取当前有效 token（过期时静默刷新）。 */
  const getToken = useCallback(async () => {
    const valid = getValidAccessToken();
    if (valid) return valid;
    return tryRefreshToken();
  }, []);

  /** 多工作空间切换（2026-08-14）：免密码，签发新会话。 */
  const switchWorkspace = useCallback(async (workspaceId) => {
    try {
      const token = getValidAccessToken() || (await tryRefreshToken());
      const res = await fetch(`${API_BASE}/v1/account/workspaces/${workspaceId}/login-session`, {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return { ok: false, error: err.detail || `Switch failed (${res.status})` };
      }
      const session = await res.json();
      return await adoptSession(session);
    } catch {
      return { ok: false, error: readLangIsZh() ? '网络错误，请稍后重试' : 'Network error, please retry' };
    }
  }, [adoptSession]);

  /**
   * 老会话补一次 /me（R1.6，2026-09-06）。
   *
   * ``organization_role`` 是本轮才加进 /me 响应的字段，因此改动上线前签发的 localStorage
   * 记录里没有它 —— 而组织管理入口的可见性正好依赖这个字段。不补的话，最坏情况是
   * 一个货真价实的 org_owner 打不开组织设置，且界面上没有任何解释（他只是「看不到一个
   * 从来没见过的按钮」）。判据是纯函数 needsProfileRefresh，只在字段缺失时触发一次。
   */
  useEffect(() => {
    const stored = readAuth();
    if (!needsProfileRefresh(stored)) return undefined;
    let cancelled = false;
    (async () => {
      const me = await fetchMe(stored.accessToken);
      if (cancelled || !me?.workspaces) return;
      const next = { ...stored, workspaces: me.workspaces, principal: me.principal || stored.principal };
      writeAuth(next);
      setAuth(next);
    })();
    return () => { cancelled = true; };
  }, []);

  const value = {
    auth,
    isLoggedIn: Boolean(auth?.accessToken),
    login,
    adoptSession,
    switchWorkspace,
    acceptInvite,
    logout,
    getToken,
  };

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
