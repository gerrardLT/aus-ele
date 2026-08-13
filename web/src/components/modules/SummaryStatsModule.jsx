/**
 * SummaryStatsModule — 自带数据获取的 SummaryStats 包装器
 */

import { useEffect, useState } from 'react';
import SummaryStats from '../SummaryStats';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';
import { translations } from '../../translations';

const API_BASE = getApiBase();

export default function SummaryStatsModule({ config, lang = 'zh' }) {
  const { filters } = useFilters();
  const [chartData, setChartData] = useState(null);
  const [loading, setLoading] = useState(false);

  const region = filters.region;
  const year = filters.year;
  const quarter = filters.quarter;
  const dayType = filters.dayType;
  const t = { ...(translations[lang] || translations.zh).summary_stats, ...(translations[lang] || translations.zh).advanced_metrics };

  useEffect(() => {
    if (!region || !year) return;
    setLoading(true);
    const params = new URLSearchParams({
      year: String(year),
      region,
      interval_minutes: String(config?.settlementIntervalMinutes || 5),
    });
    // 修复（2026-08-13）：季度/日类型筛选此前未传入，统计不随筛选变化
    if (quarter && quarter !== 'ALL') params.set('quarter', quarter);
    if (dayType && dayType !== 'ALL') params.set('day_type', dayType);
    fetchJson(`${API_BASE}/price-trend?${params}`)
      .then((res) => { setChartData(res); setLoading(false); })
      .catch(() => setLoading(false));
  }, [region, year, quarter, dayType, config?.settlementIntervalMinutes]);

  if (loading || !chartData) return null;

  // API returns stats and advanced_stats directly
  return <SummaryStats stats={chartData.stats} advancedStats={chartData.advanced_stats} t={t} />;
}
