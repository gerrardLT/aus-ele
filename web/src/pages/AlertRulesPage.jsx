// web/src/pages/AlertRulesPage.jsx
// 告警规则管理（P2-1，2026-08-14）：账户中心 tab。
// 复用既有 /api/alerts/* 端点（server.py 已有）；渠道支持 webhook/inapp/email。

import { useCallback, useEffect, useState } from 'react';
import { useAuth } from '../contexts/AuthContext.jsx';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();

const RULE_TYPES = [
  { id: 'price_threshold', zh: '价格阈值', en: 'Price threshold' },
  { id: 'data_freshness', zh: '数据新鲜度', en: 'Data freshness' },
  { id: 'wem_fcas_scarcity', zh: 'WEM FCAS 稀缺度', en: 'WEM FCAS scarcity' },
];
const CHANNEL_TYPES = [
  { id: 'inapp', zh: '站内通知', en: 'In-app' },
  { id: 'email', zh: '邮件', en: 'Email' },
  { id: 'webhook', zh: 'Webhook', en: 'Webhook' },
];

function readLang() {
  try { return globalThis.localStorage?.getItem('app_lang') || 'zh'; } catch { return 'zh'; }
}

export default function AlertRulesPage() {
  const { auth, getToken } = useAuth();
  const zh = readLang() === 'zh';
  const workspaceId = auth?.workspaceId;
  const role = auth?.workspaces?.find((w) => w.workspace_id === workspaceId)?.role || '';
  const canManage = role === 'owner' || role === 'admin';

  const [rules, setRules] = useState([]);
  const [showForm, setShowForm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [form, setForm] = useState({
    name: '', rule_type: 'price_threshold', market: 'NEM', region_or_zone: 'NSW1',
    channel_type: 'inapp', channel_target: '', operator: 'gt', threshold: '300',
  });

  const load = useCallback(async () => {
    if (!workspaceId) return;
    const res = await fetch(`${API_BASE}/alerts/rules?workspace_id=${workspaceId}`);
    if (res.ok) setRules((await res.json()).items || []);
  }, [workspaceId]);

  useEffect(() => { load().catch(() => {}); }, [load]);

  const createRule = async (e) => {
    e.preventDefault();
    setBusy(true); setError('');
    try {
      const config = form.rule_type === 'price_threshold'
        ? { operator: form.operator, threshold: Number(form.threshold) }
        : form.rule_type === 'data_freshness'
          ? { threshold_minutes: Number(form.threshold) }
          : { threshold_score: Number(form.threshold) };
      // 鉴权版创建端点（/api/v1，审计修复：旧无鉴权端点可跨租户注入）
      const token = await getToken();
      const res = await fetch(`${API_BASE}/v1/alerts/rules`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
          name: form.name, rule_type: form.rule_type, market: form.market,
          region_or_zone: form.region_or_zone || null, config,
          channel_type: form.channel_type, channel_target: form.channel_target,
          workspace_id: workspaceId,
        }),
      });
      if (!res.ok) { setError((await res.json().catch(() => ({}))).detail || `Failed (${res.status})`); return; }
      setShowForm(false);
      setForm((f) => ({ ...f, name: '', channel_target: '' }));
      await load();
    } catch {
      setError(zh ? '网络错误，请稍后重试' : 'Network error, please retry');
    } finally {
      setBusy(false);
    }
  };

  const toggleRule = async (rule) => {
    const token = await getToken();
    const res = await fetch(`${API_BASE}/v1/alerts/rules/${rule.rule_id}/toggle`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
      body: JSON.stringify({ workspace_id: workspaceId, enabled: !rule.enabled }),
    });
    if (res.ok) await load();
  };

  const inputCls = 'w-full rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-xs text-[var(--color-text)]';

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 className="text-sm font-semibold text-[var(--color-text)]">{zh ? '告警规则' : 'Alert rules'}</h2>
        {canManage && (
          <button
            type="button"
            onClick={() => setShowForm((v) => !v)}
            className="rounded-lg bg-[var(--color-primary)] px-3 py-1.5 text-xs font-semibold text-white"
          >
            {showForm ? (zh ? '取消' : 'Cancel') : (zh ? '新建规则' : 'New rule')}
          </button>
        )}
      </div>

      {showForm && canManage && (
        <form onSubmit={createRule} className="grid grid-cols-1 gap-3 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 md:grid-cols-2">
          <label className="text-xs text-[var(--color-muted)]">
            {zh ? '规则名称' : 'Name'}
            <input required value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className={`mt-1 ${inputCls}`} />
          </label>
          <label className="text-xs text-[var(--color-muted)]">
            {zh ? '规则类型' : 'Rule type'}
            <select value={form.rule_type} onChange={(e) => setForm({ ...form, rule_type: e.target.value })} className={`mt-1 ${inputCls}`}>
              {RULE_TYPES.map((t) => <option key={t.id} value={t.id}>{zh ? t.zh : t.en}</option>)}
            </select>
          </label>
          <label className="text-xs text-[var(--color-muted)]">
            {zh ? '市场 / 区域' : 'Market / region'}
            <div className="mt-1 flex gap-2">
              <select value={form.market} onChange={(e) => setForm({ ...form, market: e.target.value })} className={inputCls}>
                <option value="NEM">NEM</option>
                <option value="WEM">WEM</option>
              </select>
              <input value={form.region_or_zone} onChange={(e) => setForm({ ...form, region_or_zone: e.target.value })} placeholder="NSW1" className={inputCls} />
            </div>
          </label>
          {form.rule_type === 'price_threshold' && (
            <label className="text-xs text-[var(--color-muted)]">
              {zh ? '比较 / 阈值 ($/MWh)' : 'Operator / threshold ($/MWh)'}
              <div className="mt-1 flex gap-2">
                <select value={form.operator} onChange={(e) => setForm({ ...form, operator: e.target.value })} className={inputCls}>
                  <option value="gt">&gt;</option>
                  <option value="lt">&lt;</option>
                </select>
                <input type="number" value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} className={inputCls} />
              </div>
            </label>
          )}
          {form.rule_type !== 'price_threshold' && (
            <label className="text-xs text-[var(--color-muted)]">
              {form.rule_type === 'data_freshness' ? (zh ? '阈值（分钟）' : 'Threshold (minutes)') : (zh ? '阈值（分数）' : 'Threshold (score)')}
              <input type="number" value={form.threshold} onChange={(e) => setForm({ ...form, threshold: e.target.value })} className={`mt-1 ${inputCls}`} />
            </label>
          )}
          <label className="text-xs text-[var(--color-muted)]">
            {zh ? '投递渠道' : 'Channel'}
            <select value={form.channel_type} onChange={(e) => setForm({ ...form, channel_type: e.target.value })} className={`mt-1 ${inputCls}`}>
              {CHANNEL_TYPES.map((c) => <option key={c.id} value={c.id}>{zh ? c.zh : c.en}</option>)}
            </select>
          </label>
          <label className="text-xs text-[var(--color-muted)]">
            {form.channel_type === 'email' ? (zh ? '收件邮箱' : 'Recipient email')
              : form.channel_type === 'webhook' ? 'Webhook URL'
              : (zh ? '目标（站内可留空）' : 'Target (optional for in-app)')}
            <input
              required={form.channel_type !== 'inapp'}
              value={form.channel_target}
              onChange={(e) => setForm({ ...form, channel_target: e.target.value })}
              placeholder={form.channel_type === 'inapp' ? (zh ? '工作空间全员' : 'All workspace members') : ''}
              className={`mt-1 ${inputCls}`}
            />
          </label>
          <div className="flex items-end gap-2 md:col-span-2">
            <button type="submit" disabled={busy} className="rounded-lg bg-[var(--color-primary)] px-4 py-2 text-xs font-semibold text-white disabled:opacity-50">
              {busy ? (zh ? '提交中…' : 'Saving…') : (zh ? '创建' : 'Create')}
            </button>
            {error && <span className="text-xs text-[var(--color-status-error)]">{error}</span>}
          </div>
        </form>
      )}

      <div className="overflow-x-auto rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)]">
        <table className="w-full border-collapse text-xs">
          <thead>
            <tr className="border-b border-[var(--color-border)] text-left text-[var(--color-muted)]">
              <th className="px-3 py-2 font-semibold">{zh ? '名称' : 'Name'}</th>
              <th className="px-3 py-2 font-semibold">{zh ? '类型' : 'Type'}</th>
              <th className="px-3 py-2 font-semibold">{zh ? '渠道' : 'Channel'}</th>
              <th className="px-3 py-2 font-semibold">{zh ? '状态' : 'Status'}</th>
              {canManage && <th className="px-3 py-2" />}
            </tr>
          </thead>
          <tbody className="text-[var(--color-text)]">
            {rules.length === 0 && (
              <tr><td colSpan={5} className="px-3 py-6 text-center text-[var(--color-muted)]">{zh ? '暂无规则' : 'No rules yet'}</td></tr>
            )}
            {rules.map((r) => (
              <tr key={r.rule_id} className="border-b border-[var(--color-border)] last:border-b-0">
                <td className="px-3 py-2">{r.name}</td>
                <td className="px-3 py-2 font-mono text-[10px]">{r.rule_type}</td>
                <td className="px-3 py-2">{r.channel_type} <span className="text-[10px] text-[var(--color-muted)]">{r.channel_target}</span></td>
                <td className="px-3 py-2">
                  <span className={r.enabled ? 'text-[var(--color-status-success)]' : 'text-[var(--color-muted)]'}>
                    {r.enabled ? (zh ? '启用' : 'Enabled') : (zh ? '停用' : 'Disabled')}
                  </span>
                </td>
                {canManage && (
                  <td className="px-3 py-2 text-right">
                    <button type="button" onClick={() => toggleRule(r)} className="text-[10px] text-[var(--color-primary)] hover:underline">
                      {r.enabled ? (zh ? '停用' : 'Disable') : (zh ? '启用' : 'Enable')}
                    </button>
                  </td>
                )}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
