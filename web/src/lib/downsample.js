/**
 * Data downsampling utilities for Recharts.
 *
 * When chart datasets exceed a threshold number of points, applying
 * downsampling before rendering improves performance without visible
 * quality loss.
 *
 * Implements LTTBC (Largest Triangle Three Buckets) algorithm which
 * preserves visual shape better than simple decimation.
 */

/**
 * Downsample an array of data points using LTTBC algorithm.
 *
 * @param {Array<Object>} data - Array of data point objects.
 * @param {string} xKey - Property name for the X-axis value.
 * @param {string} yKey - Property name for the Y-axis value.
 * @param {number} [threshold=500] - Target number of output points.
 * @returns {Array<Object>} Downsampled data array (always includes first and last points).
 */
export function downsampleLTTBC(data, xKey, yKey, threshold = 500) {
  const n = data.length;
  if (n <= threshold || threshold < 3) {
    return data;
  }

  const sampled = [data[0]]; // Always keep the first point

  const bucketSize = (n - 2) / (threshold - 2);

  let prevIndex = 0;

  for (let i = 1; i < threshold - 1; i++) {
    // Calculate the average of the next bucket
    const nextBucketStart = Math.floor((i + 1) * bucketSize) + 1;
    const nextBucketEnd = Math.min(Math.floor((i + 2) * bucketSize) + 1, n);
    let avgX = 0;
    let avgY = 0;
    const nextCount = nextBucketEnd - nextBucketStart;

    for (let j = nextBucketStart; j < nextBucketEnd; j++) {
      avgX += toNumber(data[j][xKey]);
      avgY += toNumber(data[j][yKey]);
    }
    if (nextCount > 0) {
      avgX /= nextCount;
      avgY /= nextCount;
    }

    // Find the point in the current bucket with the largest triangle area
    const bucketStart = Math.floor(i * bucketSize) + 1;
    const bucketEnd = Math.min(Math.floor((i + 1) * bucketSize) + 1, n);

    const prevX = toNumber(data[prevIndex][xKey]);
    const prevY = toNumber(data[prevIndex][yKey]);

    let maxArea = -1;
    let maxIndex = bucketStart;

    for (let j = bucketStart; j < bucketEnd; j++) {
      const currX = toNumber(data[j][xKey]);
      const currY = toNumber(data[j][yKey]);
      // Triangle area = 0.5 * |x_prev(y_curr - y_avg) + x_curr(y_avg - y_prev) + x_avg(y_prev - y_curr)|
      const area = Math.abs(
        (prevX - avgX) * (currY - prevY) -
        (prevX - currX) * (avgY - prevY)
      );
      if (area > maxArea) {
        maxArea = area;
        maxIndex = j;
      }
    }

    sampled.push(data[maxIndex]);
    prevIndex = maxIndex;
  }

  sampled.push(data[n - 1]); // Always keep the last point

  return sampled;
}

/**
 * Auto-downsample chart data if it exceeds the threshold.
 *
 * Convenience wrapper that picks the first numeric property as Y-axis
 * if yKey is not specified.
 *
 * @param {Array<Object>} data - Chart data array.
 * @param {Object} [options={}] - Options.
 * @param {string} [options.xKey] - X-axis property (auto-detected if omitted).
 * @param {string} [options.yKey] - Y-axis property (auto-detected if omitted).
 * @param {number} [options.threshold=500] - Max points before downsampling.
 * @returns {Array<Object>} Possibly downsampled data.
 */
export function autoDownsample(data, options = {}) {
  if (!Array.isArray(data) || data.length === 0) {
    return data;
  }

  const threshold = options.threshold ?? 500;
  if (data.length <= threshold) {
    return data;
  }

  // Auto-detect xKey and yKey from the first data point
  const first = data[0];
  const keys = Object.keys(first);
  const xKey = options.xKey || keys.find((k) => typeof first[k] === 'string') || keys[0];
  const yKey = options.yKey || keys.find((k) => k !== xKey && typeof first[k] === 'number') || keys[1];

  if (!xKey || !yKey) {
    return data; // Can't determine axes, return as-is
  }

  return downsampleLTTBC(data, xKey, yKey, threshold);
}

/**
 * Convert a value to a number for area calculations.
 * Handles date strings, timestamps, and numeric values.
 */
function toNumber(value) {
  if (typeof value === 'number') {
    return value;
  }
  if (typeof value === 'string') {
    // Try parsing as date first (for time-series X-axis)
    const ts = Date.parse(value);
    if (!isNaN(ts)) {
      return ts;
    }
    const num = parseFloat(value);
    return isNaN(num) ? 0 : num;
  }
  return 0;
}
