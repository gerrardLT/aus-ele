// web/src/lib/dataRightsApi.test.js
// R1.7 前端判据测试。核心一条是拿后端源码当参照物：前端把 URL 拼错的表现是「点了没反应」，
// 纯前端测试永远绿，只有比对 routes/data_rights_routes.py 才能抓住。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  ACCOUNT_PATH,
  BACKEND_PREFIX,
  DELETION_PENDING_NOTICE,
  dataRightsEndpoints,
  deletionUiState,
  endpointUnavailable,
  exportUiState,
  graceDaysRemaining,
  loginNoticeCopy,
  mustReauthenticateAfterDeletion,
  ownershipBlockCopy,
  readLoginNotice,
  shouldPollExport,
} from './dataRightsApi.js';
import { isDataRightsEnabled } from './dataRights.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const readUp = (...segments) => fs.readFileSync(path.resolve(__dirname, ...segments), 'utf8');
const ROUTES_SOURCE = readUp('../../../backend/routes/data_rights_routes.py');
const SERVICE_SOURCE = readUp('../../../backend/services/data_rights.py');
const LOGIN_SOURCE = readUp('../pages/LoginPage.jsx');
const ACCOUNT_SOURCE = readUp('../pages/AccountPage.jsx');
const PANEL_SOURCE = readUp('../components/account/DataPrivacyPanel.jsx');

/** 从后端源码抽出该模块声明的全部路由（prefix + 子路径）。 */
function parseBackendRoutes(source) {
  const prefix = /APIRouter\(prefix="([^"]+)"/.exec(source);
  const decorator = /@router\.(get|post|put|delete)\(\s*"([^"]+)"/g;
  return [...source.matchAll(decorator)].map(
    (hit) => `${hit[1].toUpperCase()} ${prefix ? prefix[1] : ''}${hit[2]}`
  );
}

test('frontend endpoint table matches the routes the backend actually declares', () => {
  const declared = new Set(parseBackendRoutes(ROUTES_SOURCE));
  assert.ok(declared.size >= 6, `后端只解析出 ${declared.size} 条路由，解析器或路由文件变了`);

  const endpoints = dataRightsEndpoints('/api');
  // 参数段还原成后端的写法再比：前端填的是真 id，后端声明的是 {export_id}。
  const download = endpoints.exportDownload('exp_1').replace('exp_1', '{export_id}');
  const called = [
    'POST /api/v1/account/export',
    'GET /api/v1/account/export',
    `GET ${download}`,
    'POST /api/v1/account/delete',
    'GET /api/v1/account/delete',
    'POST /api/v1/account/delete/cancel',
  ];
  for (const route of called) {
    assert.ok(declared.has(route), `前端要调用后端没有的路由：${route}`);
  }
});

test('the prefix the frontend builds is the one the backend router mounts', () => {
  const prefix = /APIRouter\(prefix="([^"]+)"/.exec(ROUTES_SOURCE);
  assert.ok(prefix, '后端 data_rights_routes 里找不到 APIRouter(prefix=...)');
  assert.equal(BACKEND_PREFIX, prefix[1]);
  // 本仓 API_BASE 自带 '/api'（见 lib/apiBase.js）：拼出 '/api/api/...' 是一个必然 404
  // 的 URL，而且只在运行时暴露，所以这条得钉住。
  assert.equal(ACCOUNT_PATH, '/v1/account');
  const endpoints = dataRightsEndpoints('/api');
  assert.equal(endpoints.exportSubmit, '/api/v1/account/export');
  for (const url of [
    endpoints.exportSubmit,
    endpoints.exportStatus,
    endpoints.exportDownload('e1'),
    endpoints.deletionSubmit,
    endpoints.deletionStatus,
    endpoints.deletionCancel,
  ]) {
    assert.ok(!url.includes('/api/api'), `双前缀：${url}`);
  }
  // 生产态 API_BASE 是绝对地址，同样不能重复带段
  assert.equal(
    dataRightsEndpoints('http://127.0.0.1:8085/api').deletionCancel,
    'http://127.0.0.1:8085/api/v1/account/delete/cancel'
  );
});

test('export only claims self-service when the endpoint is really online', () => {
  // flag 开着但端点 404（route 模块 import 失败被静默降级）→ 必须收起来，
  // 否则隐私页那句话当场变成不实陈述。
  assert.equal(
    exportUiState({ flagOn: true, probeStatusCode: 404, row: null }),
    'unavailable'
  );
  assert.equal(exportUiState({ flagOn: true, probeStatusCode: 405, row: null }), 'unavailable');
  assert.equal(exportUiState({ flagOn: true, probeStatusCode: 200, row: null }), 'idle');
  assert.equal(exportUiState({ flagOn: false, probeStatusCode: 200, row: null }), 'disabled');
  assert.ok(isDataRightsEnabled({ VITE_DATA_RIGHTS_UI: 'true' }));
});

test('export state machine covers every status the backend can return', () => {
  const states = {
    queued: 'inflight',
    running: 'inflight',
    completed: 'ready',
    failed: 'failed',
  };
  for (const [status, expected] of Object.entries(states)) {
    const row = { status, download_ready: status === 'completed' };
    assert.equal(
      exportUiState({ flagOn: true, probeStatusCode: 200, row }),
      expected,
      `后端 status=${status} 前端没有对应状态`
    );
  }
  // 行说 completed 但文件已过期：不能显示「下载」，要点亮的是一条能走通的路。
  assert.equal(
    exportUiState({ flagOn: true, probeStatusCode: 200, row: { status: 'completed', download_ready: false } }),
    'expired'
  );
});

test('already_queued still starts polling', () => {
  // 后端对重复提交回 202 + already_queued（在先那次会完成），不是失败。
  for (const status of ['queued', 'already_queued', 'running']) {
    assert.equal(shouldPollExport({ status }), true, status);
  }
  for (const status of ['completed', 'failed', undefined, 'none']) {
    assert.equal(shouldPollExport({ status }), false, String(status));
  }
});

test('a granted deletion always sends the user back to the login page', () => {
  assert.equal(
    mustReauthenticateAfterDeletion({ status: 'pending', session_revoked: true }),
    true
  );
  // 缺 session_revoked 一律当作「不需要跳登录」：宁多留一个会话，也不要把成功做成闪断。
  assert.equal(mustReauthenticateAfterDeletion({ status: 'pending' }), false);
  assert.equal(mustReauthenticateAfterDeletion({ status: 'already_pending', session_revoked: true }), false);
  assert.equal(mustReauthenticateAfterDeletion(undefined), false);
});

test('deletion state machine never renders an entry for an executed deletion', () => {
  assert.equal(deletionUiState(null), 'idle');
  assert.equal(deletionUiState({ status: 'none' }), 'idle');
  assert.equal(deletionUiState({ status: 'pending' }), 'pending');
  assert.equal(deletionUiState({ status: 'cancelled' }), 'cancelled');
});

test('ownership block copy names the organizations the backend listed', () => {
  const detail = {
    code: 'ownership_transfer_required',
    organizations: [{ organization_id: 'org_a', name: 'Acme' }, { organization_id: 'org_b' }],
  };
  const zh = ownershipBlockCopy(detail, true);
  assert.match(zh, /Acme/);
  assert.match(zh, /org_b/, '没有 name 时要回落到 id，不能让那个组织从提示里消失');
  assert.match(zh, /移交/);
  assert.match(ownershipBlockCopy({ organizations: [] }, false), /Transfer organization ownership/);
  assert.match(ownershipBlockCopy(undefined, true), /移交/);
});

test('grace countdown degrades to null instead of NaN', () => {
  const now = Date.parse('2026-09-06T00:00:00Z');
  assert.equal(graceDaysRemaining({ scheduled_delete_at: '2026-10-06T00:00:00Z' }, now), 30);
  assert.equal(graceDaysRemaining({ scheduled_delete_at: 'not-a-date' }, now), null);
  assert.equal(graceDaysRemaining({}, now), null);
  assert.equal(graceDaysRemaining(undefined), null);
  // 已过期不显示「剩余 -3 天」。
  assert.equal(graceDaysRemaining({ scheduled_delete_at: '2026-09-01T00:00:00Z' }, now), null);
});

test('endpointUnavailable is the only meaning given to 404 here', () => {
  assert.equal(endpointUnavailable(404), true);
  assert.equal(endpointUnavailable(405), true);
  for (const code of [200, 401, 403, 409, 410, 500]) {
    assert.equal(endpointUnavailable(code), false, `${code} 不该被当成「端点不存在」`);
  }
});

test('export column redaction list covers the credential columns in the schema', () => {
  // 后端 services/data_rights.py 的 CREDENTIAL_COLUMNS 是导出脱敏的唯一防线。
  // 这里用源码断言把关键列钉住：漏一列就是「导出文件里躺着一条可用凭据」。
  const block = /CREDENTIAL_COLUMNS\s*=\s*frozenset\(\s*\{([\s\S]*?)\}/.exec(SERVICE_SOURCE);
  assert.ok(block, '后端 CREDENTIAL_COLUMNS 定义形状变了，脱敏防线可能已经失效');
  const listed = [...block[1].matchAll(/"([a-z_]+)"/g)].map((m) => m[1]);
  for (const column of ['session_token', 'token', 'token_hash', 'invite_token', 'api_key', 'password_hash', 'password_salt']) {
    assert.ok(listed.includes(column), `导出未剔除凭据列 ${column}`);
  }
});

test('login notice explains that signing in again is how you cancel', () => {
  const zh = loginNoticeCopy(DELETION_PENDING_NOTICE, true);
  assert.match(zh, /删除请求已排期/);
  assert.match(zh, /撤销/, '中文文案必须给出可执行的撤销路径');
  assert.match(zh, /宽限/);
  const en = loginNoticeCopy(DELETION_PENDING_NOTICE, false);
  assert.match(en, /grace period/i);
  assert.match(en, /Cancel/i);
  // 未知值绝不产出横幅：凭空冒出一段账户相关的提示比不提示更让人不安。
  assert.equal(loginNoticeCopy('whatever', true), null);
  assert.equal(loginNoticeCopy(null, true), null);
  assert.equal(loginNoticeCopy(undefined, true), null);
  assert.equal(loginNoticeCopy('', true), null);
});

test('readLoginNotice parses a raw location.search and survives junk', () => {
  assert.equal(readLoginNotice(`?notice=${DELETION_PENDING_NOTICE}`, true), loginNoticeCopy(DELETION_PENDING_NOTICE, true));
  assert.equal(readLoginNotice('?next=%2Faccount%2Fprivacy', true), null);
  assert.equal(readLoginNotice('', true), null);
  assert.equal(readLoginNotice(undefined, true), null);
  assert.equal(readLoginNotice(42, true), null, '非字符串（SSR/测试里可能的 undefined、数字）不能抛');
});

test('deletion handoff is wired on both ends, not just in the lib', () => {
  // 这一条是整组里最容易悄悄失效的：lib 单测全绿，但登录页从没读过 query，
  // 于是用户撞上的仍然是一堵无解释的登录墙。必须拿页面源码断言。
  assert.match(LOGIN_SOURCE, /readLoginNotice\(/, 'LoginPage 不再读 notice，删除受理后会跳进无解释的登录墙');
  assert.match(LOGIN_SOURCE, /location\?\.search/, 'LoginPage 必须从真实 URL 取值，而不是写死');
  assert.match(ACCOUNT_SOURCE, /notice=\$\{DELETION_PENDING_NOTICE\}/, 'AccountPage 跳转必须复用 lib 常量');
  assert.match(ACCOUNT_SOURCE, /onSessionEnded=\{handleDeletionAccepted\}/, '面板的成功回调没接上，令牌已作废却仍停在账户页');
});

test('privacy panel is reachable from the account shell and is code-split like its siblings', () => {
  assert.match(ACCOUNT_SOURCE, /onPrivacyRoute \? <DataPrivacyPanel/, 'tab 存在但内容空转：渲染分支没接上');
  assert.match(ACCOUNT_SOURCE, /const DataPrivacyPanel = lazy\(/, '子页面一律 lazy，别把它塞回主 chunk');
});

test('every user-facing grace period matches the number the backend schedules', () => {
  // 「30 天宽限期」出现在三处：隐私政策第 5 条（法律陈述）、面板提交前说明、永久删除
  // 前的二次确认勾选。三处都是拿后端 DEFAULT_GRACE_DAYS 写死过来的字面量，改一处忘两处
  // 的后果是：隐私页与确认框一起描述一个系统并不提供的期限 —— 那正是 Spec §232 用整条
  // 顺序约束要防的不实陈述，只是换了个方向发生（端点先于文案变化）。
  const constant = /DEFAULT_GRACE_DAYS\s*=\s*(\d+)/.exec(SERVICE_SOURCE);
  assert.ok(constant, '后端 DEFAULT_GRACE_DAYS 定义形状变了，这条防线本身可能已失效');
  const days = constant[1];
  assert.ok(Number(days) >= 1, `宽限期为 ${days} 天等于没有可撤销窗口`);
  const sources = {
    '隐私政策文案': readUp('./dataRights.js'),
    '数据与隐私面板': PANEL_SOURCE,
  };
  for (const [label, source] of Object.entries(sources)) {
    assert.match(source, new RegExp(`${days} 天宽限期`), `${label}的中文宽限天数与后端不一致`);
    assert.match(source, new RegExp(`${days}-day grace period`), `${label}的英文宽限天数与后端不一致`);
  }
});
