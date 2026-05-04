function formatCardValue(value, fallback) {
  if (value === null || value === undefined || value === '') {
    return fallback;
  }
  if (Array.isArray(value)) {
    return value.join(', ');
  }
  return String(value);
}

export default function FinlandOverviewCards({ cards = [], copy }) {
  return (
    <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
      {cards.map((card) => (
        <article
          key={card.field_key || card.id}
          className="rounded-lg border border-[var(--color-border)] bg-[linear-gradient(180deg,rgba(11,17,28,0.98),rgba(17,27,44,0.86))] p-4 shadow-[0_14px_32px_rgba(3,7,18,0.18)]"
        >
          <div className="flex items-center justify-between gap-3 text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
            <span>{card.label}</span>
            <span>{card.granularity || copy.cardFallback}</span>
          </div>
          <div className="mt-3 text-xl font-semibold text-[var(--color-text)]">
            {formatCardValue(card.value, copy.cardFallback)}
            {card.unit ? <span className="ml-2 text-sm text-[var(--color-muted)]">{card.unit}</span> : null}
          </div>
          <div className="mt-3 flex items-center justify-between gap-3 text-sm leading-6 text-[var(--color-muted)]">
            <span>{card.change_vs_previous ?? copy.cardDescriptionFallback}</span>
            <span>{card.sparkline?.length || 0}</span>
          </div>
        </article>
      ))}
    </section>
  );
}
