// web/src/components/AnonymousNoticeBanner.jsx
// 匿名 / 邮箱未验证提示横幅（R1.9 + R1.1 软限制的前端表达，2026-09-06）。
//
// 刻意不依赖 AuthContext：PageShell 挂在 MarketPage 里，而 main.jsx 并没有为市场分析页
// 提供 AuthProvider（登录页才有）。用 useAuth 会直接抛错，用 Context 反而会把「匿名也能
// 正常浏览」这条承诺绑上认证provider。这里只读 authStore —— 与 agentApi 读同一个存储，
// 因此不会出现「banner 以为已登录、请求却走匿名 bootstrap」的分叉。
//
// 判据与文案全在 lib/accountNotices.js（有 node:test）；本组件只做渲染与状态编排。

import { useCallback, useEffect, useState } from 'react';
import { getApiBase } from '../lib/apiBase.js';
import { getValidAccessToken, readAuth } from '../lib/authStore.js';
import { fetchVerificationStatus, noticeFor, readDismissed, writeDismissed } from '../lib/accountNotices.js';

const API_BASE = getApiBase();

function currentStorage() {
  try { return globalThis.localStorage; } catch { return null; }
}

export default function AnonymousNoticeBanner({ lang = 'zh' }) {
  const zh = lang === 'zh';
  const [dismissed, setDismissed] = useState(() => readDismissed(currentStorage()));
  // 初始值取本地会话里已有的一份：principal 为空（老会话）时才走一次 /register/status。
  const stored = readAuth();
  const hasSession = Boolean(stored?.accessToken);
  const [emailVerified, setEmailVerified] = useState(() => (
    typeof stored?.principal?.email_verified_at === 'undefined' ? null : Boolean(stored?.principal?.email_verified_at)
  ));

  useEffect(() => {
    let cancelled = false;
    const token = getValidAccessToken();
    if (!token) { setEmailVerified(null); return () => { cancelled = true; }; }
    if (readAuth()?.principal?.email_verified_at) return () => { cancelled = true; };
    fetchVerificationStatus(API_BASE, token).then((value) => {
      if (!cancelled && value !== null) setEmailVerified(value);
    });
    return () => { cancelled = true; };
  }, []);

  const notice = noticeFor({ hasSession, emailVerified, dismissed }, zh);

  const close = useCallback(() => {
    if (!notice) return;
    setDismissed(writeDismissed(currentStorage(), notice.kind));
  }, [notice]);

  if (!notice) return null;

  return (
    <div
      role="note"
      className="col-span-12 flex items-start gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2"
    >
      <div className="min-w-0 flex-1">
        <p className="text-xs font-semibold text-[var(--color-text)]">{notice.title}</p>
        <p className="mt-0.5 text-[11px] text-[var(--color-muted)]">{notice.body}</p>
      </div>
      <a
        href={notice.href}
        className="shrink-0 rounded-lg border border-[var(--color-inverted)] bg-[var(--color-inverted)] px-3 py-1 text-[11px] font-semibold text-[var(--color-inverted-text)] hover:opacity-90"
      >
        {notice.ctaLabel}
      </a>
      <button
        type="button"
        onClick={close}
        aria-label={zh ? '关闭提示' : 'Dismiss notice'}
        className="shrink-0 rounded px-1 text-sm leading-none text-[var(--color-muted)] hover:text-[var(--color-text)]"
      >
        ×
      </button>
    </div>
  );
}
