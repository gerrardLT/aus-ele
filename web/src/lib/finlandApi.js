export const FINLAND_DAILY_BOARD_VIEWS = ['daily_capacity', 'daily_activation'];
export const FINLAND_PRIMARY_BOARD_TABS = ['capacity_hourly', 'activation_15m', 'daily'];

const ACTIVATION_FIELD_KEY_PATTERN = /(act_|imbalance_price)/;

export function buildFinlandBoardOverviewUrl(apiBase, { start, end } = {}) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const suffix = params.toString();
  return `${apiBase}/finland/board/overview${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardTableUrl(apiBase, { view, start, end, tz } = {}) {
  const params = new URLSearchParams();
  if (view) params.set('view', view);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  const suffix = params.toString();
  return `${apiBase}/finland/board/table${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardChartUrl(apiBase, { fields = [], mode, start, end, granularity } = {}) {
  const params = new URLSearchParams();
  for (const field of fields) {
    params.append('fields', field);
  }
  if (mode) params.set('mode', mode);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (granularity) params.set('granularity', granularity);
  const suffix = params.toString();
  return `${apiBase}/finland/board/chart${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardFieldCatalogUrl(apiBase) {
  return `${apiBase}/finland/board/field-catalog`;
}

export function buildFinlandBoardReadinessUrl(apiBase) {
  return `${apiBase}/finland/board/readiness`;
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
