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
  copy,
  onLanguageToggle,
  customStartDate,
  customEndDate,
  onCustomStartDateChange,
  onCustomEndDateChange,
  validationMessage,
}) {
  const dataset = datasets.find((item) => item.dataset_id === datasetId) || {};
  const status = statusPayload?.status || {};

  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="flex flex-col gap-4 xl:flex-row xl:items-start xl:justify-between">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">{copy.brand}</div>
          <h1 className="mt-2 text-3xl font-serif text-[var(--color-text)]">{dataset.name || copy.datasetFallback}</h1>
          <p className="mt-2 max-w-3xl text-sm text-[var(--color-muted)]">{dataset.description}</p>
          <div className="mt-3 flex flex-wrap gap-2 text-xs uppercase tracking-widest text-[var(--color-muted)]">
            <span>{dataset.dataset_id || '317'}</span>
            <span>{dataset.unit || 'EUR/MW'}</span>
            <span>{dataset.frequency || '1h'}</span>
            <span>{status.last_success_at || copy.notSynced}</span>
          </div>
        </div>
        <div className="flex max-w-4xl flex-wrap gap-2">
          <a
            href="/"
            className="rounded border border-[var(--color-border)] px-4 py-2 text-sm text-[var(--color-text)]"
          >
            {copy.navToAemo}
          </a>
          <button
            onClick={onLanguageToggle}
            className="rounded border border-[var(--color-border)] px-4 py-2 text-sm text-[var(--color-text)]"
          >
            {copy.toggleLanguage}
          </button>
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
            {['7d', '30d', '90d', '1y', 'all', 'custom'].map((item) => (
              <option key={item} value={item}>
                {copy.presetLabels[item] || item}
              </option>
            ))}
          </select>
          <select
            value={aggregation}
            onChange={(event) => onAggregationChange(event.target.value)}
            className="rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm"
          >
            {['raw', '1h', '2h', '4h', 'day', 'week', 'month'].map((item) => (
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
                {copy.timezoneLabels[item] || item}
              </option>
            ))}
          </select>
          <button
            onClick={onSync}
            disabled={syncing}
            className="rounded bg-[var(--color-inverted)] px-4 py-2 text-sm font-medium text-[var(--color-inverted-text)] disabled:opacity-60"
          >
            {syncing ? copy.syncing : copy.sync}
          </button>
          <a
            href={exportHref || undefined}
            aria-disabled={!exportHref}
            className={`rounded border border-[var(--color-border)] px-4 py-2 text-sm text-[var(--color-text)] ${
              exportHref ? '' : 'pointer-events-none opacity-50'
            }`}
          >
            {copy.exportCsv}
          </a>
          {preset === 'custom' && (
            <div className="basis-full pt-2">
              <div className="flex flex-wrap gap-2">
                <label className="flex items-center gap-2 rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm">
                  <span className="text-[var(--color-muted)]">{copy.startDate}</span>
                  <input
                    type="date"
                    value={customStartDate}
                    onChange={(event) => onCustomStartDateChange(event.target.value)}
                    className="min-w-[140px] bg-transparent text-[var(--color-text)] outline-none"
                  />
                </label>
                <label className="flex items-center gap-2 rounded border border-[var(--color-border)] bg-white px-3 py-2 text-sm">
                  <span className="text-[var(--color-muted)]">{copy.endDate}</span>
                  <input
                    type="date"
                    value={customEndDate}
                    onChange={(event) => onCustomEndDateChange(event.target.value)}
                    className="min-w-[140px] bg-transparent text-[var(--color-text)] outline-none"
                  />
                </label>
              </div>
              {validationMessage && (
                <div className="mt-2 text-sm text-rose-600">{validationMessage}</div>
              )}
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
