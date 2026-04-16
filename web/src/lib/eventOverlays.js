const EVENT_COPY = {
  en: {
    stateLabels: {
      reserve_tightness: 'Reserve Tightness',
      security_intervention: 'Security Intervention',
      network_stress: 'Network Stress',
      supply_shock: 'Supply Shock',
      demand_weather_shock: 'Demand / Weather Shock',
      post_event_structural: 'Post-event / Structural',
    },
    coverage: {
      full: 'full coverage',
      core_only: 'core coverage only',
      partial: 'partial coverage',
      none: 'no verified coverage',
    },
    panelTitle: 'Event Explanation Layer',
    hintTitle: 'Event Hint',
    eventContext: 'Event Context',
    eventDaysLabel: 'Event Days',
    eventTypeLabel: 'Event Type',
    eventRegionLabel: 'Affected Regions',
    eventAssetLabel: 'Affected Assets',
    eventTimeLabel: 'Time Window',
    officialOriginalLabel: 'Official Original',
    officialOriginalToggle: 'View official original',
    noVerifiedTitle: 'No verified event explanation',
    noVerifiedMessage: 'No verified event explanation was found in the selected window.',
    availableTitle: 'Event context available',
    summaryMessage: (eventDays, evidenceCount, coverage) =>
      `${eventDays} event day(s), ${evidenceCount} official evidence item(s), ${coverage}.`,
  },
  zh: {
    stateLabels: {
      reserve_tightness: '\u5907\u7528\u7d27\u5f20',
      security_intervention: '\u5b89\u5168\u5e72\u9884',
      network_stress: '\u7f51\u7edc\u538b\u529b',
      supply_shock: '\u4f9b\u7ed9\u51b2\u51fb',
      demand_weather_shock: '\u9700\u6c42 / \u5929\u6c14\u51b2\u51fb',
      post_event_structural: '\u4e8b\u540e / \u7ed3\u6784\u6027',
    },
    coverage: {
      full: '\u5b8c\u6574\u8986\u76d6',
      core_only: '\u6838\u5fc3\u8986\u76d6',
      partial: '\u90e8\u5206\u8986\u76d6',
      none: '\u65e0\u5df2\u9a8c\u8bc1\u8986\u76d6',
    },
    panelTitle: '\u4e8b\u4ef6\u89e3\u91ca\u5c42',
    hintTitle: '\u4e8b\u4ef6\u63d0\u793a',
    eventContext: '\u4e8b\u4ef6\u80cc\u666f',
    eventDaysLabel: '\u4e8b\u4ef6\u5929\u6570',
    eventTypeLabel: '\u4e8b\u4ef6\u7c7b\u578b',
    eventRegionLabel: '\u5f71\u54cd\u533a\u57df',
    eventAssetLabel: '\u5173\u8054\u8d44\u4ea7',
    eventTimeLabel: '\u65f6\u95f4\u8303\u56f4',
    officialOriginalLabel: '\u5b98\u65b9\u539f\u6587',
    officialOriginalToggle: '\u67e5\u770b\u5b98\u65b9\u539f\u6587',
    noVerifiedTitle: '\u65e0\u5df2\u9a8c\u8bc1\u4e8b\u4ef6\u89e3\u91ca',
    noVerifiedMessage: '\u6240\u9009\u65f6\u95f4\u7a97\u53e3\u5185\u6ca1\u6709\u5df2\u9a8c\u8bc1\u7684\u4e8b\u4ef6\u89e3\u91ca\u3002',
    availableTitle: '\u5b58\u5728\u4e8b\u4ef6\u89e3\u91ca',
    summaryMessage: (eventDays, evidenceCount, coverage) =>
      `${eventDays}\u4e2a\u4e8b\u4ef6\u65e5\uff0c${evidenceCount}\u6761\u5b98\u65b9\u8bc1\u636e\uff0c${coverage}\u3002`,
  },
};

export const EVENT_STATE_META = {
  reserve_tightness: {
    color: '#1d4ed8',
    softColor: 'rgba(29, 78, 216, 0.12)',
  },
  security_intervention: {
    color: '#7c3aed',
    softColor: 'rgba(124, 58, 237, 0.12)',
  },
  network_stress: {
    color: '#d97706',
    softColor: 'rgba(217, 119, 6, 0.12)',
  },
  supply_shock: {
    color: '#dc2626',
    softColor: 'rgba(220, 38, 38, 0.12)',
  },
  demand_weather_shock: {
    color: '#0891b2',
    softColor: 'rgba(8, 145, 178, 0.12)',
  },
  post_event_structural: {
    color: '#4b5563',
    softColor: 'rgba(75, 85, 99, 0.12)',
  },
};

function normalizeLocale(locale) {
  return locale === 'zh' ? 'zh' : 'en';
}

export function getEventText(locale = 'en') {
  return EVENT_COPY[normalizeLocale(locale)];
}

function formatTimestamp(value) {
  if (!value) return '';
  return value.slice(0, 16);
}

function sourceLabel(source, locale = 'en') {
  const labels = {
    en: {
      nem_market_notice: 'AEMO Market Notice',
      nem_high_impact_outage: 'AEMO High Impact Outage',
      wem_dispatch_advisory: 'WEM Dispatch Advisory',
      wem_realtime_outage: 'WEM Realtime Outage',
      bom_warnings: 'BOM Warning',
    },
    zh: {
      nem_market_notice: 'AEMO \u5e02\u573a\u516c\u544a',
      nem_high_impact_outage: 'AEMO \u9ad8\u5f71\u54cd\u505c\u8fd0',
      wem_dispatch_advisory: 'WEM \u8c03\u5ea6\u516c\u544a',
      wem_realtime_outage: 'WEM \u5b9e\u65f6\u505c\u8fd0',
      bom_warnings: 'BOM \u6c14\u8c61\u9884\u8b66',
    },
  };

  const lang = normalizeLocale(locale);
  return labels[lang][source] || source;
}

function rawClassLabel(rawClass, locale = 'en') {
  if (!rawClass) return '';

  const labels = {
    en: {
      'SETTLEMENTS RESIDUE': 'Settlements Residue',
      'PRICES SUBJECT TO REVIEW': 'Prices Subject To Review',
      'RESERVE NOTICE': 'Reserve Notice',
      'LACK OF RESERVE NOTICE': 'Lack Of Reserve Notice',
      'NETWORK OUTAGE': 'Network Outage',
      'DISPATCH ADVISORY': 'Dispatch Advisory',
    },
    zh: {
      'SETTLEMENTS RESIDUE': '\u7ed3\u7b97\u6b8b\u5dee',
      'PRICES SUBJECT TO REVIEW': '\u4ef7\u683c\u5f85\u590d\u6838',
      'RESERVE NOTICE': '\u5907\u7528\u901a\u77e5',
      'LACK OF RESERVE NOTICE': '\u5907\u7528\u4e0d\u8db3\u901a\u77e5',
      'NETWORK OUTAGE': '\u7f51\u7edc\u505c\u8fd0',
      'DISPATCH ADVISORY': '\u8c03\u5ea6\u516c\u544a',
    },
  };

  const lang = normalizeLocale(locale);
  return labels[lang][rawClass] || rawClass;
}

function extractOfficialExcerpt(summary) {
  if (!summary) return '';

  const lines = summary
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean)
    .filter((line) => !/^AEMO ELECTRICITY MARKET NOTICE$/i.test(line))
    .filter((line) => !/^Issued by /i.test(line))
    .filter((line) => !/^This is an AEMO autogenerated Market Notice\.?$/i.test(line));

  return lines.slice(0, 2).join(' ').trim();
}

function severityRank(severity) {
  if (severity === 'high') return 3;
  if (severity === 'medium') return 2;
  if (severity === 'low') return 1;
  return 0;
}

function isoWeekKey(dateString) {
  const date = new Date(`${dateString}T00:00:00`);
  const target = new Date(Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()));
  const dayNr = (target.getUTCDay() + 6) % 7;
  target.setUTCDate(target.getUTCDate() - dayNr + 3);
  const firstThursday = new Date(Date.UTC(target.getUTCFullYear(), 0, 4));
  const firstDayNr = (firstThursday.getUTCDay() + 6) % 7;
  firstThursday.setUTCDate(firstThursday.getUTCDate() - firstDayNr + 3);
  const week = 1 + Math.round((target - firstThursday) / 604800000);
  return `${target.getUTCFullYear()}-W${String(week).padStart(2, '0')}`;
}

function buildOfficialOriginalText(event) {
  return [event?.title, event?.summary].filter(Boolean).join('\n\n').trim();
}

export function buildEventOverlayParams(year, region, month, quarter, dayType) {
  const params = new URLSearchParams({
    year: String(year),
    region,
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

export function getPeriodKey(dateString, aggregation) {
  if (!dateString) return '';
  if (aggregation === 'daily') return dateString;
  if (aggregation === 'weekly') return isoWeekKey(dateString);
  if (aggregation === 'monthly') return dateString.slice(0, 7);
  if (aggregation === 'yearly') return dateString.slice(0, 4);
  return dateString;
}

export function aggregateDailyRollup(dailyRollup = [], aggregation = 'daily') {
  const periods = new Map();

  dailyRollup.forEach((row) => {
    const key = getPeriodKey(row.date, aggregation);
    if (!key) return;

    if (!periods.has(key)) {
      periods.set(key, {
        period: key,
        event_count: 0,
        event_days: 0,
        highest_severity: 'low',
        top_states: [],
      });
    }

    const bucket = periods.get(key);
    bucket.event_count += row.event_count || 0;
    bucket.event_days += 1;

    if (severityRank(row.highest_severity) > severityRank(bucket.highest_severity)) {
      bucket.highest_severity = row.highest_severity;
    }

    const mergedStates = new Map(bucket.top_states.map((state) => [state.key, { ...state }]));
    (row.top_states || []).forEach((state) => {
      if (!mergedStates.has(state.key)) {
        mergedStates.set(state.key, { ...state });
        return;
      }

      const existing = mergedStates.get(state.key);
      existing.count += state.count || 0;
      if (severityRank(state.severity) > severityRank(existing.severity)) {
        existing.severity = state.severity;
      }
    });

    bucket.topStates = Array.from(mergedStates.values())
      .sort((a, b) => severityRank(b.severity) - severityRank(a.severity) || (b.count || 0) - (a.count || 0))
      .slice(0, 3);

    bucket.top_states = bucket.topStates;
  });

  return Array.from(periods.values()).sort((a, b) => a.period.localeCompare(b.period));
}

export function buildPeriodOverlayMap(dailyRollup = [], aggregation = 'daily') {
  return new Map(aggregateDailyRollup(dailyRollup, aggregation).map((row) => [row.period, row]));
}

export function summarizeOverlay(overlay) {
  const dailyRollup = overlay?.daily_rollup || [];
  const events = overlay?.events || [];
  const metadata = overlay?.metadata || {};
  const mergedStates = new Map();

  dailyRollup.forEach((row) => {
    (row.top_states || []).forEach((state) => {
      if (!mergedStates.has(state.key)) {
        mergedStates.set(state.key, { ...state });
        return;
      }

      const existing = mergedStates.get(state.key);
      existing.count += state.count || 0;
      if (severityRank(state.severity) > severityRank(existing.severity)) {
        existing.severity = state.severity;
      }
    });
  });

  return {
    coverageQuality: metadata.coverage_quality || 'none',
    noVerifiedExplanation: Boolean(metadata.no_verified_event_explanation),
    eventDays: dailyRollup.length,
    evidenceCount: events.length,
    topStates: Array.from(mergedStates.values())
      .sort((a, b) => severityRank(b.severity) - severityRank(a.severity) || (b.count || 0) - (a.count || 0))
      .slice(0, 4),
  };
}

export function coverageText(coverageQuality, locale = 'en') {
  const copy = getEventText(locale);
  if (coverageQuality === 'full') return copy.coverage.full;
  if (coverageQuality === 'core_only') return copy.coverage.core_only;
  if (coverageQuality === 'partial') return copy.coverage.partial;
  return copy.coverage.none;
}

export function buildOverlayNotice(overlay, locale = 'en') {
  const summary = summarizeOverlay(overlay);
  const copy = getEventText(locale);

  if (summary.noVerifiedExplanation || summary.eventDays === 0) {
    return {
      variant: 'neutral',
      hasEvents: false,
      coverageQuality: summary.coverageQuality,
      topStates: [],
      title: copy.noVerifiedTitle,
      message: copy.noVerifiedMessage,
    };
  }

  return {
    variant: summary.coverageQuality === 'core_only' ? 'warning' : 'info',
    hasEvents: true,
    coverageQuality: summary.coverageQuality,
    topStates: summary.topStates,
    title: copy.availableTitle,
    message: copy.summaryMessage(
      summary.eventDays,
      summary.evidenceCount,
      coverageText(summary.coverageQuality, locale),
    ),
  };
}

export function metaForState(key, locale = 'en') {
  const copy = getEventText(locale);
  const meta = EVENT_STATE_META[key] || {
    color: '#6b7280',
    softColor: 'rgba(107, 114, 128, 0.12)',
  };

  return {
    ...meta,
    label: copy.stateLabels[key] || key,
  };
}

export function describeEventEvidence(event, locale = 'en') {
  const copy = getEventText(locale);
  const lang = normalizeLocale(locale);
  const states = (event?.normalized_states || []).map((state) => metaForState(state, locale).label);
  const regions = (event?.region_scope || []).join(', ');
  const assets = (event?.asset_scope || []).join(', ');
  const start = formatTimestamp(event?.effective_start || event?.published_at);
  const end = formatTimestamp(event?.effective_end);
  const timeRange = end && end !== start ? `${start} -> ${end}` : start;
  const typeLabel = rawClassLabel(event?.raw_class, locale);
  const excerpt = extractOfficialExcerpt(event?.summary);
  const localizedSource = sourceLabel(event?.source, locale);
  const officialOriginalText = buildOfficialOriginalText(event);
  const hasOfficialOriginal = officialOriginalText.length > 0;

  if (lang === 'zh') {
    const summaryParts = [];
    if (typeLabel) summaryParts.push(`${copy.eventTypeLabel}\uff1a${typeLabel}`);
    if (regions) summaryParts.push(`${copy.eventRegionLabel}\uff1a${regions}`);
    if (assets) summaryParts.push(`${copy.eventAssetLabel}\uff1a${assets}`);
    if (timeRange) summaryParts.push(`${copy.eventTimeLabel}\uff1a${timeRange}`);

    return {
      sourceLabel: localizedSource,
      title: states.length > 0
        ? `${states.join(' / ')}${regions ? ` | ${regions}` : ''}${start ? ` | ${start}` : ''}`
        : `${localizedSource}${regions ? ` | ${regions}` : ''}${start ? ` | ${start}` : ''}`,
      summary: summaryParts.join('\uff1b') || copy.availableTitle,
      excerpt,
      originalTitle: event?.title || '',
      originalSummary: event?.summary || '',
      officialOriginalText,
      hasOfficialOriginal,
    };
  }

  return {
    sourceLabel: localizedSource,
    title: event?.title || `${localizedSource}${regions ? ` | ${regions}` : ''}${start ? ` | ${start}` : ''}`,
    summary: excerpt || [typeLabel, regions, assets, timeRange].filter(Boolean).join(' | '),
    excerpt,
    originalTitle: event?.title || '',
    originalSummary: event?.summary || '',
    officialOriginalText,
    hasOfficialOriginal,
  };
}
