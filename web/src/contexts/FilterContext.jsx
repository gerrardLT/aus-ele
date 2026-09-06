import { createContext, useContext, useReducer, useCallback } from 'react';
import { useUrlFilterSync } from '../hooks/useUrlFilterSync.js';
import { filterPatchActions, readUrlFilters } from '../lib/urlState.js';
import { isFlagEnabled } from '../lib/flags.js';

// R3.1 零代码回滚位（Spec §160）：关掉后本文件的行为与 R3 之前**逐字一致** ——
// 首屏不做 URL 重放、也不注册地址栏写回。之所以值得一个 flag 而不是「反正测试都绿」：
// 这一项改的是「用户看到的 URL」，而 URL 会被贴进工单、邮件与浏览器历史，
// 一旦镜像逻辑有偏差（比如把未知参数顶到末尾），出错面是全站且不可撤销的。
const URL_STATE_ENABLED = isFlagEnabled(import.meta.env, 'urlFilters');

const FilterContext = createContext(null);

const initialState = {
  market: 'NEM',
  region: 'NSW1',
  year: new Date().getFullYear(),
  quarter: 'ALL',
  dayType: 'ALL',
  months: ['ALL'],
};

function filterReducer(state, action) {
  switch (action.type) {
    case 'SET_FILTER': {
      const next = { ...state, [action.key]: action.value };
      // Derive market from region automatically
      if (action.key === 'region') {
        next.market = action.value === 'WEM' ? 'WEM' : 'NEM';
      }
      return next;
    }
    case 'RESET':
      return initialState;
    default:
      return state;
  }
}

/**
 * Convert filter state to API query parameters.
 * Only includes non-default values to keep requests clean.
 */
function toQueryParams(filters) {
  const params = { market: filters.market, region: filters.region };
  if (filters.year != null) {
    params.year = filters.year;
  }
  if (filters.quarter !== 'ALL') {
    params.quarter = filters.quarter;
  }
  if (filters.dayType !== 'ALL') {
    params.day_type = filters.dayType;
  }
  if (filters.months.length > 0 && !(filters.months.length === 1 && filters.months[0] === 'ALL')) {
    params.months = filters.months.join(',');
  }
  return params;
}

export function FilterProvider({ children }) {
  // R3.1：首屏状态 = 默认值经「URL 里的筛选器」重放而来。
  // 重放走**真 reducer**（而不是 Object.assign 一份补丁），所以 `region ⇒ market` 这条推导
  // 规则依然只有 filterReducer 一处实现；URL 侧只决定「派发哪些键、按什么顺序」。
  // 也不放在挂载后的 useEffect 里做：那一版会先渲染一遍默认态，而那次渲染触发的写回效果
  // 会先把地址栏里的 ?region=WEM 覆盖掉 —— 分享链接恰好是最不该坏的那条路径。
  const [filters, dispatch] = useReducer(filterReducer, initialState, (defaults) => {
    if (!URL_STATE_ENABLED) return defaults;
    let search = '';
    try { search = globalThis.location?.search || ''; } catch { search = ''; }
    return filterPatchActions(readUrlFilters(search)).reduce((state, action) => filterReducer(state, action), defaults);
  });

  // 之后每次状态变化把非默认值镜像回地址栏（replaceState，不新增历史记录）。
  useUrlFilterSync({ filters, dispatch, serialize: toQueryParams, enabled: URL_STATE_ENABLED });

  const setFilter = useCallback((key, value) => {
    dispatch({ type: 'SET_FILTER', key, value });
    // P2-3 Onboarding 信号：使用筛选器（2026-08-14）
    try { import('../lib/onboarding.js').then((m) => m.markOnboardingStep('filter')); } catch { /* ignore */ }
  }, []);

  const resetFilters = useCallback(() => {
    dispatch({ type: 'RESET' });
  }, []);

  const queryParams = toQueryParams(filters);

  return (
    <FilterContext.Provider value={{ filters, setFilter, resetFilters, toQueryParams: () => toQueryParams(filters), queryParams }}>
      {children}
    </FilterContext.Provider>
  );
}

export function useFilters() {
  const ctx = useContext(FilterContext);
  if (!ctx) throw new Error('useFilters must be used within FilterProvider');
  return ctx;
}
