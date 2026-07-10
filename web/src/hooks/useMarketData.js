import { useCallback } from 'react';
import { useQuery } from '@tanstack/react-query';
import { fetchJson } from '../lib/apiClient';
import { getApiBase } from '../lib/apiBase';

const API_BASE = getApiBase();

/**
 * Hook for fetching market price data with TanStack Query caching.
 * @param {Object} config - MarketConfig object
 * @param {Object} filters - { region, year, quarter, dayType }
 * @returns {{ chartData, visibleData, loading, error, onWindowChange }}
 */
export function useMarketData(config, filters) {
  const queryKey = [
    'market-data',
    filters.year,
    filters.region,
    filters.quarter,
    filters.dayType,
    config.settlementIntervalMinutes,
  ];

  const queryFn = async () => {
    let url = `${API_BASE}/price-trend?year=${filters.year}&region=${filters.region}&limit=5000&interval_minutes=${config.settlementIntervalMinutes}`;
    if (filters.quarter && filters.quarter !== 'ALL') url += `&quarter=${filters.quarter}`;
    if (filters.dayType && filters.dayType !== 'ALL') url += `&day_type=${filters.dayType}`;
    return fetchJson(url);
  };

  const { data: chartData, isLoading: loading, error } = useQuery({
    queryKey,
    queryFn,
    enabled: Boolean(filters.year && filters.region),
    staleTime: 60_000, // price data is relatively static, 1min stale
  });

  const visibleData = Array.isArray(chartData?.data) ? chartData.data : [];

  const onWindowChange = useCallback((data) => {
    // Window-level filtering is handled by the component
    return data;
  }, []);

  return { chartData, visibleData, loading, error, onWindowChange };
}
