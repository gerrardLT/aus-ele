/**
 * OpportunityIdentificationStage — Stage 2: 机会识别
 *
 * NEM: PeakAnalysis, FcasAnalysis, ChargingWindow, GridForecast
 * WEM: WemEssAnalysis
 * 每个模块包裹在 CollapsibleModule 中，使用 lazy + Suspense。
 *
 * Requirements: 2.2, 2.4, 5.2, 8.4, 12.3
 */

import { Suspense, lazy } from 'react';
import FunnelStage from '../../components/funnel/FunnelStage';
import CollapsibleModule from '../../components/funnel/CollapsibleModule';
import DeferredSection from '../../components/DeferredSection';
import { useFilters } from '../../contexts/FilterContext';
import { STAGE_DEFINITIONS } from '../../lib/marketConfig';
import { getApiBase } from '../../lib/apiBase';
import { translations } from '../../translations';

const PeakAnalysis = lazy(() => import('../../components/PeakAnalysis'));
const FcasAnalysis = lazy(() => import('../../components/FcasAnalysis'));
const ChargingWindow = lazy(() => import('../../components/ChargingWindow'));
const GridForecast = lazy(() => import('../../components/GridForecast'));
const WemEssAnalysis = lazy(() => import('../../components/wem/WemEssAnalysis'));

const API_BASE = getApiBase();

const MODULE_MAP = {
  PeakAnalysis: { id: 'peak-analysis', titleZh: '峰值分析', titleEn: 'Peak Analysis', summaryZh: '高低价时段识别', summaryEn: 'Peak/off-peak identification' },
  FcasAnalysis: { id: 'fcas-analysis', titleZh: 'FCAS 辅助服务', titleEn: 'FCAS Analysis', summaryZh: '频率控制辅助服务收入', summaryEn: 'Frequency control ancillary services' },
  ChargingWindow: { id: 'charging-window', titleZh: '充电窗口', titleEn: 'Charging Window', summaryZh: '最优充电时段分析', summaryEn: 'Optimal charging window' },
  GridForecast: { id: 'grid-forecast', titleZh: '电网预测', titleEn: 'Grid Forecast', summaryZh: '短期电网状态预测', summaryEn: 'Short-term grid forecast' },
  WemEssAnalysis: { id: 'wem-ess-analysis', titleZh: 'ESS 辅助服务', titleEn: 'ESS Analysis', summaryZh: '必要系统服务分析', summaryEn: 'Essential system services' },
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
    case 'PeakAnalysis':
      return <PeakAnalysis {...props} month={filters.months?.[0] || 'ALL'} quarter={filters.quarter} dayType={filters.dayType} t={{ ...t.peak_analysis, loadingMsg: t.loading_states?.peak }} />;
    case 'FcasAnalysis':
      return <FcasAnalysis {...props} month={filters.months?.[0] || 'ALL'} quarter={filters.quarter} dayType={filters.dayType} t={{ ...t.fcas, ...t.peak_analysis, loadingMsg: t.loading_states?.fcas }} />;
    case 'ChargingWindow':
      return <ChargingWindow {...props} t={{ ...t.charging, ...t.peak_analysis, loadingMsg: t.loading_states?.charging }} />;
    case 'GridForecast':
      return <GridForecast {...props} locale={lang} t={t.forecast} />;
    case 'WemEssAnalysis':
      return <WemEssAnalysis {...props} />;
    default:
      return null;
  }
}

export default function OpportunityIdentificationStage({ config, conclusionData, isLoading, onVisible, lang }) {
  const { filters } = useFilters();
  const stageDef = STAGE_DEFINITIONS[1];
  const modules = config.stages['opportunity-identification'].modules;
  const t = translations[lang] || translations.zh;

  return (
    <FunnelStage
      stageId="opportunity-identification"
      stageNumber={2}
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
          console.warn(`[OpportunityIdentificationStage] Unknown module: ${moduleName}`);
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
