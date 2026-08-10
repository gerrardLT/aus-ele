/**
 * MonteCarloPanel — Monte Carlo 结果面板 + NPV 分布直方图
 * 使用 Recharts BarChart 展示 NPV 分布
 * 标注 P10、P50、P90 的垂直参考线
 * 如果后端没有返回 histogram 数据，前端用 P10/P50/P90 生成近似正态分布
 */

import { useMemo } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { SummaryBlock } from './KpiCard';
import { fmt } from '../../lib/formatters';

const LABELS = {
  zh: {
    baselineDistribution: '基线分布',
    p3AdjustedDistribution: 'P3 调整后分布',
    histogramTitle: 'NPV 分布直方图',
    frequency: '频率',
  },
  en: {
    baselineDistribution: 'Baseline Distribution',
    p3AdjustedDistribution: 'P3-Adjusted Distribution',
    histogramTitle: 'NPV Distribution Histogram',
    frequency: 'Frequency',
  },
};

/**
 * 用 P10/P50/P90 生成近似正态分布的 histogram bins
 * 假设正态分布: P50 = mean, (P90 - P10) / 2.56 ≈ std
 */
function generateApproximateHistogram(p10, p50, p90, binCount = 20) {
  if (p10 == null || p50 == null || p90 == null) return [];

  const mean = p50;
  // P10 is upside (higher), P90 is downside (lower) in this convention
  const std = Math.abs(p10 - p90) / 2.56;
  if (std === 0) return [];

  const minVal = mean - 3 * std;
  const maxVal = mean + 3 * std;
  const binWidth = (maxVal - minVal) / binCount;

  const bins = [];
  for (let i = 0; i < binCount; i++) {
    const binStart = minVal + i * binWidth;
    const binCenter = binStart + binWidth / 2;
    // Normal PDF approximation
    const z = (binCenter - mean) / std;
    const frequency = Math.exp(-0.5 * z * z) / (std * Math.sqrt(2 * Math.PI));
    bins.push({
      binStart,
      binCenter,
      binEnd: binStart + binWidth,
      frequency: Math.round(frequency * 1000), // scale for display
      label: fmt(binCenter),
    });
  }
  return bins;
}

export default function MonteCarloPanel({ mc, decisionAdjustedMonteCarlo, copy, lang = 'zh' }) {
  const t = LABELS[lang] || LABELS.zh;

  const histogramData = useMemo(() => {
    if (!mc) return [];
    // 如果后端返回了 histogram 数据，直接使用
    if (mc.histogram && Array.isArray(mc.histogram) && mc.histogram.length > 0) {
      return mc.histogram.map((bin) => ({
        ...bin,
        label: fmt(bin.binCenter || bin.bin_center),
      }));
    }
    // 否则用 P10/P50/P90 生成近似分布
    return generateApproximateHistogram(mc.npv_p10, mc.npv_p50, mc.npv_p90);
  }, [mc]);

  if (!mc) return null;

  return (
    <div className="rounded-lg border border-[var(--color-border)] p-4 bg-[var(--color-surface)]">
      <h4 className="mb-3 text-sm font-bold uppercase tracking-wider text-[var(--color-primary)]">
        {copy.monteCarloToggle}
      </h4>

      <div className={`grid grid-cols-1 gap-4 ${decisionAdjustedMonteCarlo ? 'xl:grid-cols-2' : ''}`}>
        <div>
          <div className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {t.baselineDistribution}
          </div>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <SummaryBlock label={copy.monteCarloLabels.p90} value={fmt(mc.npv_p90)} />
            <SummaryBlock label={copy.monteCarloLabels.p50} value={fmt(mc.npv_p50)} />
            <SummaryBlock label={copy.monteCarloLabels.p10} value={fmt(mc.npv_p10)} />
          </div>
        </div>
        {decisionAdjustedMonteCarlo && (
          <div>
            <div className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[var(--color-primary)]">
              {t.p3AdjustedDistribution}
            </div>
            <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
              <SummaryBlock label={copy.monteCarloLabels.p90} value={fmt(decisionAdjustedMonteCarlo.npv_p90)} />
              <SummaryBlock label={copy.monteCarloLabels.p50} value={fmt(decisionAdjustedMonteCarlo.npv_p50)} />
              <SummaryBlock label={copy.monteCarloLabels.p10} value={fmt(decisionAdjustedMonteCarlo.npv_p10)} />
            </div>
          </div>
        )}
      </div>

      {/* NPV 分布直方图 */}
      {histogramData.length > 0 && (
        <div className="mt-6">
          <div className="mb-3 text-[11px] font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {t.histogramTitle}
          </div>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={histogramData} margin={{ top: 10, right: 20, left: 20, bottom: 5 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
              <XAxis
                dataKey="binCenter"
                tickFormatter={(v) => fmt(v)}
                tick={{ fontSize: 10 }}
                interval="preserveStartEnd"
              />
              <YAxis
                tick={{ fontSize: 10 }}
                label={{ value: t.frequency, angle: -90, position: 'insideLeft', style: { fontSize: 11 } }}
              />
              <Tooltip
                formatter={(value) => [value, t.frequency]}
                labelFormatter={(v) => `NPV: ${fmt(v)}`}
                contentStyle={{
                  backgroundColor: 'var(--color-bg)',
                  border: '1px solid var(--color-border)',
                  fontSize: 12,
                }}
              />
              <Bar dataKey="frequency" fill="var(--color-primary)" opacity={0.7} />
              {/* P10 参考线（主题 token，暗色下自动提亮） */}
              {mc.npv_p10 != null && (
                <ReferenceLine
                  x={mc.npv_p10}
                  stroke="var(--color-positive)"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  label={{ value: 'P10', position: 'top', fill: 'var(--color-positive)', fontSize: 11 }}
                />
              )}
              {/* P50 参考线 */}
              {mc.npv_p50 != null && (
                <ReferenceLine
                  x={mc.npv_p50}
                  stroke="var(--color-primary)"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  label={{ value: 'P50', position: 'top', fill: 'var(--color-primary)', fontSize: 11 }}
                />
              )}
              {/* P90 参考线 */}
              {mc.npv_p90 != null && (
                <ReferenceLine
                  x={mc.npv_p90}
                  stroke="var(--color-negative)"
                  strokeWidth={2}
                  strokeDasharray="4 4"
                  label={{ value: 'P90', position: 'top', fill: 'var(--color-negative)', fontSize: 11 }}
                />
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  );
}
