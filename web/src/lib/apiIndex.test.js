// web/src/lib/apiIndex.test.js
// R3.4 ⌘K 索引层的判据（2026-09-06）。
//
// 这一层最要紧的性质是「面板永不空白、也永不谎报」。索引来自运行时拉取的 OpenAPI 文档，
// 意味着它随时可能拿到：null、HTML 字符串（被 SPA fallback 兜掉时就是这个形态）、
// 缺 paths 的半截文档、被人手改过的巨型文档。任何一种都必须退化为「只剩页面项」，
// 而不是抛错把整个面板变成卡死的遮罩层。
//
// 另一半是 curl：面板对外的唯一动作就是「复制一条能用的命令」。生成一条看起来能跑、
// 实际打到别人资源上的命令，比不生成更糟。

import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  API_COMMAND_LIMIT,
  buildApiCommands,
  curlCommand,
  groupCommands,
  openapiIndexUrl,
  originOf,
  pageCommands,
  pathParams,
  scoreCommand,
  searchCommands,
} from './apiIndex.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const DOC = {
  paths: {
    '/api/v1/anomalies/{region}': {
      get: {
        tags: ['Anomalies'],
        summary: '异常检测',
        parameters: [{ name: 'days', in: 'query', required: true }],
        security: [{ HTTPBearer: [] }],
      },
    },
    '/api/v1/backtest': {
      post: { tags: ['Backtest'], summary: '回测', requestBody: { content: {} } },
    },
    '/api/health': { get: { tags: ['Health'], summary: '健康检查' } },
  },
};

test('index url follows apiBase and never double-prefixes /api', () => {
  // 必须是「同一个 base」：另立配置项的结局是页面能用而面板搜到的端点 404。
  assert.equal(openapiIndexUrl('/api'), '/api/openapi.json');
  assert.equal(openapiIndexUrl('http://10.0.0.1:8085/api/'), 'http://10.0.0.1:8085/api/openapi.json');
  assert.equal(openapiIndexUrl(''), '/api/openapi.json');
  assert.equal(openapiIndexUrl(undefined), '/api/openapi.json');
});

test('originOf keeps only scheme+host so curl cannot grow a second /api', () => {
  assert.equal(originOf('http://10.0.0.1:8085/api'), 'http://10.0.0.1:8085');
  assert.equal(originOf('https://example.com:8443/api/v1'), 'https://example.com:8443');
  // 相对形态（同源 nginx 代理）没有 origin：返回空串，path 原样就是可执行的地址
  assert.equal(originOf('/api'), '');
  assert.equal(originOf(''), '');
  assert.equal(originOf(undefined), '');
});

test('buildApiCommands flattens every documented operation', () => {
  const commands = buildApiCommands(DOC);
  assert.equal(commands.length, 3);
  assert.deepEqual(
    commands.map((c) => c.id),
    ['api:get /api/v1/anomalies/{region}', 'api:post /api/v1/backtest', 'api:get /api/health'],
  );
  const [anomaly, backtest, health] = commands;
  assert.deepEqual(anomaly.params, ['region']);
  assert.deepEqual(anomaly.requiredQuery, ['days']);
  assert.equal(anomaly.auth, true);
  assert.equal(anomaly.group, 'Anomalies');
  assert.equal(backtest.hasBody, true);
  assert.equal(health.auth, false, '无 security 的操作不得被标成需要鉴权');
  assert.equal(commands.every((c) => c.href === null), true, 'API 条目的动作是复制 curl，不是导航');
});

test('degenerate documents degrade to an empty index instead of throwing', () => {
  // 每个用例都对应一种真实会拿到的东西，尤其是第一种：
  // 端点挂错位置时 nginx 的 SPA fallback 会返回 index.html，fetch().json() 直接抛。
  for (const bad of [null, undefined, {}, 42, 'not json', [], { paths: null }, { paths: [] }, { paths: { '/x': null } }]) {
    assert.doesNotThrow(() => buildApiCommands(bad), `输入：${JSON.stringify(bad)}`);
    assert.deepEqual(buildApiCommands(bad), [], `输入：${JSON.stringify(bad)}`);
  }
  // 非 HTTP 动词的键（parameters/servers 这类 path-item 级字段）不得被当成操作
  assert.deepEqual(buildApiCommands({ paths: { '/x': { parameters: [{}], servers: [] } } }), []);
});

test('index is capped so a bloated document cannot amplify every keystroke', () => {
  const paths = {};
  for (let i = 0; i < API_COMMAND_LIMIT + 50; i += 1) paths[`/api/v1/t/${i}`] = { get: { summary: `t${i}` } };
  const commands = buildApiCommands({ paths });
  assert.equal(commands.length, API_COMMAND_LIMIT);
});

test('title falls back through summary, operationId, then the raw line', () => {
  const doc = {
    paths: {
      '/a': { get: {} },
      '/b': { get: { operationId: 'fetchThing' } },
      '/c': { get: { summary: '   ' } },
    },
  };
  const titles = buildApiCommands(doc).map((c) => c.title);
  assert.deepEqual(titles, ['GET /a', 'fetchThing', 'GET /c']);
});

test('page commands ignore anything that is not a root-relative path', () => {
  const items = [
    { id: 'wem', path: '/wem', label: 'WEM', sub: '西澳' },
    { id: 'ext', path: 'https://evil.example', label: '外链' },
    { id: 'nopath', label: '无路径' },
    null,
  ];
  const commands = pageCommands(items);
  assert.equal(commands.length, 1);
  assert.equal(commands[0].href, '/wem');
  assert.equal(commands[0].kind, 'page');
  assert.equal(commands[0].group, '页面');
  assert.deepEqual(pageCommands(null), []);
});

test('search uses AND semantics across whitespace separated tokens', () => {
  const commands = buildApiCommands(DOC);
  // 「back 测」两个词都必须命中同一条目；OR 语义会把 anomalies 也带进来
  assert.deepEqual(searchCommands('back 测', commands).map((c) => c.path), ['/api/v1/backtest']);
  assert.equal(scoreCommand('anomalies region', commands[0]) > 0, true);
  assert.equal(scoreCommand('anomalies nonexistent', commands[0]), -1);
  assert.equal(searchCommands('zzzznotathing', commands).length, 0);
});

test('empty query surfaces pages first so the panel is never blank on open', () => {
  const commands = [...pageCommands([{ id: 'wem', path: '/wem', label: 'WEM' }]), ...buildApiCommands(DOC)];
  const results = searchCommands('', commands, 12);
  assert.equal(results[0].kind, 'page');
  assert.equal(results.length, commands.length);
});

test('ranking prefers path-prefix hits and is stable for equal scores', () => {
  const commands = buildApiCommands(DOC);
  // 路径开头命中（/api/v1/anomalies）+ GET 优先，必须排在只在组名里命中的条目之前
  assert.equal(searchCommands('anomalies', commands, 1)[0].path, '/api/v1/anomalies/{region}');
  // 'api' 在两条 path 里都位于索引 0 → 同分，此时必须按 path 稳定排序而不是按文档顺序
  // （每次按键顺序跳动会毁掉方向键的肌肉记忆）
  assert.deepEqual(
    searchCommands('api', commands, 12).map((c) => c.path),
    ['/api/health', '/api/v1/anomalies/{region}', '/api/v1/backtest'],
  );
});

test('limit is honoured and a non-numeric limit degrades to the default', () => {
  const commands = buildApiCommands(DOC);
  assert.equal(searchCommands('api', commands, 2).length, 2);
  assert.equal(searchCommands('api', commands, 0).length, 3);
  assert.equal(searchCommands('api', commands, NaN).length, 3);
  assert.deepEqual(searchCommands('x', null), []);
});

test('grouping keeps first-seen order and defaults missing groups', () => {
  const groups = groupCommands([
    { group: 'B', id: 1 }, { id: 2 }, { group: 'A', id: 3 }, { group: 'B', id: 4 },
  ]);
  assert.deepEqual(groups.map((g) => g.group), ['B', '其它', 'A']);
  assert.equal(groups[0].items.length, 2);
  assert.deepEqual(groupCommands(null), []);
});

test('path params only accept bare brace tokens', () => {
  assert.deepEqual(pathParams('/api/v1/org/{org_id}/ws/{wsId}'), ['org_id', 'wsId']);
  assert.deepEqual(pathParams('/api/v1/org'), []);
  assert.deepEqual(pathParams('/api/{not a name}'), []);
  assert.deepEqual(pathParams('{leading}'), ['leading']);
  assert.deepEqual(pathParams(undefined), []);
});

test('curl keeps path placeholders instead of inventing an id', () => {
  const [anomaly] = buildApiCommands(DOC);
  const cmd = curlCommand(anomaly, { apiBase: 'http://10.0.0.1:8085/api' });
  // 填 `1` 会让命令看起来能跑而实际打到别人的资源上；写操作这比 404 更糟。
  assert.ok(cmd.includes('/api/v1/anomalies/{region}'), cmd);
  assert.ok(cmd.includes('需替换路径参数：region'), cmd);
  assert.ok(cmd.includes('必填查询参数：days'), cmd);
  assert.ok(cmd.includes('-H "Authorization: Bearer $AUS_ELE_API_KEY"'), cmd);
  assert.ok(/curl -X GET "http:\/\/10\.0\.0\.1:8085\/api\/v1\/anomalies\/\{region\}"/.test(cmd), cmd);
  // 同源相对形态（nginx 代理部署）：path 本身已带 /api，前再接一遍就是 /api/api/... 必定 404
  assert.ok(curlCommand(anomaly, { apiBase: '/api' }).includes('"/api/v1/anomalies/{region}"'));
  assert.equal(curlCommand(anomaly, { apiBase: '/api' }).includes('/api/api/'), false);
});

test('curl does not fabricate a request body', () => {
  const [, backtest] = buildApiCommands(DOC);
  const cmd = curlCommand(backtest, { apiBase: '/api' });
  assert.equal(cmd.includes('-d'), false, '编造的示例体会被当成合法入参');
  assert.ok(cmd.includes('开发者门户'), cmd);
  assert.ok(cmd.includes('-H "Content-Type: application/json"'), cmd);
});

test('curl is a single physical line so it pastes identically into bash and powershell', () => {
  const commands = buildApiCommands(DOC);
  for (const command of commands) {
    for (const line of curlCommand(command, { apiBase: '/api' }).split('\n')) {
      if (line.startsWith('#')) continue;
      assert.equal(line.includes('\\'), false, `续行反斜杠在 PowerShell 里是转义：${line}`);
    }
  }
});

test('curl degrades quietly for non-api commands', () => {
  assert.equal(curlCommand(null), '');
  assert.equal(curlCommand({ kind: 'page', href: '/wem' }), '');
});

test('the panel does not hardcode an endpoint table', () => {
  // Spec §129：索引必须从 OpenAPI 自动生成 —— 实测 234 个操作，手工维护不可能。
  // 门的方向：面板里出现任何 '/api/...' 字面量都说明有人开始抄第二份端点表。
  const source = fs.readFileSync(path.resolve(__dirname, '../components/CommandPalette.jsx'), 'utf8');
  const offenders = [...source.matchAll(/["'`]\/api\/[A-Za-z0-9_]/g)].map((m) => m[0]);
  assert.deepEqual(offenders, [], `CommandPalette 里出现硬编码端点路径：${offenders.join(', ')}`);
  assert.ok(/from '\.\.\/lib\/apiIndex\.js'/.test(source), '端点索引必须来自 lib/apiIndex.js');
});
