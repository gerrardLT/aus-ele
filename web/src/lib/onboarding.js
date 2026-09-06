// web/src/lib/onboarding.js
// Onboarding 步骤状态（P2-3，2026-08-14）：localStorage 持久化 + 自定义事件广播。
//
// 埋点单点接入（R5.1，2026-09-06）：Spec 明确要求把事件采集挂在 markOnboardingStep 而不是
// 各页面里散落 capture —— 这一步是「激活」的判据本身（Console 的激活指标据此计算），挂在
// 页面上会出现同一个步骤被多处上报、或某条路径漏报。挂在状态写入处，事件与状态同源。
import { capture } from './analytics.js';

// node --test 环境没有 import.meta.env，回落空对象 = 采集关闭（capture 变 no-op）。
const APP_ENV = import.meta.env || {};

const KEY = 'aus_onboarding_v1';
const DISMISS_KEY = 'aus_onboarding_v1_dismissed';
const MARKET_VISITS_KEY = 'aus_onboarding_v1_markets';

export const ONBOARDING_STEPS = [
  { id: 'browse', zh: '浏览市场分析页', en: 'Browse market analysis' },
  { id: 'switch_market', zh: '切换 NEM/WEM 市场', en: 'Switch between NEM/WEM' },
  { id: 'filter', zh: '使用筛选器（季度/负荷类型）', en: 'Use filters (quarter/day type)' },
  { id: 'agent', zh: '完成一次天枢 AI 分析', en: 'Complete a Tianshu AI run' },
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
  // 属性只放步骤名与总数：不放路径、不放查询文本、不放任何项目相关标识。
  capture('onboarding_step_completed', { step: id, steps_total: ONBOARDING_STEPS.length }, APP_ENV);
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
  // 「跳过引导」与「完成引导」同样重要：没有它就只会看到完成率而看不到放弃率。
  capture('onboarding_dismissed', null, APP_ENV);
}

export function isOnboardingDismissed() {
  return safeGet(DISMISS_KEY) === '1';
}

export function isOnboardingComplete() {
  const state = readOnboardingState();
  return ONBOARDING_STEPS.every((s) => Boolean(state[s.id]));
}
