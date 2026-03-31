export default function SummaryStats({ stats, advancedStats, t }) {
  if (!stats || !advancedStats || !t) return null;

  const primaryMetrics = [
    { label: t.peak, val: stats.max, emphasis: true },
    { label: t.floor, val: stats.min, emphasis: false },
    { label: t.mean, val: stats.avg, emphasis: false }
  ];

  const secondaryMetrics = [
    { label: t.negFreq, val: `${advancedStats.neg_ratio}%`, emphasis: true, color: '#0047FF' },
    { label: t.negMean, val: advancedStats.neg_avg !== null ? `$${advancedStats.neg_avg}` : '--' },
    { label: t.posMean, val: advancedStats.pos_avg !== null ? `$${advancedStats.pos_avg}` : '--' },
    { label: t.posDays, val: advancedStats.days_above_300, unit: ' Days' },
    { label: t.floorDays, val: advancedStats.days_below_100, emphasis: true, unit: ` ${t.uniqueDays || 'Days'}` }
  ];

  return (
    <div className="flex flex-col gap-10 font-sans pt-4 h-full">
      {/* Primary Settlement Stats */}
      <div className="flex flex-col gap-8">
        {primaryMetrics.map((m, idx) => (
          <div key={idx} className="flex flex-col border-b border-[var(--color-border)] pb-4">
            <span className="text-[10px] tracking-[0.2em] text-[var(--color-muted)] uppercase font-semibold mb-2">
              {m.label}
            </span>
            <span className={`text-4xl md:text-5xl font-serif tracking-tight ${
              m.emphasis ? 'text-[var(--color-primary)]' : 'text-[var(--color-text)]'
            }`}>
              ${m.val !== undefined && m.val !== null ? m.val : '--'}
            </span>
          </div>
        ))}
      </div>

      {/* Advanced Quantitative Stats */}
      <div className="mt-2 border-t border-[var(--color-border)] pt-8">
        <h3 className="text-[10px] tracking-[0.2em] text-[var(--color-muted)] uppercase font-semibold mb-6 flex items-center justify-between">
          <span>{t.deepDive || 'DEEP DIVE'}</span>
          <span className="bg-black text-white px-2 py-0.5 rounded text-[8px]">PRO</span>
        </h3>
        <div className="grid grid-cols-2 gap-x-4 gap-y-6">
          {secondaryMetrics.map((m, idx) => (
            <div key={idx} className="flex flex-col flex-1">
              <span className="text-[9px] tracking-wider text-[var(--color-muted)] uppercase mb-1">
                {m.label}
              </span>
              <div className="flex items-baseline">
                <span 
                  className={`font-serif tracking-tight ${m.emphasis ? 'text-2xl' : 'text-xl'}`}
                  style={{ color: m.color || 'var(--color-text)' }}
                >
                  {m.val}
                </span>
                {m.unit && <span className="ml-1 text-[10px] text-[var(--color-muted)]">{m.unit}</span>}
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
