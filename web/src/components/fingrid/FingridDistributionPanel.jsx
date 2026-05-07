import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

export default function FingridDistributionPanel({ payload, loading, copy }) {
  const monthly = payload?.monthly_average_series || [];
  const yearly = payload?.yearly_average_series || [];
  const hourly = payload?.hourly_profile || [];

  if (loading) {
    return <section className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">{copy.loadingDistributions}</section>;
  }

  const panels = [
    { title: copy.monthlyAverage, data: monthly, key: 'value', fill: '#0369a1', axisKey: 'timestamp' },
    { title: copy.yearlyAverage, data: yearly, key: 'value', fill: '#2563eb', axisKey: 'timestamp' },
    { title: copy.hourlyProfile, data: hourly, key: 'avg_value', fill: '#7c3aed', axisKey: 'hour' },
  ];

  return (
    <section className="grid gap-6">
      {panels.map((panel) => (
        <div key={panel.title} className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6">
          <div className="mb-4 flex items-center justify-between gap-3">
            <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">{panel.title}</div>
            <div className="rounded-full border border-[var(--color-border)] bg-[var(--color-panel)] px-3 py-1 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
              {panel.data.length} pts
            </div>
          </div>
          <div className="h-[220px]">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={panel.data}>
                <CartesianGrid strokeDasharray="3 3" stroke="color-mix(in_srgb,var(--color-border)_80%,transparent)" />
                <XAxis dataKey={panel.axisKey} minTickGap={36} />
                <YAxis />
                <Tooltip />
                <Bar dataKey={panel.key} fill={panel.fill} radius={[6, 6, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      ))}
    </section>
  );
}
