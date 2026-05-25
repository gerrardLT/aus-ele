/**
 * SaturationTracker — BESS 容量饱和度追踪
 *
 * 追踪各区域已注册和管道中的 BESS 容量，评估饱和风险。
 * 支持 NEM 和 WEM 两种市场模式。
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 4.5, 10.1, 10.2, 10.3, 10.4, 10.5
 */

import { useEffect, useState } from 'react';
import {
  Area, AreaChart, CartesianGrid, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: 'BESS 容量饱和度追踪',
    subtitle: '各区域已注册和管道中的储能容量及饱和风险评估',
    region: '区域',
    registered: '已注册 (MW)',
    pipeline: '管道 (MW)',
    saturation: '饱和度',
    pipelineRatio: '管道/注册比',
    dilutionCurve: '收入稀释曲线',
    timeline: '容量增长时间线',
    lastUpdated: '数据更新时间',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    cumulativeMw: '累计容量 (MW)',
    date: '日期',
    dilution: '收入稀释 (%)',
    capacityMw: '容量 (MW)',
  },
  en: {
    title: 'BESS Saturation Tracker',
    subtitle: 'Registered and pipeline BESS capacity with saturation risk assessment',
    region: 'Region',
    registered: 'Registered (MW)',
    pipeline: 'Pipeline (MW)',
    saturation: 'Saturation',
    pipelineRatio: 'Pipeline/Reg.',
    dilutionCurve: 'Revenue Dilution Curve',
    timeline: 'Capacity Growth Timeline',
    lastUpdated: 'Data updated',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    cumulativeMw: 'Cumulative (MW)',
    date: 'Date',
    dilution: 'Revenue Dilution (%)',
    capacityMw: 'Capacity (MW)',
  },
};

export default function SaturationTracker({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const market = filters.market;
  const region = filters.region;

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ market });
    if (region) params.set('region', region);
    fetchJson(`${API_BASE}/v1/saturation?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [market, region]);

  if (loading) {
    return <div className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">{t.loading}</div>;
  }
  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button onClick={() => setError(false)} className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]">{t.retry}</button>
      </div>
    );
  }
  if (!data) return null;

  const regions = data.regions || [];
  const timeline = data.timeline || [];

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>
      {data.last_updated && (
        <p className="text-xs text-[var(--color-muted)] mb-4">{t.lastUpdated}: {data.last_updated}</p>
      )}

      {/* Region capacity table */}
      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm font-sans border-collapse">
          <thead>
            <tr className="border-b-2 border-[var(--color-text)]">
              <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.region}</th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.registered}</th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.pipeline}</th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.saturation}</th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.pipelineRatio}</th>
            </tr>
          </thead>
          <tbody>
            {regions.map((r) => (
              <tr key={r.region} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                <td className="py-2 px-2 font-mono text-xs">{r.region}</td>
                <td className="text-right py-2 px-2 font-mono text-xs">{r.registered_mw?.toLocaleString()}</td>
                <td className="text-right py-2 px-2 font-mono text-xs">{r.pipeline_mw?.toLocaleString()}</td>
                <td className="text-right py-2 px-2 font-mono text-xs font-bold">{((r.saturation_ratio || 0) * 100).toFixed(1)}%</td>
                <td className="text-right py-2 px-2 font-mono text-xs">{((r.pipeline_ratio || 0) * 100).toFixed(0)}%</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Dilution curve + Timeline */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {data.dilution_curve && (
          <div>
            <h4 className="text-sm font-serif font-bold mb-2">{t.dilutionCurve}</h4>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={data.dilution_curve}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="capacity_mw" tick={{ fontSize: 10 }} label={{ value: t.capacityMw, fontSize: 10, position: 'bottom' }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Line type="monotone" dataKey="dilution_pct" stroke="#ef4444" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}
        {timeline.length > 0 && (
          <div>
            <h4 className="text-sm font-serif font-bold mb-2">{t.timeline}</h4>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={timeline}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Area type="stepAfter" dataKey="cumulative_mw" stroke="#6366f1" fill="#6366f1" fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}
