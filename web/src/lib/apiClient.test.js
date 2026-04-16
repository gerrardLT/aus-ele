import test from 'node:test';
import assert from 'node:assert/strict';

import { clearFetchJsonCache, fetchJson } from './apiClient.js';

test('fetchJson deduplicates concurrent GET requests for the same URL', async () => {
  clearFetchJsonCache();

  let callCount = 0;
  global.fetch = async () => {
    callCount += 1;
    await new Promise((resolve) => setTimeout(resolve, 10));
    return {
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
  global.fetch = async () => {
    callCount += 1;
    return {
      json: async () => ({ ok: true }),
    };
  };

  await Promise.all([
    fetchJson('http://example.test/api/run', { method: 'POST', body: '{"a":1}' }),
    fetchJson('http://example.test/api/run', { method: 'POST', body: '{"a":1}' }),
  ]);

  assert.equal(callCount, 2);
});
