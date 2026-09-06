// web/src/lib/apiIndex.js
// R3.4 ⌘K 命令面板的索引来源（2026-09-06）：把 OpenAPI 文档变成可搜索的命令列表。
//
// 为什么必须自动生成，而不是写一张端点表：实测本仓 OpenAPI 有 **219 个 path / 234 个操作 /
// 32 个 tag**（app.app.openapi()，2026-09-06）。手工维护这张表的结局是可以预见的 —— 加端点
// 的人不知道要同步这里，半年后面板搜不到新端点，而**没有任何测试会红**。这正是本仓反复踩过的
// 「有清单没读者」形态，所以索引直接取自运行时文档：文档变了面板就变，中间没有会过期的副本。
//
// 为什么读 `/api/openapi.json` 而不是 FastAPI 自带的 `/openapi.json`：nginx 的 `location /`
// 会把后者兜成 index.html（SPA fallback），Vite dev proxy 只转发 `/api`。用后者得到的会是
// 「JSON.parse 抛错 → 面板安静地只剩页面项」——功能缺失但不报错，最难发现的那类缺陷。
// 后端为此专门挂了一条路由，理由写在 backend/routes/health.py。
//
// 纯函数：不 fetch、不碰 DOM、不依赖 React。取文档与渲染都在 CommandPalette.jsx，
// 这样端点规模、排序、curl 生成这三件最容易错的事能在 node:test（本仓唯一硬阻断门）里跑。

/**
 * apiBase → 可直接粘进终端的 origin。
 *
 * 为什么要判：`VITE_API_BASE` 有两种合法形态 —— 部署里常见的 `/api`（同源，走 nginx 代理）
 * 与 web/.env.production 里的 `http://IP:8085/api`（直连后端）。文档里的 path 已经带 `/api`，
 * 所以拼 curl 时只能取 origin 部分，**不能把 apiBase 整个前缀再接一遍**（那会得到
 * `/api/api/v1/...`，一条看起来合理、实际必定 404 的命令）。
 */
export function originOf(apiBase = '') {
  const raw = String(apiBase || '').trim();
  const m = /^([A-Za-z][A-Za-z0-9+.-]*:\/\/[^/?#]+)/.exec(raw);
  return m ? m[1].replace(/\/+$/, '') : '';
}

/** 允许的 HTTP 方法：顺序即搜索结果里的优先顺序（读操作排在写操作前）。 */
const METHOD_ORDER = ['get', 'put', 'post', 'patch', 'delete'];
const METHOD_SET = new Set(METHOD_ORDER);
/** 一次最多索引多少个操作：面板只展示前 N 条命中，但索引本身要有上限，
 *  否则文档异常膨胀（或被人塞了个巨型 paths）会把每次按键的打分成本放大。 */
export const API_COMMAND_LIMIT = 600;

/** 索引 URL：跟随 apiBase 派生，**不另立第二个配置项**。
 *  面板与页面其它请求必须走同一个 base，否则会出现「页面能用、面板搜到的端点 404」。 */
export function openapiIndexUrl(apiBase = '/api') {
  const base = String(apiBase || '/api').trim().replace(/\/+$/, '') || '/api';
  return `${base}/openapi.json`;
}

function pickMethod(operations) {
  for (const method of METHOD_ORDER) {
    if (operations && METHOD_SET.has(method) && operations[method]) return method;
  }
  return null;
}

function firstTag(operation) {
  const tags = Array.isArray(operation?.tags) ? operation.tags : [];
  return typeof tags[0] === 'string' && tags[0].trim() ? tags[0].trim() : 'API';
}

/** 标题：summary → operationId → path。三层回落是为了「永不出现空条目的列表」。 */
function operationTitle(path, method, operation) {
  const summary = typeof operation?.summary === 'string' ? operation.summary.trim() : '';
  if (summary) return summary;
  const operationId = typeof operation?.operationId === 'string' ? operation.operationId.trim() : '';
  if (operationId) return operationId;
  return `${method.toUpperCase()} ${path}`;
}

/** 抽出路径参数名（`/api/v1/org/{org_id}` → ['org_id']）：curl 与「需要替换什么」的提示都靠它。 */
export function pathParams(path) {
  const names = [];
  for (const segment of String(path || '').split('/')) {
    const m = /^\{([A-Za-z0-9_]+)\}$/.exec(segment);
    if (m) names.push(m[1]);
  }
  return names;
}

/** 该操作要求的 query 参数（只列 required）：面板副标题里说清「还差什么」。 */
function requiredQuery(operation) {
  const params = Array.isArray(operation?.parameters) ? operation.parameters : [];
  return params
    .filter((p) => p?.in === 'query' && p?.required)
    .map((p) => (typeof p?.name === 'string' ? p.name : ''))
    .filter(Boolean);
}

/** 是否需要鉴权：操作级 security 优先，其次文档级默认。 */
function needsAuth(operation, doc) {
  const security = operation && Object.prototype.hasOwnProperty.call(operation, 'security')
    ? operation.security
    : doc?.security;
  return Array.isArray(security) && security.length > 0;
}

/**
 * OpenAPI 文档 → 扁平命令列表。
 * 非法输入一律返回空数组（面板退化到只有页面项），**绝不抛错**。
 */
export function buildApiCommands(doc) {
  const paths = doc && typeof doc === 'object' ? doc.paths : null;
  if (!paths || typeof paths !== 'object') return [];
  const commands = [];
  for (const [path, operations] of Object.entries(paths)) {
    if (!operations || typeof operations !== 'object') continue;
    for (const method of METHOD_ORDER) {
      const operation = operations[method];
      if (!operation || typeof operation !== 'object') continue;
      commands.push({
        id: `api:${method} ${path}`,
        kind: 'api',
        method,
        path,
        group: firstTag(operation),
        title: operationTitle(path, method, operation),
        params: pathParams(path),
        requiredQuery: requiredQuery(operation),
        hasBody: Boolean(operation.requestBody),
        deprecated: Boolean(operation.deprecated),
        auth: needsAuth(operation, doc),
        href: null, // API 条目不导航：它的动作是「复制 curl」，见 curlCommand
      });
      if (commands.length >= API_COMMAND_LIMIT) return commands;
    }
  }
  return commands;
}

/** 页面导航项（来自 SidebarNavigation 的同一份表）→ 命令。 */
export function pageCommands(items) {
  const list = Array.isArray(items) ? items : [];
  return list
    .filter((item) => item && typeof item.path === 'string' && item.path.startsWith('/'))
    .map((item) => ({
      id: `page:${item.id || item.path}`,
      kind: 'page',
      pageId: item.id,
      href: item.path,
      group: '页面',
      title: String(item.label || item.id || item.path),
      subtitle: typeof item.sub === 'string' ? item.sub : '',
      params: [],
      requiredQuery: [],
      hasBody: false,
      deprecated: false,
      auth: false,
    }));
}

function haystack(command) {
  const parts = [command.title, command.path, command.group, command.method, command.subtitle || ''];
  return parts.filter(Boolean).join(' ').toLowerCase();
}

/**
 * 打分：查询按空格切词，**每个词都要命中**（AND 语义）。
 *
 * 为什么不是模糊/子序列匹配：端点路径里充满 `a`、`e`、`s` 之类共字母，子序列匹配会让
 * 「输入 price 之前先打出的 pr」返回一百多条噪声，用户学到的是「面板不好用」。
 * 加分项只用于把「路径开头命中」排在「描述里才命中」的前面。
 */
export function scoreCommand(query, command) {
  const tokens = String(query || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
  if (!tokens.length) return command.kind === 'page' ? 1 : 0; // 空查询：页面项整体靠前
  const text = haystack(command);
  let total = 0;
  for (const token of tokens) {
    const inPath = command.path ? command.path.toLowerCase().indexOf(token) : -1;
    const inTitle = String(command.title || '').toLowerCase().indexOf(token);
    if (inPath === -1 && inTitle === -1 && text.indexOf(token) === -1) return -1;
    if (inPath === 0) total += 40;
    else if (inPath > 0) total += 24;
    if (inTitle === 0) total += 30;
    else if (inTitle > 0) total += 12;
    total += command.method === 'get' ? 4 : 2;
  }
  return total;
}

/** 搜索并按分数排序；分数相同按 path 稳定排序（避免每次按键结果顺序跳动）。 */
export function searchCommands(query, commands, limit = 12) {
  const list = Array.isArray(commands) ? commands : [];
  const scored = [];
  for (const command of list) {
    const score = scoreCommand(query, command);
    if (score >= 0) scored.push({ command, score });
  }
  scored.sort((a, b) => b.score - a.score || String(a.command.path || a.command.href).localeCompare(String(b.command.path || b.command.href)));
  const max = Number.isFinite(limit) && limit > 0 ? limit : 12;
  return scored.slice(0, max).map((entry) => entry.command);
}

/** 分组（面板按组渲染；无 group 的归入「其它」）。 */
export function groupCommands(commands) {
  const groups = new Map();
  for (const command of Array.isArray(commands) ? commands : []) {
    const key = command.group || '其它';
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(command);
  }
  return [...groups.entries()].map(([group, items]) => ({ group, items }));
}

/**
 * 生成一条可直接粘贴的 curl。
 *
 * 两条刻意的「不臆造」：
 * 1. 路径参数保留 `{name}` 占位并附一行注释要求替换 —— 填个 `1` 会让命令**看起来能跑**，
 *    而它实际打到的是别人可能存在的资源；对写操作这是比 404 更糟的失败方式。
 * 2. 有 requestBody 时不生成 `-d`：我们没有可靠的示例体，编一个 JSON 会让用户以为那是合法
 *    入参。改为一行注释指向开发者门户。
 */
export function curlCommand(command, { apiBase = '/api' } = {}) {
  if (!command || command.kind !== 'api') return '';
  const method = String(command.method || 'get').toUpperCase();
  // 文档里的 path 已含 /api 前缀：绝对 origin 只取协议+主机部分，相对形态则原样保留
  // （浏览器与 nginx 同源代理都能直接跑）。
  const target = `${originOf(apiBase)}${command.path || ''}`;

  const lines = [];
  if ((command.params || []).length) {
    lines.push(`# 需替换路径参数：${command.params.join('、')}`);
  }
  if ((command.requiredQuery || []).length) {
    lines.push(`# 必填查询参数：${command.requiredQuery.join('、')}`);
  }
  if (command.hasBody) {
    lines.push('# 需要 JSON 请求体（字段见开发者门户 /developer 的示例）');
  }
  const headers = [];
  if (command.auth) headers.push('-H "Authorization: Bearer $AUS_ELE_API_KEY"');
  if (command.hasBody) headers.push('-H "Content-Type: application/json"');
  // 单行成文，不带续行反斜杠：面板里是复制一段文本，多行续行在 PowerShell 里语义不同，
  // 而单行 curl 在 bash / zsh / PowerShell(`curl.exe`) 下都是同一条命令。
  const rendered = `curl -X ${method} "${target}"${headers.length ? ` ${headers.join(' ')}` : ''}`;
  lines.push(rendered);
  return lines.join('\n');
}
