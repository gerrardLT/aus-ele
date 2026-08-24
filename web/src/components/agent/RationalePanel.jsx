import { memo, useState } from 'react';

// ─── Explainable Rationale（DESIGN-v2.md v1.0：thinking toggle）─────────────
// 「查看推理轨迹」折叠面板，默认折叠。sanitized trace：仅工具名/状态/耗时/
// 摘要，不含原始调用参数 JSON（规格：no raw prompt text）。
// 数据复用 SSE tool_call/tool_result 已合成的 trace 数组，不新增请求。
const STATUS_TEXT = {
  done: '✓ 完成',
  completed: '✓ 完成',
  running: '● 执行中',
  error: '✕ 失败',
  failed: '✕ 失败',
  timeout: '⏱ 超时',
  cached: '↺ 缓存',
};

function RationalePanelBase({ trace = [], title = '查看推理轨迹' }) {
  const [open, setOpen] = useState(false);
  if (!trace || trace.length === 0) return null;
  return (
    <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)]">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-1.5 px-3 py-2 text-[11px] text-[var(--color-muted)] transition-colors hover:text-[var(--color-text)]"
      >
        <span aria-hidden="true" className={`inline-block transition-transform ${open ? 'rotate-90' : ''}`}>
          ›
        </span>
        {title}
        <span className="ml-auto font-mono text-[10px] tabular-nums">({trace.length} 步)</span>
      </button>
      {open && (
        <div className="space-y-1 border-t border-[var(--color-border)] px-3 py-2">
          {trace.map((t, i) => (
            <div key={t.callId || `${t.name}_${i}`} className="flex items-baseline gap-2 text-[11px]">
              <span className="shrink-0 font-mono tabular-nums text-[var(--color-muted)]">{i + 1}.</span>
              <span className="font-mono text-[var(--color-text)]">{t.name}</span>
              <span className="shrink-0 text-[10px] text-[var(--color-muted)]">
                {STATUS_TEXT[t.status] || t.status}
              </span>
              {typeof t.durationMs === 'number' && t.durationMs > 0 && (
                <span className="shrink-0 font-mono text-[10px] tabular-nums text-[var(--color-muted)]">
                  {(t.durationMs / 1000).toFixed(1)}s
                </span>
              )}
              {t.summary && (
                <span className="min-w-0 flex-1 truncate text-[10px] text-[var(--color-muted)]" title={t.summary}>
                  {t.summary}
                </span>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const RationalePanel = memo(RationalePanelBase);
export default RationalePanel;
