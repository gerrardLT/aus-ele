/**
 * ExecutiveSummary — 执行摘要视图
 *
 * 聚合各阶段关键 KPI，单屏呈现投资结论。
 * 从 /api/market-summary/{market}/{region} 获取数据，
 * 展示 4-6 个 KpiCard，点击可跳转到对应 FunnelStage。
 *
 * Requirements: 2.1, 2.2, 2.3, 2.4, 2.6
 */

import { useState, useEffect, useRef } from 'react';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';
import KpiCard from './KpiCard';

/**
 * 阶段 KPI 到 stageId 的映射
 */
const STAGE_KPI_MAP = [
  { stageKey: 'market_opportunity', kpiIndex: 0, stageId: 'market-opportunity' },
  { stageKey: 'opportunity_identification', kpiIndex: 0, stageId: 'opportunity-identification' },
  { stageKey: 'revenue_estimation', kpiIndex: 0, stageId: 'revenue-estimation' },
  { stageKey: 'investment_decision', kpiIndex: 0, stageId: 'investment-decision' },
];

/**
 * overall_rating → 语义色映射
 */
const RATING_SENTIMENT_MAP = {
  strong_opportunity: 'positive',
  moderate_opportunity: 'neutral',
  weak_opportunity: 'warning',
  unfavorable: 'negative',
};

/**
 * overall_rating → 双语标签
 */
const RATING_LABEL_MAP = {
  zh: { strong_opportunity: '强机会', moderate_opportunity: '中等机会', weak_opportunity: '弱机会', unfavorable: '不利' },
  en: { strong_opportunity: 'Strong', moderate_opportunity: 'Moderate', weak_opportunity: 'Weak', unfavorable: 'Unfavorable' },
};

const DEBOUNCE_MS = 500;

export default function ExecutiveSummary({
  market,
  region,
  year,
  bessParams,
  onKpiClick,
  lang = 'zh',
}) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const debounceRef = useRef(null);

  /**
   * 构建请求 URL
   */
  function buildUrl() {
    const base = getApiBase();
    const params = new URLSearchParams({
      year: String(year),
      bess_power_mw: String(bessParams.power_mw),
      bess_duration_hours: String(bessParams.duration_hours),
      bess_efficiency: String(bessParams.round_trip_efficiency),
    });
    return `${base}/market-summary/${market}/${region}?${params.toString()}`;
  }

  /**
   * 执行数据获取
   */
  async function fetchData() {
    setLoading(true);
    setError(null);

    try {
      const url = buildUrl();
      const result = await fetchJson(url);
      setData(result);
    } catch (err) {
      setError(err.message || (lang === 'zh' ? '数据加载失败' : 'Failed to load data'));
    } finally {
      setLoading(false);
    }
  }

  // 防抖获取：mount 时立即获取，props 变化时 500ms 防抖
  useEffect(() => {
    if (debounceRef.current) {
      clearTimeout(debounceRef.current);
    }

    debounceRef.current = setTimeout(() => {
      fetchData();
    }, DEBOUNCE_MS);

    return () => {
      if (debounceRef.current) {
        clearTimeout(debounceRef.current);
      }
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [market, region, year, bessParams.power_mw, bessParams.duration_hours, bessParams.round_trip_efficiency]);

  /**
   * 从 stages 数据中提取 KPI 列表
   */
  function extractKpis() {
    if (!data || !data.stages) return [];

    const kpis = [];
    for (const mapping of STAGE_KPI_MAP) {
      const stage = data.stages[mapping.stageKey];
      if (stage && stage.kpis && stage.kpis[mapping.kpiIndex]) {
        kpis.push({
          ...stage.kpis[mapping.kpiIndex],
          stageId: mapping.stageId,
        });
      }
    }
    return kpis;
  }

  function handleKpiClick(stageId) {
    if (typeof onKpiClick === 'function') {
      onKpiClick(stageId);
    }
  }

  function handleRetry() {
    fetchData();
  }

  // 加载态：骨架卡片
  if (loading) {
    return (
      <section aria-label={lang === 'zh' ? '执行摘要' : 'Executive Summary'} className="mb-8">
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
          {[1, 2, 3, 4].map((i) => (
            <div
              key={i}
              className="border border-[var(--color-border)] rounded-lg p-4 animate-pulse"
            >
              <div className="h-3 w-20 bg-[var(--color-border)] rounded mb-3" />
              <div className="h-6 w-16 bg-[var(--color-border)] rounded" />
            </div>
          ))}
        </div>
      </section>
    );
  }

  // 错误态：错误消息 + 重试按钮
  if (error) {
    return (
      <section aria-label={lang === 'zh' ? '执行摘要' : 'Executive Summary'} className="mb-8">
        <div className="border border-[var(--color-border)] rounded-lg p-6 text-center">
          <p className="text-[var(--color-muted)] mb-3">
            {error}
          </p>
          <button
            type="button"
            className="px-4 py-2 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)] transition-colors cursor-pointer"
            onClick={handleRetry}
          >
            {lang === 'zh' ? '重试' : 'Retry'}
          </button>
        </div>
      </section>
    );
  }

  const kpis = extractKpis();
  const overallRating = data?.overall_rating;
  const ratingSentiment = RATING_SENTIMENT_MAP[overallRating] || 'neutral';
  const labels = RATING_LABEL_MAP[lang] || RATING_LABEL_MAP.zh;
  const ratingLabel = labels[overallRating] || overallRating;

  return (
    <section aria-label={lang === 'zh' ? '执行摘要' : 'Executive Summary'} className="mb-8">
      {/* 总体评级徽章 */}
      {overallRating && (
        <div className="mb-4 flex items-center gap-2">
          <span className="text-xs text-[var(--color-muted)] uppercase tracking-wider">
            {lang === 'zh' ? '总体评级' : 'OVERALL RATING'}
          </span>
          <span
            className={`text-xs font-medium px-2 py-0.5 rounded ${
              ratingSentiment === 'positive'
                ? 'bg-[#22C55E]/10 text-[#22C55E]'
                : ratingSentiment === 'negative'
                ? 'bg-[#E53E3E]/10 text-[#E53E3E]'
                : ratingSentiment === 'warning'
                ? 'bg-[#F59E0B]/10 text-[#F59E0B]'
                : 'bg-[var(--color-border)] text-[var(--color-text)]'
            }`}
          >
            {ratingLabel}
          </span>
        </div>
      )}

      {/* KPI 卡片网格 */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        {kpis.map((kpi, index) => (
          <KpiCard
            key={`${kpi.label}-${index}`}
            label={kpi.label}
            value={kpi.value}
            unit={kpi.unit}
            sentiment={kpi.sentiment}
            size="md"
            onClick={() => handleKpiClick(kpi.stageId)}
          />
        ))}
      </div>
    </section>
  );
}
