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
import DataQualityBadge from './DataQualityBadge';
import { getDataGradeCaveat, getPreviewModeLabel } from '../lib/resultMetadata';

const FCAS_KEYS = [
  { key: 'raise1sec_rrp', copyKey: 'raise1sec', color: '#1d4ed8' },
  { key: 'raise6sec_rrp', copyKey: 'raise6sec', color: '#2563eb' },
  { key: 'raise60sec_rrp', copyKey: 'raise60sec', color: '#3b82f6' },
  { key: 'raise5min_rrp', copyKey: 'raise5min', color: '#60a5fa' },
  { key: 'raisereg_rrp', copyKey: 'raiseReg', color: '#93c5fd' },
  { key: 'lower1sec_rrp', copyKey: 'lower1sec', color: '#b91c1c' },
  { key: 'lower6sec_rrp', copyKey: 'lower6sec', color: '#dc2626' },
  { key: 'lower60sec_rrp', copyKey: 'lower60sec', color: '#ef4444' },
  { key: 'lower5min_rrp', copyKey: 'lower5min', color: '#f87171' },
  { key: 'lowerreg_rrp', copyKey: 'lowerReg', color: '#fca5a5' },
];

const WEM_KEYS = [
  { key: 'regulation_raise', copyKey: 'regulationRaise', color: '#2563eb' },
  { key: 'contingency_raise', copyKey: 'contingencyRaise', color: '#60a5fa' },
  { key: 'rocof', copyKey: 'rocof', color: '#7c3aed' },
  { key: 'regulation_lower', copyKey: 'regulationLower', color: '#dc2626' },
  { key: 'contingency_lower', copyKey: 'contingencyLower', color: '#f87171' },
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
  const serviceKeys = useMemo(() => {
    const labelMap = t.serviceLabels || {};
    const base = isWem ? WEM_KEYS : FCAS_KEYS;
    return base.map((service) => ({
      ...service,
      label: labelMap[service.copyKey] || service.key,
    }));
  }, [isWem, t.serviceLabels]);

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
  const previewLabel = getPreviewModeLabel(previewMode, lang);
  const previewCaveat = getDataGradeCaveat('preview', lang);
  const previewNotInvestmentGrade = t.stackPreviewNotInvestmentGrade;
  const sectionMetadata = isWem
    ? {
        data_grade: 'preview',
        unit: 'AUD/MWh',
        warnings: ['preview_only'],
      }
    : {
        data_grade: 'analytical',
        unit: 'AUD/MWh',
      };

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
        {t.stackArbitrage}
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
          <h2 className="text-3xl font-serif font-bold mb-1">{t.stackTitle}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">
            {t.stackSubtitle}
          </p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          {t.stackEyebrow}
        </div>
      </div>

      {legacySpreadFallback && (
        <div className="mb-6 rounded border border-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
          {t.stackLegacyFallback}
        </div>
      )}

      {isWem && (
        <div className="mb-6 rounded border border-amber-500 bg-amber-50 p-4 text-sm text-amber-900">
          <div className="flex flex-wrap items-center gap-3">
            <DataQualityBadge metadata={sectionMetadata} lang={lang} />
            <div className="font-semibold tracking-wide">
              {previewLabel} | {previewNotInvestmentGrade}
            </div>
          </div>
          <div className="mt-2">{previewCaveat}</div>
          {fcasData?.summary?.coverage_days !== undefined && (
            <div className="mt-1">coverage_days={fcasData.summary.coverage_days}</div>
          )}
        </div>
      )}

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg}
        </div>
      ) : isWem && !hasFcas ? (
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-sm text-[var(--color-muted)] font-sans">
          {fcasData?.message || t.stackNoPreviewData}
        </div>
      ) : isWem && overlapDays === 0 ? (
        <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-6 text-sm text-[var(--color-muted)] font-sans">
          {t.stackNoOverlap}
        </div>
      ) : chartData.length > 0 ? (
        <>
          {totalSummary && (
            <div className="grid grid-cols-2 md:grid-cols-5 gap-4 mb-8">
              <SummaryCard label={t.stackSummaryPeriods} value={totalSummary.periods} />
              <SummaryCard label={t.stackSummaryArbitrageBase} value={`$${totalSummary.totalArbitrage.toFixed(1)}`} />
              <SummaryCard label={t.stackSummaryFcasLayers} value={`$${totalSummary.totalFcas.toFixed(1)}`} />
              <SummaryCard label={t.stackSummaryCombined} value={`$${totalSummary.total.toFixed(1)}`} accent />
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
                          ? t.stackTooltipArbitrage
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
                  <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{t.stackPreviewMode}</div>
                  <div className="text-lg font-mono font-bold">{previewLabel}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{t.stackPreviewDate}</div>
                  <div className="text-lg font-mono font-bold">{chartData[0]?.period}</div>
                </div>
                <div>
                  <div className="text-xs uppercase tracking-widest text-[var(--color-muted)]">{t.stackPreviewCombined}</div>
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
                        ? t.stackTooltipArbitrage
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
                        ? t.stackTooltipArbitrage
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
              {t.stackNoFcas}
            </div>
          )}
        </>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData}
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
