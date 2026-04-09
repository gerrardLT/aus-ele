import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  ResponsiveContainer, AreaChart, Area, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend
} from 'recharts';

/**
 * Revenue Stacking Chart — Stacked Area showing Arbitrage + FCAS breakdown over time.
 */

const FCAS_KEYS = [
  { key: 'raise6sec_rrp', label: 'Raise 6s', color: '#2563eb' },
  { key: 'raise60sec_rrp', label: 'Raise 60s', color: '#3b82f6' },
  { key: 'raise5min_rrp', label: 'Raise 5m', color: '#60a5fa' },
  { key: 'raisereg_rrp', label: 'Raise Reg', color: '#93c5fd' },
  { key: 'lower6sec_rrp', label: 'Lower 6s', color: '#dc2626' },
  { key: 'lower60sec_rrp', label: 'Lower 60s', color: '#ef4444' },
  { key: 'lower5min_rrp', label: 'Lower 5m', color: '#f87171' },
  { key: 'lowerreg_rrp', label: 'Lower Reg', color: '#fca5a5' },
];

export default function RevenueStacking({ year, region, apiBase, t }) {
  const [arbitrageData, setArbitrageData] = useState(null);
  const [fcasData, setFcasData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    const fetchBoth = Promise.all([
      fetch(`${apiBase}/peak-analysis?year=${year}&region=${region}&aggregation=monthly`)
        .then(r => r.json()),
      fetch(`${apiBase}/fcas-analysis?year=${year}&region=${region}&aggregation=monthly&capacity_mw=100`)
        .then(r => r.json()),
    ]);

    fetchBoth
      .then(([arbRes, fcasRes]) => {
        setArbitrageData(arbRes);
        setFcasData(fcasRes);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, apiBase]);

  // Merge arbitrage spread + FCAS into a single time series
  const chartData = useMemo(() => {
    if (!arbitrageData?.data) return [];

    const arbByPeriod = {};
    for (const row of arbitrageData.data) {
      const period = row.period || row.date;
      arbByPeriod[period] = row.net_spread_4h || row.spread_4h || 0;
    }

    const fcasByPeriod = {};
    if (fcasData?.has_fcas_data && fcasData?.data) {
      for (const row of fcasData.data) {
        fcasByPeriod[row.period] = row;
      }
    }

    // Merge on period keys
    const allPeriods = new Set([
      ...Object.keys(arbByPeriod),
      ...Object.keys(fcasByPeriod),
    ]);

    const merged = [];
    for (const period of [...allPeriods].sort()) {
      const entry = { period, arbitrage: arbByPeriod[period] || 0 };

      const fcasRow = fcasByPeriod[period];
      for (const svc of FCAS_KEYS) {
        entry[svc.key] = fcasRow ? (fcasRow[svc.key] || 0) : 0;
      }
      entry.fcas_total = FCAS_KEYS.reduce((acc, s) => acc + (entry[s.key] || 0), 0);
      entry.total = entry.arbitrage + entry.fcas_total;

      merged.push(entry);
    }

    return merged;
  }, [arbitrageData, fcasData]);

  const hasFcas = fcasData?.has_fcas_data === true;

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.35 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.stackTitle || 'Revenue Stacking'}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">
            {t.stackSubtitle || 'Energy Arbitrage + FCAS Revenue Composition Over Time'}
          </p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          REVENUE STACKING
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">{t.loadingMsg || 'Loading...'}</div>
      ) : chartData.length > 0 ? (
        <>
          {/* Legend / summary */}
          {hasFcas && (
            <div className="flex flex-wrap gap-4 mb-6 text-xs font-mono">
              <span className="flex items-center gap-1.5">
                <span className="w-3 h-3 rounded-sm bg-[#6366f1]" />
                {t.stackArbitrage || 'Arbitrage (Net Spread 4h)'}
              </span>
              {FCAS_KEYS.map(s => (
                <span key={s.key} className="flex items-center gap-1.5">
                  <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: s.color }} />
                  {s.label}
                </span>
              ))}
            </div>
          )}

          <div className="h-[420px]">
            <ResponsiveContainer width="100%" height="100%">
              <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis
                  dataKey="period"
                  tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                  tickLine={false}
                  axisLine={false}
                  tickFormatter={v => `$${v}`}
                />
                <Tooltip
                  contentStyle={{
                    backgroundColor: 'var(--color-surface)',
                    border: '1px solid var(--color-border)',
                    fontSize: 11,
                    maxHeight: 300,
                    overflowY: 'auto',
                  }}
                  formatter={(value, name) => {
                    const label = name === 'arbitrage' ? 'Arbitrage' : FCAS_KEYS.find(s => s.key === name)?.label || name;
                    return [`$${Number(value).toFixed(1)}/MWh`, label];
                  }}
                />

                {/* Arbitrage base */}
                <Area
                  type="monotone" dataKey="arbitrage" stackId="1"
                  stroke="#6366f1" fill="#6366f1" fillOpacity={0.4} strokeWidth={2}
                  name="arbitrage"
                />

                {/* FCAS services stacked on top */}
                {hasFcas && FCAS_KEYS.map(svc => (
                  <Area
                    key={svc.key}
                    type="monotone" dataKey={svc.key} stackId="1"
                    stroke={svc.color} fill={svc.color} fillOpacity={0.5} strokeWidth={1}
                    name={svc.key}
                  />
                ))}
              </AreaChart>
            </ResponsiveContainer>
          </div>

          {!hasFcas && (
            <div className="mt-4 text-center text-sm text-[var(--color-muted)] font-sans">
              {t.stackNoFcas || 'FCAS data not yet available — showing arbitrage only. Run scraper with --fcas flag.'}
            </div>
          )}
        </>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData || 'No Data'}
        </div>
      )}
    </motion.div>
  );
}
