import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson } from '../lib/apiClient';
import { buildPeriodOverlayMap, getEventText, metaForState } from '../lib/eventOverlays';
import DataQualityBadge from './DataQualityBadge';
import { getDataGradeCaveat, getPreviewModeLabel } from '../lib/resultMetadata';

const AGGREGATIONS = ['daily', 'weekly', 'monthly'];

const FCAS_COLORS = {
  raise1sec: '#1d4ed8',
  raise6sec: '#2563eb',
  raise60sec: '#3b82f6',
  raise5min: '#60a5fa',
  raisereg: '#93c5fd',
  lower1sec: '#b91c1c',
  lower6sec: '#dc2626',
  lower60sec: '#ef4444',
  lower5min: '#f87171',
  lowerreg: '#fca5a5',
  regulation_raise: '#2563eb',
  contingency_raise: '#60a5fa',
  rocof: '#7c3aed',
  regulation_lower: '#dc2626',
  contingency_lower: '#f87171',
};

function buildParams(year, region, aggregation, capacityMw, month, quarter, dayType) {
  const params = new URLSearchParams({
    year: String(year),
    region,
    aggregation,
    capacity_mw: String(capacityMw),
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

export default function FcasAnalysis({
  year,
  region,
  lang = 'en',
  month,
  quarter,
  dayType,
  eventOverlay,
  apiBase,
  t,
}) {
  const eventText = getEventText(lang);
  const [aggregation, setAggregation] = useState('monthly');
  const [capacityMw, setCapacityMw] = useState(100);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    const params = buildParams(year, region, aggregation, capacityMw, month, quarter, dayType);
    fetchJson(`${apiBase}/fcas-analysis?${params.toString()}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, aggregation, capacityMw, month, quarter, dayType, apiBase]);

  const aggLabels = {
    daily: t.daily,
    weekly: t.weekly,
    monthly: t.monthly,
  };

  const fmt = (value) => (
    value !== null && value !== undefined ? `$${Number(value).toFixed(1)}` : '-'
  );

  const fmtK = (value) => (
    value !== null && value !== undefined ? `$${Number(value).toFixed(0)}k` : '-'
  );

  const fmtCount = (value) => Number(value ?? 0).toLocaleString(lang === 'zh' ? 'zh-CN' : 'en-US');
  const fmtDecimal = (value, digits = 1) => Number(value ?? 0).toFixed(digits);

  const serviceBreakdown = useMemo(() => data?.service_breakdown || [], [data]);
  const breakdownData = useMemo(
    () => serviceBreakdown.map((service) => ({
      service: service.service,
      key: service.key,
      group: service.group,
      avg_price: service.avg_price,
      max_price: service.max_price,
      est_revenue_k: service.est_revenue_k,
      net_incremental_revenue_k: service.net_incremental_revenue_k,
    })),
    [serviceBreakdown],
  );

  const tsData = useMemo(() => {
    if (!data?.data) return [];

    const raiseKeys = serviceBreakdown
      .filter((service) => service.group === 'raise')
      .map((service) => service.key);
    const lowerKeys = serviceBreakdown
      .filter((service) => service.group === 'lower')
      .map((service) => service.key);
    const overlayByPeriod = buildPeriodOverlayMap(eventOverlay?.daily_rollup || [], aggregation);

    return data.data.map((row) => ({
      period: row.period,
      total_fcas: row.total_fcas_avg || 0,
      raise_total: raiseKeys.reduce((sum, key) => sum + (row[key] || 0), 0),
      lower_total: lowerKeys.reduce((sum, key) => sum + (row[key] || 0), 0),
      event_labels: (overlayByPeriod.get(row.period)?.top_states || [])
        .map((state) => metaForState(state.key, lang).label)
        .join(', '),
    }));
  }, [data, serviceBreakdown, eventOverlay, aggregation, lang]);

  const hourlyData = useMemo(() => data?.hourly || [], [data]);

  const revenueLabel = data?.summary?.revenue_scope === 'loaded_window'
    ? t.fcasEstRevenueWindow
    : t.fcasEstRevenue;

  const isWemPreview = region === 'WEM' && data?.summary?.preview_mode;
  const previewLabel = getPreviewModeLabel(data?.summary?.preview_mode, lang);
  const previewCaveat = getDataGradeCaveat('preview', lang);
  const previewNotInvestmentGrade = t.fcasPreviewNotInvestmentGrade;
  const viabilityPositiveLabel = t.fcasViabilityPositive;
  const viabilityNegativeLabel = t.fcasViabilityNegative;
  const sectionMetadata = region === 'WEM'
    ? {
        data_grade: 'preview',
        unit: 'AUD/MWh',
        warnings: ['preview_only'],
      }
    : {
        data_grade: 'analytical',
        unit: 'AUD/MWh',
      };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.3 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.fcasTitle}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">{t.fcasSubtitle}</p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          {t.fcasEyebrow}
        </div>
      </div>

      <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-6 mb-10">
        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
            {t.aggregation}
          </span>
          <div className="flex gap-2 flex-wrap">
            {AGGREGATIONS.map((value) => (
              <button
                key={value}
                onClick={() => setAggregation(value)}
                className={`px-4 py-1.5 text-sm font-sans transition-colors rounded-full border ${
                  aggregation === value
                    ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]'
                    : 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]'
                }`}
              >
                {aggLabels[value]}
              </button>
            ))}
          </div>
        </div>

        <div className="flex flex-col gap-2">
          <span className="text-xs font-bold tracking-widest text-[var(--color-muted)] uppercase">
            {t.fcasCapacity}
          </span>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={capacityMw}
              onChange={(e) => {
                const nextValue = parseFloat(e.target.value);
                setCapacityMw(Number.isNaN(nextValue) || nextValue <= 0 ? 100 : nextValue);
              }}
              className="w-24 px-3 py-1.5 text-sm font-mono border border-[var(--color-border)] bg-transparent text-[var(--color-text)] rounded focus:outline-none focus:border-[var(--color-text)]"
              min="1"
              step="10"
            />
            <span className="text-xs text-[var(--color-muted)]">{t.fcasCapacityUnit}</span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg}
        </div>
      ) : data?.has_fcas_data === false ? (
        <div className="h-48 flex flex-col items-center justify-center text-[var(--color-muted)] font-serif gap-3">
          <div className="text-lg">{t.fcasNoData}</div>
          <div className="text-sm font-sans max-w-md text-center">
            {data?.message || t.fcasNoDataHelp}
          </div>
        </div>
      ) : data?.data?.length > 0 ? (
        <>
          {data.summary && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-10">
              <SummaryCard label={t.fcasTotalAvg} value={fmt(data.summary.total_avg_fcas_price)} sub="/MWh" />
              <SummaryCard label={revenueLabel} value={fmtK(data.summary.total_est_revenue_k)} accent />
              <SummaryCard label={t.fcasNetIncremental} value={fmtK(data.summary.total_net_incremental_revenue_k)} />
              <SummaryCard label={t.fcasViableServices} value={data.summary.viable_service_count ?? 0} />
              <SummaryCard label={t.fcasDataPoints} value={fmtCount(data.summary.data_points_with_fcas)} />
              <SummaryCard label={t.fcasCapacityLabel} value={`${data.summary.capacity_mw} ${t.fcasCapacityUnit}`} />
            </div>
          )}

          {data.summary?.message && (
            <div className="mb-6 rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3 text-xs text-[var(--color-muted)]">
              {data.summary.message}
              {data.summary.coverage_start && data.summary.coverage_end ? (
                <span> ({data.summary.coverage_start} to {data.summary.coverage_end})</span>
              ) : null}
            </div>
          )}

          {isWemPreview && (
            <div className="mb-8 rounded border border-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
              <div className="mb-1 flex flex-wrap items-center gap-3">
                <DataQualityBadge metadata={sectionMetadata} lang={lang} />
                <div className="font-semibold tracking-wide">
                  {previewLabel} | {previewNotInvestmentGrade}
                </div>
              </div>
              <div>
                {t.fcasCoverageDays}={data.summary.coverage_days}, {t.fcasInvestmentGrade}=
                {String(data.summary.investment_grade)}
              </div>
              <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
                <div>{t.fcasScarcity} {data.summary.scarcity_score ?? 0}</div>
                <div>{t.fcasOpportunity} {data.summary.opportunity_score ?? 0}</div>
                <div>{t.fcasQuality} {data.summary.quality_score ?? 0}</div>
                <div>{data.summary.preview_caveat}</div>
              </div>
              <div className="mt-1">{previewCaveat}</div>
            </div>
          )}

          <div className="grid grid-cols-1 md:grid-cols-2 gap-8 mb-12">
            <div>
              <h3 className="text-lg font-serif mb-4">{t.fcasServiceBreakdown}</h3>
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={breakdownData} layout="vertical" margin={{ top: 5, right: 30, left: 80, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis type="number" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                    <YAxis type="category" dataKey="service" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} width={110} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                      }}
                      formatter={(value, name) => {
                        if (name === 'net_incremental_revenue_k') return [`$${value}k`, t.fcasNetIncremental];
                        if (name === 'est_revenue_k') return [`$${value}k`, t.fcasEstRev];
                        return [`$${value}/MWh`, t.fcasAvgPrice];
                      }}
                    />
                    <Bar dataKey="net_incremental_revenue_k" name={t.fcasNetIncrementalBar} radius={[0, 4, 4, 0]}>
                      {breakdownData.map((entry) => (
                        <Cell key={entry.key} fill={FCAS_COLORS[entry.key] || '#666'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>

            <div>
              <h3 className="text-lg font-serif mb-4">{t.fcasHourly}</h3>
              <div className="h-[320px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hourlyData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="hour" tick={{ fontSize: 10, fill: 'var(--color-muted)' }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 12,
                      }}
                      formatter={(value) => [`$${value}/MWh`, t.fcasTotal]}
                      labelFormatter={(label) => `${t.fcasHourLabel}: ${label}:00`}
                    />
                    <Bar dataKey="avg_total_fcas" name={t.fcasTotalAvg} fill="#6366f1" radius={[4, 4, 0, 0]} />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </div>
          </div>

          <div className="mb-12">
            <h3 className="text-lg font-serif mb-4">{t.fcasTrend}</h3>
            <div className="h-[360px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={tsData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 12,
                    }}
                    formatter={(value) => [`$${Number(value).toFixed(1)}/MWh`, '']}
                    labelFormatter={(label, payload) => {
                      const eventLabels = payload?.[0]?.payload?.event_labels;
                      return eventLabels ? `${label} | ${eventLabels}` : label;
                    }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="raise_total" name={t.fcasRaise} stroke="#2563eb" fill="#2563eb" fillOpacity={0.15} strokeWidth={2} />
                  <Area type="monotone" dataKey="lower_total" name={t.fcasLower} stroke="#dc2626" fill="#dc2626" fillOpacity={0.15} strokeWidth={2} />
                  <Line type="monotone" dataKey="total_fcas" name={t.fcasTotal} stroke="#6366f1" strokeWidth={2.5} dot={false} />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="overflow-x-auto mb-8">
            <h3 className="text-lg font-serif mb-4">{t.fcasDetailTable}</h3>
            <table className="w-full text-sm font-sans border-collapse">
              <thead>
                <tr className="border-b-2 border-[var(--color-text)]">
                  <th className="text-left py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasService}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasAvgPrice}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasMaxPrice}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasOppCost}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasNetIncremental}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasReserved}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.fcasBindings}</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase font-bold">{t.fcasViability}</th>
                </tr>
              </thead>
              <tbody>
                {serviceBreakdown.map((service, index) => (
                  <tr key={index} className="border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors">
                    <td className="py-2.5 px-2 flex items-center gap-2">
                      <span className="inline-block w-3 h-3 rounded-sm" style={{ backgroundColor: FCAS_COLORS[service.key] || '#666' }} />
                      <span className="font-mono text-xs">{service.service}</span>
                    </td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(service.avg_price)}/MWh</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(service.max_price)}/MWh</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">{fmtK(service.opportunity_cost_k)}</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">{fmtK(service.net_incremental_revenue_k)}</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">{fmtDecimal(service.avg_reserved_capacity_mw)}</td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs">
                      {t.fcasBindingSoc} {(service.soc_binding_interval_ratio * 100).toFixed(0)}% / {t.fcasBindingPower} {(service.power_binding_interval_ratio * 100).toFixed(0)}%
                    </td>
                    <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">
                      {service.incremental_revenue_positive ? viabilityPositiveLabel : viabilityNegativeLabel}
                    </td>
                  </tr>
                ))}
                <tr className="border-t-2 border-[var(--color-text)]">
                  <td className="py-3 px-2 font-bold text-xs uppercase tracking-widest">{t.fcasTotalLabel}</td>
                  <td className="text-right py-3 px-2 font-mono text-xs font-bold">{fmt(data.summary?.total_avg_fcas_price)}/MWh</td>
                  <td className="text-right py-3 px-2 font-mono text-xs">-</td>
                  <td className="text-right py-3 px-2 font-mono text-xs">{fmtK(data.summary?.total_opportunity_cost_k)}</td>
                  <td className="text-right py-3 px-2 font-mono text-xs font-bold">{fmtK(data.summary?.total_net_incremental_revenue_k)}</td>
                  <td className="text-right py-3 px-2 font-mono text-xs">-</td>
                  <td className="text-right py-3 px-2 font-mono text-xs">-</td>
                  <td className="text-right py-3 px-2 font-mono text-xs font-bold">{data.summary?.viable_service_count ?? 0}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData}
        </div>
      )}
    </motion.div>
  );
}

function SummaryCard({ label, value, sub, accent = false }) {
  return (
    <div className={`border ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)]' : 'border-[var(--color-border)]'} p-4 rounded`}>
      <div className={`text-xs tracking-widest uppercase mb-2 ${
        accent ? 'text-[var(--color-inverted-text)] opacity-70' : 'text-[var(--color-muted)]'
      }`}
      >
        {label}
      </div>
      <div className={`text-xl font-mono font-bold ${accent ? 'text-[var(--color-inverted-text)]' : ''}`}>
        {value}
        {sub && <span className="text-xs font-normal ml-1 opacity-60">{sub}</span>}
      </div>
    </div>
  );
}
