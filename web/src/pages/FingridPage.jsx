import { useEffect, useMemo, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import {
  buildFingridExportUrl,
  buildFingridSeriesUrl,
  buildFingridStatusUrl,
  buildFingridSummaryUrl,
  buildFingridSyncUrl,
  normalizeFingridDatasetList,
} from '../lib/fingridApi';
import { buildPresetWindow } from '../lib/fingridDataset';
import FingridDistributionPanel from '../components/fingrid/FingridDistributionPanel';
import FingridHeader from '../components/fingrid/FingridHeader';
import FingridSeriesChart from '../components/fingrid/FingridSeriesChart';
import FingridStatusPanel from '../components/fingrid/FingridStatusPanel';
import FingridSummaryCards from '../components/fingrid/FingridSummaryCards';

const API_BASE = import.meta.env.VITE_API_BASE || 'http://127.0.0.1:8085/api';

export default function FingridPage() {
  const [datasets, setDatasets] = useState([]);
  const [datasetId, setDatasetId] = useState('317');
  const [preset, setPreset] = useState('30d');
  const [aggregation, setAggregation] = useState('day');
  const [tz, setTz] = useState('Europe/Helsinki');
  const [seriesPayload, setSeriesPayload] = useState(null);
  const [summaryPayload, setSummaryPayload] = useState(null);
  const [statusPayload, setStatusPayload] = useState(null);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState(null);

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
    if (datasets.length > 0 && !datasets.some((item) => item.dataset_id === datasetId)) {
      setDatasetId(datasets[0].dataset_id);
    }
  }, [datasets, datasetId]);

  const timeWindow = useMemo(() => buildPresetWindow(preset), [preset]);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([
      fetchJson(buildFingridSeriesUrl(API_BASE, { datasetId, ...timeWindow, tz, aggregation, limit: 5000 })),
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
  }, [datasetId, timeWindow, tz, aggregation]);

  const exportHref = useMemo(
    () => buildFingridExportUrl(API_BASE, { datasetId, ...timeWindow, tz, aggregation, limit: 5000 }),
    [datasetId, timeWindow, tz, aggregation],
  );

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fetch(buildFingridSyncUrl(API_BASE, datasetId), { method: 'POST' });
      const statusData = await fetchJson(buildFingridStatusUrl(API_BASE, datasetId));
      setStatusPayload(statusData);
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
          datasets={datasets}
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
        />
        <FingridSummaryCards payload={summaryPayload} loading={loading} />
        <FingridSeriesChart payload={seriesPayload} loading={loading} error={error} />
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1.3fr)_minmax(320px,0.9fr)]">
          <FingridDistributionPanel payload={summaryPayload} loading={loading} />
          <FingridStatusPanel payload={statusPayload} loading={loading} error={error} />
        </div>
      </div>
    </main>
  );
}
