export function buildFingridSeriesUrl(apiBase, { datasetId, start, end, tz, aggregation, limit }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  if (aggregation) params.set('aggregation', aggregation);
  if (limit) params.set('limit', String(limit));
  return `${apiBase}/fingrid/datasets/${datasetId}/series?${params.toString()}`;
}

export function buildFingridSummaryUrl(apiBase, { datasetId, start, end }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  return `${apiBase}/fingrid/datasets/${datasetId}/summary?${params.toString()}`;
}

export function buildFingridStatusUrl(apiBase, datasetId) {
  return `${apiBase}/fingrid/datasets/${datasetId}/status`;
}

export function buildFingridSyncUrl(apiBase, datasetId, mode = 'incremental') {
  return `${apiBase}/fingrid/datasets/${datasetId}/sync?mode=${encodeURIComponent(mode)}`;
}

export function buildFingridExportUrl(apiBase, { datasetId, start, end, tz, aggregation, limit }) {
  const params = new URLSearchParams();
  if (start) params.set('start', start);
  if (end) params.set('end', end);
  if (tz) params.set('tz', tz);
  if (aggregation) params.set('aggregation', aggregation);
  if (limit) params.set('limit', String(limit));
  return `${apiBase}/fingrid/datasets/${datasetId}/export?${params.toString()}`;
}

export function normalizeFingridDatasetList(payload = {}) {
  return Array.isArray(payload.datasets) ? payload.datasets : [];
}
