/**
 * DecisionSummaryPanel — 投资决策总结面板
 * - Go/No-Go 推荐（基于 NPV > 0 且 IRR > discount_rate）
 * - 3 个信号灯：财务可行性（NPV）、回报率（IRR vs hurdle）、融资可行性（DSCR > 1.3）
 * - 关键风险列表（从 regime_compact 和 monte_carlo 提取）
 * - "下一步行动"建议
 */

import { useMemo } from 'react';
import { fmt } from '../../lib/formatters';

const LABELS = {
  zh: {
    goRecommend: '✓ 建议推进 (GO)',
    noGoRecommend: '✗ 暂不推荐 (NO-GO)',
    basisPrefix: '基于 NPV',
    basisIrr: '且 IRR',
    basisHurdle: 'vs 门槛',
    financialViability: '财务可行性',
    returnRate: '回报率',
    financingViability: '融资可行性',
    hurdle: '门槛',
    threshold: '门槛',
    keyRisks: '关键风险',
    nextSteps: '下一步行动',
    p3AdjustedTitle: 'P3 决策调整后指标',
    risks: {
      p90Negative: (val) => `P90 (保守) NPV 为负 (${val})，下行风险显著`,
      highDispersion: 'NPV 分布离散度高，收益不确定性大',
      oversupply: '市场处于供给过剩状态，价差可能收窄',
      congestion: '网络拥塞风险，收入受节点位置影响',
      regimeShift: (hint) => `市场状态可能转变: ${hint}`,
      dscrLow: (val) => `DSCR (${val}x) 低于 1.3x 融资门槛`,
    },
    nextStepMessages: {
      goAndFinanced: '建议进入详细尽调阶段，确认技术方案和融资条款。',
      goNotFinanced: '财务指标达标但融资结构需优化，建议调整杠杆比例或寻求更优债务条款。',
      npvPositiveIrrLow: '项目 NPV 为正但 IRR 未达门槛，建议重新评估折现率假设或优化成本结构。',
      noGo: '当前假设下项目不具备投资可行性，建议重新评估关键假设（CAPEX、收入预期、融资成本）。',
    },
  },
  en: {
    goRecommend: '✓ Recommend GO',
    noGoRecommend: '✗ NO-GO Recommended',
    basisPrefix: 'Based on NPV',
    basisIrr: 'and IRR',
    basisHurdle: 'vs hurdle',
    financialViability: 'Financial Viability',
    returnRate: 'Return Rate',
    financingViability: 'Financing Viability',
    hurdle: 'Hurdle',
    threshold: 'Threshold',
    keyRisks: 'Key Risks',
    nextSteps: 'Next Steps',
    p3AdjustedTitle: 'P3 Decision-Adjusted Metrics',
    risks: {
      p90Negative: (val) => `P90 (conservative) NPV is negative (${val}), significant downside risk`,
      highDispersion: 'High NPV dispersion indicates significant return uncertainty',
      oversupply: 'Market in oversupply, spreads may compress',
      congestion: 'Network congestion risk, revenue depends on node location',
      regimeShift: (hint) => `Market regime may shift: ${hint}`,
      dscrLow: (val) => `DSCR (${val}x) below 1.3x financing threshold`,
    },
    nextStepMessages: {
      goAndFinanced: 'Recommend proceeding to detailed due diligence, confirming technical solution and financing terms.',
      goNotFinanced: 'Financial metrics pass but financing structure needs optimization. Consider adjusting leverage or seeking better debt terms.',
      npvPositiveIrrLow: 'Project NPV is positive but IRR below hurdle. Recommend reassessing discount rate assumptions or optimizing cost structure.',
      noGo: 'Project not viable under current assumptions. Recommend reassessing key assumptions (CAPEX, revenue expectations, financing costs).',
    },
  },
};

// 主题状态 token：暗色下自动提亮（2026-08-10）
const SIGNAL_COLORS = {
  green: 'var(--color-status-success)',
  yellow: 'var(--color-status-timeout)',
  red: 'var(--color-status-error)',
};

function SignalLight({ color, label, detail }) {
  return (
    <div className="flex items-start gap-3 rounded border border-[var(--color-border)] p-3">
      <div
        className="mt-0.5 h-4 w-4 shrink-0 rounded-full"
        style={{ backgroundColor: SIGNAL_COLORS[color] || SIGNAL_COLORS.yellow }}
      />
      <div>
        <div className="text-sm font-semibold">{label}</div>
        <div className="text-xs text-[var(--color-muted)]">{detail}</div>
      </div>
    </div>
  );
}

export default function DecisionSummaryPanel({ metrics, params, mc, regimeCompact, lang = 'zh' }) {
  const t = LABELS[lang] || LABELS.zh;
  const npv = metrics?.npv ?? null;
  const irr = metrics?.irr ?? null;
  const dscrAvg = metrics?.dscr_avg ?? null;
  const discountRate = params?.discount_rate ?? 0.08;
  const hurdleRate = discountRate * 100; // IRR is in percentage

  // Go/No-Go 判断
  const isGoDecision = npv > 0 && irr > hurdleRate;

  // 信号灯
  const signals = useMemo(() => {
    const npvSignal = npv > 0 ? 'green' : npv === null ? 'yellow' : 'red';
    const irrSignal = irr > hurdleRate ? 'green' : irr > hurdleRate * 0.8 ? 'yellow' : 'red';
    const dscrSignal = dscrAvg > 1.3 ? 'green' : dscrAvg > 1.1 ? 'yellow' : dscrAvg === null ? 'yellow' : 'red';

    return { npvSignal, irrSignal, dscrSignal };
  }, [npv, irr, hurdleRate, dscrAvg]);

  // 关键风险提取
  const risks = useMemo(() => {
    const riskList = [];

    // 从 Monte Carlo 提取风险
    if (mc) {
      if (mc.npv_p90 != null && mc.npv_p90 < 0) {
        riskList.push(t.risks.p90Negative(fmt(mc.npv_p90)));
      }
      const spread = mc.npv_p10 != null && mc.npv_p90 != null ? mc.npv_p10 - mc.npv_p90 : 0;
      if (spread > Math.abs(mc.npv_p50 || 1) * 2) {
        riskList.push(t.risks.highDispersion);
      }
    }

    // 从 regime_compact 提取风险
    if (regimeCompact) {
      const regime = regimeCompact.primary_regime?.regime;
      if (regime === 'oversupply') {
        riskList.push(t.risks.oversupply);
      }
      if (regime === 'congestion') {
        riskList.push(t.risks.congestion);
      }
      if (regimeCompact.transition_hints?.length > 0) {
        riskList.push(t.risks.regimeShift(regimeCompact.transition_hints[0]));
      }
    }

    // DSCR 风险
    if (dscrAvg != null && dscrAvg < 1.3) {
      riskList.push(t.risks.dscrLow(dscrAvg.toFixed(2)));
    }

    return riskList;
  }, [mc, regimeCompact, dscrAvg, t]);

  // 下一步行动建议
  const nextSteps = useMemo(() => {
    if (isGoDecision && signals.dscrSignal === 'green') {
      return t.nextStepMessages.goAndFinanced;
    }
    if (isGoDecision && signals.dscrSignal !== 'green') {
      return t.nextStepMessages.goNotFinanced;
    }
    if (npv > 0 && irr <= hurdleRate) {
      return t.nextStepMessages.npvPositiveIrrLow;
    }
    return t.nextStepMessages.noGo;
  }, [isGoDecision, signals, npv, irr, hurdleRate, t]);

  return (
    <div className="rounded-lg border-2 border-[var(--color-border)] p-5">
      {/* Go/No-Go 推荐 */}
      <div className="mb-5 flex items-center gap-3">
        <div
          className="rounded-full px-4 py-2 text-sm font-bold text-white"
          style={{ backgroundColor: isGoDecision ? SIGNAL_COLORS.green : SIGNAL_COLORS.red }}
        >
          {isGoDecision ? t.goRecommend : t.noGoRecommend}
        </div>
        <div className="text-xs text-[var(--color-muted)]">
          {`${t.basisPrefix} ${npv != null ? (npv > 0 ? '> 0' : '≤ 0') : 'N/A'} ${t.basisIrr} ${irr != null ? `${irr.toFixed(1)}%` : 'N/A'} ${t.basisHurdle} ${hurdleRate.toFixed(1)}%`}
        </div>
      </div>

      {/* 3 个信号灯 */}
      <div className="mb-5 grid grid-cols-1 gap-3 md:grid-cols-3">
        <SignalLight
          color={signals.npvSignal}
          label={t.financialViability}
          detail={`NPV: ${npv != null ? fmt(npv) : 'N/A'}`}
        />
        <SignalLight
          color={signals.irrSignal}
          label={t.returnRate}
          detail={`IRR: ${irr != null ? `${irr.toFixed(1)}%` : 'N/A'} / ${t.hurdle}: ${hurdleRate.toFixed(1)}%`}
        />
        <SignalLight
          color={signals.dscrSignal}
          label={t.financingViability}
          detail={`DSCR: ${dscrAvg != null ? `${dscrAvg.toFixed(2)}x` : 'N/A'} / ${t.threshold}: 1.30x`}
        />
      </div>

      {/* 关键风险 */}
      {risks.length > 0 && (
        <div className="mb-5">
          <div className="mb-2 text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {t.keyRisks}
          </div>
          <ul className="space-y-1 text-sm text-[var(--color-text)]">
            {risks.map((risk, i) => (
              <li key={i} className="flex items-start gap-2">
                <span className="mt-1 text-[var(--color-negative)]">•</span>
                <span>{risk}</span>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* 下一步行动 */}
      <div className="rounded border border-[var(--color-border)] bg-[var(--color-bg)] p-3">
        <div className="mb-1 text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
          {t.nextSteps}
        </div>
        <div className="text-sm leading-relaxed">{nextSteps}</div>
      </div>
    </div>
  );
}
