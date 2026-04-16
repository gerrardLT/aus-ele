import { getForecastScoreLabel } from '../lib/gridForecast';

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

function getBandCopy(score, locale = 'en') {
  const labels = locale === 'zh'
    ? { critical: '高压', elevated: '抬升', stable: '平稳' }
    : { critical: 'critical', elevated: 'elevated', stable: 'stable' };
  if (score >= 75) {
    return labels.critical;
  }
  if (score >= 55) {
    return labels.elevated;
  }
  return labels.stable;
}

export default function GridForecastSummaryCards({ summary, t, locale = 'en' }) {
  return (
    <div className="grid grid-cols-12 gap-4">
      {CARD_KEYS.map(([labelKey, valueKey]) => {
        const score = Math.round(Number(summary?.[valueKey] || 0));
        const tone = getTone(score);
        const label = t?.[labelKey] || getForecastScoreLabel(valueKey, locale);

        return (
          <div
            key={valueKey}
            className={`col-span-12 sm:col-span-6 xl:col-span-4 rounded border p-4 transition-colors ${tone.panel}`}
          >
            <div className="flex items-start justify-between gap-3">
              <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
                {label}
              </div>
              <div className={`text-[10px] font-bold uppercase tracking-widest ${tone.text}`}>
                {getBandCopy(score, locale)}
              </div>
            </div>

            <div className="mt-4 flex items-end gap-2">
              <div className="text-4xl font-serif text-[var(--color-text)]">{score}</div>
              <div className="pb-1 text-xs uppercase tracking-widest text-[var(--color-muted)]">/ 100</div>
            </div>

            <div className="mt-4 h-1.5 overflow-hidden rounded-full bg-white/80">
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
