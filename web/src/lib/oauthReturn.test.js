// web/src/lib/oauthReturn.test.js
// R1.2 社交登录回调落地的纯函数测试（node:test —— 本仓库唯一硬阻断门）。
//
// 锁三件事：令牌读一次就抹、伪造/残缺 fragment 不会被当成会话、return_to 无法指向站外。

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  consumeOAuthHash,
  fetchSocialProviders,
  oauthErrorCopy,
  parseOAuthHash,
  sanitizeReturnTo,
  socialStartUrl,
} from './oauthReturn.js';

const VALID = '#oauth_access_token=at&oauth_access_token_expires_in=1800'
  + '&oauth_session_token=st&oauth_workspace_id=ws_1&oauth_provider=google&oauth_return_to=%2Faccount';

test('parseOAuthHash reads the exact fragment contract the backend writes', () => {
  const parsed = parseOAuthHash(VALID);
  assert.equal(parsed.kind, 'session');
  assert.equal(parsed.accessToken, 'at');
  assert.equal(parsed.sessionToken, 'st');
  assert.equal(parsed.workspaceId, 'ws_1');
  assert.equal(parsed.provider, 'google');
  assert.equal(parsed.expiresIn, 1800);
  assert.equal(parsed.returnTo, '/account');
});

test('incomplete fragment is never treated as a session', () => {
  // 只有 access_token（缺 session/workspace）→ 无法 refresh，也不能算登录成功
  assert.equal(parseOAuthHash('#oauth_access_token=at'), null);
  assert.equal(parseOAuthHash('#oauth_session_token=st&oauth_workspace_id=ws'), null);
  // 与本模块无关的锚点
  assert.equal(parseOAuthHash('#chart'), null);
  assert.equal(parseOAuthHash(''), null);
});

test('missing expires_in falls back to the backend default, not NaN', () => {
  const parsed = parseOAuthHash('#oauth_access_token=a&oauth_session_token=s&oauth_workspace_id=w');
  assert.equal(parsed.expiresIn, 3600);
  assert.equal(parsed.returnTo, '');
});

test('error fragment surfaces a code, not a session', () => {
  const parsed = parseOAuthHash('#oauth_error=state_invalid&oauth_provider=google');
  assert.equal(parsed.kind, 'error');
  assert.equal(parsed.code, 'state_invalid');
  assert.match(oauthErrorCopy('state_invalid', true), /过期/);
  assert.match(oauthErrorCopy('state_invalid', false), /expired/i);
  // 未知码不得编造原因
  assert.match(oauthErrorCopy('brand_new_code', true), /邮箱登录/);
});

test('consumeOAuthHash wipes the token out of browser history', () => {
  const calls = [];
  const location = { hash: VALID, pathname: '/login', search: '' };
  const parsed = consumeOAuthHash(location, { replaceState: (...args) => calls.push(args) });
  assert.equal(parsed.accessToken, 'at');
  assert.deepEqual(calls, [[null, '', '/login']], 'fragment must be stripped, path+query kept');
});

test('consumeOAuthHash ignores unrelated fragments and survives missing history', () => {
  assert.equal(consumeOAuthHash({ hash: '', pathname: '/login', search: '' }, {}), null);
  const parsed = consumeOAuthHash({ hash: VALID, pathname: '/login', search: '' }, undefined);
  assert.equal(parsed.kind, 'session');
});

test('sanitizeReturnTo rejects every out-of-app shape', () => {
  for (const bad of [
    'https://evil.test/x', '//evil.test/x', '/\\evil.test', 'javascript:alert(1)',
    'https:/x', 'evil.test/path', 'mailto:a@b.c',
  ]) {
    assert.equal(sanitizeReturnTo(bad), '', `must reject ${bad}`);
  }
  assert.equal(sanitizeReturnTo('/account'), '/account');
  assert.equal(sanitizeReturnTo('  /account  '), '/account', 'trim parity with backend');
  assert.equal(sanitizeReturnTo('/finland/board?window=7d'), '/finland/board?window=7d');
  assert.equal(sanitizeReturnTo(''), '');
  assert.equal(sanitizeReturnTo(undefined), '');
});

test('socialStartUrl is server-owned and carries only a sanitized next', () => {
  assert.equal(
    socialStartUrl('http://localhost:8000/api/v1', 'google', '/account'),
    'http://localhost:8000/api/v1/auth/oauth/google/start?next=%2Faccount',
  );
  // 尾斜杠归一 + 站外 next 直接丢掉参数（而不是编码后照传）
  assert.equal(
    socialStartUrl('https://app.test/api/v1/', 'github', '//evil.test'),
    'https://app.test/api/v1/auth/oauth/github/start',
  );
});

test('fetchSocialProviders degrades to an empty list, never throws', () => {
  const ok = async () => ({
    ok: true,
    json: async () => ({ providers: [{ key: 'google', label: 'Google' }, { key: 1 }, null] }),
  });
  return fetchSocialProviders('https://app.test/api/v1', ok).then((list) => {
    assert.deepEqual(list, [{ key: 'google', label: 'Google' }], 'malformed entries filtered out');
  });
});

test('fetchSocialProviders swallows http and network failures', async () => {
  assert.deepEqual(await fetchSocialProviders('/api/v1', async () => ({ ok: false })), []);
  assert.deepEqual(await fetchSocialProviders('/api/v1', async () => {
    throw new Error('offline');
  }), []);
  assert.deepEqual(await fetchSocialProviders('/api/v1', async () => ({
    ok: true, json: async () => ({ providers: 'not-a-list' }),
  })), []);
});
