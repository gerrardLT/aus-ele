export function buildFinlandBoardOverviewUrl(apiBase, { start, end } = {}) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  const suffix = params.toString();
  return `${apiBase}/finland/board/overview${suffix ? `?${suffix}` : ''}`;
}

export function buildFinlandBoardTableUrl(apiBase, { view, start, end, tz } = {}) {
  const params = new URLSearchParams();
  params.set('view', view);
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  return `${apiBase}/finland/board/table?${params.toString()}`;
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
  return `${apiBase}/finland/board/chart?${params.toString()}`;
}

export function buildFinlandBoardFieldCatalogUrl(apiBase) {
  return `${apiBase}/finland/board/field-catalog`;
}

export function buildFinlandBoardReadinessUrl(apiBase) {
  return `${apiBase}/finland/board/readiness`;
}
