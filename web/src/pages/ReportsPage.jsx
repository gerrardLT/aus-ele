// web/src/pages/ReportsPage.jsx
// 报告中心（P2-2，2026-08-14）：已保存报告库 + 生成并保存。路由 /reports。

import { useCallback, useEffect, useState } from 'react';
import { AuthProvider, useAuth } from '../contexts/AuthContext.jsx';
import { usePermissions } from '../hooks/usePermissions.js';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

const NEM_REGIONS = ['NSW1', 'VIC1', 'QLD1', 'SA1', 'TAS1'];

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

function ReportsHome() {
  const { auth, getToken, isLoggedIn } = useAuth();
  const zh = readLang() === 'zh';
  const workspaceId = auth?.workspaceId;
  // 后端真值：DELETE /v1/reports/saved/{id} 用裸角色判定 owner/admin（p2_routes.py:233）。
  // 这里刻意只门控「删除」：报告生成与查看任何 workspace 成员都能做（:217 只查 _assert_workspace），
  // 把它升级成更大的 canManage 会误伤只读成员。
  const { canInWorkspace } = usePermissions(auth);
  const canDelete = canInWorkspace('workspace_manage');

  const [items, setItems] = useState([]);
  const [subs, setSubs] = useState([]);
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({ title: '', market: 'NEM', region: 'NSW1', year: new Date().getFullYear() - 1 });
  const [subForm, setSubForm] = useState({ title: '', region: 'NSW1', frequency: 'monthly', day_of_month: '1', day_of_week: 'mon', email: '' });

  const load = useCallback(async () => {
    if (!workspaceId) return;
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/reports/saved?workspace_id=${workspaceId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setItems((await res.json()).items || []);
  }, [workspaceId, getToken]);

  useEffect(() => { if (isLoggedIn) load().catch(() => {}); }, [isLoggedIn, load]);

  const loadSubs = useCallback(async () => {
    if (!workspaceId) return;
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/reports/subscriptions?workspace_id=${workspaceId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setSubs((await res.json()).items || []);
  }, [workspaceId, getToken]);

  useEffect(() => { if (isLoggedIn) loadSubs().catch(() => {}); }, [isLoggedIn, loadSubs]);

  const createSub = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/v1/reports/subscriptions`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          workspace_id: workspaceId,
          title: subForm.title || `${subForm.region} 月度报告`,
          region: subForm.region,
          frequency: subForm.frequency,
          day_of_month: subForm.frequency === 'monthly' ? Number(subForm.day_of_month) : null,
          day_of_week: subForm.frequency === 'weekly' ? subForm.day_of_week : null,
          email: subForm.email || null,
        }),
      });
      if (!res.ok) { setError((await res.json().catch(() => ({}))).detail || `Failed (${res.status})`); return; }
      setSubForm((f) => ({ ...f, title: '', email: '' }));
      await loadSubs();
    } catch {
      setError(zh ? '网络错误，请稍后重试' : 'Network error, please retry');
    } finally {
      setBusy(false);
    }
  };

  const removeSub = async (id) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/reports/subscriptions/${id}?workspace_id=${workspaceId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) await loadSubs();
  };

  const generateAndSave = async (e) => {
    e.preventDefault();
    if (!workspaceId) return;
    setBusy(true); setError('');
    try {
      const token = await getToken();
      const res = await fetch(`${API_BASE}/v1/reports/save`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          workspace_id: workspaceId,
          title: form.title || `${form.region} ${form.year} ${zh ? '月度市场报告' : 'Monthly market report'}`,
          market: form.market,
          region: form.region,
          year: Number(form.year),
        }),
      });
      if (!res.ok) { setError((await res.json().catch(() => ({}))).detail || `Failed (${res.status})`); return; }
      setForm((f) => ({ ...f, title: '' }));
      await load();
    } catch {
      setError(zh ? '网络错误，请稍后重试' : 'Network error, please retry');
    } finally {
      setBusy(false);
    }
  };

  const openReport = async (id) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/reports/saved/${id}?workspace_id=${workspaceId}`, {
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) setSelected(await res.json());
  };

  const removeReport = async (id) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/reports/saved/${id}?workspace_id=${workspaceId}`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${token}` },
    });
    if (res.ok) { if (selected?.report_id === id) setSelected(null); await load(); }
  };

  const inputCls = 'rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-text)]';

  return (
    <div className="mx-auto max-w-6xl px-6 py-10">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="font-serif text-xl text-[var(--color-text)]">{zh ? '报告中心' : 'Report center'}</h1>
        <a href="/" className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">← {zh ? '返回' : 'Back'}</a>
      </div>

      {!isLoggedIn ? (
        <p className="py-12 text-center text-sm text-[var(--color-muted)]">
          {zh ? '报告中心需要登录。' : 'Sign in required.'}{' '}
          <a href="/login" className="text-[var(--color-primary)] hover:underline">{zh ? '去登录' : 'Sign in'}</a>
        </p>
      ) : (
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <form onSubmit={generateAndSave} className="space-y-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
            <h2 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '生成并保存' : 'Generate & save'}</h2>
            <input placeholder={zh ? '报告标题（可留空）' : 'Title (optional)'} value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })} className={`w-full ${inputCls}`} />
            <div className="flex gap-2">
              <select value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value, region: e.target.value === 'NEM' ? 'NSW1' : 'WEM' })} className={inputCls}>
                <option value="NEM">NEM</option>
                <option value="WEM">WEM</option>
              </select>
              {form.market === 'NEM' ? (
                <select value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })} className={inputCls}>
                  {NEM_REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
              ) : (
                <input value="WEM" readOnly className={`${inputCls} w-20`} />
              )}
              <input type="number" min="2015" max="2100" value={form.year}
                onChange={(e) => setForm({ ...form, year: e.target.value })} className={`w-24 ${inputCls}`} />
            </div>
            <button type="submit" disabled={busy}
              className="w-full rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
              {busy ? (zh ? '生成中…' : 'Generating…') : (zh ? '生成并保存' : 'Generate & save')}
            </button>
            {error && <p className="text-xs text-[var(--color-status-error)]">{error}</p>}
          </form>

          <div className="lg:col-span-2 space-y-4">
            <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
              <table className="w-full border-collapse text-xs">
                <thead>
                  <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
                    <th className="px-3 py-2 font-semibold">{zh ? '标题' : 'Title'}</th>
                    <th className="px-3 py-2 font-semibold">{zh ? '范围' : 'Scope'}</th>
                    <th className="px-3 py-2 font-semibold">{zh ? '时间' : 'Created'}</th>
                    <th className="px-3 py-2" />
                  </tr>
                </thead>
                <tbody className="text-[var(--color-text)]">
                  {items.length === 0 && (
                    <tr><td colSpan={4} className="px-3 py-6 text-center text-[var(--color-muted)]">{zh ? '暂无保存的报告' : 'No saved reports'}</td></tr>
                  )}
                  {items.map((r) => (
                    <tr key={r.report_id} className="border-b border-[var(--color-border)] last:border-b-0">
                      <td className="px-3 py-2">
                        <button type="button" onClick={() => openReport(r.report_id)} className="text-[var(--color-primary)] hover:underline">{r.title}</button>
                      </td>
                      <td className="px-3 py-2 font-mono text-[10px]">{r.market}/{r.region}/{r.year}</td>
                      <td className="px-3 py-2 font-mono text-[10px]">{(r.created_at || '').slice(0, 10)}</td>
                      <td className="px-3 py-2 text-right">
                        {canDelete && (
                          <button type="button" onClick={() => removeReport(r.report_id)} className="text-[10px] text-[var(--color-status-error)] hover:underline">
                            {zh ? '删除' : 'Delete'}
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {selected && (
              <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <div className="mb-2 flex items-center justify-between">
                  <h3 className="text-sm font-semibold text-[var(--color-text)]">{selected.title}</h3>
                  <button type="button" onClick={() => setSelected(null)} className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)]">✕</button>
                </div>
                <pre className="max-h-96 overflow-auto rounded-lg bg-[var(--color-panel)] p-3 font-mono text-[10px] leading-relaxed text-[var(--color-muted)]">
                  {JSON.stringify(selected.payload, null, 2)}
                </pre>
              </section>
            )}

            {/* 定时订阅（2026-08-14）：邮件/站内推送 */}
            <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
              <h2 className="mb-3 text-sm font-semibold text-[var(--color-text)]">{zh ? '定时订阅（每日 03:20 检查投递）' : 'Scheduled subscriptions (dispatched daily 03:20)'}</h2>
              <form onSubmit={createSub} className="flex flex-wrap items-center gap-2">
                <input placeholder={zh ? '订阅标题' : 'Title'} value={subForm.title}
                  onChange={(e) => setSubForm({ ...subForm, title: e.target.value })} className={inputCls} />
                <select value={subForm.region} onChange={(e) => setSubForm({ ...subForm, region: e.target.value })} className={inputCls}>
                  {NEM_REGIONS.map((r) => <option key={r} value={r}>{r}</option>)}
                </select>
                <select value={subForm.frequency} onChange={(e) => setSubForm({ ...subForm, frequency: e.target.value })} className={inputCls}>
                  <option value="monthly">{zh ? '每月' : 'Monthly'}</option>
                  <option value="weekly">{zh ? '每周' : 'Weekly'}</option>
                </select>
                {subForm.frequency === 'monthly' ? (
                  <input type="number" min="1" max="31" value={subForm.day_of_month}
                    onChange={(e) => setSubForm({ ...subForm, day_of_month: e.target.value })}
                    title={zh ? '每月几号' : 'Day of month'} className={`w-20 ${inputCls}`} />
                ) : (
                  <select value={subForm.day_of_week} onChange={(e) => setSubForm({ ...subForm, day_of_week: e.target.value })} className={inputCls}>
                    {['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'].map((d) => <option key={d} value={d}>{d}</option>)}
                  </select>
                )}
                <input placeholder={zh ? '收件邮箱（缺省用账户邮箱）' : 'Email (default: account email)'} value={subForm.email}
                  onChange={(e) => setSubForm({ ...subForm, email: e.target.value })} className={`w-56 ${inputCls}`} />
                <button type="submit" disabled={busy}
                  className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
                  {zh ? '创建订阅' : 'Subscribe'}
                </button>
              </form>
              <ul className="mt-3 space-y-1.5">
                {subs.length === 0 && <li className="text-xs text-[var(--color-muted)]">{zh ? '暂无订阅' : 'No subscriptions'}</li>}
                {subs.map((s) => (
                  <li key={s.subscription_id} className="flex items-center justify-between rounded-lg border border-[var(--color-border)] px-3 py-1.5 text-xs text-[var(--color-text)]">
                    <span>
                      {s.title} · {s.region} · {s.frequency === 'monthly' ? (zh ? `每月 ${s.day_of_month} 日` : `day ${s.day_of_month}`) : (zh ? `每 ${s.day_of_week}` : s.day_of_week)}
                      {s.last_sent_at ? <span className="ml-2 text-[10px] text-[var(--color-muted)]">{zh ? '上次' : 'last'} {(s.last_sent_at || '').slice(0, 10)}</span> : null}
                    </span>
                    <button type="button" onClick={() => removeSub(s.subscription_id)} className="text-[10px] text-[var(--color-status-error)] hover:underline">
                      {zh ? '删除' : 'Delete'}
                    </button>
                  </li>
                ))}
              </ul>
            </section>
          </div>
        </div>
      )}
    </div>
  );
}

export default function ReportsPage() {
  return (
    <div className="min-h-screen bg-[var(--color-bg)]">
      <AuthProvider>
        <ReportsHome />
      </AuthProvider>
    </div>
  );
}
