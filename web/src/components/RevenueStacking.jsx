import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { fetchJson } from '../lib/apiClient';
import { buildPeriodOverlayMap, getEventText, metaForState } from '../lib/eventOverlays';

const FCAS_KEYS = [
  { key: 'raise1sec_rrp', label: 'Raise 1s', color: '#1d4ed8' },
  { key: 'raise6sec_rrp', label: 'Raise 6s', color: '#2563eb' },
  { key: 'raise60sec_rrp', label: 'Raise 60s', color: '#3b82f6' },
  { key: 'raise5min_rrp', label: 'Raise 5m', color: '#60a5fa' },
  { key: 'raisereg_rrp', label: 'Raise Reg', color: '#93c5fd' },
  { key: 'lower1sec_rrp', label: 'Lower 1s', color: '#b91c1c' },
  { key: 'lower6sec_rrp', label: 'Lower 6s', color: '#dc2626' },
  { key: 'lower60sec_rrp', label: 'Lower 60s', color: '#ef4444' },
  { key: 'lower5min_rrp', label: 'Lower 5m', color: '#f87171' },
  { key: 'lowerreg_rrp', label: 'Lower Reg', color: '#fca5a5' },
];

const WEM_KEYS = [
  { key: 'regulation_raise', label: 'Reg Raise', color: '#2563eb' },
  { key: 'contingency_raise', label: 'Cont Raise', color: '#60a5fa' },
  { key: 'rocof', label: 'RoCoF', color: '#7c3aed' },
  { key: 'regulation_lower', label: 'Reg Lower', color: '#dc2626' },
  { key: 'contingency_lower', label: 'Cont Lower', color: '#f87171' },
];

function buildParams(year, region, aggregation, month, quarter, dayType) {
  const params = new URLSearchParams({
    year: String(year),
    region,
    aggregation,
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

function getArbitrageValue(row) {
  if (row?.net_spread_4h !== null && row?.net_spread_4h !== undefined) {
    return row.net_spread_4h;
  }
  if (row?.spread_4h !== null && row?.spread_4h !== undefined) {
    return row.spread_4h;
  }
  return 0;
}

export default function RevenueStacking({
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
  const [arbitrageData, setArbitrageData] = useState(null);
  const [fcasData, setFcasData] = useState(null);
  const [loading, setLoading] = useState(false);
  const currentAggregation = region === 'WEM' ? 'daily' : 'monthly';

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);

    const peakParams = buildParams(year, region, currentAggregation, month, quarter, dayType);
    const fcasParams = buildParams(year, region, currentAggregation, month, quarter, dayType);
    fcasParams.set('capacity_mw', '100');

    Promise.all([
      fetchJson(`${apiBase}/peak-analysis?${peakParams.toString()}`),
      fetchJson(`${apiBase}/fcas-analysis?${fcasParams.toString()}`),
    ])
      .then(([arbRes, fcasRes]) => {
        setArbitrageData(arbRes);
        setFcasData(fcasRes);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, month, quarter, dayType, apiBase, currentAggregation]);

  const isWem = region === 'WEM';
  const serviceKeys = isWem ? WEM_KEYS : FCAS_KEYS;

  const mergeResult = useMemo(() => {
    if (!arbitrageData?.data?.length) {
      return {
        chartData: [],
        overlapDays: 0,
        previewMode: null,
        legacySpreadFallback: false,
      };
    }

    const arbByPeriod = new Map();
    let legacySpreadFallback = false;

    for (const row of arbitrageData.data) {
      const period = row.period || row.date;
      if (!period) continue;
      const arbitrage = getArbitrageValue(row);
      if ((row.net_spread_4h === null || row.net_spread_4h === undefined) && row.spread_4h !== null && row.spread_4h !== undefined) {
        legacySpreadFallback = true;
      }
      arbByPeriod.set(period, arbitrage);
    }

    const fcasByPeriod = new Map();
    if (fcasData?.has_fcas_data && fcasData?.data) {
      for (const row of fcasData.data) {
        fcasByPeriod.set(row.period, row);
      }
    }

    const periods = isWem
      ? [...arbByPeriod.keys()].filter((period) => fcasByPeriod.has(period))
      : Array.from(new Set([...arbByPeriod.keys(), ...fcasByPeriod.keys()]));

    const overlayByPeriod = buildPeriodOverlayMap(eventOverlay?.daily_rollup || [], currentAggregation);
    const chartData = periods
      .sort()
      .map((period) => {
        const entry = {
          period,
          arbitrage: arbByPeriod.get(period) || 0,
        };
        const fcasRow = fcasByPeriod.get(period);

        for (const service of serviceKeys) {
          entry[service.key] = fcasRow ? (fcasRow[service.key] || 0) : 0;
        }

        entry.fcas_total = serviceKeys.reduce((sum, service) => sum + (entry[service.key] || 0), 0);
        entry.total = entry.arbitrage + entry.fcas_total;
        entry.event_labels = (overlayByPeriod.get(period)?.top_states || []).map((state) => metaForState(state.key, lang).label).join(', ');
        return entry;
      });

    return {
      chartData,
      overlapDays: isWem ? chartData.length : chartData.length,
      previewMode: fcasData?.summary?.preview_mode || null,
      legacySpreadFallback,
    };
  }, [arbitrageData, fcasData, isWem, serviceKeys, eventOverlay, currentAggregation, lang]);

  const { chartData, overlapDays, previewMode, legacySpreadFallback } = mergeResult;
  const hasFcas = fcasData?.has_fcas_data === true;
  const isSingleDayPreview = isWem && overlapDays === 1;
  const isMultiDayPreview = isWem && overlapDays > 1;

  const totalSummary = useMemo(() => {
    if (!chartData.length) return null;
    const totalArbitrage = chartData.reduce((sum, row) => sum + (row.arbitrage || 0), 0);
    const totalFcas = chartData.reduce((sum, row) => sum + (row.fcas_total || 0), 0);
    return {
      periods: chartData.length,
      totalArbitrage,
      totalFcas,
      total: totalArbitrage + totalFcas,
    };
  }, [chartData]);

  const renderLegend = () => (
    <div className="flex flex-wrap gap-4 mb-6 text-xs font-mono">
      <span className="flex items-center gap-1.5">
        <span className="w-3 h-3 rounded-sm bg-[#6366f1]" />
        {t.stackArbitrage || 'Arbitrage (Net Spread 4h)'}
      </span>
      {serviceKeys.map((service) => (
        <span key={service.key} className="flex items-center gap-1.5">
          <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: service.color }} />
          {service.label}
        </span>
      ))}
    </div>
  );

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

      {legacySpreadFallback && (
        <div className="mb-6 rounded border border-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
          {lang === 'zh'
            ? '兼容模式：由于缺少 net_spread_4h，当前套利基线暂时使用 spread_4h。'
            : 'Legacy mode: arbitrage base is using spread_4h because net_spread_4h is missing.'}
        </div>
      )}

      {isWem && (
        <div className="mb-6 rounded border border-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="font-semibold uppercase tracking-wide">
            {(lang === 'zh'
              ? (previewMode === 'multi_day_preview' ? '多日预览' : '单日预览')
              : (previewMode || 'single_day_preview'))} | {lang === 'zh' ? '非投资级' : 'not investment-grade'}
          </div>
          <div className="mt-1">{lang === 'zh' ? '仅供预览，请勿用于项目融资。' : 'Preview only. Do not use for project finance.'}</div>
          {fcasData?.summary?.coverage_days !== undefined && (
            <div className="mt-1">coverage_days={fcasData.summary.coverage_days}</div>
          )}
        </div>
      )}

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg || 'Loading...'}
        </div>
      ) : isWem && !hasFcas ? (
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-sm text-[var(--color-muted)] font-sans">
          {fcasData?.message || (lang === 'zh' ? '当前还没有可用的 WEM FCAS 预览数据。' : 'No WEM FCAS preview data available yet.')}
        </div>
      ) : isWem && overlapDays === 0 ? (
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-sm text-[var(--color-muted)] font-sans">
          {t.stackNoOverlap || (lang === 'zh'
            ? 'WEM 的 peak-analysis 与 FCAS 预览日期当前没有重叠。'
            : 'No overlapping peak-analysis and FCAS preview dates were found for WEM.')}
        </div>
      ) : chartData.length > 0 ? (
        <>
          {totalSummary && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
              <SummaryCard label={lang === 'zh' ? '周期数' : 'Periods'} value={totalSummary.periods} />
              <SummaryCard label={lang === 'zh' ? '套利基线' : 'Arbitrage Base'} value={`$${totalSummary.totalArbitrage.toFixed(1)}`} />
              <SummaryCard label={lang === 'zh' ? 'FCAS 层' : 'FCAS Layers'} value={`$${totalSummary.totalFcas.toFixed(1)}`} />
              <SummaryCard label={lang === 'zh' ? '合计' : 'Combined'} value={`$${totalSummary.total.toFixed(1)}`} accent />
              <SummaryCard label={eventText.eventDaysLabel} value={eventOverlay?.daily_rollup?.length || 0} />
            </div>
          )}

          {renderLegend()}

          {isSingleDayPreview ? (
            <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
              <div className="md:col-span-2 h-[360px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                    <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                    <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                    <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                    <Tooltip
                      contentStyle={{
                        backgroundColor: 'var(--color-surface)',
                        border: '1px solid var(--color-border)',
                        fontSize: 11,
                      }}
                      formatter={(value, name) => {
                        const label = name === 'arbitrage'
                          ? 'Arbitrage'
                          : serviceKeys.find((service) => service.key === name)?.label || name;
                        return [`$${Number(value).toFixed(1)}/MWh`, label];
                      }}
                      labelFormatter={(label, payload) => {
                        const eventLabels = payload?.[0]?.payload?.event_labels;
                        return eventLabels ? `${label} | ${eventLabels}` : label;
                      }}
                    />
                    <Legend wrapperStyle={{ fontSize: 11 }} />
                    <Bar dataKey="arbitrage" stackId="stack" fill="#6366f1" name="arbitrage" />
                    {serviceKeys.map((service) => (
                      <Bar key={service.key} dataKey={service.key} stackId="stack" fill={service.color} name={service.key} />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>

              <div className="border border-[var(--color-border)] rounded p-4 space-y-3">
                <div>
                  <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{lang === 'zh' ? '预览模式' : 'Preview Mode'}</div>
                  <div className="text-lg font-mono font-bold">{lang === 'zh' ? (previewMode === 'multi_day_preview' ? '多日预览' : '单日预览') : (previewMode || 'single_day_preview')}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{lang === 'zh' ? '日期' : 'Date'}</div>
                  <div className="text-lg font-mono font-bold">{chartData[0]?.period}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{lang === 'zh' ? '叠加合计' : 'Combined Stack'}</div>
                  <div className="text-lg font-mono font-bold">${chartData[0]?.total?.toFixed(1)}</div>
                </div>
              </div>
            </div>
          ) : isMultiDayPreview ? (
            <div className="h-[420px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 11,
                    }}
                      formatter={(value, name) => {
                        const label = name === 'arbitrage'
                          ? 'Arbitrage'
                          : serviceKeys.find((service) => service.key === name)?.label || name;
                        return [`$${Number(value).toFixed(1)}/MWh`, label];
                      }}
                      labelFormatter={(label, payload) => {
                        const eventLabels = payload?.[0]?.payload?.event_labels;
                        return eventLabels ? `${label} | ${eventLabels}` : label;
                      }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Bar dataKey="arbitrage" stackId="stack" fill="#6366f1" name="arbitrage" />
                  {serviceKeys.map((service) => (
                    <Bar key={service.key} dataKey={service.key} stackId="stack" fill={service.color} name={service.key} />
                  ))}
                </BarChart>
              </ResponsiveContainer>
            </div>
          ) : (
            <div className="h-[420px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} tickFormatter={(value) => `$${value}`} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 11,
                      maxHeight: 300,
                      overflowY: 'auto',
                    }}
                      formatter={(value, name) => {
                        const label = name === 'arbitrage'
                          ? 'Arbitrage'
                          : serviceKeys.find((service) => service.key === name)?.label || name;
                        return [`$${Number(value).toFixed(1)}/MWh`, label];
                      }}
                      labelFormatter={(label, payload) => {
                        const eventLabels = payload?.[0]?.payload?.event_labels;
                        return eventLabels ? `${label} | ${eventLabels}` : label;
                      }}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Area type="monotone" dataKey="arbitrage" stackId="stack" stroke="#6366f1" fill="#6366f1" fillOpacity={0.4} strokeWidth={2} name="arbitrage" />
                  {hasFcas && serviceKeys.map((service) => (
                    <Area
                      key={service.key}
                      type="monotone"
                      dataKey={service.key}
                      stackId="stack"
                      stroke={service.color}
                      fill={service.color}
                      fillOpacity={0.5}
                      strokeWidth={1}
                      name={service.key}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          )}

          {!hasFcas && !isWem && (
            <div className="mt-4 text-center text-sm text-[var(--color-muted)] font-sans">
              {t.stackNoFcas || 'FCAS data not yet available - showing arbitrage only.'}
            </div>
          )}
        </>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData || (lang === 'zh' ? '暂无数据' : 'No Data')}
        </div>
      )}
    </motion.div>
  );
}

function SummaryCard({ label, value, accent = false }) {
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
      </div>
    </div>
  );
}
