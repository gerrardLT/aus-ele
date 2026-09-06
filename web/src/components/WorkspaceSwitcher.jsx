// web/src/components/WorkspaceSwitcher.jsx
// R1.5 顶栏工作空间切换器（2026-09-06）。
//
// 刻意不依赖 AuthContext：PageShell 用在 MarketPage 里，而 main.jsx 没有为市场分析页
// 包 AuthProvider（只有账户/登录类独立页面包了）。在这里 useAuth() 会直接抛错，
// 并把「匿名也能正常浏览」这条承诺绑上认证 provider。故本组件只读 authStore ——
// 与 agentApi、AnonymousNoticeBanner 读的是同一份存储，不会出现「切换器以为已登录、
// 请求却走匿名 bootstrap」的分叉。
//
// 零额外请求：workspaces 清单在登录时已由 /v1/account/me 落到 authStore，
// 这里只是把它渲染出来。每次进页面都拉一次 /me 会给匿名转登录后的首屏多挂一个 RTT。

import { useCallback, useState } from 'react';
import { getApiBase } from '../lib/apiBase.js';
import { getValidAccessToken, readAuth, tryRefreshToken, writeAuth } from '../lib/authStore.js';
import { loginSessionUrl, mergeSwitchedSession, switchableWorkspaces, workspaceLabel } from '../lib/workspaceSwitch.js';

const API_BASE = getApiBase();

export default function WorkspaceSwitcher({ lang = 'zh' }) {
  const zh = lang === 'zh';
  const [auth] = useState(() => readAuth());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);

  // 只有一条空间时整个组件不渲染：单选项下拉框不是功能，是噪音。
  // 判定放在所有 hook 之后 —— 放在之前会让 hook 调用数量随渲染变化，
  // React 直接报错（"Rendered fewer hooks than expected"），而用户只会在切空间时看到白屏。
  const workspaces = auth?.workspaces || [];
  const canSwitch = Boolean(auth?.accessToken) && switchableWorkspaces(auth).length > 0;

  const onChange = useCallback(async (event) => {
    const targetId = event.target.value;
    if (!targetId || targetId === auth.workspaceId) return;
    setBusy(true);
    setError(null);
    try {
      const token = getValidAccessToken() || (await tryRefreshToken());
      const res = await fetch(loginSessionUrl(API_BASE, targetId), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        const detail = await res.json().catch(() => ({}));
        setError(detail.detail || `HTTP ${res.status}`);
        setBusy(false);
        return;
      }
      const next = mergeSwitchedSession(readAuth(), await res.json(), Date.now());
      if (!next) {
        // 拒绝半写入：没有令牌的「已切换」状态会让后续每个请求 401，而界面仍显示已登录
        setError(zh ? '切换响应不完整，已保持原空间' : 'Incomplete switch response; stayed put');
        setBusy(false);
        return;
      }
      writeAuth(next);
      // 整页重载而不是就地 setState：市场分析页的全部数据都按 workspace 作用域拉取，
      // 就地换令牌会留下「新空间令牌 + 旧空间数据」的混合视图 —— 那比一次闪烁严重得多。
      globalThis.location.reload();
    } catch {
      setError(zh ? '网络错误' : 'Network error');
      setBusy(false);
    }
  }, [auth?.workspaceId, zh]);

  if (!canSwitch) return null;

  return (
    <div className="flex items-center gap-1">
      <select
        value={auth.workspaceId || ''}
        onChange={onChange}
        disabled={busy}
        aria-label={zh ? '切换工作空间' : 'Switch workspace'}
        className="max-w-[10rem] rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2 py-1 text-[11px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)] disabled:opacity-50"
      >
        {workspaces.map((w) => (
          <option key={w.workspace_id} value={w.workspace_id}>
            {workspaceLabel(w, zh)}
          </option>
        ))}
      </select>
      {error && (
        <span role="alert" className="text-[10px] text-[var(--color-status-error)]">
          {error}
        </span>
      )}
    </div>
  );
}
