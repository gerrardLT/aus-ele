const DAY_MS = 24 * 60 * 60 * 1000;

export function buildPresetWindow(preset, now = new Date()) {
  const endDate = new Date(now);
  const presetDays = {
    '7d': 7,
    '30d': 30,
    '90d': 90,
    '1y': 365,
  };

  if (preset === 'all') {
    return { start: null, end: endDate.toISOString() };
  }

  const days = presetDays[preset] ?? 30;
  const startDate = new Date(endDate.getTime() - (days * DAY_MS));
  return { start: startDate.toISOString(), end: endDate.toISOString() };
}

export function formatFingridValue(value, unit) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return `n/a ${unit}`;
  }
  return `${Number(value).toFixed(2)} ${unit}`;
}

export function buildHourlyProfile(series = []) {
  const buckets = new Map();
  for (const point of series) {
    const match = String(point.timestamp).match(/T(\d{2}):/);
    const hour = match ? Number(match[1]) : new Date(point.timestamp).getHours();
    const values = buckets.get(hour) || [];
    values.push(Number(point.value));
    buckets.set(hour, values);
  }

  return [...buckets.entries()]
    .sort((left, right) => left[0] - right[0])
    .map(([hour, values]) => ({
      hour,
      avg_value: Number((values.reduce((sum, value) => sum + value, 0) / values.length).toFixed(4)),
    }));
}
