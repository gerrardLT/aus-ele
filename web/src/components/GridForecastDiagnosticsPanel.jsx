import {
  formatForecastPercent,
  formatUnsigned,
  getForecastDiagnosticsCopy,
  getForecastText,
} from '../lib/gridForecast';

function MiniMetric({ label, value }) {
  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--color-muted)]">{label}</div>
      <div className="mt-1 text-sm font-medium text-[var(--color-text)] break-words">{value}</div>
    </div>
  );
}

function diagnosticTone(errorGrade) {
  if (errorGrade === 'high_error') return 'border-[var(--color-status-error)]/40 bg-[var(--color-status-error)]/8';
  if (errorGrade === 'moderate_error') return 'border-[var(--color-status-timeout)]/40 bg-[var(--color-status-timeout)]/8';
  return 'border-[var(--color-status-success)]/40 bg-[var(--color-status-success)]/8';
}

export default function GridForecastDiagnosticsPanel({ baselineForecast, locale = 'en' }) {
  const copy = getForecastDiagnosticsCopy(locale);
  const generic = getForecastText(locale).generic;
  const quantile = baselineForecast?.quantile_scaffold || {};
  const probabilities = baselineForecast?.probabilities || {};
  const evaluation = baselineForecast?.evaluation || {};
  const backtestWindow = evaluation.backtest_window || {};
  const calibration = evaluation.calibration || {};
  const diagnostics = evaluation.diagnostics || {};
  const governance = baselineForecast?.governance_proxy || null;

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 lg:p-5">
      <div className="flex items-center justify-between gap-3">
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {copy.title}
        </div>
        <div className="text-[10px] uppercase tracking-[0.24em] text-[var(--color-muted)]">
          {baselineForecast?.forecast_class || generic.notAvailable}
        </div>
      </div>

      <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,0.85fr)]">
        <div className="grid gap-3">
          <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.quantileBand}</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-3">
              <MiniMetric label={copy.p10} value={`${formatUnsigned(quantile.p10_price_aud_mwh, locale, 1)} AUD/MWh`} />
              <MiniMetric label={copy.p50} value={`${formatUnsigned(quantile.p50_price_aud_mwh, locale, 1)} AUD/MWh`} />
              <MiniMetric label={copy.p90} value={`${formatUnsigned(quantile.p90_price_aud_mwh, locale, 1)} AUD/MWh`} />
            </div>
          </div>

          <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.probabilities}</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <MiniMetric label={copy.spikeProbability} value={formatForecastPercent(probabilities.price_spike, locale)} />
              <MiniMetric label={copy.negativeProbability} value={formatForecastPercent(probabilities.negative_price, locale)} />
              <MiniMetric label={copy.duration} value={`${formatUnsigned(probabilities.negative_price_duration_hours, locale, 2)} h`} />
              <MiniMetric label={copy.method} value={probabilities.duration_method || generic.notAvailable} />
            </div>
          </div>

          <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
            <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">
              {copy.walkForward || 'Walk-forward'}
            </div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <MiniMetric label={copy.method} value={backtestWindow.walk_forward_mode || generic.notAvailable} />
              <MiniMetric label={copy.samplePoints || 'Sample Points'} value={String(backtestWindow.sample_points_evaluated ?? 0)} />
            </div>
          </div>
        </div>

        <div className={`rounded border p-3 ${diagnosticTone(diagnostics.error_grade)}`}>
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.diagnostics}</div>
          <div className="mt-3 grid gap-2">
            <MiniMetric label={copy.errorGrade} value={diagnostics.error_grade || generic.notAvailable} />
            <MiniMetric label={copy.gapDomain} value={diagnostics.primary_gap_domain || generic.notAvailable} />
            <MiniMetric label={copy.summaryGrade} value={calibration.summary_grade || generic.notAvailable} />
            <MiniMetric label={copy.sampleSize} value={String(calibration.sample_count ?? 0)} />
            <MiniMetric label={copy.note} value={diagnostics.summary_note || generic.notAvailable} />
            {governance ? (
              <>
                <MiniMetric
                  label={copy.infoValue || 'Info Value'}
                  value={formatUnsigned(governance.overall_information_value_index, locale, 2)}
                />
                <MiniMetric
                  label={copy.weakestRegime || 'Weakest Regime'}
                  value={governance.weakest_regime || generic.notAvailable}
                />
              </>
            ) : null}
          </div>
        </div>
      </div>
    </div>
  );
}
