import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { fetchJson } from '../lib/apiClient';
import {
  buildGridForecastUrl,
  getForecastConfidenceCopy,
  getForecastContextItems,
  getForecastCoverageCopy,
  getForecastModeCopy,
  getForecastSectionCopy,
  getForecastSourceStatusItems,
  getForecastText,
  normalizeForecastResponse,
} from '../lib/gridForecast';
import GridForecastSummaryCards from './GridForecastSummaryCards';
import GridForecastTimeline from './GridForecastTimeline';
import GridForecastDrivers from './GridForecastDrivers';

const HORIZONS = ['24h', '7d', '30d'];

function sourceTone(status) {
  if (status === 'ok') {
    return 'border-emerald-200 bg-emerald-50 text-emerald-700';
  }
  if (status === 'partial') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  if (status === 'stale') {
    return 'border-slate-300 bg-slate-100 text-slate-700';
  }
  return 'border-slate-200 bg-slate-50 text-slate-600';
}

function DeskMetric({ label, value, emphasis = false }) {
  return (
    <div className="rounded border border-[var(--color-border)] bg-white/60 px-3 py-3">
      <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
      <div className={`mt-1 break-words ${emphasis ? 'text-lg font-serif text-[var(--color-text)]' : 'text-sm text-[var(--color-text)]'}`}>
        {value}
      </div>
    </div>
  );
}

function ForecastDeskPanel({ payload, locale = 'en', sectionCopy }) {
  const copy = getForecastText(locale);
  const statusItems = useMemo(() => getForecastSourceStatusItems(payload, locale), [payload, locale]);
  const contextItems = useMemo(() => getForecastContextItems(payload, locale), [payload, locale]);
  const coverageLabel = getForecastCoverageCopy(payload?.coverage?.mode || payload?.metadata?.coverage_quality, locale);
  const confidenceLabel = getForecastConfidenceCopy(payload?.metadata?.confidence_band, locale);
  const readyCount = statusItems.filter((item) => item.status === 'ok').length;
  const coverage = payload?.coverage || {};
  const metadata = payload?.metadata || {};

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 lg:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {sectionCopy.signalDesk}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="inline-flex items-center rounded-full bg-[var(--color-inverted)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-inverted-text)]">
              {metadata.market || 'NEM'}
            </span>
            <span className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              {coverageLabel}
            </span>
            <span className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
              {confidenceLabel}
            </span>
          </div>
        </div>

        <div className="text-right text-[10px] uppercase tracking-[0.24em] text-[var(--color-muted)]">
          {metadata.horizon || '24h'}
        </div>
      </div>

      <div className="mt-4 grid gap-3 sm:grid-cols-2">
        <DeskMetric label={copy.metrics.issuedAt} value={metadata.issued_at || metadata.as_of || copy.generic.notAvailable} emphasis />
        <DeskMetric label={copy.metrics.bucket} value={coverage.as_of_bucket || copy.generic.notAvailable} />
        <DeskMetric label={copy.metrics.forecastMode} value={getForecastModeCopy(metadata.forecast_mode, locale)} />
        <DeskMetric label={copy.metrics.sourcesReady} value={`${readyCount}/${statusItems.length || 0}`} emphasis />
        <DeskMetric label={copy.metrics.forwardPoints} value={String(coverage.forward_points || 0)} />
        <DeskMetric label={copy.metrics.historyPoints} value={String(coverage.recent_history_points || 0)} />
        <DeskMetric label={copy.metrics.eventCount} value={String(coverage.event_count || 0)} />
      </div>

      <div className="mt-5 border-t border-dashed border-[var(--color-border)] pt-4">
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {copy.metrics.sourcesReady}
        </div>
        <div className="mt-3 grid gap-2">
          {statusItems.map((item) => (
            <div
              key={item.key}
              className="flex items-center justify-between gap-3 rounded border border-[var(--color-border)] bg-white/60 px-3 py-2"
            >
              <div className="min-w-0 text-sm text-[var(--color-text)]">{item.label}</div>
              <span
                className={`inline-flex flex-shrink-0 items-center rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${sourceTone(item.status)}`}
              >
                {item.statusLabel}
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="mt-5 border-t border-dashed border-[var(--color-border)] pt-4">
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {sectionCopy.marketContext}
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          {contextItems.map((item) => (
            <DeskMetric key={item.key} label={item.label} value={item.value} />
          ))}
        </div>
      </div>
    </div>
  );
}

export default function GridForecast({ apiBase, region, locale = 'en', t }) {
  const market = region === 'WEM' ? 'WEM' : 'NEM';
  const [horizon, setHorizon] = useState('24h');
  const [payload, setPayload] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const copy = useMemo(() => getForecastText(locale), [locale]);
  const sectionCopy = useMemo(() => getForecastSectionCopy(locale, t), [locale, t]);

  useEffect(() => {
    if (!apiBase || !region) {
      return undefined;
    }

    let ignore = false;
    setLoading(true);
    setError(false);

    fetchJson(
      buildGridForecastUrl(apiBase, {
        market,
        region,
        horizon,
      })
    )
      .then((data) => {
        if (!ignore) {
          setPayload(normalizeForecastResponse(data));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!ignore) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [apiBase, market, region, horizon]);

  const horizonLabels = {
    '24h': sectionCopy.horizon24h || '24h',
    '7d': sectionCopy.horizon7d || '7d',
    '30d': sectionCopy.horizon30d || '30d',
  };
  const horizonNotes = sectionCopy.horizonNotes || {};
  const coverageLabel = getForecastCoverageCopy(payload?.coverage?.mode || payload?.metadata?.coverage_quality, locale);
  const confidenceLabel = getForecastConfidenceCopy(payload?.metadata?.confidence_band, locale);

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6"
    >
      <div className="flex flex-col gap-5 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {sectionCopy.sectionLabel}
          </div>
          <h2 className="mt-2 text-3xl font-serif text-[var(--color-text)]">{sectionCopy.title}</h2>
          <p className="mt-2 text-sm leading-6 text-[var(--color-muted)]">{sectionCopy.subtitle}</p>
          <div className="mt-4 rounded border border-dashed border-[var(--color-border)] bg-white/50 px-4 py-3 text-sm leading-6 text-[var(--color-muted)]">
            {horizonNotes[horizon] || copy.generic.notAvailable}
          </div>
          {payload && (
            <div className="mt-4 flex flex-wrap gap-2">
              <span className="inline-flex items-center rounded-full bg-[var(--color-inverted)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-inverted-text)]">
                {payload.metadata.market}
              </span>
              <span className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                {coverageLabel}
              </span>
              <span className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                {confidenceLabel}
              </span>
              <span className="inline-flex items-center rounded-full border border-[var(--color-border)] px-3 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                {getForecastModeCopy(payload.metadata.forecast_mode, locale)}
              </span>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 xl:min-w-[280px] xl:items-end">
          <div className="flex flex-wrap gap-2 rounded border border-[var(--color-border)] bg-white/60 p-1">
            {HORIZONS.map((item) => (
              <button
                key={item}
                onClick={() => setHorizon(item)}
                className={`rounded px-3 py-2 text-xs font-bold uppercase tracking-widest transition-colors ${
                  horizon === item
                    ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                    : 'text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]'
                }`}
              >
                {horizonLabels[item]}
              </button>
            ))}
          </div>

          {payload && (
            <div className="text-right text-[11px] uppercase tracking-widest text-[var(--color-muted)]">
              {payload.metadata.issued_at || copy.generic.notAvailable}
            </div>
          )}
        </div>
      </div>

      {loading ? (
        <div className="mt-8 text-sm text-[var(--color-muted)]">{sectionCopy.loading || copy.generic.notAvailable}</div>
      ) : error ? (
        <div className="mt-8 rounded border border-rose-200 bg-rose-50 px-4 py-3 text-sm text-rose-700">
          {sectionCopy.error || copy.generic.notAvailable}
        </div>
      ) : !payload ? (
        <div className="mt-8 text-sm text-[var(--color-muted)]">{sectionCopy.empty || copy.generic.notAvailable}</div>
      ) : (
        <div className="mt-8 grid gap-6 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.95fr)]">
          <div className="grid gap-6">
            <GridForecastSummaryCards summary={payload.summary} t={sectionCopy} locale={locale} />
            <GridForecastTimeline windows={payload.windows} t={sectionCopy} locale={locale} />
          </div>

          <div className="grid gap-6">
            <ForecastDeskPanel payload={payload} locale={locale} sectionCopy={sectionCopy} />
            <GridForecastDrivers drivers={payload.drivers} metadata={payload.metadata} t={sectionCopy} locale={locale} />
          </div>
        </div>
      )}
    </motion.section>
  );
}
