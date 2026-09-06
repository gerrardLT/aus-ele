// web/src/pages/OrgAdminPage.jsx
// R1.4 组织自助管理（2026-09-06）：成员名册 / 邀请 / 工作空间清单 / 域名 / 审计。
//
// 挂在 /account/org 下（AccountPage 的 tab），不新开根路由 —— 账户中心的子界面历来
// 由 AccountPage 自己按 pathname 分发，`resolveRootPage('/account/…')` 已返回 'account'。
//
// 门控判据全部来自 lib/orgAdmin.js（有 node:test 与后端源码逐条比对）。这里只渲染结论，
// 并刻意**不**因为前端判过了就省掉请求：后端才是授权方，403 照常显示。

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useAuth } from '../contexts/AuthContext.jsx';
import { getApiBase } from '../lib/apiBase.js';
import {
  ORG_INVITE_ROLES,
  canManageOrganization,
  currentOrganization,
  describeOrgError,
  orgDomainsUrl,
  orgDomainVerificationUrl,
  orgInviteActionUrl,
  orgInviteLink,
  orgInvitesUrl,
  orgMemberActionUrl,
  orgMembersUrl,
  organizationUrl,
  orgAuditLogsUrl,
  orgOwnerTransferUrl,
  orgWorkspacesUrl,
  visibleSections,
} from '../lib/orgAdmin.js';

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function Card({ title, hint, children }) {
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{title}</h3>
        {hint ? <p className="mt-1 text-[10px] leading-relaxed text-[var(--color-muted)]">{hint}</p> : null}
      </div>
      {children}
    </section>
  );
}

const BTN = 'rounded-lg border border-[var(--color-border)] px-2 py-1 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-text)] disabled:opacity-40';
const INPUT = 'rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1 text-xs text-[var(--color-text)]';

function MembersSection({ zh, oid, getToken, myPrincipalId, onError, onChanged }) {
  const [rows, setRows] = useState([]);
  const load = useCallback(async () => {
    const token = await getToken();
    const res = await fetch(orgMembersUrl(API_BASE, oid), { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    setRows((await res.json()).items || []);
  }, [oid, getToken, onError]);
  useEffect(() => { load(); }, [load]);

  const act = async (principalId, action) => {
    const token = await getToken();
    const res = await fetch(orgMemberActionUrl(API_BASE, oid, principalId, action), { method: 'POST', headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    onChanged(zh ? `已${action === 'suspend' ? '停用' : action === 'reactivate' ? '恢复' : '移出'}成员` : `Member ${action}`);
    load();
  };

  const transfer = async (principalId) => {
    const warning = zh
      ? `确定把组织 owner 移交给 ${principalId}？移交后你将失去 org_manage（含域名管理与再次移交的权力）。`
      : `Transfer org owner to ${principalId}? You lose org_manage (including domain control and further transfers).`;
    if (!globalThis.confirm(warning)) return;
    const token = await getToken();
    const res = await fetch(orgOwnerTransferUrl(API_BASE, oid), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ new_owner_principal_id: principalId }),
    });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    onChanged(zh ? 'owner 已移交，界面权限将随角色变化' : 'Owner transferred');
    load();
  };

  return (
    <Card
      title={zh ? '组织成员' : 'Organization members'}
      hint={zh ? '停用会立即吊销该账户的全部会话；移出不可撤销。「停用/恢复/移出」作用于组织层成员身份，工作空间成员关系另在成员管理页处理。' : 'Suspend revokes all sessions of that account; remove is irreversible.'}
    >
      <ul className="space-y-2">
        {rows.map((row) => (
          <li key={row.organization_membership_id || row.principal_id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-medium text-[var(--color-text)]">{row.principal?.display_name || '—'}</span>
            <span className="text-[var(--color-muted)]">{row.principal?.email}</span>
            <span className="rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[10px]">{row.role}</span>
            {row.status !== 'active' ? <span className="rounded bg-[var(--color-status-error)] px-1.5 py-0.5 text-[10px] text-white">{row.status}</span> : null}
            <span className="ml-auto flex gap-1">
              {row.principal_id === myPrincipalId ? null : (
                <>
                  {row.status === 'active' ? (
                    <button type="button" className={BTN} onClick={() => act(row.principal_id, 'suspend')}>{zh ? '停用' : 'Suspend'}</button>
                  ) : (
                    <button type="button" className={BTN} onClick={() => act(row.principal_id, 'reactivate')}>{zh ? '恢复' : 'Reactivate'}</button>
                  )}
                  <button type="button" className={BTN} onClick={() => act(row.principal_id, 'remove')}>{zh ? '移出' : 'Remove'}</button>
                  {row.role !== 'org_owner' && row.status === 'active' ? (
                    <button type="button" className={BTN} onClick={() => transfer(row.principal_id)}>{zh ? '移交 owner' : 'Make owner'}</button>
                  ) : null}
                </>
              )}
            </span>
          </li>
        ))}
        {rows.length === 0 ? <li className="text-xs text-[var(--color-muted)]">—</li> : null}
      </ul>
    </Card>
  );
}

function InvitesSection({ zh, oid, getToken, onError, onChanged, workspaces = [] }) {
  const [rows, setRows] = useState([]);
  const [email, setEmail] = useState('');
  const [role, setRole] = useState('org_member');
  // 落地工作空间：留空 = 让后端自选本组织任一空间。受邀者拿到的 token 是他唯一的入场券，
  // 而后端在缺省时也会兜住（组织一个空间都没有时才拒绝落地），所以这里不该有必填项。
  const [landingWorkspace, setLandingWorkspace] = useState('');
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const token = await getToken();
    const res = await fetch(`${orgInvitesUrl(API_BASE, oid)}?status=pending`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    setRows((await res.json()).items || []);
  }, [oid, getToken, onError]);
  useEffect(() => { load(); }, [load]);

  const create = async (event) => {
    event.preventDefault();
    setBusy(true);
    const token = await getToken();
    const res = await fetch(orgInvitesUrl(API_BASE, oid), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({
        email: email.trim(),
        target_role: role,
        workspace_id: landingWorkspace || undefined,
      }),
    });
    setBusy(false);
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    const invite = await res.json();
    const link = orgInviteLink(globalThis.location.origin, invite.invite_token);
    try { await navigator.clipboard.writeText(link); } catch { /* 剪贴板不可用时下方仍给出链接 */ }
    onChanged(zh ? `邀请已创建，链接已复制：${link}` : `Invite created, link copied: ${link}`);
    setEmail('');
    load();
  };

  const act = async (inviteId, action) => {
    const token = await getToken();
    const res = await fetch(orgInviteActionUrl(API_BASE, oid, inviteId, action), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(action === 'revoke' ? { revoke_reason: 'manual_revoke' } : {}),
    });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    onChanged(action === 'revoke' ? (zh ? '邀请已撤销' : 'Invite revoked') : (zh ? '邀请已重发（token 不变）' : 'Invite reissued (same token)'));
    load();
  };

  return (
    <Card
      title={zh ? '组织邀请' : 'Organization invites'}
      hint={zh ? '组织级邀请授予的是整个组织的成员身份（可访问该组织下所有工作空间），比工作空间级邀请宽；只在确实需要跨空间协作时使用。不能邀请 org_owner —— owner 只能靠移交产生。接受邀请时后端会顺带把受邀者放进一个工作空间（viewer），否则他登录后会取不到任何空间。' : 'Organization-level invites span every workspace in the org. org_owner cannot be invited. Accepting also lands the invitee in a workspace as viewer, otherwise they could not sign in at all.'}
    >
      <form onSubmit={create} className="mb-3 flex flex-wrap items-center gap-2">
        <input className={INPUT} type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder={zh ? '邮箱' : 'email'} />
        <select className={INPUT} value={role} onChange={(e) => setRole(e.target.value)} aria-label={zh ? '组织角色' : 'organization role'}>
          {ORG_INVITE_ROLES.map((r) => <option key={r} value={r}>{r}</option>)}
        </select>
        <select
          className={INPUT}
          value={landingWorkspace}
          onChange={(e) => setLandingWorkspace(e.target.value)}
          aria-label={zh ? '落地工作空间' : 'landing workspace'}
        >
          <option value="">{zh ? '落地空间：自动' : 'Landing: auto'}</option>
          {workspaces.map((ws) => (
            <option key={ws.workspace_id} value={ws.workspace_id}>{ws.name || ws.workspace_id}</option>
          ))}
        </select>
        <button type="submit" className={BTN} disabled={busy || !email.trim()}>{zh ? '创建邀请' : 'Create invite'}</button>
      </form>
      <ul className="space-y-1.5">
        {rows.map((row) => (
          <li key={row.invite_id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-[var(--color-text)]">{row.email}</span>
            <span className="rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[10px]">{row.target_role}</span>
            <span className="text-[10px] text-[var(--color-muted)]">{row.expires_at ? `${zh ? '到期' : 'expires'} ${row.expires_at.slice(0, 10)}` : (zh ? '不过期' : 'no expiry')}</span>
            <span className="ml-auto flex gap-1">
              <button type="button" className={BTN} onClick={() => act(row.invite_id, 'reissue')}>{zh ? '延期' : 'Extend'}</button>
              <button type="button" className={BTN} onClick={() => act(row.invite_id, 'revoke')}>{zh ? '撤销' : 'Revoke'}</button>
            </span>
          </li>
        ))}
        {rows.length === 0 ? <li className="text-xs text-[var(--color-muted)]">{zh ? '无待处理邀请' : 'No pending invites'}</li> : null}
      </ul>
    </Card>
  );
}

function DomainsSection({ zh, oid, getToken, onError, onChanged }) {
  const [rows, setRows] = useState([]);
  const [domain, setDomain] = useState('');
  const [joinMode, setJoinMode] = useState('invite_only');
  const [challenge, setChallenge] = useState(null);
  const [confirmToken, setConfirmToken] = useState('');

  const load = useCallback(async () => {
    const token = await getToken();
    const res = await fetch(orgDomainsUrl(API_BASE, oid), { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    setRows((await res.json()).items || []);
  }, [oid, getToken, onError]);
  useEffect(() => { load(); }, [load]);

  const post = async (path, body) => {
    const token = await getToken();
    const res = await fetch(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify(body || {}),
    });
    const payload = await res.json().catch(() => ({}));
    if (!res.ok) { onError(payload, res.status); return null; }
    return payload;
  };

  const register = async (event) => {
    event.preventDefault();
    const row = await post(orgDomainsUrl(API_BASE, oid), { domain: domain.trim(), join_mode: joinMode });
    if (!row) return;
    onChanged(zh ? '域名已登记。登记不等于授权：必须完成所有权验证，auto-join 才会生效。' : 'Domain registered. Registration is not authorization — verify ownership before auto-join works.');
    setDomain('');
    load();
  };

  const begin = async (row) => {
    const result = await post(orgDomainVerificationUrl(API_BASE, oid, row.domain_id, 'begin'), { method: 'dns_txt' });
    if (!result) return;
    setChallenge(result);
    onChanged(result.already_verified ? (zh ? '该域名已验证' : 'Already verified') : (zh ? '请按下方 TXT 记录配置 DNS 后再点「确认」' : 'Publish the TXT record, then confirm.'));
  };

  const confirmDomain = async (row, method) => {
    const result = await post(orgDomainVerificationUrl(API_BASE, oid, row.domain_id, 'confirm'), { method, token: confirmToken || null });
    if (!result) return;
    onChanged(zh ? '域名验证已更新' : 'Domain verification updated');
    setChallenge(null);
    setConfirmToken('');
    load();
  };

  return (
    <Card
      title={zh ? '组织域名' : 'Organization domains'}
      hint={zh ? '公共邮箱域名（gmail.com 等）一律被后端拒绝。未验证的域名不会带来自动入组。列表永不返回验证 token —— 那是所有权证明物。' : 'Public email domains are rejected. Unverified domains never auto-join. The token is never returned by the API.'}
    >
      <form onSubmit={register} className="mb-3 flex flex-wrap items-center gap-2">
        <input className={INPUT} required value={domain} onChange={(e) => setDomain(e.target.value)} placeholder={zh ? 'example.com' : 'example.com'} />
        <select className={INPUT} value={joinMode} onChange={(e) => setJoinMode(e.target.value)} aria-label={zh ? '加入模式' : 'join mode'}>
          <option value="invite_only">invite_only</option>
          <option value="domain_auto_join_org">domain_auto_join_org</option>
        </select>
        <button type="submit" className={BTN} disabled={!domain.trim()}>{zh ? '登记域名' : 'Register'}</button>
      </form>
      <ul className="space-y-1.5">
        {rows.map((row) => (
          <li key={row.domain_id} className="flex flex-wrap items-center gap-2 text-xs">
            <span className="text-[var(--color-text)]">{row.domain}</span>
            <span className="rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[10px]">{row.join_mode}</span>
            <span className={`rounded px-1.5 py-0.5 text-[10px] ${row.verified ? 'bg-[var(--color-status-success)] text-white' : 'bg-[var(--color-status-error)] text-white'}`}>
              {row.verified ? (zh ? '已验证' : 'verified') : (zh ? '未验证' : 'unverified')}
            </span>
            <span className="ml-auto flex gap-1">
              <button type="button" className={BTN} onClick={() => begin(row)}>{zh ? '发起验证' : 'Verify'}</button>
              <button type="button" className={BTN} onClick={() => confirmDomain(row, 'dns_txt')}>{zh ? '确认' : 'Confirm'}</button>
            </span>
          </li>
        ))}
        {rows.length === 0 ? <li className="text-xs text-[var(--color-muted)]">—</li> : null}
      </ul>
      {challenge?.dns ? (
        <div className="mt-3 rounded-lg bg-[var(--color-panel)] p-3 text-[10px] text-[var(--color-muted)]">
          <div>TXT {challenge.dns.record_name}</div>
          <div className="font-mono text-[var(--color-text)] break-all">{challenge.dns.record_value}</div>
        </div>
      ) : null}
      {challenge && !challenge.already_verified && !challenge.dns ? (
        <div className="mt-3 flex flex-wrap items-center gap-2">
          <input className={INPUT} value={confirmToken} onChange={(e) => setConfirmToken(e.target.value)} placeholder={zh ? '邮箱收到的挑战串' : 'code from email'} />
        </div>
      ) : null}
    </Card>
  );
}

function WorkspacesSection({ zh, oid, getToken, onError }) {
  const [rows, setRows] = useState([]);
  const load = useCallback(async () => {
    const token = await getToken();
    const res = await fetch(orgWorkspacesUrl(API_BASE, oid), { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    setRows((await res.json()).items || []);
  }, [oid, getToken, onError]);
  useEffect(() => { load(); }, [load]);

  return (
    <Card title={zh ? '组织下工作空间' : 'Workspaces'} hint={zh ? '此页只列不建：建空间仍在工作空间层。' : 'Read-only here.'}>
      <ul className="space-y-1.5">
        {rows.map((row) => (
          <li key={row.workspace_id} className="flex items-center gap-2 text-xs">
            {/* 刻意不做成链接：切空间由顶栏 WorkspaceSwitcher 负责，这里放链接会出现
                一个没人读的 query 参数（点了没反应），比不放更糟。 */}
            <span className="text-[var(--color-text)]">{row.name || row.workspace_id}</span>
            <span className="text-[10px] text-[var(--color-muted)]">{row.my_workspace_role ? `${zh ? '我的角色' : 'my role'}: ${row.my_workspace_role}` : (zh ? '非空间成员' : 'not a member')}</span>
          </li>
        ))}
        {rows.length === 0 ? <li className="text-xs text-[var(--color-muted)]">—</li> : null}
      </ul>
    </Card>
  );
}

function AuditSection({ zh, oid, getToken, onError }) {
  const [rows, setRows] = useState([]);
  const load = useCallback(async () => {
    const token = await getToken();
    const res = await fetch(`${orgAuditLogsUrl(API_BASE, oid)}?limit=50`, { headers: { Authorization: `Bearer ${token}` } });
    if (!res.ok) { onError(await res.json().catch(() => ({})), res.status); return; }
    setRows((await res.json()).items || []);
  }, [oid, getToken, onError]);
  useEffect(() => { load(); }, [load]);

  return (
    <Card
      title={zh ? '组织审计流水' : 'Organization audit log'}
      hint={zh ? '按当前可见条数倒序，最多 50 条。后端只提供本组织范围内的记录。' : 'Last 50 entries scoped to this organization.'}
    >
      <ul className="space-y-1">
        {rows.map((row) => (
          <li key={row.audit_id || `${row.created_at}-${row.action}`} className="flex flex-wrap items-center gap-2 text-[10px] text-[var(--color-muted)]">
            <span className="font-mono">{(row.created_at || '').slice(0, 16).replace('T', ' ')}</span>
            <span className="text-[var(--color-text)]">{row.action}</span>
            <span>{row.actor_principal_id || '—'}</span>
          </li>
        ))}
        {rows.length === 0 ? <li className="text-xs text-[var(--color-muted)]">—</li> : null}
      </ul>
    </Card>
  );
}

export default function OrgAdminPage() {
  const { auth, getToken } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const org = useMemo(() => currentOrganization(auth), [auth]);
  const sections = useMemo(() => visibleSections(org ? { organizationRole: org.organizationRole } : null), [org]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [overview, setOverview] = useState(null);

  const onError = useCallback((payload, status) => {
    setError(describeOrgError(payload, status, zh));
    setNotice('');
  }, [zh]);
  const onChanged = useCallback((message) => { setNotice(message); setError(''); }, []);

  const organizationId = org?.organizationId || null;
  useEffect(() => {
    if (!organizationId) return undefined;
    let cancelled = false;
    (async () => {
      const token = await getToken();
      const res = await fetch(organizationUrl(API_BASE, organizationId), { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok || cancelled) return;
      setOverview(await res.json().catch(() => null));
    })();
    return () => { cancelled = true; };
  }, [organizationId, getToken]);

  if (!org) {
    return (
      <Card title={zh ? '组织管理' : 'Organization'} hint={zh ? '当前工作空间不属于任何组织，或登录记录过旧。' : 'The current workspace has no organization.'}>
        <p className="text-xs text-[var(--color-muted)]">
          {zh ? '请在顶栏切换到属于某个组织的工作空间，或退出后重新登录以刷新组织信息。' : 'Switch workspace, or sign out and back in to refresh organization info.'}
        </p>
      </Card>
    );
  }

  if (!org.organizationRoleKnown) {
    // 2026-09-06 之前签发的 StoredAuth 里没有 organization_role。不写这段的话，真
    // org_owner 只会看到一个几乎没有入口的页面，并且得不到任何解释。
    return (
      <Card title={org.organizationName || (zh ? '组织管理' : 'Organization')}>
        <p className="text-xs text-[var(--color-muted)]">
          {zh ? '本地登录记录缺少组织角色，无法判断你能管理什么。请退出后重新登录（或切换一次工作空间）。' : 'Your local session has no organization role. Sign in again or switch workspace once.'}
        </p>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      <Card
        title={org.organizationName || (zh ? '组织' : 'Organization')}
        hint={zh ? `你的组织角色：${org.organizationRole || '（无）'}${overview ? ` · 成员 ${overview.member_count} 人 · 工作空间 ${overview.workspaces.length} 个` : ''}。权限按工作空间所属组织逐条判定，切换空间可能改变这里能看到的东西。` : `Your organization role: ${org.organizationRole || '(none)'}${overview ? ` · ${overview.member_count} members · ${overview.workspaces.length} workspaces` : ''}.`}
      >
        {canManageOrganization({ organizationRole: org.organizationRole }) ? null : (
          <p className="text-xs text-[var(--color-muted)]">{zh ? '你在该组织内没有管理权限，这里只显示概览。' : 'You have no management rights in this organization.'}</p>
        )}
      </Card>

      {error ? <p className="rounded-lg bg-[var(--color-status-error)]/10 p-3 text-xs text-[var(--color-status-error)]">{error}</p> : null}
      {notice ? <p className="rounded-lg bg-[var(--color-status-success)]/10 p-3 text-xs text-[var(--color-status-success)]">{notice}</p> : null}

      {sections.includes('members') ? <MembersSection zh={zh} oid={org.organizationId} getToken={getToken} myPrincipalId={auth?.principal?.principal_id} onError={onError} onChanged={onChanged} /> : null}
      {sections.includes('invites') ? <InvitesSection zh={zh} oid={org.organizationId} getToken={getToken} onError={onError} onChanged={onChanged} workspaces={overview?.workspaces || []} /> : null}
      {sections.includes('workspaces') ? <WorkspacesSection zh={zh} oid={org.organizationId} getToken={getToken} onError={onError} /> : null}
      {sections.includes('domains') ? <DomainsSection zh={zh} oid={org.organizationId} getToken={getToken} onError={onError} onChanged={onChanged} /> : null}
      {sections.includes('audit') ? <AuditSection zh={zh} oid={org.organizationId} getToken={getToken} onError={onError} /> : null}
    </div>
  );
}
