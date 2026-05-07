import { Bar, BarChart, CartesianGrid, Cell, ComposedChart, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import DataQualityBadge from '../DataQualityBadge';
import PageSection from '../PageSection';
import FingridStatusPanel from './FingridStatusPanel';
import { buildYearlyChangeSeries } from '../../lib/fingridDataset';

function formatMetric(value, unit, fallback) {
  if (value === null || value === undefined || Number.isNaN(Number(value))) {
    return fallback;
  }
  return `${Number(value).toFixed(1)} ${unit}`;
}

function getYearLabel(timestamp) {
  return String(timestamp || '').slice(0, 4) || '--';
}

function formatDelta(currentValue, previousValue, unit, copy) {
  const current = Number(currentValue);
  const previous = Number(previousValue);
  if (!Number.isFinite(current) || !Number.isFinite(previous)) {
    return copy.none;
  }
  const delta = current - previous;
  if (Math.abs(delta) < 0.05) {
    return copy.yearlyPlanDeltaFlat;
  }
  const direction = delta > 0 ? copy.yearlyPlanDeltaUp : copy.yearlyPlanDeltaDown;
  return `${direction} ${Math.abs(delta).toFixed(1)} ${unit}`;
}

function YearlyValueTooltip({ active, payload, label, unit }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload || {};
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-3 text-sm shadow-[0_18px_38px_color-mix(in_srgb,var(--color-background)_78%,transparent)]">
      <div className="font-medium text-[var(--color-text)]">{String(label || '').slice(0, 4)}</div>
      <div className="mt-2 text-[var(--color-text)]">{formatMetric(point.value, unit, '--')}</div>
    </div>
  );
}

function YearlyDeltaTooltip({ active, payload, label, unit, copy }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload || {};
  const deltaPct = Number.isFinite(Number(point.delta_pct)) ? `${Number(point.delta_pct).toFixed(1)}%` : copy.none;
  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-3 text-sm shadow-[0_18px_38px_color-mix(in_srgb,var(--color-background)_78%,transparent)]">
      <div className="font-medium text-[var(--color-text)]">{label}</div>
      <div className="mt-2 text-[var(--color-text)]">{formatMetric(point.delta_value, unit, copy.none)}</div>
      <div className="mt-1 text-[var(--color-muted)]">{deltaPct}</div>
    </div>
  );
}

export default function FingridYearlyPlanBoard({
  dataset,
  summaryPayload,
  seriesPayload,
  statusPayload,
  statusMetadata,
  loading,
  error,
  copy,
  lang,
  mode = 'full',
  controls = null,
}) {
  const unit = dataset?.unit || summaryPayload?.dataset?.unit || 'MW';
  const series = seriesPayload?.series || [];
  const kpis = summaryPayload?.kpis || {};
  const currentYearPoint = series[series.length - 1] || null;
  const previousYearPoint = series.length > 1 ? series[series.length - 2] : null;
  const coverageStartYear = series.length > 0 ? getYearLabel(series[0]?.timestamp) : copy.none;
  const coverageEndYear = currentYearPoint ? getYearLabel(currentYearPoint.timestamp) : copy.none;
  const overviewCards = [
    {
      label: copy.yearlyPlanCurrentYear,
      value: currentYearPoint ? formatMetric(currentYearPoint.value, unit, copy.none) : copy.none,
      meta: currentYearPoint ? getYearLabel(currentYearPoint.timestamp) : copy.none,
    },
    {
      label: copy.yearlyPlanPreviousYear,
      value: previousYearPoint ? formatMetric(previousYearPoint.value, unit, copy.none) : copy.none,
      meta: previousYearPoint ? getYearLabel(previousYearPoint.timestamp) : copy.none,
    },
    {
      label: copy.yearlyPlanYearOverYear,
      value: currentYearPoint && previousYearPoint
        ? formatDelta(currentYearPoint.value, previousYearPoint.value, unit, copy)
        : copy.none,
      meta: currentYearPoint && previousYearPoint
        ? `${getYearLabel(previousYearPoint.timestamp)} -> ${getYearLabel(currentYearPoint.timestamp)}`
        : copy.none,
    },
    {
      label: copy.yearlyPlanCoverageSpan,
      value: series.length > 0 ? `${coverageStartYear} -> ${coverageEndYear}` : copy.none,
      meta: `${series.length} ${copy.yearlyPlanYearsLabel}`,
    },
  ];
  const cards = [
    { label: copy.yearlyPlanLatest, value: formatMetric(kpis.latest_value, unit, copy.none) },
    { label: copy.yearlyPlanMax, value: formatMetric(kpis.max_value, unit, copy.none) },
    { label: copy.yearlyPlanMin, value: formatMetric(kpis.min_value, unit, copy.none) },
    { label: copy.yearlyPlanPoints, value: `${series.length}` },
  ];
  const yearlyChangeSeries = buildYearlyChangeSeries(series);
  const showHero = mode === 'full' || mode === 'hero';
  const showDetails = mode === 'full' || mode === 'details';

  return (
    <>
      {showHero ? (
        <PageSection
          id="yearly-plan-series"
          fullWidthInGrid={false}
          title={copy.yearlyPlanSeriesTitle}
          description={mode === 'hero' ? null : copy.yearlyPlanBoardDescription}
          showHeader={false}
          showDivider={false}
        >
          {controls ? <div className="flex justify-end">{controls}</div> : null}
          {loading ? (
            <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
              {copy.loadingChart}
            </section>
          ) : error ? (
            <section className="rounded border border-rose-200 bg-rose-50 p-6 text-rose-700">{error}</section>
          ) : series.length === 0 ? (
            <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-sm text-[var(--color-muted)]">
              {copy.yearlyPlanEmpty}
            </section>
          ) : (
            <div className="grid gap-4">
              <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[0_16px_40px_color-mix(in_srgb,var(--color-background)_84%,transparent)]">
                <div className="mb-4 flex items-center justify-between gap-3">
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
                    {copy.yearlyPlanSeriesTitle}
                  </div>
                  <div className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
                    {series.length} pts
                  </div>
                </div>
                <div className={`${mode === 'hero' ? 'h-[340px]' : 'h-[400px]'}`}>
                  <ResponsiveContainer width="100%" height="100%">
                    <ComposedChart data={series}>
                      <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in_srgb,var(--color-border)_80%,transparent)" />
                      <XAxis dataKey="timestamp" tickFormatter={getYearLabel} minTickGap={24} />
                      <YAxis />
                      <Tooltip content={<YearlyValueTooltip unit={unit} />} />
                      <Bar dataKey="value" fill="#0f766e" radius={[10, 10, 0, 0]} barSize={28} />
                      <Line type="monotone" dataKey="value" stroke="#155e75" strokeWidth={2} dot={{ r: 3, fill: '#155e75' }} />
                    </ComposedChart>
                  </ResponsiveContainer>
                </div>
              </section>

              {yearlyChangeSeries.length > 0 ? (
                <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 shadow-[0_16px_40px_color-mix(in_srgb,var(--color-background)_84%,transparent)]">
                  <div className="mb-4 flex items-center justify-between gap-3">
                    <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
                      {copy.yearlyPlanYearOverYear}
                    </div>
                    <div className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
                      {yearlyChangeSeries.length} pts
                    </div>
                  </div>
                  <div className={`${mode === 'hero' ? 'h-[220px]' : 'h-[280px]'}`}>
                    <ResponsiveContainer width="100%" height="100%">
                      <BarChart data={yearlyChangeSeries}>
                        <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in_srgb,var(--color-border)_80%,transparent)" />
                        <XAxis dataKey="year" />
                        <YAxis />
                        <Tooltip content={<YearlyDeltaTooltip unit={unit} copy={copy} />} />
                        <Bar dataKey="delta_value" radius={[10, 10, 0, 0]}>
                          {yearlyChangeSeries.map((point) => (
                            <Cell
                              key={point.timestamp}
                              fill={Number(point.delta_value) >= 0 ? '#0f766e' : '#b45309'}
                            />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </div>
                </section>
              ) : null}
            </div>
          )}
        </PageSection>
      ) : null}

      {showDetails ? (
        <>
          <PageSection
            id="yearly-plan-board"
            fullWidthInGrid={false}
            title={copy.yearlyPlanOverviewTitle}
            description={copy.yearlyPlanOverviewDescription}
          >
            <section className="overflow-hidden rounded-2xl border border-[var(--color-border)] bg-[linear-gradient(135deg,color-mix(in_srgb,var(--color-panel)_84%,transparent),color-mix(in_srgb,var(--color-surface)_94%,transparent))] shadow-[0_20px_48px_color-mix(in_srgb,var(--color-background)_82%,transparent)]">
              <div className="grid gap-4 p-5 lg:p-6">
                <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
                  {overviewCards.map((card, index) => (
                    <div
                      key={card.label}
                      className={`min-h-[132px] rounded-xl border border-[var(--color-border)] p-4 ${
                        index === 0
                          ? 'bg-[color:color-mix(in_srgb,var(--color-surface)_68%,var(--color-panel))]'
                          : 'bg-[color:color-mix(in_srgb,var(--color-surface)_88%,transparent)]'
                      }`}
                    >
                      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{card.label}</div>
                      <div className="mt-4 font-serif text-3xl text-[var(--color-text)]">{loading ? copy.loadingCards : card.value}</div>
                      <div className="mt-3 text-xs uppercase tracking-[0.12em] text-[var(--color-muted)]">{card.meta}</div>
                    </div>
                  ))}
                </div>
              </div>
            </section>

            <section className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              {cards.map((card, index) => (
                <div
                  key={card.label}
                  className={`rounded-xl border border-[var(--color-border)] p-4 ${
                    index === 0
                      ? 'bg-[color:color-mix(in_srgb,var(--color-panel)_72%,var(--color-surface))] shadow-[0_10px_26px_color-mix(in_srgb,var(--color-background)_82%,transparent)]'
                      : 'bg-[var(--color-surface)]'
                  }`}
                >
                  <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{card.label}</div>
                  <div className={`mt-3 font-serif text-[var(--color-text)] ${index === 0 ? 'text-3xl' : 'text-2xl'}`}>
                    {loading ? copy.loadingCards : card.value}
                  </div>
                </div>
              ))}
            </section>
          </PageSection>

          <PageSection
            id="yearly-plan-status"
            fullWidthInGrid={false}
            title={copy.yearlyPlanStatusTitle}
            description={null}
          >
            <div className="grid gap-4">
              <DataQualityBadge metadata={statusMetadata} lang={lang} />
              <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.95fr)]">
                <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm leading-6 text-[var(--color-muted)]">
                  {copy.yearlyPlanStatusNote}
                </div>
                <FingridStatusPanel payload={statusPayload} loading={loading} error={error} copy={copy} lang={lang} />
              </div>
            </div>
          </PageSection>
        </>
      ) : null}
    </>
  );
}
