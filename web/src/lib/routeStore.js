// web/src/lib/routeStore.js
// R3.3 SPA 导航的状态源（2026-09-06）：把「当前在哪」从模块加载期的一次性求值
// 变成可订阅的状态，同时**不引入 react-router**。
//
// 为什么自己写这一层而不是装 router：本仓的入口结构被 4 个 node:test 字面量断言锁死
// （mainEntryPerformance / finlandBoard / developerPortal / renameGuard），换 router 等于
// 把那批断言连根拔掉；而否决 router 的**真实**代价只是「没有嵌套路由与路由级 loader」，
// 用户可感知的三项（URL 可分享、可书签、前进后退可用）这里都能给。
//
// 三条设计约束：
// 1. `getSnapshot` 必须返回**同一个对象引用**直到位置真的变化。useSyncExternalStore 每帧
//    比对快照，若每次 return 新对象就是无限重渲染。
// 2. 导航失败（同页、非本 origin、 modifier 键按住）一律回 false 让调用方**交还给浏览器**
//    走原生 `<a href>`。渐进增强的定义就是：增强逻辑判定不该接手时，原行为必须完整可用。
// 3. 只处理同源绝对路径。把 `https://evil.example` 塞进 SPA 导航会出现「点了侧边栏却在
//    站内跳转」的错乱，而外链本该开新页。
//
// 这里刻意不叫 `nav.sync` 也不叫 `handleSync`：SidebarNavigation 有一条既有断言禁止这两个名字
// （gridForecast.test.js:196-197），改名前先看那条测试。

import { resolveRoute } from './pageRouter.js';

let current = resolveRoute(globalThis.location?.pathname || '/', globalThis.location?.search || '');
const listeners = new Set();
let popsubscribed = false;

function sameRoute(a, b) {
  return a.href === b.href && JSON.stringify(a.params) === JSON.stringify(b.params);
}

function setRoute(next) {
  if (sameRoute(current, next)) return false;
  current = next;
  for (const listener of [...listeners]) {
    try {
      listener();
    } catch {
      /* 一个订阅者抛错不得影响其它订阅者 */
    }
  }
  return true;
}

/** 浏览器后退/前进：位置已由浏览器改好，这里只负责让订阅者重算。 */
export function syncRouteFromLocation() {
  setRoute(resolveRoute(globalThis.location?.pathname || '/', globalThis.location?.search || ''));
}

function ensurePopState() {
  if (popsubscribed || typeof globalThis.addEventListener !== 'function') return;
  globalThis.addEventListener('popstate', syncRouteFromLocation);
  popsubscribed = true;
}

export function getRouteSnapshot() {
  return current;
}

export function subscribeRoute(listener) {
  ensurePopState();
  listeners.add(listener);
  return () => listeners.delete(listener);
}

/** 站内 SPA 跳转。返回 false = 交给浏览器原生跳转。 */
export function navigateRoute(href, { replace = false } = {}) {
  const raw = String(href || '');
  if (!isInternalHref(raw)) return false;
  const cut = raw.indexOf('?');
  const path = cut === -1 ? raw : raw.slice(0, cut);
  const search = cut === -1 ? '' : raw.slice(cut);
  const next = resolveRoute(path, search);
  try {
    // 写回地址栏用**原样传进来的那串**而不是从 params 重建：Object.fromEntries 会把重复键
    // 折叠成最后一个（`?tag=a&tag=b` → `?tag=b`），重建即静默丢数据。解析与呈现分开，
    // 解析可以只认一种形态，呈现必须无损。
    if (replace) globalThis.history?.replaceState?.(null, '', path + search);
    else globalThis.history?.pushState?.(null, '', path + search);
  } catch {
    return false; // 沙箱里 pushState 会抛：让浏览器自己处理这次点击
  }
  setRoute(next);
  return true;
}

/**
 * `<a>` 点击拦截：只截「左键 + 无修饰键 + 无 target + 站内路径」这一种情况。
 *
 * 中间键/Ctrl/Cmd/Shift 点击的用户意图明确是「新标签打开」或「后台打开」，
 * 截下来就会变成站内跳转 —— 那是 SPA 导航最经典的倒退，且只在熟练用户身上出现。
 *
 * `href` 由调用方传入**它自己渲染的那个字符串**，而不是从 DOM 上读：锚点元素的
 * `.href` 属性是浏览器解析后的绝对 URL（`http://host/finland`），拿它判「是不是站内路径」
 * 会永远为 false，于是拦截静默失效 —— 而失效的表现只是「点了整页刷新」，看起来一切正常。
 */
export function shouldInterceptClick(event, href) {
  if (!event || event.defaultPrevented) return false;
  if (event.button !== undefined && event.button !== 0) return false;
  if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return false;
  const anchor = event.currentTarget;
  if (anchor && anchor.getAttribute && anchor.getAttribute('target')) return false;
  return isInternalHref(href ?? anchor?.getAttribute?.('href'));
}

/** 只有以单个 `/` 开头的路径算「站内可接管」。 */
export function isInternalHref(href) {
  const raw = typeof href === 'string' ? href : '';
  if (!raw.startsWith('/')) return false;
  // //evil.example 是协议相对 URL：以 / 开头但不是站内路径，接管它等于把外链变内链。
  if (raw.startsWith('//')) return false;
  return true;
}

/** 测试用：把状态复位到某个位置，不碰真实 history。 */
export function resetRouteForTests(href = '/') {
  current = resolveRoute(href.split('?')[0], href.includes('?') ? href.slice(href.indexOf('?')) : '');
  return current;
}
