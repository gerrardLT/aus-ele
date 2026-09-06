// web/src/hooks/useUrlFilterSync.js
// R3.1 筛选器 ↔ 地址栏的 DOM 侧接线（2026-09-06）。
//
// 判据全在 lib/urlState.js（纯函数，node:test 覆盖）。这里只做三件事，且每件都有理由：
// 1. **写回用 replaceState 而不是 pushState**。用户每改一个筛选条件就多一条历史记录的话，
//    「后退」会变成「撤销上一步筛选」，而所有人对后退的预期都是「回到上一个页面」 ——
//    这是可分享 URL 与可浏览历史之间必须选边的一刀，选了可分享。
// 2. **首屏恢复不在这里做**（见 urlState.filterPatchActions 的注释）：由 FilterProvider
//    在 useReducer 的惰性初始化里用真 reducer 重放，避免默认态先把 URL 覆盖掉。
// 3. **popstate 要接**：侧边栏的 SPA 导航走 pushState，用户按后退时地址栏变了而 React
//    状态不会自己跟着变 —— 不接就是「后退看起来没反应」，比没有 SPA 导航更糟。
//
// 任何一步失败都不该影响页面：全部包在 try/catch 里，最坏情况退回「URL 不动」的原行为。

import { useCallback, useEffect, useRef } from 'react';
import {
  buildUrl,
  filterPatchActions,
  filtersToUrlParams,
  mergeSearch,
  readUrlFilters,
  shouldWriteSearch,
} from '../lib/urlState.js';

/**
 * @param filters   当前筛选器状态
 * @param dispatch  FilterContext 的裸 dispatch（**不用 setFilter**：恢复不是「用户用了筛选器」，
 *                  走 setFilter 会把 onboarding 的 filter 步骤标记成已完成，激活漏斗于是开始虚高）
 * @param serialize toQueryParams 本身 —— 与 API query 共用同一个序列化器
 * @param enabled   R5.4 flag（VITE_URL_STATE_UI）。关掉时本 hook 完全不产生副作用：不写
 *                  地址栏、不接 popstate。**必须做成参数而不是在调用方条件调用 hook** ——
 *                  hook 的顺序是 React 的硬约束，`if (flag) useUrlFilterSync()` 会直接崩。
 */
export function useUrlFilterSync({ filters, dispatch, serialize, locationLike, historyLike, enabled = true } = {}) {
  const loc = locationLike || globalThis.location;
  const hist = historyLike || globalThis.history;
  const mounted = useRef(false);

  // 写回：只在**真的不同**时动地址栏。
  useEffect(() => {
    if (!enabled) return undefined;
    if (!filters || typeof serialize !== 'function') return undefined;
    // 首帧不写：首屏 URL 已由惰性初始化消费过，若此刻写回，会把「URL 里写了但被白名单挡下」
    // 的参数（例如 region=../../）静默删掉 —— 那是对的，但删的动作也该等恢复稳定后再做。
    if (!mounted.current) {
      mounted.current = true;
      return undefined;
    }
    try {
      const params = filtersToUrlParams(filters, serialize);
      const base = loc?.search || '';
      if (!shouldWriteSearch(base, params)) return undefined;
      hist?.replaceState?.(null, '', buildUrl(loc?.pathname || '/', mergeSearch(base, params)));
    } catch {
      /* 隐私模式/沙箱里 replaceState 会抛：页面照常可用，只是链接不可分享 */
    }
    return undefined;
  }, [filters, dispatch, serialize, loc, hist, enabled]);

  // 后退/前进：把 URL 里的筛选器重新灌回状态。
  const restore = useCallback(() => {
    if (!enabled) return;
    try {
      const patch = readUrlFilters(globalThis.location?.search || '');
      // 逐条派发而不是加一个 APPLY_URL case：filterReducer 是既有代码，本批次规定不动它。
      // React 18 会把同一事件里的多次派发合成一次渲染，所以「一条 action 一次渲染」的担心不成立。
      for (const action of filterPatchActions(patch)) dispatch?.(action);
    } catch {
      /* 畸形 URL 不影响当前页面 */
    }
  }, [dispatch, enabled]);

  useEffect(() => {
    if (!enabled) return undefined;
    if (typeof globalThis.addEventListener !== 'function') return undefined;
    globalThis.addEventListener('popstate', restore);
    return () => globalThis.removeEventListener('popstate', restore);
  }, [restore]);

  return restore;
}
