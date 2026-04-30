import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson } from '../lib/apiClient';

function buildParams(year, region, month, quarter, dayType) {
  const params = new URLSearchParams({
    year: String(year),
    region,
    aggregation: 'daily',
  });

  if (month && month !== 'ALL') {
    params.set('month', month);
  }
  if (quarter && quarter !== 'ALL') {
    params.set('quarter', quarter);
  }
  if (dayType && dayType !== 'ALL') {
    params.set('day_type', dayType);
  }

  return params;
}

export default function CycleCost({
  year,
  region,
  lang = 'en',
  month,
  quarter,
  dayType,
  apiBase,
  t,
}) {
  const [dailyData, setDailyData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [degradationCost, setDegradationCost] = useState(40);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    const params = buildParams(year, region, month, quarter, dayType);
    fetchJson(`${apiBase}/peak-analysis?${params.toString()}`)
      .then((res) => {
        setDailyData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, month, quarter, dayType, apiBase]);

  const analysis = useMemo(() => {
    const rows = dailyData?.data || [];
    if (!rows.length) {
      return {
        histogram: [],
        metrics: null,
        metricKey: 'net_spread_4h',
        legacyFallback: false,
      };
    }

    const netSpreads = rows
      .map((row) => row.net_spread_4h)
      .filter((value) => value !== null && value !== undefined);

    const spreadKey = netSpreads.length > 0 ? 'net_spread_4h' : 'spread_4h';
    const spreads = rows
      .map((row) => row[spreadKey])
      .filter((value) => value !== null && value !== undefined);

    if (!spreads.length) {
      return {
        histogram: [],
        metrics: null,
        metricKey: spreadKey,
        legacyFallback: spreadKey !== 'net_spread_4h',
      };
    }

    const bucketSize = 25;
    const bucketMap = {};
    for (const spread of spreads) {
      const bucket = Math.floor(spread / bucketSize) * bucketSize;
      bucketMap[bucket] = (bucketMap[bucket] || 0) + 1;
    }

    const histogram = Object.entries(bucketMap)
      .map(([bucket, count]) => ({
        range: `$${bucket}`,
        rangeNum: Number(bucket),
        count,
      }))
      .sort((a, b) => a.rangeNum - b.rangeNum);

    const totalDays = spreads.length;
    const profitableDays = spreads.filter((spread) => spread > degradationCost).length;
    const avgSpread = spreads.reduce((sum, value) => sum + value, 0) / totalDays;
    const maxSpread = Math.max(...spreads);

    return {
      histogram,
      metrics: {
        totalDays,
        profitableDays,
        unprofitableDays: totalDays - profitableDays,
        profitableRatio: totalDays > 0 ? (profitableDays / totalDays) * 100 : 0,
        avgSpread,
        maxSpread,
      },
      metricKey: spreadKey,
      legacyFallback: spreadKey !== 'net_spread_4h',
    };
  }, [dailyData, degradationCost]);

  const { histogram, metrics, legacyFallback } = analysis;

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
          <h2 className="text-3xl font-serif font-bold mb-1">{t.ccTitle}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">
            {t.ccSubtitle}
          </p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          {t.ccEyebrow}
        </div>
      </div>

      {legacyFallback && (
        <div className="mb-8 rounded border border-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
          {t.ccLegacyFallback}
        </div>
      )}

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg}
        </div>
      ) : histogram.length > 0 && metrics ? (
        <div className="grid grid-cols-1 lg:grid-cols-4 gap-8">
          <div className="space-y-6">
            <div className="flex flex-col gap-2">
              <label className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
                {t.ccDegCost}
              </label>
              <div className="flex items-center gap-2">
                <span className="font-mono text-lg font-bold">${degradationCost}</span>
                <span className="text-xs text-[var(--color-muted)]">{t.ccUnitPerMwh}</span>
              </div>
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                value={degradationCost}
                onChange={(e) => setDegradationCost(Number(e.target.value))}
                className="w-full accent-[var(--color-text)] h-1.5 bg-[var(--color-border)] rounded-full appearance-none cursor-pointer"
              />
              <div className="flex justify-between text-[10px] text-[var(--color-muted)]">
                <span>{t.ccSliderMin}</span>
                <span>{t.ccSliderMax}</span>
              </div>
            </div>

            <div className="border border-green-500/30 bg-green-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-green-600 mb-2">
                {t.ccProfitable}
              </div>
              <div className="text-3xl font-mono font-bold text-green-600">{metrics.profitableDays}</div>
              <div className="text-xs text-[var(--color-muted)] mt-1">
                {t.ccDays} ({metrics.profitableRatio.toFixed(1)}%)
              </div>
            </div>

            <div className="border border-red-500/30 bg-red-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-red-600 mb-2">
                {t.ccNotWorth}
              </div>
              <div className="text-3xl font-mono font-bold text-red-500">{metrics.unprofitableDays}</div>
              <div className="text-xs text-[var(--color-muted)] mt-1">
                {t.ccDays} ({(100 - metrics.profitableRatio).toFixed(1)}%)
              </div>
            </div>

            <div className="border border-[var(--color-border)] p-4 rounded space-y-2">
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-muted)]">{t.ccAvgSpread}</span>
                <span className="font-mono font-bold">${metrics.avgSpread.toFixed(1)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-muted)]">{t.ccMaxSpread}</span>
                <span className="font-mono font-bold">${metrics.maxSpread.toFixed(1)}</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-[var(--color-muted)]">{t.ccTotalDays}</span>
                <span className="font-mono font-bold">{metrics.totalDays}</span>
              </div>
            </div>
          </div>

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
                      value: t.ccXAxis,
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
                      value: t.ccYAxis,
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
                    formatter={(value) => [`${value} ${t.ccTooltipDays}`, t.ccTooltipFrequency]}
                    labelFormatter={(label) => `${t.ccTooltipSpread}: ${label}/MWh`}
                  />
                  <ReferenceLine
                    x={`$${Math.floor(degradationCost / 25) * 25}`}
                    stroke="#ef4444"
                    strokeWidth={2}
                    strokeDasharray="8 4"
                    label={{
                      value: `-> $${degradationCost} ${t.ccThreshold}`,
                      position: 'top',
                      style: { fontSize: 10, fill: '#ef4444', fontFamily: 'monospace' },
                    }}
                  />
                  <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                    {histogram.map((entry, index) => (
                      <Cell key={index} fill={barColor(entry.rangeNum)} fillOpacity={0.8} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>

            <div className="flex items-center justify-center gap-6 mt-3 text-xs text-[var(--color-muted)] flex-wrap">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-green-500" />
                {t.ccGo}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-yellow-500" />
                {t.ccMarginal}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-red-500" />
                {t.ccHold}
              </span>
              <span className="flex items-center gap-1.5">
                <span className="w-px h-3 border-l-2 border-dashed border-red-500" />
                {t.ccCostLine}
              </span>
            </div>
          </div>
        </div>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData}
        </div>
      )}
    </motion.div>
  );
}
