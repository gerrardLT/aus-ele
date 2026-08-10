/**
 * MarketOpportunityStage — Stage 1: 市场机会评估
 *
 * 获取价格数据，渲染 PriceChart + SummaryStats + HourlyDistributionChart。
 * 使用 useMarketData hook 获取数据，通过 FilterContext 读取筛选状态。
 *
 * Requirements: 2.2, 5.2, 5.3, 8.4, 12.1
 */

import { Suspense, lazy, useMemo } from 'react';
import FunnelStage from '../../components/funnel/FunnelStage';
import CollapsibleModule from '../../components/funnel/CollapsibleModule';
import PriceChart from '../../components/PriceChart';
import SummaryStats from '../../components/SummaryStats';
import DeferredSection from '../../components/DeferredSection';
import { useFilters } from '../../contexts/FilterContext';
import { useMarketData } from '../../hooks/useMarketData';
import { STAGE_DEFINITIONS } from '../../lib/marketConfig';
import { translations } from '../../translations';

const HourlyDistributionChart = lazy(() => import('../../components/HourlyDistributionChart'));

function computeWindowStats(points = []) {
  const prices = points.map(p => Number(p?.price)).filter(Number.isFinite);
  if (!prices.length) return { stats: { min: 0, max: 0, avg: 0 }, advancedStats: { neg_ratio: 0 } };
  const neg = prices.filter(v => v < 0);
  const pos = prices.filter(v => v > 0);
  return {
    stats: {
      min: Number(Math.min(...prices).toFixed(2)),
      max: Number(Math.max(...prices).toFixed(2)),
      avg: Number((prices.reduce((s, v) => s + v, 0) / prices.length).toFixed(2)),
    },
    advancedStats: {
      neg_ratio: Number(((neg.length / prices.length) * 100).toFixed(2)),
      neg_avg: neg.length ? Number((neg.reduce((s, v) => s + v, 0) / neg.length).toFixed(2)) : null,
      neg_min: neg.length ? Number(Math.min(...neg).toFixed(2)) : null,
      pos_avg: pos.length ? Number((pos.reduce((s, v) => s + v, 0) / pos.length).toFixed(2)) : null,
      pos_max: pos.length ? Number(Math.max(...pos).toFixed(2)) : null,
    },
  };
}

export default function MarketOpportunityStage({ config, conclusionData, isLoading, onVisible, lang }) {
  const { filters } = useFilters();
  const { chartData, visibleData, loading, error, onWindowChange } = useMarketData(config, filters);
  const stageDef = STAGE_DEFINITIONS[0];
  const modules = config.stages['market-opportunity'].modules;
  const t = translations[lang] || translations.zh;

  const summaryMetrics = useMemo(() => computeWindowStats(visibleData.length ? visibleData : (chartData?.data || [])), [visibleData, chartData]);

  // Error state
  if (error) {
    return (
      <FunnelStage
        stageId="market-opportunity"
        stageNumber={1}
        title={stageDef.title[lang]}
        coreQuestion={stageDef.coreQuestion[lang]}
        conclusionData={conclusionData}
        isLoading={isLoading}
        onVisible={onVisible}
        lang={lang}
      >
        <div className="p-4 border border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/8 text-[var(--color-status-error)] rounded">
          <p>{lang === 'zh' ? '价格数据加载失败' : 'Failed to load price data'}: {error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-2 px-4 py-1.5 text-xs border border-[var(--color-status-error)]/40 rounded hover:bg-[var(--color-status-error)]/10 transition-colors"
          >
            {lang === 'zh' ? '重试' : 'Retry'}
          </button>
        </div>
      </FunnelStage>
    );
  }

  return (
    <FunnelStage
      stageId="market-opportunity"
      stageNumber={1}
      title={stageDef.title[lang]}
      coreQuestion={stageDef.coreQuestion[lang]}
      conclusionData={conclusionData}
      isLoading={isLoading}
      onVisible={onVisible}
      lang={lang}
    >
      {/* PriceChart + SummaryStats — always visible, NOT in CollapsibleModule */}
      {loading ? (
        <div className="h-64 flex items-center justify-center">
          <span className="font-serif text-lg text-[var(--color-muted)]">
            {lang === 'zh' ? '正在分析价格趋势...' : 'Analyzing price trends...'}
          </span>
        </div>
      ) : (
        <div className="grid grid-cols-12 gap-8">
          <div className="col-span-12 md:col-span-3">
            <SummaryStats
              stats={summaryMetrics.stats}
              advancedStats={summaryMetrics.advancedStats}
              t={{ ...t.summary_stats, ...t.advanced_metrics }}
            />
          </div>
          <div className="col-span-12 md:col-span-9">
            <div className="h-[440px] md:h-[460px]">
              <PriceChart
                data={chartData?.data}
                t={t.price_chart}
                locale={lang}
                onWindowDataChange={onWindowChange}
              />
            </div>
          </div>
        </div>
      )}

      {/* HourlyDistributionChart — conditional on config */}
      {modules.includes('HourlyDistributionChart') && (
        <CollapsibleModule
          moduleId="hourly-distribution"
          title={t.hourly_dist?.title || (lang === 'zh' ? '日内分布' : 'Hourly Distribution')}
          metricSummary={lang === 'zh' ? '日内价格分布' : 'Intraday price distribution'}
          lang={lang}
        >
          <DeferredSection fallback={<div className="h-32 flex items-center justify-center text-sm text-[var(--color-muted)]">{lang === 'zh' ? '加载中...' : 'Loading...'}</div>}>
            <Suspense fallback={<div className="h-32 flex items-center justify-center text-sm text-[var(--color-muted)]">{lang === 'zh' ? '加载中...' : 'Loading...'}</div>}>
              <HourlyDistributionChart data={chartData?.hourly_distribution} t={t.hourly_dist} />
            </Suspense>
          </DeferredSection>
        </CollapsibleModule>
      )}
    </FunnelStage>
  );
}
