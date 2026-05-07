import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

function FingridSeriesTooltip({ active, payload, label, copy }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload || {};

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-3 text-sm shadow-[0_18px_38px_color-mix(in_srgb,var(--color-background)_78%,transparent)]">
      <div className="font-medium text-[var(--color-text)]">{label}</div>
      <div className="mt-2 grid gap-1.5">
        <div className="text-[var(--color-text)]">{copy.tooltip.average}: {point.avg_value ?? point.value}</div>
        <div className="text-[var(--color-text)]">{copy.tooltip.peak}: {point.peak_value ?? point.value}</div>
        <div className="text-[var(--color-text)]">{copy.tooltip.trough}: {point.trough_value ?? point.value}</div>
        <div className="text-[var(--color-text)]">{copy.tooltip.samples}: {point.sample_count ?? 1}</div>
        <div className="text-[var(--color-muted)]">{copy.tooltip.start}: {point.bucket_start ?? point.timestamp}</div>
        <div className="text-[var(--color-muted)]">{copy.tooltip.end}: {point.bucket_end ?? point.timestamp}</div>
      </div>
    </div>
  );
}

export default function FingridSeriesChart({ payload, loading, error, copy }) {
  if (loading) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        {copy?.loadingChart}
      </section>
    );
  }

  if (error) {
    return <section className="rounded border border-rose-200 bg-rose-50 p-6 text-rose-700">{error}</section>;
  }

  const series = payload?.series || [];
  if (series.length === 0) {
    return (
      <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{copy?.seriesTitle}</div>
        <div className="text-sm text-[var(--color-muted)]">
          {copy?.emptyChart}
        </div>
      </section>
    );
  }

  return (
    <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 shadow-[0_16px_40px_color-mix(in_srgb,var(--color-background)_84%,transparent)]">
      <div className="mb-4 flex items-center justify-between gap-3">
        <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{copy?.seriesTitle}</div>
        <div className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
          {series.length} pts
        </div>
      </div>
      <div className="h-[400px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in_srgb,var(--color-border)_80%,transparent)" />
            <XAxis dataKey="timestamp" minTickGap={48} />
            <YAxis />
            <Tooltip content={<FingridSeriesTooltip copy={copy} />} />
            <Line type="monotone" dataKey="value" stroke="#0f766e" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
