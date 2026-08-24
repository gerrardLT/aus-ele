import { memo } from 'react';

// ─── Intent Preview（DESIGN-v2.md v1.0：intent preview card）────────────────
// 重要操作前的有意摩擦点：surface 卡 + mono 编号步骤 + 恰好三个动作
// （primary 继续执行 / ghost 修改计划 / ghost 我自己处理）。
// 永不自动关闭、永不折叠成 toast；不可逆操作必须在 notice 中声明。
function IntentPreviewBase({ title, steps = [], notice, onConfirm, onEdit, onCancel }) {
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5">
      <div className="mb-3 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-primary)]">
        意图预览 · {title}
      </div>
      {steps.length > 0 && (
        <ol className="mb-4 space-y-1.5">
          {steps.map((s, i) => (
            <li key={i} className="flex items-baseline gap-2.5 text-[12px] leading-5 text-[var(--color-text)]">
              <span
                className="shrink-0 tabular-nums text-[var(--color-muted)]"
                style={{ fontFamily: 'var(--font-mono-data)' }}
              >
                {String(i + 1).padStart(2, '0')}
              </span>
              <span>{s}</span>
            </li>
          ))}
        </ol>
      )}
      {notice && (
        <div
          className="mb-4 rounded-md border-l-2 px-3 py-2 text-[11px] leading-5 text-[var(--color-muted)]"
          style={{ borderColor: 'var(--color-status-timeout)' }}
        >
          {notice}
        </div>
      )}
      <div className="flex items-center gap-2">
        <button
          onClick={onConfirm}
          className="rounded border border-[var(--color-inverted)] bg-[var(--color-inverted)] px-3.5 py-1.5 text-[12px] font-medium text-[var(--color-inverted-text)] transition-opacity hover:opacity-90"
        >
          继续执行
        </button>
        <button
          onClick={onEdit}
          className="rounded border border-[var(--color-border)] px-3.5 py-1.5 text-[12px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)]"
        >
          修改计划
        </button>
        <button
          onClick={onCancel}
          className="rounded border border-[var(--color-border)] px-3.5 py-1.5 text-[12px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)]"
        >
          我自己处理
        </button>
      </div>
    </div>
  );
}

const IntentPreview = memo(IntentPreviewBase);
export default IntentPreview;
