// web/src/components/account/SessionsPanel.jsx
// R1.3 会话管理面板（2026-09-06）。替代原先内联在 AccountPage 里的 SessionsSection。
//
// 相对内联版修掉的三个真实问题：
// 1. **点完「登出其他设备」当前标签页会自杀**：后端 revoke-others 除了吊销其他会话，
//    还调 `revoke_access_tokens_by_principal`（不带 exclude），当前会话的 access token
//    一并作废；而 `getValidAccessToken()` 只看 exp 不看 revoked，于是刷新后每个账户请求
//    都 401，用户看到「刚点了一下安全按钮，账户页就空了」。现在显式 `tryRefreshToken()`
//    用 session token 重新换签（会话本身没被吊销，所以这条路是通的）。
// 2. 到期未撤销的会话被算进「活跃会话」→ 计数与真实风险不符（判据见 lib/accountSessions.js）。
// 3. 请求失败静默 catch，面板显示「无会话信息」，与「真的只有一个会话」无法区分。
//    账户安全面板上的沉默会被读成「一切正常」，所以错误必须显式可见。

import { useCallback, useEffect, useState } from 'react';
import { getApiBase } from '../../lib/apiBase.js';
import { getValidAccessToken, readAuth, tryRefreshToken } from '../../lib/authStore.js';
import {
  canRevokeOthers,
  formatStamp,
  liveSessionCount,
  methodLabel,
  partitionSessions,
  revokeOthersUrl,
  sessionsUrl,
} from '../../lib/accountSessions.js';

const API_BASE = getApiBase();

const STATUS_STYLE = {
  current: 'text-[var(--color-status-success)]',
  active: 'text-[var(--color-muted)]',
  expired: 'text-[var(--color-muted)] opacity-60',
};

export default function SessionsPanel({ lang = 'zh', onTokenRotated }) {
  const zh = lang === 'zh';
  const [rows, setRows] = useState([]);
  const [state, setState] = useState('idle');
  const [error, setError] = useState(null);
  const [notice, setNotice] = useState(null);

  const load = useCallback(async () => {
    const token = await (getValidAccessToken() || tryRefreshToken());
    if (!token) { setState('error'); setError(zh ? '登录状态已失效' : 'Session expired'); return; }
    setState('loading');
    setError(null);
    try {
      const res = await fetch(sessionsUrl(API_BASE), { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) {
        setState('error');
        setError(res.status === 401 ? (zh ? '登录状态已失效' : 'Session expired') : `HTTP ${res.status}`);
        return;
      }
      setRows(partitionSessions(await res.json(), readAuth()?.workspaces || [], Date.now()));
      setState('ready');
    } catch {
      setState('error');
      setError(zh ? '网络错误' : 'Network error');
    }
  }, [zh]);

  useEffect(() => { load(); }, [load]);

  const revokeOthers = useCallback(async () => {
    setState('revoking');
    setError(null);
    try {
      const token = await (getValidAccessToken() || tryRefreshToken());
      const res = await fetch(revokeOthersUrl(API_BASE), {
        method: 'POST',
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) {
        setState('ready');
        setError(res.status === 403 ? (zh ? '匿名浏览身份无法执行此操作，请先注册' : 'Anonymous sessions cannot revoke others') : `HTTP ${res.status}`);
        return;
      }
      const body = await res.json().catch(() => ({}));
      // 当前 access token 已随之作废：不补这一手，面板之后会一直显示 401
      const fresh = await tryRefreshToken();
      onTokenRotated?.(fresh);
      await load();
      setState('ready');
      setNotice({ count: Number(body.revoked_sessions || 0) });
    } catch {
      setState('ready');
      setError(zh ? '网络错误' : 'Network error');
    }
  }, [zh, load, onTokenRotated]);

  const busy = state === 'revoking' || state === 'loading';
  const live = liveSessionCount(rows);
  const showRevoke = state === 'ready' && canRevokeOthers(rows);

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between gap-2">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">
          {zh ? `登录会话（${live} 个活跃）` : `Sign-in sessions (${live} active)`}
        </h3>
        <div className="flex items-center gap-2">
          {notice && (
            <span className="text-[10px] text-[var(--color-status-success)]">
              {zh ? `已登出 ${notice.count} 个其他会话` : `Signed out ${notice.count} other sessions`}
            </span>
          )}
          {showRevoke && (
            <button
              type="button"
              onClick={revokeOthers}
              disabled={busy}
              className="rounded-lg border border-[var(--color-status-error)]/50 px-2 py-1 text-[10px] text-[var(--color-status-error)] hover:opacity-80 disabled:opacity-50"
            >
              {zh ? '登出其他设备' : 'Sign out other devices'}
            </button>
          )}
        </div>
      </div>

      {state === 'error' && (
        <p className="mb-2 text-xs text-[var(--color-status-error)]" role="alert">
          {error} ·{' '}
          <button type="button" onClick={load} className="underline">{zh ? '重试' : 'Retry'}</button>
        </p>
      )}

      {state === 'loading' && <p className="text-xs text-[var(--color-muted)]">{zh ? '加载中…' : 'Loading…'}</p>}

      {state === 'ready' && rows.length === 0 && (
        <p className="text-xs text-[var(--color-muted)]">{zh ? '后端未返回任何会话记录。' : 'No session records returned.'}</p>
      )}

      <ul className="space-y-1.5">
        {state === 'ready' && rows.map((row) => (
          <li
            key={row.sessionId}
            className={`flex flex-wrap items-center justify-between gap-2 rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-[10px] ${STATUS_STYLE[row.status]}`}
          >
            <span className="min-w-0 truncate">
              {methodLabel(row.authMethod, zh)} · {row.workspaceName || '—'}
              {row.status === 'current' && (
                <span className="ml-1 text-[var(--color-status-success)]">{zh ? '（当前设备）' : '(this device)'}</span>
              )}
              {row.status === 'expired' && (
                <span className="ml-1">{zh ? '（已到期，未清理）' : '(expired, not purged)'}</span>
              )}
            </span>
            <span className="font-mono shrink-0" title={zh ? '最近活动' : 'Last activity'}>
              {formatStamp(row.lastSeenAt || row.createdAt, zh)}
            </span>
          </li>
        ))}
      </ul>

      <p className="mt-2 text-[10px] text-[var(--color-muted)]">
        {zh
          ? '后端只提供「保留当前设备、登出其余」一种粒度；无法逐条吊销单个会话。'
          : 'Only bulk "keep this device, sign out the rest" is supported; individual sessions cannot be revoked.'}
      </p>
    </section>
  );
}
