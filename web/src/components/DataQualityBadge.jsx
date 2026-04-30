import {
  formatDataGradeLabel,
  formatFreshnessLabel,
  formatMetadataUnitLabel,
  getDataGradeTone,
} from '../lib/resultMetadata';

function toneClasses(tone) {
  if (tone === 'success') {
    return 'border-emerald-500/30 bg-emerald-500/10 text-emerald-300';
  }
  if (tone === 'warning') {
    return 'border-amber-500/30 bg-amber-500/10 text-amber-300';
  }
  return 'border-[var(--color-border)] bg-[var(--color-surface)]/70 text-[var(--color-muted)]';
}

export default function DataQualityBadge({ metadata, lang = 'en', className = '' }) {
  const tone = getDataGradeTone(metadata?.data_grade);
  const score = metadata?.data_quality_score;
  const unitLabel = formatMetadataUnitLabel(metadata);
  const freshnessLabel = formatFreshnessLabel(metadata?.freshness, lang);

  return (
    <div
      className={`flex flex-wrap items-center gap-2 rounded-xl border px-3 py-2 text-xs ${toneClasses(tone)} ${className}`.trim()}
    >
      <span className="font-semibold tracking-wide">{formatDataGradeLabel(metadata?.data_grade, lang)}</span>
      {score != null ? <span className="font-mono">{score}</span> : null}
      {unitLabel ? <span>{unitLabel}</span> : null}
      {metadata?.interval_minutes != null ? <span>{metadata.interval_minutes} min</span> : null}
      <span className="font-mono opacity-80">{freshnessLabel}</span>
    </div>
  );
}
