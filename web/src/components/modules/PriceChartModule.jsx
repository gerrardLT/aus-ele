/**
 * PriceChartModule — 自带数据获取的 PriceChart 包装器
 *
 * 在动态渲染模式下，PriceChart 是纯展示组件（需要 data prop）。
 * 本模块包装了数据获取逻辑，使其可以独立工作。
 */

import { useEffect, useState } from 'react';
import PriceChart from '../PriceChart';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';
import { translations } from '../../translations';

const API_BASE = getApiBase();

export default function PriceChartModule({ config, lang = 'zh' }) {
  const { filters } = useFilters();
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);

  const region = filters.region;
  const year = filters.year;
  const quarter = filters.quarter;
  const dayType = filters.dayType;
  const t = (translations[lang] || translations.zh).price_chart;

  useEffect(() => {
    if (!region || !year) return;
    setLoading(true);
    const params = new URLSearchParams({
      year: String(year),
      region,
      interval_minutes: String(config?.settlementIntervalMinutes || 5),
    });
    // 修复（2026-08-13）：季度/日类型筛选此前未传入，图表不随筛选变化
    if (quarter && quarter !== 'ALL') params.set('quarter', quarter);
    if (dayType && dayType !== 'ALL') params.set('day_type', dayType);
    fetchJson(`${API_BASE}/price-trend?${params}`)
      .then((res) => {
        setChartData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [region, year, quarter, dayType, config?.settlementIntervalMinutes]);

  if (loading) {
    return <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif">{lang === 'zh' ? '加载价格数据...' : 'Loading price data...'}</div>;
  }

  return (
    <div className="h-[420px]">
      <PriceChart data={chartData?.data} t={t} locale={lang} />
    </div>
  );
}
