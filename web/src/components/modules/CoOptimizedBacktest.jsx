/**
 * CoOptimizedBacktest — 联合优化回测
 *
 * 使用 LP/MILP 联合优化能量套利与 FCAS 调度，展示分项收入。
 * 支持 NEM 和 WEM。
 * Requirements: 6.1, 6.3, 6.5
 */

import { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '联合优化回测',
    subtitle: '能量套利 + FCAS 联合优化调度结果',
    energyRevenue: '能量收入',
    fcasRevenue: 'FCAS 收入',
    totalRevenue: '总收入',
    uplift: '联合优化增量',
    optimalityGap: '最优性间隙',
    status: '求解状态',
    monthlyBreakdown: '月度收入分解',
    bindingConstraints: '约束绑定报告',
    constraint: '约束',
    bindingPct: '绑定比例',
    timeoutWarning: '求解超时，当前为可行解（非最优解）',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    month: '月份',
    energy: '能量',
    fcas: 'FCAS',
    modeFast: '快速模式',
    modePrecise: '精确模式',
    modeFastDesc: '30分钟间隔 · 约6秒',
    modePreciseDesc: '5分钟间隔 · 约60-90秒',
    loadingFast: '正在使用30分钟精度快速求解...',
    loadingPrecise: '正在使用5分钟精度求解，预计需要60-90秒，请耐心等待...',
    resolutionLabel: '求解精度',
    resolutionFast: '30分钟间隔（快速）',
    resolutionPrecise: '5分钟间隔（精确）',
  },
  en: {
    title: 'Co-Optimized Backtest',
    subtitle: 'Joint energy arbitrage + FCAS dispatch optimization',
    energyRevenue: 'Energy Revenue',
    fcasRevenue: 'FCAS Revenue',
    totalRevenue: 'Total Revenue',
    uplift: 'Co-Opt Uplift',
    optimalityGap: 'Optimality Gap',
    status: 'Solver Status',
    monthlyBreakdown: 'Monthly Revenue Breakdown',
    bindingConstraints: 'Binding Constraints Report',
    constraint: 'Constraint',
    bindingPct: 'Binding %',
    timeoutWarning: 'Solver timed out — showing feasible (non-optimal) solution',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    month: 'Month',
    energy: 'Energy',
    fcas: 'FCAS',
    modeFast: 'Fast Mode',
    modePrecise: 'Precise Mode',
    modeFastDesc: '30-min intervals · ~6s',
    modePreciseDesc: '5-min intervals · ~60-90s',
    loadingFast: 'Solving with 30-min resolution...',
    loadingPrecise: 'Solving with 5-min resolution, estimated 60-90 seconds. Please wait...',
    resolutionLabel: 'Resolution',
    resolutionFast: '30-min intervals (fast)',
    resolutionPrecise: '5-min intervals (precise)',
  },
};

export default function CoOptimizedBacktest({ config, lang = 'zh' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [errorMsg, setErrorMsg] = useState(null);
  const [mode, setMode] = useState('fast'); // 'fast' | 'precise'

  const market = filters.market;
  const region = filters.region;
  const year = filters.year;

  useEffect(() => {
    if (!region || !year) return;
    setLoading(true);
    setError(false);
    // Request month 1 as fallback since current month may not have data yet
    // For the selected year, use month=1 which is most likely to have data
    const requestMonth = 1;
    const controller = new AbortController();
    const timeLimitSeconds = mode === 'precise' ? 90 : 10;
    fetchJson(`${API_BASE}/v1/co-optimization/backtest`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market,
        region,
        year,
        month: requestMonth,
        power_mw: 100,
        duration_hours: 4,
        time_limit_seconds: timeLimitSeconds,
        resolution: mode,
      }),
      signal: controller.signal,
    })
      .then((res) => { setData(res); setLoading(false); })
      .catch((err) => {
        // 忽略被取消的请求（组件卸载或依赖变化导致的 abort）
        if (err?.name === 'AbortError') return;
        // 区分 404（无数据）和其他错误
        if (err?.message?.includes('404') || err?.status === 404) {
          setErrorMsg(lang === 'zh'
            ? `${year} 年 ${region} 区域暂无价格数据，无法执行联合优化回测`
            : `No price data available for ${region} in ${year}. Co-optimization backtest requires historical price data.`);
        } else {
          setErrorMsg(null);
        }
        setError(true);
        setLoading(false);
      });
    return () => controller.abort();
  }, [market, region, year, mode]);

  if (loading) {
    const loadingText = mode === 'precise' ? t.loadingPrecise : t.loadingFast;
    return <div className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">{loadingText}</div>;
  }
  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)] text-center text-sm px-4">{errorMsg || t.error}</span>
        <button onClick={() => { setError(false); setErrorMsg(null); }} className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]">{t.retry}</button>
      </div>
    );
  }
  if (!data) return null;

  // 无数据降级：后端返回 infeasible + solver_status 说明原因
  if (data.status === 'infeasible' && data.solver_status) {
    return (
      <div className="mt-3">
        <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
        <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>
        <div className="h-32 flex items-center justify-center text-[var(--color-muted)] text-sm text-center px-4">
          {data.solver_status}
        </div>
      </div>
    );
  }

  const isFeasible = data.status === 'feasible' || data.status === 'timeout';
  const monthly = data.monthly_breakdown || [];
  const bindings = data.binding_constraints || [];
  const fmtK = (v) => `$${((v || 0) / 1000).toFixed(0)}k`;

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Mode toggle buttons */}
      <div className="flex items-center gap-2 mb-4">
        <button
          onClick={() => setMode('fast')}
          className={`px-3 py-1.5 text-xs rounded border transition-colors ${
            mode === 'fast'
              ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-text)]'
              : 'border-[var(--color-border)] hover:border-[var(--color-text)]'
          }`}
        >
          {t.modeFast}
          <span className="ml-1 opacity-70">({t.modeFastDesc})</span>
        </button>
        <button
          onClick={() => setMode('precise')}
          className={`px-3 py-1.5 text-xs rounded border transition-colors ${
            mode === 'precise'
              ? 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-text)]'
              : 'border-[var(--color-border)] hover:border-[var(--color-text)]'
          }`}
        >
          {t.modePrecise}
          <span className="ml-1 opacity-70">({t.modePreciseDesc})</span>
        </button>
      </div>

      {/* Resolution badge */}
      <div className="mb-4 text-xs text-[var(--color-muted)] font-sans">
        {t.resolutionLabel}: <span className="font-mono">{mode === 'precise' ? t.resolutionPrecise : t.resolutionFast}</span>
      </div>

      {/* Timeout warning */}
      {isFeasible && (
        <div className="mb-4 p-3 border border-[var(--color-status-timeout)]/40 bg-[var(--color-status-timeout)]/8 rounded text-xs text-[var(--color-status-timeout)]">
          ⚠️ {t.timeoutWarning} ({t.optimalityGap}: {((data.optimality_gap || 0) * 100).toFixed(1)}%)
        </div>
      )}

      {/* Revenue cards */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-6">
        <StatCard label={t.energyRevenue} value={fmtK(data.energy_revenue)} />
        <StatCard label={t.fcasRevenue} value={fmtK(data.fcas_revenue)} />
        <StatCard label={t.totalRevenue} value={fmtK(data.total_net_revenue)} accent />
        <StatCard label={t.uplift} value={fmtK(data.co_optimization_uplift)} />
        <StatCard label={t.status} value={data.status || '-'} />
      </div>

      {/* Monthly breakdown chart */}
      {monthly.length > 0 && (
        <div className="mb-6">
          <h4 className="text-sm font-serif font-bold mb-2">{t.monthlyBreakdown}</h4>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={monthly}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis dataKey="month" tick={{ fontSize: 10 }} />
              <YAxis tick={{ fontSize: 10 }} />
              <Tooltip />
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Bar dataKey="energy_revenue" name={t.energy} fill="#3b82f6" stackId="rev" />
              <Bar dataKey="fcas_revenue" name={t.fcas} fill="#8b5cf6" stackId="rev" />
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Binding constraints */}
      {bindings.length > 0 && (
        <div>
          <h4 className="text-sm font-serif font-bold mb-2">{t.bindingConstraints}</h4>
          <div className="overflow-x-auto">
            <table className="w-full text-sm font-sans border-collapse">
              <thead>
                <tr className="border-b-2 border-[var(--color-text)]">
                  <th className="text-left py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.constraint}</th>
                  <th className="text-right py-2 px-2 text-xs tracking-widest uppercase text-[var(--color-muted)]">{t.bindingPct}</th>
                </tr>
              </thead>
              <tbody>
                {bindings.map((b, i) => (
                  <tr key={i} className="border-b border-[var(--color-border)]">
                    <td className="py-2 px-2 font-mono text-xs">{b.constraint || b.name}</td>
                    <td className="text-right py-2 px-2 font-mono text-xs">{((b.binding_pct || b.ratio || 0) * 100).toFixed(1)}%</td>
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

function StatCard({ label, value, accent = false }) {
  return (
    <div className={`border p-3 rounded ${accent ? 'border-[var(--color-text)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]' : 'border-[var(--color-border)]'}`}>
      <div className={`text-xs tracking-widest uppercase mb-1 ${accent ? 'opacity-70' : 'text-[var(--color-muted)]'}`}>{label}</div>
      <div className="text-lg font-mono font-bold">{value}</div>
    </div>
  );
}
