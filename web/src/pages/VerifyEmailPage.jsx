// web/src/pages/VerifyEmailPage.jsx
// 邮箱验证落地页（R1.1，2026-09-06）：邮件里的 {base}/verify-email?token=… 打开本页。
//
// 与社交回调同一类问题的同一个处理：token 是一次性凭据却出现在 URL query 里（邮件里必须
// 是可点链接，无法避免），因此本页读取后立刻用 replaceState 把它从会话历史中抹掉，
// 并且任何分支都不把 token 回显到界面或控制台。
//
// 后端对「过期 / 不存在 / 已使用」返回同一句 400（防枚举），因此这里也只给一句话，
// 不去猜具体是哪一种。

import { brandEyebrow } from '../lib/brand.js';
import { useEffect, useRef, useState } from 'react';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function takeToken(historyLike = globalThis.history, locationLike = globalThis.location) {
  let token = '';
  try { token = new URLSearchParams(locationLike?.search || '').get('token') || ''; } catch { token = ''; }
  try {
    historyLike?.replaceState?.(null, '', locationLike?.pathname || '/verify-email');
  } catch {
    /* 抹不掉也不能让验证流程中断 */
  }
  return token.slice(0, 200);
}

export default function VerifyEmailPage() {
  const zh = readLang() === 'zh';
  const [status, setStatus] = useState('verifying');  // verifying | verified | invalid | network
  const [email, setEmail] = useState('');
  const [resendEmail, setResendEmail] = useState('');
  const [resendSent, setResendSent] = useState(false);
  // token 只留内存副本：URL 里那份已经抹掉（不再进会话历史），但「网络异常 → 重试」
  // 需要它。丢了这份副本，重试就只能靠用户回到邮件里重新点一次链接。
  const tokenRef = useRef('');
  // StrictMode 会把挂载 effect 跑两遍，而第一遍已经把 token 从 URL 上抹掉：
  // 没有这道闸，第二遍会读不到 token 并把状态从「正在验证」改成「链接无效」。
  const consumedRef = useRef(false);

  const runVerify = async (token) => {
    setStatus('verifying');
    try {
      const res = await fetch(`${API_BASE}/register/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ token }),
      });
      const body = await res.json().catch(() => ({}));
      if (res.ok && body?.verified) {
        setEmail(body.email || '');
        setStatus('verified');
      } else {
        setStatus('invalid');
      }
    } catch {
      // 网络失败与链接无效是两回事：把两者混成一谈会让本可重试的用户被劝去重发邮件。
      setStatus('network');
    }
  };

  useEffect(() => {
    if (consumedRef.current) return;
    consumedRef.current = true;
    const token = takeToken();
    if (!token) { setStatus('invalid'); return; }
    tokenRef.current = token;
    void runVerify(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- 一次性消费：重复执行会把已用 token 再送一次
  }, []);

  const retry = () => { void runVerify(tokenRef.current); };

  const resend = async (event) => {
    event.preventDefault();
    setResendSent(false);
    try {
      await fetch(`${API_BASE}/register/resend`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ email: resendEmail.trim() }),
      });
      // 后端无论邮箱是否存在都回 202（防枚举），所以文案不能说「已发送」，
      // 只能说「请求已受理」——否则这一页就成了邮箱存在性探测器。
      setResendSent(true);
    } catch {
      setResendSent(false);
    }
  };

  const card = 'rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-sm';
  const muted = 'text-xs text-[var(--color-muted)]';
  const primaryLink = 'block w-full rounded-lg bg-[var(--color-primary)] px-4 py-2.5 text-center text-sm font-semibold text-white hover:opacity-90';

  return (
    <div className="flex min-h-screen items-center justify-center bg-[var(--color-bg)] px-4">
      <div className="w-full max-w-sm">
        <div className="mb-6 text-center">
          <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{brandEyebrow(zh)}</div>
          <h1 className="mt-1 font-serif text-2xl text-[var(--color-text)]">{zh ? '邮箱验证' : 'Verify email'}</h1>
        </div>

        {status === 'verifying' && (
          <div className={`${card} ${muted}`}>{zh ? '正在验证…' : 'Verifying…'}</div>
        )}

        {status === 'verified' && (
          <div className={card}>
            <p className="font-semibold text-[var(--color-status-success)]">{zh ? '邮箱已验证' : 'Email verified'}</p>
            <p className={`mt-2 ${muted}`}>
              {email ? (zh ? `${email} 现在可以接收价格异动提醒与报告通知。` : `${email} will now receive alerts and report notifications.`) : ''}
            </p>
            <div className="mt-4 space-y-2">
              <a href="/account" className={primaryLink}>{zh ? '进入账户中心' : 'Go to account center'}</a>
              <a href="/" className={`block text-center text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]`}>
                {zh ? '返回市场分析' : 'Back to market analysis'}
              </a>
            </div>
          </div>
        )}

        {status === 'network' && (
          <div className={card}>
            <p className="font-semibold">{zh ? '网络异常' : 'Network problem'}</p>
            <p className={`mt-2 ${muted}`}>{zh ? '验证链接仍然有效，可以重试。' : 'The verification link is still valid — you can retry.'}</p>
            <button type="button" onClick={retry} className={`mt-4 ${primaryLink}`}>
              {zh ? '重试' : 'Retry'}
            </button>
          </div>
        )}

        {status === 'invalid' && (
          <div className={card}>
            <p className="font-semibold">{zh ? '这个验证链接无效或已过期' : 'This verification link is invalid or expired'}</p>
            <p className={`mt-2 ${muted}`}>
              {zh ? '链接只有 24 小时有效，且只能使用一次。可以重新发送一封验证邮件。' : 'Links are single-use and expire after 24 hours. You can request a new one.'}
            </p>
            <form onSubmit={resend} className="mt-4 space-y-2">
              <label htmlFor="resend-email" className={muted}>{zh ? '账户邮箱' : 'Account email'}</label>
              <input
                id="resend-email"
                type="email"
                required
                value={resendEmail}
                onChange={(event) => setResendEmail(event.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]"
              />
              <button type="submit" className={`w-full rounded-lg border border-[var(--color-border)] px-4 py-2 text-xs font-semibold text-[var(--color-text)] hover:opacity-80`}>
                {zh ? '请求重发验证邮件' : 'Request a new verification email'}
              </button>
              {resendSent && (
                <p className={muted}>
                  {zh ? '请求已受理。若该邮箱存在未验证账户，稍后会收到邮件。' : 'Request accepted. If that address has an unverified account, an email will follow.'}
                </p>
              )}
            </form>
            <a href="/login" className={`mt-4 block text-center text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]`}>
              {zh ? '返回登录' : 'Back to sign in'}
            </a>
          </div>
        )}
      </div>
    </div>
  );
}
