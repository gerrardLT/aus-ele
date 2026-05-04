const DEFAULT_COPY = {
  eyebrow: 'Field Detail',
  title: 'Selected field detail shell',
  emptyTitle: 'Waiting for a field selection',
  emptyDescription: 'Choose fields from the table to preview the linked detail slots that will later host dictionary, provenance, and drill-down data.',
  listTitle: 'Active field slots',
  pending: 'Pending linked detail wiring',
};

export default function FinlandFieldDetailPanel({ selectedFields = [], copy = DEFAULT_COPY }) {
  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {copy.eyebrow || DEFAULT_COPY.eyebrow}
      </div>
      <h3 className="mt-2 text-lg font-semibold text-[var(--color-text)]">
        {copy.title || DEFAULT_COPY.title}
      </h3>

      {selectedFields.length ? (
        <div className="mt-4 grid gap-3">
          <div className="text-sm font-medium text-[var(--color-muted)]">
            {copy.listTitle || DEFAULT_COPY.listTitle}
          </div>
          {selectedFields.map((field) => (
            <article
              key={field}
              className="grid gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]/60 p-4"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-[var(--color-text)]">{field}</div>
                <span className="rounded-full border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-muted)]">
                  {copy.pending || DEFAULT_COPY.pending}
                </span>
              </div>
              <p className="text-sm leading-6 text-[var(--color-muted)]">
                This panel is intentionally limited to selection awareness for Task 6.
              </p>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 rounded-md border border-dashed border-[var(--color-border)] bg-[var(--color-surface)]/40 px-4 py-6">
          <div className="text-base font-semibold text-[var(--color-text)]">
            {copy.emptyTitle || DEFAULT_COPY.emptyTitle}
          </div>
          <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">
            {copy.emptyDescription || DEFAULT_COPY.emptyDescription}
          </p>
        </div>
      )}
    </section>
  );
}
