import { getForecastBandCopy, getForecastScoreLabel } from '../lib/gridForecast';

const CARD_KEYS = [
  ['gridStress', 'grid_stress_score'],
  ['priceSpike', 'price_spike_risk_score'],
  ['negativePrice', 'negative_price_risk_score'],
  ['fcasOpportunity', 'fcas_opportunity_score'],
  ['chargeWindow', 'charge_window_score'],
  ['dischargeWindow', 'discharge_window_score'],
];

function getTone(value) {
  if (value >= 75) {
    return {
      panel: 'border-rose-200 bg-rose-50/80',
      bar: 'bg-rose-500',
      text: 'text-rose-700',
    };
  }
  if (value >= 55) {
    return {
      panel: 'border-amber-200 bg-amber-50/80',
      bar: 'bg-amber-500',
      text: 'text-amber-700',
    };
  }
  return {
    panel: 'border-emerald-200 bg-emerald-50/70',
    bar: 'bg-emerald-500',
    text: 'text-emerald-700',
  };
}

export default function GridForecastSummaryCards({ summary, t, locale = 'en' }) {
  return (
    <div className="grid grid-cols-12 auto-rows-min content-start items-start gap-3 self-start">
      {CARD_KEYS.map(([labelKey, valueKey]) => {
        const score = Math.round(Number(summary?.[valueKey] || 0));
        const tone = getTone(score);
        const label = t?.[labelKey] || getForecastScoreLabel(valueKey, locale);

        return (
          <div
            key={valueKey}
            className={`col-span-12 self-start sm:col-span-6 xl:col-span-4 rounded border px-3.5 py-3 transition-colors ${tone.panel}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">
                {label}
              </div>
              <div className={`text-[10px] font-bold uppercase tracking-widest ${tone.text}`}>
                {getForecastBandCopy(score, locale)}
              </div>
            </div>

            <div className="mt-3 flex items-end gap-2">
              <div className="text-[2rem] leading-none font-serif text-[var(--color-text)]">{score}</div>
              <div className="pb-0.5 text-[11px] uppercase tracking-widest text-[var(--color-muted)]">/ 100</div>
            </div>

            <div className="mt-3 h-1.5 overflow-hidden rounded-full bg-white/80">
              <div
                className={`h-full rounded-full ${tone.bar}`}
                style={{ width: `${Math.max(6, Math.min(score, 100))}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}
