import { formatFingridValue } from '../../lib/fingridDataset';
import { buildFingridSummaryCards } from '../../lib/fingridUi';

export default function FingridSummaryCards({ summaryPayload, seriesPayload, aggregation, loading, lang }) {
  const cards = buildFingridSummaryCards({ lang, aggregation, summaryPayload, seriesPayload });

  return (
    <section className="grid gap-4 md:grid-cols-2 xl:grid-cols-4">
      {cards.map(({ label, value, unit }) => (
        <div key={label} className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div className="text-[11px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
          <div className="mt-2 text-xl font-serif text-[var(--color-text)]">
            {loading ? (lang === 'zh' ? '加载中...' : 'Loading...') : formatFingridValue(value, unit)}
          </div>
        </div>
      ))}
    </section>
  );
}
