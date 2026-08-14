// web/src/pages/LoginPage.jsx
// 登录页（P0 邀请制，2026-08-13）：邮箱+密码；无公开注册入口。

import { useEffect, useState } from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext.jsx';

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
      <p className="pt-2 text-center text-xs text-[var(--color-muted)]">
        {zh ? '本平台为邀请制，如需账户请联系管理员获取邀请链接' : 'Invite-only platform. Contact your administrator for an invite link.'}
      </p>
    </form>
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
