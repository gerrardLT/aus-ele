// web/src/lib/workspaceSwitch.test.js
// R1.5 切换逻辑测试（node:test）。锁的是「切换后用户仍然知道自己是谁、在哪些空间」。

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  loginSessionUrl,
  mergeSwitchedSession,
  switchableWorkspaces,
  workspaceLabel,
} from './workspaceSwitch.js';

const NOW = Date.parse('2026-09-06T12:00:00Z');

const baseAuth = {
  accessToken: 'old-token',
  accessTokenExp: 1,
  sessionToken: 'old-session',
  workspaceId: 'ws_a',
  principal: { principal_id: 'pr_1', email: 'a@example.com' },
  workspaces: [
    { workspace_id: 'ws_a', name: 'NEM Lab', role: 'owner' },
    { workspace_id: 'ws_b', name: 'Finland Pilot', role: 'analyst' },
  ],
};

test('endpoint path matches the backend route exactly', () => {
  assert.equal(loginSessionUrl('/api', 'ws_b'), '/api/v1/account/workspaces/ws_b/login-session');
  assert.equal(loginSessionUrl('/api', 'a/b?c'), '/api/v1/account/workspaces/a%2Fb%3Fc/login-session');
});

test('switching swaps tokens and workspace but keeps identity and the workspace list', () => {
  const next = mergeSwitchedSession(
    baseAuth,
    { access_token: 'new-token', session_token: 'new-session', workspace_id: 'ws_b', access_token_expires_in: 900 },
    NOW,
  );
  assert.equal(next.accessToken, 'new-token');
  assert.equal(next.sessionToken, 'new-session');
  assert.equal(next.workspaceId, 'ws_b');
  assert.equal(next.accessTokenExp, Math.floor(NOW / 1000) + 900);
  // 这两条是本轮修复的核心：换签响应里没有 principal / workspaces，
  // 用响应对象整体替换旧记录会把它们清成 undefined。
  assert.deepEqual(next.principal, baseAuth.principal);
  assert.deepEqual(next.workspaces, baseAuth.workspaces);
});

test('a session payload missing any credential is refused instead of half-written', () => {
  // 半写入的后果是「有 workspaceId 却没令牌」：此后每个请求 401，而用户看到的仍是已登录态
  const complete = { access_token: 't', session_token: 's', workspace_id: 'w' };
  for (const field of ['access_token', 'session_token', 'workspace_id']) {
    assert.equal(mergeSwitchedSession(baseAuth, { ...complete, [field]: '' }, NOW), null, `${field} 为空必须拒绝`);
    const missing = { ...complete };
    delete missing[field];
    assert.equal(mergeSwitchedSession(baseAuth, missing, NOW), null, `${field} 缺失必须拒绝`);
  }
  assert.equal(mergeSwitchedSession(null, complete, NOW), null);
  assert.equal(mergeSwitchedSession(baseAuth, null, NOW), null);
  assert.equal(mergeSwitchedSession(baseAuth, {}, NOW), null);
});

test('default token ttl keeps a single switch from locking the tab out early', () => {
  const next = mergeSwitchedSession(baseAuth, { access_token: 't', session_token: 's', workspace_id: 'ws_b' }, NOW);
  assert.equal(next.accessTokenExp, Math.floor(NOW / 1000) + 3600);
});

test('a single workspace yields no switcher at all', () => {
  assert.deepEqual(switchableWorkspaces({ ...baseAuth, workspaces: [baseAuth.workspaces[0]] }), []);
  assert.deepEqual(switchableWorkspaces({ ...baseAuth, workspaces: [] }), []);
  assert.deepEqual(switchableWorkspaces(null), []);
  const options = switchableWorkspaces(baseAuth);
  assert.deepEqual(options.map((w) => w.workspace_id), ['ws_b'], '当前空间不作为可切换项出现');
});

test('label falls back to a truncated id rather than a bare uuid or blank', () => {
  assert.equal(workspaceLabel({ name: 'NEM Lab', role: 'owner' }, true), 'NEM Lab（owner）');
  assert.equal(workspaceLabel({ name: 'NEM Lab', role: 'owner' }, false), 'NEM Lab (owner)');
  assert.equal(workspaceLabel({ workspace_id: 'ws_deadbeef1234' }, true), '未命名空间 ws_deadb');
  assert.equal(workspaceLabel({ workspace_id: 'ws_deadbeef1234' }, false), 'Untitled ws_deadb');
  assert.equal(workspaceLabel({}, true), '未命名空间');
});
