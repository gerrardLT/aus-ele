import FinlandComparisonRail from './FinlandComparisonRail';
import FinlandPrimaryPriceSelector from './FinlandPrimaryPriceSelector';
import FinlandPriceSummaryStrip from './FinlandPriceSummaryStrip';

export default function FinlandPrimaryPriceWorkbench({
  copy,
  priceOptions = [],
  selectedFieldKey = '',
  onSelectField,
  summary = null,
  comparisonItems = [],
}) {
  return (
    <section className="grid gap-4 rounded-lg border border-[var(--color-border)] bg-[linear-gradient(180deg,rgba(10,14,24,0.92),rgba(16,24,38,0.9))] p-5 shadow-[0_24px_80px_rgba(6,10,18,0.28)]">
      <div className="grid gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
          {copy.eyebrow}
        </div>
        <h3 className="text-xl font-semibold text-[var(--color-text)]">{copy.title}</h3>
        <p className="max-w-3xl text-sm leading-6 text-[var(--color-muted)]">
          {copy.description}
        </p>
      </div>

      <FinlandPrimaryPriceSelector
        options={priceOptions}
        selectedFieldKey={selectedFieldKey}
        onChange={onSelectField}
        copy={copy.selector}
      />

      <FinlandPriceSummaryStrip
        summary={summary}
        copy={copy.summary}
      />

      <FinlandComparisonRail
        items={comparisonItems}
        copy={copy.comparison}
      />
    </section>
  );
}
