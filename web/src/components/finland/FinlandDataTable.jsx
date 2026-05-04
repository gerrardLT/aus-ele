const DEFAULT_COPY = {
  eyebrow: 'Field Table',
  title: 'Selectable field workbench',
  description: 'Pick fields here to drive the linked chart and detail shell.',
  empty: 'No field rows available yet.',
  columns: {
    field: 'Field',
    source: 'Source',
    readiness: 'Readiness',
    value: 'Signal',
  },
  action: {
    selected: 'Selected',
    available: 'Select',
  },
};

export default function FinlandDataTable({
  fields = [],
  selectedFields = [],
  onSelectField,
  copy = DEFAULT_COPY,
}) {
  const labels = copy?.columns ? { ...DEFAULT_COPY.columns, ...copy.columns } : DEFAULT_COPY.columns;
  const actionCopy = copy?.action ? { ...DEFAULT_COPY.action, ...copy.action } : DEFAULT_COPY.action;

  const toggleField = (fieldId) => {
    const nextSelected = selectedFields.includes(fieldId)
      ? selectedFields.filter((item) => item !== fieldId)
      : [...selectedFields, fieldId];
    onSelectField?.(nextSelected);
  };

  return (
    <section className="overflow-hidden rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)]">
      <div className="border-b border-[var(--color-border)] bg-[linear-gradient(135deg,rgba(79,209,197,0.14),rgba(251,191,36,0.1),transparent)] px-5 py-4">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
          {copy.eyebrow || DEFAULT_COPY.eyebrow}
        </div>
        <h3 className="mt-2 text-lg font-semibold text-[var(--color-text)]">
          {copy.title || DEFAULT_COPY.title}
        </h3>
        <p className="mt-1 text-sm leading-6 text-[var(--color-muted)]">
          {copy.description || DEFAULT_COPY.description}
        </p>
      </div>

      {fields.length ? (
        <div className="max-h-[28rem] overflow-auto">
          <table className="min-w-full border-separate border-spacing-0 text-left text-sm">
            <thead className="sticky top-0 z-20">
              <tr className="bg-[var(--color-surface)]/95 text-[var(--color-muted)] backdrop-blur">
                <th className="sticky left-0 z-30 border-b border-r border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 font-semibold">
                  {labels.field}
                </th>
                <th className="border-b border-[var(--color-border)] px-4 py-3 font-semibold">
                  {labels.source}
                </th>
                <th className="border-b border-[var(--color-border)] px-4 py-3 font-semibold">
                  {labels.readiness}
                </th>
                <th className="border-b border-[var(--color-border)] px-4 py-3 font-semibold">
                  {labels.value}
                </th>
              </tr>
            </thead>
            <tbody>
              {fields.map((field, index) => {
                const isSelected = selectedFields.includes(field.id);
                return (
                  <tr
                    key={field.id}
                    className={index % 2 === 0 ? 'bg-[var(--color-panel)]' : 'bg-[var(--color-surface)]/35'}
                  >
                    <td className="sticky left-0 z-10 border-b border-r border-[var(--color-border)] bg-inherit px-4 py-3">
                      <button
                        type="button"
                        onClick={() => toggleField(field.id)}
                        aria-pressed={isSelected}
                        className={`flex w-full min-w-[14rem] items-center justify-between gap-3 text-left transition ${
                          isSelected ? 'text-[var(--color-text)]' : 'text-[var(--color-muted)] hover:text-[var(--color-text)]'
                        }`}
                      >
                        <span className="font-medium">{field.label}</span>
                        <span
                          className={`rounded-full border px-2 py-1 text-[10px] font-semibold uppercase tracking-[0.12em] ${
                            isSelected
                              ? 'border-amber-300/60 bg-amber-300/15 text-amber-200'
                              : 'border-[var(--color-border)] text-[var(--color-muted)]'
                          }`}
                        >
                          {isSelected ? actionCopy.selected : actionCopy.available}
                        </span>
                      </button>
                    </td>
                    <td className="border-b border-[var(--color-border)] px-4 py-3 text-[var(--color-text)]">
                      {field.source}
                    </td>
                    <td className="border-b border-[var(--color-border)] px-4 py-3">
                      <span className="rounded-full border border-emerald-300/25 bg-emerald-300/10 px-2 py-1 text-[11px] font-medium text-emerald-200">
                        {field.readiness}
                      </span>
                    </td>
                    <td className="border-b border-[var(--color-border)] px-4 py-3 text-[var(--color-muted)]">
                      {field.value}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="px-5 py-8 text-sm text-[var(--color-muted)]">
          {copy.empty || DEFAULT_COPY.empty}
        </div>
      )}
    </section>
  );
}
