/**
 * CapacityCreditsAnalysis — WEM 容量信用分析
 *
 * 分析 WEM 容量信用机制对 BESS 项目的收入贡献。
 * Requirements: 7.1, 7.2, 7.3, 7.4, 7.5
 */

import { useEffect, useState } from 'react';
import {
  CartesianGrid, Legend, Line, LineChart, Pie, PieChart,
  Cell, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const PIE_COLORS = ['#6366f1', '#f59e0b'];

const LABELS = {
  zh: {
    title: 'WEM 容量信用分析',
    subtitle: '容量信用机制对 BESS 项目的收入贡献评估',
    annualRevenue: '年度容量信用收入',
    eligibility: '资格系数',
    currentPrice: '当前信用价格',
    capacityShare: '容量收入占比',
    priceTrend: '历史容量信用价格趋势',
    revenueComparison: '容量 vs 能量收入对比',
    capacityRev: '容量信用收入',
    energyRev: '能量市场收入',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    year: '年份',
    pricePerMw: '$/MW/年',
  },
  en: {
    title: 'WEM Capacity Credits Analysis',
    subtitle: 'Capacity credit revenue contribution for BESS projects',
    annualRevenue: 'Annual CC Revenue',
    eligibility: 'Eligibility Coeff.',
    currentPrice: 'Current CC Price',
    capacityShare: 'CC Revenue Share',
    priceTrend: 'Historical Capacity Credit Price Trend',
    revenueComparison: 'Capacity vs Energy Revenue',
    capacityRev: 'Capacity Credits',
    energyRev: 'Energy Market',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    year: 'Year',
    pricePerMw: '$/MW/yr',
  },
};

export default function CapacityCreditsAnalysis({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const powerMw = 100;
  const durationHours = 4;

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ power_mw: String(powerMw), duration_hours: String(durationHours) });
    fetchJson(`${API_BASE}/v1/wem/capacity-credits?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [powerMw, durationHours]);

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

  const pieData = [
    { name: t.capacityRev, value: data.annual_capacity_revenue || 0 },
    { name: t.energyRev, value: data.energy_revenue_estimate || 0 },
  ];
  const historicalPrices = data.historical_prices || [];

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-6">{t.subtitle}</p>

      {/* Stats cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mb-6">
        <StatCard label={t.annualRevenue} value={`$${((data.annual_capacity_revenue || 0) / 1000).toFixed(0)}k`} accent />
        <StatCard label={t.eligibility} value={(data.eligibility_coefficient || 0).toFixed(2)} />
        <StatCard label={t.currentPrice} value={`$${(data.credit_price_current || 0).toLocaleString()}`} sub={t.pricePerMw} />
        <StatCard label={t.capacityShare} value={`${(data.capacity_revenue_share_pct || 0).toFixed(1)}%`} />
      </div>

      {/* Charts */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {historicalPrices.length > 0 && (
          <div>
            <h4 className="text-sm font-serif font-bold mb-2">{t.priceTrend}</h4>
            <ResponsiveContainer width="100%" height={200}>
              <LineChart data={historicalPrices}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="year" tick={{ fontSize: 10 }} />
                <YAxis tick={{ fontSize: 10 }} />
                <Tooltip />
                <Line type="monotone" dataKey="price_per_mw" stroke="#6366f1" strokeWidth={2} dot={{ r: 3 }} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        <div>
          <h4 className="text-sm font-serif font-bold mb-2">{t.revenueComparison}</h4>
          <ResponsiveContainer width="100%" height={200}>
            <PieChart>
              <Pie data={pieData} dataKey="value" nameKey="name" cx="50%" cy="50%" outerRadius={70} label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`} labelLine={false}>
                {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i]} />)}
              </Pie>
              <Tooltip formatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
              <Legend wrapperStyle={{ fontSize: 11 }} />
            </PieChart>
          </ResponsiveContainer>
        </div>
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
