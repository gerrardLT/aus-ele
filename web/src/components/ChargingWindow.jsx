import { useState, useEffect, useMemo, useRef } from 'react';
import { motion } from 'framer-motion';
import EventBadgeList from './EventBadgeList';
import { fetchJson } from '../lib/apiClient';
import { buildOverlayNotice, getEventText } from '../lib/eventOverlays';

/**
 * ChargingWindow — 24-hour Clock Heatmap
 * Shows optimal charge (negative price) and discharge (peak price) hours.
 * Pure SVG radial chart — no external chart library needed.
 */

const HOUR_LABELS = Array.from({ length: 24 }, (_, i) => `${i.toString().padStart(2, '0')}:00`);

function interpolateColor(value, min, max) {
  // neg → deep green, zero → neutral, positive → warm red/orange
  if (value <= 0) {
    // Negative prices: green shades (profitable to charge)
    const t = Math.min(1, Math.abs(value) / Math.max(1, Math.abs(min)));
    const g = Math.round(160 + t * 95);
    const r = Math.round(30 - t * 20);
    return `rgb(${r}, ${g}, ${Math.round(80 - t * 30)})`;
  }
  // Positive prices: warm yellow → red (profitable to discharge)
  const t = Math.min(1, value / Math.max(1, max));
  if (t < 0.5) {
    const p = t * 2;
    return `rgb(${Math.round(200 + p * 55)}, ${Math.round(180 - p * 80)}, ${Math.round(50 - p * 30)})`;
  }
  const p = (t - 0.5) * 2;
  return `rgb(${Math.round(230 + p * 25)}, ${Math.round(80 - p * 50)}, ${Math.round(30 - p * 20)})`;
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
      .then(res => {
        setData(res);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [year, region, apiBase]);

  const hourlyData = useMemo(() => data?.hourly || [], [data]);

  const stats = useMemo(() => {
    if (!hourlyData.length) return null;
    const prices = hourlyData.map(h => h.avg_price);
    const minPrice = Math.min(...prices);
    const maxPrice = Math.max(...prices);

    // Best charge / discharge windows
    const sorted = [...hourlyData].sort((a, b) => a.avg_price - b.avg_price);
    const bestCharge = sorted.slice(0, 4).map(h => h.hour);
    const bestDischarge = sorted.slice(-4).reverse().map(h => h.hour);

    return { minPrice, maxPrice, bestCharge, bestDischarge };
  }, [hourlyData]);

  const eventText = getEventText(lang);
  const overlayNotice = useMemo(() => buildOverlayNotice(eventOverlay, lang), [eventOverlay, lang]);

  // SVG clock heatmap geometry
  const size = 380;
  const cx = size / 2;
  const cy = size / 2;
  const innerR = 60;
  const outerR = 160;
  const labelR = 175;

  const arcPath = (startAngle, endAngle, r1, r2) => {
    const toRad = (a) => ((a - 90) * Math.PI) / 180;
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
          <h2 className="text-3xl font-serif font-bold mb-1">{t.cwTitle || 'Charging Window Radar'}</h2>
          <p className="text-sm text-[var(--color-muted)] font-sans">
            {t.cwSubtitle || '24-hour Price Clock — Optimal Charge & Discharge Windows'}
          </p>
        </div>
        <div className="text-xs text-[var(--color-muted)] tracking-widest uppercase font-bold">
          DUCK CURVE
        </div>
      </div>

      {loading ? (
        <div className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif text-lg">{t.loadingMsg || 'Loading...'}</div>
      ) : hourlyData.length > 0 && stats ? (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-start">
          {/* Clock Heatmap */}
          <div className="lg:col-span-2 flex justify-center">
            <svg ref={svgRef} viewBox={`0 0 ${size} ${size}`} className="w-full max-w-[500px]" aria-label="Price clock heatmap">
              {/* Hour segments */}
              {hourlyData.map((h, i) => {
                const startAngle = i * 15;
                const endAngle = (i + 1) * 15;
                const color = interpolateColor(h.avg_price, stats.minPrice, stats.maxPrice);
                const isSelected = selectedHour === i;

                return (
                  <g key={i}
                    onMouseEnter={() => setSelectedHour(i)}
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
                    {/* Negative price indicator — inner ring glow */}
                    {h.neg_pct > 20 && (
                      <path
                        d={arcPath(startAngle + 1, endAngle - 1, innerR - 8, innerR - 2)}
                        fill="#10b981"
                        fillOpacity={Math.min(1, h.neg_pct / 50)}
                      />
                    )}
                  </g>
                );
              })}

              {/* Hour labels */}
              {[0, 3, 6, 9, 12, 15, 18, 21].map(h => {
                const angle = ((h * 15) - 90) * Math.PI / 180;
                const x = cx + labelR * Math.cos(angle);
                const y = cy + labelR * Math.sin(angle);
                return (
                  <text
                    key={h} x={x} y={y}
                    textAnchor="middle" dominantBaseline="central"
                    fontSize={11} fill="var(--color-muted)" fontFamily="monospace"
                  >
                    {`${h.toString().padStart(2, '0')}:00`}
                  </text>
                );
              })}

              {/* Center text */}
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
                    /MWh avg
                  </text>
                  {hourlyData[selectedHour]?.neg_pct > 0 && (
                    <text x={cx} y={cy + 36} textAnchor="middle" fontSize={10} fill="#10b981">
                      {hourlyData[selectedHour].neg_pct}% neg
                    </text>
                  )}
                </>
              ) : (
                <>
                  <text x={cx} y={cy - 8} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                    {t.cwHover || 'HOVER'}
                  </text>
                  <text x={cx} y={cy + 8} textAnchor="middle" fontSize={11} fill="var(--color-muted)">
                    {t.cwToSee || 'TO SEE'}
                  </text>
                </>
              )}
            </svg>
          </div>

          {/* Right: Insights */}
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
              {overlayNotice.topStates.length > 0 && (
                <div className="mt-3">
                  <EventBadgeList states={overlayNotice.topStates.slice(0, 2)} size="xs" locale={lang} />
                </div>
              )}
            </div>

            {/* Best charge window */}
            <div className="border border-green-500/30 bg-green-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-green-600 mb-3">
                ⇣ {t.cwBestCharge || 'Best Charge Window (Lowest Prices)'}
              </div>
              <div className="flex flex-wrap gap-2">
                {stats.bestCharge.map(h => (
                  <div key={h} className="px-3 py-1.5 bg-green-100 text-green-800 rounded font-mono text-sm font-bold">
                    {h.toString().padStart(2, '0')}:00
                  </div>
                ))}
              </div>
              <div className="text-xs text-[var(--color-muted)] mt-2">
                {t.cwChargeHint || 'Solar surplus → negative/low prices → free charging'}
              </div>
            </div>

            {/* Best discharge window */}
            <div className="border border-red-500/30 bg-red-500/5 p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-red-600 mb-3">
                ⇡ {t.cwBestDischarge || 'Best Discharge Window (Highest Prices)'}
              </div>
              <div className="flex flex-wrap gap-2">
                {stats.bestDischarge.map(h => (
                  <div key={h} className="px-3 py-1.5 bg-red-100 text-red-800 rounded font-mono text-sm font-bold">
                    {h.toString().padStart(2, '0')}:00
                  </div>
                ))}
              </div>
              <div className="text-xs text-[var(--color-muted)] mt-2">
                {t.cwDischargeHint || 'Evening peak → price surge → maximum revenue'}
              </div>
            </div>

            {/* Negative price stats */}
            <div className="border border-[var(--color-border)] p-4 rounded">
              <div className="text-xs tracking-widest uppercase font-bold text-[var(--color-muted)] mb-3">
                {t.cwNegStats || 'Negative Price Stats'}
              </div>
              <div className="space-y-2 font-mono text-sm">
                {hourlyData.filter(h => h.neg_pct > 5).sort((a, b) => b.neg_pct - a.neg_pct).slice(0, 6).map(h => (
                  <div key={h.hour} className="flex justify-between">
                    <span>{h.hour.toString().padStart(2, '0')}:00</span>
                    <span className="text-green-600 font-bold">{h.neg_pct}% neg</span>
                  </div>
                ))}
              </div>
            </div>

            {/* Color legend */}
            <div className="flex items-center gap-2 text-xs text-[var(--color-muted)]">
              <div className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: interpolateColor(-50, -100, 200) }} />
                {t.cwCharge || 'Charge'}
              </div>
              <span>←</span>
              <div className="w-12 h-3 rounded-sm" style={{
                background: 'linear-gradient(to right, rgb(10,200,60), rgb(200,200,80), rgb(230,100,20), rgb(255,50,10))'
              }} />
              <span>→</span>
              <div className="flex items-center gap-1">
                <span className="w-3 h-3 rounded-sm" style={{ backgroundColor: interpolateColor(200, -100, 200) }} />
                {t.cwDischarge || 'Discharge'}
              </div>
            </div>
          </div>
        </div>
      ) : (
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] font-serif">
          {t.noData || (lang === 'zh' ? '暂无数据' : 'No Data')}
        </div>
      )}
    </motion.div>
  );
}
