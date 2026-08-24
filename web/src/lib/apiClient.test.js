import test from 'node:test';
import assert from 'node:assert/strict';

import { clearFetchJsonCache, fetchJson } from './apiClient.js';

test('fetchJson deduplicates concurrent GET requests for the same URL', async () => {
  clearFetchJsonCache();

  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    await new Promise((resolve) => setTimeout(resolve, 10));
    return {
      ok: true,
      json: async () => ({ rows: [{ value: 1 }] }),
    };
  };

  const [left, right] = await Promise.all([
    fetchJson('http://example.test/api/items'),
    fetchJson('http://example.test/api/items'),
  ]);

  assert.equal(callCount, 1);
  assert.deepEqual(left, { rows: [{ value: 1 }] });
  assert.deepEqual(right, { rows: [{ value: 1 }] });
  assert.notEqual(left, right);
});

test('fetchJson does not deduplicate POST requests', async () => {
  clearFetchJsonCache();

  let callCount = 0;
  globalThis.fetch = async () => {
    callCount += 1;
    return {
      ok: true,
      json: async () => ({ ok: true }),
    };
  };

  await Promise.all([
    fetchJson('http://example.test/api/run', { method: 'POST', body: '{"a":1}' }),
    fetchJson('http://example.test/api/run', { method: 'POST', body: '{"a":1}' }),
  ]);

  assert.equal(callCount, 2);
});

test('fetchJson evicts older GET cache entries when the cache grows beyond the cap', async () => {
  clearFetchJsonCache();

  const callCounts = new Map();
  globalThis.fetch = async (url) => {
    callCounts.set(url, (callCounts.get(url) || 0) + 1);
    return {
      ok: true,
      json: async () => ({ url, callCount: callCounts.get(url) }),
    };
  };

  for (let index = 0; index < 65; index += 1) {
    await fetchJson(`http://example.test/api/items/${index}`);
  }

  const refetched = await fetchJson('http://example.test/api/items/0');

  assert.equal(callCounts.get('http://example.test/api/items/0'), 2);
  assert.equal(refetched.callCount, 2);
});
