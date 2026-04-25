import { formatFingridStatusValue } from '../../lib/fingridUi';

export default function FingridStatusPanel({ payload, loading, error, copy, lang }) {
  const status = payload?.status || {};

  if (loading) {
    return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">{copy.loadingStatus}</section>;
  }

  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="text-sm uppercase tracking-widest text-[var(--color-muted)]">{copy.syncStatus}</div>
      <div className="mt-4 grid gap-3 text-sm text-[var(--color-text)]">
        <div>{copy.statusFields.status}: {formatFingridStatusValue(status.sync_status, lang)}</div>
        <div>{copy.statusFields.lastSuccess}: {status.last_success_at || copy.notSynced}</div>
        <div>{copy.statusFields.coverageStart}: {status.coverage_start_utc || copy.none}</div>
        <div>{copy.statusFields.coverageEnd}: {status.coverage_end_utc || copy.none}</div>
        <div>{copy.statusFields.records}: {status.record_count || 0}</div>
        <div>{copy.statusFields.lastError}: {status.last_error || error || copy.none}</div>
      </div>
    </section>
  );
}
