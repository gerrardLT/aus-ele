const DAY_MS = 24 * 60 * 60 * 1000;
const ISO_DATE_RE = /^(\d{4})-(\d{2})-(\d{2})$/;
const formatterCache = new Map();

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

function parseIsoDate(dateString) {
  const match = ISO_DATE_RE.exec(String(dateString || ''));
  if (!match) {
    return null;
  }
  return {
    year: Number(match[1]),
    month: Number(match[2]),
    day: Number(match[3]),
  };
}

function formatIsoDate(date) {
  return [
    date.getUTCFullYear(),
    String(date.getUTCMonth() + 1).padStart(2, '0'),
    String(date.getUTCDate()).padStart(2, '0'),
  ].join('-');
}

function shiftIsoDate(dateString, days) {
  const parts = parseIsoDate(dateString);
  if (!parts) {
    return null;
  }
  return formatIsoDate(new Date(Date.UTC(parts.year, parts.month - 1, parts.day + days)));
}

function getFormatter(timeZone) {
  if (!formatterCache.has(timeZone)) {
    formatterCache.set(
      timeZone,
      new Intl.DateTimeFormat('en-CA', {
        timeZone,
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit',
        hourCycle: 'h23',
      }),
    );
  }
  return formatterCache.get(timeZone);
}

function getTimeZoneOffsetMs(date, timeZone) {
  if (timeZone === 'UTC') {
    return 0;
  }

  const parts = {};
  for (const part of getFormatter(timeZone).formatToParts(date)) {
    if (part.type !== 'literal') {
      parts[part.type] = Number(part.value);
    }
  }

  const zonedTime = Date.UTC(
    parts.year,
    (parts.month || 1) - 1,
    parts.day || 1,
    parts.hour || 0,
    parts.minute || 0,
    parts.second || 0,
  );
  return zonedTime - date.getTime();
}

function zonedMidnightToUtcIso(dateString, timeZone) {
  const parts = parseIsoDate(dateString);
  if (!parts) {
    return null;
  }

  if (timeZone === 'UTC') {
    return `${dateString}T00:00:00.000Z`;
  }

  const utcMidnight = new Date(Date.UTC(parts.year, parts.month - 1, parts.day, 0, 0, 0));
  const initialOffset = getTimeZoneOffsetMs(utcMidnight, timeZone);
  let resolved = new Date(utcMidnight.getTime() - initialOffset);
  const refinedOffset = getTimeZoneOffsetMs(resolved, timeZone);
  if (refinedOffset !== initialOffset) {
    resolved = new Date(utcMidnight.getTime() - refinedOffset);
  }
  return resolved.toISOString();
}

export function getCustomDateRangeValidationCode({ preset, customStartDate, customEndDate }) {
  if (preset !== 'custom') {
    return null;
  }
  if (!customStartDate || !customEndDate) {
    return 'missing_custom_dates';
  }
  if (customStartDate > customEndDate) {
    return 'invalid_custom_range';
  }
  return null;
}

export function buildCustomDateWindow({ customStartDate, customEndDate, tz = 'UTC' }) {
  return {
    start: zonedMidnightToUtcIso(customStartDate, tz),
    end: zonedMidnightToUtcIso(shiftIsoDate(customEndDate, 1), tz),
  };
}

export function buildFingridTimeWindow({
  preset,
  customStartDate,
  customEndDate,
  tz = 'UTC',
  now = new Date(),
}) {
  if (preset === 'custom') {
    return buildCustomDateWindow({ customStartDate, customEndDate, tz });
  }
  return buildPresetWindow(preset, now);
}

function getNumericMetric(value, fallback = 0) {
  const numeric = Number(value);
  return Number.isFinite(numeric) ? numeric : fallback;
}

function roundMetric(value) {
  return Number(getNumericMetric(value).toFixed(4));
}

function aggregateChartBucket(bucket = []) {
  if (!Array.isArray(bucket) || bucket.length === 0) {
    return null;
  }

  const midpoint = bucket[Math.floor(bucket.length / 2)];
  let weightedSum = 0;
  let totalSamples = 0;
  let peakValue = Number.NEGATIVE_INFINITY;
  let troughValue = Number.POSITIVE_INFINITY;

  for (const point of bucket) {
    const sampleCount = Math.max(1, getNumericMetric(point?.sample_count, 1));
    const averageValue = getNumericMetric(point?.avg_value ?? point?.value);
    const pointPeak = getNumericMetric(point?.peak_value ?? point?.value);
    const pointTrough = getNumericMetric(point?.trough_value ?? point?.value);
    weightedSum += averageValue * sampleCount;
    totalSamples += sampleCount;
    if (pointPeak > peakValue) {
      peakValue = pointPeak;
    }
    if (pointTrough < troughValue) {
      troughValue = pointTrough;
    }
  }

  const avgValue = totalSamples > 0 ? roundMetric(weightedSum / totalSamples) : 0;
  return {
    timestamp: midpoint?.timestamp,
    timestamp_utc: midpoint?.timestamp_utc,
    bucket_start: bucket[0]?.bucket_start ?? bucket[0]?.timestamp,
    bucket_end: bucket[bucket.length - 1]?.bucket_end ?? bucket[bucket.length - 1]?.timestamp,
    value: avgValue,
    avg_value: avgValue,
    peak_value: roundMetric(peakValue),
    trough_value: roundMetric(troughValue),
    sample_count: totalSamples,
    unit: midpoint?.unit ?? bucket[0]?.unit,
  };
}

export function downsampleSeriesForChart(series = [], maxPoints = 1200) {
  if (!Array.isArray(series) || series.length <= maxPoints) {
    return Array.isArray(series) ? series : [];
  }

  const firstPoint = series[0];
  const lastPoint = series[series.length - 1];
  if (maxPoints <= 2) {
    return [firstPoint, lastPoint];
  }

  const interiorSeries = series.slice(1, -1);
  if (interiorSeries.length === 0) {
    return [firstPoint, lastPoint];
  }

  const interiorCapacity = Math.max(1, maxPoints - 2);
  const bucketSize = Math.ceil(interiorSeries.length / interiorCapacity);
  const chartSeries = [firstPoint];

  for (let start = 0; start < interiorSeries.length; start += bucketSize) {
    const bucket = interiorSeries.slice(start, start + bucketSize);
    const aggregatedPoint = aggregateChartBucket(bucket);
    if (aggregatedPoint) {
      chartSeries.push(aggregatedPoint);
    }
  }

  if (chartSeries[chartSeries.length - 1] !== lastPoint) {
    chartSeries.push(lastPoint);
  }

  return chartSeries;
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
