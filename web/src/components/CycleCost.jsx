import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip, ReferenceLine, Cell
} from 'recharts';

/**
 * CycleCost — Histogram: Daily Spread Distribution
 * Overlaid with a degradation cost threshold line.
 * "Is this trade worth making?"
 */

export default function CycleCost({ year, region, apiBase, t }) {
  const [dailyData, setDailyData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [degradationCost, setDegradationCost] = useState(40);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    fetch(`${apiBase}/peak-analysis?year=${year}&region=${region}&aggregation=daily`)
      .then(r => r.json())
      .then(res => {
        setDailyData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, apiBase]);

  const { histogram, metrics } = useMemo(() => {
    if (!dailyData?.data) return { histogram: [], metrics: null };

    const spreads = dailyData.data
      .map(d => d.spread_4h)
      .filter(v => v !== null && v !== undefined);

    if (spreads.length === 0) return { histogram: [], metrics: null };

    // Histogram: bucket by $25 ranges for cleaner bars
    const bucketSize = 25;
    const bucketMap = {};
    for (const s of spreads) {
      const bucket = Math.floor(s / bucketSize) * bucketSize;
      bucketMap[bucket] = (bucketMap[bucket] || 0) + 1;
    }

    const hist = Object.entries(bucketMap)
      .map(([k, v]) => ({
        range: `$${k}`,
        rangeNum: Number(k),
        count: v,
      }))
      .sort((a, b) => a.rangeNum - b.rangeNum);

    // Metrics
    const totalDays = spreads.length;
    const profitableDays = spreads.filter(s => s > degradationCost).length;
    const avgSpread = spreads.reduce((a, b) => a + b, 0) / totalDays;
    const maxSpread = Math.max(...spreads);

    return {
      histogram: hist,
      metrics: {
        totalDays,
        profitableDays,
        unprofitableDays: totalDays - profitableDays,
        profitableRatio: ((profitableDays / totalDays) * 100).toFixed(1),
        avgSpread: avgSpread.toFixed(1),
        maxSpread: maxSpread.toFixed(1),
      },
    };
  }, [dailyData, degradationCost]);

  const barColor = (rangeNum) => {
    if (rangeNum >= degradationCost) return '#10b981';
    if (rangeNum >= degradationCost * 0.7) return '#f59e0b';
    return '#ef4444';
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.4 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.ccTitle || 'Cycle Cost vs Profitability'}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">
            {t.ccSubtitle || 'Is each charge-discharge cycle worth the battery wear?'}
          </p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          DEGRADATION
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">{t.loadingMsg || 'Loading...'}</div>
      ) : histogram.length > 0 && metrics ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          {/* Left: Controls + Stats */}
          <div className="space-y-6">
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
                {t.ccDegCost || 'Cycle Degradation Cost'}
              </label>
              <div className="flex items-center gap-2">
                <span className="font-mono text-lg font-bold">${degradationCost}</span>
                <span className="text-xs text-[var(--color-muted)]">/MWh</span>
              </div>
              <input
                type="range" min={5} max={100} step={5}
                value={degradationCost}
                onChange={e => setDegradationCost(Number(e.target.value))}
                className="w-full accent-[var(--color-text)] h-1.5 bg-[var(--color-border)] rounded-full appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-[var(--color-muted)]">
                <span>$5</span>
                <span>$100/MWh</span>
              </div>
            </div>

            <div className="border border-green-500/30 bg-green-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-green-600 mb-2">
                ✓ {t.ccProfitable || 'Worth Cycling'}
              </div>
              <div className="text-3xl font-mono font-bold text-green-600">{metrics.profitableDays}</div>
              <div className="text-xs text-[var(--color-muted)] mt-1">
                {t.ccDays || 'days'} ({metrics.profitableRatio}%)
              </div>
            </div>

            <div className="border border-red-500/30 bg-red-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-red-600 mb-2">
                ✗ {t.ccNotWorth || 'Hold — Not Worth It'}
              </div>
              <div className="text-3xl font-mono font-bold text-red-500">{metrics.unprofitableDays}</div>
              <div className="text-xs text-[var(--color-muted)] mt-1">
                {t.ccDays || 'days'} ({(100 - metrics.profitableRatio).toFixed(1)}%)
              </div>
            </div>

            <div className="border border-[var(--color-border)] p-4 rounded space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-muted)]">{t.ccAvgSpread || 'Avg Spread'}</span>
                <span className="font-mono font-bold">${metrics.avgSpread}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-muted)]">{t.ccMaxSpread || 'Max Spread'}</span>
                <span className="font-mono font-bold">${metrics.maxSpread}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-muted)]">{t.ccTotalDays || 'Total Days'}</span>
                <span className="font-mono font-bold">{metrics.totalDays}</span>
              </div>
            </div>
          </div>

          {/* Histogram Bar Chart */}
          <div className="lg:col-span-3">
            <div style={{ width: '100%', height: 420 }}>
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={histogram} margin={{ top: 10, right: 20, left: 0, bottom: 30 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" vertical={false} />
                  <XAxis
                    dataKey="range"
                    tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                    tickLine={false}
                    interval={1}
                    angle={-45}
                    textAnchor="end"
                    label={{
                      value: t.ccXAxis || 'Daily Spread ($/MWh)',
                      position: 'bottom',
                      offset: 15,
                      style: { fontSize: 11, fill: 'var(--color-muted)' },
                    }}
                  />
                  <YAxis
                    tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                    tickLine={false}
                    axisLine={false}
                    label={{
                      value: 'Days',
                      angle: -90,
                      position: 'insideLeft',
                      style: { fontSize: 11, fill: 'var(--color-muted)' },
                    }}
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 12,
                    }}
                    formatter={(value) => [`${value} days`, 'Frequency']}
                    labelFormatter={(label) => `Spread: ${label}/MWh`}
                  />
                  <ReferenceLine
                    x={`$${Math.floor(degradationCost / 25) * 25}`}
                    stroke="#ef4444"
                    strokeWidth={2}
                    strokeDasharray="8 4"
                    label={{
                      value: `← $${degradationCost} ${t.ccThreshold || 'threshold'}`,
                      position: 'top',
                      style: { fontSize: 10, fill: '#ef4444', fontFamily: 'monospace' },
                    }}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {histogram.map((entry, i) => (
                      <Cell key={i} fill={barColor(entry.rangeNum)} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Legend */}
            <div className="flex items-center justify-center gap-6 mt-3 text-xs text-[var(--color-muted)]">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-green-500" />
                {t.ccGo || 'Profitable — Cycle'}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-yellow-500" />
                {t.ccMarginal || 'Marginal'}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-red-500" />
                {t.ccHold || 'Hold — Not Worth'}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-px h-3 border-l-2 border-dashed border-red-500" />
                {t.ccCostLine || 'Cost Line'}
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData || 'No Data'}
        </div>
      )}
    </motion.div>
  );
}
