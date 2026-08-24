// web/src/pages/ForgotPasswordPage.jsx
// 忘记密码（2026-08-14）：/forgot 请求重置邮件；/reset?token=xxx 设置新密码。

import { useState } from 'react';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function ForgotPasswordPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  const params = new URLSearchParams(globalThis.location.search || '');
  const token = params.get('token') || '';
  const isReset = globalThis.location.pathname.startsWith('/reset') && Boolean(token);

  const [email, setEmail] = useState('');
  const [pw, setPw] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const requestReset = async (e) => {
    e.preventDefault();
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/v1/account/password/reset-request`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: email.trim() }),
      });
      if (res.ok) {
        setMsg({ ok: true, text: zh ? '若该邮箱已注册，重置链接已发送（30 分钟内有效），请查收邮件' : 'If the email exists, a reset link has been sent (valid 30 min)' });
      } else {
        setMsg({ ok: false, text: `Failed (${res.status})` });
      }
    } catch {
      setMsg({ ok: false, text: zh ? '网络错误，请稍后重试' : 'Network error, please retry' });
    } finally {
      setBusy(false);
    }
  };

  const doReset = async (e) => {
    e.preventDefault();
    if (pw !== confirm) { setMsg({ ok: false, text: zh ? '两次密码不一致' : 'Passwords do not match' }); return; }
    setBusy(true); setMsg(null);
    try {
      const res = await fetch(`${API_BASE}/v1/account/password/reset-confirm`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token, new_password: pw }),
      });
      if (res.ok) {
        setMsg({ ok: true, text: zh ? '密码已重置，请使用新密码登录' : 'Password reset. Sign in with your new password' });
      } else {
        const err = await res.json().catch(() => ({}));
        setMsg({ ok: false, text: zh ? String(err.detail || '重置失败') : String(err.detail || 'Reset failed') });
      }
    } catch {
      setMsg({ ok: false, text: zh ? '网络错误，请稍后重试' : 'Network error, please retry' });
    } finally {
      setBusy(false);
    }
  };

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]';

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">AEMO Intelligence</div>
          <h1 className="mt-1 font-serif text-2xl text-[var(--color-text)]">
            {isReset ? (zh ? '设置新密码' : 'Set new password') : (zh ? '忘记密码' : 'Forgot password')}
          </h1>
        </div>
        <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          {isReset ? (
            <form onSubmit={doReset} className="space-y-4">
              <input type="password" required minLength={8} value={pw} onChange={(e) => setPw(e.target.value)}
                aria-label={zh ? '新密码（至少 8 位）' : 'New password (min 8 chars)'}
                placeholder={zh ? '新密码（至少 8 位）' : 'New password (min 8 chars)'} className={inputCls} autoComplete="new-password" />
              <input type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)}
                aria-label={zh ? '确认新密码' : 'Confirm new password'}
                placeholder={zh ? '确认新密码' : 'Confirm new password'} className={inputCls} autoComplete="new-password" />
              {msg && (
                <div className={`rounded-lg px-3 py-2 text-xs ${msg.ok ? 'bg-[var(--color-status-success)]/10 text-[var(--color-status-success)]' : 'bg-[var(--color-status-error)]/10 text-[var(--color-status-error)]'}`}>
                  {msg.text}
                </div>
              )}
              <button type="submit" disabled={busy}
                className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
                {busy ? (zh ? '提交中…' : 'Submitting…') : (zh ? '重置密码' : 'Reset password')}
              </button>
            </form>
          ) : (
            <form onSubmit={requestReset} className="space-y-4">
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                aria-label={zh ? '账户邮箱' : 'Account email'}
                placeholder={zh ? '账户邮箱' : 'Account email'} className={inputCls} autoComplete="email" />
              {msg && (
                <div className={`rounded-lg px-3 py-2 text-xs ${msg.ok ? 'bg-[var(--color-status-success)]/10 text-[var(--color-status-success)]' : 'bg-[var(--color-status-error)]/10 text-[var(--color-status-error)]'}`}>
                  {msg.text}
                </div>
              )}
              <button type="submit" disabled={busy}
                className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
                {busy ? (zh ? '发送中…' : 'Sending…') : (zh ? '发送重置邮件' : 'Send reset email')}
              </button>
            </form>
          )}
        </div>
        <div className="mt-4 text-center">
          <a href="/login" className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">← {zh ? '返回登录' : 'Back to sign in'}</a>
        </div>
      </div>
    </div>
  );
}
