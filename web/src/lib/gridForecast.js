const FORECAST_COPY = {
  en: {
    section: {
      sectionLabel: 'Grid Forecast',
      title: 'Australian Grid Forecast',
      subtitle: 'Forward-looking risk and opportunity forecast using official market and event signals.',
      signalDesk: 'Signal Desk',
      marketContext: 'Market Context',
      horizon24h: '24h',
      horizon7d: '7d',
      horizon30d: '30d',
      horizonNotes: {
        '24h': '24h mode is predispatch-led and highlights the next actionable charge and discharge windows.',
        '7d': '7d mode switches to a daily regime outlook instead of pretending to be a point-by-point price forecast.',
        '30d': '30d mode shows a structural outlook band for market regime and system pressure, not precise price points.',
      },
    },
    coverage: {
      full: 'full coverage',
      partial: 'partial coverage',
      core_only: 'core-only coverage',
      none: 'no verified coverage',
    },
    confidence: {
      high: 'high confidence',
      medium: 'medium confidence',
      low: 'low confidence',
      none: 'confidence unknown',
    },
    forecastModes: {
      hybrid_signal_calibrated: 'Predispatch-led hybrid',
      daily_regime_outlook: 'Daily regime outlook',
      structural_regime_outlook: 'Structural regime outlook',
    },
    severity: {
      high: 'high',
      medium: 'medium',
      low: 'low',
    },
    statuses: {
      ok: 'ready',
      missing: 'missing',
      partial: 'partial',
      stale: 'stale',
    },
    sources: {
      recent_market_history: 'Recent market history',
      event_state: 'Event state layer',
      nem_predispatch: 'NEM predispatch',
      wem_ess_slim: 'WEM ESS slim',
    },
    windowTypes: {
      charge: 'Charge window',
      discharge: 'Discharge window',
      core_risk_window: 'Core risk window',
    },
    driverTypes: {
      reserve_tightness: 'Reserve tightness',
      security_intervention: 'Security intervention',
      network_stress: 'Network stress',
      supply_shock: 'Supply shock',
      demand_weather_shock: 'Demand/weather shock',
      post_event_structural: 'Post-event structural shift',
      predispatch_price_spike: 'Predispatch spike risk',
      predispatch_negative_price: 'Predispatch negative-price window',
      wem_constraint_tightness: 'WEM constraint tightness',
      wem_shortfall_signal: 'WEM shortfall signal',
      market_regime_shift: 'Market regime shift',
      negative_price_regime: 'Negative-price regime risk',
      fcas_pressure_regime: 'FCAS pressure regime',
    },
    scoreLabels: {
      grid_stress_score: 'Grid stress',
      price_spike_risk_score: 'Spike risk',
      negative_price_risk_score: 'Negative-price risk',
      reserve_tightness_risk_score: 'Reserve tightness',
      fcas_opportunity_score: 'FCAS opportunity',
      charge_window_score: 'Charge window',
      discharge_window_score: 'Discharge window',
    },
    contextLabels: {
      forward_price_band: 'Forward price band',
      forward_demand_peak_mw: 'Forward demand peak',
      recent_avg_price_aud_mwh: 'Recent average price',
      recent_price_max_aud_mwh: 'Recent high price',
      recent_price_min_aud_mwh: 'Recent low price',
      recent_negative_ratio_pct: 'Negative-price share',
      recent_fcas_avg_aud_mwh: 'Recent FCAS average',
      binding_count_avg: 'Average binding constraints',
      binding_shadow_max: 'Max binding shadow',
      network_shadow_max: 'Max network shadow',
      shortfall_total_mw: 'Reserve shortfall total',
      constraint_pressure_index: 'Constraint pressure',
    },
    metrics: {
      issuedAt: 'Issued',
      bucket: 'Refresh bucket',
      forecastMode: 'Mode',
      sourcesReady: 'Sources ready',
      forwardPoints: 'Forward points',
      historyPoints: 'History points',
      eventCount: 'Event overlaps',
    },
    warnings: {
      core_only_coverage: 'WEM is currently running in core-only mode and does not represent full-market coverage.',
      confidence_constrained: 'Forecast confidence is constrained by currently available source coverage.',
      predispatch_missing_fallback: 'Official predispatch data was incomplete, so the model fell back to history plus event signals.',
    },
    generic: {
      notAvailable: 'n/a',
      noDrivers: 'No verified forward driver was found in the selected horizon.',
      noWindows: 'No strong forward window was flagged in the selected horizon.',
      keyDrivers: 'Key Drivers',
      futureWindows: 'Future Windows',
      signal: 'signal',
      source: 'source',
      originalSignal: 'Original source signal',
      sourceLink: 'Source link',
      bands: {
        critical: 'critical',
        elevated: 'elevated',
        stable: 'stable',
      },
    },
  },
  zh: {
    section: {
      sectionLabel: '电网预测',
      title: '澳洲电网预测',
      subtitle: '基于官方市场与事件信号的未来风险与机会前瞻。',
      signalDesk: '信号总览',
      marketContext: '市场上下文',
      horizon24h: '24 ??',
      horizon7d: '7 ?',
      horizon30d: '30 ?',
      horizonNotes: {
        '24h': '24 小时模式以官方预调度为主，用于识别最近的充放电机会窗口。',
        '7d': '7 天模式切换为日度风险展望，不再伪装成逐点价格预测。',
        '30d': '30 天模式显示结构性区间与系统压力，不提供精确点位预测。',
      },
    },
    coverage: {
      full: '完整覆盖',
      partial: '部分覆盖',
      core_only: '核心覆盖',
      none: '无已验证覆盖',
    },
    confidence: {
      high: '高置信度',
      medium: '中等置信度',
      low: '低置信度',
      none: '置信度未知',
    },
    forecastModes: {
      hybrid_signal_calibrated: '预调度混合模式',
      daily_regime_outlook: '日度风险展望',
      structural_regime_outlook: '结构性风险展望',
    },
    severity: {
      high: '高',
      medium: '中',
      low: '低',
    },
    statuses: {
      ok: '已接入',
      missing: '缺失',
      partial: '部分',
      stale: '仅作参考',
    },
    sources: {
      recent_market_history: '近期市场历史',
      event_state: '事件状态层',
      nem_predispatch: 'NEM 预调度',
      wem_ess_slim: 'WEM 轻量 ESS/FCAS',
    },
    windowTypes: {
      charge: '充电窗口',
      discharge: '放电窗口',
      core_risk_window: '核心风险窗口',
    },
    driverTypes: {
      reserve_tightness: '备用紧张',
      security_intervention: '安全干预',
      network_stress: '网络受压',
      supply_shock: '供给冲击',
      demand_weather_shock: '需求或天气冲击',
      post_event_structural: '事件后结构变化',
      predispatch_price_spike: '预调度尖峰风险',
      predispatch_negative_price: '预调度负价窗口',
      wem_constraint_tightness: 'WEM 约束趋紧',
      wem_shortfall_signal: 'WEM 短缺信号',
      market_regime_shift: '市场结构切换',
      negative_price_regime: '负电价结构风险',
      fcas_pressure_regime: 'FCAS 压力结构',
    },
    scoreLabels: {
      grid_stress_score: '电网紧张度',
      price_spike_risk_score: '高价尖峰风险',
      negative_price_risk_score: '负电价风险',
      reserve_tightness_risk_score: '备用紧张风险',
      fcas_opportunity_score: 'FCAS 机会',
      charge_window_score: '充电窗口',
      discharge_window_score: '放电窗口',
    },
    contextLabels: {
      forward_price_band: '前瞻价格区间',
      forward_demand_peak_mw: '前瞻需求峰值',
      recent_avg_price_aud_mwh: '近期均价',
      recent_price_max_aud_mwh: '近期高价',
      recent_price_min_aud_mwh: '近期低价',
      recent_negative_ratio_pct: '负电价占比',
      recent_fcas_avg_aud_mwh: '近期 FCAS 均价',
      binding_count_avg: '平均绑定约束数',
      binding_shadow_max: '最大绑定影子价',
      network_shadow_max: '最大网络影子价',
      shortfall_total_mw: '短缺总量',
      constraint_pressure_index: '约束压力指数',
    },
    metrics: {
      issuedAt: '生成时间',
      bucket: '刷新桶',
      forecastMode: '模式',
      sourcesReady: '已接入来源',
      forwardPoints: '前瞻点数',
      historyPoints: '历史点数',
      eventCount: '事件重叠数',
    },
    warnings: {
      core_only_coverage: '当前 WEM 仍为核心覆盖模式，不代表全市场完整覆盖。',
      confidence_constrained: '当前预测置信度受限于可用数据覆盖范围。',
      predispatch_missing_fallback: '官方预调度数据不完整，当前结果已回退为历史加事件信号估计。',
    },
    generic: {
      notAvailable: '暂无',
      noDrivers: '所选预测周期内暂无已验证的前瞻驱动。',
      noWindows: '所选预测周期内暂无强信号窗口。',
      keyDrivers: '关键驱动',
      futureWindows: '未来窗口',
      signal: '信号',
      source: '来源',
      originalSignal: '原始来源信号',
      sourceLink: '来源链接',
      bands: {
        critical: '高压',
        elevated: '抬升',
        stable: '平稳',
      },
    },
  },
};

function normalizeLocale(locale) {
  return locale === 'zh' ? 'zh' : 'en';
}

function getCopy(locale = 'en') {
  return FORECAST_COPY[normalizeLocale(locale)];
}

function toNumber(value) {
  if (value === null || value === undefined || value === '') {
    return null;
  }
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : null;
}

function formatSigned(value, locale = 'en', fractionDigits = 1) {
  const numeric = toNumber(value);
  if (numeric === null) {
    return getCopy(locale).generic.notAvailable;
  }
  return new Intl.NumberFormat(normalizeLocale(locale) === 'zh' ? 'zh-CN' : 'en-US', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
    signDisplay: 'always',
  }).format(numeric);
}

function formatUnsigned(value, locale = 'en', fractionDigits = 1) {
  const numeric = toNumber(value);
  if (numeric === null) {
    return getCopy(locale).generic.notAvailable;
  }
  return new Intl.NumberFormat(normalizeLocale(locale) === 'zh' ? 'zh-CN' : 'en-US', {
    minimumFractionDigits: fractionDigits,
    maximumFractionDigits: fractionDigits,
  }).format(numeric);
}

function buildPriceBand(context, locale = 'en') {
  const min = toNumber(context.forward_price_min_aud_mwh);
  const max = toNumber(context.forward_price_max_aud_mwh);
  const separator = normalizeLocale(locale) === 'zh' ? ' 至 ' : ' to ';
  if (min === null && max === null) {
    return getCopy(locale).generic.notAvailable;
  }
  if (min !== null && max !== null) {
    return `${formatSigned(min, locale, 0)}${separator}${formatSigned(max, locale, 0)} AUD/MWh`;
  }
  return `${formatSigned(min ?? max, locale, 0)} AUD/MWh`;
}

function buildMetricValue(key, value, locale = 'en') {
  switch (key) {
    case 'forward_price_band':
      return value;
    case 'forward_demand_peak_mw':
    case 'shortfall_total_mw':
      return `${formatUnsigned(value, locale, 0)} MW`;
    case 'recent_negative_ratio_pct':
      return `${formatUnsigned(value, locale, 1)}%`;
    case 'binding_count_avg':
    case 'constraint_pressure_index':
      return formatUnsigned(value, locale, 1);
    default:
      return `${formatSigned(value, locale, 1)} AUD/MWh`;
  }
}

function parseNumericSignal(summaryText) {
  const match = String(summaryText || '').match(/-?\d+(?:\.\d+)?/);
  return match ? Number(match[0]) : null;
}

export function buildGridForecastUrl(apiBase, { market, region, horizon, asOf }) {
  const params = new URLSearchParams({
    market,
    region,
    horizon,
  });
  if (asOf) {
    params.set('as_of', asOf);
  }
  return `${apiBase}/grid-forecast?${params.toString()}`;
}

export function normalizeForecastResponse(payload = {}) {
  const metadata = {
    warnings: [],
    sources_used: [],
    ...(payload.metadata || {}),
  };
  const coverageInput = payload.coverage || {};
  const coverage = {
    mode: coverageInput.mode || metadata.coverage_quality || 'none',
    as_of_bucket: coverageInput.as_of_bucket || null,
    source_status: { ...(coverageInput.source_status || {}) },
    recent_history_points: Number(coverageInput.recent_history_points || 0),
    forward_points: Number(coverageInput.forward_points || 0),
    event_count: Number(coverageInput.event_count || 0),
    forward_window_start: coverageInput.forward_window_start || null,
    forward_window_end: coverageInput.forward_window_end || null,
  };
  const windows = [...(payload.windows || [])].sort((left, right) =>
    String(left.start_time || '').localeCompare(String(right.start_time || ''))
  );
  const drivers = [...(payload.drivers || [])].sort((left, right) =>
    String(left.effective_start || '').localeCompare(String(right.effective_start || ''))
  );

  return {
    metadata,
    summary: payload.summary || {},
    coverage,
    marketContext: payload.market_context || {},
    windows,
    drivers,
    disclaimer: payload.disclaimer || null,
  };
}

export function getForecastCoverageCopy(coverageQuality, locale = 'en') {
  const copy = getCopy(locale);
  return copy.coverage[coverageQuality] || copy.coverage.none;
}

export function getForecastConfidenceCopy(confidenceBand, locale = 'en') {
  const copy = getCopy(locale);
  return copy.confidence[confidenceBand] || copy.confidence.none;
}

export function getForecastModeCopy(mode, locale = 'en') {
  const copy = getCopy(locale);
  return copy.forecastModes[mode] || mode || copy.generic.notAvailable;
}

export function getForecastSectionCopy(locale = 'en', overrides = {}) {
  return {
    ...getCopy(locale).section,
    ...(overrides || {}),
  };
}

export function getForecastSourceLabel(sourceKey, locale = 'en') {
  return getCopy(locale).sources[sourceKey] || sourceKey;
}

export function getForecastStatusCopy(status, locale = 'en') {
  return getCopy(locale).statuses[status] || status;
}

export function getForecastWindowTypeCopy(windowType, locale = 'en') {
  return getCopy(locale).windowTypes[windowType] || windowType;
}

export function getForecastScoreLabel(scoreKey, locale = 'en') {
  return getCopy(locale).scoreLabels[scoreKey] || scoreKey;
}

export function getForecastDriverLabel(driverType, locale = 'en') {
  return getCopy(locale).driverTypes[driverType] || driverType;
}

export function getForecastWarningCopy(warningKey, locale = 'en') {
  return getCopy(locale).warnings[warningKey] || warningKey;
}

export function getForecastSeverityCopy(severity, locale = 'en') {
  return getCopy(locale).severity[severity] || severity;
}

export function getForecastText(locale = 'en') {
  return getCopy(locale);
}

export function getForecastBandCopy(score, locale = 'en') {
  const labels = getCopy(locale).generic.bands;
  if (score >= 75) {
    return labels.critical;
  }
  if (score >= 55) {
    return labels.elevated;
  }
  return labels.stable;
}

export function getForecastSourceStatusItems(payload, locale = 'en') {
  const normalized = payload?.coverage ? payload : normalizeForecastResponse(payload);
  return Object.entries(normalized.coverage.source_status || {}).map(([key, status]) => ({
    key,
    label: getForecastSourceLabel(key, locale),
    status,
    statusLabel: getForecastStatusCopy(status, locale),
  }));
}

export function getForecastContextItems(payload, locale = 'en') {
  const normalized = payload?.marketContext ? payload : normalizeForecastResponse(payload);
  const market = normalized?.metadata?.market || 'NEM';
  const context = normalized.marketContext || {};
  const text = getCopy(locale);

  const entries = market === 'WEM'
    ? [
        ['constraint_pressure_index', context.constraint_pressure_index],
        ['binding_shadow_max', context.binding_shadow_max],
        ['network_shadow_max', context.network_shadow_max],
        ['shortfall_total_mw', context.shortfall_total_mw],
        ['recent_avg_price_aud_mwh', context.recent_avg_price_aud_mwh],
        ['recent_fcas_avg_aud_mwh', context.recent_fcas_avg_aud_mwh],
      ]
    : [
        ['forward_price_band', buildPriceBand(context, locale)],
        ['forward_demand_peak_mw', context.forward_demand_peak_mw],
        ['recent_avg_price_aud_mwh', context.recent_avg_price_aud_mwh],
        ['recent_negative_ratio_pct', context.recent_negative_ratio_pct],
        ['recent_fcas_avg_aud_mwh', context.recent_fcas_avg_aud_mwh],
        ['recent_price_min_aud_mwh', context.recent_price_min_aud_mwh],
      ];

  return entries
    .filter(([, value]) => value !== null && value !== undefined && value !== '')
    .map(([key, value]) => ({
      key,
      label: text.contextLabels[key] || key,
      value: buildMetricValue(key, value, locale),
    }));
}

export function localizeForecastDriver(driver = {}, locale = 'en') {
  const lang = normalizeLocale(locale);
  const fallbackTitle = driver.headline || getForecastDriverLabel(driver.driver_type, locale);
  let summary = driver.summary || '';

  if (lang === 'zh') {
    const signalValue = parseNumericSignal(driver.summary);
    if (driver.driver_type === 'predispatch_price_spike' && signalValue !== null) {
      summary = `官方预调度价格上探至 ${formatSigned(signalValue, locale, 0)} AUD/MWh。`;
    } else if (driver.driver_type === 'predispatch_negative_price' && signalValue !== null) {
      summary = `官方预调度价格下探至 ${formatSigned(signalValue, locale, 0)} AUD/MWh。`;
    } else if (driver.driver_type === 'wem_constraint_tightness') {
      summary = '近期约束影子价与绑定约束数量同步抬升，提示局部系统压力加大。';
    } else if (driver.driver_type === 'market_regime_shift') {
      summary = '近期价格带显著拉宽，说明更长周期的风险区间正在抬升。';
    } else if (driver.driver_type === 'negative_price_regime') {
      summary = '近期负电价占比或低价尾部偏弱，充电窗口机会更依赖结构性过剩。';
    } else if (driver.driver_type === 'fcas_pressure_regime') {
      summary = '近期 FCAS 均价仍处于偏高区间，辅助服务机会优于平稳时段。';
    } else if (!summary && driver.headline) {
      summary = `${getCopy(locale).generic.originalSignal}: ${driver.headline}`;
    }
  }

  return {
    ...driver,
    title: lang === 'zh' ? getForecastDriverLabel(driver.driver_type, locale) : fallbackTitle,
    summary,
    sourceLabel: getForecastSourceLabel(driver.source, locale),
    severityLabel: getForecastSeverityCopy(driver.severity, locale),
  };
}
