// web/src/pages/RegisterPage.jsx
// 自助注册页（R1.1，2026-09-06）：邮箱 + 密码 + 显示名 → 账户 + 自有组织/工作空间。
//
// 两条实现纪律：
// 1. **不在前端复刻密码策略**。强度判据只有一处真值（``services/password_policy.py``）；
//    这里只做「把后端 422 的 errors[] 一次显示全」和一条静态提示。JS 里再写一份规则
//    迟早与后端漂移，结果是「前端放行、后端拒绝」的死循环表单。
// 2. **注册成功即已登录**。后端返回的会话与普通登录完全同形（见 registration_routes 的
//    docstring：未验证是软限制），因此落地一律走 ``adoptSession``，本页不自己写 token。

import { brandEyebrow } from '../lib/brand.js';
import { useState } from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext.jsx';
import SocialLoginButtons from '../components/account/SocialLoginButtons.jsx';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function messageFrom(status, body, zh) {
  const detail = body?.detail;
  if (status === 422 && Array.isArray(detail?.errors)) return detail.errors;
  if (status === 409) return [zh ? '该邮箱已注册，请直接登录或找回密码' : 'This email is already registered'];
  if (status === 429) return [zh ? '操作过于频繁，请稍后再试' : 'Too many attempts, please retry later'];
  if (status === 403) return [zh ? '注册功能暂时关闭，请稍后再试' : 'Registration is temporarily unavailable'];
  const text = typeof detail === 'string' ? detail : (detail?.code || `Registration failed (${status})`);
  return [text];
}

function RegisterForm() {
  const { adoptSession } = useAuth();
  const zh = readLang() === 'zh';
  const [form, setForm] = useState({ email: '', display_name: '', organization_name: '', password: '', confirm: '' });
  const [errors, setErrors] = useState([]);
  const [busy, setBusy] = useState(false);
  const [sent, setSent] = useState(null);  // {email, verificationStatus}

  const field = (key) => (event) => setForm((prev) => ({ ...prev, [key]: event.target.value }));

  const submit = async (event) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    // 只做「两次输入一致」这一条纯 UX 判据：它不需要与后端共享语义，因此不存在漂移问题。
    if (form.password !== form.confirm) {
      setBusy(false);
      setErrors([zh ? '两次输入的密码不一致' : 'Passwords do not match']);
      return;
    }
    try {
      const res = await fetch(`${API_BASE}/register`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: form.email.trim(),
          password: form.password,
          display_name: form.display_name.trim(),
          organization_name: form.organization_name.trim() || undefined,
        }),
      });
      const body = await res.json().catch(() => ({}));
      if (!res.ok) {
        setErrors(messageFrom(res.status, body, zh));
        return;
      }
      const landed = await adoptSession(body);
      if (!landed.ok) {
        setErrors([landed.error || (zh ? '注册已完成，但自动登录失败，请手动登录' : 'Registered, but auto sign-in failed')]);
        return;
      }
      // 后端已签发会话（未验证也是软限制），所以这里不是「卡住等邮件」，
      // 而是一个可跳过、可稍后回来、且明确说明跳过了什么的状态页。
      setSent({ email: body.email || form.email.trim(), verificationStatus: body.verification_status });
    } catch {
      setErrors([zh ? '网络错误，请稍后重试' : 'Network error, please retry']);
    } finally {
      setBusy(false);
    }
  };

  const resend = async () => {
    setErrors([]);
    try {
      await fetch(`${API_BASE}/register/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: sent.email }),
      });
      setSent({ ...sent, resent: true });
    } catch {
      setErrors([zh ? '网络错误，请稍后重试' : 'Network error, please retry']);
    }
  };

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]';
  const labelCls = 'mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]';

  if (sent) {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-[var(--color-status-success)]/40 bg-[var(--color-status-success)]/10 px-3 py-3 text-sm text-[var(--color-text)]">
          <p className="font-semibold">{zh ? '账号已创建' : 'Account created'}</p>
          <p className="mt-1 text-xs text-[var(--color-muted)]">
            {zh
              ? '已为你登录并创建好独立的工作空间。验证邮箱后可以收到价格异动提醒，并解锁报告保存与导出。'
              : 'You are signed in with your own workspace. Verifying your email unlocks alerts, saved reports and exports.'}
          </p>
        </div>
        {sent.verificationStatus === 'verified' && (
          <p className="text-xs text-[var(--color-muted)]">{zh ? '邮箱已验证，无需额外操作。' : 'Email already verified — nothing else to do.'}</p>
        )}
        {sent.verificationStatus !== 'verified' && (
          <div className="space-y-2 text-xs text-[var(--color-muted)]">
            <p>{zh ? `验证邮件已发送至 ${sent.email}（24 小时内有效）。` : `A verification email is on its way to ${sent.email} (valid for 24 hours).`}</p>
            {sent.resent && <p>{zh ? '已再次发送。' : 'Email re-sent.'}</p>}
            <div className="flex items-center gap-3 pt-1">
              <button type="button" onClick={resend} className="text-[var(--color-primary)] hover:opacity-80">
                {zh ? '重发验证邮件' : 'Resend verification email'}
              </button>
              <a href="/account" className="text-[var(--color-muted)] hover:text-[var(--color-text)]">
                {zh ? '稍后再说' : 'Later'}
              </a>
            </div>
          </div>
        )}
        <a href="/account" className="block w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-center text-sm font-semibold text-white hover:opacity-90">
          {zh ? '进入账户中心' : 'Go to account center'}
        </a>
      </div>
    );
  }

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="reg-email" className={labelCls}>{zh ? '邮箱' : 'Email'}</label>
        <input id="reg-email" type="email" required autoComplete="email" value={form.email} onChange={field('email')} className={inputCls} />
      </div>
      <div>
        <label htmlFor="reg-name" className={labelCls}>{zh ? '显示名' : 'Display name'}</label>
        <input id="reg-name" type="text" required maxLength={120} autoComplete="name" value={form.display_name} onChange={field('display_name')} className={inputCls} />
      </div>
      <div>
        <label htmlFor="reg-org" className={labelCls}>
          {zh ? '组织名（可选）' : 'Organization (optional)'}
        </label>
        <input id="reg-org" type="text" maxLength={160} autoComplete="organization" value={form.organization_name} onChange={field('organization_name')} className={inputCls} placeholder={zh ? '缺省按显示名生成' : 'Defaults to your display name'} />
      </div>
      <div>
        <label htmlFor="reg-password" className={labelCls}>{zh ? '密码' : 'Password'}</label>
        <input id="reg-password" type="password" required autoComplete="new-password" value={form.password} onChange={field('password')} className={inputCls} />
        <p className="mt-1 text-[11px] text-[var(--color-muted)]">
          {zh
            ? '至少 12 位，混合大小写/数字/符号，且不能是常见密码或包含你的邮箱与姓名。'
            : 'At least 12 characters, mixed character classes, not a common password or derived from your email/name.'}
        </p>
      </div>
      <div>
        <label htmlFor="reg-confirm" className={labelCls}>{zh ? '确认密码' : 'Confirm password'}</label>
        <input id="reg-confirm" type="password" required autoComplete="new-password" value={form.confirm} onChange={field('confirm')} className={inputCls} />
      </div>
      {errors.length > 0 && (
        <ul className="space-y-1 rounded-lg border border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/10 px-3 py-2 text-xs text-[var(--color-status-error)]">
          {errors.map((item) => <li key={item}>{item}</li>)}
        </ul>
      )}
      <button
        type="submit"
        disabled={busy}
        className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-sm font-semibold text-white transition-opacity hover:opacity-90 disabled:opacity-50"
      >
        {busy ? (zh ? '创建中…' : 'Creating…') : zh ? '创建账号' : 'Create account'}
      </button>
      <SocialLoginButtons zh={zh} disabled={busy} />
      <p className="pt-1 text-center text-xs text-[var(--color-muted)]">
        {zh ? '已有账号？' : 'Already have an account?'}{' '}
        <a href="/login" className="text-[var(--color-text)] hover:underline">{zh ? '登录' : 'Sign in'}</a>
      </p>
    </form>
  );
}

export default function RegisterPage() {
  const zh = readLang() === 'zh';
  return (
    <AuthProvider>
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
        <div className="w-full max-w-sm">
          <div className="mb-6 text-center">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{brandEyebrow(zh)}</div>
            <h1 className="mt-1 font-serif text-2xl text-[var(--color-text)]">{zh ? '创建账号' : 'Create account'}</h1>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <RegisterForm />
          </div>
          {/* 注册即构成对条款的同意，所以同意对象必须在这页上可见可点。只写「注册即表示同意」
              而不给链接，等于让人同意一份读不到的合同（R2.4 法务补全的落地要求）。 */}
          <p className="mx-auto mt-4 max-w-md text-center text-[11px] leading-relaxed text-[var(--color-muted)]">
            {zh ? '注册即表示同意' : 'By registering you agree to the '}
            <a href="/legal/terms" className="underline hover:text-[var(--color-text)]">{zh ? '服务条款' : 'Terms of Service'}</a>
            {zh ? '与' : ' and the '}
            <a href="/legal/privacy" className="underline hover:text-[var(--color-text)]">{zh ? '隐私政策' : 'Privacy Policy'}</a>
            {zh ? '，并遵守' : ' and the '}
            <a href="/legal/aup" className="underline hover:text-[var(--color-text)]">{zh ? '可接受使用政策' : 'Acceptable Use Policy'}</a>
            {zh ? '。' : '.'}
          </p>
          <div className="mt-4 text-center">
            <a href="/" className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">← {zh ? '返回市场分析' : 'Back to market analysis'}</a>
          </div>
        </div>
      </div>
    </AuthProvider>
  );
}
