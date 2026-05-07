import DataQualityBadge from '../DataQualityBadge';
import PageSection from '../PageSection';
import FingridDistributionPanel from './FingridDistributionPanel';
import FingridSeriesChart from './FingridSeriesChart';
import FingridStatusPanel from './FingridStatusPanel';
import FingridSummaryCards from './FingridSummaryCards';

export default function FingridHourlyBoard({
  summaryPayload,
  seriesPayload,
  statusPayload,
  statusMetadata,
  loading,
  error,
  copy,
  lang,
  marketModelCopy,
  mode = 'full',
  controls = null,
}) {
  const showHero = mode === 'full' || mode === 'hero';
  const showDetails = mode === 'full' || mode === 'details';

  return (
    <>
      {showHero ? (
        <PageSection
          id="price-trend"
          fullWidthInGrid={false}
          title={copy.seriesTitle}
          description={null}
          showHeader={false}
          showDivider={false}
        >
          {controls ? <div className="flex justify-end">{controls}</div> : null}
          <FingridSummaryCards
            summaryPayload={summaryPayload}
            seriesPayload={seriesPayload}
            aggregation={seriesPayload?.query?.aggregation || 'day'}
            loading={loading}
            lang={lang}
            compact
          />
          <FingridSeriesChart payload={seriesPayload} loading={loading} error={error} copy={copy} />
        </PageSection>
      ) : null}

      {showDetails ? (
        <PageSection
          id="market-supporting-signals"
          fullWidthInGrid={false}
          title={copy.syncStatus}
          description={null}
        >
          <div className="grid gap-4">
            <DataQualityBadge metadata={statusMetadata} lang={lang} />
            <div className="grid gap-6 xl:grid-cols-[minmax(0,1.1fr)_minmax(340px,0.95fr)]">
              <FingridDistributionPanel payload={summaryPayload} loading={loading} copy={copy} />
              <FingridStatusPanel payload={statusPayload} loading={loading} error={error} copy={copy} lang={lang} />
            </div>
            <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm leading-6 text-[var(--color-muted)]">
              {marketModelCopy.noSignals}
            </div>
          </div>
        </PageSection>
      ) : null}
    </>
  );
}
