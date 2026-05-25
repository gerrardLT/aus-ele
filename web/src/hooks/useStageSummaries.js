import { useState, useEffect } from 'react';
import { fetchJson } from '../lib/apiClient';
import { getApiBase } from '../lib/apiBase';
import { STAGE_IDS } from '../lib/marketConfig';

const API_BASE = getApiBase();

/**
 * Hook that fetches all 4 stage summaries in parallel.
 * Single stage failure does not affect other stages.
 * @param {string} market - 'NEM' or 'WEM'
 * @param {string} region - e.g. 'NSW1' or 'WEM'
 * @param {number} year - analysis year
 * @param {Object} bessParams - { power_mw, duration_hours, round_trip_efficiency }
 * @returns {{ summaries: Object, loading: Object }}
 */
export function useStageSummaries(market, region, year, bessParams) {
  const [summaries, setSummaries] = useState({});
  const [loading, setLoading] = useState({});

  useEffect(() => {
    if (!year || !region) return;

    // Mark all as loading
    const loadingState = {};
    STAGE_IDS.forEach(id => { loadingState[id] = true; });
    setLoading(loadingState);

    // Fetch each stage in parallel
    STAGE_IDS.forEach(stageId => {
      const url = `${API_BASE}/stage-summary/${market}/${region}/${stageId}?year=${year}&bess_power_mw=${bessParams.power_mw}&bess_duration_hours=${bessParams.duration_hours}&bess_efficiency=${bessParams.round_trip_efficiency}`;

      fetchJson(url)
        .then(data => {
          setSummaries(prev => ({ ...prev, [stageId]: data }));
          setLoading(prev => ({ ...prev, [stageId]: false }));
        })
        .catch(() => {
          setSummaries(prev => ({ ...prev, [stageId]: null }));
          setLoading(prev => ({ ...prev, [stageId]: false }));
        });
    });
  }, [market, region, year, bessParams.power_mw, bessParams.duration_hours, bessParams.round_trip_efficiency]);

  return { summaries, loading };
}
