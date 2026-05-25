/**
 * DataCompletenessBadge — displays WEM module data completeness status.
 *
 * Shows a colored badge indicating whether a WEM module has complete data
 * or is in preview mode with a specific reason.
 *
 * Props:
 *   - status: "complete" | "preview"
 *   - label: display text (e.g. "完整数据", "预览 — ESS 管道未连接")
 *   - module: "wem_ess" | "wem_fcas" (optional, for additional context)
 *   - className: additional CSS classes (optional)
 */

function statusToneClasses(status) {
  if (status === 'complete') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-800';
  }
  // "preview" — amber tone
  return 'border-amber-500/30 bg-amber-500/10 text-amber-800';
}

function StatusIcon({ status }) {
  if (status === 'complete') {
    return (
      <svg
        className="h-3.5 w-3.5 flex-shrink-0"
        viewBox="0 0 16 16"
        fill="currentColor"
        aria-hidden="true"
      >
        <path
          fillRule="evenodd"
          d="M8 15A7 7 0 1 0 8 1a7 7 0 0 0 0 14Zm3.28-8.72a.75.75 0 0 0-1.06-1.06L7 8.44 5.78 7.22a.75.75 0 0 0-1.06 1.06l1.75 1.75a.75.75 0 0 0 1.06 0l3.75-3.75Z"
          clipRule="evenodd"
        />
      </svg>
    );
  }
  // Preview — info/warning icon
  return (
    <svg
      className="h-3.5 w-3.5 flex-shrink-0"
      viewBox="0 0 16 16"
      fill="currentColor"
      aria-hidden="true"
    >
      <path
        fillRule="evenodd"
        d="M8 15A7 7 0 1 0 8 1a7 7 0 0 0 0 14ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 0 0-2 1 1 0 0 0 0 2Z"
        clipRule="evenodd"
      />
    </svg>
  );
}

export default function DataCompletenessBadge({ status, label, module, className = '' }) {
  if (!status || !label) return null;

  const toneClasses = statusToneClasses(status);

  return (
    <div
      className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium ${toneClasses} ${className}`.trim()}
      role="status"
      aria-label={`Data completeness: ${label}`}
      data-module={module}
    >
      <StatusIcon status={status} />
      <span>{label}</span>
    </div>
  );
}
