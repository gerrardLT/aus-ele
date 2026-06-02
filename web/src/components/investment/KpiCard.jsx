/**
 * KpiCard & SummaryBlock — 可复用的 KPI 展示卡片
 * 从 InvestmentAnalysis.jsx 提取
 */

const KPI_COLORS = {
  good: '#15803d',
  bad: '#b91c1c',
  warn: '#b45309',
  brand: '#0047FF',
};

export function KpiCard({ label, value, sub, tone }) {
  return (
    <div className="rounded-lg border border-[var(--color-border)] p-4">
      <div className="mb-1 text-xs uppercase tracking-wider text-[var(--color-muted)]">{label}</div>
      <div className="text-2xl font-bold font-mono" style={{ color: KPI_COLORS[tone] || 'inherit' }}>{value}</div>
      <div className="mt-1 text-xs text-[var(--color-muted)]">{sub}</div>
    </div>
  );
}

export function SummaryBlock({ label, value }) {
  return (
    <div className="rounded border border-[var(--color-border)] p-4">
      <div className="mb-1 text-xs uppercase tracking-widest text-[var(--color-muted)]">{label}</div>
      <div className="text-xl font-bold font-mono">{value}</div>
    </div>
  );
}

export default KpiCard;
