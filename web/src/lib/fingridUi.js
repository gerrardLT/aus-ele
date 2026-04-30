const DEFAULT_UNIT = 'EUR/MW';

const COPY = {
  zh: {
    brand: 'Fingrid \u82ac\u5170\u7535\u7f51',
    navToAemo: '\u6fb3\u6d32\u5e02\u573a',
    datasetFallback: '\u82ac\u5170\u6570\u636e\u96c6 317',
    defaultDatasetId: '317',
    defaultUnit: 'EUR/MW',
    defaultFrequency: '1h',
    presetLabels: {
      '7d': '7\u5929',
      '30d': '30\u5929',
      '90d': '90\u5929',
      '1y': '1\u5e74',
      all: '\u5168\u90e8',
      custom: '\u81ea\u5b9a\u4e49',
    },
    timezoneLabels: {
      'Europe/Helsinki': '\u6b27\u6d32/\u8d6b\u5c14\u8f9b\u57fa',
      UTC: 'UTC',
    },
    sync: '\u540c\u6b65',
    syncing: '\u540c\u6b65\u4e2d...',
    exportCsv: '\u5bfc\u51fa CSV',
    toggleLanguage: 'EN',
    startDate: '\u5f00\u59cb\u65e5\u671f',
    endDate: '\u7ed3\u675f\u65e5\u671f',
    latest: '\u6700\u65b0\u503c',
    avg24h: '24H \u5747\u503c',
    avg30d: '30D \u5747\u503c',
    min: '\u6700\u4f4e',
    max: '\u6700\u9ad8',
    bucketAvg: '\u5e73\u5747',
    bucketPeak: '\u6ce2\u5cf0',
    bucketTrough: '\u6ce2\u8c37',
    loadingCards: '\u52a0\u8f7d\u4e2d...',
    loadingChart: '\u56fe\u8868\u52a0\u8f7d\u4e2d...',
    emptyChart: '\u6240\u9009\u7a97\u53e3\u6682\u65e0\u53ef\u7528\u65f6\u95f4\u5e8f\u5217\u6570\u636e\u3002',
    loadingDistributions: '\u5206\u5e03\u52a0\u8f7d\u4e2d...',
    loadingStatus: '\u72b6\u6001\u52a0\u8f7d\u4e2d...',
    seriesTitle: '\u65f6\u95f4\u5e8f\u5217',
    monthlyAverage: '\u6708\u5747\u4ef7',
    yearlyAverage: '\u5e74\u5747\u4ef7',
    hourlyProfile: '\u5c0f\u65f6\u753b\u50cf',
    syncStatus: '\u540c\u6b65\u72b6\u6001',
    statusFields: {
      status: '\u72b6\u6001',
      lastSuccess: '\u6700\u8fd1\u6210\u529f',
      coverageStart: '\u8986\u76d6\u5f00\u59cb',
      coverageEnd: '\u8986\u76d6\u7ed3\u675f',
      records: '\u8bb0\u5f55\u6570',
      lastError: '\u6700\u8fd1\u9519\u8bef',
    },
    statusValues: {
      loading: '\u52a0\u8f7d\u4e2d',
      idle: '\u672a\u540c\u6b65',
      ok: '\u6b63\u5e38',
      running: '\u8fd0\u884c\u4e2d',
      error: '\u9519\u8bef',
    },
    tooltip: {
      average: '\u5e73\u5747',
      peak: '\u6ce2\u5cf0',
      trough: '\u6ce2\u8c37',
      samples: '\u6837\u672c\u6570',
      start: '\u5f00\u59cb',
      end: '\u7ed3\u675f',
    },
    notSynced: '\u672a\u540c\u6b65',
    none: '\u65e0',
    validation: {
      missing_custom_dates: '\u8bf7\u9009\u62e9\u5f00\u59cb\u65e5\u671f\u548c\u7ed3\u675f\u65e5\u671f\u3002',
      invalid_custom_range: '\u5f00\u59cb\u65e5\u671f\u4e0d\u80fd\u665a\u4e8e\u7ed3\u675f\u65e5\u671f\u3002',
    },
    datasetNames: {
      '317': '\u82ac\u5170 FCR-N \u5c0f\u65f6\u5e02\u573a\u4ef7\u683c',
    },
    datasetDescriptions: {
      '317': '\u82ac\u5170 FCR-N \u5907\u7528\u5bb9\u91cf\u5e02\u573a\u7684\u5c0f\u65f6\u4ef7\u683c\u6570\u636e\u3002',
    },
    marketModel: {
      title: '\u82ac\u5170\u5e02\u573a\u6a21\u578b',
      subtitle: 'Fingrid \u5df2\u6269\u5c55\u4e3a\u82ac\u5170\u591a\u6765\u6e90\u4e0a\u4e0b\u6587\u9875',
      description: '\u5f53\u524d\u5df2\u63a5\u5165 Fingrid \u7684\u5907\u7528\u5bb9\u91cf\u4e0e imbalance \u4fe1\u53f7\uff0cNord Pool \u4e0e ENTSO-E \u4fdd\u7559\u4e3a\u540e\u7eed\u63a5\u5165\u4f4d\u3002\u8fd9\u4e2a\u9875\u9762\u4e0d\u518d\u628a Finland \u7b49\u540c\u4e8e\u5355\u4e00\u6570\u636e\u96c6\u3002',
      modelStatus: '\u6a21\u578b\u72b6\u6001',
      liveDatasets: '\u5728\u7ebf\u6570\u636e\u96c6',
      liveSignals: '\u5f53\u524d\u5728\u7ebf\u4fe1\u53f7',
      noSignals: '\u5f53\u524d\u8fd8\u6ca1\u6709\u53ef\u5c55\u793a\u7684\u82ac\u5170\u5728\u7ebf\u4fe1\u53f7\u3002',
      plannedNordPool: '\u5f85\u63a5\u5165 day-ahead / intraday',
      plannedEntsoe: '\u5f85\u63a5\u5165 transparency \u4e0e cross-border flow',
    },
    marketPulseTitle: '\u82ac\u5170\u5e02\u573a\u5feb\u7167',
    marketPulseSubtitle: '\u5148\u770b\u5f53\u524d\u6570\u636e\u96c6\u3001\u7a97\u53e3\u4e0e\u540c\u6b65\u72b6\u6001\uff0c\u518d\u8fdb\u5165\u65f6\u95f4\u5e8f\u5217\u548c\u5206\u5e03\u8bfb\u53d6\u3002',
    marketPulseDataset: '\u5f53\u524d\u6570\u636e\u96c6',
    marketPulseWindow: '\u89c2\u5bdf\u7a97\u53e3',
    marketPulseMode: '\u805a\u5408\u7c92\u5ea6',
    marketPulseStatus: '\u540c\u6b65\u72b6\u6001',
    marketPulseRunning: '\u6570\u636e\u540c\u6b65\u6b63\u5728\u8fd0\u884c\uff0c\u5148\u5173\u6ce8\u72b6\u6001\u9762\u677f\u548c\u6700\u65b0\u8986\u76d6\u8303\u56f4\u3002',
    marketPulseReady: '\u5f53\u524d\u6570\u636e\u53ef\u7528\uff0c\u5efa\u8bae\u6309\u7167\u4e0a\u4e0b\u6587\u3001\u65f6\u5e8f\u3001\u72b6\u6001\u7684\u987a\u5e8f\u9605\u8bfb\u3002',
    stageContext: '\u9636\u6bb5 1\uff1a\u82ac\u5170\u5e02\u573a\u4e0a\u4e0b\u6587',
    stageContextDesc: '\u660e\u786e Fingrid \u5f53\u524d\u5df2\u63a5\u5165\u7684\u4fe1\u53f7\u6e90\uff0c\u533a\u5206\u5df2\u5728\u7ebf\u7684\u6570\u636e\u96c6\u548c\u540e\u7eed\u9884\u7559\u7684\u6e90\u69fd\u4f4d\u3002',
    stageTimeSeries: '\u9636\u6bb5 2\uff1a\u65f6\u5e8f\u4e0e\u7edf\u8ba1\u89c6\u56fe',
    stageTimeSeriesDesc: '\u5148\u770b\u6838\u5fc3 KPI\uff0c\u518d\u770b\u65f6\u95f4\u5e8f\u5217\u66f2\u7ebf\uff0c\u786e\u8ba4\u4ef7\u683c\u7ed3\u6784\u548c\u8fd1\u671f\u6ce2\u52a8\u3002',
    stageOperations: '\u9636\u6bb5 3\uff1a\u5206\u5e03\u4e0e\u8fd0\u884c\u72b6\u6001',
    stageOperationsDesc: '\u7528\u5206\u5e03\u753b\u50cf\u548c\u540c\u6b65\u72b6\u6001\u9762\u677f\uff0c\u5224\u65ad\u6570\u636e\u53ef\u9760\u6027\u4e0e\u5f53\u524d\u8fd0\u884c\u5065\u5eb7\u5ea6\u3002',
  },
  en: {
    brand: 'Fingrid Finland',
    navToAemo: 'Australia Market',
    datasetFallback: 'Dataset 317',
    defaultDatasetId: '317',
    defaultUnit: 'EUR/MW',
    defaultFrequency: '1h',
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
    toggleLanguage: '\u4e2d\u6587',
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
    emptyChart: 'No time-series data is available for the selected window.',
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
      loading: 'loading',
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
    marketModel: {
      title: 'Finland Market Model',
      subtitle: 'Fingrid expanded into a Finland multi-source context view',
      description: 'The current scope includes live Fingrid reserve-capacity and imbalance signals, while Nord Pool and ENTSO-E remain explicit future source slots. Finland is no longer treated as a single-dataset view.',
      modelStatus: 'Model Status',
      liveDatasets: 'Live Datasets',
      liveSignals: 'Live Signals',
      noSignals: 'No live Finland signals are available yet.',
      plannedNordPool: 'planned day-ahead / intraday',
      plannedEntsoe: 'planned transparency and cross-border flow',
    },
    marketPulseTitle: 'Finland Market Readout',
    marketPulseSubtitle: 'Read dataset scope, time window, and sync state first, then move into the time-series and distribution views.',
    marketPulseDataset: 'Current Dataset',
    marketPulseWindow: 'Observation Window',
    marketPulseMode: 'Aggregation',
    marketPulseStatus: 'Sync Status',
    marketPulseRunning: 'A data sync is running. Prioritize the status panel and latest coverage range before reading the chart.',
    marketPulseReady: 'The current dataset is available. Read the page in order: context, time series, then operations.',
    stageContext: 'Stage 1: Finland Context',
    stageContextDesc: 'Clarify which Fingrid signals are live today, and which source slots remain planned for later integration.',
    stageTimeSeries: 'Stage 2: Time Series and KPI View',
    stageTimeSeriesDesc: 'Start from the key summary cards, then inspect the series chart to confirm shape and recent volatility.',
    stageOperations: 'Stage 3: Distribution and Operational Status',
    stageOperationsDesc: 'Use the distribution view and sync-status panel to judge data reliability and current operating health.',
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
    return normalizeLang(lang) === 'zh' ? '\u539f\u59cb' : 'Raw';
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
