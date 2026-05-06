export const FINLAND_DAILY_BOARD_VIEWS = ['daily_capacity', 'daily_activation'];
export const FINLAND_PRIMARY_BOARD_TABS = ['capacity_hourly', 'activation_15m', 'daily'];

const ACTIVATION_FIELD_KEY_PATTERN = /(act_|imbalance_price)/;
const NON_SELECTABLE_FIELD_CATEGORIES = new Set(['time']);
const NON_SELECTABLE_GRANULARITIES = new Set(['display']);
const FINLAND_DEFAULT_PRIMARY_PRICE_FIELD = 'fcr_n_price_eur_mw';
const FINLAND_SPOT_PRICE_FIELD = 'spot_price_fi_eur_mwh';
const FINLAND_RESERVE_PRICE_CATEGORIES = new Set(['capacity', 'activation']);
const FINLAND_BOARD_VIEW_CATEGORY_MAP = {
  capacity_hourly: 'capacity',
  daily_capacity: 'capacity',
  activation_15m: 'activation',
  daily_activation: 'activation',
};
const FINLAND_PRICE_SUPPORT_FIELD_MAP = new Map([
  ['fcr_n_price_eur_mw', 'fcr_n_volume_mw'],
  ['fcr_d_up_price_eur_mw', 'fcr_d_up_volume_mw'],
  ['fcr_d_down_price_eur_mw', 'fcr_d_down_volume_mw'],
  ['afrr_cap_up_eur_mw', 'afrr_cap_up_volume_mw'],
  ['afrr_cap_down_eur_mw', 'afrr_cap_down_volume_mw'],
  ['mfrr_cap_up_eur_mw', 'mfrr_cap_up_volume_mw'],
  ['mfrr_cap_down_eur_mw', 'mfrr_cap_down_volume_mw'],
]);

function isFiniteNumber(value) {
  return typeof value === 'number' && Number.isFinite(value);
}

function getFinlandSupportFieldKey(primaryFieldKey) {
  if (FINLAND_PRICE_SUPPORT_FIELD_MAP.has(primaryFieldKey)) {
    return FINLAND_PRICE_SUPPORT_FIELD_MAP.get(primaryFieldKey);
  }

  if (typeof primaryFieldKey !== 'string' || !primaryFieldKey) {
    return null;
  }

  const isReservePriceField = /^(fcr|afrr|mfrr)_/.test(primaryFieldKey);

  if (isReservePriceField && primaryFieldKey.includes('_price_')) {
    return primaryFieldKey.replace('_price_', '_volume_');
  }

  if (isReservePriceField && primaryFieldKey.endsWith('_eur_mw')) {
    return primaryFieldKey.replace(/_eur_mw$/, '_volume_mw');
  }

  return null;
}

function getFinlandVolatilityLabel(values) {
  if (!values.length) {
    return 'no_data';
  }

  const highValue = Math.max(...values);
  const lowValue = Math.min(...values);
  const meanValue = values.reduce((sum, value) => sum + value, 0) / values.length;
  const baseline = Math.max(Math.abs(meanValue), 1);
  const normalizedRange = Math.abs(highValue - lowValue) / baseline;

  if (normalizedRange >= 0.75) {
    return 'high';
  }
  if (normalizedRange >= 0.25) {
    return 'medium';
  }
  return 'low';
}

export function buildFinlandBoardOverviewUrl(apiBase, { start, end } = {}) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const suffix = params.toString();
  return `${apiBase}/finland/board/overview${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardTableUrl(apiBase, { view, start, end, tz, limit } = {}) {
  const params = new URLSearchParams();
  if (view) params.set('view', view);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  if (limit) params.set('limit', String(limit));
  const suffix = params.toString();
  return `${apiBase}/finland/board/table${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardChartUrl(apiBase, { fields = [], mode, start, end, granularity, limitPoints } = {}) {
  const params = new URLSearchParams();
  for (const field of fields) {
    params.append('fields', field);
  }
  if (mode) params.set('mode', mode);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (granularity) params.set('granularity', granularity);
  if (limitPoints) params.set('limit_points', String(limitPoints));
  const suffix = params.toString();
  return `${apiBase}/finland/board/chart${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardFieldCatalogUrl(apiBase) {
  return `${apiBase}/finland/board/field-catalog`;
}

export function buildFinlandBoardReadinessUrl(apiBase) {
  return `${apiBase}/finland/board/readiness`;
}

export function getDefaultFinlandPrimaryPriceField() {
  return FINLAND_DEFAULT_PRIMARY_PRICE_FIELD;
}

export function buildFinlandPrimaryPriceOptions(fieldCatalogItems = [], { boardView } = {}) {
  const preferredCategory = FINLAND_BOARD_VIEW_CATEGORY_MAP[boardView] || null;
  const reservePriceItems = fieldCatalogItems.filter((item) => {
    if (!item?.field_key || !item?.label || !item?.unit) {
      return false;
    }

    if (!FINLAND_RESERVE_PRICE_CATEGORIES.has(item.category)) {
      return false;
    }

    if (!item.unit.startsWith('EUR/')) {
      return false;
    }

    if (preferredCategory && item.category !== preferredCategory) {
      return false;
    }

    return true;
  });

  return reservePriceItems.sort((left, right) => {
    if (left.field_key === FINLAND_DEFAULT_PRIMARY_PRICE_FIELD) {
      return -1;
    }
    if (right.field_key === FINLAND_DEFAULT_PRIMARY_PRICE_FIELD) {
      return 1;
    }
    return left.label.localeCompare(right.label);
  });
}

export function buildFinlandPrimaryPriceSummary({
  primaryFieldKey = FINLAND_DEFAULT_PRIMARY_PRICE_FIELD,
  tableRows = [],
} = {}) {
  const primaryValues = [];
  let latestValue = null;
  let latestAlignedSpotValue = null;

  for (const row of tableRows) {
    const primaryValue = row?.[primaryFieldKey];
    const spotValue = row?.[FINLAND_SPOT_PRICE_FIELD];

    if (isFiniteNumber(primaryValue)) {
      primaryValues.push(primaryValue);
      latestValue = primaryValue;
      latestAlignedSpotValue = isFiniteNumber(spotValue) ? spotValue : null;
    }
  }

  if (!primaryValues.length) {
    return {
      latestValue: null,
      highValue: null,
      lowValue: null,
      meanValue: null,
      spreadVsSpotLatest: null,
      volatilityBand: 'no_data',
    };
  }

  const highValue = Math.max(...primaryValues);
  const lowValue = Math.min(...primaryValues);
  const meanValue = primaryValues.reduce((sum, value) => sum + value, 0) / primaryValues.length;

  return {
    latestValue,
    highValue,
    lowValue,
    meanValue,
    spreadVsSpotLatest:
      latestValue !== null && latestAlignedSpotValue !== null
        ? latestValue - latestAlignedSpotValue
        : null,
    volatilityBand: getFinlandVolatilityLabel(primaryValues),
  };
}

export function buildFinlandComparisonRailRequest({
  primaryFieldKey = FINLAND_DEFAULT_PRIMARY_PRICE_FIELD,
  granularity,
  limitPoints = 240,
} = {}) {
  const fields = [primaryFieldKey];
  const supportFieldKey = getFinlandSupportFieldKey(primaryFieldKey);

  if (supportFieldKey) {
    fields.push(supportFieldKey);
  }

  if (!fields.includes(FINLAND_SPOT_PRICE_FIELD)) {
    fields.push(FINLAND_SPOT_PRICE_FIELD);
  }

  return {
    fields,
    mode: 'compare',
    granularity,
    limitPoints,
  };
}

export function getFinlandBoardOverviewCards(overviewPayload) {
  return Array.isArray(overviewPayload?.cards) ? overviewPayload.cards : [];
}

export function getFinlandBoardTableColumns(tablePayload) {
  return Array.isArray(tablePayload?.columns) ? tablePayload.columns : [];
}

export function getFinlandBoardTableRows(tablePayload) {
  return Array.isArray(tablePayload?.rows) ? tablePayload.rows : [];
}

export function buildFinlandBoardDictionaryRows(fieldCatalogItems = []) {
  return fieldCatalogItems.map((item) => ({
    ...item,
    preferredView: getFinlandDictionaryTargetView(item.field_key, item.granularity),
  }));
}

function getFinlandLatestFieldValue(rows, fieldKey) {
  for (let index = rows.length - 1; index >= 0; index -= 1) {
    const value = rows[index]?.[fieldKey];
    if (value !== null && value !== undefined) {
      return value;
    }
  }
  return null;
}

function isSelectableBoardColumn(column) {
  if (!column?.field_key) {
    return false;
  }
  if (NON_SELECTABLE_FIELD_CATEGORIES.has(column.category)) {
    return false;
  }
  if (NON_SELECTABLE_GRANULARITIES.has(column.granularity)) {
    return false;
  }
  return true;
}

export function buildFinlandBoardSelectedFields({
  selectedFieldIds = [],
  tablePayload,
  fieldCatalogItems = [],
} = {}) {
  const columns = getFinlandBoardTableColumns(tablePayload);
  const rows = getFinlandBoardTableRows(tablePayload);
  const catalogByKey = new Map(fieldCatalogItems.map((item) => [item.field_key, item]));
  const columnsByKey = new Map(columns.map((column) => [column.field_key, column]));

  return selectedFieldIds.map((fieldId) => {
    const column = columnsByKey.get(fieldId) || {};
    const catalog = catalogByKey.get(fieldId) || {};
    const fieldKey = column.field_key || catalog.field_key;

    if (!fieldKey) {
      return null;
    }

    return {
      field_key: fieldKey,
      id: fieldKey,
      label: column.label || catalog.label || fieldKey,
      unit: column.unit ?? catalog.unit ?? null,
      source_name: column.source_name || catalog.source_name || null,
      source_dataset_id: catalog.source_dataset_id || null,
      source_type: column.source_type || catalog.source_type || null,
      category: column.category || catalog.category || null,
      granularity: column.granularity || catalog.granularity || null,
      methodology_note: catalog.methodology_note || null,
      latestValue: getFinlandLatestFieldValue(rows, fieldKey),
    };
  }).filter(Boolean);
}

export function buildFinlandBoardChartRequest({
  selectedFields = [],
  viewGranularity,
  limitPoints,
} = {}) {
  const fields = selectedFields
    .map((field) => field?.field_key || field?.id)
    .filter(Boolean);

  if (!fields.length) {
    return null;
  }

  return {
    fields,
    mode: fields.length === 1 ? 'single' : 'compare',
    granularity: viewGranularity || selectedFields[0]?.granularity || '1h',
    limitPoints,
  };
}

export function isFinlandBoardSelectableColumn(column) {
  return isSelectableBoardColumn(column);
}

export function resolveFinlandBoardView(activeTab, dailyMode = 'daily_capacity') {
  return activeTab === 'daily' ? dailyMode : activeTab;
}

export function getFinlandDictionaryTargetView(fieldKey, granularity) {
  const normalizedFieldKey = String(fieldKey || '');
  const normalizedGranularity = String(granularity || '');
  const targetsDailyActivation = ACTIVATION_FIELD_KEY_PATTERN.test(normalizedFieldKey);

  if (normalizedGranularity === 'day') {
    return targetsDailyActivation ? 'daily_activation' : 'daily_capacity';
  }

  return targetsDailyActivation ? 'activation_15m' : 'capacity_hourly';
}

export function normalizeFinlandDictionaryJumpTarget(preferredView) {
  if (FINLAND_DAILY_BOARD_VIEWS.includes(preferredView)) {
    return 'daily';
  }

  if (FINLAND_PRIMARY_BOARD_TABS.includes(preferredView)) {
    return preferredView;
  }

  return 'capacity_hourly';
}
