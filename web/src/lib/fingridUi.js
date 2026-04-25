const DEFAULT_UNIT = 'EUR/MW';

const COPY = {
  zh: {
    brand: 'Fingrid 芬兰电网',
    navToAemo: '澳洲市场',
    datasetFallback: '芬兰数据集 317',
    presetLabels: {
      '7d': '7天',
      '30d': '30天',
      '90d': '90天',
      '1y': '1年',
      all: '全部',
      custom: '自定义',
    },
    timezoneLabels: {
      'Europe/Helsinki': '欧洲/赫尔辛基',
      UTC: 'UTC',
    },
    sync: '同步',
    syncing: '同步中...',
    exportCsv: '导出 CSV',
    toggleLanguage: 'EN',
    startDate: '开始日期',
    endDate: '结束日期',
    latest: '最新值',
    avg24h: '24H 均值',
    avg30d: '30D 均值',
    min: '最低',
    max: '最高',
    bucketAvg: '平均',
    bucketPeak: '波峰',
    bucketTrough: '波谷',
    loadingCards: '加载中...',
    loadingChart: '图表加载中...',
    loadingDistributions: '分布加载中...',
    loadingStatus: '状态加载中...',
    seriesTitle: '时间序列',
    monthlyAverage: '月均价',
    yearlyAverage: '年均价',
    hourlyProfile: '小时画像',
    syncStatus: '同步状态',
    statusFields: {
      status: '状态',
      lastSuccess: '最近成功',
      coverageStart: '覆盖开始',
      coverageEnd: '覆盖结束',
      records: '记录数',
      lastError: '最近错误',
    },
    statusValues: {
      idle: '未同步',
      ok: '正常',
      running: '运行中',
      error: '错误',
    },
    tooltip: {
      average: '平均',
      peak: '波峰',
      trough: '波谷',
      samples: '样本数',
      start: '开始',
      end: '结束',
    },
    notSynced: '未同步',
    none: '无',
    validation: {
      missing_custom_dates: '请选择开始日期和结束日期。',
      invalid_custom_range: '开始日期不能晚于结束日期。',
    },
    datasetNames: {
      '317': '芬兰 FCR-N 小时市场价格',
    },
    datasetDescriptions: {
      '317': '芬兰 FCR-N 备用容量市场的小时价格数据。',
    },
  },
  en: {
    brand: 'Fingrid Finland',
    navToAemo: 'Australia Market',
    datasetFallback: 'Dataset 317',
    presetLabels: {
      '7d': '7d',
      '30d': '30d',
      '90d': '90d',
      '1y': '1y',
      all: 'all',
      custom: 'Custom',
    },
    timezoneLabels: {
      'Europe/Helsinki': 'Europe/Helsinki',
      UTC: 'UTC',
    },
    sync: 'Sync',
    syncing: 'Syncing...',
    exportCsv: 'Export CSV',
    toggleLanguage: '中文',
    startDate: 'Start date',
    endDate: 'End date',
    latest: 'Latest',
    avg24h: '24h Avg',
    avg30d: '30d Avg',
    min: 'Min',
    max: 'Max',
    bucketAvg: 'Avg',
    bucketPeak: 'Peak',
    bucketTrough: 'Trough',
    loadingCards: 'Loading...',
    loadingChart: 'Loading chart...',
    loadingDistributions: 'Loading distributions...',
    loadingStatus: 'Loading status...',
    seriesTitle: 'Time Series',
    monthlyAverage: 'Monthly Average',
    yearlyAverage: 'Yearly Average',
    hourlyProfile: 'Hourly Profile',
    syncStatus: 'Sync Status',
    statusFields: {
      status: 'Status',
      lastSuccess: 'Last success',
      coverageStart: 'Coverage start',
      coverageEnd: 'Coverage end',
      records: 'Records',
      lastError: 'Last error',
    },
    statusValues: {
      idle: 'idle',
      ok: 'ok',
      running: 'running',
      error: 'error',
    },
    tooltip: {
      average: 'Average',
      peak: 'Peak',
      trough: 'Trough',
      samples: 'Samples',
      start: 'Start',
      end: 'End',
    },
    notSynced: 'not-synced',
    none: 'none',
    validation: {
      missing_custom_dates: 'Choose both a start date and an end date.',
      invalid_custom_range: 'The start date cannot be after the end date.',
    },
    datasetNames: {
      '317': 'FCR-N hourly market prices',
    },
    datasetDescriptions: {
      '317': 'FCR-N hourly reserve-capacity market price in Finland.',
    },
  },
};

function normalizeLang(lang = 'en') {
  return lang === 'zh' ? 'zh' : 'en';
}

export function getFingridCopy(lang = 'en') {
  return COPY[normalizeLang(lang)];
}

export function getAggregationDisplayLabel(aggregation = 'raw', lang = 'en') {
  const normalized = aggregation === 'hour' ? '1h' : aggregation;
  if (normalized === 'raw') {
    return normalizeLang(lang) === 'zh' ? '原始' : 'Raw';
  }
  return normalized.toUpperCase();
}

export function buildFingridRequestLimit({ preset = '30d', aggregation = 'day' } = {}) {
  const normalized = aggregation === 'hour' ? '1h' : aggregation;
  if ((preset === 'all' || preset === 'custom') && normalized !== 'raw') {
    return null;
  }
  return 5000;
}

export function localizeFingridDataset(dataset = {}, lang = 'en') {
  const copy = getFingridCopy(lang);
  const datasetId = String(dataset.dataset_id || '');
  return {
    ...dataset,
    name: copy.datasetNames[datasetId] || dataset.name || copy.datasetFallback,
    description: copy.datasetDescriptions[datasetId] || dataset.description || '',
  };
}

export function buildFingridSummaryCards({
  lang = 'en',
  aggregation = 'day',
  summaryPayload = {},
  seriesPayload = {},
} = {}) {
  const copy = getFingridCopy(lang);
  const unit = summaryPayload?.dataset?.unit || seriesPayload?.dataset?.unit || DEFAULT_UNIT;
  const kpis = summaryPayload?.kpis || {};
  const series = seriesPayload?.series || [];
  const latestBucket = series[series.length - 1] || {};
  const aggregationLabel = getAggregationDisplayLabel(aggregation, lang);

  return [
    { label: `${aggregationLabel} ${copy.bucketAvg}`, value: latestBucket.avg_value, unit },
    { label: `${aggregationLabel} ${copy.bucketPeak}`, value: latestBucket.peak_value, unit },
    { label: `${aggregationLabel} ${copy.bucketTrough}`, value: latestBucket.trough_value, unit },
    { label: copy.latest, value: kpis.latest_value, unit },
    { label: copy.avg24h, value: kpis.avg_24h, unit },
    { label: copy.avg30d, value: kpis.avg_30d, unit },
    { label: copy.min, value: kpis.min_value, unit },
    { label: copy.max, value: kpis.max_value, unit },
  ];
}

export function formatFingridStatusValue(value, lang = 'en') {
  if (!value) {
    return getFingridCopy(lang).statusValues.idle;
  }
  const copy = getFingridCopy(lang);
  return copy.statusValues[value] || value;
}
