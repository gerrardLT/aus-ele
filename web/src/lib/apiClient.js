const inflightGetRequests = new Map();
const recentGetResponses = new Map();
const DEFAULT_TTL_MS = 5000;
const MAX_CACHED_GET_RESPONSES = 64;
const DEFAULT_TIMEOUT_MS = 30_000;

function cloneJson(value) {
  if (typeof globalThis.structuredClone === 'function') {
    return globalThis.structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function buildCacheKey(url, method) {
  return `${method}:${url}`;
}

function pruneExpiredGetResponses(now = Date.now()) {
  for (const [cacheKey, entry] of recentGetResponses.entries()) {
    if (entry.expiresAt <= now) {
      recentGetResponses.delete(cacheKey);
    }
  }
}

function pruneOverflowingGetResponses() {
  while (recentGetResponses.size > MAX_CACHED_GET_RESPONSES) {
    const oldestKey = recentGetResponses.keys().next().value;
    if (!oldestKey) {
      break;
    }
    recentGetResponses.delete(oldestKey);
  }
}

export function clearFetchJsonCache() {
  inflightGetRequests.clear();
  recentGetResponses.clear();
}

/**
 * Fetch JSON with AbortController timeout, retry, and caching.
 *
 * @param {string} url - The URL to fetch.
 * @param {Object} [options={}] - Fetch options (method, body, headers, etc.).
 * @param {number} [options.timeoutMs] - Abort timeout in ms (default 30000).
 * @param {number} [options.retries] - Number of retries on network error (default 1 for GET).
 * @param {AbortSignal} [options.signal] - External AbortSignal (takes precedence).
 * @returns {Promise<any>} Parsed JSON response.
 */
export async function fetchJson(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const cacheable = method === 'GET' && !options.body;
  const cacheKey = buildCacheKey(url, method);
  const now = Date.now();
  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const maxRetries = options.retries ?? (cacheable ? 1 : 0);

  if (cacheable) {
    pruneExpiredGetResponses(now);
    const cached = recentGetResponses.get(cacheKey);
    if (cached && cached.expiresAt > now) {
      return cloneJson(cached.data);
    }

    const inflight = inflightGetRequests.get(cacheKey);
    if (inflight) {
      return cloneJson(await inflight);
    }
  }

  const requestPromise = _fetchWithRetry(url, options, { timeoutMs, maxRetries });

  if (cacheable) {
    inflightGetRequests.set(cacheKey, requestPromise);
  }

  try {
    const data = await requestPromise;
    if (cacheable) {
      recentGetResponses.set(cacheKey, {
        data,
        expiresAt: Date.now() + DEFAULT_TTL_MS,
      });
      pruneOverflowingGetResponses();
    }
    return cloneJson(data);
  } finally {
    if (cacheable) {
      inflightGetRequests.delete(cacheKey);
    }
  }
}

/**
 * Internal fetch with AbortController timeout and retry on network errors.
 */
async function _fetchWithRetry(url, options, { timeoutMs, maxRetries }) {
  // If caller provides their own signal, use it directly (no internal timeout)
  if (options.signal) {
    const resp = await fetch(url, options);
    if (!resp.ok) {
      throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
    }
    return resp.json();
  }

  for (let attempt = 0; attempt <= maxRetries; attempt++) {
    const controller = new AbortController();
    const timerId = setTimeout(() => controller.abort(), timeoutMs);

    try {
      const resp = await fetch(url, {
        ...options,
        signal: controller.signal,
      });
      if (!resp.ok) {
        throw new Error(`HTTP ${resp.status}: ${resp.statusText}`);
      }
      return await resp.json();
    } catch (err) {
      const isAbort = err.name === 'AbortError';
      const isNetwork = err.name === 'TypeError' || (err.message && err.message.includes('fetch'));
      const isLastAttempt = attempt === maxRetries;

      if (isLastAttempt) {
        if (isAbort) {
          throw new Error(`Request to ${url} timed out after ${timeoutMs}ms`);
        }
        throw err;
      }

      // Retry on network errors or abort (timeout), but not on HTTP errors
      if (isAbort || isNetwork) {
        // Exponential backoff: 500ms, 1000ms, ...
        await new Promise((r) => setTimeout(r, 500 * (attempt + 1)));
        continue;
      }

      // Non-retryable error (e.g., 4xx/5xx)
      throw err;
    } finally {
      clearTimeout(timerId);
    }
  }
}
