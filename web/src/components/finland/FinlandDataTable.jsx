import { isFinlandBoardSelectableColumn } from '../../lib/finlandApi';

function formatCellValue(value, fallback) {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  if (typeof value === 'object') {
    return JSON.stringify(value);
  }
  return String(value);
}

export default function FinlandDataTable({
  columns = [],
  rows = [],
  selectedFieldIds = [],
  onSelectField,
  copy,
}) {
  const actionCopy = copy.action;

  const toggleField = (fieldId) => {
    const nextSelected = selectedFieldIds.includes(fieldId)
      ? selectedFieldIds.filter((item) => item !== fieldId)
      : [...selectedFieldIds, fieldId];
    onSelectField?.(nextSelected);
  };

  return (
    <section className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)]">
      <div className="border-b border-[var(--color-border)] bg-[linear-gradient(135deg,rgba(79,209,197,0.14),rgba(251,191,36,0.1),transparent)] px-5 py-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
          {copy.eyebrow}
        </div>
        <h3 className="mt-2 text-lg font-semibold text-[var(--color-text)]">
          {copy.title}
        </h3>
        <p className="mt-1 text-sm leading-6 text-[var(--color-muted)]">
          {copy.description}
        </p>
      </div>

      {columns.length ? (
        <div className="max-h-[28rem] overflow-auto">
          <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
            <thead className="sticky top-0 z-20">
              <tr className="bg-[var(--color-surface)]/95 text-[var(--color-muted)] backdrop-blur">
                {columns.map((column, index) => {
                  const isSelected = selectedFieldIds.includes(column.field_key);
                  const isSelectable = isFinlandBoardSelectableColumn(column);
                  const baseClassName = index === 0
                    ? 'sticky left-0 z-30 border-b border-r border-[var(--color-border)] bg-[var(--color-surface)]'
                    : 'border-b border-[var(--color-border)]';

                  return (
                    <th
                      key={column.field_key}
                      className={`${baseClassName} min-w-[12rem] px-4 py-3 font-semibold`}
                    >
                      {isSelectable ? (
                        <button
                          type="button"
                          onClick={() => toggleField(column.field_key)}
                          aria-pressed={isSelected}
                          className={`grid w-full gap-2 text-left transition ${
                            isSelected ? 'text-[var(--color-text)]' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                          }`}
                        >
                          <span>{column.label}</span>
                          <span className="flex items-center gap-2 text-[10px] uppercase tracking-[0.12em]">
                            <span>{column.unit || copy.notAvailable}</span>
                            <span
                              className={`rounded-full border px-2 py-1 ${
                                isSelected
                                  ? 'border-amber-300/60 bg-amber-300/15 text-amber-200'
                                  : 'border-[var(--color-border)] text-[var(--color-muted)]'
                              }`}
                            >
                              {isSelected ? actionCopy.selected : actionCopy.available}
                            </span>
                          </span>
                        </button>
                      ) : (
                        <div className="grid gap-2 text-[var(--color-text)]">
                          <span>{column.label}</span>
                          <span className="text-[10px] uppercase tracking-[0.12em] text-[var(--color-muted)]">
                            {column.unit || column.granularity || copy.notAvailable}
                          </span>
                        </div>
                      )}
                    </th>
                  );
                })}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, rowIndex) => (
                <tr
                  key={row.timestamp_utc || row.timestamp_helsinki || row.date || rowIndex}
                  className={rowIndex % 2 === 0 ? 'bg-[var(--color-panel)]' : 'bg-[var(--color-surface)]/35'}
                >
                  {columns.map((column, columnIndex) => (
                    <td
                      key={column.field_key}
                      className={`border-b border-[var(--color-border)] px-4 py-3 ${
                        columnIndex === 0 ? 'sticky left-0 z-10 border-r bg-inherit font-medium text-[var(--color-text)]' : 'text-[var(--color-muted)]'
                      }`}
                    >
                      {formatCellValue(row?.[column.field_key], copy.notAvailable)}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="px-5 py-8 text-sm text-[var(--color-muted)]">
          {copy.empty}
        </div>
      )}
    </section>
  );
}
