/**
 * MerchantRiskQuantifier — 商户风险量化器
 *
 * 基于蒙特卡洛模拟生成收入概率分布（P10/P50/P90），
 * 计算满足银行融资门槛所需的最低合约覆盖率。
 * 支持可调 DSCR 和银行合约要求比例滑块。
 * Requirements: 4.1, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8, 6.4
 */

import { useEffect, useState } from 'react';
import {
  Bar, BarChart, CartesianGrid, ReferenceLine,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '商户风险量化器',
    subtitle: '蒙特卡洛模拟收入分布与合约覆盖率分析',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    histogram: '收入分布直方图 (AUD/MW/年)',
    frequency: '频率',
    revenue: '收入 ($/MW/年)',
    contractPanel: '合约覆盖率计算',
    dscr: '债务偿还覆盖率 (DSCR)',
    bankPct: '银行合约要求比例',
    minCoverage: '最低合约覆盖率',
    contractNeeded: '合约收入需求',
    bankability: '银行融资可行性',
    bankabilityMet: '满足',
    bankabilityNotMet: '不满足',
    historicalRange: '历史实际收入范围',
    historicalMin: '最低',
    historicalMax: '最高',
    yearsUsed: '使用年份',
    dataWarning: '统计代表性警告',
    conclusion: '合约策略建议',
    simulations: '模拟次数',
    p10: 'P10',
    p50: 'P50',
    p90: 'P90',
  },
  en: {
    title: 'Merchant Risk Quantifier',
    subtitle: 'Monte Carlo revenue distribution & contract coverage analysis',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    histogram: 'Revenue Distribution Histogram (AUD/MW/yr)',
    frequency: 'Frequency',
    revenue: 'Revenue ($/MW/yr)',
    contractPanel: 'Contract Coverage Calculation',
    dscr: 'Debt Service Coverage Ratio (DSCR)',
    bankPct: 'Bank Contract Requirement',
    minCoverage: 'Min Contract Coverage',
    contractNeeded: 'Contract Revenue Needed',
    bankability: 'Bankability',
    bankabilityMet: 'Met',
    bankabilityNotMet: 'Not Met',
    historicalRange: 'Historical Revenue Range',
    historicalMin: 'Min',
    historicalMax: 'Max',
    yearsUsed: 'Years Used',
    dataWarning: 'Statistical Representativeness Warning',
    conclusion: 'Contract Strategy Recommendation',
    simulations: 'Simulations',
    p10: 'P10',
    p50: 'P50',
    p90: 'P90',
  },
};

export default function MerchantRiskQuantifier({ config, lang = 'en' }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [dscr, setDscr] = useState(1.3);
  const [bankContractPct, setBankContractPct] = useState(0.7);

  const market = filters.market;
  const region = filters.region;

  useEffect(() => {
    setLoading(true);
    setError(false);
    fetchJson(`${API_BASE}/v1/outlook/merchant-risk`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        market,
        region,
        dscr,
        bank_contract_pct: bankContractPct,
      }),
    })
      .then((res) => { setData(res); setLoading(false); })
      .catch(() => { setError(true); setLoading(false); });
  }, [market, region, dscr, bankContractPct]);

  if (loading) {
    return <div className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">{t.loading}</div>;
  }
  if (error) {
    return (
      <div className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button onClick={() => setError(false)} className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]">{t.retry}</button>
      </div>
    );
  }
  if (!data) return null;

  const distribution = data.distribution || {};
  const histogramBins = data.histogram_bins || [];
  const historicalRange = data.historical_revenue_range || {};
  const marketExamples = data.market_examples || [];

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Data warning */}
      {data.data_warning && (
        <div className="mb-4 p-3 rounded border border-[var(--color-status-timeout)]/50 bg-[var(--color-status-timeout)]/8">
          <p className="text-sm font-sans text-[var(--color-status-timeout)]">
            ⚠️ {t.dataWarning}: {data.data_warning}
          </p>
        </div>
      )}

      {/* Revenue Distribution Histogram */}
      <div className="mb-6">
        <h4 className="text-sm font-serif font-bold mb-2">{t.histogram}</h4>
        <p className="text-xs text-[var(--color-muted)] mb-2">
          {t.simulations}: {data.n_simulations?.toLocaleString()} | {t.p10}: ${(distribution.p10 / 1000).toFixed(0)}k | {t.p50}: ${(distribution.p50 / 1000).toFixed(0)}k | {t.p90}: ${(distribution.p90 / 1000).toFixed(0)}k
        </p>
        <ResponsiveContainer width="100%" height={240}>
          <BarChart data={histogramBins} margin={{ top: 10, right: 20, left: 10, bottom: 5 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="bin_start"
              tick={{ fontSize: 10 }}
              tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
              label={{ value: t.revenue, fontSize: 10, position: 'bottom', offset: 0 }}
            />
            <YAxis
              dataKey="frequency"
              tick={{ fontSize: 10 }}
              tickFormatter={(v) => `${(v * 100).toFixed(0)}%`}
              label={{ value: t.frequency, fontSize: 10, angle: -90, position: 'insideLeft' }}
            />
            <Tooltip
              formatter={(value) => [`${(value * 100).toFixed(1)}%`, t.frequency]}
              labelFormatter={(v) => `$${(v / 1000).toFixed(0)}k/MW/yr`}
            />
            <Bar dataKey="frequency" fill="#6366f1" fillOpacity={0.7} />
            {/* P10 reference line */}
            <ReferenceLine
              x={distribution.p10}
              stroke="#ef4444"
              strokeWidth={2}
              strokeDasharray="4 4"
              label={{ value: 'P10', position: 'top', fontSize: 11, fill: '#ef4444' }}
            />
            {/* P50 reference line */}
            <ReferenceLine
              x={distribution.p50}
              stroke="#f59e0b"
              strokeWidth={2}
              strokeDasharray="4 4"
              label={{ value: 'P50', position: 'top', fontSize: 11, fill: '#f59e0b' }}
            />
            {/* P90 reference line */}
            <ReferenceLine
              x={distribution.p90}
              stroke="#10b981"
              strokeWidth={2}
              strokeDasharray="4 4"
              label={{ value: 'P90', position: 'top', fontSize: 11, fill: '#10b981' }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Contract Coverage Panel + Historical Range */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-6 mb-6">
        {/* Contract Coverage Calculation Panel */}
        <div className="p-4 border border-[var(--color-border)] rounded">
          <h4 className="text-sm font-serif font-bold mb-3">{t.contractPanel}</h4>

          {/* DSCR Slider */}
          <div className="mb-4">
            <div className="flex justify-between items-center mb-1">
              <label className="text-xs font-sans text-[var(--color-muted)]">{t.dscr}</label>
              <span className="text-xs font-mono font-bold">{dscr.toFixed(2)}x</span>
            </div>
            <input
              type="range"
              min="1.0"
              max="2.0"
              step="0.05"
              value={dscr}
              onChange={(e) => setDscr(parseFloat(e.target.value))}
              className="w-full h-1.5 rounded-lg appearance-none cursor-pointer bg-[var(--color-border)]"
            />
            <div className="flex justify-between text-xs text-[var(--color-muted)] mt-0.5">
              <span>1.0x</span>
              <span>2.0x</span>
            </div>
          </div>

          {/* Bank Contract Percentage Slider */}
          <div className="mb-4">
            <div className="flex justify-between items-center mb-1">
              <label className="text-xs font-sans text-[var(--color-muted)]">{t.bankPct}</label>
              <span className="text-xs font-mono font-bold">{(bankContractPct * 100).toFixed(0)}%</span>
            </div>
            <input
              type="range"
              min="0.5"
              max="0.9"
              step="0.05"
              value={bankContractPct}
              onChange={(e) => setBankContractPct(parseFloat(e.target.value))}
              className="w-full h-1.5 rounded-lg appearance-none cursor-pointer bg-[var(--color-border)]"
            />
            <div className="flex justify-between text-xs text-[var(--color-muted)] mt-0.5">
              <span>50%</span>
              <span>90%</span>
            </div>
          </div>

          {/* Results */}
          <div className="space-y-2 pt-2 border-t border-[var(--color-border)]">
            <div className="flex justify-between text-xs font-sans">
              <span className="text-[var(--color-muted)]">{t.minCoverage}</span>
              <span className="font-mono font-bold">{data.min_contract_coverage_pct?.toFixed(1)}%</span>
            </div>
            <div className="flex justify-between text-xs font-sans">
              <span className="text-[var(--color-muted)]">{t.contractNeeded}</span>
              <span className="font-mono font-bold">${(data.contract_revenue_needed / 1000).toFixed(0)}k/MW/yr</span>
            </div>
            <div className="flex justify-between text-xs font-sans">
              <span className="text-[var(--color-muted)]">{t.bankability}</span>
              <span className={`font-mono font-bold ${data.bankability_met ? 'text-[var(--color-status-success)]' : 'text-red-500'}`}>
                {data.bankability_met ? t.bankabilityMet : t.bankabilityNotMet}
              </span>
            </div>
          </div>
        </div>

        {/* Historical Revenue Range */}
        <div className="p-4 border border-[var(--color-border)] rounded">
          <h4 className="text-sm font-serif font-bold mb-3">{t.historicalRange}</h4>

          {/* Range bar visualization */}
          <div className="mb-4">
            <div className="relative h-8 bg-[var(--color-border)] rounded overflow-hidden">
              {historicalRange.min != null && historicalRange.max != null && historicalRange.max > 0 && (
                <div
                  className="absolute top-0 h-full bg-indigo-500/30 border-l-2 border-r-2 border-indigo-500"
                  style={{
                    left: `${(historicalRange.min / (historicalRange.max * 1.2)) * 100}%`,
                    width: `${((historicalRange.max - historicalRange.min) / (historicalRange.max * 1.2)) * 100}%`,
                  }}
                />
              )}
            </div>
            <div className="flex justify-between text-xs font-mono text-[var(--color-muted)] mt-1">
              <span>${(historicalRange.min / 1000).toFixed(0)}k</span>
              <span>${(historicalRange.max / 1000).toFixed(0)}k</span>
            </div>
          </div>

          <div className="space-y-2">
            <div className="flex justify-between text-xs font-sans">
              <span className="text-[var(--color-muted)]">{t.historicalMin}</span>
              <span className="font-mono">${(historicalRange.min / 1000).toFixed(0)}k/MW/yr</span>
            </div>
            <div className="flex justify-between text-xs font-sans">
              <span className="text-[var(--color-muted)]">{t.historicalMax}</span>
              <span className="font-mono">${(historicalRange.max / 1000).toFixed(0)}k/MW/yr</span>
            </div>
            <div className="flex justify-between text-xs font-sans">
              <span className="text-[var(--color-muted)]">{t.yearsUsed}</span>
              <span className="font-mono">{(historicalRange.years_used || []).join(', ') || '—'}</span>
            </div>
          </div>

          {/* Market examples */}
          {marketExamples.length > 0 && (
            <div className="mt-3 pt-3 border-t border-[var(--color-border)]">
              {marketExamples.map((ex, i) => (
                <p key={i} className="text-xs text-[var(--color-muted)] italic mb-1">
                  📊 {ex.description} ({ex.data_year}, {ex.label})
                </p>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Conclusion */}
      <div className="p-4 border-t-2 border-[var(--color-text)]">
        <h4 className="text-sm font-serif font-bold mb-2">{t.conclusion}</h4>
        <p className="text-sm font-sans whitespace-pre-line leading-relaxed">{data.conclusion}</p>
      </div>
    </div>
  );
}
