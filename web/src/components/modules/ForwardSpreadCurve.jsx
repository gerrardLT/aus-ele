/**
 * ForwardSpreadCurve — 前瞻价差曲线组件
 *
 * 展示 20 年价差预测三情景线图 + 历史实际数据。
 * - 历史数据：黑色实线
 * - Central 情景：蓝色虚线
 * - High/Low 情景：灰色虚线 + 浅蓝色置信带
 * - 支持区域切换重新加载数据
 *
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5
 */

import { useEffect, useState } from 'react';
import {
  Area,
  CartesianGrid,
  ComposedChart,
  Legend,
  Line,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    title: '前瞻价差曲线',
    subtitle: '20 年三情景价差预测（含历史数据）',
    historical: '历史实际',
    central: 'Central 情景',
    high: 'High 情景',
    low: 'Low 情景',
    confidenceBand: '置信区间',
    spread: '价差 ($/MWh)',
    year: '年份',
    loading: '加载前瞻价差数据...',
    error: '数据加载失败',
    retry: '重试',
    noData: '暂无数据',
    noHistorical: '历史数据不可用，仅显示预测',
    directionAccuracy: '方向准确率',
    aiCalibrated: 'AI 校准',
    calibrationBadge: 'AI 校准',
    r2Label: 'R²',
    maeLabel: 'MAE',
    directionLabel: '方向准确率',
    validationTitle: '收入反推验证',
    modelRevenue: '模型收入',
    benchmark: 'Modo 基准',
    dataSource: '数据来源: Modo Energy',
    validationUnavailable: '验证数据不可用',
  },
  en: {
    title: 'Forward Spread Curve',
    subtitle: '20-year three-scenario spread projection with historical data',
    historical: 'Historical',
    central: 'Central',
    high: 'High',
    low: 'Low',
    confidenceBand: 'Confidence Band',
    spread: 'Spread ($/MWh)',
    year: 'Year',
    loading: 'Loading forward spread data...',
    error: 'Failed to load data',
    retry: 'Retry',
    noData: 'No data available',
    noHistorical: 'Historical data unavailable, showing projection only',
    directionAccuracy: 'Direction Acc.',
    aiCalibrated: 'AI Calibrated',
    calibrationBadge: 'AI Calibrated',
    r2Label: 'R²',
    maeLabel: 'MAE',
    directionLabel: 'Direction Accuracy',
    validationTitle: 'Revenue Backvalidation',
    modelRevenue: 'Model Revenue',
    benchmark: 'Modo Benchmark',
    dataSource: 'Source: Modo Energy',
    validationUnavailable: 'Validation data unavailable',
  },
};

/**
 * 偏差颜色编码：绿色(≤15%)、琥珀色(15-30%)、红色(>30%)
 */
function _getDeviationColor(deviation) {
  if (deviation == null) return 'bg-gray-100 text-gray-600';
  const abs = Math.abs(deviation);
  if (abs <= 15) return 'bg-green-100 text-green-800';
  if (abs <= 30) return 'bg-amber-100 text-amber-800';
  return 'bg-red-100 text-red-800';
}

export default function ForwardSpreadCurve({ config, lang = 'zh', region: regionProp }) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.zh;

  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);
  const [calibrationStatus, setCalibrationStatus] = useState(null);
  const [backvalidation, setBackvalidation] = useState(null);

  const region = regionProp || filters.region;

  useEffect(() => {
    if (!region) return;
    let cancelled = false;
    setLoading(true);
    setError(false);

    fetchJson(`${API_BASE}/v1/narrative/forward-spread/${region}`)
      .then((res) => {
        if (!cancelled) { setData(res); setLoading(false); }
      })
      .catch(() => {
        if (!cancelled) { setError(true); setLoading(false); }
      });

    return () => { cancelled = true; };
  }, [region]);

  // 加载校准状态（精度指标）— 仅 mount 时触发一次
  useEffect(() => {
    let cancelled = false;

    fetchJson(`${API_BASE}/v1/narrative/calibration-status`)
      .then((res) => {
        if (!cancelled) {
          if (res && res.status && res.status !== 'not_available' && res.status !== 'not_run') {
            setCalibrationStatus(res);
          }
        }
      })
      .catch(() => {
        if (!cancelled) setCalibrationStatus(null);
      });

    return () => { cancelled = true; };
  }, []);

  // 加载反推验证数据
  useEffect(() => {
    if (!region) return;
    let cancelled = false;

    fetchJson(`${API_BASE}/v1/narrative/backvalidation/${region}`)
      .then((res) => {
        if (!cancelled && res && res.model_revenue) {
          setBackvalidation(res);
        }
      })
      .catch(() => {
        if (!cancelled) setBackvalidation(null);
      });

    return () => { cancelled = true; };
  }, [region]);

  if (loading) {
    return (
      <div data-testid="forward-spread-curve" className="h-64 flex items-center justify-center text-[var(--color-muted)] font-serif">
        {t.loading}
      </div>
    );
  }

  if (error) {
    return (
      <div data-testid="forward-spread-curve" className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button
          onClick={() => setError(false)}
          className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]"
        >
          {t.retry}
        </button>
      </div>
    );
  }

  if (!data) return null;

  const chartData = buildChartData(data);

  return (
    <div data-testid="forward-spread-curve" className="mt-3">
      <div className="flex items-center gap-2 mb-1">
        <h3 className="text-xl font-serif font-bold">{t.title}</h3>
        {calibrationStatus && calibrationStatus.status && calibrationStatus.status !== 'not_available' && calibrationStatus.status !== 'not_run' && (
          <span
            className={`inline-block px-2 py-0.5 text-xs rounded font-sans ${
              calibrationStatus.status === 'calibrated'
                ? 'bg-green-100 text-green-800'
                : 'bg-amber-100 text-amber-800'
            }`}
            title={calibrationStatus.status !== 'calibrated'
              ? `${calibrationStatus.status}${calibrationStatus.calibrated_at ? ` (${calibrationStatus.calibrated_at})` : ''}`
              : undefined}
          >
            {t.calibrationBadge}
          </span>
        )}
      </div>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {calibrationStatus && calibrationStatus.validation_r2 != null && (
        <div className="flex gap-4 text-xs text-[var(--color-muted)] font-sans mb-2">
          <span>{t.r2Label}: {calibrationStatus.validation_r2.toFixed(2)}</span>
          <span>{t.maeLabel}: ${calibrationStatus.validation_mae?.toFixed(1)}/MWh</span>
          <span>{t.directionLabel}: {(calibrationStatus.direction_accuracy * 100).toFixed(0)}%</span>
        </div>
      )}

      {!data.historical_available && (
        <p className="text-xs text-[var(--color-muted)] italic mb-2">{t.noHistorical}</p>
      )}

      <div className="h-[380px]">
        <ResponsiveContainer width="100%" height="100%">
          <ComposedChart data={chartData} margin={{ top: 10, right: 30, left: 10, bottom: 10 }}>
            <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
            <XAxis
              dataKey="year"
              tick={{ fontSize: 11 }}
              label={{ value: t.year, position: 'insideBottom', offset: -5, fontSize: 11 }}
            />
            <YAxis
              tick={{ fontSize: 11 }}
              label={{ value: t.spread, angle: -90, position: 'insideLeft', fontSize: 11 }}
            />
            <Tooltip content={<SpreadTooltip t={t} />} />
            <Legend wrapperStyle={{ fontSize: 11 }} />

            {/* 置信带：High 和 Low 之间的浅蓝色填充 */}
            <Area
              type="monotone"
              dataKey="high_spread"
              stroke="none"
              fill="#dbeafe"
              fillOpacity={0.5}
              name={t.confidenceBand}
              legendType="none"
              isAnimationActive={false}
            />
            <Area
              type="monotone"
              dataKey="low_spread"
              stroke="none"
              fill="#ffffff"
              fillOpacity={1}
              legendType="none"
              isAnimationActive={false}
            />

            {/* 历史数据：黑色实线 */}
            <Line
              type="monotone"
              dataKey="historical_spread"
              stroke="#000000"
              strokeWidth={2}
              dot={{ r: 3, fill: '#000000' }}
              name={t.historical}
              connectNulls={false}
              isAnimationActive={false}
            />

            {/* Central 情景：蓝色虚线 */}
            <Line
              type="monotone"
              dataKey="central_spread"
              stroke="#2563eb"
              strokeWidth={2}
              strokeDasharray="6 3"
              dot={false}
              name={t.central}
              connectNulls={false}
              isAnimationActive={false}
            />

            {/* High 情景：灰色虚线 */}
            <Line
              type="monotone"
              dataKey="high_spread"
              stroke="#6b7280"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              name={t.high}
              connectNulls={false}
              isAnimationActive={false}
            />

            {/* Low 情景：灰色虚线 */}
            <Line
              type="monotone"
              dataKey="low_spread"
              stroke="#6b7280"
              strokeWidth={1.5}
              strokeDasharray="4 4"
              dot={false}
              name={t.low}
              connectNulls={false}
              isAnimationActive={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
      </div>

      {/* 反推验证摘要 */}
      {backvalidation ? (
        <div className="mt-4 p-3 border border-[var(--color-border)] rounded text-xs font-sans">
          <div className="flex items-center justify-between mb-2">
            <span className="font-bold">{t.validationTitle}</span>
            <span className={`px-2 py-0.5 rounded-full ${_getDeviationColor(backvalidation.deviation_percent)}`}>
              {backvalidation.status === 'within_range' ? '✓' : '⚠'} {backvalidation.deviation_percent != null ? `${backvalidation.deviation_percent > 0 ? '+' : ''}${backvalidation.deviation_percent.toFixed(1)}%` : 'N/A'}
            </span>
          </div>
          <div className="grid grid-cols-2 gap-2 text-[var(--color-muted)]">
            <div>{t.modelRevenue}: <span className="text-[var(--color-text)]">${backvalidation.model_revenue?.toLocaleString(undefined, {maximumFractionDigits: 0})}/MW</span></div>
            <div>{t.benchmark}: <span className="text-[var(--color-text)]">${backvalidation.benchmark_revenue?.toLocaleString(undefined, {maximumFractionDigits: 0})}/MW</span></div>
          </div>
          <p className="mt-2 text-[var(--color-muted)] italic">{t.dataSource}</p>
        </div>
      ) : (
        calibrationStatus && (
          <p className="mt-3 text-xs text-[var(--color-muted)]">{t.validationUnavailable}</p>
        )
      )}
    </div>
  );
}

/**
 * 将 API 响应数据转换为 Recharts 所需的统一数据格式。
 * 历史数据和预测数据合并到同一数组中，通过不同字段区分。
 */
function buildChartData(apiData) {
  const chartData = [];

  // 历史数据：仅有 historical_spread 字段
  if (apiData.historical && apiData.historical.length > 0) {
    for (const point of apiData.historical) {
      chartData.push({
        year: point.year,
        historical_spread: point.spread,
        central_spread: null,
        high_spread: null,
        low_spread: null,
      });
    }
  }

  // 预测数据：仅有 central/high/low 字段
  if (apiData.projection && apiData.projection.length > 0) {
    // 连接点：历史最后一年的值也作为预测起点
    const lastHistorical = apiData.historical?.length > 0
      ? apiData.historical[apiData.historical.length - 1]
      : null;

    for (let i = 0; i < apiData.projection.length; i++) {
      const point = apiData.projection[i];
      const entry = {
        year: point.year,
        historical_spread: null,
        central_spread: point.central_spread,
        high_spread: point.high_spread,
        low_spread: point.low_spread,
      };

      // 第一个预测点同时显示历史连接
      if (i === 0 && lastHistorical) {
        entry.historical_spread = lastHistorical.spread;
      }

      chartData.push(entry);
    }
  }

  return chartData;
}

/**
 * 自定义 Tooltip 组件
 */
function SpreadTooltip({ active, payload, label, t }) {
  if (!active || !payload || payload.length === 0) return null;

  const items = payload.filter((p) => p.value != null && p.name !== t.confidenceBand);

  return (
    <div className="bg-[var(--color-bg)] border border-[var(--color-border)] rounded p-2 shadow-sm text-xs">
      <p className="font-serif font-bold mb-1">{label}</p>
      {items.map((item) => (
        <p key={item.dataKey} style={{ color: item.stroke || item.color }}>
          {item.name}: ${item.value?.toFixed(1)}/MWh
        </p>
      ))}
    </div>
  );
}
