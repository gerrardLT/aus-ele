import {
  formatDataGradeLabel,
  formatCoverageModeLabel,
  formatFreshnessLabel,
  formatMetadataUnitLabel,
  formatReadinessStatusLabel,
  getDataGradeTone,
} from '../lib/resultMetadata';

function toneClasses(tone) {
  if (tone === 'success') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-[var(--color-status-success)]';
  }
  if (tone === 'warning') {
    return 'border-[var(--color-status-timeout)]/30 bg-amber-500/10 text-[var(--color-status-timeout)]';
  }
  return 'border-[var(--color-border)] bg-[var(--color-surface)]/70 text-[var(--color-muted)]';
}

function normalizeTagValue(tag, lang) {
  if (!tag) return '';
  if (tag.format === 'coverage_mode') return formatCoverageModeLabel(tag.value, lang);
  if (tag.format === 'readiness_status') return formatReadinessStatusLabel(tag.value, lang);
  return tag.value;
}

export default function DataQualityBadge({ metadata, lang = 'en', className = '', tags = [] }) {
  const tone = getDataGradeTone(metadata?.data_grade);
  const score = metadata?.data_quality_score;
  const unitLabel = formatMetadataUnitLabel(metadata);
  const freshnessLabel = formatFreshnessLabel(metadata?.freshness, lang);
  const normalizedTags = Array.isArray(tags)
    ? tags
        .map((tag) => ({ ...tag, value: normalizeTagValue(tag, lang) }))
        .filter((tag) => tag?.value)
    : [];

  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-xs ${toneClasses(tone)} ${className}`.trim()}
    >
      <span className="font-semibold tracking-wide">{formatDataGradeLabel(metadata?.data_grade, lang)}</span>
      {score != null ? <span className="font-mono">{score}</span> : null}
      {unitLabel ? <span>{unitLabel}</span> : null}
      {metadata?.interval_minutes != null ? <span>{metadata.interval_minutes} min</span> : null}
      <span className="font-mono">{freshnessLabel}</span>
      {normalizedTags.map((tag) => (
        <span
          key={`${tag.label}-${tag.value}`}
          className="inline-flex items-center gap-1 rounded-full border border-current/20 bg-black/10 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide"
        >
          <span>{tag.label}</span>
          <span>{tag.value}</span>
        </span>
      ))}
    </div>
  );
}
