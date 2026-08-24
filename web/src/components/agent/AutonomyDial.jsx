import { memo, useCallback, useState } from 'react';

// ─── Autonomy Dial（DESIGN-v2.md v1.0：autonomy dial）───────────────────────
// 工作区控制条四段开关，默认「计划需确认」（Plan & Propose 层）。
// 契约偏差登记（2026-08-24）：v2 规格为 per-user 持久化；本期按设备级
// localStorage 实现（键 app_autonomy_tier，遵 app_* 惯例），服务端用户设置
// 列为后续 epic。
// TODO(后端契约)：当前为「界面偏好」语义——执行门控待 agent API 提供
// autonomy tier 契约后接入，不谎称已生效。
export const AUTONOMY_TIERS = [
  { id: 'notify', label: '仅提醒' },
  { id: 'plan_confirm', label: '计划需确认' },
  { id: 'confirm_exec', label: '确认后执行' },
  { id: 'auto', label: '自动执行' },
];

export const DEFAULT_AUTONOMY_TIER = 'plan_confirm';
const STORAGE_KEY = 'app_autonomy_tier';

export function readAutonomyTier() {
  try {
    const v = globalThis.localStorage?.getItem(STORAGE_KEY);
    return AUTONOMY_TIERS.some((t) => t.id === v) ? v : DEFAULT_AUTONOMY_TIER;
  } catch {
    return DEFAULT_AUTONOMY_TIER;
  }
}

// state 提升在 AgentPage 内、prop 下发（不建全局 Context，避免树级重渲染）
export function useAutonomyTier() {
  const [tier, setTier] = useState(() => readAutonomyTier());
  const update = useCallback((next) => {
    if (!AUTONOMY_TIERS.some((t) => t.id === next)) return;
    setTier(next);
    try {
      globalThis.localStorage?.setItem(STORAGE_KEY, next);
    } catch {
      /* 存储不可用时仅会话内生效 */
    }
  }, []);
  return [tier, update];
}

function AutonomyDialBase({ value, onChange }) {
  return (
    <div
      className="flex items-center gap-1 rounded-md border border-[var(--color-border)] bg-[var(--color-panel)] p-0.5"
      title="自主性档位（界面偏好；执行门控待后端契约接入）"
    >
      {AUTONOMY_TIERS.map((t) => {
        const active = value === t.id;
        return (
          <button
            key={t.id}
            onClick={() => onChange(t.id)}
            aria-pressed={active}
            className={`rounded px-2 py-0.5 text-[10px] transition-colors ${
              active
                ? 'bg-[var(--color-surface-hover)] text-[var(--color-text)]'
                : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
            }`}
          >
            {t.label}
          </button>
        );
      })}
    </div>
  );
}

const AutonomyDial = memo(AutonomyDialBase);
export default AutonomyDial;
