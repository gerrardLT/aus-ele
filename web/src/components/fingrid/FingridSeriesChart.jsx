import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function FingridSeriesChart({ payload, loading, error }) {
  if (loading) {
    return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">Loading chart...</section>;
  }

  if (error) {
    return <section className="rounded border border-rose-200 bg-rose-50 p-6 text-rose-700">{error}</section>;
  }

  const series = payload?.series || [];
  return (
    <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
      <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">Time Series</div>
      <div className="h-[360px]">
        <ResponsiveContainer width="100%" height="100%">
          <LineChart data={series}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="timestamp" minTickGap={48} />
            <YAxis />
            <Tooltip />
            <Line type="monotone" dataKey="value" stroke="#0f766e" strokeWidth={2} dot={false} />
          </LineChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}
