import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function FingridDistributionPanel({ payload, loading, copy }) {
  const monthly = payload?.monthly_average_series || [];
  const yearly = payload?.yearly_average_series || [];
  const hourly = payload?.hourly_profile || [];

  if (loading) {
    return <section className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">{copy.loadingDistributions}</section>;
  }

  return (
    <section className="grid gap-6">
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">{copy.monthlyAverage}</div>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" minTickGap={36} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#0369a1" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">{copy.yearlyAverage}</div>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={yearly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="timestamp" minTickGap={36} />
              <YAxis />
              <Tooltip />
              <Bar dataKey="value" fill="#2563eb" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
        <div className="mb-4 text-sm uppercase tracking-widest text-[var(--color-muted)]">{copy.hourlyProfile}</div>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={hourly}>
              <CartesianGrid strokeDasharray="3 3" />
              <XAxis dataKey="hour" />
              <YAxis />
              <Tooltip />
              <Bar dataKey="avg_value" fill="#7c3aed" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </section>
  );
}
