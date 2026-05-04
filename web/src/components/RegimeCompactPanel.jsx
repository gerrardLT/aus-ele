import { memo } from 'react';
import { Activity, AlertTriangle, ArrowRightLeft, Gauge, Zap } from 'lucide-react';
import { formatRegimeName, getRegimeAccent, normalizeRegimeCompact } from '../lib/regimeCompact';

const SCORE_KEYS = [
  'negative_price',
  'oversupply',
  'scarcity',
  'reserve_stress',
];

function getRegimeIcon(regime) {
  switch (regime) {
    case 'negative_price':
      return Zap;
    case 'oversupply':
      return ArrowRightLeft;
    case 'scarcity':
      return AlertTriangle;
    default:
      return Gauge;
  }
}

function StatusBadge({ availability, copy }) {
  const isAvailable = availability === 'available';
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[10px] font-semibold tracking-[0.16em] uppercase ${
        isAvailable
          ? 'bg-[rgba(15,159,130,0.1)] text-[#0f9f82]'
          : 'bg-[rgba(185,28,28,0.1)] text-[#b91c1c]'
      }`}
    >
      {isAvailable ? copy.available : copy.unavailable}
    </span>
  );
}

function ScoreStrip({ compact, copy }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      {SCORE_KEYS.map((key) => {
        const score = Number(compact.regime_score_map?.[key] ?? 0);
        return (
          <div key={key} className="rounded-2xl border border-[var(--color-border)] bg-[var(--color-surface)]/65 px-3 py-2.5">
            <div className="mb-2 flex items-center justify-between gap-2">
              <span className="text-[9px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
                {copy.regimeNames?.[key] || key}
              </span>
              <span className="text-[11px] font-semibold text-[var(--color-text)]">{score.toFixed(0)}</span>
            </div>
            <div className="h-1.5 rounded-full bg-black/6">
              <div
                className="h-1.5 rounded-full bg-[var(--color-primary)] transition-[width]"
                style={{ width: `${Math.max(0, Math.min(score, 100))}%` }}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

function RegimeCompactPanel({ compact, t }) {
  const copy = {
    title: t?.title || 'Regime snapshot',
    subtitle: t?.subtitle || 'Current market state summary',
    available: t?.available || 'Available',
    unavailable: t?.unavailable || 'Unavailable',
    primaryLabel: t?.primaryLabel || 'Primary regime',
    scoreLabel: t?.scoreLabel || 'Score',
    confidenceLabel: t?.confidenceLabel || 'Confidence',
    activeLabel: t?.activeLabel || 'Active regimes',
    driversLabel: t?.driversLabel || 'Top drivers',
    transitionsLabel: t?.transitionsLabel || 'Transition hints',
    unavailableMessage:
      t?.unavailableMessage || 'Regime context is not available for the current dataset window.',
    noDrivers: t?.noDrivers || 'No verified driver summary is available.',
    noTransitions: t?.noTransitions || 'No immediate transition hint is available.',
    unknown: t?.unknown || 'Unavailable',
    regimeNames: t?.regimeNames || {},
  };

  const normalized = normalizeRegimeCompact(compact);
  const primary = normalized.primary_regime;
  const accent = getRegimeAccent(primary?.regime);
  const PrimaryIcon = getRegimeIcon(primary?.regime);

  return (
    <section className="mb-6 overflow-hidden rounded-[28px] border border-[var(--color-border)] bg-[linear-gradient(180deg,rgba(255,255,255,0.94),rgba(248,250,252,0.92))] shadow-[0_18px_44px_rgba(15,23,42,0.06)]">
      <div
        className="border-b border-[var(--color-border)] px-5 py-4"
        style={{ background: `linear-gradient(135deg, ${accent.soft}, rgba(255,255,255,0.92))` }}
      >
        <div className="mb-2 flex items-center justify-between gap-3">
          <div className="inline-flex items-center gap-2">
            <span
              className="inline-flex h-9 w-9 items-center justify-center rounded-2xl"
              style={{ backgroundColor: accent.soft, color: accent.color }}
            >
              <PrimaryIcon size={18} />
            </span>
            <div>
              <div className="text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--color-muted)]">
                {copy.title}
              </div>
              <div className="mt-1 text-sm text-[var(--color-muted)]">{copy.subtitle}</div>
            </div>
          </div>
          <StatusBadge availability={normalized.availability_status} copy={copy} />
        </div>

        <div className="mt-4 rounded-[22px] border border-black/6 bg-white/78 px-4 py-4">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
            {copy.primaryLabel}
          </div>
          <div className="mt-2 flex items-end justify-between gap-3">
            <div>
              <div className="text-2xl font-semibold capitalize" style={{ color: accent.color }}>
                {formatRegimeName(primary?.regime, copy)}
              </div>
              <div className="mt-3 flex flex-wrap gap-2">
                <span className="rounded-full bg-black/5 px-2.5 py-1 text-[11px] font-medium text-[var(--color-text)]">
                  {copy.scoreLabel}: {primary?.score?.toFixed?.(1) ?? '--'}
                </span>
                <span className="rounded-full bg-black/5 px-2.5 py-1 text-[11px] font-medium text-[var(--color-text)]">
                  {copy.confidenceLabel}: {primary?.confidence?.toFixed?.(2) ?? '--'}
                </span>
              </div>
            </div>
            <div className="hidden rounded-2xl bg-black/[0.035] p-3 md:block">
              <Activity size={22} color={accent.color} />
            </div>
          </div>
        </div>
      </div>

      <div className="space-y-4 px-5 py-4">
        {normalized.availability_status === 'available' ? <ScoreStrip compact={normalized} copy={copy} /> : null}

        <div className="grid gap-4">
          <div className="rounded-2xl border border-[var(--color-border)] bg-white/70 px-4 py-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
              {copy.activeLabel}
            </div>
            <div className="flex flex-wrap gap-2">
              {normalized.active_regimes.length ? normalized.active_regimes.map((item) => (
                <span
                  key={item.regime}
                  className="rounded-full px-2.5 py-1 text-[11px] font-medium"
                  style={{
                    color: getRegimeAccent(item.regime).color,
                    backgroundColor: getRegimeAccent(item.regime).soft,
                  }}
                >
                  {formatRegimeName(item.regime, copy)}
                </span>
              )) : (
                <span className="text-sm text-[var(--color-muted)]">{copy.unavailableMessage}</span>
              )}
            </div>
          </div>

          <div className="rounded-2xl border border-[var(--color-border)] bg-white/70 px-4 py-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
              {copy.driversLabel}
            </div>
            {normalized.top_drivers.length ? (
              <ul className="space-y-2">
                {normalized.top_drivers.map((item, index) => (
                  <li key={`${item.headline}-${index}`} className="text-sm leading-6 text-[var(--color-text)]">
                    {item.headline}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-sm text-[var(--color-muted)]">{copy.noDrivers}</div>
            )}
          </div>

          <div className="rounded-2xl border border-[var(--color-border)] bg-white/70 px-4 py-3">
            <div className="mb-2 text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
              {copy.transitionsLabel}
            </div>
            {normalized.transition_hints.length ? (
              <ul className="space-y-2">
                {normalized.transition_hints.map((item, index) => (
                  <li key={`${item}-${index}`} className="text-sm leading-6 text-[var(--color-text)]">
                    {item}
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-sm text-[var(--color-muted)]">{copy.noTransitions}</div>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}

export default memo(RegimeCompactPanel);
