// web/src/components/CommandPalette.jsx
// R3.4 ⌘K 命令面板（2026-09-06）。
//
// 两条硬规定的落点：
// 1. **只能被动态 import**。本文件不得出现在任何静态 import 链上（`r3NavGuards.test.js`
//    常驻检查，并且 build 后会核对入口 chunk 里没有它）。入口预算只剩 6%，一个只在用户
//    按下组合键时才需要的东西没有理由占它。
// 2. **端点索引取自 OpenAPI**（判据与打分全在 lib/apiIndex.js，那里有 node:test 覆盖）。
//    面板自己只负责渲染与键盘，不解析文档 —— 否则「234 个端点」这件事就没有测试面了。
//
// 失败路径的设计目标只有一个：面板**永远能关、永远能用**。文档拉不下来就只剩页面项
// （并说明原因），剪贴板不可用就把 curl 显示出来让人自己复制。这些都是「用户已经按下
// ⌘K」之后发生的事，此时任何抛错都会把一个可用功能变成一次卡死的遮罩层。

import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { navItems } from './SidebarNavigation.jsx';
import { getRouteSnapshot, navigateRoute } from '../lib/routeStore.js';
import { resolveRootPage } from '../lib/pageRouter.js';
import { isFlagEnabled } from '../lib/flags.js';
import { buildApiCommands, curlCommand, openapiIndexUrl, pageCommands, searchCommands } from '../lib/apiIndex.js';

const MAX_RESULTS = 12;

// 文档只取一次：每次打开面板都重拉一份 500KB 的 JSON 是没有必要的浪费。
// 失败也记住（记为 rejected 的 promise 会被下方 .catch 消化成空索引），但不重试 ——
// 重试时机交给「刷新页面」，因为一个挂掉的后端不会因为面板再打一次就好。
let docPromise = null;

function loadDoc(apiBase) {
  if (docPromise) return docPromise;
  const url = openapiIndexUrl(apiBase);
  docPromise = fetch(url, { credentials: 'same-origin' })
    .then((res) => (res.ok ? res.json() : Promise.reject(new Error(`HTTP ${res.status}`))))
    .catch(() => null);
  return docPromise;
}

/** 把选中的页面命令落地。返回 true 表示「已交给浏览器/路由，可以关面板」。 */
function activatePage(command) {
  const href = command.href || '/';
  const samePage = resolveRootPage(href.split('?')[0]) === getRouteSnapshot().page;
  // spaNav 关掉时面板也退回整页跳转：两个 flag 各管各的（一个管面板在不在，一个管导航方式），
  // 组合出「面板开着但导航行为与 R3 前一致」才是可预期的回滚语义。
  if (!samePage && isFlagEnabled(import.meta.env, 'spaNav') && navigateRoute(href)) return true;
  try { globalThis.location.href = href; } catch { return false; /* 沙箱里赋值失败：留在面板里比白屏好 */ }
  return true;
}

export default function CommandPalette({ open, onClose, lang = 'zh', apiBase = '/api' }) {
  const zh = lang === 'zh';
  const [query, setQuery] = useState('');
  const [apiCommands, setApiCommands] = useState([]);
  const [docState, setDocState] = useState('loading'); // loading | ready | empty
  const [notice, setNotice] = useState('');
  const [curlText, setCurlText] = useState('');
  // 复制结果的三态。刻意不用「把中文文案再 includes 一遍」判断该显示哪个兜底输入框 ——
  // 那种写法在改文案时会静默失效（语言换了，判断条件还留着旧字符串）。
  const [copyMode, setCopyMode] = useState('none'); // none | copied | manual
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef(null);
  const listRef = useRef(null);

  const pages = useMemo(() => pageCommands(navItems(lang)), [lang]);

  useEffect(() => {
    if (!open) return undefined;
    let cancelled = false;
    loadDoc(apiBase).then((doc) => {
      if (cancelled) return;
      const commands = buildApiCommands(doc);
      setApiCommands(commands);
      setDocState(commands.length ? 'ready' : 'empty');
    });
    return () => { cancelled = true; };
  }, [open, apiBase]);

  // 打开即清空：上一次搜索留下的结果和光标位置对下一次调用是干扰项。
  useEffect(() => {
    if (!open) return;
    setQuery('');
    setCursor(0);
    setNotice('');
    setCurlText('');
    setCopyMode('none');
    try { inputRef.current?.focus?.(); } catch { /* 无焦点管理能力的宿主环境照常可用 */ }
  }, [open]);

  const results = useMemo(
    () => searchCommands(query, [...pages, ...apiCommands], MAX_RESULTS),
    [query, pages, apiCommands],
  );

  useEffect(() => { setCursor(0); }, [query]);

  const copyCurl = useCallback(async (command) => {
    const text = curlCommand(command, { apiBase });
    if (!text) return;
    setCurlText(text);
    let copied = false;
    try {
      if (globalThis.navigator?.clipboard?.writeText) {
        await globalThis.navigator.clipboard.writeText(text);
        copied = true;
      }
    } catch {
      copied = false;
    }
    if (!copied) {
      // 生产站点跑在 http://IP 上 —— 非安全上下文里 navigator.clipboard 根本不存在，
      // 所以这条回退不是保险而是主路径之一。execCommand 已废弃但仍是唯一能在 http 下
      // 完成复制的手段；再不行就把文本显示出来让人手动复制，**绝不谎称已复制**。
      try {
        const ta = document.createElement('textarea');
        ta.value = text;
        ta.setAttribute('readonly', 'readonly');
        ta.style.position = 'fixed';
        ta.style.opacity = '0';
        document.body.appendChild(ta);
        ta.select();
        copied = document.execCommand('copy');
        document.body.removeChild(ta);
      } catch {
        copied = false;
      }
    }
    setCopyMode(copied ? 'copied' : 'manual');
    setNotice(copied
      ? (zh ? 'curl 已复制到剪贴板' : 'curl copied to clipboard')
      : (zh ? '复制失败，请手动选取下面这行' : 'copy failed - select the line below'));
    return undefined;
  }, [apiBase, zh]);

  const run = useCallback((command) => {
    if (!command) return;
    if (command.kind === 'api') { copyCurl(command); return; }
    if (activatePage(command)) onClose?.();
  }, [copyCurl, onClose]);

  // 键盘：↑/↓ 移动光标，Enter 执行，Esc 关闭。Tab 留在面板内（焦点只有输入框与列表）。
  const onKeyDown = (event) => {
    if (event.key === 'Escape') { event.preventDefault(); onClose?.(); return; }
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      if (results.length) setCursor((c) => (c + 1) % results.length);
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      if (results.length) setCursor((c) => (c - 1 + results.length) % results.length);
      return;
    }
    if (event.key === 'Enter') { event.preventDefault(); run(results[cursor]); }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-[60] flex items-start justify-center bg-black/55 px-4 pt-[12vh]"
      role="dialog"
      aria-modal="true"
      aria-label={zh ? '命令面板' : 'Command palette'}
      onMouseDown={(event) => { if (event.target === event.currentTarget) onClose?.(); }}
    >
      <div className="w-full max-w-xl overflow-hidden rounded-2xl border border-white/12 bg-[#13161A] text-[#F3F5F7] shadow-2xl">
        <div className="flex items-center gap-2 border-b border-white/8 px-4">
          <span className="text-xs text-white/40" aria-hidden="true">⌘</span>
          <input
            ref={inputRef}
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            onKeyDown={onKeyDown}
            role="combobox"
            aria-expanded
            aria-controls="command-palette-results"
            aria-label={zh ? '搜索页面或 API 端点' : 'Search pages or API endpoints'}
            placeholder={zh ? '搜索页面、端点…' : 'Search pages, endpoints…'}
            className="w-full bg-transparent py-3 text-sm text-white placeholder:text-white/35 focus:outline-none"
          />
          <button
            type="button"
            onClick={onClose}
            aria-label={zh ? '关闭命令面板' : 'Close command palette'}
            className="min-h-[32px] rounded-md px-2 text-xs text-white/50 hover:text-white focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#8AB7FF]"
          >
            Esc
          </button>
        </div>

        <ul
          id="command-palette-results"
          ref={listRef}
          role="listbox"
          aria-label={zh ? '搜索结果' : 'Results'}
          className="max-h-[52vh] overflow-y-auto py-1"
        >
          {results.length === 0 && (
            <li className="px-4 py-6 text-sm text-white/45">
              {docState === 'loading'
                ? (zh ? '正在载入端点索引…' : 'Loading endpoint index…')
                : (zh ? '没有匹配项' : 'No matches')}
              {docState === 'empty' && query.trim() === '' && (
                <span className="mt-1 block text-xs text-white/35">
                  {zh ? '端点索引不可用（后端未就绪），页面项仍可使用' : 'Endpoint index unavailable - page entries still work'}
                </span>
              )}
            </li>
          )}
          {results.map((command, index) => {
            const active = index === cursor;
            return (
              <li key={command.id} role="option" aria-selected={active}>
                <button
                  type="button"
                  onMouseEnter={() => setCursor(index)}
                  onClick={() => run(command)}
                  className={`flex w-full items-center gap-3 px-4 py-2 text-left text-sm focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#8AB7FF] ${
                    active ? 'bg-white/10' : ''
                  }`}
                >
                  <span
                    className={`shrink-0 rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase ${
                      command.kind === 'api' ? 'bg-white/10 text-white/70' : 'bg-[#8AB7FF]/20 text-[#BBD3FF]'
                    }`}
                  >
                    {command.kind === 'api' ? command.method : 'page'}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate">{command.title}</span>
                    <span className="block truncate text-[11px] text-white/45">
                      {command.kind === 'api' ? command.path : `${command.group} · ${command.href}`}
                    </span>
                  </span>
                  {command.kind === 'api' && command.params.length > 0 && (
                    <span className="shrink-0 text-[10px] text-white/35">{zh ? '需替换参数' : 'params'}</span>
                  )}
                </button>
              </li>
            );
          })}
        </ul>

        {notice && (
          <div className="border-t border-white/8 px-4 py-2">
            <div className="text-[11px] text-white/60">{notice}</div>
            {copyMode === 'manual' && curlText && (
              <textarea
                readOnly
                value={curlText}
                rows={Math.min(4, curlText.split('\n').length)}
                onFocus={(event) => event.currentTarget.select()}
                className="mt-1 w-full rounded-md bg-black/40 p-2 text-[10px] text-white/70"
              />
            )}
          </div>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-white/8 px-4 py-2 text-[10px] text-white/35">
          <span>{zh ? '↑↓ 选择 · Enter 执行 · Esc 关闭' : '↑↓ select · Enter run · Esc close'}</span>
          <span>
            {docState === 'ready'
              ? (zh ? `端点索引 ${apiCommands.length} 条 · 取自 OpenAPI` : `${apiCommands.length} endpoints from OpenAPI`)
              : (zh ? '端点索引不可用' : 'endpoint index off')}
          </span>
        </div>
      </div>
    </div>
  );
}
