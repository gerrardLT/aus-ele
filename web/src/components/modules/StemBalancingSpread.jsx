/**
 * StemBalancingSpread — WEM STEM/Balancing 价差分析
 *
 * 分析 STEM 和 Balancing 市场价差套利机会。
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
 */

import { useEffect, useState } from 'react';
import {
  Area, AreaChart, Bar, BarChart, CartesianGrid,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';
import NarrativeTooltip from './NarrativeTooltip';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: 'STEM/Balancing 价差分析',
    subtitle: 'WEM 短期能量市场价差套利机会评估',
    dataWindow: '数据窗口',
    meanSpread: '均值价差',
    medianSpread: '中位数价差',
    p90Spread: 'P90 价差',
    theoreticalRev: '理论套利收入',
    hourlyPattern: '时段价差分布',
    cumulativeRev: '累计套利收入趋势',
    dataUnavailable: '数据不可用',
    dataUnavailableDesc: 'STEM 和 Balancing 市场数据当前不可用',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    hour: '时段',
    spread: '价差 ($/MWh)',
    cumulative: '累计收入 ($)',
  },
  en: {
    title: 'STEM/Balancing Spread',
    subtitle: 'WEM short-term energy market spread arbitrage assessment',
    dataWindow: 'Data window',
    meanSpread: 'Mean Spread',
    medianSpread: 'Median Spread',
    p90Spread: 'P90 Spread',
    theoreticalRev: 'Theoretical Revenue',
    hourlyPattern: 'Hourly Spread Pattern',
    cumulativeRev: 'Cumulative Revenue Trend',
    dataUnavailable: 'Data Unavailable',
    dataUnavailableDesc: 'STEM or Balancing market data is currently unavailable',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    hour: 'Hour',
    spread: 'Spread ($/MWh)',
    cumulative: 'Cumulative ($)',
  },
};

export default function StemBalancingSpread({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [unavailable, setUnavailable] = useState(false);

  const year = filters.year;

  useEffect(() => {
    setLoading(true);
    setError(false);
    setUnavailable(false);
    const startDate = `${year}-01-01`;
    const endDate = `${year}-12-31`;
    const params = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
      power_mw: '100',
      duration_hours: '4',
    });
    fetchJson(`${API_BASE}/v1/wem/stem-balancing?${params}`)
      .then((res) => {
        if (res.error_code || res.data_unavailable) {
          setUnavailable(true);
        } else {
          setData(res);
        }
        setLoading(false);
      })
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
  if (unavailable) {
    return (
      <div className="mt-3">
        <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
        <div className="h-32 flex flex-col items-center justify-center border border-[var(--color-border)] rounded p-6 gap-2">
          <span className="text-lg font-serif text-[var(--color-muted)]">{t.dataUnavailable}</span>
          <span className="text-xs text-[var(--color-muted)]">{t.dataUnavailableDesc}</span>
        </div>
      </div>
    );
  }
  if (!data) return null;

  const stats = data.spread_stats || {};
  const hourly = data.hourly_pattern || [];
  const dw = data.data_window;
  const dr = data.date_range || {};

  // Build subtitle: show actual date range and data window
  const rangeLabel = `${dr.start || ''} ~ ${dr.end || ''}`;
  const windowLabel = dw
    ? (lang === 'zh'
        ? `${t.dataWindow}: ${dw.start} ~ ${dw.end} (${dw.days}${lang === 'zh' ? '天' : 'd'})`
        : `${t.dataWindow}: ${dw.start} ~ ${dw.end} (${dw.days}d)`)
    : null;

  // Format spread: use 2 decimal places to capture small but meaningful differences
  const fmtSpread = (v) => {
    const n = v || 0;
    return `$${n.toFixed(2)}`;
  };

  // Format revenue: use $ not k for small values
  const fmtRevenue = (v) => {
    const n = v || 0;
    if (Math.abs(n) >= 1000) return `$${(n / 1000).toFixed(1)}k`;
    return `$${n.toFixed(0)}`;
  };

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-1">{t.subtitle}</p>
      <p className="text-[10px] text-[var(--color-muted)] font-mono mb-4">
        {rangeLabel}
        {windowLabel && <span className="ml-3 opacity-70">{windowLabel}</span>}
      </p>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard label={t.meanSpread} value={<NarrativeTooltip module="forward_price" lang={lang}>{fmtSpread(stats.mean)}</NarrativeTooltip>} sub="/MWh" />
        <StatCard label={t.medianSpread} value={fmtSpread(stats.median)} sub="/MWh" />
        <StatCard label={t.p90Spread} value={fmtSpread(stats.p90)} sub="/MWh" />
        <StatCard label={t.theoreticalRev} value={fmtRevenue(data.theoretical_revenue)} accent />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {hourly.length > 0 && (
          <div>
            <h4 className="text-sm font-serif font-bold mb-2">{t.hourlyPattern}</h4>
            <ResponsiveContainer width="100%" height={200}>
              <BarChart data={hourly}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="hour" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Bar dataKey="avg_spread" fill="#8b5cf6" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}

        {data.cumulative_trend && data.cumulative_trend.length > 0 && (
          <div>
            <h4 className="text-sm font-serif font-bold mb-2">{t.cumulativeRev}</h4>
            <ResponsiveContainer width="100%" height={200}>
              <AreaChart data={data.cumulative_trend}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Area type="monotone" dataKey="cumulative_revenue" stroke="#10b981" fill="#10b981" fillOpacity={0.15} />
              </AreaChart>
            </ResponsiveContainer>
          </div>
        )}
      </div>
    </div>
  );
}

function StatCard({ label, value, sub, accent = false }) {
  return (
    <div className={`border p-3 rounded ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]' : 'border-[var(--color-border)]'}`}>
      <div className={`text-xs tracking-widest uppercase mb-1 ${accent ? 'opacity-70' : 'text-[var(--color-muted)]'}`}>{label}</div>
      <div className="text-lg font-mono font-bold">
        {value}
        {sub && <span className="text-xs font-normal ml-1 opacity-60">{sub}</span>}
      </div>
    </div>
  );
}
