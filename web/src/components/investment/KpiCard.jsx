/**
 * KpiCard & SummaryBlock — 可复用的 KPI 展示卡片
 * 从 InvestmentAnalysis.jsx 提取
 */

// 主题感知：暗色模式下自动提亮（原深绿/深红仅适配亮色背景，2026-08-10）
const KPI_COLORS = {
  good: 'var(--color-positive)',
  bad: 'var(--color-negative)',
  warn: 'var(--color-status-timeout)',
  brand: 'var(--color-primary)',
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
