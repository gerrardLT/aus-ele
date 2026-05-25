/**
 * FcasCollapseForecaster — FCAS 崩塌预判器
 *
 * 基于供需比模型预测 FCAS 各服务类型的价格天花板。
 * 渲染 10 种 FCAS 服务汇总表格和历史收入轨迹折线图。
 * Requirements: 2.1, 2.4, 2.5, 2.6, 2.8, 6.2
 */

import { useEffect, useState } from 'react';
import {
  CartesianGrid, Line, LineChart,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: 'FCAS 崩塌预判器',
    subtitle: '基于供需比模型预测各 FCAS 服务类型的价格天花板',
    serviceName: '服务名称',
    supplyDemandRatio: '供需比',
    classification: '分类',
    priceCeiling: '价格天花板 ($/MW/hr)',
    healthy: '健康',
    at_risk: '风险',
    collapsed: '崩塌',
    historicalTrajectory: 'FCAS 历史收入轨迹',
    revenuePerMw: '收入 ($/MW/年)',
    year: '年份',
    totalCeiling: '总 FCAS 收入天花板',
    perMwYear: '/MW/年',
    conclusion: '结论',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
  },
  en: {
    title: 'FCAS Collapse Forecaster',
    subtitle: 'Supply-demand ratio model forecasting price ceilings for each FCAS service',
    serviceName: 'Service',
    supplyDemandRatio: 'S/D Ratio',
    classification: 'Status',
    priceCeiling: 'Price Ceiling ($/MW/hr)',
    healthy: 'Healthy',
    at_risk: 'At Risk',
    collapsed: 'Collapsed',
    historicalTrajectory: 'FCAS Historical Revenue Trajectory',
    revenuePerMw: 'Revenue ($/MW/yr)',
    year: 'Year',
    totalCeiling: 'Total FCAS Revenue Ceiling',
    perMwYear: '/MW/yr',
    conclusion: 'Conclusion',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
  },
};

const CLASSIFICATION_COLORS = {
  healthy: '#22c55e',
  at_risk: '#f97316',
  collapsed: '#ef4444',
};

export default function FcasCollapseForecaster({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const market = filters.market;
  const region = filters.region;
  const year = filters.year || new Date().getFullYear();

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ market, region, year: String(year) });
    fetchJson(`${API_BASE}/v1/outlook/fcas-collapse?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [market, region, year]);

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

  const services = data.services || [];
  const trajectory = data.historical_trajectory || [];
  const totalCeiling = data.total_fcas_ceiling_per_mw_year || 0;

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* FCAS Services Summary Table */}
      <div className="overflow-x-auto mb-6">
        <table className="w-full text-sm font-sans border-collapse">
          <thead>
            <tr className="border-b-2 border-[var(--color-text)]">
              <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.serviceName}</th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.supplyDemandRatio}</th>
              <th className="text-center py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.classification}</th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.priceCeiling}</th>
            </tr>
          </thead>
          <tbody>
            {services.map((s) => (
              <tr key={s.service_name} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                <td className="py-2 px-2 font-mono text-xs">{s.service_name}</td>
                <td className="text-right py-2 px-2 font-mono text-xs">{s.supply_demand_ratio?.toFixed(2)}</td>
                <td className="text-center py-2 px-2">
                  <span
                    className="inline-block px-2 py-0.5 rounded text-xs font-bold"
                    style={{ color: CLASSIFICATION_COLORS[s.classification] || '#888', borderColor: CLASSIFICATION_COLORS[s.classification] || '#888', border: '1px solid' }}
                  >
                    {t[s.classification] || s.classification}
                  </span>
                </td>
                <td className="text-right py-2 px-2 font-mono text-xs">${s.price_ceiling_per_mwh?.toFixed(4)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Total FCAS Ceiling */}
      <div className="mb-6 p-3 border border-[var(--color-border)] rounded">
        <span className="text-sm font-serif font-bold">{t.totalCeiling}: </span>
        <span className="font-mono text-lg font-bold">${totalCeiling.toLocaleString(undefined, { maximumFractionDigits: 0 })}</span>
        <span className="text-xs text-[var(--color-muted)]"> {t.perMwYear}</span>
      </div>

      {/* Historical Revenue Trajectory Chart */}
      {trajectory.length > 0 && (
        <div className="mb-6">
          <h4 className="text-sm font-serif font-bold mb-2">{t.historicalTrajectory}</h4>
          <ResponsiveContainer width="100%" height={220}>
            <LineChart data={trajectory}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="year" tick={{ fontSize: 10 }} label={{ value: t.year, fontSize: 10, position: 'bottom' }} />
              <YAxis tick={{ fontSize: 10 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
              <Tooltip formatter={(value) => [`$${value.toLocaleString()}`, t.revenuePerMw]} labelFormatter={(label) => `${t.year}: ${label}`} />
              <Line type="monotone" dataKey="total_fcas_revenue_per_mw" stroke="#ef4444" strokeWidth={2} dot={{ r: 4 }} name={t.revenuePerMw} />
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Conclusion */}
      {data.conclusion && (
        <div className="mt-4 p-3 bg-[var(--color-surface)] border border-[var(--color-border)] rounded">
          <h4 className="text-sm font-serif font-bold mb-1">{t.conclusion}</h4>
          <p className="text-xs font-sans text-[var(--color-muted)] leading-relaxed">{data.conclusion}</p>
        </div>
      )}
    </div>
  );
}
