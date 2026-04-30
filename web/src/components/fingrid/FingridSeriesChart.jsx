import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

function FingridSeriesTooltip({ active, payload, label, copy }) {
  if (!active || !payload?.length) {
    return null;
  }

  const point = payload[0]?.payload || {};

  return (
    <div className="rounded border border-[var(--color-border)] bg-white p-3 text-sm shadow-lg">
      <div className="font-medium text-[var(--color-text)]">{label}</div>
      <div className="mt-2 text-[var(--color-text)]">{copy.tooltip.average}: {point.avg_value ?? point.value}</div>
      <div className="text-[var(--color-text)]">{copy.tooltip.peak}: {point.peak_value ?? point.value}</div>
      <div className="text-[var(--color-text)]">{copy.tooltip.trough}: {point.trough_value ?? point.value}</div>
      <div className="text-[var(--color-text)]">{copy.tooltip.samples}: {point.sample_count ?? 1}</div>
      <div className="text-[var(--color-muted)]">{copy.tooltip.start}: {point.bucket_start ?? point.timestamp}</div>
      <div className="text-[var(--color-muted)]">{copy.tooltip.end}: {point.bucket_end ?? point.timestamp}</div>
    </div>
  );
}

export default function FingridSeriesChart({ payload, loading, error, copy }) {
  if (loading) {
    return (
      <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
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
      <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">{copy?.seriesTitle}</div>
        <div className="text-sm text-[var(--color-muted)]">
          {copy?.emptyChart}
        </div>
      </section>
    );
  }

  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">{copy?.seriesTitle}</div>
      <div className="h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
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
