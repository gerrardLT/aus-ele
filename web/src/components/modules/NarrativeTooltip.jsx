/**
 * NarrativeTooltip — 因果归因悬浮提示组件
 *
 * 可展开的悬浮提示，显示指标的因果归因链：
 * 驱动因素名称、类型、贡献量、来源引用。
 * 支持任意触发元素（指标数值），hover 时按需加载数据。
 *
 * Requirements: 1.2, 1.3, 1.5
 */

import { useState, useRef, useCallback } from 'react';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const LABELS = {
  zh: {
    loading: '加载中...',
    error: '归因数据加载失败',
    noData: '暂无归因数据',
    expand: '展开详情',
    collapse: '收起',
    contribution: '贡献',
    source: '来源',
    driverTypes: {
      coal_closure: '煤电退役',
      bess_saturation: 'BESS 饱和',
      network_augmentation: '网络增强',
      gas_price: '气价变动',
      demand_growth: '需求增长',
      fcas_collapse: 'FCAS 崩塌',
    },
  },
  en: {
    loading: 'Loading...',
    error: 'Failed to load attribution',
    noData: 'No attribution data',
    expand: 'Show details',
    collapse: 'Collapse',
    contribution: 'Contribution',
    source: 'Source',
    driverTypes: {
      coal_closure: 'Coal Closure',
      bess_saturation: 'BESS Saturation',
      network_augmentation: 'Network Augmentation',
      gas_price: 'Gas Price',
      demand_growth: 'Demand Growth',
      fcas_collapse: 'FCAS Collapse',
    },
  },
};

/**
 * NarrativeTooltip 组件
 *
 * @param {object} props
 * @param {React.ReactNode} props.children - 触发元素（指标数值等）
 * @param {string} [props.module] - 模块名称，默认 'forward_price'
 * @param {number} [props.year] - 目标年份（可选，默认使用 filter 中的年份）
 * @param {string} [props.scenario] - 情景类型，默认 'central'
 * @param {string} [props.lang] - 语言，默认 'zh'
 */
export default function NarrativeTooltip({
  children,
  module = 'forward_price',
  year,
  scenario = 'central',
  lang = 'zh',
}) {
  const { filters } = useFilters();
  const t = LABELS[lang] || LABELS.zh;

  const [visible, setVisible] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const hoverTimerRef = useRef(null);
  const hasFetchedRef = useRef(false);
  const tooltipRef = useRef(null);

  const region = filters.region;
  const targetYear = year || filters.year;

  const fetchAttribution = useCallback(() => {
    if (hasFetchedRef.current || loading) return;
    hasFetchedRef.current = true;
    setLoading(true);
    setError(false);

    const params = new URLSearchParams({
      module,
      scenario,
      ...(targetYear ? { year: String(targetYear) } : {}),
    });

    fetchJson(`${API_BASE}/v1/narrative/attribution/${region}?${params}`)
      .then((res) => {
        setData(res);
        setLoading(false);
      })
      .catch(() => {
        setError(true);
        setLoading(false);
        hasFetchedRef.current = false;
      });
  }, [region, module, scenario, targetYear, loading]);

  const handleMouseEnter = useCallback(() => {
    hoverTimerRef.current = setTimeout(() => {
      setVisible(true);
      fetchAttribution();
    }, 200);
  }, [fetchAttribution]);

  const handleMouseLeave = useCallback(() => {
    if (hoverTimerRef.current) {
      clearTimeout(hoverTimerRef.current);
      hoverTimerRef.current = null;
    }
    setVisible(false);
    setExpanded(false);
  }, []);

  return (
    <span
      className="relative inline-block cursor-help"
      onMouseEnter={handleMouseEnter}
      onMouseLeave={handleMouseLeave}
      ref={tooltipRef}
    >
      {/* 触发元素 */}
      <span className="border-b border-dotted border-[var(--color-muted)]">
        {children}
      </span>

      {/* 悬浮提示面板 */}
      {visible && (
        <div className="absolute z-50 bottom-full left-1/2 -translate-x-1/2 mb-2 w-72 max-w-sm bg-[var(--color-bg)] border border-[var(--color-border)] rounded shadow-lg p-3 text-xs font-sans">
          {/* 箭头 */}
          <div className="absolute top-full left-1/2 -translate-x-1/2 w-0 h-0 border-l-4 border-r-4 border-t-4 border-l-transparent border-r-transparent border-t-[var(--color-border)]" />

          {loading && (
            <div className="text-center text-[var(--color-muted)] py-2">{t.loading}</div>
          )}

          {error && (
            <div className="text-center text-red-500 py-2">{t.error}</div>
          )}

          {!loading && !error && data && (
            <TooltipContent
              data={data}
              expanded={expanded}
              onToggleExpand={() => setExpanded((v) => !v)}
              t={t}
            />
          )}

          {!loading && !error && !data && (
            <div className="text-center text-[var(--color-muted)] py-2">{t.noData}</div>
          )}
        </div>
      )}
    </span>
  );
}

/**
 * 提示内容区域
 */
function TooltipContent({ data, expanded, onToggleExpand, t }) {
  const { metric_name, metric_value, metric_unit, narrative_text, causal_factors } = data;
  const hasFactors = causal_factors && causal_factors.length > 0;

  return (
    <div>
      {/* 指标摘要 */}
      <div className="flex items-baseline justify-between mb-1.5">
        <span className="font-serif font-bold text-sm">{metric_name}</span>
        <span className="font-mono text-sm">
          {typeof metric_value === 'number' ? metric_value.toFixed(2) : metric_value}
          {metric_unit && <span className="text-[var(--color-muted)] ml-0.5">{metric_unit}</span>}
        </span>
      </div>

      {/* 叙事文本 */}
      <p className="text-[var(--color-muted)] leading-relaxed mb-2">{narrative_text}</p>

      {/* 因果因素列表 */}
      {hasFactors && (
        <>
          {/* 始终显示前 2 个因素 */}
          <FactorList factors={causal_factors.slice(0, 2)} t={t} />

          {/* 展开/收起更多因素 */}
          {causal_factors.length > 2 && (
            <>
              {expanded && <FactorList factors={causal_factors.slice(2)} t={t} />}
              <button
                onClick={(e) => { e.stopPropagation(); onToggleExpand(); }}
                className="mt-1.5 text-[10px] text-[var(--color-muted)] hover:text-[var(--color-text)] underline"
              >
                {expanded ? t.collapse : `${t.expand} (+${causal_factors.length - 2})`}
              </button>
            </>
          )}
        </>
      )}
    </div>
  );
}

/**
 * 因果因素列表
 */
function FactorList({ factors, t }) {
  return (
    <ul className="space-y-1.5">
      {factors.map((factor, idx) => (
        <FactorItem key={idx} factor={factor} t={t} />
      ))}
    </ul>
  );
}

/**
 * 单个因果因素条目
 */
function FactorItem({ factor, t }) {
  const { driver_name, driver_type, contribution_amount, contribution_pct, source_reference } = factor;
  const typeLabel = t.driverTypes[driver_type] || driver_type;

  return (
    <li className="border-l-2 border-[var(--color-border)] pl-2">
      <div className="flex items-center justify-between">
        <span className="font-medium">{driver_name}</span>
        <span className="font-mono text-[var(--color-muted)]">
          {contribution_amount > 0 ? '+' : ''}
          {contribution_amount.toFixed(1)}
          {contribution_pct != null && (
            <span className="ml-1">({contribution_pct.toFixed(0)}%)</span>
          )}
        </span>
      </div>
      <div className="flex items-center justify-between text-[10px] text-[var(--color-muted)] mt-0.5">
        <span className="inline-block px-1 py-0.5 bg-[var(--color-border)] rounded">
          {typeLabel}
        </span>
        {source_reference && (
          <span className="truncate max-w-[120px]" title={source_reference}>
            {t.source}: {source_reference}
          </span>
        )}
      </div>
    </li>
  );
}
