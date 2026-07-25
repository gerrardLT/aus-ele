/**
 * DecisionTerminal — U3: 投资决策终端面板
 *
 * 汇总全链路分析结论，输出 GO/NO-GO/WAIT 建议 + 置信度 + 关键风险。
 * 消费 investment-analysis 响应中的 decision_terminal 字段。
 */

import { useEffect, useState } from 'react';
import { motion } from 'framer-motion';
import { AlertTriangle, CheckCircle2, Clock, XCircle, TrendingUp, Shield } from 'lucide-react';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const REC_CONFIG = {
  GO: { icon: CheckCircle2, color: '#22C55E', label: { zh: '建议投资', en: 'GO' }, pulse: true },
  NO_GO: { icon: XCircle, color: '#EF4444', label: { zh: '不建议', en: 'NO-GO' }, pulse: false },
  WAIT: { icon: Clock, color: '#F59E0B', label: { zh: '观望', en: 'WAIT' }, pulse: true },
};

const RISK_ICONS = {
  irr_thin_margin: TrendingUp,
  payback_exceeds_tenor: Clock,
  dscr_tight: Shield,
  cannibalization_high: AlertTriangle,
  llcr_low: Shield,
};

export default function DecisionTerminal({ lang = 'zh', region, year }) {
  const { filters } = useFilters();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    const r = region || filters.region;
    if (!r) return;
    setLoading(true);
    const body = {
      region: r,
      battery: { power_mw: 100, duration_hours: 4 },
      backtest_years: [year || filters.year || 2025],
    };
    fetchJson(`${API_BASE}/api/investment-analysis`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then(res => setData(res?.decision_terminal || null))
      .catch(() => setData(null))
      .finally(() => setLoading(false));
  }, [region, filters.region, year, filters.year]);

  if (loading) {
    return (
      <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-8 text-center panel-glass">
        <div className="mx-auto mb-3 h-8 w-8 animate-spin rounded-full border-4 border-[var(--color-border)] border-t-[var(--color-primary)]" />
        <p className="text-sm text-[var(--color-muted)]">
          {lang === 'zh' ? '正在生成投资决策...' : 'Generating investment decision...'}
        </p>
      </div>
    );
  }

  if (!data) return null;

  const rec = REC_CONFIG[data.recommendation] || REC_CONFIG.WAIT;
  const RecIcon = rec.icon;

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-6 panel-glass">
      {/* Recommendation badge */}
      <div className="flex items-center gap-4 mb-6">
        <motion.div
          animate={rec.pulse ? { scale: [1, 1.08, 1] } : {}}
          transition={rec.pulse ? { repeat: Infinity, duration: 2 } : {}}
          className="flex items-center justify-center w-14 h-14 rounded-full"
          style={{ backgroundColor: `${rec.color}18`, border: `2px solid ${rec.color}` }}
        >
          <RecIcon size={28} style={{ color: rec.color }} />
        </motion.div>
        <div>
          <h3 className="text-xl font-bold font-serif" style={{ color: rec.color }}>
            {rec.label[lang]}
          </h3>
          <p className="text-xs text-[var(--color-muted)] mt-0.5">
            {lang === 'zh' ? '置信度' : 'Confidence'}: {(data.confidence * 100).toFixed(0)}%
          </p>
        </div>
        {/* Confidence ring */}
        <div className="ml-auto relative w-12 h-12">
          <svg viewBox="0 0 36 36" className="w-12 h-12 -rotate-90">
            <circle cx="18" cy="18" r="15" fill="none" stroke="var(--color-border)" strokeWidth="3" />
            <circle
              cx="18" cy="18" r="15" fill="none"
              stroke={rec.color} strokeWidth="3" strokeLinecap="round"
              strokeDasharray={`${data.confidence * 94.2} 94.2`}
            />
          </svg>
        </div>
      </div>

      {/* Key metrics strip */}
      <div className="grid grid-cols-3 gap-3 mb-5">
        <div className="rounded-lg bg-[var(--color-background)] p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">NPV/MW</p>
          <p className="text-sm font-bold font-mono glow-kpi text-[var(--color-text)]">
            ${Math.round(data.npv_per_mw).toLocaleString()}
          </p>
        </div>
        <div className="rounded-lg bg-[var(--color-background)] p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">IRR vs Hurdle</p>
          <p className={`text-sm font-bold font-mono ${data.irr_vs_hurdle.margin >= 0 ? 'text-green-500' : 'text-red-500'}`}>
            {(data.irr_vs_hurdle.margin * 100).toFixed(1)}pp
          </p>
        </div>
        <div className="rounded-lg bg-[var(--color-background)] p-3 text-center">
          <p className="text-[10px] uppercase tracking-wider text-[var(--color-muted)]">
            {lang === 'zh' ? '回本/贷款期' : 'Payback/Tenor'}
          </p>
          <p className="text-sm font-bold font-mono text-[var(--color-text)]">
            {data.payback_vs_tenor.payback.toFixed(1)}/{data.payback_vs_tenor.tenor}y
          </p>
        </div>
      </div>

      {/* Key risks */}
      {data.key_risks.length > 0 && (
        <div className="space-y-2">
          <p className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
            {lang === 'zh' ? '关键风险' : 'Key Risks'}
          </p>
          {data.key_risks.map((risk, i) => {
            const RiskIcon = RISK_ICONS[risk.type] || AlertTriangle;
            return (
              <div key={i} className="flex items-start gap-2 text-xs text-[var(--color-muted)]">
                <RiskIcon size={14} className={risk.severity === 'high' ? 'text-red-500 mt-0.5' : 'text-amber-500 mt-0.5'} />
                <span>{risk.description}</span>
              </div>
            );
          })}
        </div>
      )}

      {/* Cannibalization + data completeness footer */}
      <div className="mt-4 pt-3 border-t border-[var(--color-border)] flex items-center justify-between text-[10px] text-[var(--color-muted)]">
        <span>
          {lang === 'zh' ? '蚕食风险' : 'Cannibalization'}: {data.cannibalization_exposure}
        </span>
        <span>
          {lang === 'zh' ? '数据完整度' : 'Data'}: {(data.data_completeness * 100).toFixed(0)}%
        </span>
      </div>
    </div>
  );
}
