// web/src/components/NotificationBell.jsx
// 站内通知铃铛（P2-1，2026-08-14）：未读数徽章 + 下拉列表 + 标记已读。
// 仅登录用户显示（匿名访问无 workspace 归属）。

import { useCallback, useEffect, useRef, useState } from 'react';
import { readAuth, getValidAccessToken, tryRefreshToken } from '../lib/authStore.js';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

async function authToken() {
  return getValidAccessToken() || (await tryRefreshToken());
}

export default function NotificationBell({ lang = 'zh' }) {
  const zh = lang === 'zh';
  const auth = readAuth();
  const workspaceId = auth?.workspaceId;
  const [open, setOpen] = useState(false);
  const [unread, setUnread] = useState(0);
  const [items, setItems] = useState([]);
  const boxRef = useRef(null);

  const loadUnread = useCallback(async () => {
    if (!workspaceId) return;
    const token = await authToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/v1/notify/unread-count?workspace_id=${workspaceId}`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setUnread((await res.json()).unread || 0);
    } catch { /* best-effort */ }
  }, [workspaceId]);

  const loadItems = useCallback(async () => {
    if (!workspaceId) return;
    const token = await authToken();
    if (!token) return;
    try {
      const res = await fetch(`${API_BASE}/v1/notify?workspace_id=${workspaceId}&limit=20`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setItems((await res.json()).items || []);
    } catch { /* best-effort */ }
  }, [workspaceId]);

  useEffect(() => { loadUnread(); }, [loadUnread]);

  useEffect(() => {
    if (!open) return undefined;
    loadItems();
    const onDoc = (e) => {
      if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false);
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open, loadItems]);

  const markRead = async (id) => {
    const token = await authToken();
    if (!token) return;
    await fetch(`${API_BASE}/v1/notify/${id}/read?workspace_id=${workspaceId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    setItems((prev) => prev.map((it) => (it.notification_id === id ? { ...it, read: true } : it)));
    setUnread((n) => Math.max(0, n - 1));
  };

  const markAll = async () => {
    const token = await authToken();
    if (!token) return;
    await fetch(`${API_BASE}/v1/notify/read-all?workspace_id=${workspaceId}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${token}` },
    });
    setItems((prev) => prev.map((it) => ({ ...it, read: true })));
    setUnread(0);
  };

  if (!workspaceId) return null;

  return (
    <div ref={boxRef} data-tour="bell" className="fixed right-4 top-3 z-50">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="relative rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] p-2 shadow-sm"
        aria-label={zh ? '通知' : 'Notifications'}
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" className="text-[var(--color-muted)]">
          <path d="M18 8a6 6 0 0 0-12 0c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && (
          <span className="absolute -right-1 -top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-[var(--color-status-error)] px-1 text-[9px] font-bold text-white">
            {unread > 99 ? '99+' : unread}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 mt-2 w-80 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg">
          <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
            <span className="text-xs font-semibold text-[var(--color-text)]">{zh ? '通知' : 'Notifications'}</span>
            {unread > 0 && (
              <button type="button" onClick={markAll} className="text-[10px] text-[var(--color-primary)] hover:underline">
                {zh ? '全部已读' : 'Mark all read'}
              </button>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto">
            {items.length === 0 && (
              <p className="px-3 py-6 text-center text-xs text-[var(--color-muted)]">{zh ? '暂无通知' : 'No notifications'}</p>
            )}
            {items.map((it) => (
              <div
                key={it.notification_id}
                className={`border-b border-[var(--color-border)] px-3 py-2 last:border-b-0 ${it.read ? 'opacity-60' : ''}`}
              >
                <div className="flex items-start justify-between gap-2">
                  <p className="text-xs font-medium text-[var(--color-text)]">{it.title}</p>
                  {!it.read && (
                    <button type="button" onClick={() => markRead(it.notification_id)} className="shrink-0 text-[10px] text-[var(--color-primary)] hover:underline">
                      {zh ? '已读' : 'Read'}
                    </button>
                  )}
                </div>
                {it.body?.value != null && (
                  <p className="mt-0.5 font-mono text-[10px] text-[var(--color-muted)]">
                    {it.body.region_or_zone || ''} → {it.body.value}
                  </p>
                )}
                <p className="mt-0.5 text-[10px] text-[var(--color-muted)]">{(it.created_at || '').slice(0, 16).replace('T', ' ')}</p>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
