/**
 * FuelSensitivityTable — 燃料敏感性分析展示
 *
 * 展示天然气价格变化对 BESS 收入的影响，显示 5 个情景：
 * -20%, -10%, base, +10%, +20% 气价变化对应的收入影响。
 * 调用 GET /api/v1/narrative/fuel-sensitivity/{region} 获取数据。
 *
 * Requirements: 13.4
 */

import { useEffect, useState, useCallback } from 'react';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '燃料成本敏感性分析',
    subtitle: '天然气价格变化对 BESS 收入的传导效应',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    noData: '暂无敏感性数据',
    gasChange: '气价变化',
    gasPrice: '气价 ($/GJ)',
    peakImpact: '峰值电价影响 ($/MWh)',
    revenueImpact: '收入影响 ($)',
    revenueChangePct: '收入变化 %',
    baseCase: '基准情景',
    sensitivityCoeff: '敏感性系数',
    sensitivityCoeffDesc: 'BESS 年收入变化% / 气价变化 10%',
    baseRevenue: '基准年收入',
  },
  en: {
    title: 'Fuel Cost Sensitivity',
    subtitle: 'Gas price pass-through impact on BESS revenue',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    noData: 'No sensitivity data available',
    gasChange: 'Gas Price Change',
    gasPrice: 'Gas Price ($/GJ)',
    peakImpact: 'Peak Price Impact ($/MWh)',
    revenueImpact: 'Revenue Impact ($)',
    revenueChangePct: 'Revenue Change %',
    baseCase: 'Base Case',
    sensitivityCoeff: 'Sensitivity Coefficient',
    sensitivityCoeffDesc: 'BESS annual revenue change % per 10% gas price change',
    baseRevenue: 'Base Annual Revenue',
  },
};

export default function FuelSensitivityTable({ config, lang = 'en', region }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const effectiveRegion = region || filters.region || config?.defaultRegion || 'NSW1';

  const fetchData = useCallback(() => {
    setLoading(true);
    setError(false);
    fetchJson(`${API_BASE}/v1/narrative/fuel-sensitivity/${effectiveRegion}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [effectiveRegion]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  if (loading && !data) {
    return (
      <div className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">
        {t.loading}
      </div>
    );
  }

  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button
          onClick={fetchData}
          className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]"
        >
          {t.retry}
        </button>
      </div>
    );
  }

  if (!data || !data.scenarios || data.scenarios.length === 0) {
    return (
      <div className="h-32 flex items-center justify-center text-[var(--color-muted)] text-sm">
        {t.noData}
      </div>
    );
  }

  const scenarios = data.scenarios || [];

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Summary Cards */}
      <div className="grid grid-cols-2 gap-3 mb-4">
        <div className="p-3 rounded border border-[var(--color-border)]">
          <p className="text-xs text-[var(--color-muted)]">{t.sensitivityCoeff}</p>
          <p className="text-lg font-mono font-bold">
            {data.sensitivity_coefficient != null
              ? `${data.sensitivity_coefficient.toFixed(2)}%`
              : '—'}
          </p>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">{t.sensitivityCoeffDesc}</p>
        </div>
        <div className="p-3 rounded border border-[var(--color-border)]">
          <p className="text-xs text-[var(--color-muted)]">{t.baseRevenue}</p>
          <p className="text-lg font-mono font-bold">
            {data.base_revenue != null
              ? `$${(data.base_revenue / 1000).toFixed(0)}k`
              : '—'}
          </p>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">{effectiveRegion} | {data.scenario || 'central'}</p>
        </div>
      </div>

      {/* Sensitivity Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm font-sans border-collapse">
          <thead>
            <tr className="border-b-2 border-[var(--color-text)]">
              <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                {t.gasChange}
              </th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                {t.gasPrice}
              </th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                {t.peakImpact}
              </th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                {t.revenueImpact}
              </th>
              <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                {t.revenueChangePct}
              </th>
            </tr>
          </thead>
          <tbody>
            {scenarios.map((scenario, idx) => {
              const isBase = scenario.gas_price_change_pct === 0;
              const isPositive = scenario.revenue_change_pct > 0;
              const isNegative = scenario.revenue_change_pct < 0;

              return (
                <tr
                  key={idx}
                  className={`border-b border-[var(--color-border)] ${
                    isBase ? 'bg-blue-50 dark:bg-blue-950/20 font-bold' : ''
                  }`}
                >
                  <td className="py-2 px-2 font-mono text-xs">
                    {isBase
                      ? t.baseCase
                      : `${scenario.gas_price_change_pct > 0 ? '+' : ''}${scenario.gas_price_change_pct}%`}
                  </td>
                  <td className="text-right py-2 px-2 font-mono text-xs">
                    ${scenario.gas_price?.toFixed(2) ?? '—'}
                  </td>
                  <td className="text-right py-2 px-2 font-mono text-xs">
                    {scenario.peak_price_impact != null
                      ? `${scenario.peak_price_impact >= 0 ? '+' : ''}${scenario.peak_price_impact.toFixed(1)}`
                      : '—'}
                  </td>
                  <td className="text-right py-2 px-2 font-mono text-xs">
                    {scenario.revenue_impact != null
                      ? `${scenario.revenue_impact >= 0 ? '+' : ''}$${(scenario.revenue_impact / 1000).toFixed(1)}k`
                      : '—'}
                  </td>
                  <td className={`text-right py-2 px-2 font-mono text-xs font-bold ${
                    isPositive ? 'text-green-800 dark:text-green-400' : ''
                  }${isNegative ? 'text-red-800 dark:text-red-400' : ''}`}>
                    {scenario.revenue_change_pct != null
                      ? `${scenario.revenue_change_pct >= 0 ? '+' : ''}${scenario.revenue_change_pct.toFixed(1)}%`
                      : '—'}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
