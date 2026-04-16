import { useEffect, useMemo, useState } from 'react';
import { motion } from 'framer-motion';
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import EventBadgeList from './EventBadgeList';
import { fetchJson } from '../lib/apiClient';
import { buildPeriodOverlayMap, getEventText } from '../lib/eventOverlays';

const AGGREGATIONS = ['daily', 'weekly', 'monthly', 'yearly'];

function buildTemporalParams(year, region, aggregation, month, quarter, dayType, networkFee) {
  const params = new URLSearchParams({
    year: String(year),
    region,
    aggregation,
  });

  if (networkFee !== null && networkFee !== undefined) {
    params.set('network_fee', String(networkFee));
  }
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

export default function PeakAnalysis({
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
  const [feeOverride, setFeeOverride] = useState(null);
  const [defaultFee, setDefaultFee] = useState(40);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetchJson(`${apiBase}/network-fees`)
      .then((res) => {
        const found = res.fees?.find((item) => item.region === region);
        if (found) {
          setDefaultFee(found.fee);
          setFeeOverride(null);
        }
      })
      .catch(() => {});
  }, [region, apiBase]);

  useEffect(() => {
    if (!year || !region) return;

    setLoading(true);
    const params = buildTemporalParams(year, region, aggregation, month, quarter, dayType, feeOverride);

    fetchJson(`${apiBase}/peak-analysis?${params.toString()}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, aggregation, month, quarter, dayType, feeOverride, apiBase]);

  const chartData = useMemo(() => {
    if (!data?.data) return [];

    return data.data.map((row) => ({
      period: row.period || row.date || '',
      spread_2h: row.spread_2h,
      spread_4h: row.spread_4h,
      spread_6h: row.spread_6h,
      net_spread_2h: row.net_spread_2h,
      net_spread_4h: row.net_spread_4h,
      net_spread_6h: row.net_spread_6h,
    }));
  }, [data]);

  const periodOverlayMap = useMemo(
    () => buildPeriodOverlayMap(eventOverlay?.daily_rollup || [], aggregation),
    [eventOverlay, aggregation],
  );

  const aggLabels = {
    daily: t.daily,
    weekly: t.weekly,
    monthly: t.monthly,
    yearly: t.yearly,
  };

  const fmt = (value) => (
    value !== null && value !== undefined ? `$${Number(value).toFixed(1)}` : '-'
  );

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.title}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">{t.subtitle}</p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          STORAGE ARBITRAGE
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
            {t.networkFee}
          </span>
          <div className="flex items-center gap-3">
            <input
              type="number"
              value={feeOverride ?? defaultFee ?? ''}
              onChange={(e) => {
                const nextValue = parseFloat(e.target.value);
                setFeeOverride(Number.isNaN(nextValue) ? null : nextValue);
              }}
              className="w-24 px-3 py-1.5 text-sm font-mono border border-[var(--color-border)] bg-transparent text-[var(--color-text)] rounded focus:outline-none focus:border-[var(--color-text)]"
              min="0"
              step="1"
            />
            <span className="text-xs text-[var(--color-muted)]">
              {t.networkFeeHint}: ${defaultFee}
            </span>
          </div>
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg || 'Loading...'}
        </div>
      ) : data?.data?.length > 0 ? (
        <>
          {data.summary && (
            <div className="grid grid-cols-2 md:grid-cols-6 gap-4 mb-10">
              <SummaryCard label={`${t.avgSpread} 2h`} value={fmt(data.summary.avg_spread_2h)} />
              <SummaryCard label={`${t.avgSpread} 4h`} value={fmt(data.summary.avg_spread_4h)} />
              <SummaryCard label={`${t.avgSpread} 6h`} value={fmt(data.summary.avg_spread_6h)} />
              <SummaryCard
                label={`${t.avgNetSpread} 4h`}
                value={fmt(data.summary.avg_net_spread_4h)}
                accent
              />
              <SummaryCard label={t.totalDays} value={data.summary.total_days} />
              <SummaryCard label={eventText.eventDaysLabel} value={eventOverlay?.daily_rollup?.length || 0} />
            </div>
          )}

          <div className="mb-12">
            <h3 className="text-lg font-serif mb-4">{t.chartTitle}</h3>
            <div className="h-[360px]">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={chartData} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                  <XAxis dataKey="period" tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} />
                  <YAxis tick={{ fontSize: 11, fill: 'var(--color-muted)' }} tickLine={false} axisLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'var(--color-surface)',
                      border: '1px solid var(--color-border)',
                      fontSize: 12,
                    }}
                    formatter={(value) => [`$${Number(value).toFixed(1)}`, '']}
                  />
                  <Legend wrapperStyle={{ fontSize: 11 }} />
                  <Line type="monotone" dataKey="spread_2h" name={`${t.spreadLine} 2h`} stroke="#2563eb" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="spread_4h" name={`${t.spreadLine} 4h`} stroke="#059669" strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="spread_6h" name={`${t.spreadLine} 6h`} stroke="#d97706" strokeWidth={2} dot={false} />
                  <Line
                    type="monotone"
                    dataKey="net_spread_4h"
                    name={`${t.netSpreadLine} 4h`}
                    stroke="#059669"
                    strokeWidth={1.5}
                    strokeDasharray="5 5"
                    dot={false}
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          </div>

          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans border-collapse">
              <thead>
                <tr className="border-b-2 border-[var(--color-text)]">
                  <th className="text-left py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.period}</th>
                  {aggregation !== 'daily' && (
                    <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.daysCount}</th>
                  )}
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.peak} 1h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.peak} 4h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.trough} 1h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.trough} 4h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase font-bold">{t.spread} 2h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase font-bold">{t.spread} 4h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase font-bold">{t.spread} 6h</th>
                  <th className="text-right py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.netSpread} 4h</th>
                  <th className="text-left py-3 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">Events</th>
                </tr>
              </thead>
              <tbody>
                {data.data.map((row, index) => {
                  const isInsufficient = row.days_count !== undefined && row.days_count <= 1 && row.peak_1h === null;
                  const overlayInfo = periodOverlayMap.get(row.period || row.date);
                  return (
                    <tr
                      key={index}
                      className={`border-b border-[var(--color-border)] hover:bg-[var(--color-surface-hover)] transition-colors ${
                        isInsufficient ? 'opacity-40' : ''
                      }`}
                    >
                      <td className="py-2.5 px-2 font-mono text-xs">
                        {row.period || row.date}
                      </td>
                      {aggregation !== 'daily' && (
                        <td className="text-right py-2.5 px-2 font-mono text-xs text-[var(--color-muted)]">{row.days_count}</td>
                      )}
                      <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(row.peak_1h)}</td>
                      <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(row.peak_4h)}</td>
                      <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(row.trough_1h)}</td>
                      <td className="text-right py-2.5 px-2 font-mono text-xs">{fmt(row.trough_4h)}</td>
                      <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">{fmt(row.spread_2h)}</td>
                      <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">{fmt(row.spread_4h)}</td>
                      <td className="text-right py-2.5 px-2 font-mono text-xs font-bold">{fmt(row.spread_6h)}</td>
                      <td className={`text-right py-2.5 px-2 font-mono text-xs ${
                        row.net_spread_4h !== null && row.net_spread_4h > 0 ? 'text-green-600' : 'text-red-500'
                      }`}
                      >
                        {fmt(row.net_spread_4h)}
                      </td>
                      <td className="py-2.5 px-2">
                        {overlayInfo?.top_states?.length ? (
                          <EventBadgeList states={overlayInfo.top_states} size="xs" locale={lang} />
                        ) : (
                          <span className="text-[10px] text-[var(--color-muted)]">-</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
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

function SummaryCard({ label, value, accent = false }) {
  return (
    <div
      className={`border ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)]' : 'border-[var(--color-border)]'} p-4 rounded`}
    >
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
