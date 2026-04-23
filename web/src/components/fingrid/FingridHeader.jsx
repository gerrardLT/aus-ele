export default function FingridHeader({
  datasets,
  datasetId,
  onDatasetChange,
  preset,
  onPresetChange,
  aggregation,
  onAggregationChange,
  tz,
  onTimezoneChange,
  statusPayload,
  syncing,
  onSync,
  exportHref,
}) {
  const dataset = datasets.find((item) => item.dataset_id === datasetId) || {};
  const status = statusPayload?.status || {};

  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">Fingrid</div>
          <h1 className="mt-2 text-3xl font-serif text-[var(--color-text)]">{dataset.name || 'Dataset 317'}</h1>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-muted)]">{dataset.description}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs uppercase tracking-widest text-[var(--color-muted)]">
            <span>{dataset.dataset_id || '317'}</span>
            <span>{dataset.unit || 'EUR/MW'}</span>
            <span>{dataset.frequency || '1h'}</span>
            <span>{status.last_success_at || 'not-synced'}</span>
          </div>
        </div>
        <div className="flex flex-wrap gap-2">
          <select
            value={datasetId}
            onChange={(event) => onDatasetChange(event.target.value)}
            className="rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
          >
            {datasets.map((item) => (
              <option key={item.dataset_id} value={item.dataset_id}>
                {item.name}
              </option>
            ))}
          </select>
          <select
            value={preset}
            onChange={(event) => onPresetChange(event.target.value)}
            className="rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
          >
            {['7d', '30d', '90d', '1y', 'all'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={aggregation}
            onChange={(event) => onAggregationChange(event.target.value)}
            className="rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
          >
            {['raw', 'day', 'week', 'month'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={tz}
            onChange={(event) => onTimezoneChange(event.target.value)}
            className="rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
          >
            {['Europe/Helsinki', 'UTC'].map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <button
            onClick={onSync}
            disabled={syncing}
            className="rounded bg-[var(--color-inverted)] px-4 py-2 text-sm font-medium text-[var(--color-inverted-text)] disabled:opacity-60"
          >
            {syncing ? 'Syncing...' : 'Sync'}
          </button>
          <a
            href={exportHref}
            className="rounded border border-[var(--color-border)] px-4 py-2 text-sm text-[var(--color-text)]"
          >
            Export CSV
          </a>
        </div>
      </div>
    </section>
  );
}
