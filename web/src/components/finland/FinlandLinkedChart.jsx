export default function FinlandLinkedChart({ selectedFields = [], copy }) {
  const hasSelection = selectedFields.length > 0;

  return (
    <section className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-5">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {copy.eyebrow}
      </div>
      <div className="mt-3 overflow-hidden rounded-lg border border-[var(--color-border)] bg-[linear-gradient(160deg,rgba(15,23,42,0.86),rgba(18,24,38,0.92))]">
        <div className="flex items-center justify-between border-b border-[var(--color-border)] px-4 py-3">
          <h3 className="text-base font-semibold text-[var(--color-text)]">
            {copy.title}
          </h3>
          <span className="rounded-full border border-cyan-300/30 bg-cyan-300/10 px-2 py-1 text-[11px] font-semibold text-cyan-200">
            {selectedFields.length} {copy.selectionCountSuffix}
          </span>
        </div>
        <div className="grid gap-4 p-4">
          <div className="grid h-52 place-items-center rounded-md border border-dashed border-cyan-300/25 bg-[radial-gradient(circle_at_top,rgba(34,211,238,0.14),transparent_55%),linear-gradient(180deg,rgba(15,23,42,0.65),rgba(15,23,42,0.92))]">
            {hasSelection ? (
              <div className="w-full max-w-xl">
                <div className="flex items-end gap-3">
                  {selectedFields.map((field, index) => (
                    <div key={field.id} className="flex flex-1 flex-col items-center gap-3">
                      <div
                        className="w-full rounded-t-md bg-[linear-gradient(180deg,#5eead4,#f59e0b)]"
                        style={{ height: `${72 + (index % 4) * 24}px` }}
                      />
                      <div className="max-w-full truncate text-xs text-[var(--color-muted)]">
                        {field.label}{field.unit ? ` (${field.unit})` : ''}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (
              <div className="grid max-w-md gap-2 text-center">
                <div className="text-base font-semibold text-[var(--color-text)]">
                  {copy.emptyTitle}
                </div>
                <p className="text-sm leading-6 text-[var(--color-muted)]">
                  {copy.emptyDescription}
                </p>
              </div>
            )}
          </div>
          {hasSelection ? (
            <p className="text-sm leading-6 text-[var(--color-muted)]">
              {copy.populatedDescription}
            </p>
          ) : null}
        </div>
      </div>
    </section>
  );
}
