/**
 * RevenueEstimationStage — Stage 3: 收入估算
 *
 * NEM: BessSimulator, RevenueStacking, CycleCost
 * WEM: WemCapacityAnalysis
 * 每个模块包裹在 CollapsibleModule 中。
 *
 * Requirements: 2.2, 5.2, 8.4
 */

import { Suspense, lazy } from 'react';
import FunnelStage from '../../components/funnel/FunnelStage';
import CollapsibleModule from '../../components/funnel/CollapsibleModule';
import DeferredSection from '../../components/DeferredSection';
import { useFilters } from '../../contexts/FilterContext';
import { STAGE_DEFINITIONS } from '../../lib/marketConfig';
import { getApiBase } from '../../lib/apiBase';
import { translations } from '../../translations';

const BessSimulator = lazy(() => import('../../components/BessSimulator'));
const RevenueStacking = lazy(() => import('../../components/RevenueStacking'));
const CycleCost = lazy(() => import('../../components/CycleCost'));
const WemCapacityAnalysis = lazy(() => import('../../components/wem/WemCapacityAnalysis'));

const API_BASE = getApiBase();

const MODULE_MAP = {
  BessSimulator: { id: 'bess-simulator', titleZh: 'BESS 模拟器', titleEn: 'BESS Simulator', summaryZh: '储能套利回测模拟', summaryEn: 'Battery arbitrage backtest' },
  RevenueStacking: { id: 'revenue-stacking', titleZh: '收入叠加', titleEn: 'Revenue Stacking', summaryZh: '多收入流叠加分析', summaryEn: 'Multi-stream revenue stacking' },
  CycleCost: { id: 'cycle-cost', titleZh: '循环成本', titleEn: 'Cycle Cost', summaryZh: '电池循环降解成本', summaryEn: 'Battery cycle degradation cost' },
  WemCapacityAnalysis: { id: 'wem-capacity-analysis', titleZh: '容量分析', titleEn: 'Capacity Analysis', summaryZh: 'WEM 容量市场分析', summaryEn: 'WEM capacity market analysis' },
};

function LoadingFallback({ lang }) {
  return (
    <div className="h-32 flex items-center justify-center text-sm text-[var(--color-muted)]">
      {lang === 'zh' ? '正在加载模块...' : 'Loading module...'}
    </div>
  );
}

function renderModule(moduleName, filters, lang, t) {
  const props = { year: filters.year, region: filters.region, lang, apiBase: API_BASE };

  switch (moduleName) {
    case 'BessSimulator':
      return <BessSimulator {...props} t={{ ...t.simulator, loadingMsg: t.loading_states?.simulator }} />;
    case 'RevenueStacking':
      return <RevenueStacking {...props} month={filters.months?.[0] || 'ALL'} quarter={filters.quarter} dayType={filters.dayType} t={{ ...t.stacking, ...t.peak_analysis, loadingMsg: t.loading_states?.stacking }} />;
    case 'CycleCost':
      return <CycleCost {...props} month={filters.months?.[0] || 'ALL'} quarter={filters.quarter} dayType={filters.dayType} t={{ ...t.cycleCost, ...t.peak_analysis, loadingMsg: t.loading_states?.cycleCost }} />;
    case 'WemCapacityAnalysis':
      return <WemCapacityAnalysis {...props} />;
    default:
      return null;
  }
}

export default function RevenueEstimationStage({ config, conclusionData, isLoading, onVisible, lang }) {
  const { filters } = useFilters();
  const stageDef = STAGE_DEFINITIONS[2];
  const modules = config.stages['revenue-estimation'].modules;
  const t = translations[lang] || translations.zh;

  return (
    <FunnelStage
      stageId="revenue-estimation"
      stageNumber={3}
      title={stageDef.title[lang]}
      coreQuestion={stageDef.coreQuestion[lang]}
      conclusionData={conclusionData}
      isLoading={isLoading}
      onVisible={onVisible}
      lang={lang}
    >
      {modules.map(moduleName => {
        const meta = MODULE_MAP[moduleName];
        if (!meta) {
          console.warn(`[RevenueEstimationStage] Unknown module: ${moduleName}`);
          return null;
        }
        return (
          <CollapsibleModule
            key={meta.id}
            moduleId={meta.id}
            title={lang === 'zh' ? meta.titleZh : meta.titleEn}
            metricSummary={lang === 'zh' ? meta.summaryZh : meta.summaryEn}
            defaultExpanded={moduleName === modules[0]}
            lang={lang}
          >
            <DeferredSection fallback={<LoadingFallback lang={lang} />}>
              <Suspense fallback={<LoadingFallback lang={lang} />}>
                {renderModule(moduleName, filters, lang, t)}
              </Suspense>
            </DeferredSection>
          </CollapsibleModule>
        );
      })}
    </FunnelStage>
  );
}
