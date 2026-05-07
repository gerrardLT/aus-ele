import FinlandComparisonRail from './FinlandComparisonRail';
import FinlandFieldDetailPanel from './FinlandFieldDetailPanel';
import FinlandLinkedChart from './FinlandLinkedChart';
import FinlandPrimaryPriceSelector from './FinlandPrimaryPriceSelector';
import FinlandPriceSummaryStrip from './FinlandPriceSummaryStrip';

export default function FinlandPrimaryPriceWorkbench({
  apiBase,
  copy,
  priceOptions = [],
  selectedFieldKey = '',
  onSelectField,
  summary = null,
  comparisonItems = [],
  mainChartRequest = null,
  comparisonChartRequest = null,
  selectedField = null,
  mainChartCopy,
  fieldDetailCopy,
}) {
  return (
    <section className="grid gap-5 rounded-lg border border-[color:color-mix(in_oklab,var(--color-border)_80%,var(--color-primary)_20%)] bg-[linear-gradient(180deg,color-mix(in_oklab,var(--color-panel)_90%,var(--color-primary)_10%),var(--color-panel))] p-5 shadow-[0_14px_36px_color-mix(in_oklab,var(--color-primary)_8%,transparent)]">
      <div className="grid gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-primary)]/78">
          {copy.eyebrow}
        </div>
        <h3 className="text-xl font-semibold text-[var(--color-text)] md:text-2xl">{copy.title}</h3>
        <p className="max-w-3xl text-sm leading-6 text-[var(--color-muted)]">
          {copy.description}
        </p>
      </div>

      <FinlandPriceSummaryStrip
        summary={summary}
        copy={copy.summary}
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.85fr)_minmax(18rem,0.95fr)] xl:items-start">
        <FinlandLinkedChart
          apiBase={apiBase}
          chartRequest={mainChartRequest}
          selectedFields={selectedField ? [selectedField] : []}
          copy={mainChartCopy}
        />

        <div className="grid gap-4">
          <FinlandPrimaryPriceSelector
            options={priceOptions}
            selectedFieldKey={selectedFieldKey}
            onChange={onSelectField}
            copy={copy.selector}
          />
          <FinlandFieldDetailPanel
            selectedFields={selectedField ? [selectedField] : []}
            copy={fieldDetailCopy}
          />
        </div>
      </div>

      <FinlandComparisonRail
        apiBase={apiBase}
        chartRequest={comparisonChartRequest}
        items={comparisonItems}
        copy={copy.comparison}
      />
    </section>
  );
}
