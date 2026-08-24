import { memo } from 'react';

// ─── Escalation Pathway（DESIGN-v2.md v1.0：escalation card）───────────────
// 不确定时先问而不猜：panel 卡平实陈述歧义 + 2–3 个具体选项（ghost 按钮）
// + 「标记给分析师」回落。琥珀左边框 2px，永不做整条红色横幅。
// 后端契约现状（2026-08-24）：SSE 尚无 escalation 事件，message.escalation
// 负载就绪后条件渲染即生效；本期为组件级交付。
function EscalationCardBase({ ambiguity, options = [], onResolve, onEscalate }) {
  return (
    <div
      className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-3"
      style={{ borderLeft: '2px solid var(--color-status-timeout)' }}
    >
      <div className="mb-1 text-[10px] font-semibold uppercase tracking-[0.1em]" style={{ color: 'var(--color-status-timeout)' }}>
        ▲ 需要你的确认
      </div>
      <p className="mb-3 text-[12px] leading-5 text-[var(--color-text)]">{ambiguity}</p>
      {options.length > 0 && (
        <div className="mb-2 flex flex-wrap gap-2">
          {options.map((opt, i) => {
            const label = typeof opt === 'string' ? opt : opt.label;
            return (
              <button
                key={i}
                onClick={() => onResolve?.(label)}
                className="rounded border border-[var(--color-border)] px-3 py-1.5 text-[11px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)]"
              >
                {label}
              </button>
            );
          })}
        </div>
      )}
      <button
        onClick={onEscalate}
        className="text-[11px] text-[var(--color-muted)] underline-offset-2 transition-colors hover:text-[var(--color-text)] hover:underline"
      >
        标记给分析师
      </button>
    </div>
  );
}

const EscalationCard = memo(EscalationCardBase);
export default EscalationCard;
