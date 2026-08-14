// web/src/pages/AuditPage.jsx
// 审计日志（P2-5，2026-08-14）：账户中心 tab，只读，仅 owner/admin 可见。

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext.jsx';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function AuditPage() {
  const { auth, getToken } = useAuth();
  const zh = readLang() === 'zh';
  const workspaceId = auth?.workspaceId;
  const [items, setItems] = useState([]);
  const [error, setError] = useState('');

  const load = useCallback(async () => {
    if (!workspaceId) return;
    const token = await getToken();
    try {
      const res = await fetch(`${API_BASE}/v1/audit?workspace_id=${workspaceId}&limit=200`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) setItems((await res.json()).items || []);
      else if (res.status === 403) setError(zh ? '仅 owner/admin 可查看审计日志' : 'Only owner/admin can view audit logs');
    } catch {
      setError(zh ? '网络错误，请稍后重试' : 'Network error, please retry');
    }
  }, [workspaceId, getToken, zh]);

  useEffect(() => { load(); }, [load]);

  if (error) {
    return <p className="py-8 text-center text-xs text-[var(--color-status-error)]">{error}</p>;
  }

  return (
    <div className="space-y-4">
      <h2 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '审计日志' : 'Audit log'}</h2>
      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
              <th className="px-3 py-2 font-semibold">{zh ? '时间' : 'Time'}</th>
              <th className="px-3 py-2 font-semibold">{zh ? '操作者' : 'Actor'}</th>
              <th className="px-3 py-2 font-semibold">{zh ? '动作' : 'Action'}</th>
              <th className="px-3 py-2 font-semibold">{zh ? '目标' : 'Target'}</th>
            </tr>
          </thead>
          <tbody className="text-[var(--color-text)]">
            {items.length === 0 && (
              <tr><td colSpan={4} className="px-3 py-6 text-center text-[var(--color-muted)]">{zh ? '暂无审计记录' : 'No audit entries'}</td></tr>
            )}
            {items.map((it) => (
              <tr key={it.audit_id} className="border-b border-[var(--color-border)] last:border-b-0">
                <td className="whitespace-nowrap px-3 py-2 font-mono text-[10px]">{(it.created_at || '').slice(0, 19).replace('T', ' ')}</td>
                <td className="px-3 py-2 font-mono text-[10px]">{it.actor_principal_id || '—'}</td>
                <td className="px-3 py-2">{it.action}</td>
                <td className="px-3 py-2 font-mono text-[10px]">{it.target_type}/{it.target_id}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
