/**
 * InvestmentAnalysis — 编排组件
 * 组合 ParameterPanel、KpiDashboard、CashFlowChart、CashFlowTable、
 * MonteCarloPanel、DecisionSummaryPanel 等子组件
 */

import { useEffect, useMemo, useRef, useState } from 'react';
import { motion } from 'framer-motion';
import {
  buildInvestmentRequestKey,
  formatPercentageValue,
  getInvestmentCopy,
  shouldAutoRunInvestment,
} from '../lib/investmentAnalysis';
import { fmt } from '../lib/formatters';
import { getApiBase } from '../lib/apiBase';
import DataQualityBadge from './DataQualityBadge';
import RegimeCompactInline from './RegimeCompactInline';
import { formatRegimeName, normalizeRegimeCompact } from '../lib/regimeCompact';
import { getDataGradeCaveat, getResultMetadata } from '../lib/resultMetadata';
import { SummaryBlock } from './investment/KpiCard';
import ParameterPanel from './investment/ParameterPanel';
import KpiDashboard from './investment/KpiDashboard';
import CashFlowChart from './investment/CashFlowChart';
import CashFlowTable from './investment/CashFlowTable';
import MonteCarloPanel from './investment/MonteCarloPanel';
import DecisionSummaryPanel from './investment/DecisionSummaryPanel';

const API_BASE = getApiBase();

export const INVESTMENT_PRESET_DEFAULTS = {
  power_mw: 100,
  duration_hours: 4,
  round_trip_efficiency: 0.87,
  degradation_rate: 0.025,
  capex_per_kwh: 350,
  fixed_om_per_mw_year: 12000,
  variable_om_per_mwh: 2.5,
  grid_connection_cost: 5000000,
  land_lease_per_year: 200000,
  discount_rate: 0.08,
  project_life_years: 20,
  revenue_capture_rate: 0.65,
  fcas_revenue_per_mw_year: 15000,
  fcas_revenue_mode: 'auto',
  capacity_payment_per_mw_year: 0,
  backtest_years: [2024, 2025],
  monte_carlo_enabled: false,
  forecast_inefficiency: 0.15,
  fcas_activation_probability: 0.15,
  cost_of_debt: 0.06,
  target_dscr: 1.30,
  debt_tenor_years: 15,
};

function getDefaultMode(region) {
  return region === 'WEM' ? 'manual' : 'auto';
}

function getRegimeFinanceNarrative(regime, lang) {
  const isZh = lang === 'zh';
  switch (regime) {
    case 'oversupply':
      return isZh
        ? '供给宽松更利于低价充电，但项目价值仍取决于后续能否稳定兑现放电价差。'
        : 'Oversupply improves charging entry conditions, but project value still depends on reliably monetizing the downstream discharge spread.';
    case 'negative_price':
      return isZh
        ? '负价提高了充电机会密度，但要看持续时长、回升速度和可兑现的卖出窗口。'
        : 'Negative pricing increases charge opportunities, but value depends on duration, rebound speed, and executable sell windows.';
    case 'scarcity':
      return isZh
        ? '紧缺通常抬升放电与辅助服务上行空间，但现金流波动和预测误差也会同步放大。'
        : 'Scarcity usually lifts discharge and ancillary upside, while increasing cash-flow volatility and forecast error at the same time.';
    case 'reserve_stress':
      return isZh
        ? '备用紧张往往先利好 FCAS 与应急价值，但持续性需要结合短缺链条和恢复速度判断。'
        : 'Reserve stress often supports FCAS and emergency value first, but durability depends on how persistent the shortfall chain becomes.';
    case 'congestion':
      return isZh
        ? '拥塞意味着区域价差信号更重要，收益判断需要同时看节点位置和约束持续时间。'
        : 'Congestion makes locational spreads more important, so revenue quality depends on node exposure and constraint duration.';
    case 'transmission_separation':
      return isZh
        ? '区域分离会放大跨区价差与局地风险，模型应谨慎区分结构性机会和一次性异常。'
        : 'Transmission separation widens inter-regional spreads and local risk, so the model should separate structural opportunity from one-off dislocation.';
    default:
      return isZh
        ? '当前 regime 信号不足，投资判断应更多依赖基础现金流、回测覆盖和参数敏感性。'
        : 'Regime evidence is limited here, so investment interpretation should lean more on baseline cash flow, backtest coverage, and sensitivity ranges.';
  }
}

export function buildInvestmentDecisionRequest({ region, year, params = INVESTMENT_PRESET_DEFAULTS }) {
  return {
    market: region === 'WEM' ? 'WEM' : 'NEM',
    region,
    year: year || (Array.isArray(params.backtest_years) ? params.backtest_years[0] : null),
    power_mw: params.power_mw,
    energy_mwh: params.power_mw * params.duration_hours,
    duration_hours: params.duration_hours,
    round_trip_efficiency: params.round_trip_efficiency,
    degradation_cost_per_mwh: 0,
    variable_om_per_mwh: params.variable_om_per_mwh,
    network_fee_per_mwh: 0,
    forecast_horizon: '7d',
    reserve_soc_pct: 15,
    risk_mode: 'balanced',
  };
}

export default function InvestmentAnalysis({ region, year, lang = 'en', t, scopeNote, regimeCompactCopy, showDecisionPanel = true }) {
  const sectionRef = useRef(null);
  const requestControllerRef = useRef(null);
  const requestSeqRef = useRef(0);
  const [params, setParams] = useState({
    ...INVESTMENT_PRESET_DEFAULTS,
    fcas_revenue_mode: getDefaultMode(region),
  });
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [isVisible, setIsVisible] = useState(false);
  const [loadedKey, setLoadedKey] = useState(null);
  const requestKey = buildInvestmentRequestKey(region);
  const copy = useMemo(() => getInvestmentCopy(lang, t), [lang, t]);

  const resultMetadata = getResultMetadata(result);
  const sectionMetadata = result?.metadata
    ? resultMetadata
    : {
        data_grade: region === 'WEM' ? 'preview' : 'decision-grade',
        unit: 'AUD',
        warnings: region === 'WEM' ? ['preview_only', 'core_only'] : [],
      };
  const previewCaveat = region === 'WEM' ? getDataGradeCaveat(sectionMetadata.data_grade, lang) : '';
  const wemReadinessCaveat = region === 'WEM'
    ? (lang === 'zh'
      ? 'WEM 的市场设计与 NEM 不同。这里的结果更适合用于方向判断，暂未纳入容量收入和全部制度价值流，因此不建议直接与 NEM 结果逐项对比。'
      : 'WEM follows a different market design from NEM. This view is best used for directional assessment and does not yet include capacity revenue or every market value stream, so it should not be compared one-for-one with NEM results.')
    : '';
  const capitalViewScopeNote = !showDecisionPanel
    ? (lang === 'zh'
      ? '这里提供项目收益、现金流和回本分析，用于辅助判断市场进入可行性。'
      : 'This section provides project return, cash-flow, and payback analysis to support entry decisions.')
    : '';

  // --- Intersection Observer ---
  useEffect(() => {
    const node = sectionRef.current;
    if (!node) return undefined;
    const observer = new IntersectionObserver(
      ([entry]) => { setIsVisible(entry.isIntersecting); },
      { threshold: 0.15, rootMargin: '0px 0px -10% 0px' },
    );
    observer.observe(node);
    return () => observer.disconnect();
  }, []);

  // --- Region change reset ---
  useEffect(() => {
    setParams((prev) => ({ ...prev, fcas_revenue_mode: getDefaultMode(region) }));
    setResult(null);
    setError(null);
    setLoadedKey(null);
    requestControllerRef.current?.abort();
    requestControllerRef.current = null;
    setLoading(false);
  }, [region]);

  useEffect(() => (() => { requestControllerRef.current?.abort(); }), []);

  // --- Run Analysis ---
  async function runAnalysis(nextParams = params) {
    requestControllerRef.current?.abort();
    const controller = new AbortController();
    requestControllerRef.current = controller;
    requestSeqRef.current += 1;
    const seq = requestSeqRef.current;
    const requestKeyForRun = buildInvestmentRequestKey(region);

    setLoading(true);
    setError(null);

    try {
      const body = {
        region,
        battery: {
          power_mw: nextParams.power_mw,
          duration_hours: nextParams.duration_hours,
          round_trip_efficiency: nextParams.round_trip_efficiency,
        },
        financial: {
          capex_per_kwh: nextParams.capex_per_kwh,
          fixed_om_per_mw_year: nextParams.fixed_om_per_mw_year,
          variable_om_per_mwh: nextParams.variable_om_per_mwh,
          grid_connection_cost: nextParams.grid_connection_cost,
          land_lease_per_year: nextParams.land_lease_per_year,
          discount_rate: nextParams.discount_rate,
          project_life_years: nextParams.project_life_years,
          capacity_payment_per_mw_year: nextParams.capacity_payment_per_mw_year,
        },
        revenue_capture_rate: nextParams.revenue_capture_rate,
        fcas_revenue_per_mw_year: nextParams.fcas_revenue_per_mw_year,
        fcas_revenue_mode: nextParams.fcas_revenue_mode,
        monte_carlo: { enabled: nextParams.monte_carlo_enabled, iterations: 100 },
      };

      const response = await fetch(`${API_BASE}/investment-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal: controller.signal,
      });
      const data = await response.json();
      if (!response.ok || data.error) {
        throw new Error(data.error || data.detail || copy.statuses.requestFailed);
      }
      setResult(data);
      setLoadedKey(requestKeyForRun);
    } catch (err) {
      if (err.name === 'AbortError') return;
      setError(err.message);
    } finally {
      if (requestSeqRef.current === seq) setLoading(false);
    }
  }

  // --- Auto-run on visibility ---
  useEffect(() => {
    if (!shouldAutoRunInvestment({ isVisible, isLoading: loading, requestKey, loadedKey })) return;
    runAnalysis({ ...params, fcas_revenue_mode: getDefaultMode(region) });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [isVisible, requestKey, loadedKey, loading]);

  // --- Derived data ---
  const cashFlows = useMemo(() => (
    (result?.cash_flows || result?.scenarios?.[0]?.cash_flows || [])
      .filter((row) => row.year > 0)
      .map((row) => ({ ...row, revenue: row.total_revenue ?? row.revenue ?? 0, cumulative: row.cumulative_cash_flow ?? row.cumulative ?? 0 }))
  ), [result]);

  const decisionAdjustedCashFlows = useMemo(() => (
    (result?.decision_adjusted_cash_flows || [])
      .filter((row) => row.year > 0)
      .map((row) => ({ ...row, revenue: row.total_revenue ?? row.revenue ?? 0, cumulative: row.cumulative_cash_flow ?? row.cumulative ?? 0 }))
  ), [result]);

  const decisionAdjustedScenarios = useMemo(() => result?.decision_adjusted_scenarios || [], [result]);

  const scenarioComparisonRows = useMemo(() => {
    const baselineScenarios = result?.scenarios || [];
    if (!baselineScenarios.length || !decisionAdjustedScenarios.length) return [];
    return baselineScenarios.map((scenario) => {
      const adj = decisionAdjustedScenarios.find((c) => c.scenario_name === scenario.scenario_name);
      const baseNpv = scenario?.metrics?.npv ?? null;
      const adjNpv = adj?.metrics?.npv ?? null;
      return {
        scenario_name: scenario.scenario_name,
        base_npv: baseNpv,
        adjusted_npv: adjNpv,
        delta_npv: (adjNpv != null && baseNpv != null) ? adjNpv - baseNpv : null,
        base_irr: scenario?.metrics?.irr ?? null,
        adjusted_irr: adj?.metrics?.irr ?? null,
      };
    });
  }, [decisionAdjustedScenarios, result]);

  const chartData = useMemo(() => cashFlows.map((row) => {
    const adjustedRow = decisionAdjustedCashFlows.find((c) => c.year === row.year);
    return { ...row, adjusted_cumulative: adjustedRow?.cumulative ?? null, adjusted_revenue: adjustedRow?.revenue ?? null };
  }), [cashFlows, decisionAdjustedCashFlows]);

  const metrics = result?.base_metrics || {};
  const decisionAdjustedMetrics = result?.decision_adjusted_metrics || null;
  const mc = result?.monte_carlo;
  const decisionAdjustedMonteCarlo = result?.decision_adjusted_monte_carlo || null;
  const p3Governance = result?.p3_decision?.governance || null;
  const p3Decision = result?.p3_decision || null;
  const backtest_observed = result?.backtest_observed || null;
  const backtest_reference = result?.backtest_reference || null;
  const backtest_fallback_used = Boolean(result?.backtest_fallback_used);
  const noStandardizedBacktestCoverage = result?.arbitrage_baseline_source === 'no_standardized_backtest_data';
  const primaryBacktestDriver = backtest_reference?.drivers?.[0] || null;
  const backtestSourceYears = backtest_reference?.inputs?.map((item) => item.year).filter(Boolean).join(', ') || '-';

  const normalizedRegimeCompact = useMemo(() => normalizeRegimeCompact(result?.regime_compact), [result?.regime_compact]);
  const primaryRegime = normalizedRegimeCompact.primary_regime;
  const primaryRegimeName = formatRegimeName(primaryRegime?.regime, regimeCompactCopy);
  const regimeNarrativeDriver = normalizedRegimeCompact.top_drivers[0]?.headline || copy.regimeNarrativeEmpty;
  const regimeNarrativeTransition = normalizedRegimeCompact.transition_hints[0] || copy.regimeNarrativeEmpty;
  const regimeNarrativeFinance = getRegimeFinanceNarrative(primaryRegime?.regime, lang);

  const assumptionChips = [
    { label: copy.kpis.fcasMode, value: params.fcas_revenue_mode },
    { label: copy.kpis.uiYear, value: year || '-' },
  ];
  const lazyLoadNote = isVisible ? copy.lazyVisible : (copy.lazyHidden || copy.statuses.hidden);
  const investmentStatusTags = [
    { label: lang === 'zh' ? '准备度' : 'Readiness', value: p3Decision?.readiness_status || '', format: 'readiness_status' },
    { label: lang === 'zh' ? '覆盖' : 'Coverage', value: p3Decision?.coverage_mode || '', format: 'coverage_mode' },
    { label: lang === 'zh' ? '范围' : 'Scope', value: p3Decision?.conclusion_scope || '' },
  ].filter((item) => item.value);

  // --- Render ---
  return (
    <div ref={sectionRef} className="col-span-12 mt-12 border-t border-[var(--color-border)] pt-8">
      <div className="mb-6 flex flex-col justify-between gap-2 md:flex-row md:items-baseline">
        <div>
          <h2 className="text-2xl font-serif md:text-[1.75rem]">{copy.title}</h2>
          <p className="font-sans text-xs leading-5 text-[var(--color-muted)] md:overflow-hidden md:text-ellipsis md:whitespace-nowrap">
            {copy.subtitle}
          </p>
        </div>
        <div className="text-sm font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {copy.eyebrow}
        </div>
      </div>

      <div className="mb-6">
        <DataQualityBadge metadata={sectionMetadata} lang={lang} tags={investmentStatusTags} />
      </div>
      <div className="mb-6">
        <RegimeCompactInline compact={result?.regime_compact} copy={regimeCompactCopy} />
      </div>

      {scopeNote && (
        <div className="mb-5 rounded border border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-xs leading-5 text-[var(--color-muted)]">{scopeNote}</div>
      )}
      {capitalViewScopeNote && (
        <div className="mb-5 rounded border border-[var(--color-border)] bg-[var(--color-bg)] px-4 py-3 text-xs leading-5 text-[var(--color-muted)]">{capitalViewScopeNote}</div>
      )}
      {previewCaveat && (
        <div className="mb-5 rounded border border-amber-500 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">{previewCaveat}</div>
      )}
      {wemReadinessCaveat && (
        <div className="mb-5 rounded border border-amber-500 bg-amber-50 px-4 py-3 text-xs leading-5 text-amber-900">{wemReadinessCaveat}</div>
      )}
      {!result && !loading && (
        <div className="mb-6 rounded border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-4 py-3 text-xs leading-5 text-[var(--color-muted)]">{lazyLoadNote}</div>
      )}

      <div className="grid grid-cols-12 gap-6">
        {/* 左侧参数面板 */}
        <div className="col-span-12 space-y-4 lg:col-span-4">
          <ParameterPanel
            params={params}
            setParams={setParams}
            loading={loading}
            onRun={() => runAnalysis()}
            copy={copy}
          />
        </div>

        {/* 右侧结果区域 */}
        <div className="col-span-12 lg:col-span-8">
          {error && (
            <div className="mb-4 rounded border border-red-300 bg-red-50 p-4 text-red-700">{error}</div>
          )}

          {loading && !result && (
            <div className="flex flex-col items-center justify-center rounded-lg border border-dashed border-[var(--color-border)] bg-[var(--color-surface)] px-6 py-16 text-center">
              <div className="mb-4 h-10 w-10 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-blue-500" />
              <p className="text-sm font-medium text-[var(--color-text)]">
                {lang === 'zh' ? '正在计算 20 年投资预测...' : 'Computing 20-year investment projection...'}
              </p>
              <p className="mt-2 text-xs text-[var(--color-muted)]">
                {lang === 'zh'
                  ? '首次加载需要 30–60 秒（模型校准中），后续请求会快很多'
                  : 'First load takes 30–60s (model calibrating), subsequent requests will be much faster'}
              </p>
            </div>
          )}

          {result && (
            <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="space-y-8">
              {/* KPI 仪表盘 */}
              <KpiDashboard
                metrics={metrics}
                params={params}
                copy={copy}
                lang={lang}
                decisionAdjustedMetrics={decisionAdjustedMetrics}
                decisionAdjustedCashFlows={decisionAdjustedCashFlows}
                scenarioComparisonRows={scenarioComparisonRows}
              />

              {/* 投资决策总结面板 */}
              <DecisionSummaryPanel
                metrics={metrics}
                params={params}
                mc={mc}
                regimeCompact={normalizedRegimeCompact}
                lang={lang}
              />

              {/* P4 数据状态 */}
              {p3Governance && (
                <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                  <h4 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">
                    {lang === 'zh' ? 'P4 数据状态概览' : 'P4 Data Status Snapshot'}
                  </h4>
                  <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
                    <SummaryBlock label={lang === 'zh' ? '适用范围' : 'Use Case'} value={p3Governance?.disclaimer?.usage_scope || '-'} />
                    <SummaryBlock label={lang === 'zh' ? '数据新鲜度' : 'Freshness'} value={p3Governance?.freshness?.status || '-'} />
                    <SummaryBlock label={lang === 'zh' ? '漂移状态' : 'Drift'} value={p3Governance?.drift?.status || '-'} />
                    <SummaryBlock label={lang === 'zh' ? '预测增益' : 'Forecast Uplift'} value={fmt(p3Governance?.forecast_value_attribution?.net_uplift)} />
                  </div>
                  <div className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                    {p3Governance?.disclaimer?.investment_grade === false
                      ? (lang === 'zh' ? '当前输出为研究与运营辅助口径，不应直接视为投资级结论。' : 'Current output is for research and operational support only and should not be treated as an investment-grade conclusion.')
                      : '-'}
                  </div>
                </div>
              )}

              {/* 假设标签 */}
              <div className="grid grid-cols-1 gap-3 md:grid-cols-5">
                {assumptionChips.map((chip) => (
                  <div key={chip.label} className="rounded border border-[var(--color-border)] p-3">
                    <div className="mb-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{chip.label}</div>
                    <div className="break-words text-sm font-bold font-mono">{chip.value}</div>
                  </div>
                ))}
              </div>

              {/* 市场状态说明 */}
              <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
                <h4 className="mb-3 text-sm font-bold uppercase tracking-wider">{copy.regimeNarrativeTitle}</h4>
                {normalizedRegimeCompact.availability_status !== 'available' ? (
                  <div className="text-sm text-[var(--color-muted)]">{copy.regimeNarrativeEmpty}</div>
                ) : (
                  <div className="grid grid-cols-1 gap-3 text-sm md:grid-cols-3">
                    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                      <div className="mb-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{copy.regimeNarrativePrimary}</div>
                      <div className="font-semibold">{primaryRegimeName}</div>
                      <div className="mt-1 text-xs text-[var(--color-muted)]">Score {primaryRegime?.score?.toFixed?.(0) ?? '--'}</div>
                    </div>
                    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                      <div className="mb-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{copy.regimeNarrativeDriver}</div>
                      <div className="leading-6 text-[var(--color-text)]">{regimeNarrativeDriver}</div>
                    </div>
                    <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
                      <div className="mb-1 text-[10px] uppercase tracking-widest text-[var(--color-muted)]">{copy.regimeNarrativeFinance}</div>
                      <div className="leading-6 text-[var(--color-text)]">{regimeNarrativeFinance}</div>
                      <div className="mt-2 border-t border-[var(--color-border)] pt-2 text-xs text-[var(--color-muted)]">
                        <span className="font-semibold">{copy.regimeNarrativeTransition}: </span>{regimeNarrativeTransition}
                      </div>
                    </div>
                  </div>
                )}
              </div>

              {/* 回测面板 */}
              {backtest_observed && (
                <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
                  <div className="rounded-lg border border-[var(--color-border)] p-4">
                    <h4 className="mb-3 text-sm font-bold uppercase tracking-wider">{copy.backtestObservedTitle}</h4>
                    <div className="grid grid-cols-2 gap-3">
                      <SummaryBlock label={copy.grossEnergyRevenue} value={fmt(backtest_observed.gross_energy_revenue)} />
                      <SummaryBlock label={copy.netEnergyRevenue} value={fmt(backtest_observed.net_energy_revenue)} />
                      <SummaryBlock label={copy.observedNetArbitrage} value={fmt(result?.baseline_revenue?.arbitrage_net_observed)} />
                      <SummaryBlock label={copy.equivalentCycles} value={backtest_observed.equivalent_cycles?.toFixed?.(2) ?? '-'} />
                    </div>
                  </div>
                  <div className="rounded-lg border border-[var(--color-border)] p-4 bg-[var(--color-surface)]">
                    <h4 className="mb-3 text-sm font-bold uppercase tracking-wider">{copy.backtestTraceTitle}</h4>
                    <div className="grid grid-cols-2 gap-3">
                      <SummaryBlock label={copy.methodologyVersion} value={backtest_observed.methodology_version || '-'} />
                      <SummaryBlock label={copy.driverCount} value={`${backtest_reference?.drivers?.length || 0}`} />
                      <SummaryBlock label={copy.timelinePoints} value={`${primaryBacktestDriver?.timeline_points ?? '-'}`} />
                      <SummaryBlock label={copy.sourceYears} value={backtestSourceYears} />
                    </div>
                    {backtest_fallback_used && (
                      <div className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">{copy.statuses.legacyFallbackActive}</div>
                    )}
                    {noStandardizedBacktestCoverage && (
                      <div className="mt-3 rounded border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-900">
                        <div className="font-bold">{copy.noBacktestCoverageTitle}</div>
                        <div className="mt-1">{copy.noBacktestCoverageBody}</div>
                      </div>
                    )}
                  </div>
                </div>
              )}

              {/* 假设列表 */}
              {result.assumptions?.length > 0 && (
                <div className="rounded-lg border border-[var(--color-border)] p-4">
                  <h4 className="mb-3 text-sm font-bold uppercase tracking-wider">{copy.assumptions}</h4>
                  <div className="space-y-2 text-sm text-[var(--color-muted)]">
                    {result.assumptions.map((item, index) => (
                      <div key={index}>- {item}</div>
                    ))}
                  </div>
                </div>
              )}

              {/* Monte Carlo 面板 */}
              <MonteCarloPanel
                mc={mc}
                decisionAdjustedMonteCarlo={decisionAdjustedMonteCarlo}
                copy={copy}
                lang={lang}
              />

              {/* 现金流图表 */}
              <CashFlowChart
                chartData={chartData}
                copy={copy}
                lang={lang}
                hasDecisionAdjusted={decisionAdjustedCashFlows.length > 0}
              />

              {/* 现金流表格 */}
              <CashFlowTable cashFlows={cashFlows} copy={copy} lang={lang} />
            </motion.div>
          )}
        </div>
      </div>
    </div>
  );
}
