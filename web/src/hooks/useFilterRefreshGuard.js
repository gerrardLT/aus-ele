import { useState, useEffect, useRef } from 'react';
import { useFilters } from '../contexts/FilterContext';

/**
 * useFilterRefreshGuard — tracks filter changes and provides a `isRefreshing`
 * boolean that stays true for up to 2 seconds after a filter change.
 *
 * This satisfies Requirement 6.4: "过滤条件变更后 2 秒内发起所有可见模块的数据刷新请求"
 *
 * The existing hooks (usePriceAnalysis, useRevenueAnalysis, etc.) already
 * auto-fetch via useEffect when filters change — which fires synchronously
 * after state update (well within 2 seconds). This guard hook provides UI
 * feedback (e.g. a brief loading indicator) during the refresh window.
 *
 * Returns:
 *   - isRefreshing: true for up to 2000ms after the last filter change
 *   - lastFilterChangeTime: timestamp (ms) of the most recent filter change
 */
const REFRESH_WINDOW_MS = 2000;

export function useFilterRefreshGuard() {
  const { filters } = useFilters();
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [lastFilterChangeTime, setLastFilterChangeTime] = useState(null);
  const timerRef = useRef(null);
  const prevFiltersRef = useRef(filters);

  useEffect(() => {
    // Skip the initial mount — only react to actual changes
    const prev = prevFiltersRef.current;
    if (prev === filters) return;

    // Check if filters actually changed (shallow compare relevant keys)
    const changed =
      prev.region !== filters.region ||
      prev.year !== filters.year ||
      prev.quarter !== filters.quarter ||
      prev.dayType !== filters.dayType ||
      prev.months?.join(',') !== filters.months?.join(',');

    prevFiltersRef.current = filters;

    if (!changed) return;

    const now = Date.now();
    setLastFilterChangeTime(now);
    setIsRefreshing(true);

    // Clear any existing timer
    if (timerRef.current) {
      clearTimeout(timerRef.current);
    }

    // Set refreshing to false after the window expires
    timerRef.current = setTimeout(() => {
      setIsRefreshing(false);
    }, REFRESH_WINDOW_MS);

    return () => {
      if (timerRef.current) {
        clearTimeout(timerRef.current);
      }
    };
  }, [filters]);

  return { isRefreshing, lastFilterChangeTime };
}
