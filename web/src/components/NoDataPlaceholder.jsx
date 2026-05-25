/**
 * NoDataPlaceholder — displays a friendly message when a module has no data
 * for the current filter combination.
 *
 * Props:
 *   - lang: 'zh' | 'en' (default 'zh')
 *   - filters: object with active filter values (optional, shows filter chips)
 *   - className: additional CSS classes (optional)
 */

const FILTER_LABELS = {
  zh: {
    region: '区域',
    year: '年份',
    quarter: '季度',
    dayType: '日类型',
    months: '月份',
  },
  en: {
    region: 'Region',
    year: 'Year',
    quarter: 'Quarter',
    dayType: 'Day Type',
    months: 'Months',
  },
};

function formatFilterValue(key, value) {
  if (key === 'months' && Array.isArray(value)) {
    if (value.length === 1 && value[0] === 'ALL') return null;
    return value.join(', ');
  }
  if (value === 'ALL' || value == null) return null;
  return String(value);
}

export default function NoDataPlaceholder({ lang = 'zh', filters, className = '' }) {
  const message =
    lang === 'zh'
      ? '当前筛选条件下无数据'
      : 'No data available for current filters';

  const labels = FILTER_LABELS[lang] || FILTER_LABELS.zh;

  // Build active filter chips from the filters object
  const chips = [];
  if (filters) {
    for (const [key, value] of Object.entries(filters)) {
      if (key === 'market') continue; // market is derived from region, skip
      const display = formatFilterValue(key, value);
      if (display && labels[key]) {
        chips.push({ label: labels[key], value: display });
      }
    }
  }

  return (
    <div
      className={`flex flex-col items-center justify-center gap-3 rounded-2xl border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/50 px-6 py-10 text-center ${className}`.trim()}
      role="status"
      aria-label={message}
    >
      {/* Empty state icon */}
      <svg
        className="h-8 w-8 text-[var(--color-muted)]/60"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M3 3h18v18H3z" opacity="0.3" />
        <path d="M9 9l6 6M15 9l-6 6" />
      </svg>

      <p className="text-sm font-medium text-[var(--color-muted)]">{message}</p>

      {chips.length > 0 && (
        <div className="mt-1 flex flex-wrap items-center justify-center gap-2">
          {chips.map((chip) => (
            <span
              key={chip.label}
              className="inline-flex items-center gap-1 rounded-full border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-1 text-[11px] text-[var(--color-muted)]"
            >
              <span className="font-semibold uppercase tracking-wider">{chip.label}</span>
              <span>{chip.value}</span>
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
