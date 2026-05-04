export default function FinlandFieldDetailPanel({ selectedFields = [], copy }) {
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
              className="grid gap-2 rounded-md border border-[var(--color-border)] bg-[var(--color-surface)]/60 p-4"
            >
              <div className="flex items-center justify-between gap-3">
                <div className="font-medium text-[var(--color-text)]">
                  {field.label}{field.unit ? ` (${field.unit})` : ''}
                </div>
                <span className="rounded-full border border-[var(--color-border)] px-2 py-1 text-[11px] text-[var(--color-muted)]">
                  {copy.pending}
                </span>
              </div>
              <p className="text-sm leading-6 text-[var(--color-muted)]">
                {copy.selectionDescription}
              </p>
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
