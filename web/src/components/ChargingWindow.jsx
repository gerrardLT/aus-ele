import { useState, useEffect, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import EventBadgeList from './EventBadgeList';
import { fetchJson } from '../lib/apiClient';
import { buildOverlayNotice, getEventText } from '../lib/eventOverlays';

/**
 * ChargingWindow - 24-hour Clock Heatmap
 * Shows optimal charge (negative price) and discharge (peak price) hours.
 * Pure SVG radial chart - no external chart library needed.
 */

const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}:00`);

function interpolateColor(value, min, max) {
  if (value <= 0) {
    const ratio = Math.min(1, Math.abs(value) / Math.max(1, Math.abs(min)));
    const green = Math.round(160 + ratio * 95);
    const red = Math.round(30 - ratio * 20);
    return `rgb(${red}, ${green}, ${Math.round(80 - ratio * 30)})`;
  }

  const ratio = Math.min(1, value / Math.max(1, max));
  if (ratio < 0.5) {
    const phase = ratio * 2;
    return `rgb(${Math.round(200 + phase * 55)}, ${Math.round(180 - phase * 80)}, ${Math.round(50 - phase * 30)})`;
  }

  const phase = (ratio - 0.5) * 2;
  return `rgb(${Math.round(230 + phase * 25)}, ${Math.round(80 - phase * 50)}, ${Math.round(30 - phase * 20)})`;
}

export default function ChargingWindow({ year, region, lang = 'en', eventOverlay, apiBase, t }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [selectedHour, setSelectedHour] = useState(null);
  const svgRef = useRef(null);

  useEffect(() => {
    if (!year || !region) return;
    setLoading(true);
    fetchJson(`${apiBase}/hourly-price-profile?year=${year}&region=${region}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, apiBase]);

  const hourlyData = useMemo(() => data?.hourly || [], [data]);

  const stats = useMemo(() => {
    if (!hourlyData.length) return null;
    const prices = hourlyData.map((hour) => hour.avg_price);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);
    const sorted = [...hourlyData].sort((left, right) => left.avg_price - right.avg_price);
    const bestCharge = sorted.slice(0, 4).map((hour) => hour.hour);
    const bestDischarge = sorted.slice(-4).reverse().map((hour) => hour.hour);

    return { minPrice, maxPrice, bestCharge, bestDischarge };
  }, [hourlyData]);

  const eventText = getEventText(lang);
  const overlayNotice = useMemo(() => buildOverlayNotice(eventOverlay, lang), [eventOverlay, lang]);

  const size = 380;
  const cx = size / 2;
  const cy = size / 2;
  const innerR = 60;
  const outerR = 160;
  const labelR = 175;

  const arcPath = (startAngle, endAngle, r1, r2) => {
    const toRad = (angle) => ((angle - 90) * Math.PI) / 180;
    const x1 = cx + r2 * Math.cos(toRad(startAngle));
    const y1 = cy + r2 * Math.sin(toRad(startAngle));
    const x2 = cx + r2 * Math.cos(toRad(endAngle));
    const y2 = cy + r2 * Math.sin(toRad(endAngle));
    const x3 = cx + r1 * Math.cos(toRad(endAngle));
    const y3 = cy + r1 * Math.sin(toRad(endAngle));
    const x4 = cx + r1 * Math.cos(toRad(startAngle));
    const y4 = cy + r1 * Math.sin(toRad(startAngle));
    return `M ${x1} ${y1} A ${r2} ${r2} 0 0 1 ${x2} ${y2} L ${x3} ${y3} A ${r1} ${r1} 0 0 0 ${x4} ${y4} Z`;
  };

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.35 }}
      className="col-span-12 mt-16 pt-12 border-t-2 border-[var(--color-text)]"
    >
      <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-4 mb-10">
        <div>
          <h2 className="text-3xl font-serif font-bold mb-1">{t.cwTitle}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">
            {t.cwSubtitle}
          </p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          {t.cwEyebrow}
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">
          {t.loadingMsg}
        </div>
      ) : hourlyData.length > 0 && stats ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
          <div className="lg:col-span-2 flex justify-center">
            <svg ref={svgRef} viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[500px]" aria-label={t.cwChartAria}>
              {hourlyData.map((hour, index) => {
                const startAngle = index * 15;
                const endAngle = (index + 1) * 15;
                const color = interpolateColor(hour.avg_price, stats.minPrice, stats.maxPrice);
                const isSelected = selectedHour === index;

                return (
                  <g
                    key={index}
                    onMouseEnter={() => setSelectedHour(index)}
                    onMouseLeave={() => setSelectedHour(null)}
                    style={{ cursor: 'pointer' }}
                  >
                    <path
                      d={arcPath(startAngle, endAngle, innerR, outerR)}
                      fill={color}
                      fillOpacity={isSelected ? 1 : 0.75}
                      stroke="var(--color-background)"
                      strokeWidth={1.5}
                    />
                    {hour.neg_pct > 20 ? (
                      <path
                        d={arcPath(startAngle + 1, endAngle - 1, innerR - 8, innerR - 2)}
                        fill="#10b981"
                        fillOpacity={Math.min(1, hour.neg_pct / 50)}
                      />
                    ) : null}
                  </g>
                );
              })}

              {[0, 3, 6, 9, 12, 15, 18, 21].map((hour) => {
                const angle = ((hour * 15) - 90) * Math.PI / 180;
                const x = cx + labelR * Math.cos(angle);
                const y = cy + labelR * Math.sin(angle);
                return (
                  <text
                    key={hour}
                    x={x}
                    y={y}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={11}
                    fill="var(--color-muted)"
                    fontFamily="monospace"
                  >
                    {`${hour.toString().padStart(2, '0')}:00`}
                  </text>
                );
              })}

              <circle cx={cx} cy={cy} r={innerR - 10} fill="var(--color-background)" />
              {selectedHour !== null ? (
                <>
                  <text x={cx} y={cy - 18} textAnchor="middle" fontSize={12} fill="var(--color-muted)" fontFamily="monospace">
                    {HOUR_LABELS[selectedHour]}
                  </text>
                  <text x={cx} y={cy + 4} textAnchor="middle" fontSize={18} fontWeight="bold" fill="var(--color-text)" fontFamily="monospace">
                    ${hourlyData[selectedHour]?.avg_price}
                  </text>
                  <text x={cx} y={cy + 22} textAnchor="middle" fontSize={10} fill="var(--color-muted)">
                    {t.cwAvgUnit}
                  </text>
                  {hourlyData[selectedHour]?.neg_pct > 0 ? (
                    <text x={cx} y={cy + 36} textAnchor="middle" fontSize={10} fill="#10b981">
                      {hourlyData[selectedHour].neg_pct}% {t.cwNegativeSuffix}
                    </text>
                  ) : null}
                </>
              ) : (
                <>
                  <text x={cx} y={cy - 8} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                    {t.cwHover}
                  </text>
                  <text x={cx} y={cy + 8} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                    {t.cwToSee}
                  </text>
                </>
              )}
            </svg>
          </div>

          <div className="lg:col-span-1 space-y-6">
            <div className={`rounded border p-4 ${
              overlayNotice.variant === 'warning'
                ? 'border-amber-500/40 bg-amber-50 text-amber-900'
                : overlayNotice.variant === 'info'
                  ? 'border-sky-500/30 bg-sky-50 text-sky-900'
                  : 'border-[var(--color-border)] bg-[var(--color-surface)] text-[var(--color-text)]'
            }`}>
              <div className="text-xs tracking-widest uppercase font-bold mb-2">
                {eventText.hintTitle}
              </div>
              <div className="text-sm font-medium">
                {overlayNotice.title}
              </div>
              <div className="mt-1 text-xs opacity-80">
                {overlayNotice.message}
              </div>
              {overlayNotice.topStates.length > 0 ? (
                <div className="mt-3">
                  <EventBadgeList states={overlayNotice.topStates.slice(0, 2)} size="xs" locale={lang} />
                </div>
              ) : null}
            </div>

            <div className="border border-green-500/30 bg-green-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-green-600 mb-3">
                {t.cwBestCharge}
              </div>
              <div className="flex flex-wrap gap-2">
                {stats.bestCharge.map((hour) => (
                  <div key={hour} className="px-3 py-1.5 bg-green-100 text-green-800 rounded font-mono text-sm font-bold">
                    {hour.toString().padStart(2, '0')}:00
                  </div>
                ))}
              </div>
              <div className="text-xs text-[var(--color-muted)] mt-2">
                {t.cwChargeHint}
              </div>
            </div>

            <div className="border border-red-500/30 bg-red-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-red-600 mb-3">
                {t.cwBestDischarge}
              </div>
              <div className="flex flex-wrap gap-2">
                {stats.bestDischarge.map((hour) => (
                  <div key={hour} className="px-3 py-1.5 bg-red-100 text-red-800 rounded font-mono text-sm font-bold">
                    {hour.toString().padStart(2, '0')}:00
                  </div>
                ))}
              </div>
              <div className="text-xs text-[var(--color-muted)] mt-2">
                {t.cwDischargeHint}
              </div>
            </div>

            <div className="border border-[var(--color-border)] p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-[var(--color-muted)] mb-3">
                {t.cwNegStats}
              </div>
              <div className="space-y-2 font-mono text-sm">
                {hourlyData
                  .filter((hour) => hour.neg_pct > 5)
                  .sort((left, right) => right.neg_pct - left.neg_pct)
                  .slice(0, 6)
                  .map((hour) => (
                    <div key={hour.hour} className="flex justify-between">
                      <span>{hour.hour.toString().padStart(2, '0')}:00</span>
                      <span className="text-green-600 font-bold">{hour.neg_pct}% {t.cwNegativeSuffix}</span>
                    </div>
                  ))}
              </div>
            </div>

            <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
              <div className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: interpolateColor(-50, -100, 200) }} />
                {t.cwCharge}
              </div>
              <span>{'->'}</span>
              <div
                className="w-12 h-3 rounded-sm"
                style={{
                  background: 'linear-gradient(to right, rgb(10,200,60), rgb(200,200,80), rgb(230,100,20), rgb(255,50,10))',
                }}
              />
              <span>{'->'}</span>
              <div className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: interpolateColor(200, -100, 200) }} />
                {t.cwDischarge}
              </div>
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
