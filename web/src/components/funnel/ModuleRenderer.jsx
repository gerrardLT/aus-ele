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
  WemCsvUploader: lazy(() => import('../wem/WemCsvUploader')),
  // U3: Decision Terminal
  DecisionTerminal: lazy(() => import('../modules/DecisionTerminal')),
  // U5: What-if Scenario Split
  ScenarioSplit: lazy(() => import('../modules/ScenarioSplit')),
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

// --- Module Loading Copy (S6/F1) ---
// Per-module loading messages shown during Suspense fallback.
const MODULE_LOADING_COPY = {
  InvestmentAnalysis: { zh: '正在求解 20 年现金流与蒙特卡洛分布…（首次约 30-60 秒）', en: 'Solving 20-year cash flows & Monte Carlo… (first run ~30-60s)', variant: 'compute' },
  CoOptimizedBacktest: { zh: '正在运行能量+FCAS 联合优化 MILP…', en: 'Running energy+FCAS joint MILP optimization…', variant: 'compute' },
  CannibalizationSimulator: { zh: '正在模拟容量增长蚕食效应…', en: 'Simulating capacity growth cannibalization…', variant: 'compute' },
  MerchantRiskQuantifier: { zh: '正在运行蒙特卡洛风险量化…', en: 'Running Monte Carlo risk quantification…', variant: 'compute' },
  SpikeProfitAnalysis: { zh: '正在分析极端价格事件…', en: 'Analyzing extreme price events…', variant: 'chart' },
  RegionalRanking: { zh: '正在计算区域投资排名…', en: 'Computing regional investment ranking…', variant: 'chart' },
};

// --- ModuleLoadingSkeleton ---
// Animated pulse placeholder shown while a module is loading.
// S6/F1: accepts `label` and `variant` ('chart' | 'compute') for contextual copy.
export function ModuleLoadingSkeleton({ label, variant = 'chart' }) {
  return (
    <div className="module-loading-skeleton" aria-busy="true" aria-label={label || 'Loading module'}>
      {label && (
        <p style={{
          fontSize: '13px',
          color: '#666',
          marginBottom: '8px',
          display: 'flex',
          alignItems: 'center',
          gap: '6px',
        }}>
          {variant === 'compute' && <span aria-hidden="true">⚙️</span>}
          {label}
        </p>
      )}
      <div className="skeleton-pulse" style={{
        height: variant === 'compute' ? '80px' : '120px',
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
    WemCsvUploader: {},
  };

  const extraProps = legacyPropsMap[moduleEntry.component] || {};

  return (
    <ModuleErrorBoundary moduleName={moduleEntry.component}>
      <Suspense fallback={
        <ModuleLoadingSkeleton
          label={MODULE_LOADING_COPY[moduleEntry.component]?.[lang] || MODULE_LOADING_COPY[moduleEntry.component]?.zh}
          variant={MODULE_LOADING_COPY[moduleEntry.component]?.variant || 'chart'}
        />
      }>
        <ComponentLazy {...baseProps} {...extraProps} />
      </Suspense>
    </ModuleErrorBoundary>
  );
}
