import EventBadgeList from './EventBadgeList';
import {
  buildOverlayNotice,
  coverageText,
  describeEventEvidence,
  getEventText,
  summarizeOverlay,
} from '../lib/eventOverlays';

export default function EventContextPanel({ overlay, title, compact = false, locale = 'en' }) {
  const summary = summarizeOverlay(overlay);
  const notice = buildOverlayNotice(overlay, locale);
  const copy = getEventText(locale);
  const evidence = overlay?.events?.slice(0, compact ? 2 : 4) || [];
  const coverageQuality = summary.coverageQuality;

  return (
    <div className="mb-8 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
        <div>
          <div className="text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {title || copy.panelTitle}
          </div>
          <div className="mt-1 text-sm text-[var(--color-muted)]">
            {notice.message}
          </div>
        </div>
        <div className={`rounded px-3 py-1 text-[11px] font-bold uppercase tracking-widest ${
          coverageQuality === 'full'
            ? 'bg-[var(--color-status-success)]/8 text-[var(--color-status-success)]'
            : coverageQuality === 'core_only'
              ? 'bg-[var(--color-status-timeout)]/8 text-[var(--color-status-timeout)]'
              : coverageQuality === 'partial'
                ? 'bg-[var(--color-primary)]/8 text-[var(--color-primary)]'
                : 'bg-[var(--color-surface-hover)] text-[var(--color-muted)]'
        }`}
        >
          {coverageText(coverageQuality, locale)}
        </div>
      </div>

      {summary.topStates.length > 0 && (
        <div className="mt-4">
          <EventBadgeList states={summary.topStates} size={compact ? 'xs' : 'sm'} locale={locale} />
        </div>
      )}

      {evidence.length > 0 && (
        <div className="mt-4 grid gap-3">
          {evidence.map((event) => {
            const rendered = describeEventEvidence(event, locale);

            return (
              <article
                key={event.event_id}
                className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                    {event.source_url ? (
                      <a
                        href={event.source_url}
                        target="_blank"
                        rel="noreferrer"
                        className="transition-colors hover:text-[var(--color-text)] hover:underline"
                      >
                        {rendered.sourceLabel}
                      </a>
                    ) : (
                      rendered.sourceLabel
                    )}
                  </div>
                </div>

                <div className="mt-1 text-sm font-semibold text-[var(--color-text)] break-words">
                  {rendered.title}
                </div>

                {rendered.summary && (
                  <div className="mt-1 text-xs leading-5 text-[var(--color-muted)] whitespace-pre-line break-words">
                    {rendered.summary}
                  </div>
                )}

                {rendered.hasOfficialOriginal && (
                  <details className="mt-3 rounded border border-[var(--color-border)] bg-[var(--color-surface-hover)]/80 p-2">
                    <summary className="cursor-pointer text-[11px] font-semibold text-[var(--color-muted)]">
                      {copy.officialOriginalToggle}
                    </summary>
                    <div className="mt-2 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">
                      {copy.officialOriginalLabel}
                    </div>
                    {rendered.originalTitle && (
                      <div className="mt-1 text-xs font-medium text-[var(--color-text)] break-words">
                        {rendered.originalTitle}
                      </div>
                    )}
                    {rendered.originalSummary && (
                      <div className="mt-1 text-xs leading-5 text-[var(--color-muted)] whitespace-pre-line break-words">
                        {rendered.originalSummary}
                      </div>
                    )}
                  </details>
                )}
              </article>
            );
          })}
        </div>
      )}
    </div>
  );
}
