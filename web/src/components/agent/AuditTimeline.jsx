import { memo, useCallback, useEffect, useRef, useState } from 'react';

// ─── Action Audit & Undo（DESIGN-v2.md v1.0：action audit & undo）───────────
// 每个破坏性/导出动作写一条 audit-row（时间线展示 + 状态）；
// 可逆动作附 ghost 撤销按钮（撤销语义 = 恢复上一状态），
// 不可逆动作的不可逆性在意图预览中提前声明，而非事后发现。
// 本期审计对象：导出 PDF 报告（不可逆）、清空对话（可逆，撤销恢复消息快照）。

// 条目上限：防止长会话无限保留消息快照导致内存增长（清空对话的 onUndo 持有整份转录）
const MAX_ENTRIES = 20;

export function useAuditLog() {
  const [entries, setEntries] = useState([]);
  const seqRef = useRef(0);
  // entries 镜像供 undo 在 updater 外定位条目（updater 必须纯，StrictMode 会双重调用）
  const entriesRef = useRef(entries);
  useEffect(() => {
    entriesRef.current = entries;
  }, [entries]);

  // entry: { action: string, reversible?: boolean, onUndo?: () => void }
  const log = useCallback((entry) => {
    seqRef.current += 1;
    setEntries((prev) => [
      ...prev.slice(-(MAX_ENTRIES - 1)),
      {
        id: `audit_${Date.now()}_${seqRef.current}`,
        time: new Date().toLocaleTimeString('zh-CN', { hour12: false }),
        status: 'done',
        reversible: false,
        ...entry,
      },
    ]);
  }, []);

  // 副作用（onUndo）在 updater 外执行：StrictMode 双重调用 updater 时不会双发；
  // 撤销成功后释放 onUndo 引用，避免快照常驻内存
  const undo = useCallback((id) => {
    const entry = entriesRef.current.find((e) => e.id === id);
    if (!entry || !entry.reversible || entry.status !== 'done') return;
    let failed = false;
    try {
      entry.onUndo?.();
    } catch {
      failed = true;
    }
    setEntries((prev) =>
      prev.map((e) =>
        e.id === id
          ? { ...e, status: failed ? 'undo_failed' : 'undone', onUndo: undefined }
          : e,
      ),
    );
  }, []);

  return { entries, log, undo };
}

function AuditTimelineBase({ entries = [], onUndo }) {
  if (entries.length === 0) return null;
  return (
    <div className="mt-3 border-t border-[var(--color-border)] pt-2.5">
      <div className="mb-1.5 text-[10px] font-semibold uppercase tracking-[0.1em] text-[var(--color-muted)]">
        操作审计
      </div>
      <div className="space-y-1">
        {entries.map((e) => (
          <div
            key={e.id}
            className="flex items-center gap-2 rounded-md bg-[var(--color-panel)] px-2.5 py-1.5 text-[11px]"
          >
            <span className="shrink-0 font-mono text-[10px] tabular-nums text-[var(--color-muted)]">
              {e.time}
            </span>
            <span className="min-w-0 flex-1 truncate text-[var(--color-text)]">{e.action}</span>
            {e.status === 'undone' ? (
              <span className="shrink-0 text-[10px] text-[var(--color-muted)]">已撤销</span>
            ) : e.status === 'undo_failed' ? (
              <span className="shrink-0 text-[10px] text-[var(--color-status-error)]">撤销失败</span>
            ) : e.reversible && e.status === 'done' ? (
              <button
                onClick={() => onUndo(e.id)}
                className="shrink-0 rounded border border-[var(--color-border)] px-2 py-0.5 text-[10px] text-[var(--color-muted)] transition-colors hover:border-[var(--color-text)] hover:text-[var(--color-text)]"
              >
                撤销
              </button>
            ) : (
              <span className="shrink-0 text-[10px] text-[var(--color-muted)]">不可逆</span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const AuditTimeline = memo(AuditTimelineBase);
export default AuditTimeline;
