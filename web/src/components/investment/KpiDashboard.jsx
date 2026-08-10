/**
 * KpiDashboard — 6 个 KPI 卡片（NPV、IRR、Debt Cap、Levered IRR、Payback、ROI）
 * 包含 P3 决策调整后指标和情景重估表格
 */

import { KpiCard, SummaryBlock } from './KpiCard';
import { fmt } from '../../lib/formatters';
import { formatPercentageValue } from '../../lib/investmentAnalysis';
import NarrativeTooltip from '../modules/NarrativeTooltip';

const LABELS = {
  zh: {
    p3AdjustedMetrics: 'P3 决策调整后指标',
    adjNpv: '调整后 NPV',
    adjIrr: '调整后 IRR',
    adjRoi: '调整后 ROI',
    adjPayback: '调整后回本期',
    p3Adjusted: 'P3 调整',
    p3AdjustedCashFlow: 'P3 调整后现金流',
    year1NetCashFlow: '首年净现金流',
    finalCumulative: '末年累计现金流',
    year1Revenue: '首年总收入',
    year1Soh: '首年 SOH',
    p3ScenarioRepricing: 'P3 情景重估',
    scenario: '情景',
    baseNpv: '基线 NPV',
    p3Npv: 'P3 后 NPV',
    npvDelta: 'NPV 变化',
    p3Irr: 'P3 后 IRR',
  },
  en: {
    p3AdjustedMetrics: 'P3 Decision-Adjusted Metrics',
    adjNpv: 'Adj. NPV',
    adjIrr: 'Adj. IRR',
    adjRoi: 'Adj. ROI',
    adjPayback: 'Adj. Payback',
    p3Adjusted: 'P3 adjusted',
    p3AdjustedCashFlow: 'P3 Decision-Adjusted Cash Flow',
    year1NetCashFlow: 'Year 1 Net Cash Flow',
    finalCumulative: 'Final Cumulative Cash Flow',
    year1Revenue: 'Year 1 Revenue',
    year1Soh: 'Year 1 SoH',
    p3ScenarioRepricing: 'P3 Scenario Repricing',
    scenario: 'Scenario',
    baseNpv: 'Base NPV',
    p3Npv: 'P3 NPV',
    npvDelta: 'NPV Delta',
    p3Irr: 'P3 IRR',
  },
};

export default function KpiDashboard({
  metrics,
  params,
  copy,
  lang = 'zh',
  decisionAdjustedMetrics,
  decisionAdjustedCashFlows,
  scenarioComparisonRows,
}) {
  const t = LABELS[lang] || LABELS.zh;

  return (
    <div className="space-y-8">
      {/* 主 KPI 卡片 */}
      <div className="grid grid-cols-2 gap-4 md:grid-cols-3 xl:grid-cols-6">
        <KpiCard
          label={copy.kpis.npv}
          value={<NarrativeTooltip module="investment_npv" lang={lang}>{fmt(metrics.npv)}</NarrativeTooltip>}
          tone={metrics.npv > 0 ? 'good' : 'bad'}
          sub={`${copy.kpiSubs.discount} ${(params.discount_rate * 100).toFixed(1)}%`}
        />
        <KpiCard
          label={copy.kpis.irr}
          value={<NarrativeTooltip module="investment_irr" lang={lang}>{formatPercentageValue(metrics.irr)}</NarrativeTooltip>}
          tone={metrics.irr > params.discount_rate * 100 ? 'good' : 'warn'}
          sub={copy.kpiSubs.unlevered}
        />
        <KpiCard
          label={copy.kpis.debtCap}
          value={fmt(metrics.debt_capacity)}
          tone="brand"
          sub={`${copy.kpiSubs.avgDscr} ${metrics.dscr_avg ? metrics.dscr_avg.toFixed(2) : '-'}x`}
        />
        <KpiCard
          label={copy.kpis.leveredIrr}
          value={formatPercentageValue(metrics.levered_irr !== null && metrics.levered_irr !== undefined ? metrics.levered_irr * 100 : null)}
          tone="good"
          sub={copy.kpiSubs.equityReturn}
        />
        <KpiCard
          label={copy.kpis.payback}
          value={metrics.payback_years ? `${metrics.payback_years} ${copy.kpiSubs.years}` : copy.kpis.overLife}
          tone={metrics.payback_years ? 'good' : 'warn'}
          sub={`${copy.kpiSubs.life} ${params.project_life_years} ${copy.kpiSubs.years}`}
        />
        <KpiCard
          label={copy.kpis.roi}
          value={formatPercentageValue(metrics.roi_pct)}
          tone="brand"
          sub={copy.kpiSubs.totalReturn}
        />
      </div>

      {/* P3 决策调整后指标 */}
      {decisionAdjustedMetrics && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <h4 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">
            {t.p3AdjustedMetrics}
          </h4>
          <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
            <KpiCard label={t.adjNpv} value={fmt(decisionAdjustedMetrics.npv)} tone={decisionAdjustedMetrics.npv > metrics.npv ? 'good' : 'warn'} sub={t.p3Adjusted} />
            <KpiCard label={t.adjIrr} value={formatPercentageValue(decisionAdjustedMetrics.irr)} tone="good" sub={t.p3Adjusted} />
            <KpiCard label={t.adjRoi} value={formatPercentageValue(decisionAdjustedMetrics.roi_pct)} tone="brand" sub={t.p3Adjusted} />
            <KpiCard label={t.adjPayback} value={decisionAdjustedMetrics.payback_years ? `${decisionAdjustedMetrics.payback_years} ${copy.kpiSubs.years}` : copy.kpis.overLife} tone="good" sub={t.p3Adjusted} />
          </div>
        </div>
      )}

      {/* P3 调整后现金流摘要 */}
      {decisionAdjustedCashFlows.length > 0 && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <h4 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">
            {t.p3AdjustedCashFlow}
          </h4>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            <SummaryBlock
              label={t.year1NetCashFlow}
              value={fmt(decisionAdjustedCashFlows[0]?.net_cash_flow)}
            />
            <SummaryBlock
              label={t.finalCumulative}
              value={fmt(decisionAdjustedCashFlows[decisionAdjustedCashFlows.length - 1]?.cumulative)}
            />
            <SummaryBlock
              label={t.year1Revenue}
              value={fmt(decisionAdjustedCashFlows[0]?.revenue)}
            />
            <SummaryBlock
              label={t.year1Soh}
              value={decisionAdjustedCashFlows[0]?.state_of_health ? `${(decisionAdjustedCashFlows[0].state_of_health * 100).toFixed(1)}%` : '-'}
            />
          </div>
        </div>
      )}

      {/* P3 情景重估 */}
      {scenarioComparisonRows.length > 0 && (
        <div className="rounded-lg border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
          <h4 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">
            {t.p3ScenarioRepricing}
          </h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--color-border)] text-left text-[11px] uppercase tracking-widest text-[var(--color-muted)]">
                  <th className="py-2 pr-3">{t.scenario}</th>
                  <th className="py-2 pr-3 text-right">{t.baseNpv}</th>
                  <th className="py-2 pr-3 text-right">{t.p3Npv}</th>
                  <th className="py-2 pr-3 text-right">{t.npvDelta}</th>
                  <th className="py-2 text-right">{t.p3Irr}</th>
                </tr>
              </thead>
              <tbody>
                {scenarioComparisonRows.map((row) => (
                  <tr key={row.scenario_name} className="border-b border-[var(--color-border)]/70">
                    <td className="py-3 pr-3 font-semibold">{row.scenario_name}</td>
                    <td className="py-3 pr-3 text-right font-mono">{fmt(row.base_npv)}</td>
                    <td className="py-3 pr-3 text-right font-mono">{fmt(row.adjusted_npv)}</td>
                    <td
                      className="py-3 pr-3 text-right font-mono"
                      style={{ color: (row.delta_npv ?? 0) >= 0 ? 'var(--color-positive)' : 'var(--color-negative)' }}
                    >
                      {fmt(row.delta_npv)}
                    </td>
                    <td className="py-3 text-right font-mono">{formatPercentageValue(row.adjusted_irr)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}
