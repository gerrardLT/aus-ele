import {
  getForecastText,
  getForecastWarningCopy,
  localizeForecastDriver,
} from '../lib/gridForecast';

function severityTone(severity) {
  if (severity === 'high') {
    return 'border-rose-200 bg-rose-50 text-rose-700';
  }
  if (severity === 'medium') {
    return 'border-amber-200 bg-amber-50 text-amber-700';
  }
  return 'border-emerald-200 bg-emerald-50 text-emerald-700';
}

export default function GridForecastDrivers({ drivers, metadata, t, locale = 'en' }) {
  const copy = getForecastText(locale);
  const warningKeys = metadata?.warnings || [];
  const localizedDrivers = (drivers || []).map((driver) => localizeForecastDriver(driver, locale));
  const sourceLinkText = copy.generic.sourceLink;

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 lg:p-5">
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {t?.keyDrivers || copy.generic.keyDrivers}
          </div>
          <div className="mt-1 text-sm leading-6 text-[var(--color-muted)]">
            {t?.disclaimer || copy.generic.noDrivers}
          </div>
        </div>
        <div className="text-[10px] uppercase tracking-[0.24em] text-[var(--color-muted)]">
          {localizedDrivers.length}
        </div>
      </div>

      {warningKeys.length > 0 && (
        <div className="mt-4 grid gap-2">
          {warningKeys.map((warningKey) => (
            <div
              key={warningKey}
              className="rounded border border-amber-200 bg-amber-50 px-3 py-2 text-xs leading-5 text-amber-900"
            >
              {t?.warnings?.[warningKey] || getForecastWarningCopy(warningKey, locale)}
            </div>
          ))}
        </div>
      )}

      {localizedDrivers.length > 0 ? (
        <div className="mt-4 grid gap-3">
          {localizedDrivers.map((driver, index) => (
            <article
              key={`${driver.driver_type}-${driver.effective_start || index}`}
              className="rounded border border-[var(--color-border)] bg-white/50 p-4"
            >
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-semibold text-[var(--color-text)] break-words">
                    {driver.title}
                  </div>
                  {driver.summary && (
                    <div className="mt-1 text-xs leading-6 text-[var(--color-muted)] break-words">
                      {driver.summary}
                    </div>
                  )}
                </div>
                <div
                  className={`inline-flex items-center rounded-full border px-2.5 py-1 text-[10px] font-bold uppercase tracking-widest ${severityTone(driver.severity)}`}
                >
                  {driver.severityLabel || driver.severity || copy.generic.signal}
                </div>
              </div>

              <div className="mt-4 flex flex-wrap items-center gap-3 text-[11px] leading-5 text-[var(--color-muted)]">
                <span>{driver.sourceLabel || driver.source || copy.generic.source}</span>
                {driver.effective_start && <span>{driver.effective_start}</span>}
                {driver.effective_end && driver.effective_end !== driver.effective_start && <span>{driver.effective_end}</span>}
                {driver.source_url ? (
                  <a
                    href={driver.source_url}
                    target="_blank"
                    rel="noreferrer"
                    className="text-[var(--color-primary)] underline-offset-2 hover:underline"
                  >
                    {sourceLinkText}
                  </a>
                ) : null}
              </div>
            </article>
          ))}
        </div>
      ) : (
        <div className="mt-4 text-sm leading-6 text-[var(--color-muted)]">{copy.generic.noDrivers}</div>
      )}
    </div>
  );
}
