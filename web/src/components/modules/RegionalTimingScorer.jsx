/**
 * RegionalTimingScorer — 区域投资时机评分器
 *
 * 基于前瞻性因素（煤电退役、管道增长、可再生渗透率、收入趋势）
 * 计算各区域投资吸引力评分，支持目标年份选择和雷达图对比。
 * Requirements: 3.1, 3.2, 3.5, 3.6, 3.7, 6.3
 */

import { useEffect, useState } from 'react';
import {
  PolarAngleAxis, PolarGrid, PolarRadiusAxis,
  Radar, RadarChart, ResponsiveContainer, Tooltip,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const DIMENSION_KEYS = ['coal_retirement', 'pipeline_growth', 'renewable_penetration', 'revenue_trajectory'];

const DIMENSION_LABELS = {
  zh: {
    coal_retirement: '煤电退役',
    pipeline_growth: '管道增长',
    renewable_penetration: '可再生渗透',
    revenue_trajectory: '收入趋势',
  },
  en: {
    coal_retirement: 'Coal Retirement',
    pipeline_growth: 'Pipeline Growth',
    renewable_penetration: 'Renewable Penetration',
    revenue_trajectory: 'Revenue Trajectory',
  },
};

const LABELS = {
  zh: {
    title: '区域投资时机评分',
    subtitle: '基于前瞻性因素的区域投资吸引力综合评分',
    rank: '排名',
    region: '区域',
    score: '综合评分',
    targetYear: '目标投资年份',
    keyEvents: '关键事件',
    marketExample: '真实案例',
    conclusion: '推荐结论',
    coalDataNote: '注：煤电退役数据不可用，评分仅基于其余维度',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
  },
  en: {
    title: 'Regional Timing Score',
    subtitle: 'Forward-looking regional investment attractiveness scoring',
    rank: 'Rank',
    region: 'Region',
    score: 'Score',
    targetYear: 'Target Year',
    keyEvents: 'Key Events',
    marketExample: 'Market Example',
    conclusion: 'Recommendation',
    coalDataNote: 'Note: Coal retirement data unavailable, scoring based on remaining dimensions',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
  },
};

const REGION_COLORS = {
  NSW1: '#2563eb',
  QLD1: '#dc2626',
  VIC1: '#7c3aed',
  SA1: '#f59e0b',
  TAS1: '#10b981',
};

function buildYearOptions() {
  const currentYear = new Date().getFullYear();
  const options = [];
  for (let i = 0; i <= 5; i++) {
    options.push(currentYear + i);
  }
  return options;
}

export default function RegionalTimingScorer({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const dimLabels = DIMENSION_LABELS[lang] || DIMENSION_LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [targetYear, setTargetYear] = useState(new Date().getFullYear() + 2);

  const market = filters.market;
  const yearOptions = buildYearOptions();

  useEffect(() => {
    setLoading(true);
    setError(false);
    const params = new URLSearchParams({ market, target_year: String(targetYear) });
    fetchJson(`${API_BASE}/v1/outlook/regional-timing?${params}`)
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [market, targetYear]);

  if (loading) {
    return <div className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">{t.loading}</div>;
  }
  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button onClick={() => { setError(false); setLoading(true); }} className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]">{t.retry}</button>
      </div>
    );
  }
  if (!data) return null;

  const rankings = data.rankings || [];
  const marketExamples = data.market_examples || [];

  // Build radar chart data: one entry per dimension, with each region as a key
  const radarData = DIMENSION_KEYS.map((dim) => {
    const entry = { dimension: dimLabels[dim] };
    rankings.forEach((r) => { entry[r.region] = r.dimensions?.[dim] || 0; });
    return entry;
  });

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Target year selector */}
      <div className="mb-4 flex items-center gap-3">
        <label className="text-xs font-bold tracking-widest uppercase text-[var(--color-muted)]">{t.targetYear}</label>
        <select
          value={targetYear}
          onChange={(e) => setTargetYear(Number(e.target.value))}
          className="px-3 py-1.5 text-sm font-mono border border-[var(--color-border)] rounded bg-transparent hover:border-[var(--color-text)] focus:outline-none"
        >
          {yearOptions.map((yr) => (
            <option key={yr} value={yr}>{yr}</option>
          ))}
        </select>
      </div>

      {/* Coal data availability note */}
      {data.coal_data_available === false && (
        <p className="text-xs text-[var(--color-muted)] italic mb-4">{t.coalDataNote}</p>
      )}

      {/* Ranking table + Radar chart */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        <div className="overflow-x-auto">
          <table className="w-full text-sm font-sans border-collapse">
            <thead>
              <tr className="border-b-2 border-[var(--color-text)]">
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.rank}</th>
                <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.region}</th>
                <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.score}</th>
                {DIMENSION_KEYS.map((dim) => (
                  <th key={dim} className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{dimLabels[dim]}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rankings.map((r) => (
                <tr key={r.region} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                  <td className="py-2 px-2 font-mono text-xs font-bold">{r.rank}</td>
                  <td className="py-2 px-2 font-mono text-xs">{r.region}</td>
                  <td className="text-right py-2 px-2 font-mono text-xs font-bold">{r.total_score?.toFixed(2)}</td>
                  {DIMENSION_KEYS.map((dim) => (
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
                <Radar
                  key={r.region}
                  name={r.region}
                  dataKey={r.region}
                  stroke={REGION_COLORS[r.region] || '#666'}
                  fill={REGION_COLORS[r.region] || '#666'}
                  fillOpacity={0.1}
                />
              ))}
            </RadarChart>
          </ResponsiveContainer>
        </div>
      </div>

      {/* Market examples annotation */}
      {marketExamples.length > 0 && (
        <div className="mb-6 p-3 border border-[var(--color-border)] rounded">
          <h4 className="text-xs font-bold tracking-widest uppercase text-[var(--color-muted)] mb-2">{t.marketExample}</h4>
          {marketExamples.map((ex, idx) => (
            <p key={idx} className="text-xs text-[var(--color-muted)] mb-1">
              <span className="font-mono font-bold">{ex.region}</span>
              {' — '}
              {ex.description}
              {' '}
              <span className="italic">({ex.data_year}, {ex.label})</span>
            </p>
          ))}
        </div>
      )}

      {/* Conclusion */}
      {data.conclusion && (
        <div className="p-3 border-l-2 border-[var(--color-text)]">
          <h4 className="text-xs font-bold tracking-widest uppercase text-[var(--color-muted)] mb-1">{t.conclusion}</h4>
          <p className="text-sm font-serif">{data.conclusion}</p>
        </div>
      )}
    </div>
  );
}
