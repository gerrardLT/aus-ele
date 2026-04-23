import { formatFingridValue } from '../../lib/fingridDataset';

export default function FingridSummaryCards({ payload, loading }) {
  const kpis = payload?.kpis || {};
  const unit = payload?.dataset?.unit || 'EUR/MW';
  const cards = [
    ['Latest', kpis.latest_value],
    ['24h Avg', kpis.avg_24h],
    ['7d Avg', kpis.avg_7d],
    ['30d Avg', kpis.avg_30d],
    ['Min', kpis.min_value],
    ['Max', kpis.max_value],
  ];

  return (
    <section className="grid gap-4 md:grid-cols-3 xl:grid-cols-6">
      {cards.map(([label, value]) => (
        <div key={label} className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <div className="text-[11px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
          <div className="mt-2 text-xl font-serif text-[var(--color-text)]">
            {loading ? 'Loading...' : formatFingridValue(value, unit)}
          </div>
        </div>
      ))}
    </section>
  );
}
