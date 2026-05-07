export default function FinlandBoardHeader({
  copy,
  loading,
  error,
  headerMetrics,
}) {
  const statusTone = error
    ? 'border-[var(--color-error)]/50 text-[var(--color-error)]'
    : loading
      ? 'border-[var(--color-border)] text-[var(--color-muted)]'
      : 'border-[color:color-mix(in_oklab,var(--color-primary)_28%,var(--color-border))] text-[var(--color-primary)]';
  const statusLabel = error
    ? copy.status.error
    : loading
      ? copy.status.loading
      : copy.status.ready;

  return (
    <section className="rounded-lg border border-[color:color-mix(in_oklab,var(--color-border)_82%,var(--color-primary)_18%)] bg-[linear-gradient(180deg,var(--color-surface),color-mix(in_oklab,var(--color-panel)_84%,var(--color-primary)_16%))] p-5 text-[var(--color-text)] shadow-[0_18px_42px_color-mix(in_oklab,var(--color-primary)_10%,transparent)]">
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.8fr)]">
        <div className="grid gap-4">
          <div className={`inline-flex w-fit items-center rounded-full border px-3 py-1 text-xs uppercase tracking-[0.18em] ${statusTone}`}>
            {statusLabel}
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-[0.01em] text-[var(--color-text)]">
              {copy.heroTitle}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-[var(--color-muted)]">
              {copy.heroDescription}
            </p>
          </div>
        </div>

        <div className="grid gap-3 rounded-lg border border-[var(--color-border)] bg-[color:color-mix(in_oklab,var(--color-surface)_94%,var(--color-primary)_6%)] p-4">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
            {copy.signalLabel}
          </div>
          <div className="grid gap-2 text-sm text-[var(--color-text)]">
            <div className="flex items-center justify-between gap-3">
              <span className="text-[var(--color-muted)]">{copy.overviewPayloadLabel}</span>
              <span>{headerMetrics.overviewCount}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[var(--color-muted)]">{copy.readinessPayloadLabel}</span>
              <span>{headerMetrics.readinessCount}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-[var(--color-muted)]">{copy.deliveryLabel}</span>
              <span>{headerMetrics.deliveryValue}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
