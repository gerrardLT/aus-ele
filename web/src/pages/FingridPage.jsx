import { useEffect, useMemo, useRef, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import {
  buildFingridExportUrl,
  buildFingridSeriesUrl,
  buildFingridStatusUrl,
  buildFingridSummaryUrl,
  buildFingridSyncUrl,
  normalizeFingridDatasetList,
} from '../lib/fingridApi';
import { buildFingridTimeWindow, getCustomDateRangeValidationCode } from '../lib/fingridDataset';
import {
  buildFingridRequestLimit,
  getFingridCopy,
  localizeFingridDataset,
} from '../lib/fingridUi';
import FingridDistributionPanel from '../components/fingrid/FingridDistributionPanel';
import FingridHeader from '../components/fingrid/FingridHeader';
import FingridSeriesChart from '../components/fingrid/FingridSeriesChart';
import FingridStatusPanel from '../components/fingrid/FingridStatusPanel';
import FingridSummaryCards from '../components/fingrid/FingridSummaryCards';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';
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
  const [syncing, setSyncing] = useState(false);
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

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fetch(buildFingridSyncUrl(API_BASE, datasetId), { method: 'POST' });
      const statusData = await fetchJson(buildFingridStatusUrl(API_BASE, datasetId));
      const nextRefreshKey = buildStatusRefreshKey(statusData);
      const previousRefreshKey = statusRefreshKeyRef.current;
      statusRefreshKeyRef.current = nextRefreshKey;
      setStatusPayload(statusData);
      if (previousRefreshKey && previousRefreshKey !== nextRefreshKey) {
        setRefreshNonce((value) => value + 1);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <main className="min-h-screen bg-[var(--color-background)] px-6 py-8 text-[var(--color-text)]">
      <div className="mx-auto grid max-w-7xl gap-6">
        <FingridHeader
          datasets={localizedDatasets}
          datasetId={datasetId}
          onDatasetChange={setDatasetId}
          preset={preset}
          onPresetChange={setPreset}
          aggregation={aggregation}
          onAggregationChange={setAggregation}
          tz={tz}
          onTimezoneChange={setTz}
          statusPayload={statusPayload}
          syncing={syncing}
          onSync={handleSync}
          exportHref={exportHref}
          copy={copy}
          onLanguageToggle={() => setLang((current) => (current === 'zh' ? 'en' : 'zh'))}
          customStartDate={customStartDate}
          customEndDate={customEndDate}
          onCustomStartDateChange={setCustomStartDate}
          onCustomEndDateChange={setCustomEndDate}
          validationMessage={customDateRangeValidationMessage}
        />
        <FingridSummaryCards
          summaryPayload={summaryPayload}
          seriesPayload={seriesPayload}
          aggregation={aggregation}
          loading={loading}
          lang={lang}
        />
        <FingridSeriesChart payload={seriesPayload} loading={loading} error={error} copy={copy} />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
          <FingridDistributionPanel payload={summaryPayload} loading={loading} copy={copy} />
          <FingridStatusPanel payload={statusPayload} loading={loading} error={error} copy={copy} lang={lang} />
        </div>
      </div>
    </main>
  );
}
