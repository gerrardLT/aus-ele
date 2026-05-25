/**
 * SpikeProfitAnalysis — NEM 极端价格事件利润分析
 *
 * 分析 >$3000/MWh 价格事件对 BESS 年收入的贡献。
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.5
 */

import { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '极端价格事件利润分析',
    subtitle: '分析 >$3000/MWh 价格事件对年收入的贡献',
    spikeCount: '事件数量',
    totalHours: '总持续时间',
    maxRevenue: '单次最大收入',
    revenuePct: '收入贡献占比',
    monthlyDist: '月度分布',
    hourlyDist: '时段分布',
    durationDist: '持续时长分布',
    yearlyTrend: '年际趋势对比',
    noEvents: '当前筛选条件下无极端价格事件',
    historicalRef: '该区域历史事件频率参考',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    events: '次',
    hours: '小时',
    month: '月份',
    hour: '时段',
    minutes: '分钟',
    count: '次数',
    revenue: '收入 ($)',
    year: '年份',
  },
  en: {
    title: 'Spike Profit Analysis',
    subtitle: 'Revenue contribution from extreme price events (>$3000/MWh)',
    spikeCount: 'Spike Count',
    totalHours: 'Total Duration',
    maxRevenue: 'Max Single Event',
    revenuePct: 'Revenue Share',
    monthlyDist: 'Monthly Distribution',
    hourlyDist: 'Hourly Distribution',
    durationDist: 'Duration Distribution',
    yearlyTrend: 'Yearly Trend Comparison',
    noEvents: 'No extreme price events in selected period',
    historicalRef: 'Historical event frequency for reference',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    events: 'events',
    hours: 'hrs',
    month: 'Month',
    hour: 'Hour',
    minutes: 'min',
    count: 'Count',
    revenue: 'Revenue ($)',
    year: 'Year',
  },
};

export default function SpikeProfitAnalysis({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const region = filters.region;
  const year = filters.year;

  useEffect(() => {
    if (!region || !year) return;
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ region, year: String(year), threshold: '3000' });
    fetchJson(`${API_BASE}/v1/nem/spike-profit?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [region, year]);

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

  const hasEvents = data && data.spike_count > 0;

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-6">{t.subtitle}</p>

      {!hasEvents && data ? (
        <div className="h-32 flex flex-col items-center justify-center text-[var(--color-muted)] gap-2">
          <span className="font-serif">{t.noEvents}</span>
          {data.yearly_trend?.length > 0 && (
            <span className="text-xs">{t.historicalRef}: {data.yearly_trend.map(y => `${y.year}(${y.count})`).join(', ')}</span>
          )}
        </div>
      ) : data ? (
        <>
          {/* Stats cards */}
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
            <StatCard label={t.spikeCount} value={`${data.spike_count} ${t.events}`} />
            <StatCard label={t.totalHours} value={`${data.total_spike_hours?.toFixed(1)} ${t.hours}`} />
            <StatCard label={t.maxRevenue} value={`$${(data.max_single_event_revenue || 0).toLocaleString()}`} />
            <StatCard label={t.revenuePct} value={`${(data.spike_revenue_pct || 0).toFixed(1)}%`} accent />
          </div>

          {/* Monthly + Hourly charts */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
            <ChartSection title={t.monthlyDist}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.monthly_distribution || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#f59e0b" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartSection>
            <ChartSection title={t.hourlyDist}>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart data={data.hourly_distribution || []}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="hour" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Bar dataKey="count" fill="#ef4444" radius={[3, 3, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </ChartSection>
          </div>

          {/* Yearly trend */}
          {data.yearly_trend?.length > 0 && (
            <ChartSection title={t.yearlyTrend}>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={data.yearly_trend}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="year" tick={{ fontSize: 10 }} />
                  <YAxis yAxisId="left" tick={{ fontSize: 10 }} />
                  <YAxis yAxisId="right" orientation="right" tick={{ fontSize: 10 }} />
                  <Tooltip />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line yAxisId="left" type="monotone" dataKey="count" stroke="#f59e0b" name={t.count} strokeWidth={2} />
                  <Line yAxisId="right" type="monotone" dataKey="revenue" stroke="#10b981" name={t.revenue} strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </ChartSection>
          )}
        </>
      ) : null}
    </div>
  );
}

function StatCard({ label, value, accent = false }) {
  return (
    <div className={`border p-3 rounded ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]' : 'border-[var(--color-border)]'}`}>
      <div className={`text-xs tracking-widest uppercase mb-1 ${accent ? 'opacity-70' : 'text-[var(--color-muted)]'}`}>{label}</div>
      <div className="text-lg font-mono font-bold">{value}</div>
    </div>
  );
}

function ChartSection({ title, children }) {
  return (
    <div>
      <h4 className="text-sm font-serif font-bold mb-2">{title}</h4>
      {children}
    </div>
  );
}
