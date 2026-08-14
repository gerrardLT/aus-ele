// web/src/components/SavedViewsBar.jsx
// 保存视图（P2-6 个性化，2026-08-14）：保存当前筛选快照 + 一键恢复 + 删除。
// 登录用户持久化到后端 user_preference（saved_views）；匿名用户回落 localStorage。

import { useCallback, useEffect, useState } from 'react';
import { useFilters } from '../contexts/FilterContext';
import { readAuth, getValidAccessToken, tryRefreshToken } from '../lib/authStore.js';
import { getApiBase } from '../lib/apiBase.js';

const API_BASE = getApiBase();
const LOCAL_KEY = 'aus_saved_views_v1';
const SNAPSHOT_KEYS = ['region', 'year', 'dayType', 'quarter'];

function readLocalViews() {
  try { return JSON.parse(globalThis.localStorage?.getItem(LOCAL_KEY) || '[]'); } catch { return []; }
}

export default function SavedViewsBar({ market = 'NEM', lang = 'zh' }) {
  const zh = lang === 'zh';
  const { filters, setFilter } = useFilters();
  const auth = readAuth();
  const workspaceId = auth?.workspaceId;
  const principalId = auth?.principal?.principal_id;

  const [views, setViews] = useState([]); // 全部市场的视图（持久化单元）
  const [name, setName] = useState('');
  const [saving, setSaving] = useState(false);

  const marketViews = views.filter((v) => v.market === market);

  const loadViews = useCallback(async () => {
    if (workspaceId && principalId) {
      try {
        const token = getValidAccessToken() || (await tryRefreshToken());
        if (token) {
          const res = await fetch(`${API_BASE}/v1/preferences/saved_views?workspace_id=${workspaceId}`, {
            headers: { Authorization: `Bearer ${token}` },
          });
          if (res.ok) {
            const body = await res.json();
            setViews(body.value?.views || []);
            return;
          }
        }
      } catch { /* 回落本地 */ }
    }
    setViews(readLocalViews());
  }, [workspaceId, principalId]);

  useEffect(() => { loadViews(); }, [loadViews]);

  const persist = async (nextAll) => {
    setViews(nextAll);
    if (workspaceId && principalId) {
      try {
        const token = getValidAccessToken() || (await tryRefreshToken());
        if (token) {
          const res = await fetch(`${API_BASE}/v1/preferences/saved_views`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
            body: JSON.stringify({ workspace_id: workspaceId, value: { views: nextAll } }),
          });
          if (res.ok) return;
          // 后端失败回落本地，避免视图静默丢失（审计修复 2026-08-14）
        }
      } catch { /* 回落本地 */ }
    }
    try { globalThis.localStorage?.setItem(LOCAL_KEY, JSON.stringify(nextAll)); } catch { /* ignore */ }
  };

  const saveView = async () => {
    const viewName = name.trim() || `${filters.region || ''} ${filters.year || ''}`.trim();
    if (!viewName || saving) return;
    setSaving(true);
    const snapshot = {};
    SNAPSHOT_KEYS.forEach((k) => { if (filters[k] != null && filters[k] !== '') snapshot[k] = filters[k]; });
    const next = [
      ...views.filter((v) => !(v.market === market && v.name === viewName)),
      { name: viewName, market, filters: snapshot, saved_at: Date.now() },
    ];
    await persist(next);
    setName('');
    setSaving(false);
  };

  const applyView = (view) => {
    SNAPSHOT_KEYS.forEach((k) => {
      if (view.filters[k] != null) setFilter(k, view.filters[k]);
    });
  };

  const removeView = async (viewName) => {
    await persist(views.filter((v) => !(v.market === market && v.name === viewName)));
  };

  return (
    <div className="flex items-center gap-1.5">
      {marketViews.length > 0 && (
        <select
          value=""
          onChange={(e) => {
            const v = marketViews.find((x) => x.name === e.target.value);
            if (v) applyView(v);
          }}
          className="max-w-32 rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-1.5 py-0.5 text-[10px] text-[var(--color-text)]"
          title={zh ? '恢复已保存视图' : 'Restore saved view'}
        >
          <option value="" disabled>{zh ? '视图…' : 'Views…'}</option>
          {marketViews.map((v) => <option key={v.name} value={v.name}>{v.name}</option>)}
        </select>
      )}
      <input
        value={name}
        onChange={(e) => setName(e.target.value)}
        placeholder={zh ? '视图名' : 'View name'}
        className="w-20 rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-1.5 py-0.5 text-[10px] text-[var(--color-text)]"
      />
      <button
        type="button"
        onClick={saveView}
        disabled={saving}
        className="rounded bg-[var(--color-border)] px-1.5 py-0.5 text-[10px] font-medium text-[var(--color-text)] hover:opacity-80 disabled:opacity-50"
        title={zh ? '保存当前筛选为视图' : 'Save current filters as view'}
      >
        {zh ? '保存视图' : 'Save'}
      </button>
      {marketViews.length > 0 && (
        <button
          type="button"
          onClick={() => removeView(marketViews[marketViews.length - 1].name)}
          className="rounded px-1 py-0.5 text-[10px] text-[var(--color-status-error)] hover:opacity-80"
          title={zh ? '删除最近保存的视图' : 'Remove last saved view'}
        >
          ✕
        </button>
      )}
    </div>
  );
}
