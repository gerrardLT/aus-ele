/**
 * CrossValidationTable — 多源数据交叉验证对比表
 *
 * 渲染多源数据对比表格，显示数据点、来源名称、来源日期、报告值、差异百分比。
 * 差异超过 10% 的数据点高亮显示，过期数据（is_stale）显示警告标志。
 * 调用 GET /api/v1/narrative/cross-validation/{category} 获取数据。
 *
 * Requirements: 7.4, 7.5, 12.1, 12.2, 12.3, 12.4, 12.5
 */

import { useEffect, useState, useCallback } from 'react';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const CATEGORIES = ['coal_retirements', 'revenue_benchmarks', 'price_forecasts'];

const LABELS = {
  zh: {
    title: '多源交叉验证',
    subtitle: '对比多个独立数据源的估计值，识别数据差异',
    dataPoint: '数据点',
    source: '来源',
    sourceDate: '来源日期',
    reportedValue: '报告值',
    discrepancy: '差异%',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    noData: '暂无对比数据',
    staleWarning: '数据已过期（超过12个月未更新）',
    categories: {
      coal_retirements: '煤电退役日期',
      revenue_benchmarks: '收入基准',
      price_forecasts: '价格预测',
    },
  },
  en: {
    title: 'Cross-Validation',
    subtitle: 'Compare estimates from multiple independent data sources',
    dataPoint: 'Data Point',
    source: 'Source',
    sourceDate: 'Source Date',
    reportedValue: 'Reported Value',
    discrepancy: 'Discrepancy %',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    noData: 'No comparison data available',
    staleWarning: 'Data is stale (not updated in 12+ months)',
    categories: {
      coal_retirements: 'Coal Retirements',
      revenue_benchmarks: 'Revenue Benchmarks',
      price_forecasts: 'Price Forecasts',
    },
  },
};

const DISCREPANCY_THRESHOLD = 10;

// eslint-disable-next-line no-unused-vars
export default function CrossValidationTable({ config, lang = 'en', category: propCategory }) {
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [category, setCategory] = useState(propCategory || CATEGORIES[0]);

  const fetchData = useCallback(() => {
    setLoading(true);
    setError(false);
    fetchJson(`${API_BASE}/v1/narrative/cross-validation/${category}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [category]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useEffect(() => {
    if (propCategory && CATEGORIES.includes(propCategory)) {
      setCategory(propCategory);
    }
  }, [propCategory]);

  if (loading && !data) {
    return <div className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">{t.loading}</div>;
  }
  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button onClick={fetchData} className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]">{t.retry}</button>
      </div>
    );
  }
  if (!data) return null;

  const entries = data.entries || [];

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Category tabs */}
      <div className="flex gap-2 mb-4">
        {CATEGORIES.map((cat) => (
          <button
            key={cat}
            onClick={() => setCategory(cat)}
            className={`px-3 py-1.5 text-xs font-sans rounded border transition-colors ${
              category === cat
                ? 'border-[var(--color-text)] bg-[var(--color-text)] text-[var(--color-bg)]'
                : 'border-[var(--color-border)] hover:border-[var(--color-text)]'
            }`}
          >
            {t.categories[cat] || cat}
          </button>
        ))}
      </div>

      {entries.length === 0 ? (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] text-sm">{t.noData}</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans border-collapse">
            <thead>
              <tr className="border-b-2 border-[var(--color-text)]">
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.dataPoint}</th>
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.source}</th>
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.sourceDate}</th>
                <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.reportedValue}</th>
                <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.discrepancy}</th>
              </tr>
            </thead>
            <tbody>
              {entries.map((entry, idx) => {
                const isHighDiscrepancy = entry.discrepancy_pct != null && Math.abs(entry.discrepancy_pct) > DISCREPANCY_THRESHOLD;
                const isStale = entry.is_stale;

                return (
                  <tr
                    key={`${entry.data_point}-${entry.source_name}-${idx}`}
                    className={`border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] ${
                      isHighDiscrepancy ? 'bg-red-50 dark:bg-red-950/20' : ''
                    }`}
                  >
                    <td className="py-2 px-2 font-mono text-xs">{entry.data_point}</td>
                    <td className="py-2 px-2 text-xs">
                      {entry.source_url ? (
                        <a href={entry.source_url} target="_blank" rel="noopener noreferrer" className="underline hover:text-blue-600">
                          {entry.source_name}
                        </a>
                      ) : (
                        entry.source_name
                      )}
                    </td>
                    <td className="py-2 px-2 text-xs font-mono">
                      <span className="inline-flex items-center gap-1">
                        {entry.source_date}
                        {isStale && (
                          <span title={t.staleWarning} className="text-amber-500 cursor-help">⚠️</span>
                        )}
                      </span>
                    </td>
                    <td className="text-right py-2 px-2 font-mono text-xs">{entry.reported_value}</td>
                    <td className={`text-right py-2 px-2 font-mono text-xs font-bold ${
                      isHighDiscrepancy ? 'text-red-800 dark:text-red-400' : ''
                    }`}>
                      {entry.discrepancy_pct != null
                        ? `${entry.discrepancy_pct > 0 ? '+' : ''}${entry.discrepancy_pct.toFixed(1)}%`
                        : '—'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      {/* Last updated info */}
      {data.last_updated && (
        <p className="text-xs text-[var(--color-muted)] mt-3 font-sans">
          Last updated: {data.last_updated}
        </p>
      )}
    </div>
  );
}
