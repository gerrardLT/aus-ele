// web/src/pages/MembersPage.jsx
// 成员管理（P0 账户中心，2026-08-13）：成员列表 + 邀请创建/撤销（owner/admin）。

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext.jsx';
import { usePermissions } from '../hooks/usePermissions.js';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function MembersPage() {
  const { auth, getToken } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const workspaceId = auth?.workspaceId;
  // 后端真值：invites 的 list/create/revoke 全部走 check_workspace_permission(actor,
  // "member_manage")（account_routes.py:562、access_control.py:1807/1840）。
  // 用 member_manage 而不是 workspace_manage，是因为这两组权限当前恰好同集合（owner/admin），
  // 但「恰好相等」不是「同一个东西」：日后给 admin 摘掉 workspace_manage 时，
  // 写死角色串的页面会一起变，而按权限名门控的页面只会在真正需要的那一项上收敛。
  const { canInWorkspace } = usePermissions(auth);
  const canManage = canInWorkspace('member_manage');

  const [members, setMembers] = useState([]);
  const [invites, setInvites] = useState([]);
  const [email, setEmail] = useState('');
  const [inviteRole, setInviteRole] = useState('analyst');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [resettingId, setResettingId] = useState(null);
  const [resetPw, setResetPw] = useState('');

  const authedFetch = useCallback(async (path, opts = {}) => {
    const token = await getToken();
    return fetch(`${API_BASE}${path}`, { ...opts, headers: { ...(opts.headers || {}), Authorization: `Bearer ${token}` } });
  }, [getToken]);

  const reload = useCallback(async () => {
    if (!workspaceId) return;
    const [mRes, iRes] = await Promise.all([
      authedFetch(`/v1/account/workspaces/${workspaceId}/members`),
      canManage ? authedFetch(`/v1/account/workspaces/${workspaceId}/invites`) : Promise.resolve(null),
    ]);
    if (mRes.ok) setMembers((await mRes.json()).members || []);
    if (iRes && iRes.ok) setInvites((await iRes.json()).invites || []);
  }, [workspaceId, canManage, authedFetch]);

  useEffect(() => { reload(); }, [reload]);

  const createInvite = async (e) => {
    e.preventDefault();
    setBusy(true); setError(''); setNotice('');
    const res = await authedFetch(`/v1/account/workspaces/${workspaceId}/invites`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email.trim(), role: inviteRole }),
    });
    setBusy(false);
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      setError(String(err.detail || `Failed (${res.status})`));
      return;
    }
    const body = await res.json();
    const link = `${globalThis.location.origin}${body.invite_url_path}`;
    try { await navigator.clipboard.writeText(link); } catch { /* 剪贴板不可用时展示链接 */ }
    setNotice(zh ? `邀请已创建，链接已复制到剪贴板：${link}` : `Invite created. Link copied: ${link}`);
    setEmail('');
    reload();
  };

  const revokeInvite = async (inviteId) => {
    const res = await authedFetch(`/v1/account/workspaces/${workspaceId}/invites/${inviteId}/revoke`, { method: 'POST' });
    if (res.ok) reload();
  };

  // 管理员重置成员密码（2026-08-14）：重置后目标全部会话失效
  const resetMemberPassword = async (principalId) => {
    if (!resetPw || resetPw.length < 8) {
      setError(zh ? '新密码至少 8 位' : 'New password must be at least 8 characters');
      return;
    }
    setError('');
    const res = await authedFetch(`/v1/account/workspaces/${workspaceId}/members/${principalId}/reset-password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ new_password: resetPw }),
    });
    if (res.ok) {
      setNotice(zh ? '密码已重置，该成员原会话已全部失效' : 'Password reset; all sessions of the member revoked');
      setResettingId(null);
      setResetPw('');
    } else {
      const err = await res.json().catch(() => ({}));
      setError(String(err.detail || `Failed (${res.status})`));
    }
  };

  const cellCls = 'px-3 py-2 text-xs';
  const thCls = `${cellCls} text-left font-semibold uppercase tracking-wider text-[var(--color-muted)]`;

  return (
    <div className="space-y-6">
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h2 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? '成员列表' : 'Members'}</h2>
        <table className="w-full border-collapse">
          <thead>
            <tr>
              <th className={thCls}>{zh ? '邮箱' : 'Email'}</th>
              <th className={thCls}>{zh ? '显示名' : 'Name'}</th>
              <th className={thCls}>{zh ? '角色' : 'Role'}</th>
              {canManage && <th className={thCls}></th>}
            </tr>
          </thead>
          <tbody>
            {members.map((m) => (
              <tr key={m.membership_id} className="border-t border-[var(--color-border)]">
                <td className={`${cellCls} font-mono`}>{m.email}</td>
                <td className={cellCls}>{m.display_name || '—'}</td>
                <td className={cellCls}><span className="rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[10px] font-semibold">{m.role}</span></td>
                {canManage && (
                  <td className={cellCls}>
                    {resettingId === m.principal_id ? (
                      <span className="flex items-center gap-2">
                        <input type="text" value={resetPw} onChange={(e) => setResetPw(e.target.value)}
                          placeholder={zh ? '新密码（≥8位）' : 'New password'}
                          className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-0.5 text-[10px] text-[var(--color-text)]" />
                        <button onClick={() => resetMemberPassword(m.principal_id)} className="text-[10px] text-[var(--color-primary)] hover:underline">{zh ? '确认' : 'OK'}</button>
                        <button onClick={() => { setResettingId(null); setResetPw(''); }} className="text-[10px] text-[var(--color-muted)] hover:underline">{zh ? '取消' : 'Cancel'}</button>
                      </span>
                    ) : (
                      <button onClick={() => { setResettingId(m.principal_id); setResetPw(''); setError(''); }}
                        className="text-[10px] text-[var(--color-muted)] hover:text-[var(--color-text)] hover:underline">
                        {zh ? '重置密码' : 'Reset password'}
                      </button>
                    )}
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </section>

      {canManage ? (
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <h2 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? '邀请新成员' : 'Invite member'}</h2>
          <form onSubmit={createInvite} className="flex flex-wrap items-end gap-3">
            <div className="min-w-[220px] flex-1">
              <label className="mb-1 block text-xs text-[var(--color-muted)]">{zh ? '受邀人邮箱' : 'Email'}</label>
              <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)}
                className="w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-sm text-[var(--color-text)] outline-none focus:border-[var(--color-primary)]" />
            </div>
            <div>
              <label className="mb-1 block text-xs text-[var(--color-muted)]">{zh ? '角色' : 'Role'}</label>
              <select value={inviteRole} onChange={(e) => setInviteRole(e.target.value)}
                className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-sm text-[var(--color-text)]">
                <option value="admin">admin</option>
                <option value="analyst">analyst</option>
                <option value="viewer">viewer</option>
              </select>
            </div>
            <button type="submit" disabled={busy}
              className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50">
              {busy ? (zh ? '创建中…' : 'Creating…') : zh ? '创建邀请' : 'Create invite'}
            </button>
          </form>
          {notice && <p className="mt-3 break-all rounded-lg bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-muted)]">{notice}</p>}
          {error && <p className="mt-3 text-xs text-[var(--color-status-error)]">{error}</p>}

          {invites.length > 0 && (
            <table className="mt-4 w-full border-collapse">
              <thead>
                <tr>
                  <th className={thCls}>{zh ? '邮箱' : 'Email'}</th>
                  <th className={thCls}>{zh ? '角色' : 'Role'}</th>
                  <th className={thCls}>{zh ? '状态' : 'Status'}</th>
                  <th className={thCls}></th>
                </tr>
              </thead>
              <tbody>
                {invites.map((inv) => (
                  <tr key={inv.invite_id} className="border-t border-[var(--color-border)]">
                    <td className={`${cellCls} font-mono`}>{inv.email}</td>
                    <td className={cellCls}>{inv.role}</td>
                    <td className={cellCls}>{zh ? { pending: '待接受', accepted: '已接受', revoked: '已撤销' }[inv.status] : inv.status}</td>
                    <td className={cellCls}>
                      {inv.status === 'pending' && (
                        <button onClick={() => revokeInvite(inv.invite_id)} className="text-xs text-[var(--color-status-error)] hover:underline">
                          {zh ? '撤销' : 'Revoke'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </section>
      ) : (
        <p className="text-xs text-[var(--color-muted)]">{zh ? '当前角色无权管理成员（需 owner/admin）' : 'Member management requires owner/admin role'}</p>
      )}
    </div>
  );
}
