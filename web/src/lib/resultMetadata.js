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

export function formatMetadataUnitLabel(metadata = {}) {
  const currency = metadata.currency || '';
  const unit = metadata.unit || '';
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
