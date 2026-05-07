import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import { getApiBase } from '../lib/apiBase';
import {
  buildFingridAllMarketsExportUrl,
  buildFingridExportUrl,
  buildFingridSeriesUrl,
  buildFingridStatusUrl,
  buildFingridSummaryUrl,
  normalizeFingridDatasetList,
} from '../lib/fingridApi';
import { buildFingridTimeWindow, getCustomDateRangeValidationCode } from '../lib/fingridDataset';
import {
  buildFingridRequestLimit,
  getFingridCopy,
  localizeFingridDataset,
} from '../lib/fingridUi';
import PageWorkspaceNav from '../components/PageWorkspaceNav';
import FingridHeader from '../components/fingrid/FingridHeader';
import FingridHourlyBoard from '../components/fingrid/FingridHourlyBoard';
import FingridYearlyPlanBoard from '../components/fingrid/FingridYearlyPlanBoard';

const API_BASE = getApiBase();
const LANG_STORAGE_KEY = 'app_lang';
const AUTO_REFRESH_STATUS_INTERVAL_MS = 5 * 60 * 1000;

function readPreferredLang() {
  try {
    return globalThis.localStorage?.getItem(LANG_STORAGE_KEY) || 'zh';
  } catch {
    return 'zh';
  }
}

function buildStatusRefreshKey(payload) {
  const status = payload?.status || {};
  return [
    status.dataset_id || '',
    status.last_success_at || '',
    status.coverage_end_utc || '',
    status.record_count || 0,
  ].join('|');
}

export default function FingridPage() {
  const [lang, setLang] = useState(() => readPreferredLang());
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetId] = useState('317');
  const [preset, setPreset] = useState('30d');
  const [customStartDate, setCustomStartDate] = useState('');
  const [customEndDate, setCustomEndDate] = useState('');
  const [aggregation, setAggregation] = useState('day');
  const [tz, setTz] = useState('Europe/Helsinki');
  const [seriesPayload, setSeriesPayload] = useState(null);
  const [summaryPayload, setSummaryPayload] = useState(null);
  const [statusPayload, setStatusPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [refreshNonce, setRefreshNonce] = useState(0);
  const statusRefreshKeyRef = useRef('');
  const copy = useMemo(() => getFingridCopy(lang), [lang]);
  const localizedDatasets = useMemo(
    () => datasets.map((dataset) => localizeFingridDataset(dataset, lang)),
    [datasets, lang],
  );
  const requestLimit = useMemo(
    () => buildFingridRequestLimit({ preset, aggregation }),
    [preset, aggregation],
  );
  const customDateRangeValidationCode = useMemo(
    () => getCustomDateRangeValidationCode({ preset, customStartDate, customEndDate }),
    [preset, customStartDate, customEndDate],
  );
  const customDateRangeValidationMessage = customDateRangeValidationCode
    ? copy.validation[customDateRangeValidationCode]
    : null;
  const marketModelCopy = copy.marketModel || {};
  const workspaceLinkCopy = copy.workspaceLinks || {};
  const statusMetadata = statusPayload?.metadata || statusPayload?.status_metadata || statusPayload?.status?.metadata || null;
  const selectedDataset = useMemo(
    () => localizedDatasets.find((item) => item.dataset_id === datasetId) || null,
    [localizedDatasets, datasetId],
  );
  const presetOptions = useMemo(
    () => (selectedDataset?.groupKey === 'yearly_plans' ? ['1y', 'all', 'custom'] : ['7d', '30d', '90d', '1y', 'all', 'custom']),
    [selectedDataset],
  );
  const aggregationOptions = useMemo(
    () => selectedDataset?.supported_aggregations || ['raw', '1h', '2h', '4h', 'day', 'week', 'month'],
    [selectedDataset],
  );

  useEffect(() => {
    try {
      globalThis.localStorage?.setItem(LANG_STORAGE_KEY, lang);
    } catch {
      // Ignore localStorage write failures in restricted environments.
    }
  }, [lang]);

  useEffect(() => {
    let cancelled = false;

    fetchJson(`${API_BASE}/fingrid/datasets`)
      .then((payload) => {
        if (!cancelled) {
          setDatasets(normalizeFingridDatasetList(payload));
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(String(err));
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (localizedDatasets.length > 0 && !localizedDatasets.some((item) => item.dataset_id === datasetId)) {
      setDatasetId(localizedDatasets[0].dataset_id);
    }
  }, [localizedDatasets, datasetId]);

  useEffect(() => {
    if (!selectedDataset) {
      return;
    }

    const supportedAggregations = new Set(selectedDataset.supported_aggregations || []);
    if (!supportedAggregations.has(aggregation)) {
      if (selectedDataset.groupKey === 'yearly_plans') {
        setAggregation(supportedAggregations.has('month') ? 'month' : (selectedDataset.supported_aggregations?.[0] || 'month'));
      } else {
        setAggregation(supportedAggregations.has('day') ? 'day' : (selectedDataset.supported_aggregations?.[0] || 'day'));
      }
      return;
    }

    if (selectedDataset.groupKey === 'yearly_plans') {
      if (preset !== 'all' && preset !== '1y' && preset !== 'custom') {
        setPreset('1y');
      }
      if (aggregation === 'raw' || aggregation === '1h' || aggregation === '2h' || aggregation === '4h') {
        setAggregation(supportedAggregations.has('month') ? 'month' : (selectedDataset.supported_aggregations?.[0] || 'month'));
      }
    }
  }, [selectedDataset, aggregation, preset]);

  const timeWindow = useMemo(
    () => buildFingridTimeWindow({ preset, customStartDate, customEndDate, tz }),
    [preset, customStartDate, customEndDate, tz],
  );

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    if (customDateRangeValidationCode) {
      setSeriesPayload(null);
      setSummaryPayload(null);
      setLoading(false);
      return () => {
        cancelled = true;
      };
    }

    Promise.all([
      fetchJson(buildFingridSeriesUrl(API_BASE, { datasetId, ...timeWindow, tz, aggregation, limit: requestLimit })),
      fetchJson(buildFingridSummaryUrl(API_BASE, { datasetId, ...timeWindow })),
      fetchJson(buildFingridStatusUrl(API_BASE, datasetId)),
    ])
      .then(([seriesData, summaryData, statusData]) => {
        if (cancelled) {
          return;
        }
        setSeriesPayload(seriesData);
        setSummaryPayload(summaryData);
        setStatusPayload(statusData);
        statusRefreshKeyRef.current = buildStatusRefreshKey(statusData);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        setError(String(err));
        setLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [datasetId, timeWindow, tz, aggregation, requestLimit, customDateRangeValidationCode, refreshNonce]);

  useEffect(() => {
    let cancelled = false;

    const pollStatus = async () => {
      try {
        const nextStatusPayload = await fetchJson(buildFingridStatusUrl(API_BASE, datasetId));
        if (cancelled) {
          return;
        }
        const nextRefreshKey = buildStatusRefreshKey(nextStatusPayload);
        const previousRefreshKey = statusRefreshKeyRef.current;
        statusRefreshKeyRef.current = nextRefreshKey;
        setStatusPayload(nextStatusPayload);
        if (previousRefreshKey && previousRefreshKey !== nextRefreshKey) {
          setRefreshNonce((value) => value + 1);
        }
      } catch (err) {
        if (!cancelled) {
          console.warn('Fingrid status polling failed', err);
        }
      }
    };

    const intervalId = globalThis.setInterval(pollStatus, AUTO_REFRESH_STATUS_INTERVAL_MS);
    return () => {
      cancelled = true;
      globalThis.clearInterval(intervalId);
    };
  }, [datasetId]);

  const exportHref = useMemo(
    () => (
      customDateRangeValidationCode
        ? null
        : buildFingridExportUrl(API_BASE, { datasetId, ...timeWindow, tz, aggregation, limit: requestLimit })
    ),
    [datasetId, timeWindow, tz, aggregation, requestLimit, customDateRangeValidationCode],
  );
  const exportAllHref = useMemo(
    () => (
      customDateRangeValidationCode
        ? null
        : buildFingridAllMarketsExportUrl(API_BASE, { ...timeWindow, tz, aggregation, limit: requestLimit })
    ),
    [timeWindow, tz, aggregation, requestLimit, customDateRangeValidationCode],
  );
  const isYearlyPlanBoard = selectedDataset?.groupKey === 'yearly_plans';
  const workspaceLinks = [
    { key: 'home', href: '/', label: workspaceLinkCopy.home || 'Home' },
    { key: 'finland', href: '/finland', label: workspaceLinkCopy.finland || 'Finland Board' },
    { key: 'fingrid', href: '/fingrid', label: workspaceLinkCopy.fingrid || 'Fingrid' },
    { key: 'developer', href: '/developer', label: workspaceLinkCopy.developer || 'Developer Portal' },
  ];
  const toolbar = (
    <FingridHeader
      datasets={localizedDatasets}
      datasetId={datasetId}
      onDatasetChange={setDatasetId}
      preset={preset}
      onPresetChange={setPreset}
      presetOptions={presetOptions}
      aggregation={aggregation}
      onAggregationChange={setAggregation}
      aggregationOptions={aggregationOptions}
      tz={tz}
      onTimezoneChange={setTz}
      statusPayload={statusPayload}
      exportHref={exportHref}
      exportAllHref={exportAllHref}
      copy={copy}
      customStartDate={customStartDate}
      customEndDate={customEndDate}
      onCustomStartDateChange={setCustomStartDate}
      onCustomEndDateChange={setCustomEndDate}
      validationMessage={customDateRangeValidationMessage}
      toolbarOnly
    />
  );

  return (
    <main
      className={`min-h-screen px-6 py-8 text-[var(--color-text)] ${
        isYearlyPlanBoard
          ? 'bg-[radial-gradient(circle_at_top_left,color-mix(in_srgb,var(--color-accent)_10%,transparent),transparent_28%),linear-gradient(180deg,color-mix(in_srgb,var(--color-panel)_55%,var(--color-background)),var(--color-background))]'
          : 'bg-[radial-gradient(circle_at_top_right,color-mix(in_srgb,var(--color-accent)_8%,transparent),transparent_24%),linear-gradient(180deg,color-mix(in_srgb,var(--color-surface)_72%,var(--color-background)),var(--color-background))]'
      }`}
    >
      <div className="mx-auto grid grid-cols-1 max-w-7xl gap-8">
        <PageWorkspaceNav
          brand={copy.brand}
          title={null}
          subtitle={null}
          current="fingrid"
          links={workspaceLinks}
          languageLabel={copy.toggleLanguage}
          languageAriaLabel={copy.toggleLanguageAriaLabel}
          onToggleLanguage={() => setLang((current) => (current === 'zh' ? 'en' : 'zh'))}
          compact
          meta={null}
        />

        {isYearlyPlanBoard ? (
          <>
            <FingridYearlyPlanBoard
              dataset={selectedDataset}
              summaryPayload={summaryPayload}
              seriesPayload={seriesPayload}
              statusPayload={statusPayload}
              statusMetadata={statusMetadata}
              loading={loading}
              error={error}
              copy={copy}
              lang={lang}
              mode="hero"
              controls={toolbar}
            />
            <FingridYearlyPlanBoard
              dataset={selectedDataset}
              summaryPayload={summaryPayload}
              seriesPayload={seriesPayload}
              statusPayload={statusPayload}
              statusMetadata={statusMetadata}
              loading={loading}
              error={error}
              copy={copy}
              lang={lang}
              mode="details"
            />
          </>
        ) : (
          <>
            <FingridHourlyBoard
              summaryPayload={summaryPayload}
              seriesPayload={seriesPayload}
              statusPayload={statusPayload}
              statusMetadata={statusMetadata}
              loading={loading}
              error={error}
              copy={copy}
              lang={lang}
              marketModelCopy={marketModelCopy}
              mode="hero"
              controls={toolbar}
            />

            <FingridHourlyBoard
              summaryPayload={summaryPayload}
              seriesPayload={seriesPayload}
              statusPayload={statusPayload}
              statusMetadata={statusMetadata}
              loading={loading}
              error={error}
              copy={copy}
              lang={lang}
              marketModelCopy={marketModelCopy}
              mode="details"
            />
          </>
        )}
      </div>
    </main>
  );
}
