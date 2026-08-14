// web/src/components/OnboardingChecklist.jsx
// 新手引导清单（P2-3，2026-08-14）：左下角悬浮卡片，5 步完成打勾，可关闭。

import { useEffect, useState } from 'react';
import {
  ONBOARDING_STEPS, readOnboardingState, isOnboardingDismissed,
  isOnboardingComplete, dismissOnboarding,
} from '../lib/onboarding.js';

export default function OnboardingChecklist({ lang = 'zh' }) {
  const zh = lang === 'zh';
  const [state, setState] = useState(readOnboardingState());
  const [collapsed, setCollapsed] = useState(false);

  useEffect(() => {
    const onEvent = (e) => setState(e.detail || readOnboardingState());
    globalThis.addEventListener('aus-onboarding', onEvent);
    return () => globalThis.removeEventListener('aus-onboarding', onEvent);
  }, []);

  if (isOnboardingDismissed() || isOnboardingComplete()) return null;

  const doneCount = ONBOARDING_STEPS.filter((s) => state[s.id]).length;

  return (
    <div className="fixed bottom-4 left-4 z-40 w-64 rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] shadow-lg">
      <div className="flex items-center justify-between border-b border-[var(--color-border)] px-3 py-2">
        <button type="button" onClick={() => setCollapsed((v) => !v)} className="text-xs font-semibold text-[var(--color-text)]">
          {zh ? `新手引导 ${doneCount}/${ONBOARDING_STEPS.length}` : `Getting started ${doneCount}/${ONBOARDING_STEPS.length}`}
          <span className="ml-1 text-[var(--color-muted)]">{collapsed ? '+' : '−'}</span>
        </button>
        <button type="button" onClick={dismissOnboarding} className="text-[var(--color-muted)] hover:text-[var(--color-text)]" aria-label="dismiss">✕</button>
      </div>
      {!collapsed && (
        <ul className="space-y-1.5 px-3 py-2">
          {ONBOARDING_STEPS.map((s) => (
            <li key={s.id} className="flex items-center gap-2 text-[11px]">
              <span className={state[s.id] ? 'text-[var(--color-status-success)]' : 'text-[var(--color-muted)]'}>
                {state[s.id] ? '✓' : '○'}
              </span>
              <span className={state[s.id] ? 'text-[var(--color-muted)] line-through' : 'text-[var(--color-text)]'}>
                {zh ? s.zh : s.en}
              </span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
