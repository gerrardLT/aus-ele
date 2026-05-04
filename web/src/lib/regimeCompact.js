export function normalizeRegimeCompact(payload) {
  if (!payload || typeof payload !== 'object') {
    return {
      availability_status: 'unavailable',
      primary_regime: null,
      active_regimes: [],
      regime_score_map: {},
      top_drivers: [],
      transition_hints: [],
      warnings: ['regime_layer_unavailable'],
    };
  }

  return {
    availability_status: payload.availability_status || 'unavailable',
    primary_regime: payload.primary_regime || null,
    active_regimes: Array.isArray(payload.active_regimes) ? payload.active_regimes : [],
    regime_score_map: payload.regime_score_map && typeof payload.regime_score_map === 'object' ? payload.regime_score_map : {},
    top_drivers: Array.isArray(payload.top_drivers) ? payload.top_drivers : [],
    transition_hints: Array.isArray(payload.transition_hints) ? payload.transition_hints : [],
    warnings: Array.isArray(payload.warnings) ? payload.warnings : [],
  };
}

export function pickFirstAvailableRegimeCompact(...candidates) {
  for (const candidate of candidates) {
    const normalized = normalizeRegimeCompact(candidate);
    if (normalized.availability_status === 'available') {
      return candidate;
    }
  }

  return candidates.find(Boolean) || null;
}

export function getRegimeAccent(regime) {
  switch (regime) {
    case 'negative_price':
      return {
        tone: 'negative',
        color: 'var(--color-primary)',
        soft: 'rgba(87, 141, 255, 0.12)',
      };
    case 'oversupply':
      return {
        tone: 'oversupply',
        color: '#0f9f82',
        soft: 'rgba(15, 159, 130, 0.12)',
      };
    case 'scarcity':
      return {
        tone: 'scarcity',
        color: '#d97706',
        soft: 'rgba(217, 119, 6, 0.12)',
      };
    case 'reserve_stress':
      return {
        tone: 'reserve',
        color: '#b91c1c',
        soft: 'rgba(185, 28, 28, 0.12)',
      };
    case 'congestion':
      return {
        tone: 'congestion',
        color: '#7c3aed',
        soft: 'rgba(124, 58, 237, 0.12)',
      };
    case 'transmission_separation':
      return {
        tone: 'separation',
        color: '#0891b2',
        soft: 'rgba(8, 145, 178, 0.12)',
      };
    default:
      return {
        tone: 'neutral',
        color: 'var(--color-text)',
        soft: 'rgba(15, 23, 42, 0.06)',
      };
  }
}

export function formatRegimeName(regime, copy) {
  if (!regime) {
    return copy?.unknown || 'Unavailable';
  }
  return copy?.regimeNames?.[regime] || regime.replaceAll('_', ' ');
}
