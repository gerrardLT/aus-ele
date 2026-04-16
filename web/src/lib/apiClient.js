const inflightGetRequests = new Map();
const recentGetResponses = new Map();
const DEFAULT_TTL_MS = 5000;

function cloneJson(value) {
  if (typeof globalThis.structuredClone === 'function') {
    return globalThis.structuredClone(value);
  }
  return JSON.parse(JSON.stringify(value));
}

function buildCacheKey(url, method) {
  return `${method}:${url}`;
}

export function clearFetchJsonCache() {
  inflightGetRequests.clear();
  recentGetResponses.clear();
}

export async function fetchJson(url, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  const cacheable = method === 'GET' && !options.body;
  const cacheKey = buildCacheKey(url, method);
  const now = Date.now();

  if (cacheable) {
    const cached = recentGetResponses.get(cacheKey);
    if (cached && cached.expiresAt > now) {
      return cloneJson(cached.data);
    }

    const inflight = inflightGetRequests.get(cacheKey);
    if (inflight) {
      return cloneJson(await inflight);
    }
  }

  const requestPromise = fetch(url, options).then((response) => response.json());

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
    }
    return cloneJson(data);
  } finally {
    if (cacheable) {
      inflightGetRequests.delete(cacheKey);
    }
  }
}
