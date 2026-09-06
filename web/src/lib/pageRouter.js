export function resolveRootPage(pathname = '/') {
  if (pathname.startsWith('/login')) {
    return 'login';
  }
  if (pathname.startsWith('/register')) {
    return 'register';
  }
  if (pathname.startsWith('/verify-email')) {
    return 'verifyEmail';
  }
  if (pathname.startsWith('/invite')) {
    return 'invite';
  }
  if (pathname.startsWith('/forgot') || pathname.startsWith('/reset')) {
    return 'forgot';
  }
  if (pathname.startsWith('/account')) {
    return 'account';
  }
  if (pathname.startsWith('/pricing')) {
    return 'pricing';
  }
  if (pathname.startsWith('/legal')) {
    return 'legal';
  }
  // R6.1（2026-09-06）：方法论白皮书公开页。与 /legal 同为「承诺的出处」类文档：
  // 定价页 Pro 套餐承诺了白皮书，这里必须能真的到达，否则那是一句不实陈述。
  if (pathname.startsWith('/methodology')) {
    return 'methodology';
  }
  if (pathname.startsWith('/reports')) {
    return 'reports';
  }
  if (pathname.startsWith('/help')) {
    return 'help';
  }
  if (pathname.startsWith('/wem')) {
    return 'wem';
  }
  if (pathname.startsWith('/finland')) {
    return 'finland';
  }
  if (pathname.startsWith('/fingrid')) {
    return 'fingrid';
  }
  if (pathname.startsWith('/developer')) {
    return 'developer';
  }
  if (pathname.startsWith('/agent')) {
    return 'agent';
  }
  return 'aemo';
}

// ---------------------------------------------------------------------------
// R3.2 路由解析（2026-09-06）：在不动上面那个函数的前提下加一层结构化解析。
//
// 为什么需要这一层：`resolveRootPage` 只回答「挂哪个页面」，而页面内部的二段分发
// （AccountPage 按 pathname 挑 tab、LegalPage 挑文档、FingridPage 挑序列）此前各自
// `new URLSearchParams` + `pathname.startsWith` 现编。现编的代价不是重复几行，而是
// **同一件事有多个答案**：`/account/privacy` 到底是 tab 还是子路由，两处判断可以给出
// 两种结论，而分歧只在用户点到那个组合时才暴露。
//
// 兜底仍然全部走 resolveRootPage —— 包括它那句 `return 'aemo'`。旧链接零失效是硬约束：
// 这一层新增的任何分支都不得改变已有 URL 的归属页。
// ---------------------------------------------------------------------------

const SECTION_PREFIXES = {
  account: ['privacy', 'org', 'members', 'api-keys', 'alerts', 'audit', 'overview'],
  legal: ['terms', 'privacy', 'dpa', 'aup', 'cookies'],
};

/** 把 `'/fingrid/317'` 与 `'/fingrid?x=1'` 这类输入拆成 { path, search }。 */
function splitLocation(pathname = '/') {
  const raw = String(pathname || '/');
  const cut = raw.indexOf('?');
  if (cut === -1) return { path: raw, search: '' };
  return { path: raw.slice(0, cut), search: raw.slice(cut) };
}

/**
 * 页内段落：取路径的第二段，且只认白名单。
 *
 * 为什么不直接把第二段原样返回：`/account/anything` 会让人以为存在这个 tab。返回 null
 * 时调用方按「未知子路径」处理（回落到该页默认视图），比凭空造一个空 tab 好；而
 * `/fingrid/317` 这种 id 型子路径不属于「段落」，走 params.id，两件事不混在一起。
 */
function resolveSection(page, path) {
  const allowed = SECTION_PREFIXES[page];
  if (!allowed) return null;
  const segments = path.split('/').filter(Boolean);
  const candidate = segments[1] || (page === 'account' ? 'overview' : null);
  return allowed.includes(candidate) ? candidate : null;
}

/**
 * 解析一条位置为 `{ page, section, params, href }`。
 *
 * `params` 是 query 的**全部**键值（不只筛选器那几个）：调用方要的是「一处解析」，
 * 各页再自己挑认识的键。未知键原样带着，正是「保留 ?window=7d」这类页面自带参数的前提。
 */
export function resolveRoute(pathname = '/', search = '') {
  const { path, search: embedded } = splitLocation(pathname);
  let params = {};
  try {
    const qs = String(search || embedded || '').replace(/^\?/, '');
    params = Object.fromEntries(new URLSearchParams(qs).entries());
  } catch {
    params = {};
  }
  const page = resolveRootPage(path);
  const section = resolveSection(page, path);
  // fingrid 的序列 id 走 params.id：它不是「段落」而是「资源」，且既可能来自路径也可能来自 query。
  if (page === 'fingrid' && !params.id) {
    const segments = path.split('/').filter(Boolean);
    if (segments[1]) params = { ...params, id: segments[1] };
  }
  return { page, section, params, href: path };
}
