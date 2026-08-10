/**
 * NetworkImpactDisplay — 网络增强前后对比展示
 *
 * 展示网络增强项目（新互联线）对区域价差的影响，
 * 显示增强前后的价差对比和压缩百分比。
 * 调用 GET /api/v1/narrative/network-impact/{region} 获取数据。
 *
 * Requirements: 14.4
 */

import { useEffect, useState, useCallback } from 'react';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '网络增强影响分析',
    subtitle: '新互联线投运对区域价差的压缩效应',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    noData: '暂无网络增强数据',
    projectName: '项目名称',
    region: '影响区域',
    reductionPct: '价差压缩',
    beforeAugmentation: '增强前价差',
    afterAugmentation: '增强后价差',
    year: '年份',
    spread: '价差 ($/MWh)',
    comparisonTitle: '价差前后对比',
    before: '增强前',
    after: '增强后',
    reduction: '压缩幅度',
  },
  en: {
    title: 'Network Augmentation Impact',
    subtitle: 'Interconnector commissioning effect on regional price spreads',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    noData: 'No network augmentation data available',
    projectName: 'Project',
    region: 'Affected Region',
    reductionPct: 'Spread Reduction',
    beforeAugmentation: 'Spread Before',
    afterAugmentation: 'Spread After',
    year: 'Year',
    spread: 'Spread ($/MWh)',
    comparisonTitle: 'Before vs After Comparison',
    before: 'Before',
    after: 'After',
    reduction: 'Reduction',
  },
};

export default function NetworkImpactDisplay({ config, lang = 'zh', region }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const effectiveRegion = region || filters.region || config?.defaultRegion || 'NSW1';

  const fetchData = useCallback(() => {
    setLoading(true);
    setError(false);
    fetchJson(`${API_BASE}/v1/narrative/network-impact/${effectiveRegion}`)
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

  if (!data || (!data.project_name && !data.spread_before)) {
    return (
      <div className="h-32 flex items-center justify-center text-[var(--color-muted)] text-sm">
        {t.noData}
      </div>
    );
  }

  const spreadBefore = data.spread_before || [];
  const spreadAfter = data.spread_after || [];
  const reductionPct = data.reduction_pct;

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Project Summary */}
      <div className="mb-4 p-3 rounded border border-[var(--color-status-success)]/40 bg-[var(--color-status-success)]/10">
        <div className="flex items-center gap-2 mb-2">
          <span className="text-[var(--color-status-success)] text-lg">◆</span>
          <span className="text-sm font-serif font-bold">{data.project_name || 'Network Project'}</span>
        </div>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <p className="text-xs text-[var(--color-muted)]">{t.region}</p>
            <p className="text-sm font-mono">{data.region || effectiveRegion}</p>
          </div>
          <div>
            <p className="text-xs text-[var(--color-muted)]">{t.reductionPct}</p>
            <p className="text-sm font-mono font-bold text-[var(--color-status-success)]">
              {reductionPct != null ? `-${reductionPct.toFixed(1)}%` : '—'}
            </p>
          </div>
        </div>
      </div>

      {/* Before/After Comparison Table */}
      {spreadBefore.length > 0 && (
        <>
          <h4 className="text-sm font-serif font-bold mb-2">{t.comparisonTitle}</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans border-collapse">
              <thead>
                <tr className="border-b-2 border-[var(--color-text)]">
                  <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                    {t.year}
                  </th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                    {t.before} ($/MWh)
                  </th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                    {t.after} ($/MWh)
                  </th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">
                    {t.reduction}
                  </th>
                </tr>
              </thead>
              <tbody>
                {spreadBefore.map((beforeEntry, idx) => {
                  const afterEntry = spreadAfter[idx] || {};
                  const beforeSpread = beforeEntry.spread;
                  const afterSpread = afterEntry.spread;
                  const diff = beforeSpread != null && afterSpread != null
                    ? beforeSpread - afterSpread
                    : null;
                  const diffPct = beforeSpread && diff != null
                    ? (diff / beforeSpread) * 100
                    : null;

                  return (
                    <tr key={idx} className="border-b border-[var(--color-border)]">
                      <td className="py-2 px-2 font-mono text-xs">{beforeEntry.year}</td>
                      <td className="text-right py-2 px-2 font-mono text-xs">
                        {beforeSpread != null ? `$${beforeSpread.toFixed(1)}` : '—'}
                      </td>
                      <td className="text-right py-2 px-2 font-mono text-xs text-[var(--color-status-success)]">
                        {afterSpread != null ? `$${afterSpread.toFixed(1)}` : '—'}
                      </td>
                      <td className="text-right py-2 px-2 font-mono text-xs text-[var(--color-status-success)] font-bold">
                        {diffPct != null ? `-${diffPct.toFixed(1)}%` : '—'}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
