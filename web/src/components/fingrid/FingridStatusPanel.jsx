export default function FingridStatusPanel({ payload, loading, error }) {
  const status = payload?.status || {};

  if (loading) {
    return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">Loading status...</section>;
  }

  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="text-sm uppercase tracking-widest text-[var(--color-muted)]">Sync Status</div>
      <div className="mt-4 grid gap-3 text-sm text-[var(--color-text)]">
        <div>Status: {status.sync_status || 'idle'}</div>
        <div>Last success: {status.last_success_at || 'n/a'}</div>
        <div>Coverage start: {status.coverage_start_utc || 'n/a'}</div>
        <div>Coverage end: {status.coverage_end_utc || 'n/a'}</div>
        <div>Records: {status.record_count || 0}</div>
        <div>Last error: {status.last_error || error || 'none'}</div>
      </div>
    </section>
  );
}
