import { motion } from 'framer-motion';

/**
 * WemCapacityAnalysis — WEM 容量市场分析组件
 *
 * Displays capacity credit and capacity price data for the WEM market.
 * Currently shows a graceful "data unavailable" state since the backend
 * endpoint for capacity market data is not yet available.
 */
export default function WemCapacityAnalysis({
  year,
  region = 'WEM',
  lang = 'zh',
}) {
  // Capacity market data is not yet served by the backend.
  // Show a graceful unavailable state with explanation.
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
    >
      <div className="grid grid-cols-1 gap-6 md:grid-cols-3 mb-8">
        <CapacityCard
          label={lang === 'zh' ? '容量价格' : 'Capacity Price'}
          value="—"
          sub={lang === 'zh' ? '待接入' : 'Pending'}
          status="unavailable"
        />
        <CapacityCard
          label={lang === 'zh' ? '容量信用' : 'Capacity Credits'}
          value="—"
          sub={lang === 'zh' ? '待接入' : 'Pending'}
          status="unavailable"
        />
        <CapacityCard
          label={lang === 'zh' ? '储能容量信用估算' : 'Storage Credit Est.'}
          value="—"
          sub={lang === 'zh' ? '待接入' : 'Pending'}
          status="unavailable"
        />
      </div>

      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-center">
        <div className="mb-3">
          <span className="inline-block rounded-full bg-[var(--color-surface-hover)] px-3 py-1 text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {lang === 'zh' ? '数据暂不可用' : 'DATA UNAVAILABLE'}
          </span>
        </div>
        <p className="text-sm text-[var(--color-muted)] max-w-lg mx-auto leading-relaxed">
          {lang === 'zh'
            ? 'WEM 容量市场数据（容量价格、容量信用、储能容量信用估算）尚未接入后端 API。该模块将在数据源就绪后自动启用。'
            : 'WEM capacity market data (capacity price, capacity credits, storage credit estimation) is not yet available from the backend API. This module will activate automatically once the data source is ready.'}
        </p>
        <div className="mt-4 text-xs text-[var(--color-muted)]">
          {lang === 'zh'
            ? `当前年份: ${year || '—'} · 区域: ${region}`
            : `Year: ${year || '—'} · Region: ${region}`}
        </div>
      </div>
    </motion.div>
  );
}

function CapacityCard({ label, value, sub }) {
  return (
    <div className="border border-[var(--color-border)] p-4 rounded-lg">
      <div className="text-xs tracking-widest uppercase mb-2 text-[var(--color-muted)]">
        {label}
      </div>
      <div className="text-2xl font-mono font-bold text-[var(--color-muted)]">
        {value}
      </div>
      {sub && (
        <div className="text-xs text-[var(--color-muted)] mt-1 opacity-60">
          {sub}
        </div>
      )}
    </div>
  );
}
