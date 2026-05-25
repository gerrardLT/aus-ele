export function buildP3DecisionUrl(apiBase) {
  return `${apiBase}/p3/bess/decision-layer`;
}

export function formatDecisionActionLabel(action = '', locale = 'en') {
  const isZh = locale === 'zh';
  if (action === 'forecast_driven_dispatch') {
    return isZh ? '展望支持的进入判断' : 'Outlook-backed entry case';
  }
  if (action === 'rule_based_dispatch') {
    return isZh ? '保守回退判断' : 'Conservative fallback case';
  }
  return action || (isZh ? '暂无' : 'n/a');
}

export function formatDecisionCalibrationGrade(grade = '', locale = 'en') {
  const isZh = locale === 'zh';
  const labels = {
    strong: isZh ? '校准较强' : 'Well calibrated',
    mixed: isZh ? '可用但需谨慎' : 'Usable with caution',
    poor: isZh ? '校准偏弱' : 'Calibration is weak',
    unknown: isZh ? '暂无校准结论' : 'Calibration unclear',
  };
  return labels[grade] || grade || labels.unknown;
}

export function formatDecisionErrorGrade(grade = '', locale = 'en') {
  const isZh = locale === 'zh';
  const labels = {
    low_error: isZh ? '误差较低' : 'Low forecast error',
    moderate_error: isZh ? '误差处于常规范围' : 'Normal forecast error',
    high_error: isZh ? '误差偏高' : 'Error is elevated',
    unknown: isZh ? '暂无误差结论' : 'Error level unclear',
  };
  return labels[grade] || grade || labels.unknown;
}

export function formatDecisionUsageScope(scope = '', locale = 'en') {
  const isZh = locale === 'zh';
  const labels = {
    'decision-grade': isZh ? '可用于投资判断参考' : 'Suitable for investment review',
    'preview/core-only': isZh ? '适合方向判断' : 'Best for directional review',
  };
  return labels[scope] || scope || (isZh ? '暂无' : 'n/a');
}

export function normalizeP3DecisionPayload(payload = {}) {
  return {
    market: payload.market || '',
    region: payload.region || '',
    year: payload.year ?? null,
    forecastContext: payload.forecast_context || {},
    decisionSummary: payload.decision_summary || {},
    recommendationSummary: (payload.decision_summary || {}).recommendation_summary || {},
    explanationChain: (payload.decision_summary || {}).explanation_chain || [],
    riskBoundary: (payload.decision_summary || {}).risk_boundary || {},
    strategyBundle: payload.strategy_bundle || {},
    revenueAttribution: payload.revenue_attribution || {},
    sourceBacktest: payload.source_backtest || {},
    governance: payload.governance || null,
    warnings: payload.warnings || [],
    metadata: payload.metadata || {},
    marketDesignContext: payload.market_design_context || (payload.decision_summary || {}).market_design_context || '',
    valueStreamCoverage: payload.value_stream_coverage || (payload.decision_summary || {}).value_stream_coverage || [],
    capacityRevenueInScope: payload.capacity_revenue_in_scope ?? (payload.decision_summary || {}).capacity_revenue_in_scope ?? null,
    benchmarkFamily: payload.benchmark_family || (payload.decision_summary || {}).benchmark_family || '',
    readinessStatus: payload.readiness_status || (payload.decision_summary || {}).readiness_status || '',
    conclusionScope: payload.conclusion_scope || (payload.decision_summary || {}).conclusion_scope || '',
    coverageMode: payload.coverage_mode || '',
    regulatoryScope: payload.regulatory_scope || '',
    resultType: payload.result_type || '',
  };
}

export function getP3DecisionCopy(locale = 'en') {
  if (locale === 'zh') {
    return {
      title: '市场进入判断',
      subtitle: '把当前市场、市场展望和收益来源整理成面向项目判断的结果。',
      recommended: '判断结论',
      riskMode: '风险模式',
      reserveSoc: '保留电量',
      rollingMode: '滚动模式',
      strategyBundle: '策略包',
      revenueAttribution: '收入归因',
      forecastDriven: '预测驱动',
      ruleBased: '规则基线',
      stochastic: '随机场景',
      netRevenue: '净收益',
      scenarioSpread: '场景价差',
      timingAlpha: '择时增益',
      regimeAlpha: '市场状态增益',
      fcasProxy: 'FCAS 机会收益',
      degradationPenalty: '退化保守罚项',
      grossEnergy: '毛能量收益',
      degradationCost: '退化成本',
      primaryRegime: '主导状态',
      calibrationGrade: '校准等级',
      errorGrade: '误差等级',
      backtestSummary: '回测摘要',
      timelinePoints: '轨迹点数',
      equivalentCycles: '等效循环',
      socStart: '起始 SoC',
      socEnd: '结束 SoC',
      governance: '数据状态',
      freshness: '新鲜度',
      drift: '漂移',
      disclaimer: '适用范围',
      lineage: '追溯',
      recommendationSummary: '结果摘要',
      decisionHeadline: '核心判断',
      decisionWhy: '为什么这样看',
      decisionEconomics: '收益与风险范围',
      decisionDiagnostics: '更多细节',
      explanationChain: '判断过程',
      riskBoundary: '风险范围',
      currentMarketStep: '当前市场',
      outlookStep: '市场展望',
      decisionStep: '进入判断',
      expectedRange: '预期区间',
      downsideCase: '下行场景',
      upsideCase: '上行场景',
      marketDesignContext: '市场机制',
      valueStreamCoverage: '覆盖收益来源',
      capacityRevenueInScope: '是否含容量收益',
      benchmarkFamily: '模型版本',
      readinessStatus: '进入准备度',
      conclusionScope: '适用边界',
      coverageMode: '覆盖情况',
      regulatoryScope: '市场范围',
      resultType: '结果分类',
      warnings: '提示',
      notAvailable: '暂无',
    };
  }

  return {
    title: 'Market Entry View',
    subtitle: 'Brings current market conditions, outlook, and revenue drivers together for the selected market.',
    recommended: 'Conclusion',
    riskMode: 'Risk Mode',
    reserveSoc: 'Reserve SoC',
    rollingMode: 'Rolling Mode',
    strategyBundle: 'Strategy Bundle',
    revenueAttribution: 'Revenue Attribution',
    forecastDriven: 'Forecast-driven',
    ruleBased: 'Rule-based',
    stochastic: 'Stochastic',
    netRevenue: 'Net Revenue',
    scenarioSpread: 'Scenario Spread',
    timingAlpha: 'Timing Alpha',
    regimeAlpha: 'Market-State Alpha',
    fcasProxy: 'FCAS Revenue Signal',
    degradationPenalty: 'Degradation Penalty',
    grossEnergy: 'Gross Energy',
    degradationCost: 'Degradation Cost',
    primaryRegime: 'Primary Regime',
    calibrationGrade: 'Calibration Grade',
    errorGrade: 'Error Grade',
    backtestSummary: 'Backtest Summary',
    timelinePoints: 'Timeline Points',
    equivalentCycles: 'Equivalent Cycles',
    socStart: 'Start SoC',
    socEnd: 'End SoC',
    governance: 'Data Status',
    freshness: 'Freshness',
    drift: 'Drift',
    disclaimer: 'Use Case',
    lineage: 'Lineage',
    recommendationSummary: 'Summary',
    decisionHeadline: 'Core View',
    decisionWhy: 'Why This View',
    decisionEconomics: 'Returns And Risk Range',
    decisionDiagnostics: 'More Detail',
    explanationChain: 'How We Got Here',
    riskBoundary: 'Risk Range',
    currentMarketStep: 'Current Market',
    outlookStep: 'Market Outlook',
    decisionStep: 'Entry View',
    expectedRange: 'Expected Range',
    downsideCase: 'Downside Case',
    upsideCase: 'Upside Case',
    marketDesignContext: 'Market Setup',
    valueStreamCoverage: 'Covered Revenue Streams',
    capacityRevenueInScope: 'Includes Capacity Revenue',
    benchmarkFamily: 'Model Version',
    readinessStatus: 'Entry Readiness',
    conclusionScope: 'Where To Use It',
    coverageMode: 'Coverage',
    regulatoryScope: 'Market Scope',
    resultType: 'Result Type',
    warnings: 'Warnings',
    notAvailable: 'n/a',
  };
}
