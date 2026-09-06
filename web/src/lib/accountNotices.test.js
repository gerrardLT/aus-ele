// web/src/lib/accountNotices.test.js
// R1.9/R1.1 提示判据测试（node:test）。锁的是「什么时候不许说话」。

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  DISMISS_TTL_MS,
  fetchVerificationStatus,
  noticeFor,
  readDismissed,
  writeDismissed,
} from './accountNotices.js';

const NOW = 1_800_000_000_000;

test('anonymous visitors are told what registration unlocks', () => {
  const notice = noticeFor({ hasSession: false, emailVerified: null }, true, NOW);
  assert.equal(notice.kind, 'anonymous');
  assert.equal(notice.href, '/register');
  assert.match(notice.title, /保存|提醒|导出/);
  assert.match(noticeFor({ hasSession: false, emailVerified: null }, false, NOW).title, /free account/i);
});

test('unverified sessions get the verify nudge, verified ones get silence', () => {
  assert.equal(noticeFor({ hasSession: true, emailVerified: false }, true, NOW).kind, 'unverified');
  assert.equal(noticeFor({ hasSession: true, emailVerified: true }, true, NOW), null);
  // 状态未知（拉取失败）必须沉默：把「不确定」渲染成「去验证」是在撒谎
  assert.equal(noticeFor({ hasSession: true, emailVerified: null }, true, NOW), null);
});

test('dismissing silences the banner for two weeks, then it returns', () => {
  const dismissed = { anonymous: NOW };
  assert.equal(noticeFor({ hasSession: false, emailVerified: null, dismissed }, true, NOW + 1000), null);
  const revived = noticeFor({ hasSession: false, emailVerified: null, dismissed }, true, NOW + DISMISS_TTL_MS + 1);
  assert.equal(revived.kind, 'anonymous', '永久静默会让半年前关掉横幅的人再也看不到新能力');
  // 关闭 anonymous 不影响 unverified（两条判据各自独立）
  assert.equal(noticeFor({ hasSession: true, emailVerified: false, dismissed }, true, NOW).kind, 'unverified');
});

test('dismissal round-trips through storage and prunes expired entries', () => {
  const store = new Map();
  const storage = {
    getItem: (key) => (store.has(key) ? store.get(key) : null),
    setItem: (key, value) => store.set(key, value),
  };
  assert.deepEqual(readDismissed(storage), {});
  assert.deepEqual(readDismissed(undefined), {});
  assert.deepEqual(readDismissed({ getItem: () => 'not-json' }), {});

  writeDismissed(storage, 'anonymous', NOW);
  assert.deepEqual(readDismissed(storage), { anonymous: NOW });

  writeDismissed(storage, 'unverified', NOW + DISMISS_TTL_MS + 1);
  assert.deepEqual(readDismissed(storage), { unverified: NOW + DISMISS_TTL_MS + 1 },
    '过期条目应在下一次写入时被剪掉');

  // 存储不可用（Safari 隐私模式 / SSR）时不得抛错
  assert.doesNotThrow(() => writeDismissed({ getItem: () => { throw new Error('denied'); }, setItem: () => { throw new Error('denied'); } }, 'anonymous'));
});

test('fetchVerificationStatus distinguishes unknown from false', async () => {
  assert.equal(await fetchVerificationStatus('/api/v1', ''), null, '无 token 不发请求');
  assert.equal(await fetchVerificationStatus('/api/v1', 't', async () => ({ ok: false })), null);
  assert.equal(await fetchVerificationStatus('/api/v1', 't', async () => { throw new Error('offline'); }), null);
  assert.equal(await fetchVerificationStatus('/api/v1', 't', async () => ({
    ok: true, json: async () => ({ email_verified: 'yes' }),
  })), null, '非布尔值一律当未知，不做真值猜测');
  assert.equal(await fetchVerificationStatus('/api/v1/', 't', async (url) => {
    assert.equal(url, '/api/v1/register/status', 'base 尾斜杠归一');
    return { ok: true, json: async () => ({ email_verified: true }) };
  }), true);
});

test('fetchVerificationStatus sends the bearer token', async () => {
  let seen = null;
  await fetchVerificationStatus('https://app.test/api/v1', 'tok-1', async (url, init) => {
    seen = { url, init };
    return { ok: true, json: async () => ({ email_verified: false }) };
  });
  assert.equal(seen.url, 'https://app.test/api/v1/register/status');
  assert.equal(seen.init.headers.Authorization, 'Bearer tok-1');
});
