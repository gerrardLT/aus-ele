import { groupFingridDatasets } from '../../lib/fingridUi';

export default function FingridHeader({
  datasets,
  datasetId,
  onDatasetChange,
  preset,
  onPresetChange,
  presetOptions,
  aggregation,
  onAggregationChange,
  aggregationOptions,
  tz,
  onTimezoneChange,
  statusPayload,
  exportHref,
  exportAllHref,
  copy,
  customStartDate,
  customEndDate,
  onCustomStartDateChange,
  onCustomEndDateChange,
  validationMessage,
  compactLayout = false,
  toolbarOnly = false,
}) {
  const dataset = datasets.find((item) => item.dataset_id === datasetId) || {};
  const status = statusPayload?.status || {};
  const groupedDatasets = groupFingridDatasets(datasets);
  const datasetGroupLabel = copy.datasetGroups?.[dataset.groupKey] || copy.datasetGroups?.other;
  const datasetBehaviorNotice = dataset.groupKey === 'yearly_plans'
    ? copy.yearlyDatasetNotice
    : copy.hourlyDatasetNotice;
  const controlClassName =
    'min-h-[44px] rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2 text-sm text-[var(--color-text)] shadow-sm outline-none transition focus-visible:border-[var(--color-accent)] focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_srgb,var(--color-accent)_28%,transparent)]';
  const buttonClassName =
    'inline-flex min-h-[44px] items-center justify-center rounded border border-[var(--color-border)] bg-[var(--color-panel)] px-4 py-2 text-sm text-[var(--color-text)] shadow-sm transition hover:border-[var(--color-accent)] hover:text-[var(--color-accent)] focus-visible:border-[var(--color-accent)] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[color:color-mix(in_srgb,var(--color-accent)_28%,transparent)]';
  const metaPillClassName =
    'rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1 text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]';
  const isYearlyPlanBoard = dataset.groupKey === 'yearly_plans';
  const useCompactLayout = compactLayout || isYearlyPlanBoard;
  const compactDescription = dataset.productLabel || dataset.description || copy.datasetFallback;

  if (toolbarOnly) {
    return (
      <section className={`grid gap-3 rounded-xl border p-4 shadow-[0_12px_30px_color-mix(in_srgb,var(--color-background)_78%,transparent)] ${
        isYearlyPlanBoard
          ? 'border-[color:color-mix(in_srgb,var(--color-accent)_24%,var(--color-border))] bg-[color:color-mix(in_srgb,var(--color-panel)_92%,var(--color-accent)_8%)]'
          : 'border-[var(--color-border)] bg-[color:color-mix(in_srgb,var(--color-panel)_96%,var(--color-surface)_4%)]'
      }`}>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div className="flex flex-wrap items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
            <span>{copy.controlsTitle}</span>
            <span className={metaPillClassName}>{dataset.dataset_id || copy.defaultDatasetId}</span>
          </div>
          <div
            data-testid="fingrid-header-actions"
            className="flex flex-wrap items-center justify-end gap-2"
          >
            <a
              href={exportHref || undefined}
              aria-disabled={!exportHref}
              className={`${buttonClassName} px-3 text-xs ${exportHref ? '' : 'pointer-events-none opacity-50'}`}
            >
              {copy.exportCsv}
            </a>
            <a
              href={exportAllHref || undefined}
              aria-disabled={!exportAllHref}
              className={`${buttonClassName} px-3 text-xs ${exportAllHref ? '' : 'pointer-events-none opacity-50'}`}
            >
              {copy.exportAllMarketsCsv}
            </a>
          </div>
        </div>
        <div
          data-testid="fingrid-header-filters"
          className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4"
        >
          <select
            value={datasetId}
            onChange={(event) => onDatasetChange(event.target.value)}
            aria-label={copy.datasetSelectorLabel}
            className={`${controlClassName} min-w-0`}
          >
            {groupedDatasets.map((group) => (
              <optgroup key={group.key} label={copy.datasetGroups?.[group.key] || group.key}>
                {group.items.map((item) => (
                  <option key={item.dataset_id} value={item.dataset_id}>
                    {item.name}
                  </option>
                ))}
              </optgroup>
            ))}
          </select>
          <select
            value={preset}
            onChange={(event) => onPresetChange(event.target.value)}
            className={`${controlClassName} min-w-0`}
          >
            {presetOptions.map((item) => (
              <option key={item} value={item}>
                {copy.presetLabels[item] || item}
              </option>
            ))}
          </select>
          <select
            value={aggregation}
            onChange={(event) => onAggregationChange(event.target.value)}
            className={`${controlClassName} min-w-0`}
          >
            {aggregationOptions.map((item) => (
              <option key={item} value={item}>
                {item}
              </option>
            ))}
          </select>
          <select
            value={tz}
            onChange={(event) => onTimezoneChange(event.target.value)}
            className={`${controlClassName} min-w-0`}
          >
            {['Europe/Helsinki', 'UTC'].map((item) => (
              <option key={item} value={item}>
                {copy.timezoneLabels[item] || item}
              </option>
            ))}
          </select>
        </div>
        {preset === 'custom' ? (
          <div className="grid gap-2 sm:grid-cols-2">
            <label className={`${controlClassName} flex items-center gap-2`}>
              <span className="text-[var(--color-muted)]">{copy.startDate}</span>
              <input
                type="date"
                value={customStartDate}
                onChange={(event) => onCustomStartDateChange(event.target.value)}
                className="min-w-0 flex-1 bg-transparent text-[var(--color-text)] outline-none"
              />
            </label>
            <label className={`${controlClassName} flex items-center gap-2`}>
              <span className="text-[var(--color-muted)]">{copy.endDate}</span>
              <input
                type="date"
                value={customEndDate}
                onChange={(event) => onCustomEndDateChange(event.target.value)}
                className="min-w-0 flex-1 bg-transparent text-[var(--color-text)] outline-none"
              />
            </label>
            {validationMessage ? (
              <div className="sm:col-span-2 text-sm text-[var(--color-status-error)]">{validationMessage}</div>
            ) : null}
          </div>
        ) : null}
      </section>
    );
  }

  return (
    <section className={`rounded-xl border ${useCompactLayout ? 'p-5' : 'p-6'} shadow-[0_14px_40px_color-mix(in_srgb,var(--color-background)_72%,transparent)] ${
      isYearlyPlanBoard
        ? 'border-[color:color-mix(in_srgb,var(--color-accent)_26%,var(--color-border))] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-surface)_90%,var(--color-accent)_10%),var(--color-surface))]'
        : 'border-[var(--color-border)] bg-[linear-gradient(180deg,color-mix(in_srgb,var(--color-surface)_94%,transparent),var(--color-surface))]'
    }`}>
      <div className={`grid ${useCompactLayout ? 'gap-4' : 'gap-6'} ${useCompactLayout ? 'xl:grid-cols-1' : 'xl:grid-cols-[minmax(0,1fr)_minmax(360px,0.95fr)]'} xl:items-start`}>
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
              {copy.brand}
            </div>
            <span className={`${metaPillClassName} ${isYearlyPlanBoard ? 'border-[color:color-mix(in_srgb,var(--color-accent)_28%,var(--color-border))] text-[var(--color-accent)]' : ''}`}>
              {datasetGroupLabel}
            </span>
            <span className={metaPillClassName}>{dataset.dataset_id || copy.defaultDatasetId}</span>
          </div>
          <h1 className={`mt-2 font-serif text-[var(--color-text)] ${useCompactLayout ? 'text-2xl md:text-3xl' : 'text-3xl md:text-4xl'}`}>
            {dataset.name || copy.datasetFallback}
          </h1>
          <p className={`${useCompactLayout ? 'mt-1.5 text-xs leading-5' : 'mt-3 text-sm leading-6'} max-w-3xl text-[var(--color-muted)]`}>
            {useCompactLayout ? compactDescription : dataset.description}
          </p>
          <div className={`${useCompactLayout ? 'mt-3' : 'mt-5'} flex flex-wrap gap-2`}>
            <span className={metaPillClassName}>{dataset.unit || copy.defaultUnit}</span>
            <span className={metaPillClassName}>{dataset.frequency || copy.defaultFrequency}</span>
            {!useCompactLayout ? <span className={metaPillClassName}>{status.last_success_at || copy.notSynced}</span> : null}
          </div>
        </div>
        <div className={`grid gap-3 rounded-xl border p-4 ${
          isYearlyPlanBoard
            ? 'border-[color:color-mix(in_srgb,var(--color-accent)_22%,var(--color-border))] bg-[color:color-mix(in_srgb,var(--color-panel)_88%,var(--color-accent)_12%)]'
            : 'border-[var(--color-border)] bg-[var(--color-panel)]'
        }`}>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="text-[11px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
              {copy.controlsTitle}
            </div>
            <span className={`rounded-full border px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] ${
              isYearlyPlanBoard
                ? 'border-[color:color-mix(in_srgb,var(--color-accent)_28%,var(--color-border))] bg-[color:color-mix(in_srgb,var(--color-surface)_88%,var(--color-accent)_12%)] text-[var(--color-accent)]'
                : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-muted)]'
            }`}>
              {dataset.dataset_id || copy.defaultDatasetId}
            </span>
          </div>
          <div
            data-testid="fingrid-header-actions"
            className={`${useCompactLayout ? 'grid grid-cols-2' : 'flex flex-wrap items-center justify-start xl:justify-end'} gap-2 border-b border-[var(--color-border)] pb-3`}
          >
            <a
              href={exportHref || undefined}
              aria-disabled={!exportHref}
              className={`${buttonClassName} ${useCompactLayout ? 'px-3 text-xs' : ''} ${exportHref ? '' : 'pointer-events-none opacity-50'}`}
            >
              {copy.exportCsv}
            </a>
            <a
              href={exportAllHref || undefined}
              aria-disabled={!exportAllHref}
              className={`${buttonClassName} ${useCompactLayout ? 'px-3 text-xs' : ''} ${exportAllHref ? '' : 'pointer-events-none opacity-50'}`}
            >
              {copy.exportAllMarketsCsv}
            </a>
          </div>
          <div
            data-testid="fingrid-header-filters"
            className={`grid gap-2 ${useCompactLayout ? 'grid-cols-1 sm:grid-cols-2' : 'sm:grid-cols-2 xl:grid-cols-4'}`}
          >
            <select
              value={datasetId}
              onChange={(event) => onDatasetChange(event.target.value)}
              aria-label={copy.datasetSelectorLabel}
              className={`${controlClassName} min-w-0`}
            >
              {groupedDatasets.map((group) => (
                <optgroup key={group.key} label={copy.datasetGroups?.[group.key] || group.key}>
                  {group.items.map((item) => (
                    <option key={item.dataset_id} value={item.dataset_id}>
                      {item.name}
                    </option>
                  ))}
                </optgroup>
              ))}
            </select>
            <select
              value={preset}
              onChange={(event) => onPresetChange(event.target.value)}
              className={`${controlClassName} min-w-0`}
            >
              {presetOptions.map((item) => (
                <option key={item} value={item}>
                  {copy.presetLabels[item] || item}
                </option>
              ))}
            </select>
            <select
              value={aggregation}
              onChange={(event) => onAggregationChange(event.target.value)}
              className={`${controlClassName} min-w-0`}
            >
              {aggregationOptions.map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
            <select
              value={tz}
              onChange={(event) => onTimezoneChange(event.target.value)}
              className={`${controlClassName} min-w-0`}
            >
              {['Europe/Helsinki', 'UTC'].map((item) => (
                <option key={item} value={item}>
                  {copy.timezoneLabels[item] || item}
                </option>
              ))}
            </select>
          </div>
          {preset === 'custom' && (
            <div className="grid gap-2 sm:grid-cols-2">
              <label className={`${controlClassName} flex items-center gap-2`}>
                <span className="text-[var(--color-muted)]">{copy.startDate}</span>
                <input
                  type="date"
                  value={customStartDate}
                  onChange={(event) => onCustomStartDateChange(event.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-[var(--color-text)] outline-none"
                />
              </label>
              <label className={`${controlClassName} flex items-center gap-2`}>
                <span className="text-[var(--color-muted)]">{copy.endDate}</span>
                <input
                  type="date"
                  value={customEndDate}
                  onChange={(event) => onCustomEndDateChange(event.target.value)}
                  className="min-w-0 flex-1 bg-transparent text-[var(--color-text)] outline-none"
                />
              </label>
              {validationMessage && (
                <div className="sm:col-span-2 text-sm text-[var(--color-status-error)]">{validationMessage}</div>
              )}
            </div>
          )}
          <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
              {copy.datasetContextTitle}
            </div>
            <div className={`${useCompactLayout ? 'mt-1 text-xs leading-5' : 'mt-2 text-sm leading-6'} text-[var(--color-text)]`}>
              {useCompactLayout ? compactDescription : (dataset.explanation || dataset.description)}
            </div>
            {!useCompactLayout ? (
              <div className="mt-2 text-sm leading-6 text-[var(--color-muted)]">
                {datasetBehaviorNotice}
              </div>
            ) : null}
            {dataset.groupKey === 'yearly_plans' && !useCompactLayout && (
              <div className="mt-2 text-sm leading-6 text-[var(--color-muted)]">
                {copy.yearlyDatasetAutoWindowNotice}
              </div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
