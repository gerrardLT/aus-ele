import { useEffect, useMemo, useState } from 'react';
import { fetchJson } from '../lib/apiClient';
import DataQualityBadge from './DataQualityBadge';
import {
  buildP3DecisionUrl,
  formatDecisionActionLabel,
  formatDecisionCalibrationGrade,
  formatDecisionErrorGrade,
  formatDecisionUsageScope,
  getP3DecisionCopy,
  normalizeP3DecisionPayload,
} from '../lib/p3Decision';

function money(value) {
  if (value === null || value === undefined || !Number.isFinite(Number(value))) return 'n/a';
  return `A$${Number(value).toLocaleString(undefined, { maximumFractionDigits: 1 })}`;
}

function SmallMetric({ label, value }) {
  return (
    <div className="rounded border border-[var(--color-border)] bg-white/60 px-3 py-2">
      <div className="text-[10px] uppercase tracking-[0.18em] text-[var(--color-muted)]">{label}</div>
      <div className="mt-1 text-sm font-medium text-[var(--color-text)] break-words">{value}</div>
    </div>
  );
}

export default function P3BessDecisionPanel({ apiBase, year, region, params, requestPayload = null, initialPayload = null, locale = 'en' }) {
  const copy = useMemo(() => getP3DecisionCopy(locale), [locale]);
  const [payload, setPayload] = useState(() => initialPayload ? normalizeP3DecisionPayload(initialPayload) : null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  useEffect(() => {
    if (initialPayload) {
      setPayload(normalizeP3DecisionPayload(initialPayload));
      setLoading(false);
      setError(false);
    }
  }, [initialPayload]);

  useEffect(() => {
    if (initialPayload) return;
    const derivedPayload = requestPayload || (
      apiBase && year && region && params?.capacityMw && params?.durationH
        ? {
            market: region === 'WEM' ? 'WEM' : 'NEM',
            region,
            year,
            power_mw: params.capacityMw,
            energy_mwh: params.capacityMw * params.durationH,
            duration_hours: params.durationH,
            round_trip_efficiency: params.rte / 100,
            degradation_cost_per_mwh: params.degradationCost,
            variable_om_per_mwh: 0,
            network_fee_per_mwh: 0,
            forecast_horizon: '24h',
            reserve_soc_pct: 15,
            risk_mode: 'balanced',
          }
        : null
    );
    if (!apiBase || !derivedPayload) return;

    let ignore = false;
    setLoading(true);
    setError(false);

    fetchJson(buildP3DecisionUrl(apiBase), {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(derivedPayload),
    })
      .then((res) => {
        if (!ignore) {
          setPayload(normalizeP3DecisionPayload(res));
          setLoading(false);
        }
      })
      .catch(() => {
        if (!ignore) {
          setError(true);
          setLoading(false);
        }
      });

    return () => {
      ignore = true;
    };
  }, [apiBase, year, region, params, requestPayload, initialPayload]);

  if (loading) {
    return (
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 text-sm text-[var(--color-muted)]">
        {copy.title}...
      </div>
    );
  }

  if (error || !payload) {
    return (
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">{copy.title}</div>
        <div className="mt-2 text-sm text-[var(--color-muted)]">{copy.notAvailable}</div>
      </div>
    );
  }

  const decision = payload.decisionSummary;
  const recommendationSummary = payload.recommendationSummary || {};
  const explanationChain = payload.explanationChain || [];
  const riskBoundary = payload.riskBoundary || {};
  const strategy = payload.strategyBundle;
  const revenue = payload.revenueAttribution;
  const context = payload.forecastContext;
  const governance = payload.governance || null;
  const sourceBacktest = payload.sourceBacktest || {};
  const cycleSummary = sourceBacktest.cycle_summary || {};
  const socSummary = sourceBacktest.soc_summary || {};
  const dispatchSummary = strategy.forecast_driven_dispatch?.dispatch_summary || {};
  const stochasticScenarios = strategy.stochastic_dispatch?.scenarios || [];
  const coOptimizationLabel = locale === 'zh' ? '联合优化' : 'Co-opt Mode';
  const degradationModeLabel = locale === 'zh' ? '退化约束' : 'Degradation Mode';
  const reserveValueLabel = locale === 'zh' ? '备用价值' : 'Reserve Value';
  const chargeMwhLabel = locale === 'zh' ? '充电量' : 'Charge MWh';
  const dischargeMwhLabel = locale === 'zh' ? '放电量' : 'Discharge MWh';
  const raiseReserveLabel = locale === 'zh' ? '升频备用' : 'Raise Reserve';
  const lowerReserveLabel = locale === 'zh' ? '降频备用' : 'Lower Reserve';
  const avgSocLabel = locale === 'zh' ? '平均 SoC' : 'Avg SoC';
  const scenarioMatrixLabel = locale === 'zh' ? '场景矩阵' : 'Scenario Matrix';
  const actionLabel = formatDecisionActionLabel(recommendationSummary.action || decision.recommended_strategy, locale);
  const calibrationLabel = formatDecisionCalibrationGrade(context.calibration_grade, locale);
  const errorGradeLabel = formatDecisionErrorGrade(context.forecast_error_grade, locale);
  const usageScopeLabel = formatDecisionUsageScope(riskBoundary.usage_scope || governance?.disclaimer?.usage_scope, locale);
  const valueStreamCoverage = Array.isArray(payload.valueStreamCoverage) && payload.valueStreamCoverage.length
    ? payload.valueStreamCoverage.join(', ')
    : copy.notAvailable;
  const capacityRevenueLabel = payload.capacityRevenueInScope === null
    ? copy.notAvailable
    : (payload.capacityRevenueInScope ? 'Yes' : 'No');
  const capacityRevenueText = locale === 'zh'
    ? (payload.capacityRevenueInScope ? '是' : '否')
    : capacityRevenueLabel;

  return (
    <div className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-4 lg:p-5">
      <div className="flex flex-col gap-1">
        <div className="text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">{copy.title}</div>
        <div className="text-sm text-[var(--color-muted)]">{copy.subtitle}</div>
      </div>
      <div className="mt-4">
        <DataQualityBadge
          metadata={payload.metadata}
          lang={locale}
          tags={[
            { label: locale === 'zh' ? '准备度' : 'Readiness', value: payload.readinessStatus, format: 'readiness_status' },
            { label: locale === 'zh' ? '覆盖' : 'Coverage', value: payload.coverageMode, format: 'coverage_mode' },
            { label: locale === 'zh' ? '范围' : 'Scope', value: payload.regulatoryScope || payload.market },
          ]}
        />
      </div>
      {payload.market === 'WEM' || payload.regulatoryScope === 'WEM' ? (
        <div className="mt-3 rounded border border-amber-500 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">
          {locale === 'zh'
            ? 'WEM 的市场设计与 NEM 不同。当前结论更适合用于市场进入方向判断，暂未纳入容量收入，也不建议与 NEM 结果逐项对比。'
            : 'WEM follows a different market design from NEM. This conclusion is best used for market-entry direction, does not yet include capacity revenue, and should not be compared one-for-one with NEM results.'}
        </div>
      ) : null}

      <div className="mt-4 rounded border border-[var(--color-border)] bg-white/50 p-4">
        <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.decisionHeadline || copy.recommendationSummary}</div>
        <div className="mt-3 grid gap-3 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,0.8fr)]">
          <div>
            <div className="text-xl font-semibold text-[var(--color-text)]">
              {recommendationSummary.headline || actionLabel || copy.notAvailable}
            </div>
            <div className="mt-2 text-sm leading-6 text-[var(--color-muted)]">
              {recommendationSummary.rationale || copy.notAvailable}
            </div>
          </div>
          <div className="grid gap-2 sm:grid-cols-3">
            <SmallMetric label={copy.currentMarketStep} value={context.primary_regime || copy.notAvailable} />
            <SmallMetric label={copy.outlookStep} value={context.horizon || copy.notAvailable} />
            <SmallMetric label={copy.decisionStep} value={actionLabel || copy.notAvailable} />
          </div>
        </div>
      </div>

      <div className="mt-4 rounded border border-[var(--color-border)] bg-white/50 p-4">
        <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.recommendationSummary}</div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
          <SmallMetric label={copy.readinessStatus} value={payload.readinessStatus || copy.notAvailable} />
          <SmallMetric label={copy.coverageMode} value={payload.coverageMode || copy.notAvailable} />
          <SmallMetric label={copy.regulatoryScope} value={payload.regulatoryScope || payload.market || copy.notAvailable} />
          <SmallMetric label={copy.capacityRevenueInScope} value={capacityRevenueText} />
        </div>
        <div className="mt-3 grid gap-2 sm:grid-cols-2">
          <SmallMetric label={copy.marketDesignContext} value={payload.marketDesignContext || copy.notAvailable} />
          <SmallMetric label={copy.conclusionScope} value={payload.conclusionScope || copy.notAvailable} />
          <SmallMetric label={copy.valueStreamCoverage} value={valueStreamCoverage} />
          <SmallMetric label={copy.benchmarkFamily} value={payload.benchmarkFamily || copy.notAvailable} />
        </div>
      </div>

      {explanationChain.length > 0 ? (
        <div className="mt-4 rounded border border-[var(--color-border)] bg-white/50 p-4">
          <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.decisionWhy || copy.explanationChain}</div>
          <div className="mt-3 grid gap-3 md:grid-cols-3">
            {explanationChain.map((item, index) => (
              <div key={`${item.step || 'step'}-${index}`} className="rounded border border-[var(--color-border)] bg-[var(--color-surface)] p-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-primary)]">{item.step || copy.notAvailable}</div>
                <div className="mt-2 text-sm font-medium text-[var(--color-text)]">{item.title || copy.notAvailable}</div>
                <div className="mt-2 text-sm leading-6 text-[var(--color-muted)]">{item.detail || copy.notAvailable}</div>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      <div className="mt-4 rounded border border-[var(--color-border)] bg-white/50 p-4">
        <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.decisionEconomics || copy.riskBoundary}</div>
        <div className="mt-3 grid gap-3 lg:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="grid gap-2 sm:grid-cols-2">
            <SmallMetric label={copy.expectedRange} value={riskBoundary.expected_range || money(revenue.scenario_spread)} />
            <SmallMetric label={copy.downsideCase} value={riskBoundary.downside_case || money(revenue.bear_case_net_revenue)} />
            <SmallMetric label={copy.upsideCase} value={riskBoundary.upside_case || money(revenue.bull_case_net_revenue)} />
            <SmallMetric label={copy.disclaimer} value={usageScopeLabel || copy.notAvailable} />
          </div>
          <div className="grid gap-2 sm:grid-cols-2">
            <SmallMetric label={copy.netRevenue} value={money(revenue.net_revenue_after_decision_adjustments)} />
            <SmallMetric label={copy.scenarioSpread} value={money(strategy.stochastic_dispatch?.scenario_spread)} />
            <SmallMetric label={reserveValueLabel} value={money(strategy.forecast_driven_dispatch?.reserve_value_revenue)} />
            <SmallMetric label={copy.fcasProxy} value={money(revenue.fcas_stack_proxy)} />
          </div>
        </div>
      </div>

      <div className="mt-4 grid gap-2 sm:grid-cols-3">
        <SmallMetric label={copy.recommended} value={actionLabel || copy.notAvailable} />
        <SmallMetric label={copy.primaryRegime} value={context.primary_regime || copy.notAvailable} />
        <SmallMetric label={copy.calibrationGrade} value={calibrationLabel || copy.notAvailable} />
      </div>

      <details className="mt-4 rounded border border-[var(--color-border)] bg-white/40 p-4">
        <summary className="cursor-pointer list-none text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">
          {copy.decisionDiagnostics || copy.governance || 'More Detail'}
        </summary>
        <div className="mt-4 grid gap-3 xl:grid-cols-[minmax(0,0.9fr)_minmax(0,1.1fr)]">
          <div className="grid gap-2">
          <SmallMetric label={copy.recommended} value={actionLabel || copy.notAvailable} />
          <SmallMetric label={copy.readinessStatus} value={payload.readinessStatus || copy.notAvailable} />
          <SmallMetric label={copy.riskMode} value={decision.risk_mode || copy.notAvailable} />
          <SmallMetric label={copy.reserveSoc} value={`${decision.reserve_soc_mwh ?? 0} MWh`} />
          <SmallMetric label={copy.rollingMode} value={decision.rolling_horizon_mode || copy.notAvailable} />
          <SmallMetric label={coOptimizationLabel} value={decision.co_optimization_mode || copy.notAvailable} />
          <SmallMetric label={degradationModeLabel} value={decision.degradation_mode || copy.notAvailable} />
          <SmallMetric label={copy.calibrationGrade} value={calibrationLabel || copy.notAvailable} />
          <SmallMetric label={copy.errorGrade} value={errorGradeLabel || copy.notAvailable} />
          </div>

          <div className="grid gap-3">
            <div className="rounded border border-[var(--color-border)] bg-white/50 p-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.strategyBundle}</div>
              <div className="mt-3 grid gap-2 sm:grid-cols-3">
                <SmallMetric label={copy.ruleBased} value={money(strategy.rule_based_dispatch?.net_revenue)} />
                <SmallMetric label={copy.forecastDriven} value={money(strategy.forecast_driven_dispatch?.net_revenue)} />
                <SmallMetric label={copy.stochastic} value={money(strategy.stochastic_dispatch?.base_case_net_revenue)} />
              </div>
            </div>

            <div className="rounded border border-[var(--color-border)] bg-white/50 p-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.revenueAttribution}</div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <SmallMetric label={copy.grossEnergy} value={money(revenue.gross_energy_revenue)} />
                <SmallMetric label={reserveValueLabel} value={money(strategy.forecast_driven_dispatch?.reserve_value_revenue)} />
                <SmallMetric label={copy.degradationCost} value={money(revenue.degradation_cost)} />
                <SmallMetric label={copy.timingAlpha} value={money(revenue.timing_alpha)} />
                <SmallMetric label={copy.regimeAlpha} value={money(revenue.regime_capture_alpha)} />
                <SmallMetric label={copy.fcasProxy} value={money(revenue.fcas_stack_proxy)} />
                <SmallMetric label={copy.degradationPenalty} value={money(strategy.forecast_driven_dispatch?.degradation_reserve_penalty)} />
                <SmallMetric label={copy.netRevenue} value={money(revenue.net_revenue_after_decision_adjustments)} />
                <SmallMetric label={copy.scenarioSpread} value={money(strategy.stochastic_dispatch?.scenario_spread)} />
              </div>
            </div>

            <div className="rounded border border-[var(--color-border)] bg-white/50 p-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{locale === 'zh' ? '调度摘要' : 'Dispatch Summary'}</div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <SmallMetric label={chargeMwhLabel} value={`${dispatchSummary.total_charge_mwh ?? 0} MWh`} />
                <SmallMetric label={dischargeMwhLabel} value={`${dispatchSummary.total_discharge_mwh ?? 0} MWh`} />
                <SmallMetric label={raiseReserveLabel} value={`${dispatchSummary.total_raise_reserve_mwh ?? 0} MWh`} />
                <SmallMetric label={lowerReserveLabel} value={`${dispatchSummary.total_lower_reserve_mwh ?? 0} MWh`} />
                <SmallMetric label={avgSocLabel} value={`${dispatchSummary.average_soc_mwh ?? 0} MWh`} />
                <SmallMetric label={copy.reserveSoc} value={`${dispatchSummary.reserve_soc_mwh ?? decision.reserve_soc_mwh ?? 0} MWh`} />
              </div>
            </div>

            <div className="rounded border border-[var(--color-border)] bg-white/50 p-3">
              <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.backtestSummary || 'Backtest Summary'}</div>
              <div className="mt-3 grid gap-2 sm:grid-cols-2">
                <SmallMetric label={copy.timelinePoints || 'Timeline Points'} value={String(sourceBacktest.timeline_points ?? 0)} />
                <SmallMetric label={copy.equivalentCycles || 'Equivalent Cycles'} value={String(cycleSummary.equivalent_cycles ?? 0)} />
                <SmallMetric label={copy.socStart || 'Start SoC'} value={`${socSummary.soc_start_mwh ?? 0} MWh`} />
                <SmallMetric label={copy.socEnd || 'End SoC'} value={`${socSummary.soc_end_mwh ?? 0} MWh`} />
              </div>
            </div>

            {governance ? (
              <div className="rounded border border-[var(--color-border)] bg-white/50 p-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{copy.governance || 'Governance'}</div>
                <div className="mt-3 grid gap-2 sm:grid-cols-2">
                  <SmallMetric label={copy.freshness || 'Freshness'} value={governance.freshness?.status || copy.notAvailable} />
                  <SmallMetric label={copy.drift || 'Drift'} value={governance.drift?.status || copy.notAvailable} />
                  <SmallMetric label={copy.disclaimer || 'Usage Scope'} value={governance.disclaimer?.usage_scope || copy.notAvailable} />
                  <SmallMetric label={copy.lineage || 'Lineage'} value={governance.lineage?.source_id || copy.notAvailable} />
                </div>
              </div>
            ) : null}

            {stochasticScenarios.length > 0 ? (
              <div className="rounded border border-[var(--color-border)] bg-white/50 p-3">
                <div className="text-[10px] font-bold uppercase tracking-[0.2em] text-[var(--color-muted)]">{scenarioMatrixLabel}</div>
                <div className="mt-3 overflow-x-auto">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="border-b border-[var(--color-border)] text-left uppercase tracking-wider text-[var(--color-muted)]">
                        <th className="pb-2 pr-3">{locale === 'zh' ? '场景' : 'Scenario'}</th>
                        <th className="pb-2 pr-3 text-right">{copy.netRevenue}</th>
                        <th className="pb-2 pr-3 text-right">{raiseReserveLabel}</th>
                        <th className="pb-2 text-right">{lowerReserveLabel}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {stochasticScenarios.map((scenario) => (
                        <tr key={scenario.name} className="border-b border-[var(--color-border)]/60">
                          <td className="py-2 pr-3 font-medium capitalize">{scenario.name}</td>
                          <td className="py-2 pr-3 text-right">{money(scenario.net_revenue)}</td>
                          <td className="py-2 pr-3 text-right">{scenario.dispatch_summary?.total_raise_reserve_mwh ?? 0}</td>
                          <td className="py-2 text-right">{scenario.dispatch_summary?.total_lower_reserve_mwh ?? 0}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            ) : null}
          </div>
        </div>
      </details>

      {payload.warnings?.length ? (
        <div className="mt-4 flex flex-wrap gap-2">
          {payload.warnings.map((warning) => (
            <span key={warning} className="inline-flex items-center rounded-full border border-amber-200 bg-amber-50 px-3 py-1 text-[10px] uppercase tracking-widest text-amber-700">
              {warning}
            </span>
          ))}
        </div>
      ) : null}
    </div>
  );
}
