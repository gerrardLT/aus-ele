import { formatFingridValue } from '../../lib/fingridDataset';
import { buildFingridSummaryCards, getFingridCopy } from '../../lib/fingridUi';

export default function FingridSummaryCards({ summaryPayload, seriesPayload, aggregation, loading, lang, compact = false }) {
  const cards = buildFingridSummaryCards({ lang, aggregation, summaryPayload, seriesPayload });
  const copy = getFingridCopy(lang);

  return (
    <section className={`grid gap-2 ${compact ? 'sm:grid-cols-2 xl:grid-cols-4' : 'md:grid-cols-2 xl:grid-cols-4'}`}>
      {cards.map(({ label, value, unit }, index) => (
        <div
          key={label}
          className={`rounded-xl border border-[var(--color-border)] ${compact ? 'p-3' : 'p-4'} ${
            index === 0
              ? 'bg-[color:color-mix(in_srgb,var(--color-panel)_72%,var(--color-surface))] shadow-[0_10px_26px_color-mix(in_srgb,var(--color-background)_82%,transparent)]'
              : 'bg-[var(--color-surface)]'
          }`}
        >
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{label}</div>
          <div className={`font-serif text-[var(--color-text)] ${compact ? 'mt-2 text-lg xl:text-xl' : index === 0 ? 'mt-3 text-3xl' : 'mt-3 text-2xl'}`}>
            {loading ? copy.loadingCards : formatFingridValue(value, unit)}
          </div>
        </div>
      ))}
    </section>
  );
}
