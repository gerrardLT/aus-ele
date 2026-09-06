// web/src/pages/InviteAcceptPage.jsx
// 受邀注册页（P0 邀请制，2026-08-13）：/invite?token=xxx
// 填显示名+设密码 → 接受邀请即完成注册并自动登录。
//
// R1.4（2026-09-06）：同一页面也承载组织级邀请，用 ?scope=org 判别。为什么不新开一条
// 根路由：/invite 的表单、校验、文案、错误语义与工作空间级完全一致，分两页就是两份
// 迟早分叉的实现；而 main.jsx 的 lazy/三元结构被 renameGuard 与 mainEntryPerformance
// 两处测试锁着，加一条根路由的代价远大于加一个 query 位。

import { brandEyebrow } from '../lib/brand.js';
import { useMemo, useState } from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext.jsx';
import { inviteScope } from '../lib/orgAdmin.js';

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function InviteForm() {
  const { acceptInvite } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const inviteToken = useMemo(
    () => new URLSearchParams(globalThis.location.search).get('token') || '',
    [],
  );
  const scope = useMemo(() => inviteScope(globalThis.location.search), []);
  const [displayName, setDisplayName] = useState('');
  const [password, setPassword] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  // 邀请已被后端接受、但组织还没有工作空间（无法自动登录）时的成功态。
  const [acceptedEmail, setAcceptedEmail] = useState('');

  const submit = async (e) => {
    e.preventDefault();
    setError('');
    if (password.length < 8) {
      setError(zh ? '密码至少 8 位' : 'Password must be at least 8 characters');
      return;
    }
    if (password !== confirm) {
      setError(zh ? '两次输入的密码不一致' : 'Passwords do not match');
      return;
    }
    setBusy(true);
    const res = await acceptInvite(inviteToken, displayName.trim(), password, scope);
    setBusy(false);
    if (res.ok) {
      globalThis.location.href = '/account';
      return;
    }
    if (res.acceptedNoWorkspace) {
      // 关键区别：这不是失败。成员关系已经写进后端，再点一次只会撞上「邀请无效」。
      setAcceptedEmail(res.email || '');
      return;
    }
    if (res.status === 400) setError(zh ? '邀请无效（可能已被撤销或已接受）' : 'Invite is not valid (revoked or already accepted)');
    else setError(String(res.error || 'Invite accept failed'));
  };

  if (!inviteToken) {
    return (
      <div className="rounded-lg border border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/10 px-3 py-2 text-xs text-[var(--color-status-error)]">
        {zh ? '邀请链接缺少 token 参数，请检查链接是否完整' : 'Invite link is missing the token parameter'}
      </div>
    );
  }

  if (acceptedEmail !== '') {
    return (
      <div className="space-y-4">
        <div className="rounded-lg border border-[var(--color-status-success)]/40 bg-[var(--color-status-success)]/10 px-3 py-2 text-xs text-[var(--color-status-success)]">
          {zh ? '邀请已接受，账户已创建。' : 'Invite accepted, account created.'}
        </div>
        <p className="text-xs leading-relaxed text-[var(--color-muted)]">
          {zh
            ? `该组织还没有可进入的工作空间，因此无法自动登录。请用 ${acceptedEmail || '受邀邮箱'} 与刚才设置的密码在登录页登录。`
            : `This organization has no workspace to land in yet, so auto sign-in is unavailable. Sign in with ${acceptedEmail || 'the invited email'} and the password you just set.`}
        </p>
        <a
          href="/login"
          className="block w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-center text-sm font-semibold text-white transition-opacity hover:opacity-90"
        >
          {zh ? '前往登录' : 'Go to sign in'}
        </a>
      </div>
    );
  }

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]';

  return (
    <form onSubmit={submit} className="space-y-4">
      <div>
        <label htmlFor="invite-display-name" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
          {zh ? '显示名' : 'Display name'}
        </label>
        <input id="invite-display-name" required value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={inputCls} />
      </div>
      <div>
        <label htmlFor="invite-password" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
          {zh ? '设置密码（至少 8 位）' : 'Password (min 8 chars)'}
        </label>
        <input id="invite-password" type="password" required value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} autoComplete="new-password" />
      </div>
      <div>
        <label htmlFor="invite-confirm" className="mb-1.5 block text-xs font-semibold uppercase tracking-wider text-[var(--color-muted)]">
          {zh ? '确认密码' : 'Confirm password'}
        </label>
        <input id="invite-confirm" type="password" required value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} autoComplete="new-password" />
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
        {busy ? (zh ? '接受邀请中…' : 'Accepting…') : zh ? '接受邀请并创建账户' : 'Accept invite & create account'}
      </button>
    </form>
  );
}

export default function InviteAcceptPage() {
  const lang = readLang();
  const zh = lang === 'zh';
  const isOrgInvite = inviteScope(globalThis.location.search) === 'org';
  return (
    <AuthProvider>
      <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
        <div className="w-full max-w-sm">
          <div className="mb-6 text-center">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{brandEyebrow(zh)}</div>
            <h1 className="mt-1 font-serif text-2xl text-[var(--color-text)]">{zh ? '接受邀请' : 'Accept invite'}</h1>
            <p className="mt-1 text-xs text-[var(--color-muted)]">
              {isOrgInvite
                ? (zh ? '这是一封组织级邀请：接受后你将加入该组织下的全部工作空间' : 'This is an organization invite: it covers every workspace in that organization')
                : (zh ? '设置密码后即可登录使用' : 'Set a password to activate your account')}
            </p>
          </div>
          <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
            <InviteForm />
          </div>
        </div>
      </div>
    </AuthProvider>
  );
}
