/**
 * ModuleRenderer — 动态模块加载器
 *
 * 使用 React.lazy + Suspense 按组件名称动态加载模块。
 * 如果组件不存在于 MODULE_REGISTRY，跳过渲染并在控制台记录警告。
 * 如果组件加载/渲染失败，ErrorBoundary 捕获错误并跳过渲染。
 *
 * Requirements: 11.3, 11.5
 */

import { lazy, Suspense, Component } from 'react';
import { useFilters } from '../../contexts/FilterContext';
import { getApiBase } from '../../lib/apiBase';
import { translations } from '../../translations';

// --- Module Registry ---
// Maps component names to React.lazy dynamic imports.
const MODULE_REGISTRY = {
  // 新增模块 (7 个)
  SpikeProfitAnalysis: lazy(() => import('../modules/SpikeProfitAnalysis')),
  SaturationTracker: lazy(() => import('../modules/SaturationTracker')),
  RegionalRanking: lazy(() => import('../modules/RegionalRanking')),
  CoOptimizedBacktest: lazy(() => import('../modules/CoOptimizedBacktest')),
  CapacityCreditsAnalysis: lazy(() => import('../modules/CapacityCreditsAnalysis')),
  StemBalancingSpread: lazy(() => import('../modules/StemBalancingSpread')),
  FiveMinSettlementImpact: lazy(() => import('../modules/FiveMinSettlementImpact')),
  // 投资前景情景分析模块 (4 个)
  CannibalizationSimulator: lazy(() => import('../modules/CannibalizationSimulator')),
  FcasCollapseForecaster: lazy(() => import('../modules/FcasCollapseForecaster')),
  RegionalTimingScorer: lazy(() => import('../modules/RegionalTimingScorer')),
  MerchantRiskQuantifier: lazy(() => import('../modules/MerchantRiskQuantifier')),
  // 叙事层模块 (Investment Narrative Layer)
  ForwardSpreadCurve: lazy(() => import('../modules/ForwardSpreadCurve')),
  EventAnnotationOverlay: lazy(() => import('../modules/EventAnnotationOverlay')),
  RevenueStratificationChart: lazy(() => import('../modules/RevenueStratificationChart')),
  // 现有模块（全部保留）
  PriceChart: lazy(() => import('../modules/PriceChartModule')),
  SummaryStats: lazy(() => import('../modules/SummaryStatsModule')),
  // 投资叙事层模块 (Narrative Layer)
  AssumptionPanel: lazy(() => import('../modules/AssumptionPanel')),
  AssetConfigPanel: lazy(() => import('../modules/AssetConfigPanel')),
  CrossValidationTable: lazy(() => import('../modules/CrossValidationTable')),
  FuelSensitivityTable: lazy(() => import('../modules/FuelSensitivityTable')),
  NetworkImpactDisplay: lazy(() => import('../modules/NetworkImpactDisplay')),
  PeakAnalysis: lazy(() => import('../PeakAnalysis')),
  FcasAnalysis: lazy(() => import('../FcasAnalysis')),
  ChargingWindow: lazy(() => import('../ChargingWindow')),
  GridForecast: lazy(() => import('../GridForecast')),
  InvestmentAnalysis: lazy(() => import('../InvestmentAnalysis')),
  CycleCost: lazy(() => import('../CycleCost')),
  ReportPreview: lazy(() => import('../ReportPreview')),
  WemEssAnalysis: lazy(() => import('../wem/WemEssAnalysis')),
};

// --- ErrorBoundary ---
// Catches render errors in lazy-loaded modules and returns null.
class ModuleErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false };
  }

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error, errorInfo) {
    console.warn(
      `[ModuleRenderer] Module "${this.props.moduleName}" failed to render:`,
      error,
      errorInfo,
    );
  }

  render() {
    if (this.state.hasError) {
      return null;
    }
    return this.props.children;
  }
}

// --- ModuleLoadingSkeleton ---
// Animated pulse placeholder shown while a module is loading.
export function ModuleLoadingSkeleton() {
  return (
    <div className="module-loading-skeleton" aria-busy="true" aria-label="Loading module">
      <div className="skeleton-pulse" style={{
        height: '120px',
        borderRadius: '8px',
        background: 'linear-gradient(90deg, #f0f0f0 25%, #e0e0e0 50%, #f0f0f0 75%)',
        backgroundSize: '200% 100%',
        animation: 'skeleton-shimmer 1.5s infinite',
      }} />
      <style>{`
        @keyframes skeleton-shimmer {
          0% { background-position: 200% 0; }
          100% { background-position: -200% 0; }
        }
      `}</style>
    </div>
  );
}

// --- ModuleRenderer ---
export default function ModuleRenderer({ moduleEntry, config, lang }) {
  const ComponentLazy = MODULE_REGISTRY[moduleEntry.component];
  const { filters } = useFilters();
  const apiBase = getApiBase();
  const t = translations[lang] || translations.zh;

  if (!ComponentLazy) {
    console.warn(
      `[ModuleRenderer] Module component "${moduleEntry.component}" not found in registry, skipping.`,
    );
    return null;
  }

  // Build props bridge for legacy components that expect specific props
  const baseProps = {
    config,
    lang,
    year: filters.year,
    region: filters.region,
    apiBase,
  };

  // Legacy component prop mapping — these components expect `t` sub-objects and filter props
  const legacyPropsMap = {
    PriceChart: { t: t.price_chart },
    SummaryStats: { t: { ...t.summary_stats, ...t.advanced_metrics } },
    PeakAnalysis: { t: { ...t.peak_analysis, loadingMsg: t.loading_states?.peak }, month: filters.months?.[0] || 'ALL', quarter: filters.quarter, dayType: filters.dayType, regimeCompactCopy: t.regime_compact },
    FcasAnalysis: { t: { ...t.fcas, ...t.peak_analysis, loadingMsg: t.loading_states?.fcas }, month: filters.months?.[0] || 'ALL', quarter: filters.quarter, dayType: filters.dayType, regimeCompactCopy: t.regime_compact },
    ChargingWindow: { t: { ...t.charging, ...t.peak_analysis, loadingMsg: t.loading_states?.charging }, regimeCompactCopy: t.regime_compact },
    GridForecast: { locale: lang, t: t.forecast, regimeCompactCopy: t.regime_compact },
    InvestmentAnalysis: { t, showDecisionPanel: false, regimeCompactCopy: t.regime_compact },
    CycleCost: { t: { ...t.cycleCost, ...t.peak_analysis, loadingMsg: t.loading_states?.cycleCost }, month: filters.months?.[0] || 'ALL', quarter: filters.quarter, dayType: filters.dayType, regimeCompactCopy: t.regime_compact },
    ReportPreview: { t: t.reportPreview || { title: lang === 'zh' ? '报告预览' : 'Report Preview' }, month: filters.months?.[0] || 'ALL' },
    WemEssAnalysis: {},
  };

  const extraProps = legacyPropsMap[moduleEntry.component] || {};

  return (
    <ModuleErrorBoundary moduleName={moduleEntry.component}>
      <Suspense fallback={<ModuleLoadingSkeleton />}>
        <ComponentLazy {...baseProps} {...extraProps} />
      </Suspense>
    </ModuleErrorBoundary>
  );
}
