const SUMMARY_FIELDS = [
  { valueKey: 'latestValue', labelKey: 'latestLabel' },
  { valueKey: 'highValue', labelKey: 'highLabel' },
  { valueKey: 'lowValue', labelKey: 'lowLabel' },
  { valueKey: 'meanValue', labelKey: 'meanLabel' },
  { valueKey: 'spreadVsSpotLatest', labelKey: 'spreadLabel' },
  { valueKey: 'volatilityBand', labelKey: 'volatilityLabel', isVolatility: true },
];

function formatValue(value, { isVolatility = false, copy } = {}) {
  if (value === null || value === undefined || value === '') {
    return '--';
  }
  if (isVolatility) {
    return copy?.volatilityValues?.[value] || String(value);
  }
  return typeof value === 'number' ? value.toFixed(2) : String(value);
}

export default function FinlandPriceSummaryStrip({
  summary = null,
  copy,
}) {
  return (
    <section className="grid gap-3 rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="text-[11px] font-semibold uppercase tracking-[0.14em] text-[var(--color-muted)]">
        {copy.title}
      </div>

      {summary ? (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-6">
          {SUMMARY_FIELDS.map(({ valueKey, labelKey, isVolatility = false }) => (
            <div
              key={valueKey}
              className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] p-3"
            >
              <div className="text-[11px] font-semibold uppercase tracking-[0.12em] text-[var(--color-muted)]">
                {copy[labelKey]}
              </div>
              <div className="mt-2 text-lg font-semibold text-[var(--color-text)]">
                {formatValue(summary[valueKey], { isVolatility, copy })}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="text-sm text-[var(--color-muted)]">{copy.empty}</div>
      )}
    </section>
  );
}
