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
