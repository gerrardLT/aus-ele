// web/src/lib/marketConfig.js
// Market configuration for NEM and WEM markets
// Upgraded to array-based stage definitions with module registry

// --- Module Registry ---
// Maps component names to metadata for dynamic loading validation.
// Actual React.lazy imports are handled by ModuleRenderer.

export const MODULE_REGISTRY = {
  // NEM 模块
  PriceChart: { category: 'shared', description: 'Price trend chart' },
  SummaryStats: { category: 'shared', description: 'Summary statistics' },
  RegionalRanking: { category: 'nem', description: 'NEM regional investment ranking' },
  GridForecast: { category: 'nem', description: 'Short-term grid forecast' },
  SpikeProfitAnalysis: { category: 'nem', description: 'Extreme price event profit analysis' },
  PeakAnalysis: { category: 'nem', description: 'Peak period analysis' },
  FcasAnalysis: { category: 'nem', description: 'FCAS market analysis' },
  ChargingWindow: { category: 'nem', description: 'Optimal charging window identification' },
  SaturationTracker: { category: 'shared', description: 'BESS capacity saturation tracker' },
  CoOptimizedBacktest: { category: 'shared', description: 'Co-optimized energy + FCAS backtest' },
  CannibalizationSimulator: { category: 'nem', description: 'Revenue cannibalization simulation' },
  FcasCollapseForecaster: { category: 'nem', description: 'FCAS supply-demand collapse forecast' },
  RegionalTimingScorer: { category: 'nem', description: 'Forward-looking regional timing score' },
  MerchantRiskQuantifier: { category: 'nem', description: 'Monte Carlo merchant risk quantification' },
  InvestmentAnalysis: { category: 'shared', description: 'NPV/IRR investment analysis' },
  CycleCost: { category: 'nem', description: 'Battery cycle cost analysis' },
  ReportPreview: { category: 'nem', description: 'Investment report preview' },
  // 叙事层模块 (Investment Narrative Layer)
  ForwardSpreadCurve: { category: 'shared', description: '20-year forward spread curve with three scenarios' },
  EventAnnotationOverlay: { category: 'shared', description: 'Reusable event annotation overlay for time-series charts' },
  RevenueStratificationChart: { category: 'shared', description: 'Revenue risk stratification stacked area chart' },
  // 投资叙事层模块 (Narrative Layer)
  AssumptionPanel: { category: 'shared', description: 'Model assumption transparency panel' },
  AssetConfigPanel: { category: 'shared', description: 'Asset configuration panel' },
  CrossValidationTable: { category: 'shared', description: 'Multi-source cross-validation table' },
  FuelSensitivityTable: { category: 'shared', description: 'Fuel cost sensitivity analysis table' },
  NetworkImpactDisplay: { category: 'shared', description: 'Network augmentation impact comparison' },
  // WEM 模块
  StemBalancingSpread: { category: 'wem', description: 'STEM vs Balancing spread analysis' },
  CapacityCreditsAnalysis: { category: 'wem', description: 'WEM capacity credits analysis' },
  WemEssAnalysis: { category: 'wem', description: 'WEM ESS market analysis' },
  FiveMinSettlementImpact: { category: 'wem', description: '5-minute settlement impact analysis' },
  WemCsvUploader: { category: 'wem', description: 'WEM CSV data upload/import tool' },
};

// --- Market Configurations ---

export const MARKET_CONFIGS = {
  NEM: {
    id: 'NEM',
    label: '国家电力市场 (NEM)',
    regions: ['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1'],
    dataStartYear: 2020, // 年份按钮按市场数据覆盖过滤（2026-08-13）
    settlementIntervalMinutes: 5,
    timezone: 'Australia/Sydney',
    timezoneLabel: 'AEST',
    currency: 'AUD',
    ancillaryServiceType: 'FCAS',
    ancillaryServices: [
      'raise1sec', 'raise6sec', 'raise60sec', 'raise5min', 'raisereg',
      'lower1sec', 'lower6sec', 'lower60sec', 'lower5min', 'lowerreg',
    ],
    defaultRegion: 'NSW1',
    path: '/',
    stages: [
      {
        id: 'market-screening',
        title: { zh: '市场筛选', en: 'Market Screening' },
        coreQuestion: { zh: '哪个区域最值得深入分析？', en: 'Which region deserves deeper analysis?' },
        modules: [
          { component: 'PriceChart', dataDependencies: ['/api/price-trend'], loadPriority: 1, enabled: true },
          { component: 'SummaryStats', dataDependencies: ['/api/price-trend'], loadPriority: 1, enabled: true },
          { component: 'RegionalRanking', dataDependencies: ['/api/v1/nem/regional-ranking'], loadPriority: 2, enabled: true },
          { component: 'GridForecast', dataDependencies: ['/api/grid-forecast'], loadPriority: 3, enabled: true },
        ],
      },
      {
        id: 'revenue-deep-dive',
        title: { zh: '收入深潜', en: 'Revenue Deep Dive' },
        coreQuestion: { zh: '收入来源的结构和集中度如何？', en: "What's the revenue structure and concentration?" },
        modules: [
          { component: 'SpikeProfitAnalysis', dataDependencies: ['/api/v1/nem/spike-profit'], loadPriority: 1, enabled: true },
          { component: 'PeakAnalysis', dataDependencies: ['/api/peak-analysis'], loadPriority: 2, enabled: true },
          { component: 'FcasAnalysis', dataDependencies: ['/api/fcas-analysis'], loadPriority: 2, enabled: true },
          { component: 'ChargingWindow', dataDependencies: ['/api/peak-analysis'], loadPriority: 3, enabled: true },
        ],
      },
      {
        id: 'saturation-competition',
        title: { zh: '饱和与竞争', en: 'Saturation & Competition' },
        coreQuestion: { zh: '市场饱和风险有多大？', en: 'How significant is market saturation risk?' },
        modules: [
          { component: 'SaturationTracker', dataDependencies: ['/api/v1/saturation'], loadPriority: 1, enabled: true },
        ],
      },
      {
        id: 'investment-outlook',
        title: { zh: '投资前景情景', en: 'Investment Outlook Scenarios' },
        coreQuestion: { zh: '未来投资环境如何变化？', en: 'How will the investment landscape evolve?' },
        modules: [
          { component: 'ForwardSpreadCurve', dataDependencies: ['/api/v1/narrative/forward-spread'], loadPriority: 1, enabled: true },
          { component: 'EventAnnotationOverlay', dataDependencies: ['/api/v1/narrative/events'], loadPriority: 2, enabled: true },
          { component: 'RevenueStratificationChart', dataDependencies: ['/api/v1/narrative/stratification'], loadPriority: 3, enabled: true },
          { component: 'CannibalizationSimulator', dataDependencies: ['/api/v1/outlook/cannibalization'], loadPriority: 4, enabled: true },
          { component: 'FcasCollapseForecaster', dataDependencies: ['/api/v1/outlook/fcas-collapse'], loadPriority: 5, enabled: true },
          { component: 'RegionalTimingScorer', dataDependencies: ['/api/v1/outlook/regional-timing'], loadPriority: 6, enabled: true },
          { component: 'MerchantRiskQuantifier', dataDependencies: ['/api/v1/outlook/merchant-risk'], loadPriority: 7, enabled: true },
        ],
      },
      {
        id: 'co-optimized-backtest',
        title: { zh: '联合优化回测', en: 'Co-Optimized Backtest' },
        coreQuestion: { zh: '联合优化后的真实收入是多少？', en: "What's the real revenue after co-optimization?" },
        modules: [
          { component: 'CoOptimizedBacktest', dataDependencies: ['/api/v1/co-optimization/backtest'], loadPriority: 1, enabled: true },
        ],
      },
      {
        id: 'financial-modeling',
        title: { zh: '财务建模', en: 'Financial Modeling' },
        coreQuestion: { zh: '项目财务指标是否达标？', en: 'Do financial metrics meet thresholds?' },
        modules: [
          { component: 'InvestmentAnalysis', dataDependencies: ['/api/investment-analysis'], loadPriority: 1, enabled: true },
          { component: 'CycleCost', dataDependencies: ['/api/price-trend'], loadPriority: 2, enabled: true },
          { component: 'AssetConfigPanel', dataDependencies: ['/api/v1/narrative/asset-config'], loadPriority: 3, enabled: true },
          { component: 'AssumptionPanel', dataDependencies: ['/api/v1/narrative/asset-config'], loadPriority: 4, enabled: true },
          { component: 'CrossValidationTable', dataDependencies: ['/api/v1/narrative/cross-validation'], loadPriority: 5, enabled: true },
          { component: 'FuelSensitivityTable', dataDependencies: ['/api/v1/narrative/fuel-sensitivity'], loadPriority: 6, enabled: true },
          { component: 'NetworkImpactDisplay', dataDependencies: ['/api/v1/narrative/network-impact'], loadPriority: 7, enabled: true },
        ],
      },
      {
        id: 'investment-decision',
        title: { zh: '投资决策', en: 'Investment Decision' },
        coreQuestion: { zh: '最终投资建议是什么？', en: "What's the final investment recommendation?" },
        modules: [
          { component: 'DecisionTerminal', dataDependencies: ['/api/investment-analysis'], loadPriority: 1, enabled: true },
          { component: 'ScenarioSplit', dataDependencies: ['/api/investment-analysis'], loadPriority: 2, enabled: true },
          { component: 'ReportPreview', dataDependencies: ['/api/reports'], loadPriority: 3, enabled: true },
        ],
      },
    ],
  },
  WEM: {
    id: 'WEM',
    label: '西澳电力市场 (WEM)',
    regions: ['WEM'],
    dataStartYear: 2023, // WEM 数据自 2023 起（2020-2022 无数据，年份按钮需过滤，2026-08-13）
    settlementIntervalMinutes: 30,
    timezone: 'Australia/Perth',
    timezoneLabel: 'AWST',
    currency: 'AUD',
    ancillaryServiceType: 'ESS',
    ancillaryServices: [
      'regulation_raise', 'regulation_lower',
      'contingency_raise', 'contingency_lower',
      'rocof',
    ],
    defaultRegion: 'WEM',
    path: '/wem',
    stages: [
      {
        id: 'market-screening',
        title: { zh: '市场筛选', en: 'Market Screening' },
        coreQuestion: { zh: 'WEM 市场整体机会如何？', en: "What's the overall WEM market opportunity?" },
        modules: [
          { component: 'PriceChart', dataDependencies: ['/api/price-trend'], loadPriority: 1, enabled: true },
          { component: 'SummaryStats', dataDependencies: ['/api/price-trend'], loadPriority: 1, enabled: true },
          { component: 'StemBalancingSpread', dataDependencies: ['/api/v1/wem/stem-balancing'], loadPriority: 2, enabled: true },
          { component: 'WemCsvUploader', dataDependencies: [], loadPriority: 3, enabled: true },
        ],
      },
      {
        id: 'revenue-deep-dive',
        title: { zh: '收入深潜', en: 'Revenue Deep Dive' },
        coreQuestion: { zh: '容量信用和能量市场收入潜力？', en: 'Capacity credit and energy market revenue potential?' },
        modules: [
          { component: 'CapacityCreditsAnalysis', dataDependencies: ['/api/v1/wem/capacity-credits'], loadPriority: 1, enabled: true },
          { component: 'WemEssAnalysis', dataDependencies: ['/api/v1/wem/ess-analysis'], loadPriority: 2, enabled: true },
          { component: 'FiveMinSettlementImpact', dataDependencies: ['/api/v1/wem/five-min-settlement'], loadPriority: 3, enabled: true },
        ],
      },
      {
        id: 'saturation-competition',
        title: { zh: '饱和与竞争', en: 'Saturation & Competition' },
        coreQuestion: { zh: 'WEM 饱和风险和容量信用压力？', en: 'WEM saturation risk and capacity credit pressure?' },
        modules: [
          { component: 'SaturationTracker', dataDependencies: ['/api/v1/saturation'], loadPriority: 1, enabled: true },
        ],
      },
      {
        id: 'co-optimized-backtest',
        title: { zh: '联合优化回测', en: 'Co-Optimized Backtest' },
        coreQuestion: { zh: '联合优化后的 WEM 收入？', en: 'WEM revenue after co-optimization?' },
        modules: [
          { component: 'CoOptimizedBacktest', dataDependencies: ['/api/v1/co-optimization/backtest'], loadPriority: 1, enabled: true },
        ],
      },
      {
        id: 'investment-decision',
        title: { zh: '投资决策', en: 'Investment Decision' },
        coreQuestion: { zh: 'WEM 投资是否可行？', en: 'Is WEM investment viable?' },
        modules: [
          { component: 'InvestmentAnalysis', dataDependencies: ['/api/investment-analysis'], loadPriority: 1, enabled: true },
        ],
      },
    ],
  },
};

// Legacy stage ID mapping for backward compatibility
// Maps old 4-stage IDs to new stage IDs
const LEGACY_STAGE_ID_MAP = {
  'market-opportunity': 'market-screening',
  'opportunity-identification': 'revenue-deep-dive',
  'revenue-estimation': 'financial-modeling',
  // 'investment-decision' is unchanged
};

export function getMarketConfig(marketId) {
  const config = MARKET_CONFIGS[marketId] || MARKET_CONFIGS.NEM;
  // Ensure backward-compatible keyed access on stages array
  // Allows config.stages['stage-id'].modules to return component name strings
  if (!config._stagesIndexed) {
    for (const stage of config.stages) {
      config.stages[stage.id] = {
        modules: stage.modules.filter(m => m.enabled).map(m => m.component),
      };
    }
    // Also register legacy stage IDs pointing to new stages
    for (const [legacyId, newId] of Object.entries(LEGACY_STAGE_ID_MAP)) {
      if (!config.stages[legacyId] && config.stages[newId]) {
        config.stages[legacyId] = config.stages[newId];
      }
    }
    config._stagesIndexed = true;
  }
  return config;
}

// --- Backward Compatibility ---

/**
 * getStageDefinitions(marketId) — 从新数组格式生成阶段定义列表
 * 返回: [{ id, number, title: {zh, en}, coreQuestion: {zh, en} }, ...]
 */
export function getStageDefinitions(marketId = 'NEM') {
  const config = MARKET_CONFIGS[marketId] || MARKET_CONFIGS.NEM;
  return config.stages.map((stage, index) => ({
    id: stage.id,
    number: index + 1,
    title: stage.title,
    coreQuestion: stage.coreQuestion,
  }));
}

// Legacy STAGE_DEFINITIONS — preserves old 4-stage format for existing components
// These will be removed when MarketPage migrates to dynamic rendering (Task 10.1)
export const STAGE_DEFINITIONS = [
  { id: 'market-opportunity', number: 1, title: { zh: '市场机会评估', en: 'Market Opportunity Assessment' }, coreQuestion: { zh: '市场是否存在套利机会？规模多大？', en: 'Is there arbitrage opportunity? How big?' } },
  { id: 'opportunity-identification', number: 2, title: { zh: '机会识别', en: 'Opportunity Identification' }, coreQuestion: { zh: '何时交易？哪些时段？哪些服务？', en: 'When to trade? Which slots? Which services?' } },
  { id: 'revenue-estimation', number: 3, title: { zh: '收入估算', en: 'Revenue Estimation' }, coreQuestion: { zh: '电池能赚多少？扣除成本后呢？', en: 'How much can a battery earn? After costs?' } },
  { id: 'investment-decision', number: 4, title: { zh: '投资决策', en: 'Investment Decision' }, coreQuestion: { zh: '项目是否值得投资？NPV/IRR/回收期？', en: 'Is the project worth investing? NPV/IRR/payback?' } },
];

export const STAGE_IDS = STAGE_DEFINITIONS.map(s => s.id);

// --- Default BESS Parameters ---

export const DEFAULT_BESS_PARAMS = {
  power_mw: 100,
  duration_hours: 4,
  round_trip_efficiency: 0.87,
  variable_om_per_mwh: 2.5,
};

// --- Helper Functions ---

export function buildSectionLinks(lang, marketId) {
  const stages = marketId ? getStageDefinitions(marketId) : STAGE_DEFINITIONS;
  return [
    ...stages.map(s => ({ id: s.id, label: s.title[lang] || s.title.zh })),
  ];
}

/**
 * getStageById(marketId, stageId) — 按 ID 查找阶段定义
 * 返回完整的阶段对象（含 modules 数组），未找到时返回 undefined。
 */
export function getStageById(marketId, stageId) {
  const config = getMarketConfig(marketId);
  return config.stages.find(s => s.id === stageId);
}

/**
 * getStageModules(marketId, stageId) — 获取指定阶段的模块组件名称列表
 * 仅返回 enabled: true 的模块，按 loadPriority 排序。
 * 兼容旧代码中 config.stages[stageId].modules 的使用模式。
 */
export function getStageModules(marketId, stageId) {
  const stage = getStageById(marketId, stageId);
  if (!stage) return [];
  return stage.modules
    .filter(m => m.enabled)
    .sort((a, b) => a.loadPriority - b.loadPriority)
    .map(m => m.component);
}
