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
    <section className="grid gap-5 rounded-lg border border-[color:color-mix(in_oklab,var(--color-border)_72%,#c6a86a_28%)] bg-[radial-gradient(circle_at_top_left,rgba(198,168,106,0.18),transparent_28%),linear-gradient(180deg,rgba(9,15,25,0.96),rgba(11,20,29,0.94))] p-5 shadow-[0_28px_90px_rgba(4,8,18,0.34)]">
      <div className="grid gap-2">
        <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-amber-100/72">
          {copy.eyebrow}
        </div>
        <h3 className="text-xl font-semibold text-[var(--color-text)] md:text-2xl">{copy.title}</h3>
        <p className="max-w-3xl text-sm leading-6 text-slate-300/78">
          {copy.description}
        </p>
      </div>

      <FinlandPriceSummaryStrip
        summary={summary}
        copy={copy.summary}
      />

      <div className="grid gap-4 xl:grid-cols-[minmax(0,16rem)_minmax(0,1fr)] xl:items-start">
        <FinlandPrimaryPriceSelector
          options={priceOptions}
          selectedFieldKey={selectedFieldKey}
          onChange={onSelectField}
          copy={copy.selector}
        />

        <div className="grid gap-4 xl:grid-cols-[minmax(0,1.7fr)_minmax(18rem,0.88fr)]">
          <FinlandLinkedChart
            apiBase={apiBase}
            chartRequest={mainChartRequest}
            selectedFields={selectedField ? [selectedField] : []}
            copy={mainChartCopy}
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
