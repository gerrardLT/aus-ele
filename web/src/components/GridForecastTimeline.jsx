import {
  getForecastDriverLabel,
  getForecastScoreLabel,
  getForecastText,
  getForecastWindowTypeCopy,
} from '../lib/gridForecast';

function getWindowTone(windowType) {
  if (windowType === 'charge') {
    return 'border-emerald-200 bg-emerald-50/70';
  }
  if (windowType === 'discharge') {
    return 'border-amber-200 bg-amber-50/70';
  }
  return 'border-slate-200 bg-slate-50/70';
}

function formatProbability(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return null;
  }
  return `${Math.round(numeric * 100)}%`;
}

export default function GridForecastTimeline({ windows, t, locale = 'en' }) {
  const copy = getForecastText(locale);
  const emptyCopy = t?.empty || copy.generic.noWindows;

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {t?.futureWindows || copy.generic.futureWindows}
        </div>
        <div className="text-[10px] uppercase tracking-[0.24em] text-[var(--color-muted)]">
          {windows?.length || 0}
        </div>
      </div>

      {!windows || windows.length === 0 ? (
        <div className="mt-4 text-sm leading-6 text-[var(--color-muted)]">{emptyCopy}</div>
      ) : (
        <div className="mt-3 grid gap-2.5">
          {windows.map((window) => (
            <article
              key={`${window.window_type}-${window.start_time}-${window.end_time}`}
              className={`rounded border px-3.5 py-3 ${getWindowTone(window.window_type)}`}
            >
              <div className="flex flex-col gap-2.5 lg:flex-row lg:items-start lg:justify-between">
                <div className="space-y-0.5">
                  <div className="text-sm font-semibold text-[var(--color-text)]">
                    {getForecastWindowTypeCopy(window.window_type, locale)}
                  </div>
                  <div className="text-xs leading-5 text-[var(--color-muted)]">
                    {window.start_time}
                    {window.end_time && window.end_time !== window.start_time ? ` -> ${window.end_time}` : ''}
                  </div>
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  {window.confidence && (
                    <span className="inline-flex items-center rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                      {copy.confidence[window.confidence] || window.confidence}
                    </span>
                  )}
                  {Object.entries(window.probabilities || {}).map(([key, value]) => {
                    const formatted = formatProbability(value);
                    if (!formatted) {
                      return null;
                    }
                    return (
                      <span
                        key={key}
                        className="inline-flex items-center rounded-full bg-white/80 px-2.5 py-1 text-[10px] font-medium uppercase tracking-widest text-slate-700"
                      >
                        {formatted}
                      </span>
                    );
                  })}
                </div>
              </div>

              {Object.entries(window.scores || {}).length > 0 && (
                <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
                  {Object.entries(window.scores || {}).slice(0, 4).map(([key, value]) => (
                    <div
                      key={key}
                      className="rounded border border-white/80 bg-white/80 px-2.5 py-2"
                    >
                      <div className="text-[10px] uppercase tracking-[0.16em] text-[var(--color-muted)]">
                        {getForecastScoreLabel(key, locale)}
                      </div>
                      <div className="mt-0.5 text-base font-serif text-[var(--color-text)]">
                        {Math.round(Number(value || 0))}
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {(window.driver_tags || []).length > 0 && (
                <div className="mt-3 flex flex-wrap gap-1.5">
                  {window.driver_tags.slice(0, 5).map((tag) => (
                    <span
                      key={tag}
                      className="inline-flex items-center rounded-full border border-[var(--color-border)] px-2.5 py-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]"
                    >
                      {getForecastDriverLabel(tag, locale)}
                    </span>
                  ))}
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </div>
  );
}
