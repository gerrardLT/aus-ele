import { memo } from 'react';

// ─── Confidence Signal（DESIGN-v2.md v1.0：confidence badge）─────────────────
// 契约偏差登记（2026-08-24）：v2 规格为数值阈值（✓ 绿 ≥0.8 / ? 琥珀 <0.8），
// 但后端 confidence_level 为枚举（high/medium/low，backend/agent/schemas.py
// ConfidenceLevel）。映射表：high → 高档（绿 ✓）；medium/low → 低档（琥珀 ?）。
// 不伪造数值百分比；后端补 confidence_score 数值字段后优先读数值。
export const CONFIDENCE_LEVEL_MAP = {
  high: { tier: 'high', icon: '✓', label: '高置信' },
  medium: { tier: 'low', icon: '?', label: '中置信' },
  low: { tier: 'low', icon: '?', label: '低置信' },
};

function ConfidenceBadgeBase({ level, showLabel = true }) {
  const mapped = CONFIDENCE_LEVEL_MAP[level] || CONFIDENCE_LEVEL_MAP.medium;
  const colorVar =
    mapped.tier === 'high' ? 'var(--color-confidence-high)' : 'var(--color-confidence-low)';
  return (
    <span
      className="inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[10px] transition-colors"
      style={{ borderColor: colorVar, color: colorVar }}
      title={`置信度等级: ${CONFIDENCE_LEVEL_MAP[level] ? level : `未知(${level})→回落中档`}（后端枚举，非数值百分比）`}
    >
      {/* 图标双编码：色 + 形恒同时出现（DESIGN.md 状态色规则） */}
      <span aria-hidden="true" className="font-mono font-semibold">{mapped.icon}</span>
      {showLabel && <span>{mapped.label}</span>}
    </span>
  );
}

const ConfidenceBadge = memo(ConfidenceBadgeBase);
export default ConfidenceBadge;
