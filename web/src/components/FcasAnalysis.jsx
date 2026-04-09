import { useState, useEffect, useMemo } from 'react';
import { motion } from 'framer-motion';
import {
  ResponsiveContainer, BarChart, Bar, LineChart, Line, XAxis, YAxis,
  CartesianGrid, Tooltip, Legend, Cell, AreaChart, Area
} from 'recharts';

const AGGREGATIONS = ['daily', 'weekly', 'monthly'];

// Color palette for 8 FCAS services
const FCAS_COLORS = {
  raise6sec:  '#2563eb',
  raise60sec: '#3b82f6',
  raise5min:  '#60a5fa',
  raisereg:   '#93c5fd',
  lower6sec:  '#dc2626',
  lower60sec: '#ef4444',
  lower5min:  '#f87171',
  lowerreg:   '#fca5a5',
};

export default function FcasAnalysis({ year, region, apiBase, t }) {
  const [aggregation, setAggregation] = useState('monthly');
  const [capacityMw, setCapacityMw] = useState(100);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    fetch(
      `${apiBase}/fcas-analysis?year=${year}&region=${region}&aggregation=${aggregation}&capacity_mw=${capacityMw}`
    )
      .then(r => r.json())
      .then(res => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, aggregation, capacityMw, apiBase]);

  const aggLabels = {
    daily: t.daily || 'Daily',
    weekly: t.weekly || 'Weekly',
    monthly: t.monthly || 'Monthly',
  };

  const fmt = (v) => v !== null && v !== undefined ? `$${Number(v).toFixed(1)}` : '—';
  const fmtK = (v) => v !== null && v !== undefined ? `$${Number(v).toFixed(0)}k` : '—';

  // Chart: stacked bar chart of service breakdown
  const breakdownData = useMemo(() => {
    if (!data?.service_breakdown) return [];
    return data.service_breakdown.map(s => ({
      service: s.service,
      key: s.key,
      avg_price: s.avg_price,
      max_price: s.max_price,
      est_revenue_k: s.est_revenue_k,
    }));
  }, [data]);

  // Time series chart data
  const tsData = useMemo(() => {
    if (!data?.data) return [];
    return data.data.map(row => ({
      period: row.period,
      total_fcas: row.total_fcas_avg || 0,
      raise_total: (row.raise6sec_rrp || 0) + (row.raise60sec_rrp || 0) + (row.raise5min_rrp || 0) + (row.raisereg_rrp || 0),
      lower_total: (row.lower6sec_rrp || 0) + (row.lower60sec_rrp || 0) + (row.lower5min_rrp || 0) + (row.lowerreg_rrp || 0),
    }));
  }, [data]);

  // Hourly distribution
  const hourlyData = useMemo(() => {
    if (!data?.hourly) return [];
    return data.hourly;
  }, [data]);

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      {/* Section Header */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.fcasTitle || 'FCAS Revenue Analysis'}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">{t.fcasSubtitle || 'Frequency Control Ancillary Services — Revenue Stacking'}</p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          FCAS MARKET
        </div>
      </div>

      {/* Controls */}
      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-10">
        {/* Aggregation */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
            {t.aggregation || 'Aggregation'}
          </span>
          <div className="flex gap-2">
            {AGGREGATIONS.map(a => (
              <button
                key={a}
                onClick={() => setAggregation(a)}
                className={`px-4 py-1.5 text-sm font-sans transition-colors rounded-full border ${
                  aggregation === a
                    ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]'
                    : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]'
                }`}
              >
                {aggLabels[a]}
              </button>
            ))}
          </div>
        </div>

        {/* Capacity Input */}
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
            {t.fcasCapacity || 'Battery Capacity (MW)'}
          </span>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={capacityMw}
              onChange={e => {
                const v = parseFloat(e.target.value);
                setCapacityMw(isNaN(v) || v <= 0 ? 100 : v);
              }}
              className="w-24 px-3 py-1.5 text-sm font-mono border border-[var(--color-border)] bg-transparent text-[var(--color-text)] rounded focus:outline-none focus:border-[var(--color-text)]"
              min="1"
              step="10"
            />
            <span className="text-xs text-[var(--color-muted)]">MW</span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg || 'Loading FCAS data...'}
        </div>
      ) : data?.has_fcas_data === false ? (
        <div className="h-48 flex flex-col items-center justify-center text-[var(--color-muted)] font-serif gap-3">
          <div className="text-lg">{t.fcasNoData || 'No FCAS Data Available'}</div>
          <div className="text-sm font-sans max-w-md text-center">
            {data?.message || 'Run scraper with --fcas flag to collect FCAS pricing data.'}
          </div>
          <code className="text-xs mt-2 px-3 py-1 bg-[var(--color-surface)] border border-[var(--color-border)] rounded">
            python aemo_nem_scraper.py --start 2025-01 --end 2025-03 --fcas
          </code>
        </div>
      ) : data?.data?.length > 0 ? (
        <>
          {/* Summary Cards */}
          {data.summary && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-10">
              <SummaryCard
                label={t.fcasTotalAvg || 'Avg Total FCAS Price'}
                value={fmt(data.summary.total_avg_fcas_price)}
                sub="/MWh"
              />
              <SummaryCard
                label={t.fcasEstRevenue || 'Est. Annual Revenue'}
                value={fmtK(data.summary.total_est_revenue_k)}
                accent
              />
              <SummaryCard
                label={t.fcasDataPoints || 'FCAS Data Points'}
                value={data.summary.data_points_with_fcas?.toLocaleString() || '0'}
              />
              <SummaryCard
                label={t.fcasCapacityLabel || 'Capacity'}
                value={`${data.summary.capacity_mw} MW`}
              />
            </div>
          )}

          {/* Service Breakdown Bar Chart */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
            {/* Revenue by Service */}
            <div>
              <h3 className="text-lg font-serif mb-4">{t.fcasServiceBreakdown || 'Revenue by Service'}</h3>
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={breakdownData} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis
                      type="number"
                      tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="service"
                      tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                      tickLine={false}
                      width={75}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                      }}
                      formatter={(value, name) => {
                        if (name === 'est_revenue_k') return [`$${value}k`, 'Est. Revenue'];
                        return [`$${value}/MWh`, 'Avg Price'];
                      }}
                    />
                    <Bar dataKey="est_revenue_k" name="Est. Revenue ($k)" radius={[0, 4, 4, 0]}>
                      {breakdownData.map((entry) => (
                        <Cell key={entry.key} fill={FCAS_COLORS[entry.key] || '#666'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            {/* Hourly Distribution */}
            <div>
              <h3 className="text-lg font-serif mb-4">{t.fcasHourly || 'Hourly FCAS Price Distribution'}</h3>
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hourlyData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis
                      dataKey="hour"
                      tick={{ fontSize: 10, fill: 'var(--color-muted)' }}
                      tickLine={false}
                    />
                    <YAxis
                      tick={{ fontSize: 11, fill: 'var(--color-muted)' }}
                      tickLine={false}
                      axisLine={false}
                    />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                      }}
                      formatter={(value) => [`$${value}/MWh`, 'Total FCAS']}
                      labelFormatter={(label) => `Hour: ${label}:00`}
                    />
                    <Bar dataKey="avg_total_fcas" name="Avg Total FCAS" fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          {/* Time Series — Raise vs Lower Trend */}
          <div className="mb-12">
            <h3 className="text-lg font-serif mb-4">{t.fcasTrend || 'FCAS Price Trend — Raise vs Lower'}</h3>
            <div className="h-[360px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={tsData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
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
                  />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 12,
                    }}
                    formatter={(value) => [`$${Number(value).toFixed(1)}/MWh`, '']}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area
                    type="monotone" dataKey="raise_total" name={t.fcasRaise || 'Raise Services'}
                    stroke="#2563eb" fill="#2563eb" fillOpacity={0.15} strokeWidth={2}
                  />
                  <Area
                    type="monotone" dataKey="lower_total" name={t.fcasLower || 'Lower Services'}
                    stroke="#dc2626" fill="#dc2626" fillOpacity={0.15} strokeWidth={2}
                  />
                  <Line
                    type="monotone" dataKey="total_fcas" name={t.fcasTotal || 'Total FCAS'}
                    stroke="#6366f1" strokeWidth={2.5} dot={false}
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          {/* Service Breakdown Table */}
          <div className="overflow-x-auto mb-8">
            <h3 className="text-lg font-serif mb-4">{t.fcasDetailTable || 'Service Detail'}</h3>
            <table className="w-full text-sm font-sans border-collapse">
              <thead>
                <tr className="border-b-2 border-[var(--color-text)]">
                  <th className="text-left py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasService || 'Service'}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasAvgPrice || 'Avg Price'}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasMaxPrice || 'Max Price'}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase font-bold">{t.fcasEstRev || 'Est. Revenue'}</th>
                </tr>
              </thead>
              <tbody>
                {data.service_breakdown?.map((svc, i) => (
                  <tr key={i} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                    <td className="py-2.5 px-2 flex items-center gap-2">
                      <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: FCAS_COLORS[svc.key] || '#666' }} />
                      <span className="font-mono text-xs">{svc.service}</span>
                    </td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(svc.avg_price)}/MWh</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(svc.max_price)}/MWh</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">{fmtK(svc.est_revenue_k)}</td>
                  </tr>
                ))}
                {/* Total row */}
                <tr className="border-t-2 border-[var(--color-text)]">
                  <td className="py-3 px-2 font-bold text-xs uppercase tracking-widest">{t.fcasTotalLabel || 'Total'}</td>
                  <td className="text-right py-3 px-2 font-mono text-xs font-bold">
                    {fmt(data.summary?.total_avg_fcas_price)}/MWh
                  </td>
                  <td className="text-right py-3 px-2 font-mono text-xs">—</td>
                  <td className="text-right py-3 px-2 font-mono text-xs font-bold">
                    {fmtK(data.summary?.total_est_revenue_k)}
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData || 'No Data'}
        </div>
      )}
    </motion.div>
  );
}


function SummaryCard({ label, value, sub, accent = false }) {
  return (
    <div className={`border ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)]' : 'border-[var(--color-border)]'} p-4 rounded`}>
      <div className={`text-xs tracking-widest uppercase mb-2 ${accent ? 'text-[var(--color-inverted-text)] opacity-70' : 'text-[var(--color-muted)]'}`}>
        {label}
      </div>
      <div className={`text-xl font-mono font-bold ${accent ? 'text-[var(--color-inverted-text)]' : ''}`}>
        {value}
        {sub && <span className="text-xs font-normal ml-1 opacity-60">{sub}</span>}
      </div>
    </div>
  );
}
