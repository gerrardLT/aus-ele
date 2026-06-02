/**
 * InvestmentDecisionStage — Stage 4: 投资决策
 *
 * 渲染 InvestmentAnalysis + ReportPreview（NEM）或仅 InvestmentAnalysis（WEM）。
 * 每个模块包裹在 CollapsibleModule 中。
 *
 * Requirements: 2.2, 5.2, 8.4
 */

import { Suspense, lazy } from 'react';
import FunnelStage from '../../components/funnel/FunnelStage';
import CollapsibleModule from '../../components/funnel/CollapsibleModule';
import DeferredSection from '../../components/DeferredSection';
import { useFilters } from '../../contexts/FilterContext';
import { getApiBase } from '../../lib/apiBase';
import { translations } from '../../translations';

const InvestmentAnalysis = lazy(() => import('../../components/InvestmentAnalysis'));
const ReportPreview = lazy(() => import('../../components/ReportPreview'));

const API_BASE = getApiBase();

const MODULE_MAP = {
  InvestmentAnalysis: { id: 'investment-analysis', titleZh: '投资分析', titleEn: 'Investment Analysis', summaryZh: 'NPV / IRR / 回收期', summaryEn: 'NPV / IRR / Payback' },
  ReportPreview: { id: 'report-preview', titleZh: '报告预览', titleEn: 'Report Preview', summaryZh: '投资备忘录与报告', summaryEn: 'Investment memo & reports' },
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
    case 'InvestmentAnalysis':
      return <InvestmentAnalysis {...props} t={t} showDecisionPanel={false} />;
    case 'ReportPreview':
      return <ReportPreview {...props} month={filters.months?.[0] || 'ALL'} t={t.reportPreview || { title: lang === 'zh' ? '报告预览' : 'Report Preview' }} />;
    default:
      return null;
  }
}

export default function InvestmentDecisionStage({ config, conclusionData, isLoading, onVisible, lang }) {
  const { filters } = useFilters();
  const stageConfig = config.stages?.find?.((s) => s.id === 'investment-decision') || config.stages?.['investment-decision'];
  const stageDef = stageConfig || { title: { zh: '投资决策', en: 'Investment Decision' }, coreQuestion: { zh: '最终投资建议是什么？', en: "What's the final investment recommendation?" } };
  const modules = Array.isArray(stageConfig?.modules)
    ? stageConfig.modules.map((m) => typeof m === 'string' ? m : m.component)
    : (config.stages?.['investment-decision']?.modules || ['InvestmentAnalysis', 'ReportPreview']);
  const t = translations[lang] || translations.zh;

  return (
    <FunnelStage
      stageId="investment-decision"
      stageNumber={4}
      title={stageDef.title?.[lang] || stageDef.title?.zh || 'Investment Decision'}
      coreQuestion={stageDef.coreQuestion?.[lang] || stageDef.coreQuestion?.zh || ''}
      conclusionData={conclusionData}
      isLoading={isLoading}
      onVisible={onVisible}
      lang={lang}
    >
      {modules.map(moduleName => {
        const meta = MODULE_MAP[moduleName];
        if (!meta) {
          console.warn(`[InvestmentDecisionStage] Unknown module: ${moduleName}`);
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
