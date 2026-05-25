import { useState, useEffect, useCallback } from 'react';
import { fetchJson } from '../lib/apiClient';
import { getApiBase } from '../lib/apiBase';

const API_BASE = getApiBase();

/**
 * Hook for fetching market price data with window selection support.
 * @param {Object} config - MarketConfig object
 * @param {Object} filters - { region, year, quarter, dayType }
 * @returns {{ chartData, visibleData, loading, error, onWindowChange }}
 */
export function useMarketData(config, filters) {
  const [chartData, setChartData] = useState(null);
  const [visibleData, setVisibleData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    if (!filters.year || !filters.region) return;
    setLoading(true);
    setError(null);

    let url = `${API_BASE}/price-trend?year=${filters.year}&region=${filters.region}&limit=720&interval_minutes=${config.settlementIntervalMinutes}`;
    if (filters.quarter && filters.quarter !== 'ALL') url += `&quarter=${filters.quarter}`;
    if (filters.dayType && filters.dayType !== 'ALL') url += `&day_type=${filters.dayType}`;

    fetchJson(url)
      .then(data => {
        setChartData(data);
        setVisibleData(Array.isArray(data?.data) ? data.data : []);
        setLoading(false);
      })
      .catch(err => {
        setError(err.message || 'Failed to load price data');
        setLoading(false);
      });
  }, [filters.year, filters.region, filters.quarter, filters.dayType, config.settlementIntervalMinutes]);

  const onWindowChange = useCallback((data) => {
    setVisibleData(data);
  }, []);

  return { chartData, visibleData, loading, error, onWindowChange };
}
