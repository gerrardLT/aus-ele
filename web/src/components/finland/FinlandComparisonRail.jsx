export default function FinlandComparisonRail({
  items = [],
  copy,
}) {
  return (
    <section className="grid gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-4">
      <div className="grid gap-1">
        <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
          {copy.title}
        </div>
        <p className="text-sm leading-6 text-[var(--color-muted)]">
          {copy.description}
        </p>
      </div>

      {items.length ? (
        <div className="grid gap-3 lg:grid-cols-3">
          {items.map((item) => (
            <article
              key={item.field_key || item.id}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
            >
              <div className="text-sm font-semibold text-[var(--color-text)]">{item.label}</div>
              <div className="mt-2 text-sm text-[var(--color-muted)]">
                {item.description || item.unit || item.field_key}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="text-sm text-[var(--color-muted)]">{copy.empty}</div>
      )}
    </section>
  );
}
