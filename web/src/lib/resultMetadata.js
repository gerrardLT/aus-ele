export function getResultMetadata(payload = {}) {
  const metadata = payload?.metadata || {};
  return {
    market: metadata.market || '',
    region_or_zone: metadata.region_or_zone || '',
    timezone: metadata.timezone || '',
    currency: metadata.currency || '',
    unit: metadata.unit || '',
    interval_minutes: metadata.interval_minutes ?? null,
    data_grade: metadata.data_grade || 'unknown',
    grade: metadata.grade || metadata.data_grade || 'unknown',
    dataset_family: metadata.dataset_family || '',
    observation_kind: metadata.observation_kind || '',
    lineage: metadata.lineage || {},
    data_quality_score: metadata.data_quality_score ?? null,
    source_name: metadata.source_name || '',
    source_version: metadata.source_version || '',
    methodology_version: metadata.methodology_version || '',
    freshness: metadata.freshness || {},
    coverage: metadata.coverage || {},
    warnings: metadata.warnings || [],
  };
}

export function getDataGradeTone(grade = 'unknown') {
  if (grade === 'analytical') return 'success';
  if (grade === 'preview' || grade === 'analytical-preview') return 'warning';
  return 'neutral';
}

export function formatDataGradeLabel(grade = 'unknown', lang = 'en') {
  const normalizedLang = lang === 'zh' ? 'zh' : 'en';
  const labels = {
    analytical: { zh: '分析级', en: 'Analytical' },
    preview: { zh: '预览级', en: 'Preview' },
    'analytical-preview': { zh: '分析预览', en: 'Analytical Preview' },
    unknown: { zh: '未知', en: 'Unknown' },
  };
  return (labels[grade] || labels.unknown)[normalizedLang];
}

export function formatDatasetFamilyLabel(family = '', lang = 'en') {
  const normalizedLang = lang === 'zh' ? 'zh' : 'en';
  const labels = {
    load_actual: { zh: '负荷实绩', en: 'Load Actual' },
    load_forecast: { zh: '负荷预测', en: 'Load Forecast' },
    wind_forecast: { zh: '风电预测', en: 'Wind Forecast' },
    wind_actual: { zh: '风电实绩', en: 'Wind Actual' },
    solar_forecast: { zh: '光伏预测', en: 'Solar Forecast' },
    solar_actual: { zh: '光伏实绩', en: 'Solar Actual' },
    rooftop_pv: { zh: '屋顶光伏', en: 'Rooftop PV' },
    outage: { zh: '停机事件', en: 'Outage' },
    interconnector_flow: { zh: '联络线潮流', en: 'Interconnector Flow' },
    reserve_requirement: { zh: '备用需求', en: 'Reserve Requirement' },
    reserve_shortfall: { zh: '备用缺口', en: 'Reserve Shortfall' },
    weather: { zh: '天气', en: 'Weather' },
    unit_availability: { zh: '机组可用容量', en: 'Unit Availability' },
    constraint: { zh: '约束输入', en: 'Constraint Input' },
    settlement: { zh: '结算输入', en: 'Settlement Input' },
    forecast_layer: { zh: '预测层', en: 'Forecast Layer' },
    bess_decision_layer: { zh: '储能决策层', en: 'BESS Decision Layer' },
  };
  return (labels[family] || { zh: family || '未知数据集', en: family || 'Unknown Dataset' })[normalizedLang];
}

export function formatMetadataUnitLabel(metadata = {}) {
  const normalizedMetadata = metadata || {};
  const currency = normalizedMetadata.currency || '';
  const unit = normalizedMetadata.unit || '';
  if (unit) {
    return unit;
  }
  return currency;
}

export function formatFreshnessLabel(freshness = {}, lang = 'en') {
  const normalizedLang = lang === 'zh' ? 'zh' : 'en';
  const lastUpdatedAt = freshness?.last_updated_at;
  if (!lastUpdatedAt) {
    return normalizedLang === 'zh' ? '暂无更新时间' : 'Update time unavailable';
  }
  return normalizedLang === 'zh' ? `更新于 ${lastUpdatedAt}` : `Updated ${lastUpdatedAt}`;
}

export function getPreviewModeLabel(mode = '', lang = 'en') {
  const normalizedLang = lang === 'zh' ? 'zh' : 'en';
  const labels = {
    single_day_preview: { zh: '单日预览', en: 'Single-day Preview' },
    multi_day_preview: { zh: '多日预览', en: 'Multi-day Preview' },
    default: { zh: '预览', en: 'Preview' },
  };
  return (labels[mode] || labels.default)[normalizedLang];
}

export function getDataGradeCaveat(grade = 'unknown', lang = 'en') {
  const normalizedLang = lang === 'zh' ? 'zh' : 'en';
  const copy = {
    preview: {
      zh: '仅供预览，请勿用于项目融资。',
      en: 'Preview only. Do not use for project finance.',
    },
    'analytical-preview': {
      zh: '仅供分析预览，请勿用于项目融资。',
      en: 'Analytical preview only. Do not use for project finance.',
    },
  };
  return copy[grade]?.[normalizedLang] || '';
}
