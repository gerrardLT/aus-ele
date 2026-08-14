// web/src/lib/onboarding.js
// Onboarding 步骤状态（P2-3，2026-08-14）：localStorage 持久化 + 自定义事件广播。

const KEY = 'aus_onboarding_v1';
const DISMISS_KEY = 'aus_onboarding_v1_dismissed';
const MARKET_VISITS_KEY = 'aus_onboarding_v1_markets';

export const ONBOARDING_STEPS = [
  { id: 'browse', zh: '浏览市场分析页', en: 'Browse market analysis' },
  { id: 'switch_market', zh: '切换 NEM/WEM 市场', en: 'Switch between NEM/WEM' },
  { id: 'filter', zh: '使用筛选器（季度/负荷类型）', en: 'Use filters (quarter/day type)' },
  { id: 'agent', zh: '完成一次 AI 决策引擎分析', en: 'Complete an AI Decision Engine run' },
  { id: 'pricing', zh: '查看定价与套餐', en: 'View pricing plans' },
];

function safeGet(key) {
  try { return globalThis.localStorage?.getItem(key); } catch { return null; }
}

function safeSet(key, value) {
  try { globalThis.localStorage?.setItem(key, value); } catch { /* ignore */ }
}

export function readOnboardingState() {
  try { return JSON.parse(safeGet(KEY) || '{}'); } catch { return {}; }
}

export function markOnboardingStep(id) {
  const state = readOnboardingState();
  if (state[id]) return;
  state[id] = Date.now();
  safeSet(KEY, JSON.stringify(state));
  globalThis.dispatchEvent(new CustomEvent('aus-onboarding', { detail: state }));
}

/** 记录市场访问；NEM 与 WEM 都访问过后标记 switch_market 步骤。 */
export function visitMarket(market) {
  if (!market) return;
  let visits = [];
  try { visits = JSON.parse(safeGet(MARKET_VISITS_KEY) || '[]'); } catch { visits = []; }
  if (!visits.includes(market)) {
    visits.push(market);
    safeSet(MARKET_VISITS_KEY, JSON.stringify(visits));
  }
  if (visits.includes('NEM') && visits.includes('WEM')) {
    markOnboardingStep('switch_market');
  }
}

export function dismissOnboarding() {
  safeSet(DISMISS_KEY, '1');
  globalThis.dispatchEvent(new CustomEvent('aus-onboarding', { detail: readOnboardingState() }));
}

export function isOnboardingDismissed() {
  return safeGet(DISMISS_KEY) === '1';
}

export function isOnboardingComplete() {
  const state = readOnboardingState();
  return ONBOARDING_STEPS.every((s) => Boolean(state[s.id]));
}
