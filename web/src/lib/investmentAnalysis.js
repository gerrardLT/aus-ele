const DEFAULT_INVESTMENT_COPY = {
  en: {
    title: 'Investment Analysis',
    subtitle: 'Conservative cash-flow view using an optimized hindsight arbitrage upper bound with capture-rate haircut.',
    eyebrow: 'BESS Cash Flow Model',
    parameters: 'Parameters',
    runAnalysis: 'Run Analysis',
    running: 'Running...',
    fcasRevenueMode: 'FCAS Revenue Mode',
    modeAuto: 'Auto',
    modeManual: 'Manual',
    modeHelpAuto: 'Auto mode uses NEM historical FCAS when available. WEM falls back to manual.',
    modeHelpManual: 'Manual mode uses the entered FCAS revenue per MW-year.',
    groups: {
      storage: 'Storage',
      cost: 'Cost',
      finance: 'Finance',
    },
    fields: {
      power_mw: 'Power',
      duration_hours: 'Duration',
      degradation_rate: 'Degradation',
      revenue_capture_rate: 'Capture Rate',
      capex_per_kwh: 'CAPEX',
      fixed_om_per_mw_year: 'Fixed O&M',
      variable_om_per_mwh: 'Variable O&M',
      grid_connection_cost: 'Grid Connect',
      land_lease_per_year: 'Land Lease',
      discount_rate: 'Discount Rate',
      project_life_years: 'Project Life',
      fcas_revenue_per_mw_year: 'Manual FCAS',
      capacity_payment_per_mw_year: 'Capacity Payment',
    },
    capexSummary: 'Total CAPEX',
    sizeSummary: 'Size',
    assumptions: 'Assumptions',
    backtestResults: 'Backtest Results',
    implementableBaseline: 'Implementable Baseline',
    captureRate: 'Capture rate',
    revenueBreakdown: 'Revenue Breakdown (Year 1)',
    totalPerYear: 'Total',
    perYear: '/yr',
    cashFlowProjection: 'Cash Flow Projection',
    annualCashFlows: 'Annual Cash Flows',
    revenue: 'Revenue',
    opex: 'OpEx',
    cumulative: 'Cumulative',
    year: 'Year',
    net: 'Net',
    degradationFactor: 'Deg. Factor',
    kpis: {
      npv: 'NPV',
      irr: 'IRR',
      payback: 'Payback',
      baselinePerMw: 'Baseline / MW',
      discount: 'Discount',
      postTaxNotModeled: 'Post-tax not modeled',
      projectLife: 'Project life',
      arbitrage: 'Arbitrage',
      overLife: '> life',
      yearSuffix: 'yr',
      perMwPerYear: '/MW/yr',
      uiYear: 'UI Year',
      backtestMode: 'Backtest Mode',
      effectiveDegradation: 'Effective Degradation',
      fcasSource: 'FCAS Source',
      fcasMode: 'FCAS Mode',
      tradingDays: 'trading days',
    },
    revenueLabels: {
      arbitrage: 'Arbitrage',
      fcas: 'FCAS',
      capacity: 'Capacity',
    },
    lazyVisible: 'The full investment model loads only when this section enters view. After editing parameters, use Run Analysis to refresh it.',
    lazyHidden: 'The investment model now loads lazily, so changing top-level filters no longer triggers the heaviest request immediately.',
  },
  zh: {
    title: '投资分析',
    subtitle: '基于优化回看套利上限并叠加 capture rate 折减的保守现金流视图。',
    eyebrow: '储能现金流模型',
    parameters: '参数设置',
    runAnalysis: '运行分析',
    running: '分析中...',
    fcasRevenueMode: 'FCAS 收入口径',
    modeAuto: '自动',
    modeManual: '手动',
    modeHelpAuto: '自动模式会在 NEM 可用时使用历史 FCAS 基线；WEM 会回退到手动模式。',
    modeHelpManual: '手动模式直接使用输入的每 MW 年化 FCAS 收入。',
    groups: {
      storage: '储能参数',
      cost: '成本参数',
      finance: '财务参数',
    },
    fields: {
      power_mw: '功率',
      duration_hours: '时长',
      degradation_rate: '退化率',
      revenue_capture_rate: '实现率',
      capex_per_kwh: 'CAPEX',
      fixed_om_per_mw_year: '固定运维',
      variable_om_per_mwh: '可变运维',
      grid_connection_cost: '并网成本',
      land_lease_per_year: '土地租赁',
      discount_rate: '折现率',
      project_life_years: '项目寿命',
      fcas_revenue_per_mw_year: '手动 FCAS',
      capacity_payment_per_mw_year: '容量补偿',
    },
    capexSummary: '总 CAPEX',
    sizeSummary: '项目规模',
    assumptions: '模型假设',
    backtestResults: '回测结果',
    implementableBaseline: '可实现基线',
    captureRate: '实现率',
    revenueBreakdown: '收入拆分（第 1 年）',
    totalPerYear: '合计',
    perYear: '/年',
    cashFlowProjection: '现金流预测',
    annualCashFlows: '年度现金流',
    revenue: '收入',
    opex: '运维',
    cumulative: '累计',
    year: '年份',
    net: '净额',
    degradationFactor: '退化系数',
    kpis: {
      npv: 'NPV',
      irr: 'IRR',
      payback: '回本期',
      baselinePerMw: '基线 / MW',
      discount: '折现',
      postTaxNotModeled: '未纳入税后口径',
      projectLife: '项目寿命',
      arbitrage: '套利',
      overLife: '> 寿命期',
      yearSuffix: '年',
      perMwPerYear: '/MW/年',
      uiYear: '界面年份',
      backtestMode: '回测模式',
      effectiveDegradation: '有效退化率',
      fcasSource: 'FCAS 来源',
      fcasMode: 'FCAS 模式',
      tradingDays: '交易日',
    },
    revenueLabels: {
      arbitrage: '套利',
      fcas: 'FCAS',
      capacity: '容量',
    },
    lazyVisible: '只有滚动到本模块后才会加载完整投资模型；修改参数后，请点击“运行分析”重新计算。',
    lazyHidden: '投资模型已改为懒加载，因此顶部筛选变化不会立刻触发这类最重的请求。',
  },
};

export function getInvestmentCopy(lang = 'en', overrides = {}) {
  const locale = lang === 'zh' ? 'zh' : 'en';
  return {
    ...DEFAULT_INVESTMENT_COPY[locale],
    ...(overrides || {}),
    groups: {
      ...DEFAULT_INVESTMENT_COPY[locale].groups,
      ...(overrides?.groups || {}),
    },
    fields: {
      ...DEFAULT_INVESTMENT_COPY[locale].fields,
      ...(overrides?.fields || {}),
    },
    kpis: {
      ...DEFAULT_INVESTMENT_COPY[locale].kpis,
      ...(overrides?.kpis || {}),
    },
    revenueLabels: {
      ...DEFAULT_INVESTMENT_COPY[locale].revenueLabels,
      ...(overrides?.revenueLabels || {}),
    },
  };
}

export function buildInvestmentRequestKey(region) {
  return region || '';
}

export function formatPercentageValue(value, decimals = 2) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return '-';
  }

  return `${Number(value).toFixed(decimals)}%`;
}

export function shouldAutoRunInvestment({
  isVisible,
  isLoading,
  requestKey,
  loadedKey,
}) {
  return Boolean(isVisible && !isLoading && requestKey && requestKey !== loadedKey);
}
