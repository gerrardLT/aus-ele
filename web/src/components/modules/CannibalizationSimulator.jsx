/**
 * CannibalizationSimulator — 收入蚕食模拟器
 *
 * 基于幂律稀释曲线模拟容量增长对单位收入的蚕食效应。
 * 显示稀释曲线图、年度预测时间线、真实市场数据标注和警告指示器。
 * Requirements: 1.1, 1.2, 1.4, 1.5, 1.6, 1.8, 6.1
 */

import { useEffect, useState } from 'react';
import {
  CartesianGrid, Line, LineChart,
  ReferenceDot, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '收入蚕食模拟器',
    subtitle: '基于管道容量数据模拟前瞻性收入稀释效应',
    dilutionCurve: '稀释曲线',
    capacityMw: '容量 (MW)',
    revenuePerMw: '收入 ($/MW/年)',
    yearlyProjections: '年度预测时间线',
    year: '年份',
    projectedCapacity: '预计容量 (MW)',
    projectedRevenue: '预计收入 ($/MW/年)',
    dilution: '稀释率',
    newProjects: '新增项目',
    marketExamples: '真实市场数据',
    warning: '⚠️ 稀释超过50%',
    conclusion: '结论',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    actual: '实际',
    projected: '预测',
  },
  en: {
    title: 'Revenue Cannibalization Simulator',
    subtitle: 'Forward-looking revenue dilution simulation based on pipeline capacity',
    dilutionCurve: 'Dilution Curve',
    capacityMw: 'Capacity (MW)',
    revenuePerMw: 'Revenue ($/MW/yr)',
    yearlyProjections: 'Yearly Projection Timeline',
    year: 'Year',
    projectedCapacity: 'Projected Capacity (MW)',
    projectedRevenue: 'Projected Revenue ($/MW/yr)',
    dilution: 'Dilution',
    newProjects: 'New Projects',
    marketExamples: 'Real Market Data',
    warning: '⚠️ Dilution exceeds 50%',
    conclusion: 'Conclusion',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    actual: 'Actual',
    projected: 'Projected',
  },
};

export default function CannibalizationSimulator({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const market = filters.market;
  const region = filters.region;

  // Configurable parameters with defaults
  const alpha = config?.alpha ?? 0.6;
  const projectionYears = config?.projectionYears ?? 3;

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({
      market,
      region,
      alpha: String(alpha),
      projection_years: String(projectionYears),
    });
    fetchJson(`${API_BASE}/v1/outlook/cannibalization?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [market, region, alpha, projectionYears]);

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

  const dilutionCurve = data.dilution_curve || [];
  const yearlyProjections = data.yearly_projections || [];
  const marketExamples = data.market_examples || [];
  const warningTriggered = data.warning_triggered || false;

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Warning indicator when dilution > 50% */}
      {warningTriggered && (
        <div className="mb-4 px-4 py-2 rounded border border-orange-400 bg-orange-50 dark:bg-orange-950/20 text-orange-700 dark:text-orange-300 text-sm font-sans">
          {t.warning}
        </div>
      )}

      {/* Dilution Curve Chart */}
      {dilutionCurve.length > 0 && (
        <div className="mb-6">
          <h4 className="text-sm font-serif font-bold mb-2">{t.dilutionCurve}</h4>
          <ResponsiveContainer width="100%" height={240}>
            <LineChart data={dilutionCurve} margin={{ top: 5, right: 20, bottom: 20, left: 10 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="capacity_mw"
                tick={{ fontSize: 10 }}
                label={{ value: t.capacityMw, fontSize: 10, position: 'bottom', offset: 5 }}
              />
              <YAxis
                tick={{ fontSize: 10 }}
                label={{ value: t.revenuePerMw, fontSize: 10, angle: -90, position: 'insideLeft' }}
              />
              <Tooltip
                formatter={(value) => [`$${Number(value).toLocaleString()}`, t.revenuePerMw]}
                labelFormatter={(label) => `${Number(label).toLocaleString()} MW`}
              />
              <Line
                type="monotone"
                dataKey="revenue_per_mw"
                stroke="#6366f1"
                strokeWidth={2}
                dot={false}
              />
              {/* Annotate real market data points */}
              {marketExamples.map((ex, i) => (
                <ReferenceDot
                  key={i}
                  x={ex.actual_value ? undefined : undefined}
                  y={ex.actual_value}
                  r={0}
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
          {/* Market examples annotation below chart */}
          {marketExamples.length > 0 && (
            <div className="mt-2">
              <h5 className="text-xs font-sans font-bold text-[var(--color-muted)] uppercase tracking-widest mb-1">{t.marketExamples}</h5>
              {marketExamples.map((ex, i) => (
                <p key={i} className="text-xs text-[var(--color-muted)] font-sans leading-relaxed">
                  <span className="inline-block px-1.5 py-0.5 rounded text-[10px] font-mono mr-1 bg-[var(--color-surface-hover)]">
                    {ex.label === 'actual' ? t.actual : t.projected}
                  </span>
                  {ex.description} ({ex.region}, {ex.data_year})
                </p>
              ))}
            </div>
          )}
        </div>
      )}

      {/* Yearly Projections Table */}
      {yearlyProjections.length > 0 && (
        <div className="mb-6">
          <h4 className="text-sm font-serif font-bold mb-2">{t.yearlyProjections}</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans border-collapse">
              <thead>
                <tr className="border-b-2 border-[var(--color-text)]">
                  <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.year}</th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.projectedCapacity}</th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.projectedRevenue}</th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.dilution}</th>
                  <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.newProjects}</th>
                </tr>
              </thead>
              <tbody>
                {yearlyProjections.map((row) => (
                  <tr key={row.year} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                    <td className="py-2 px-2 font-mono text-xs">{row.year}</td>
                    <td className="text-right py-2 px-2 font-mono text-xs">{row.projected_capacity_mw?.toLocaleString()} MW</td>
                    <td className="text-right py-2 px-2 font-mono text-xs">${row.projected_revenue_per_mw?.toLocaleString()}</td>
                    <td className={`text-right py-2 px-2 font-mono text-xs font-bold ${row.dilution_pct > 50 ? 'text-orange-500' : ''}`}>
                      {row.dilution_pct?.toFixed(1)}%
                    </td>
                    <td className="py-2 px-2 text-xs text-[var(--color-muted)]">
                      {(row.new_projects || []).join(', ') || '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Conclusion summary */}
      {data.conclusion && (
        <div className="mt-4 pt-4 border-t border-[var(--color-border)]">
          <h4 className="text-sm font-serif font-bold mb-1">{t.conclusion}</h4>
          <p className="text-sm text-[var(--color-muted)] font-sans leading-relaxed">{data.conclusion}</p>
        </div>
      )}
    </div>
  );
}
