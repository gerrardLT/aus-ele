// web/src/lib/accountSessions.test.js
// R1.3 会话判据测试（node:test）。锁的是「不许把计数说谎」。

import test from 'node:test';
import assert from 'node:assert/strict';
import {
  canRevokeOthers,
  formatStamp,
  liveSessionCount,
  methodLabel,
  partitionSessions,
  revokeOthersUrl,
  sessionsUrl,
} from './accountSessions.js';

const T0 = Date.parse('2026-09-06T12:00:00Z');
const FUTURE = '2026-09-06T18:00:00Z';
const PAST = '2026-09-05T18:00:00Z';

function session(id, overrides = {}) {
  return {
    session_id: id,
    workspace_id: 'ws_a',
    auth_method: 'password',
    created_at: '2026-09-01T00:00:00Z',
    last_seen_at: '2026-09-06T11:00:00Z',
    expires_at: FUTURE,
    ...overrides,
  };
}

test('url builders take the api base verbatim without doubling /api', () => {
  assert.equal(sessionsUrl('/api'), '/api/v1/account/sessions');
  assert.equal(revokeOthersUrl('http://127.0.0.1:8085/api'), 'http://127.0.0.1:8085/api/v1/account/sessions/revoke-others');
});

test('expired-but-not-revoked sessions are never counted as live', () => {
  // 后端 SQL 只过滤 revoked，到期会话照样返回。面板若原样宣称「3 个活跃会话」，
  // 就是在给用户一个虚高的入侵感，同时让「登出其他设备」的实际效果与宣称不符。
  const rows = partitionSessions(
    { current_session_id: 's1', items: [session('s1'), session('s2', { expires_at: PAST }), session('s3', { expires_at: PAST })] },
    [],
    T0,
  );
  assert.equal(liveSessionCount(rows), 1, '只剩当前会话是活的');
  assert.deepEqual(rows.map((r) => r.status), ['current', 'expired', 'expired'], '到期行仍展示，但分类明确');
});

test('the revoke button disappears when no other live session exists', () => {
  assert.equal(canRevokeOthers(partitionSessions({ current_session_id: 's1', items: [session('s1')] }, [], T0)), false);
  assert.equal(
    canRevokeOthers(partitionSessions({ current_session_id: 's1', items: [session('s1'), session('s2', { expires_at: PAST })] }, [], T0)),
    false,
    '其他会话已到期 = 登出它们没有安全收益，不该留一个谎称能保护你的按钮',
  );
  assert.equal(
    canRevokeOthers(partitionSessions({ current_session_id: 's1', items: [session('s1'), session('s2')] }, [], T0)),
    true,
  );
});

test('missing expiry is treated conservatively as still live', () => {
  const rows = partitionSessions({ current_session_id: 's1', items: [session('s2', { expires_at: null })] }, [], T0);
  assert.equal(rows[0].status, 'active');
  assert.equal(canRevokeOthers(rows), true, '宁可多给一次登出机会，不可谎报已失活');
});

test('current session pins to the top and others sort by recency', () => {
  const rows = partitionSessions(
    {
      current_session_id: 's-current',
      items: [
        session('s-old', { last_seen_at: '2026-09-02T00:00:00Z' }),
        session('s-current'),
        session('s-new', { last_seen_at: '2026-09-06T11:59:00Z' }),
      ],
    },
    [],
    T0,
  );
  assert.deepEqual(rows.map((r) => r.sessionId), ['s-current', 's-new', 's-old']);
});

test('workspace ids are translated into the names the user actually recognises', () => {
  const rows = partitionSessions(
    { current_session_id: null, items: [session('s1', { workspace_id: 'ws_b' }), session('s2', { workspace_id: 'ws_unknown' })] },
    [{ workspace_id: 'ws_b', name: 'Finland Pilot' }],
    T0,
  );
  assert.equal(rows[0].workspaceName, 'Finland Pilot');
  // 未知 id 退回原值而不是留空：留空会让用户在安全面板上看到一条没有归属的会话，
  // 那正是最需要指向某个空间的信息。
  assert.equal(rows[1].workspaceName, 'ws_unknown');
});

test('empty or malformed payloads degrade to an empty list, not a crash', () => {
  assert.deepEqual(partitionSessions(null, [], T0), []);
  assert.deepEqual(partitionSessions({}, [], T0), []);
  assert.equal(liveSessionCount([]), 0);
  assert.equal(canRevokeOthers([]), false);
});

test('auth methods are labelled, including ones the backend adds later', () => {
  assert.equal(methodLabel('google', true), 'Google');
  assert.equal(methodLabel('oidc', true), '企业 SSO');
  assert.equal(methodLabel('oidc', false), 'SSO');
  assert.equal(methodLabel('passkey', true), 'passkey', '未知方式原样显示，不伪装成 password');
  assert.equal(methodLabel(null, true), '—');
});

test('absent timestamps render as unknown instead of epoch zero', () => {
  // 缺值若走 Date 兜底会印出 1970-01-01，在安全面板上等于声称「这个会话 1970 年就存在」
  assert.equal(formatStamp(null, true), '未知');
  assert.equal(formatStamp(undefined, false), 'unknown');
  assert.equal(formatStamp('2026-09-06T11:59:00Z'), '2026-09-06 11:59');
});
