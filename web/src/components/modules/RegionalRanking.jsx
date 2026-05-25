/**
 * RegionalRanking — NEM 区域投资吸引力排名
 *
 * 基于多维度指标对 NEM 五个区域进行排序，支持权重调整。
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
 */

import { useEffect, useState, useCallback } from 'react';
import {
  PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Tooltip,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const DEFAULT_WEIGHTS = {
  weight_arbitrage: 0.2,
  weight_spikes: 0.2,
  weight_fcas: 0.2,
  weight_saturation: 0.2,
  weight_constraints: 0.2,
};

const DIMENSION_LABELS = {
  zh: { arbitrage: '套利收入', spikes: '极端事件', fcas: 'FCAS收入', saturation: '饱和风险', constraints: '网络约束' },
  en: { arbitrage: 'Arbitrage', spikes: 'Spikes', fcas: 'FCAS', saturation: 'Saturation', constraints: 'Constraints' },
};

const LABELS = {
  zh: {
    title: 'NEM 区域投资排名',
    subtitle: '基于多维度指标的区域投资吸引力综合排序',
    rank: '排名',
    region: '区域',
    score: '总分',
    weights: '权重调整',
    dataYear: '数据年份',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
  },
  en: {
    title: 'NEM Regional Ranking',
    subtitle: 'Multi-dimensional investment attractiveness ranking',
    rank: 'Rank',
    region: 'Region',
    score: 'Score',
    weights: 'Weight Adjustment',
    dataYear: 'Data Year',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
  },
};

const REGION_COLORS = { NSW1: '#2563eb', QLD1: '#dc2626', VIC1: '#7c3aed', SA1: '#f59e0b', TAS1: '#10b981' };

export default function RegionalRanking({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const dimLabels = DIMENSION_LABELS[lang] || DIMENSION_LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [weights, setWeights] = useState(DEFAULT_WEIGHTS);

  const year = filters.year;

  const fetchData = useCallback(() => {
    if (!year) return;
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ year: String(year), ...Object.fromEntries(Object.entries(weights).map(([k, v]) => [k, String(v)])) });
    fetchJson(`${API_BASE}/v1/nem/regional-ranking?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [year, weights]);

  // Debounce: only fetch 500ms after last weight change
  useEffect(() => {
    const timer = setTimeout(() => { fetchData(); }, 500);
    return () => clearTimeout(timer);
  }, [fetchData]);

  const handleWeightChange = (key, value) => {
    setWeights((prev) => ({ ...prev, [key]: parseFloat(value) || 0 }));
  };

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

  const rankings = data.rankings || [];
  const radarData = Object.keys(dimLabels).map((dim) => {
    const entry = { dimension: dimLabels[dim] };
    rankings.forEach((r) => { entry[r.region] = r.dimensions?.[dim] || 0; });
    return entry;
  });

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>
      {data.data_year && <p className="text-xs text-[var(--color-muted)] mb-4">{t.dataYear}: {data.data_year}</p>}

      {/* Weight sliders */}
      <div className="mb-6 p-3 border border-[var(--color-border)] rounded">
        <h4 className="text-xs font-bold tracking-widest uppercase text-[var(--color-muted)] mb-3">{t.weights}</h4>
        <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
          {Object.entries(weights).map(([key, val]) => {
            const dimKey = key.replace('weight_', '');
            return (
              <div key={key} className="flex flex-col gap-1">
                <label className="text-xs text-[var(--color-muted)]">{dimLabels[dimKey] || dimKey}</label>
                <input
                  type="range" min="0" max="1" step="0.05" value={val}
                  onChange={(e) => handleWeightChange(key, e.target.value)}
                  className="w-full h-1.5 rounded-full appearance-auto cursor-pointer accent-[#6366f1]"
                />
                <span className="text-xs font-mono text-center">{val.toFixed(2)}</span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Ranking table + Radar chart */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans border-collapse">
            <thead>
              <tr className="border-b-2 border-[var(--color-text)]">
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.rank}</th>
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.region}</th>
                <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.score}</th>
                {Object.values(dimLabels).map((label) => (
                  <th key={label} className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rankings.map((r) => (
                <tr key={r.region} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)]">
                  <td className="py-2 px-2 font-mono text-xs font-bold">{r.rank}</td>
                  <td className="py-2 px-2 font-mono text-xs">{r.region}</td>
                  <td className="text-right py-2 px-2 font-mono text-xs font-bold">{r.total_score?.toFixed(2)}</td>
                  {Object.keys(dimLabels).map((dim) => (
                    <td key={dim} className="text-right py-2 px-2 font-mono text-xs">{(r.dimensions?.[dim] || 0).toFixed(2)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <div>
          <ResponsiveContainer width="100%" height={280}>
            <RadarChart data={radarData}>
              <PolarGrid stroke="var(--color-border)" />
              <PolarAngleAxis dataKey="dimension" tick={{ fontSize: 10 }} />
              <PolarRadiusAxis tick={{ fontSize: 9 }} domain={[0, 1]} />
              <Tooltip />
              {rankings.map((r) => (
                <Radar key={r.region} name={r.region} dataKey={r.region} stroke={REGION_COLORS[r.region] || '#666'} fill={REGION_COLORS[r.region] || '#666'} fillOpacity={0.1} />
              ))}
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
