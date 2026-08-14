// web/src/contexts/AuthContext.jsx
// 认证上下文（P0 账户中心，2026-08-13）：登录/受邀注册/登出/当前用户。
// 持久化经 authStore（localStorage），agentApi 从同一存储读用户 token。

import { createContext, useCallback, useContext, useState } from 'react';
import { getApiBase } from '../lib/apiBase.js';
import { clearAuth, getValidAccessToken, readAuth, tryRefreshToken, writeAuth } from '../lib/authStore.js';

const API_BASE = getApiBase();
const AuthContext = createContext(null);

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
      const session = await res.json();
      const next = sessionToAuth(session);
      const me = await fetchMe(next.accessToken);
      if (me) {
        next.principal = me.principal;
        next.workspaces = me.workspaces || [];
      }
      writeAuth(next);
      setAuth(next);
      return { ok: true };
    } catch {
      return { ok: false, error: readLangIsZh() ? '网络错误，请稍后重试' : 'Network error, please retry' };
    }
  }, []);

  /** 接受邀请（注册）：成功后自动登录。网络错误统一兜底。 */
  const acceptInvite = useCallback(async (inviteToken, displayName, password) => {
    try {
      // JSON body 端点（密码不进 URL，代码审查修复 2026-08-13）
      const res = await fetch(`${API_BASE}/v1/account/invites/accept`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ invite_token: inviteToken, display_name: displayName, password }),
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        return { ok: false, status: res.status, error: err.detail || `Invite accept failed (${res.status})` };
      }
      const accepted = await res.json();
      const email = accepted?.principal?.email;
      const workspaceId = accepted?.workspace?.workspace_id;
      if (!email || !workspaceId) return { ok: false, error: 'Invite response incomplete' };
      return login(email, password, workspaceId);
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
  }, []);

  /** 取当前有效 token（过期时静默刷新）。 */
  const getToken = useCallback(async () => {
    const valid = getValidAccessToken();
    if (valid) return valid;
    return tryRefreshToken();
  }, []);

  const value = {
    auth,
    isLoggedIn: Boolean(auth?.accessToken),
    login,
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
