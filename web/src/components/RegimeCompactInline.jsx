import { AlertTriangle, ArrowRightLeft, Gauge, Zap } from 'lucide-react';
import { formatRegimeName, getRegimeAccent, normalizeRegimeCompact } from '../lib/regimeCompact';

function getRegimeIcon(regime) {
  switch (regime) {
    case 'negative_price':
      return Zap;
    case 'oversupply':
      return ArrowRightLeft;
    case 'scarcity':
    case 'reserve_stress':
      return AlertTriangle;
    default:
      return Gauge;
  }
}

export default function RegimeCompactInline({ compact, copy, className = '' }) {
  const normalized = normalizeRegimeCompact(compact);
  const primary = normalized.primary_regime;
  const accent = getRegimeAccent(primary?.regime);
  const Icon = getRegimeIcon(primary?.regime);
  const labels = {
    title: copy?.title || 'Regime snapshot',
    available: copy?.available || 'Available',
    unavailable: copy?.unavailable || 'Unavailable',
    primaryLabel: copy?.primaryLabel || 'Primary regime',
    driversLabel: copy?.driversLabel || 'Top drivers',
    activeLabel: copy?.activeLabel || 'Active regimes',
    unavailableMessage: copy?.unavailableMessage || 'Regime context is not available for the current dataset window.',
    unknown: copy?.unknown || 'Unavailable',
    regimeNames: copy?.regimeNames || {},
  };

  const primaryName = formatRegimeName(primary?.regime, labels);
  const availabilityLabel = normalized.availability_status === 'available' ? labels.available : labels.unavailable;
  const driverHeadline = normalized.top_drivers[0]?.headline || labels.unavailableMessage;

  return (
    <section
      className={`rounded-3xl border border-[var(--color-border)] bg-[linear-gradient(135deg,rgba(255,255,255,0.95),${accent.soft})] px-4 py-3 ${className}`.trim()}
    >
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span
              className="inline-flex h-8 w-8 flex-shrink-0 items-center justify-center rounded-2xl"
              style={{ backgroundColor: accent.soft, color: accent.color }}
            >
              <Icon size={16} />
            </span>
            <div className="min-w-0">
              <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
                {labels.title}
              </div>
              <div className="truncate text-base font-semibold" style={{ color: accent.color }}>
                {primaryName}
              </div>
            </div>
          </div>

          <div className="mt-2 flex flex-wrap gap-2">
            <span className="rounded-full bg-black/5 px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em] text-[var(--color-text)]">
              {labels.primaryLabel}
            </span>
            <span className="rounded-full bg-black/5 px-2.5 py-1 text-[10px] font-medium text-[var(--color-text)]">
              {primary?.score?.toFixed?.(0) ?? '--'}
            </span>
            <span
              className="rounded-full px-2.5 py-1 text-[10px] font-semibold uppercase tracking-[0.14em]"
              style={{ color: accent.color, backgroundColor: accent.soft }}
            >
              {availabilityLabel}
            </span>
          </div>
        </div>

        <div className="min-w-[220px] flex-1">
          <div className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
            {labels.driversLabel}
          </div>
          <div className="mt-1 text-sm leading-6 text-[var(--color-text)]">{driverHeadline}</div>
        </div>
      </div>

      {normalized.active_regimes.length ? (
        <div className="mt-3 flex flex-wrap items-center gap-2 border-t border-black/6 pt-3">
          <span className="text-[10px] font-semibold uppercase tracking-[0.16em] text-[var(--color-muted)]">
            {labels.activeLabel}
          </span>
          {normalized.active_regimes.slice(0, 4).map((item) => (
            <span
              key={item.regime}
              className="rounded-full px-2.5 py-1 text-[11px] font-medium"
              style={{
                color: getRegimeAccent(item.regime).color,
                backgroundColor: getRegimeAccent(item.regime).soft,
              }}
            >
              {formatRegimeName(item.regime, labels)}
            </span>
          ))}
        </div>
      ) : null}
    </section>
  );
}
