// web/src/pages/AccountPage.jsx
// 账户中心（P0，2026-08-13）：总览（个人资料+工作空间+用量看板）+ 子页导航。
// 子路由：/account（总览） /account/members（成员） /account/api-keys（API Key）

import { Suspense, lazy, useCallback, useEffect, useState } from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext.jsx';
import { getApiBase } from '../lib/apiBase.js';

const MembersPage = lazy(() => import('./MembersPage.jsx'));
const ApiKeysPage = lazy(() => import('./ApiKeysPage.jsx'));
const AlertRulesPage = lazy(() => import('./AlertRulesPage.jsx'));
const AuditPage = lazy(() => import('./AuditPage.jsx'));

const API_BASE = getApiBase();

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function UsageBars({ title, rows, valueKey, color }) {
  const max = Math.max(1, ...rows.map((r) => r[valueKey] || 0));
  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <h3 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{title}</h3>
      {rows.length === 0 ? (
        <p className="text-xs text-[var(--color-muted)]">—</p>
      ) : (
        <div className="space-y-1.5">
          {rows.slice(-14).map((r) => (
            <div key={r.date} className="flex items-center gap-2 text-[10px] text-[var(--color-muted)]">
              <span className="w-16 shrink-0 font-mono">{r.date.slice(5)}</span>
              <div className="h-3 flex-1 rounded-sm bg-[var(--color-panel)]">
                <div
                  className="h-3 rounded-sm"
                  style={{ width: `${Math.max(2, ((r[valueKey] || 0) / max) * 100)}%`, background: color }}
                />
              </div>
              <span className="w-12 shrink-0 text-right font-mono">{r[valueKey] || 0}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

function QuotaBar({ label, used, limit, over }) {
  const pct = limit ? Math.min(100, ((used || 0) / limit) * 100) : 0;
  return (
    <div className="mb-2">
      <div className="mb-1 flex items-center justify-between text-[10px] text-[var(--color-muted)]">
        <span>{label}</span>
        <span className="font-mono">{used}{limit != null ? ` / ${limit}` : ' / ∞'}{over ? ' ⚠' : ''}</span>
      </div>
      <div className="h-2 rounded-full bg-[var(--color-panel)]">
        <div
          className="h-2 rounded-full"
          style={{ width: `${Math.max(2, pct)}%`, background: over ? 'var(--color-status-error)' : 'var(--color-primary)' }}
        />
      </div>
    </div>
  );
}

function SubscriptionCard({ zh, workspaceId, role, getToken, onPlanChanged }) {
  const [sub, setSub] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    if (!workspaceId) return;
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/account/workspaces/${workspaceId}/subscription`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setSub(await res.json());
  }, [workspaceId, getToken]);

  useEffect(() => { load(); }, [load]);

  const changePlan = async (e) => {
    const plan = e.target.value;
    setBusy(true);
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/account/workspaces/${workspaceId}/subscription`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ plan }),
    });
    setBusy(false);
    if (res.ok) { setSub((s) => ({ ...s, plan })); onPlanChanged?.(); }
  };

  if (!sub) return null;
  const t = sub.today || {};

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '订阅与配额' : 'Subscription & quota'}</h3>
        {role === 'owner' ? (
          <select value={sub.plan} onChange={changePlan} disabled={busy}
            className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-1 text-xs text-[var(--color-text)]">
            <option value="starter">starter</option>
            <option value="growth">growth</option>
            <option value="pro">pro</option>
          </select>
        ) : (
          <span className="rounded bg-[var(--color-border)] px-2 py-0.5 text-[10px] font-semibold">{sub.plan}</span>
        )}
      </div>
      <QuotaBar label={zh ? 'Agent 运行（今日）' : 'Agent runs (today)'} used={t.agent_runs} limit={t.agent_run_limit} over={t.agent_over_quota} />
      <QuotaBar label={zh ? 'API 用量（今日 units）' : 'API units (today)'} used={t.api_units} limit={t.api_unit_limit} over={t.api_over_quota} />
      <p className="mt-2 text-[10px] text-[var(--color-muted)]">{sub.note}</p>
    </section>
  );
}

function PasswordChangeForm({ zh, getToken }) {
  const [current, setCurrent] = useState('');
  const [next, setNext] = useState('');
  const [confirm, setConfirm] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState(null);

  const submit = async (e) => {
    e.preventDefault();
    if (next !== confirm) { setMsg({ ok: false, text: zh ? '两次新密码不一致' : 'New passwords do not match' }); return; }
    setBusy(true); setMsg(null);
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/v1/account/password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ current_password: current, new_password: next }),
      });
      if (res.ok) {
        setMsg({ ok: true, text: zh ? '密码已修改' : 'Password changed' });
        setCurrent(''); setNext(''); setConfirm('');
      } else {
        const err = await res.json().catch(() => ({}));
        setMsg({ ok: false, text: err.detail || `Failed (${res.status})` });
      }
    } catch {
      setMsg({ ok: false, text: zh ? '网络错误，请稍后重试' : 'Network error, please retry' });
    } finally {
      setBusy(false);
    }
  };

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-text)]';

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <h3 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? '修改密码' : 'Change password'}</h3>
      <form onSubmit={submit} className="space-y-2">
        <input type="password" required placeholder={zh ? '当前密码' : 'Current password'} value={current} onChange={(e) => setCurrent(e.target.value)} className={inputCls} />
        <input type="password" required minLength={8} placeholder={zh ? '新密码（至少 8 位）' : 'New password (min 8 chars)'} value={next} onChange={(e) => setNext(e.target.value)} className={inputCls} />
        <input type="password" required placeholder={zh ? '确认新密码' : 'Confirm new password'} value={confirm} onChange={(e) => setConfirm(e.target.value)} className={inputCls} />
        <div className="flex items-center gap-3">
          <button type="submit" disabled={busy} className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
            {busy ? (zh ? '提交中…' : 'Saving…') : (zh ? '修改密码' : 'Change')}
          </button>
          {msg && <span className={`text-xs ${msg.ok ? 'text-[var(--color-status-success)]' : 'text-[var(--color-status-error)]'}`}>{msg.text}</span>}
        </div>
      </form>
    </section>
  );
}

function SessionsSection({ zh, getToken }) {
  const [items, setItems] = useState([]);
  const [currentId, setCurrentId] = useState(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const token = await getToken();
    try {
      const res = await fetch(`${API_BASE}/v1/account/sessions`, {
        headers: { Authorization: `Bearer ${token}` },
      });
      if (res.ok) {
        const body = await res.json();
        setItems(body.items || []);
        setCurrentId(body.current_session_id);
      }
    } catch { /* best-effort */ }
  }, [getToken]);

  useEffect(() => { load(); }, [load]);

  const revokeOthers = async () => {
    setBusy(true);
    const token = await getToken();
    try {
      await fetch(`${API_BASE}/v1/account/sessions/revoke-others`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${token}` },
      });
      await load();
    } finally {
      setBusy(false);
    }
  };

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '活跃会话' : 'Active sessions'}</h3>
        {items.length > 1 && (
          <button type="button" onClick={revokeOthers} disabled={busy}
            className="rounded-lg border border-[var(--color-status-error)]/50 px-2 py-1 text-[10px] text-[var(--color-status-error)] hover:opacity-80 disabled:opacity-50">
            {zh ? '登出其他设备' : 'Sign out others'}
          </button>
        )}
      </div>
      <ul className="space-y-1.5">
        {items.map((s) => (
          <li key={s.session_id} className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-2 py-1.5 text-[10px] text-[var(--color-muted)]">
            <span>
              {s.auth_method || 'password'} · ws: {(s.workspace_id || '').slice(0, 12)}…
              {s.session_id === currentId && <span className="ml-1 text-[var(--color-status-success)]">{zh ? '（当前）' : '(current)'}</span>}
            </span>
            <span className="font-mono">{(s.last_seen_at || s.created_at || '').slice(0, 16).replace('T', ' ')}</span>
          </li>
        ))}
        {items.length === 0 && <li className="text-xs text-[var(--color-muted)]">{zh ? '无会话信息' : 'No sessions'}</li>}
      </ul>
    </section>
  );
}

function AccountHome() {
  const { auth, getToken } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const [usage, setUsage] = useState(null);
  const role = auth?.workspaces?.find((w) => w.workspace_id === auth?.workspaceId)?.role || '';

  const loadUsage = useCallback(async () => {
    if (!auth?.workspaceId) return;
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/account/workspaces/${auth.workspaceId}/usage?days=30`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setUsage(await res.json());
  }, [auth?.workspaceId, getToken]);

  useEffect(() => { loadUsage(); }, [loadUsage]);

  const currentWs = auth?.workspaces?.find((w) => w.workspace_id === auth?.workspaceId);

  // 显示名编辑（2026-08-14）
  const [editingName, setEditingName] = useState(false);
  const [nameDraft, setNameDraft] = useState('');
  const saveDisplayName = async () => {
    if (!nameDraft.trim()) return;
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/account/me`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ display_name: nameDraft.trim() }),
    });
    if (res.ok) {
      setEditingName(false);
      globalThis.location.reload();
    }
  };

  // 工作空间切换（2026-08-14）
  const { switchWorkspace } = useAuth();
  const onSwitchWorkspace = async (e) => {
    const wsId = e.target.value;
    if (!wsId || wsId === auth?.workspaceId) return;
    const res = await switchWorkspace(wsId);
    if (res.ok) globalThis.location.reload();
  };

  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6">
        <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <h3 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? '个人资料' : 'Profile'}</h3>
          <dl className="space-y-2 text-xs">
            <div><dt className="text-[var(--color-muted)]">{zh ? '邮箱' : 'Email'}</dt><dd className="mt-0.5 font-mono text-[var(--color-text)]">{auth?.principal?.email || '—'}</dd></div>
            <div>
              <dt className="text-[var(--color-muted)]">{zh ? '显示名' : 'Display name'}</dt>
              <dd className="mt-0.5 flex items-center gap-2 text-[var(--color-text)]">
                {editingName ? (
                  <>
                    <input value={nameDraft} onChange={(e) => setNameDraft(e.target.value)}
                      className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-0.5 text-xs text-[var(--color-text)]" />
                    <button type="button" onClick={saveDisplayName} className="text-[10px] text-[var(--color-primary)] hover:underline">{zh ? '保存' : 'Save'}</button>
                    <button type="button" onClick={() => setEditingName(false)} className="text-[10px] text-[var(--color-muted)] hover:underline">{zh ? '取消' : 'Cancel'}</button>
                  </>
                ) : (
                  <>
                    <span>{auth?.principal?.display_name || '—'}</span>
                    <button type="button" onClick={() => { setNameDraft(auth?.principal?.display_name || ''); setEditingName(true); }}
                      className="text-[10px] text-[var(--color-primary)] hover:underline">{zh ? '编辑' : 'Edit'}</button>
                  </>
                )}
              </dd>
            </div>
            <div>
              <dt className="text-[var(--color-muted)]">{zh ? '当前工作空间' : 'Workspace'}</dt>
              <dd className="mt-0.5 text-[var(--color-text)]">
                {(auth?.workspaces?.length || 0) > 1 ? (
                  <select value={auth?.workspaceId || ''} onChange={onSwitchWorkspace}
                    className="rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-2 py-0.5 text-xs text-[var(--color-text)]">
                    {auth.workspaces.map((w) => (
                      <option key={w.workspace_id} value={w.workspace_id}>{w.name}（{w.role}）</option>
                    ))}
                  </select>
                ) : (
                  <span>{currentWs?.name || auth?.workspaceId}</span>
                )}
              </dd>
            </div>
            <div><dt className="text-[var(--color-muted)]">{zh ? '组织' : 'Organization'}</dt><dd className="mt-0.5 text-[var(--color-text)]">{currentWs?.organization_name || '—'}</dd></div>
            <div><dt className="text-[var(--color-muted)]">{zh ? '角色' : 'Role'}</dt><dd className="mt-0.5 text-[var(--color-text)]">{currentWs?.role || '—'}</dd></div>
          </dl>
        </section>
        <SubscriptionCard zh={zh} workspaceId={auth?.workspaceId} role={role} getToken={getToken} onPlanChanged={loadUsage} />
        <PasswordChangeForm zh={zh} getToken={getToken} />
        <SessionsSection zh={zh} getToken={getToken} />
      </div>

      <UsageBars
        title={zh ? 'API 调用量（近 30 天，units/天）' : 'API usage (30d, units/day)'}
        rows={usage?.api_usage_daily || []}
        valueKey="units"
        color="var(--color-primary)"
      />
      <UsageBars
        title={zh ? 'Agent 运行次数（近 30 天）' : 'Agent runs (30d)'}
        rows={usage?.agent_runs_daily || []}
        valueKey="runs"
        color="var(--color-status-success)"
      />
    </div>
  );
}

function AccountShell() {
  const { auth, isLoggedIn, logout } = useAuth();
  const lang = readLang();
  const zh = lang === 'zh';
  const path = globalThis.location.pathname;

  useEffect(() => {
    if (!isLoggedIn) globalThis.location.href = '/login';
  }, [isLoggedIn]);

  if (!isLoggedIn) return null;

  const tabs = [
    { id: 'overview', path: '/account', label: zh ? '总览' : 'Overview' },
    { id: 'members', path: '/account/members', label: zh ? '成员管理' : 'Members' },
    { id: 'api-keys', path: '/account/api-keys', label: 'API Keys' },
    { id: 'alerts', path: '/account/alerts', label: zh ? '告警规则' : 'Alerts' },
    { id: 'audit', path: '/account/audit', label: zh ? '审计' : 'Audit' },
  ];
  const activeTab = tabs.find((t) => (t.id === 'overview' ? path === '/account' || path === '/account/' : path.startsWith(t.path))) || tabs[0];

  const handleLogout = async () => {
    await logout();
    globalThis.location.href = '/';
  };

  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <header className="border-b border-[var(--color-border)] bg-[var(--color-surface)]">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center gap-4 px-6 py-4">
          <a href="/" className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)] hover:text-[var(--color-text)]">
            ← AEMO Intelligence
          </a>
          <h1 className="font-serif text-lg text-[var(--color-text)]">{zh ? '账户中心' : 'Account'}</h1>
          <nav className="flex gap-1">
            {tabs.map((t) => (
              <a
                key={t.id}
                href={t.path}
                className={`rounded-lg px-3 py-1.5 text-xs font-medium transition-colors ${
                  activeTab.id === t.id
                    ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                    : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                }`}
              >
                {t.label}
              </a>
            ))}
          </nav>
          <div className="ml-auto flex items-center gap-3">
            <span className="text-xs text-[var(--color-muted)]">{auth?.principal?.email}</span>
            <button onClick={handleLogout} className="rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">
              {zh ? '登出' : 'Sign out'}
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-6 py-8">
        <Suspense fallback={<div className="py-16 text-center text-sm text-[var(--color-muted)]">{zh ? '加载中…' : 'Loading…'}</div>}>
          {activeTab.id === 'members' ? <MembersPage /> : activeTab.id === 'api-keys' ? <ApiKeysPage /> : activeTab.id === 'alerts' ? <AlertRulesPage /> : activeTab.id === 'audit' ? <AuditPage /> : <AccountHome />}
        </Suspense>
      </main>
    </div>
  );
}

export default function AccountPage() {
  return (
    <AuthProvider>
      <AccountShell />
    </AuthProvider>
  );
}
