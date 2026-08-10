import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import { fetchJson } from '../lib/apiClient';
import {
  buildForecastLayerUrl,
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
import RegimeCompactInline from './RegimeCompactInline';
import GridForecastDiagnosticsPanel from './GridForecastDiagnosticsPanel';
import DataQualityBadge from './DataQualityBadge';

const HORIZONS = ['24h', '7d', '30d'];

// 主题感知徽章：原亮色调色板在暗色模式下出现亮色块（2026-08-10）
function sourceTone(status) {
  if (status === 'ok') {
    return 'border-[var(--color-status-success)]/40 bg-[var(--color-status-success)]/10 text-[var(--color-status-success)]';
  }
  if (status === 'partial') {
    return 'border-[var(--color-status-timeout)]/40 bg-[var(--color-status-timeout)]/10 text-[var(--color-status-timeout)]';
  }
  if (status === 'stale') {
    return 'border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-muted)]';
  }
  return 'border-[var(--color-border)] bg-[var(--color-surface-hover)] text-[var(--color-muted)]';
}

function DeskMetric({ label, value, emphasis = false }) {
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-2.5 py-2">
      <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
      <div className={`mt-0.5 break-words leading-5 ${emphasis ? 'text-[0.95rem] font-serif text-[var(--color-text)]' : 'text-sm text-[var(--color-text)]'}`}>
        {value}
      </div>
    </div>
  );
}

function GovernanceMetric({ label, value }) {
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
      <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
      <div className="mt-1 break-words text-sm text-[var(--color-text)]">{value || 'n/a'}</div>
    </div>
  );
}

function ForecastDeskPanel({ payload, locale = 'en', sectionCopy, fallbackMarket, fallbackHorizon }) {
  const [activePanel, setActivePanel] = useState('sources');
  const copy = getForecastText(locale);
  const statusItems = useMemo(() => getForecastSourceStatusItems(payload, locale), [payload, locale]);
  const contextItems = useMemo(() => getForecastContextItems(payload, locale), [payload, locale]);
  const coverageLabel = getForecastCoverageCopy(payload?.coverage?.mode || payload?.metadata?.coverage_quality, locale);
  const confidenceLabel = getForecastConfidenceCopy(payload?.metadata?.confidence_band, locale);
  const readyCount = statusItems.filter((item) => item.status === 'ok').length;
  const coverage = payload?.coverage || {};
  const metadata = payload?.metadata || {};
  const tabItems = [
    { key: 'sources', label: copy.metrics.sourcesReady },
    { key: 'context', label: sectionCopy.marketContext },
  ];

  return (
    <div className="h-full rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
              {sectionCopy.signalDesk}
          </div>
          <div className="mt-2 flex flex-wrap gap-2">
            <span className="inline-flex items-center rounded-full bg-[var(--color-inverted)] px-3 py-1 text-[10px] font-bold uppercase tracking-widest text-[var(--color-inverted-text)]">
              {metadata.market || fallbackMarket}
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
          {metadata.horizon || fallbackHorizon}
        </div>
      </div>

      <div className="mt-2.5 grid gap-2 sm:grid-cols-2">
        <DeskMetric label={copy.metrics.issuedAt} value={metadata.issued_at || metadata.as_of || copy.generic.notAvailable} emphasis />
        <DeskMetric label={copy.metrics.bucket} value={coverage.as_of_bucket || copy.generic.notAvailable} />
        <DeskMetric label={copy.metrics.forecastMode} value={getForecastModeCopy(metadata.forecast_mode, locale)} />
        <DeskMetric label={copy.metrics.sourcesReady} value={`${readyCount}/${statusItems.length || 0}`} emphasis />
        <DeskMetric label={copy.metrics.forwardPoints} value={String(coverage.forward_points || 0)} />
        <DeskMetric label={copy.metrics.historyPoints} value={String(coverage.recent_history_points || 0)} />
        <DeskMetric label={copy.metrics.eventCount} value={String(coverage.event_count || 0)} />
      </div>

      <div className="mt-3 border-t border-dashed border-[var(--color-border)] pt-2.5">
        <div className="flex flex-wrap gap-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-1">
          {tabItems.map((item) => (
            <button
              key={item.key}
              type="button"
              onClick={() => setActivePanel(item.key)}
              className={`rounded px-3 py-1.5 text-[10px] font-bold uppercase tracking-widest transition-colors ${
                activePanel === item.key
                  ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)]'
                  : 'text-[var(--color-muted)] hover:bg-[var(--color-surface-hover)] hover:text-[var(--color-text)]'
              }`}
            >
              {item.label}
            </button>
          ))}
        </div>

        <div className="mt-2.5 max-h-[220px] overflow-y-auto pr-1">
          {activePanel === 'sources' ? (
            <div className="grid gap-2">
              {statusItems.map((item) => (
                <div
                  key={item.key}
                  className="flex items-center justify-between gap-3 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2"
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
          ) : (
            <div className="grid gap-2 sm:grid-cols-2">
              {contextItems.map((item) => (
                <DeskMetric key={item.key} label={item.label} value={item.value} />
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

export default function GridForecast({ apiBase, region, locale = 'en', t, regimeCompactCopy }) {
  const market = region === 'WEM' ? 'WEM' : 'NEM';
  const [horizon, setHorizon] = useState('30d');
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
    setPayload(null);

    fetchJson(
      buildForecastLayerUrl(apiBase, {
        market,
        region,
        horizon,
      })
    )
      .then((data) => {
        if (!ignore) {
          const normalized = normalizeForecastResponse(data);
          if (!normalized || (!normalized.windows?.length && !normalized.coverage?.forward_points)) {
            console.warn('[GridForecast] Empty payload after normalization:', { data, normalized });
          }
          setPayload(normalized);
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
    '24h': sectionCopy.horizon24h,
    '7d': sectionCopy.horizon7d,
    '30d': sectionCopy.horizon30d,
  };
  const horizonNotes = sectionCopy.horizonNotes || {};
  const coverageLabel = getForecastCoverageCopy(payload?.coverage?.mode || payload?.metadata?.coverage_quality, locale);
  const confidenceLabel = getForecastConfidenceCopy(payload?.metadata?.confidence_band, locale);
  const governance = payload?.governance || null;
  const forecastStatusMetadata = payload
    ? {
        ...payload.metadata,
        freshness: payload.metadata?.freshness || governance?.freshness || {},
      }
    : null;
  const forecastStatusTags = payload
    ? [
        { label: locale === 'zh' ? '覆盖' : 'Coverage', value: payload.coverageMode || payload.coverage?.mode || payload.metadata?.coverage_quality, format: 'coverage_mode' },
        { label: locale === 'zh' ? '范围' : 'Scope', value: payload.regulatoryScope || governance?.disclaimer?.usage_scope || '' },
        { label: locale === 'zh' ? '市场' : 'Market', value: market },
      ]
    : [];
  const isWemPreview = market === 'WEM';
  const wemOutlookCaveat = locale === 'zh'
    ? `WEM 的市场设计与 NEM 不同。当前展望主要覆盖 ${Array.isArray(payload?.valueStreamCoverage) && payload.valueStreamCoverage.length ? payload.valueStreamCoverage.join('、') : '能量与备用代理'}，适合用于方向判断，不代表完整市场或容量收入结论。`
    : `WEM follows a different market design from NEM. This outlook currently covers ${Array.isArray(payload?.valueStreamCoverage) && payload.valueStreamCoverage.length ? payload.valueStreamCoverage.join(', ') : 'energy and reserve proxy streams'} and is best used for directional assessment rather than a full-market or capacity-revenue conclusion.`;

  return (
    <motion.section
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.4, ease: 'easeOut' }}
      className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4"
    >
      <div className="flex flex-col gap-3 xl:flex-row xl:items-start xl:justify-between">
        <div className="max-w-3xl">
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {sectionCopy.sectionLabel}
          </div>
          <h2 className="mt-1 text-2xl font-serif text-[var(--color-text)] md:text-[1.75rem]">{sectionCopy.title}</h2>
          <p className="mt-1 text-xs leading-5 text-[var(--color-muted)] md:overflow-hidden md:text-ellipsis md:whitespace-nowrap">{sectionCopy.subtitle}</p>
          <div className="mt-2 rounded border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2 text-xs leading-5 text-[var(--color-muted)]">
            {horizonNotes[horizon] || copy.generic.notAvailable}
          </div>
          {payload && (
            <div className="mt-2 flex flex-wrap gap-2">
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
          {forecastStatusMetadata && (
            <div className="mt-3">
              <DataQualityBadge metadata={forecastStatusMetadata} lang={locale} tags={forecastStatusTags} />
            </div>
          )}
          {isWemPreview && (
            <div className="mt-3 rounded border border-[var(--color-status-timeout)]/50 bg-[var(--color-status-timeout)]/8 px-3 py-2 text-xs leading-5 text-[var(--color-muted)]">
              <div className="font-semibold">
                {locale === 'zh' ? 'WEM 独立制度提醒' : 'WEM Market-Design Caveat'}
              </div>
              <div className="mt-1">{wemOutlookCaveat}</div>
            </div>
          )}
        </div>

        <div className="flex flex-col gap-3 xl:min-w-[280px] xl:items-end">
          <div className="flex flex-wrap gap-2 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-1">
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
        <div className="mt-6 text-sm text-[var(--color-muted)]">{sectionCopy.loading || copy.generic.notAvailable}</div>
      ) : error ? (
        <div className="mt-6 rounded border border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/8 px-4 py-3 text-sm text-[var(--color-status-error)]">
          {sectionCopy.error || copy.generic.notAvailable}
        </div>
      ) : !payload ? (
        null
      ) : (
        <>
        <div className="mt-6 grid items-stretch gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(320px,0.95fr)]">
          <div className="grid content-start gap-2">
            <RegimeCompactInline compact={payload.regime_compact} copy={regimeCompactCopy} />
            <GridForecastSummaryCards summary={payload.summary} t={sectionCopy} locale={locale} />
            <GridForecastDiagnosticsPanel
              baselineForecast={{
                ...(payload.baselineForecast || {}),
                governance_proxy: governance?.forecast_value_attribution || null,
              }}
              locale={locale}
            />
            <GridForecastTimeline windows={payload.windows} t={sectionCopy} locale={locale} />
          </div>

            <div className="grid">
              <ForecastDeskPanel payload={payload} locale={locale} sectionCopy={sectionCopy} fallbackMarket={market} fallbackHorizon={horizon} />
            </div>
          </div>

          <div className="mt-3">
            <GridForecastDrivers drivers={payload.drivers} metadata={payload.metadata} t={sectionCopy} locale={locale} />
          </div>

          {governance && (
            <div className="mt-3 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3.5">
              <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
                {sectionCopy.governanceTitle}
              </div>
              <div className="mt-3 grid gap-2 md:grid-cols-4">
                <GovernanceMetric label={sectionCopy.governanceFreshness} value={governance?.freshness?.status} />
                <GovernanceMetric label={sectionCopy.governanceDrift} value={governance?.drift?.status} />
                <GovernanceMetric label={sectionCopy.governanceDisclaimer} value={governance?.disclaimer?.usage_scope} />
                <GovernanceMetric label={sectionCopy.governanceLineage} value={governance?.lineage?.source_id} />
              </div>
            </div>
          )}
        </>
      )}
    </motion.section>
  );
}
