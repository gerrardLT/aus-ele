import { useState, useEffect, useRef } from 'react';
import { useFilters } from '../contexts/FilterContext';
import { fetchJson } from '../lib/apiClient';
import { getApiBase } from '../lib/apiBase';

const API_BASE = getApiBase();

/**
 * Hook for revenue analysis state and API calls.
 * Subscribes to FilterContext and auto-refetches when filters change.
 */
export function useRevenueAnalysis() {
  const { filters, queryParams } = useFilters();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const controllerRef = useRef(null);

  useEffect(() => {
    if (!filters.year) return;

    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setLoading(true);
    setError(null);

    const params = new URLSearchParams(queryParams);
    fetchJson(`${API_BASE}/revenue-analysis?${params}`, { signal: controller.signal })
      .then((result) => {
        setData(result);
        setLoading(false);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setError(err.message);
          setLoading(false);
        }
      });

    return () => controller.abort();
  }, [filters.year, filters.region, filters.month, filters.quarter, filters.dayType]);

  return { data, loading, error };
}
