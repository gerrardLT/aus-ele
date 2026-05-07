import { formatFingridStatusValue } from '../../lib/fingridUi';

export default function FingridStatusPanel({ payload, loading, error, copy, lang, compact = false }) {
  const status = payload?.status || {};
  const rows = [
    { label: copy.statusFields.status, value: formatFingridStatusValue(status.sync_status, lang) },
    { label: copy.statusFields.lastSuccess, value: status.last_success_at || copy.notSynced },
    { label: copy.statusFields.coverageStart, value: status.coverage_start_utc || copy.none },
    { label: copy.statusFields.coverageEnd, value: status.coverage_end_utc || copy.none },
    { label: copy.statusFields.records, value: status.record_count || 0 },
    { label: copy.statusFields.lastError, value: status.last_error || error || copy.none },
  ];

  if (loading) {
    return <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">{copy.loadingStatus}</section>;
  }

  if (compact) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div className="mb-3 flex items-center justify-between gap-3">
          <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{copy.syncStatus}</div>
          <div className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
            {rows.length} cards
          </div>
        </div>
        <div className="grid gap-2 md:grid-cols-2 xl:grid-cols-3">
          {rows.map((row) => (
            <div key={row.label} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-2.5">
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">{row.label}</div>
              <div className="mt-1 break-words text-xs leading-5 text-[var(--color-text)]">{row.value}</div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{copy.syncStatus}</div>
      <div className="mt-4 grid gap-3">
        {rows.map((row) => (
          <div key={row.label} className="rounded-lg border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">{row.label}</div>
            <div className="mt-1 break-words text-sm leading-6 text-[var(--color-text)]">{row.value}</div>
          </div>
        ))}
      </div>
    </section>
  );
}
