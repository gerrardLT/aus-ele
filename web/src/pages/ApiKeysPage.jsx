// web/src/pages/ApiKeysPage.jsx
// API Key 管理（P0 账户中心，2026-08-13）：创建（raw key 一次性展示）/列表/吊销。

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext.jsx';
import { usePermissions } from '../hooks/usePermissions.js';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function ApiKeysPage() {
  const { auth, getToken } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const workspaceId = auth?.workspaceId;
  // 后端真值：GET/POST api-keys 走 check_workspace_permission(actor, "workspace_manage")
  // （account_routes.py:632/660/688）。
  const { canInWorkspace } = usePermissions(auth);
  const canManage = canInWorkspace('workspace_manage');

  const [keys, setKeys] = useState([]);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [rawKey, setRawKey] = useState(null); // {client_name, api_key_raw}
  const [error, setError] = useState('');

  const authedFetch = useCallback(async (path, opts = {}) => {
    const token = await getToken();
    return fetch(`${API_BASE}${path}`, { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${token}` } });
  }, [getToken]);

  const reload = useCallback(async () => {
    if (!workspaceId || !canManage) return;
    const res = await authedFetch(`/v1/account/workspaces/${workspaceId}/api-keys`);
    if (res.ok) setKeys((await res.json()).api_keys || []);
  }, [workspaceId, canManage, authedFetch]);

  useEffect(() => { reload(); }, [reload]);

  const createKey = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    const res = await authedFetch(`/v1/account/workspaces/${workspaceId}/api-keys`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ client_name: name.trim() }),
    });
    setBusy(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setError(String(err.detail || `Failed (${res.status})`));
      return;
    }
    const body = await res.json();
    setRawKey({ client_name: body.client_name, api_key_raw: body.api_key_raw });
    setName('');
    reload();
  };

  const revokeKey = async (clientId) => {
    if (!globalThis.confirm(zh ? '吊销后不可恢复，确认吊销该 Key？' : 'Revoking is irreversible. Continue?')) return;
    const res = await authedFetch(`/v1/account/workspaces/${workspaceId}/api-keys/${clientId}/revoke`, { method: 'POST' });
    if (res.ok) reload();
  };

  const copyRaw = async () => {
    try { await navigator.clipboard.writeText(rawKey.api_key_raw); } catch { /* 剪贴板不可用时手动复制 */ }
  };

  if (!canManage) {
    return <p className="text-xs text-[var(--color-muted)]">{zh ? '当前角色无权管理 API Key（需 owner/admin）' : 'API key management requires owner/admin role'}</p>;
  }

  const cellCls = 'px-3 py-2 text-xs';
  const thCls = `${cellCls} text-left font-semibold uppercase tracking-wider text-[var(--color-muted)]`;

  return (
    <div className="space-y-6">
      {rawKey && (
        <section className="rounded-xl border border-[var(--color-status-warning)]/50 bg-[var(--color-status-warning)]/10 p-4">
          <h2 className="mb-2 text-sm font-semibold text-[var(--color-text)]">
            {zh ? `Key「${rawKey.client_name}」已创建 — 仅显示一次` : `Key "${rawKey.client_name}" created — shown only once`}
          </h2>
          <code className="block break-all rounded-lg bg-[var(--color-panel)] px-3 py-2 font-mono text-xs text-[var(--color-text)]">
            {rawKey.api_key_raw}
          </code>
          <div className="mt-3 flex gap-3">
            <button onClick={copyRaw} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:bg-[var(--color-panel)]">
              {zh ? '复制' : 'Copy'}
            </button>
            <button onClick={() => setRawKey(null)} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs hover:bg-[var(--color-panel)]">
              {zh ? '我已保存，关闭' : 'Saved, dismiss'}
            </button>
          </div>
        </section>
      )}

      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? '创建 API Key' : 'Create API key'}</h2>
        <form onSubmit={createKey} className="flex flex-wrap items-end gap-3">
          <div className="min-w-[220px] flex-1">
            <label className="mb-1 block text-xs text-[var(--color-muted)]">{zh ? 'Key 名称' : 'Key name'}</label>
            <input required value={name} onChange={(e) => setName(e.target.value)}
              className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" />
          </div>
          <button type="submit" disabled={busy}
            className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
            {busy ? (zh ? '创建中…' : 'Creating…') : zh ? '创建' : 'Create'}
          </button>
        </form>
        {error && <p className="mt-3 text-xs text-[var(--color-status-error)]">{error}</p>}
        <p className="mt-2 text-xs text-[var(--color-muted)]">
          {zh ? '默认 starter 套餐（1,000 units/天）。raw key 仅创建时显示一次，请立即保存。' : 'Default starter plan (1,000 units/day). The raw key is shown only once — save it now.'}
        </p>
      </section>

      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? 'Key 列表' : 'API keys'}</h2>
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className={thCls}>{zh ? '名称' : 'Name'}</th>
              <th className={thCls}>Key</th>
              <th className={thCls}>{zh ? '套餐' : 'Plan'}</th>
              <th className={thCls}>{zh ? '今日用量' : 'Today'}</th>
              <th className={thCls}>{zh ? '状态' : 'Status'}</th>
              <th className={thCls}></th>
            </tr>
          </thead>
          <tbody>
            {keys.map((k) => (
              <tr key={k.client_id} className="border-t border-[var(--color-border)]">
                <td className={cellCls}>{k.client_name}</td>
                <td className={`${cellCls} font-mono`}>{k.api_key_masked}</td>
                <td className={cellCls}>{k.plan}</td>
                <td className={`${cellCls} font-mono`}>
                  {k.used_units_today}{k.daily_unit_limit != null ? ` / ${k.daily_unit_limit}` : ''}
                </td>
                <td className={cellCls}>
                  <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold ${k.enabled ? 'bg-[var(--color-status-success)]/15 text-[var(--color-status-success)]' : 'bg-[var(--color-border)] text-[var(--color-muted)]'}`}>
                    {k.enabled ? (zh ? '启用' : 'active') : zh ? '已吊销' : 'revoked'}
                  </span>
                </td>
                <td className={cellCls}>
                  {k.enabled && (
                    <button onClick={() => revokeKey(k.client_id)} className="text-xs text-[var(--color-status-error)] hover:underline">
                      {zh ? '吊销' : 'Revoke'}
                    </button>
                  )}
                </td>
              </tr>
            ))}
            {keys.length === 0 && (
              <tr><td colSpan={6} className={`${cellCls} text-center text-[var(--color-muted)]`}>{zh ? '暂无 API Key' : 'No API keys yet'}</td></tr>
            )}
          </tbody>
        </table>
      </section>
    </div>
  );
}
