// web/src/pages/LoginPage.jsx
// 登录页（P0 邀请制，2026-08-13）：邮箱+密码；无公开注册入口。

import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext.jsx';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function LoginForm() {
  const { login, isLoggedIn } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setBusy(true);
    setError('');
    const res = await login(email.trim(), password);
    setBusy(false);
    if (res.ok) {
      globalThis.location.href = '/account';
      return;
    }
    if (res.status === 429) setError(zh ? '尝试次数过多，请稍后再试' : 'Too many attempts, please retry later');
    else if (res.status === 401) setError(zh ? '邮箱或密码错误' : 'Invalid email or password');
    else if (res.status === 403) setError(zh ? '该账户没有可用的工作空间' : 'No workspace access for this account');
    else setError(String(res.error || 'Login failed'));
  };

  useEffect(() => {
    if (isLoggedIn) {
      const t = setTimeout(() => { globalThis.location.href = '/account'; }, 300);
      return () => clearTimeout(t);
    }
    return undefined;
  }, [isLoggedIn]);

  if (isLoggedIn) {
    return (
      <div className="text-center text-sm text-[var(--color-muted)]">
        {zh ? '已登录，正在跳转…' : 'Already logged in, redirecting…'}
      </div>
    );
  }

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]';

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
          {zh ? '邮箱' : 'Email'}
        </label>
        <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} className={inputCls} autoComplete="email" />
      </div>
      <div>
        <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
          {zh ? '密码' : 'Password'}
        </label>
        <input type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} autoComplete="current-password" />
      </div>
      {error && (
        <div className="rounded-lg border border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/10 px-3 py-2 text-xs text-[var(--color-status-error)]">
          {error}
        </div>
      )}
      <button
        type="submit"
        disabled={busy}
        className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {busy ? (zh ? '登录中…' : 'Signing in…') : zh ? '登录' : 'Sign in'}
      </button>
      <div className="flex items-center justify-between pt-1 text-xs">
        <a href="/forgot" className="text-[var(--color-muted)] hover:text-[var(--color-text)]">
          {zh ? '忘记密码？' : 'Forgot password?'}
        </a>
        <span className="text-[var(--color-muted)]">
          {zh ? '邀请制，联系管理员获取邀请' : 'Invite-only, contact admin'}
        </span>
      </div>
      <SsoBlock zh={zh} />
    </form>
  );
}

/** SSO 入口（P1-7，2026-08-14）：组织已注册 OIDC provider 后可用；
 * 未开通时报 404 提示联系管理员。 */
function SsoBlock({ zh }) {
  const [open, setOpen] = useState(false);
  const [orgId, setOrgId] = useState('');
  const [provider, setProvider] = useState('google');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');

  const startSso = async () => {
    if (!orgId.trim()) { setError(zh ? '请输入组织 ID' : 'Organization ID required'); return; }
    setBusy(true); setError('');
    try {
      const redirectUri = `${globalThis.location.origin}/api/auth/oidc/callback`;
      const qs = new URLSearchParams({
        organization_id: orgId.trim(),
        provider_key: provider,
        redirect_uri: redirectUri,
      });
      const res = await fetch(`${API_BASE}/auth/oidc/start?${qs}`, { method: 'POST' });
      if (res.ok) {
        const body = await res.json();
        if (body.authorization_url) { globalThis.location.href = body.authorization_url; return; }
        setError(zh ? 'SSO 响应缺少授权地址' : 'SSO response missing authorization URL');
      } else if (res.status === 404) {
        setError(zh ? '该组织未开通 SSO，请联系管理员' : 'SSO not enabled for this organization');
      } else {
        setError(`SSO failed (${res.status})`);
      }
    } catch {
      setError(zh ? '网络错误，请稍后重试' : 'Network error, please retry');
    } finally {
      setBusy(false);
    }
  };

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]';

  return (
    <div className="border-t border-[var(--color-border)] pt-3">
      <button type="button" onClick={() => setOpen((v) => !v)} className="w-full text-center text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
        {zh ? `企业 SSO 登录 ${open ? '−' : '+'}` : `Enterprise SSO ${open ? '−' : '+'}`}
      </button>
      {open && (
        <div className="mt-3 space-y-2">
          <input placeholder={zh ? '组织 ID（org_xxx）' : 'Organization ID (org_xxx)'} value={orgId} onChange={(e) => setOrgId(e.target.value)} className={inputCls} />
          <select value={provider} onChange={(e) => setProvider(e.target.value)} className={inputCls}>
            <option value="google">Google</option>
            <option value="microsoft">Microsoft</option>
          </select>
          <button type="button" onClick={startSso} disabled={busy}
            className="w-full rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-semibold text-[var(--color-text)] hover:opacity-80 disabled:opacity-50">
            {busy ? (zh ? '跳转中…' : 'Redirecting…') : (zh ? '使用 SSO 登录' : 'Sign in with SSO')}
          </button>
          {error && <p className="text-center text-[11px] text-[var(--color-status-error)]">{error}</p>}
        </div>
      )}
    </div>
  );
}

export default function LoginPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  return (
    <AuthProvider>
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
        <div className="w-full max-w-sm">
          <div className="mb-6 text-center">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">AEMO Intelligence</div>
            <h1 className="mt-1 font-serif text-2xl text-[var(--color-text)]">{zh ? '登录' : 'Sign in'}</h1>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <LoginForm />
          </div>
          <div className="mt-4 text-center">
            <a href="/" className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">← {zh ? '返回市场分析' : 'Back to market analysis'}</a>
          </div>
        </div>
      </div>
    </AuthProvider>
  );
}
