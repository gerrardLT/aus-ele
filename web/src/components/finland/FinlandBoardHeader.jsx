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
      : 'border-emerald-400/35 text-emerald-200';
  const statusLabel = error
    ? copy.status.error
    : loading
      ? copy.status.loading
      : copy.status.ready;

  return (
    <section className="relative overflow-hidden rounded-lg border border-[var(--color-border)] bg-[linear-gradient(135deg,rgba(9,14,28,0.96),rgba(15,32,47,0.92)_42%,rgba(110,43,22,0.78))] p-5 text-[var(--color-text)] shadow-[0_28px_90px_rgba(7,10,18,0.32)]">
      <div
        aria-hidden="true"
        className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_top_right,rgba(251,191,36,0.24),transparent_30%),radial-gradient(circle_at_16%_24%,rgba(56,189,248,0.16),transparent_34%)]"
      />
      <div className="relative grid gap-5 lg:grid-cols-[minmax(0,1.5fr)_minmax(260px,0.8fr)]">
        <div className="grid gap-4">
          <div className={`inline-flex w-fit items-center rounded-full border px-3 py-1 text-xs uppercase tracking-[0.18em] ${statusTone}`}>
            {statusLabel}
          </div>
          <div>
            <h2 className="text-2xl font-semibold tracking-[0.01em] text-white">
              {copy.heroTitle}
            </h2>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-white/70">
              {copy.heroDescription}
            </p>
          </div>
        </div>

        <div className="grid gap-3 rounded-lg border border-white/10 bg-black/20 p-4 backdrop-blur-sm">
          <div className="text-[11px] font-semibold uppercase tracking-[0.16em] text-white/45">
            {copy.signalLabel}
          </div>
          <div className="grid gap-2 text-sm text-white/78">
            <div className="flex items-center justify-between gap-3">
              <span className="text-white/45">{copy.overviewPayloadLabel}</span>
              <span>{headerMetrics.overviewCount}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-white/45">{copy.readinessPayloadLabel}</span>
              <span>{headerMetrics.readinessCount}</span>
            </div>
            <div className="flex items-center justify-between gap-3">
              <span className="text-white/45">{copy.deliveryLabel}</span>
              <span>{headerMetrics.deliveryValue}</span>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
