/**
 * FiveMinSettlementImpact — WEM 5 分钟结算影响分析
 *
 * 评估 5 分钟结算对储能收入的影响，支持模拟/实际数据模式。
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5
 */

import { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '5 分钟结算影响分析',
    subtitle: '评估 WEM 5 分钟结算对储能收入的影响',
    volatilityChange: '波动性变化',
    revenueChange: '收入变化',
    dataMode: '数据模式',
    simulated: '模拟数据',
    actual: '实际数据',
    comparison: '30min vs 5min 对比',
    vol30min: '30min 波动率',
    vol5min: '5min 波动率',
    spreadDist: '价差分布对比',
    spikeCapture: '极端事件捕获率',
    thirtyMin: '30分钟结算',
    fiveMin: '5分钟结算',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    metric: '指标',
  },
  en: {
    title: '5-Minute Settlement Impact',
    subtitle: 'Impact assessment of WEM 5-minute settlement on BESS revenue',
    volatilityChange: 'Volatility Change',
    revenueChange: 'Revenue Change',
    dataMode: 'Data Mode',
    simulated: 'Simulated',
    actual: 'Actual',
    comparison: '30min vs 5min Comparison',
    vol30min: '30min Volatility',
    vol5min: '5min Volatility',
    spreadDist: 'Spread Distribution',
    spikeCapture: 'Spike Capture Rate',
    thirtyMin: '30-min Settlement',
    fiveMin: '5-min Settlement',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    metric: 'Metric',
  },
};

export default function FiveMinSettlementImpact({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const year = filters.year;

  useEffect(() => {
    if (!year) return;
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ year: String(year), power_mw: '100', duration_hours: '4' });
    fetchJson(`${API_BASE}/v1/wem/five-min-settlement?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [year]);

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

  const modeLabel = data.data_mode === 'actual' ? t.actual : t.simulated;
  const volChange = data.volatility_change_pct || 0;
  const revChange = data.revenue_change_pct || 0;

  // Build comparison data for side-by-side chart
  const comparisonData = [];
  if (data.spread_distribution_comparison) {
    const spread = data.spread_distribution_comparison;
    Object.keys(spread.thirty_min || spread['30min'] || {}).forEach((key) => {
      comparisonData.push({
        metric: key,
        thirty_min: (spread.thirty_min || spread['30min'])?.[key] || 0,
        five_min: (spread.five_min || spread['5min'])?.[key] || 0,
      });
    });
  }

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Data mode badge */}
      <div className="mb-4">
        <span className={`inline-block px-3 py-1 text-xs rounded-full border ${data.data_mode === 'actual' ? 'border-green-500 text-green-700 bg-green-50' : 'border-amber-400 text-amber-700 bg-amber-50'}`}>
          {t.dataMode}: {modeLabel}
        </span>
      </div>

      {/* Key metrics */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard label={t.volatilityChange} value={`${volChange > 0 ? '+' : ''}${volChange.toFixed(1)}%`} />
        <StatCard label={t.revenueChange} value={`${revChange > 0 ? '+' : ''}${revChange.toFixed(1)}%`} accent={revChange > 0} />
        <StatCard label={t.vol30min} value={`$${(data.volatility_30min || 0).toFixed(1)}`} />
        <StatCard label={t.vol5min} value={`$${(data.volatility_5min || 0).toFixed(1)}`} />
      </div>

      {/* Side-by-side comparison chart */}
      {comparisonData.length > 0 && (
        <div>
          <h4 className="text-sm font-serif font-bold mb-2">{t.comparison}</h4>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={comparisonData}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="metric" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="thirty_min" name={t.thirtyMin} fill="#94a3b8" />
              <Bar dataKey="five_min" name={t.fiveMin} fill="#6366f1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}

function StatCard({ label, value, accent = false }) {
  return (
    <div className={`border p-3 rounded ${accent ? 'border-green-500 bg-green-50' : 'border-[var(--color-border)]'}`}>
      <div className="text-xs tracking-widest uppercase mb-1 text-[var(--color-muted)]">{label}</div>
      <div className="text-lg font-mono font-bold">{value}</div>
    </div>
  );
}
