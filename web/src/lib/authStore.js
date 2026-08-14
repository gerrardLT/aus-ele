// web/src/lib/authStore.js
// 认证状态持久化（localStorage）——AuthContext 与 agentApi 共享。
// 登录后存储会话（access token + session token）；agentApi 优先使用用户
// token，未登录时回落到匿名 web-session bootstrap（不破坏匿名访问）。

import { getApiBase } from './apiBase.js';

export const AUTH_STORAGE_KEY = 'aus_auth_v1';

/**
 * @typedef {Object} StoredAuth
 * @property {string} accessToken - JWT access token（Bearer）
 * @property {number} accessTokenExp - epoch 秒
 * @property {string} sessionToken - 用于 refresh/logout 的会话令牌
 * @property {string} workspaceId
 * @property {{principal_id:string, email:string, display_name?:string}} principal
 * @property {Array<{workspace_id:string, name:string, role:string, organization_name?:string}>} [workspaces]
 */

export function readAuth() {
  try {
    const raw = globalThis.localStorage?.getItem(AUTH_STORAGE_KEY);
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

export function writeAuth(auth) {
  try {
    if (auth) globalThis.localStorage?.setItem(AUTH_STORAGE_KEY, JSON.stringify(auth));
    else globalThis.localStorage?.removeItem(AUTH_STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function clearAuth() {
  writeAuth(null);
}

/** 当前有效（未过期）的 access token；否则 null。 */
export function getValidAccessToken() {
  const auth = readAuth();
  if (!auth?.accessToken) return null;
  const now = Math.floor(Date.now() / 1000);
  if (auth.accessTokenExp && auth.accessTokenExp <= now + 30) return null;
  return auth.accessToken;
}

/**
 * 用 session token 静默刷新 access token；成功则更新存储并返回新 token。
 * @returns {Promise<string|null>}
 */
export async function tryRefreshToken() {
  const auth = readAuth();
  if (!auth?.sessionToken) return null;
  try {
    const res = await fetch(`${getApiBase()}/auth/refresh`, {
      method: 'POST',
      headers: { 'X-Session-Token': auth.sessionToken },
    });
    if (!res.ok) return null;
    const d = await res.json();
    const updated = {
      ...auth,
      accessToken: d.access_token,
      accessTokenExp: Math.floor(Date.now() / 1000) + (d.access_token_expires_in || 3600),
      sessionToken: d.session_token || auth.sessionToken,
    };
    writeAuth(updated);
    return updated.accessToken;
  } catch {
    return null;
  }
}
