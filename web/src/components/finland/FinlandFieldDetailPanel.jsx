function formatFieldValue(value, fallback) {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  return String(value);
}

export default function FinlandFieldDetailPanel({ selectedFields = [], copy }) {
  const labels = copy.labels;

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {copy.eyebrow}
      </div>
      <h3 className="mt-2 text-lg font-semibold text-[var(--color-text)]">
        {copy.title}
      </h3>

      {selectedFields.length ? (
        <div className="mt-4 grid gap-3">
          <div className="text-sm font-medium text-[var(--color-muted)]">
            {copy.listTitle}
          </div>
          {selectedFields.map((field) => (
            <article
              key={field.id}
              className="grid gap-3 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]/60 p-4"
            >
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="font-medium text-[var(--color-text)]">
                  {field.label}{field.unit ? ` (${field.unit})` : ''}
                </div>
                <span className="rounded-full border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-muted)]">
                  {formatFieldValue(field.category, copy.notAvailable)}
                </span>
              </div>
              <dl className="grid gap-2 text-sm leading-6 text-[var(--color-muted)]">
                <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3">
                  <dt>{labels.source}</dt>
                  <dd className="text-[var(--color-text)]">{formatFieldValue(field.source_name, copy.notAvailable)}</dd>
                </div>
                <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3">
                  <dt>{labels.granularity}</dt>
                  <dd className="text-[var(--color-text)]">{formatFieldValue(field.granularity, copy.notAvailable)}</dd>
                </div>
                <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3">
                  <dt>{labels.dataset}</dt>
                  <dd className="text-[var(--color-text)]">{formatFieldValue(field.source_dataset_id, copy.notAvailable)}</dd>
                </div>
                <div className="grid grid-cols-[7rem_minmax(0,1fr)] gap-3">
                  <dt>{labels.latestValue}</dt>
                  <dd className="text-[var(--color-text)]">{formatFieldValue(field.latestValue, copy.notAvailable)}</dd>
                </div>
                <div className="grid gap-1">
                  <dt>{labels.methodology}</dt>
                  <dd className="text-[var(--color-text)]">
                    {formatFieldValue(field.methodology_note, copy.notAvailable)}
                  </dd>
                </div>
              </dl>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/40 px-4 py-6">
          <div className="text-base font-semibold text-[var(--color-text)]">
            {copy.emptyTitle}
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">
            {copy.emptyDescription}
          </p>
        </div>
      )}
    </section>
  );
}
