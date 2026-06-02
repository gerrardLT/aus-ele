/**
 * RevenueStratificationChart — 收入分层堆叠面积图
 *
 * 使用 Recharts StackedAreaChart 展示 20 年收入分层数据。
 * Layer 1 蓝色（基础套利）、Layer 2 琥珀色（FCAS）、Layer 3 红色（极端事件）。
 * 悬浮显示各层金额和百分比，显示 layer-weighted NPV 与 standard NPV 对比。
 * Requirements: 3.1, 3.2, 3.3, 3.4, 3.5
 */

import { useEffect, useState } from 'react';
import {
  Area, AreaChart, CartesianGrid, Legend,
  ResponsiveContainer, Tooltip, XAxis, YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import NarrativeTooltip from './NarrativeTooltip';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LAYER_COLORS = {
  layer1: '#3b82f6', // 蓝色 - 基础套利
  layer2: '#f59e0b', // 琥珀色 - FCAS
  layer3: '#ef4444', // 红色 - 极端事件
};

const LABELS = {
  zh: {
    title: '收入风险分层',
    subtitle: '20 年收入按置信度分层堆叠面积图',
    layer1: '基础套利 (Layer 1)',
    layer2: 'FCAS 辅助服务 (Layer 2)',
    layer3: '极端事件 (Layer 3)',
    confidenceHigh: '高置信度',
    confidenceMedium: '中置信度',
    confidenceLow: '低置信度',
    discountRate: '折现率',
    layerWeightedNpv: '分层加权 NPV',
    standardNpv: '标准 NPV',
    npvDifference: 'NPV 差异',
    year: '年份',
    revenue: '收入 ($)',
    total: '合计',
    percentage: '占比',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
  },
  en: {
    title: 'Revenue Risk Stratification',
    subtitle: '20-year revenue stacked by confidence layer',
    layer1: 'Base Arbitrage (Layer 1)',
    layer2: 'FCAS Services (Layer 2)',
    layer3: 'Extreme Events (Layer 3)',
    confidenceHigh: 'High Confidence',
    confidenceMedium: 'Medium Confidence',
    confidenceLow: 'Low Confidence',
    discountRate: 'Discount Rate',
    layerWeightedNpv: 'Layer-Weighted NPV',
    standardNpv: 'Standard NPV',
    npvDifference: 'NPV Difference',
    year: 'Year',
    revenue: 'Revenue ($)',
    total: 'Total',
    percentage: 'Share',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
  },
};

export default function RevenueStratificationChart({ config, lang = 'zh', region: regionProp }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.en;
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const region = regionProp || filters.region;

  useEffect(() => {
    if (!region) return;
    let cancelled = false;
    setLoading(true);
    setError(false);
    fetchJson(`${API_BASE}/v1/narrative/stratification/${encodeURIComponent(region)}`)
      .then((res) => { if (!cancelled) { setData(res); setLoading(false); } })
      .catch(() => { if (!cancelled) { setError(true); setLoading(false); } });
    return () => { cancelled = true; };
  }, [region]);

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

  if (!data || !data.annual_layers || data.annual_layers.length === 0) return null;

  // Transform API data for Recharts
  const chartData = data.annual_layers.map((entry) => ({
    year: entry.year,
    layer1: entry.layer1?.amount ?? 0,
    layer2: entry.layer2?.amount ?? 0,
    layer3: entry.layer3?.amount ?? 0,
    layer1_pct: entry.layer1?.percentage ?? 0,
    layer2_pct: entry.layer2?.percentage ?? 0,
    layer3_pct: entry.layer3?.percentage ?? 0,
    total: entry.total_revenue ?? 0,
  }));

  const discountRates = data.discount_rates || {};

  return (
    <div className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-6">{t.subtitle}</p>

      {/* NPV comparison cards */}
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-6">
        <NpvCard
          label={t.layerWeightedNpv}
          value={data.layer_weighted_npv}
          narrativeModule="stratification_npv"
          lang={lang}
        />
        <NpvCard
          label={t.standardNpv}
          value={data.standard_npv}
        />
        <NpvCard
          label={t.npvDifference}
          value={data.npv_difference}
          highlight
        />
      </div>

      {/* Stacked Area Chart */}
      <ResponsiveContainer width="100%" height={320}>
        <AreaChart data={chartData} margin={{ top: 10, right: 20, left: 20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
          <XAxis
            dataKey="year"
            tick={{ fontSize: 10 }}
            label={{ value: t.year, position: 'insideBottom', offset: -2, fontSize: 11 }}
          />
          <YAxis
            tick={{ fontSize: 10 }}
            tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`}
            label={{ value: t.revenue, angle: -90, position: 'insideLeft', fontSize: 11 }}
          />
          <Tooltip content={<CustomTooltip t={t} />} />
          <Area
            type="monotone"
            dataKey="layer1"
            stackId="revenue"
            fill={LAYER_COLORS.layer1}
            stroke={LAYER_COLORS.layer1}
            fillOpacity={0.7}
            name={t.layer1}
          />
          <Area
            type="monotone"
            dataKey="layer2"
            stackId="revenue"
            fill={LAYER_COLORS.layer2}
            stroke={LAYER_COLORS.layer2}
            fillOpacity={0.7}
            name={t.layer2}
          />
          <Area
            type="monotone"
            dataKey="layer3"
            stackId="revenue"
            fill={LAYER_COLORS.layer3}
            stroke={LAYER_COLORS.layer3}
            fillOpacity={0.7}
            name={t.layer3}
          />
        </AreaChart>
      </ResponsiveContainer>

      {/* Legend with confidence and discount rates */}
      <div className="mt-4 grid grid-cols-1 md:grid-cols-3 gap-3">
        <LegendItem
          color={LAYER_COLORS.layer1}
          name={t.layer1}
          confidence={t.confidenceHigh}
          discountRate={discountRates.layer1}
          t={t}
        />
        <LegendItem
          color={LAYER_COLORS.layer2}
          name={t.layer2}
          confidence={t.confidenceMedium}
          discountRate={discountRates.layer2}
          t={t}
        />
        <LegendItem
          color={LAYER_COLORS.layer3}
          name={t.layer3}
          confidence={t.confidenceLow}
          discountRate={discountRates.layer3}
          t={t}
        />
      </div>
    </div>
  );
}

/** Custom tooltip showing layer amounts and percentages */
function CustomTooltip({ active, payload, label, t }) {
  if (!active || !payload || payload.length === 0) return null;

  const entry = payload[0]?.payload;
  if (!entry) return null;

  return (
    <div className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded p-3 shadow-md text-xs font-sans">
      <div className="font-serif font-bold mb-2">{t.year}: {label}</div>
      <div className="space-y-1">
        <TooltipRow color={LAYER_COLORS.layer1} name={t.layer1} amount={entry.layer1} pct={entry.layer1_pct} />
        <TooltipRow color={LAYER_COLORS.layer2} name={t.layer2} amount={entry.layer2} pct={entry.layer2_pct} />
        <TooltipRow color={LAYER_COLORS.layer3} name={t.layer3} amount={entry.layer3} pct={entry.layer3_pct} />
      </div>
      <div className="mt-2 pt-2 border-t border-[var(--color-border)] font-bold">
        {t.total}: ${entry.total.toLocaleString(undefined, { maximumFractionDigits: 0 })}
      </div>
    </div>
  );
}

function TooltipRow({ color, name, amount, pct }) {
  return (
    <div className="flex items-center justify-between gap-4">
      <div className="flex items-center gap-1.5">
        <span className="inline-block w-2.5 h-2.5 rounded-sm" style={{ backgroundColor: color }} />
        <span>{name}</span>
      </div>
      <div className="text-right font-mono">
        ${amount.toLocaleString(undefined, { maximumFractionDigits: 0 })}
        <span className="text-[var(--color-muted)] ml-1">({pct.toFixed(1)}%)</span>
      </div>
    </div>
  );
}

/** NPV comparison card */
function NpvCard({ label, value, highlight = false, narrativeModule, lang }) {
  const formatted = value != null
    ? `$${Math.abs(value).toLocaleString(undefined, { maximumFractionDigits: 0 })}${value < 0 ? ' ↓' : ''}`
    : '—';

  const valueContent = narrativeModule ? (
    <NarrativeTooltip module={narrativeModule} lang={lang}>
      <span className="text-lg font-mono font-bold">{formatted}</span>
    </NarrativeTooltip>
  ) : (
    <div className="text-lg font-mono font-bold">{formatted}</div>
  );

  return (
    <div className={`border p-3 rounded ${highlight ? 'border-[var(--color-text)] bg-[var(--color-inverted)] text-[var(--color-inverted-text)]' : 'border-[var(--color-border)]'}`}>
      <div className={`text-xs tracking-widest uppercase mb-1 ${highlight ? 'opacity-70' : 'text-[var(--color-muted)]'}`}>{label}</div>
      {valueContent}
    </div>
  );
}

/** Legend item with layer name, confidence, and discount rate */
function LegendItem({ color, name, confidence, discountRate, t }) {
  return (
    <div className="flex items-start gap-2 border border-[var(--color-border)] rounded p-2">
      <span className="inline-block w-3 h-3 rounded-sm mt-0.5 flex-shrink-0" style={{ backgroundColor: color }} />
      <div className="text-xs">
        <div className="font-serif font-bold">{name}</div>
        <div className="text-[var(--color-muted)]">{confidence}</div>
        {discountRate != null && (
          <div className="text-[var(--color-muted)]">{t.discountRate}: {(discountRate * 100).toFixed(0)}%</div>
        )}
      </div>
    </div>
  );
}
