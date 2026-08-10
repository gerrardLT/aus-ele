/**
 * AssumptionPanel — 假设透明面板
 *
 * 按类别分组展示所有模型输入假设（battery、cost、tax、forward_price、scenario），
 * 显示当前值、默认值、有效范围，支持用户修改并触发重新计算，
 * 显示数据来源引用（financial_evidence.json），提供重置按钮恢复默认值。
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6
 */

import { useCallback, useMemo, useState } from 'react';


const LABELS = {
  zh: {
    title: '模型假设面板',
    subtitle: '所有模型输入假设一览，支持修改与重置',
    loading: '加载中...',
    error: '数据加载失败',
    retry: '重试',
    resetAll: '重置全部',
    resetCategory: '重置',
    currentValue: '当前值',
    defaultValue: '默认值',
    range: '有效范围',
    source: '数据来源',
    modified: '已修改',
    recalculating: '重新计算中...',
    categories: {
      battery: '电池参数',
      cost: '成本参数',
      tax: '税务参数',
      forward_price: '前瞻电价假设',
      scenario: '情景选择',
    },
  },
  en: {
    title: 'Model Assumptions',
    subtitle: 'All model input assumptions with source references',
    loading: 'Loading...',
    error: 'Failed to load data',
    retry: 'Retry',
    resetAll: 'Reset All',
    resetCategory: 'Reset',
    currentValue: 'Current',
    defaultValue: 'Default',
    range: 'Valid Range',
    source: 'Source',
    modified: 'Modified',
    recalculating: 'Recalculating...',
    categories: {
      battery: 'Battery Specs',
      cost: 'Cost Parameters',
      tax: 'Tax Parameters',
      forward_price: 'Forward Price',
      scenario: 'Scenario',
    },
  },
};

/**
 * Default assumptions grouped by category.
 * Each assumption has: key, label (zh/en), defaultValue, range, unit, source.
 */
const DEFAULT_ASSUMPTIONS = [
  // Battery
  { category: 'battery', key: 'power_mw', label: { zh: '额定功率 (MW)', en: 'Power (MW)' }, defaultValue: 100, range: { min: 1, max: 2000 }, unit: 'MW', source: 'User configuration' },
  { category: 'battery', key: 'duration_hours', label: { zh: '储能时长 (h)', en: 'Duration (h)' }, defaultValue: 4, range: { min: 0.5, max: 12 }, unit: 'h', source: 'User configuration' },
  { category: 'battery', key: 'round_trip_efficiency', label: { zh: '往返效率', en: 'Round-Trip Efficiency' }, defaultValue: 0.87, range: { min: 0.70, max: 0.95 }, unit: '', source: 'modo_nem_2024_review' },
  { category: 'battery', key: 'degradation_rate', label: { zh: '年衰减率', en: 'Annual Degradation' }, defaultValue: 0.025, range: { min: 0.005, max: 0.05 }, unit: '%/yr', source: 'Industry standard' },
  // Cost
  { category: 'cost', key: 'capex_per_kwh', label: { zh: 'CAPEX ($/kWh)', en: 'CAPEX ($/kWh)' }, defaultValue: 350, range: { min: 150, max: 800 }, unit: '$/kWh', source: 'aemo_isp_2026' },
  { category: 'cost', key: 'opex_per_kw_year', label: { zh: 'OPEX ($/kW/年)', en: 'OPEX ($/kW/yr)' }, defaultValue: 12, range: { min: 5, max: 30 }, unit: '$/kW/yr', source: 'aemo_isp_2026' },
  // Tax
  { category: 'tax', key: 'company_tax_rate', label: { zh: '公司税率', en: 'Company Tax Rate' }, defaultValue: 0.30, range: { min: 0.0, max: 0.50 }, unit: '', source: 'ato_company_tax' },
  { category: 'tax', key: 'effective_life_years', label: { zh: '有效使用年限', en: 'Effective Life (yrs)' }, defaultValue: 20, range: { min: 10, max: 30 }, unit: 'yrs', source: 'ato_depreciation_2024' },
  // Forward Price
  { category: 'forward_price', key: 'base_spread', label: { zh: '基础价差 ($/MWh)', en: 'Base Spread ($/MWh)' }, defaultValue: 120, range: { min: 20, max: 500 }, unit: '$/MWh', source: 'modo_nem_2024_review' },
  { category: 'forward_price', key: 'spike_frequency', label: { zh: '极端价格频率', en: 'Spike Frequency' }, defaultValue: 0.003, range: { min: 0.0, max: 0.05 }, unit: '', source: 'modo_nem_2024_review' },
  { category: 'forward_price', key: 'gas_base_price', label: { zh: '天然气基础价 ($/GJ)', en: 'Gas Base Price ($/GJ)' }, defaultValue: 10.0, range: { min: 3.0, max: 30.0 }, unit: '$/GJ', source: 'financial_evidence.json' },
  { category: 'forward_price', key: 'pass_through_coefficient', label: { zh: '气价传导系数', en: 'Pass-Through Coeff' }, defaultValue: 9.5, range: { min: 5.0, max: 15.0 }, unit: '$/MWh per $/GJ', source: 'financial_evidence.json' },
  // Scenario
  { category: 'scenario', key: 'scenario_type', label: { zh: '情景类型', en: 'Scenario Type' }, defaultValue: 'central', range: null, unit: '', source: 'aemo_isp_2026', options: ['central', 'high', 'low'] },
  { category: 'scenario', key: 'spread_threshold', label: { zh: '价差阈值 ($/MWh)', en: 'Spread Threshold ($/MWh)' }, defaultValue: 300, range: { min: 0, max: 16600 }, unit: '$/MWh', source: 'NEM market price cap' },
];

const CATEGORY_ORDER = ['battery', 'cost', 'tax', 'forward_price', 'scenario'];

export default function AssumptionPanel({ lang = 'zh', onRecalculate }) {
  const t = LABELS[lang] || LABELS.en;

  const [values, setValues] = useState(() => {
    const initial = {};
    DEFAULT_ASSUMPTIONS.forEach((a) => { initial[a.key] = a.defaultValue; });
    return initial;
  });
  const [recalculating, setRecalculating] = useState(false);
  const [expandedCategories, setExpandedCategories] = useState(() => {
    const expanded = {};
    CATEGORY_ORDER.forEach((c) => { expanded[c] = true; });
    return expanded;
  });

  // Group assumptions by category
  const grouped = useMemo(() => {
    const groups = {};
    CATEGORY_ORDER.forEach((cat) => { groups[cat] = []; });
    DEFAULT_ASSUMPTIONS.forEach((a) => {
      if (groups[a.category]) {
        groups[a.category].push(a);
      }
    });
    return groups;
  }, []);

  // Track which values have been modified from defaults
  const modifiedKeys = useMemo(() => {
    const modified = new Set();
    DEFAULT_ASSUMPTIONS.forEach((a) => {
      if (values[a.key] !== a.defaultValue) {
        modified.add(a.key);
      }
    });
    return modified;
  }, [values]);

  // Handle value change
  const handleChange = useCallback((key, newValue, assumption) => {
    // Validate range
    if (assumption.range) {
      const numVal = parseFloat(newValue);
      if (isNaN(numVal)) return;
      if (numVal < assumption.range.min || numVal > assumption.range.max) return;
      setValues((prev) => ({ ...prev, [key]: numVal }));
    } else {
      setValues((prev) => ({ ...prev, [key]: newValue }));
    }
  }, []);

  // Trigger recalculation when values change
  const triggerRecalculate = useCallback(() => {
    if (onRecalculate) {
      setRecalculating(true);
      Promise.resolve(onRecalculate(values))
        .then(() => setRecalculating(false))
        .catch(() => setRecalculating(false));
    }
  }, [values, onRecalculate]);

  // Reset all to defaults
  const handleResetAll = useCallback(() => {
    const defaults = {};
    DEFAULT_ASSUMPTIONS.forEach((a) => { defaults[a.key] = a.defaultValue; });
    setValues(defaults);
    if (onRecalculate) {
      onRecalculate(defaults);
    }
  }, [onRecalculate]);

  // Reset a single category
  const handleResetCategory = useCallback((category) => {
    setValues((prev) => {
      const next = { ...prev };
      DEFAULT_ASSUMPTIONS.filter((a) => a.category === category).forEach((a) => {
        next[a.key] = a.defaultValue;
      });
      return next;
    });
  }, []);

  // Toggle category expansion
  const toggleCategory = useCallback((category) => {
    setExpandedCategories((prev) => ({ ...prev, [category]: !prev[category] }));
  }, []);

  // Count modified items per category
  const modifiedCountByCategory = useMemo(() => {
    const counts = {};
    CATEGORY_ORDER.forEach((cat) => {
      counts[cat] = DEFAULT_ASSUMPTIONS.filter(
        (a) => a.category === cat && modifiedKeys.has(a.key)
      ).length;
    });
    return counts;
  }, [modifiedKeys]);

  return (
    <div className="mt-3">
      {/* Header */}
      <div className="flex items-center justify-between mb-1">
        <h3 className="text-xl font-serif font-bold">{t.title}</h3>
        <div className="flex items-center gap-2">
          {recalculating && (
            <span className="text-xs text-[var(--color-muted)] animate-pulse">{t.recalculating}</span>
          )}
          {modifiedKeys.size > 0 && (
            <button
              onClick={handleResetAll}
              className="px-3 py-1 text-xs border border-[var(--color-border)] rounded hover:border-[var(--color-text)] transition-colors"
            >
              {t.resetAll}
            </button>
          )}
        </div>
      </div>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Category Groups */}
      <div className="space-y-3">
        {CATEGORY_ORDER.map((category) => {
          const assumptions = grouped[category];
          if (!assumptions || assumptions.length === 0) return null;
          const isExpanded = expandedCategories[category];
          const modCount = modifiedCountByCategory[category];

          return (
            <div key={category} className="border border-[var(--color-border)] rounded">
              {/* Category Header */}
              <button
                onClick={() => toggleCategory(category)}
                className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-[var(--color-border)]/20 transition-colors"
              >
                <div className="flex items-center gap-2">
                  <span className="text-sm font-serif font-bold">
                    {t.categories[category] || category}
                  </span>
                  {modCount > 0 && (
                    <span className="px-1.5 py-0.5 text-xs bg-[var(--color-status-timeout)]/10 text-[var(--color-status-timeout)] rounded">
                      {modCount} {t.modified}
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-2">
                  {modCount > 0 && (
                    <span
                      onClick={(e) => { e.stopPropagation(); handleResetCategory(category); }}
                      className="text-xs text-[var(--color-muted)] hover:text-[var(--color-text)] cursor-pointer"
                    >
                      {t.resetCategory}
                    </span>
                  )}
                  <span className="text-xs text-[var(--color-muted)]">{isExpanded ? '▼' : '▶'}</span>
                </div>
              </button>

              {/* Assumption Rows */}
              {isExpanded && (
                <div className="border-t border-[var(--color-border)]">
                  {assumptions.map((assumption) => (
                    <AssumptionRow
                      key={assumption.key}
                      assumption={assumption}
                      value={values[assumption.key]}
                      isModified={modifiedKeys.has(assumption.key)}
                      onChange={handleChange}
                      onBlur={triggerRecalculate}
                      lang={lang}
                      t={t}
                    />
                  ))}
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

/**
 * Single assumption row component.
 */
function AssumptionRow({ assumption, value, isModified, onChange, onBlur, lang, t }) {
  const label = assumption.label[lang] || assumption.label.en;
  const hasOptions = assumption.options && assumption.options.length > 0;

  return (
    <div className={`px-4 py-2.5 flex flex-col sm:flex-row sm:items-center gap-2 border-b border-[var(--color-border)] last:border-b-0 ${isModified ? 'bg-[var(--color-status-timeout)]/8' : ''}`}>
      {/* Label + Source */}
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-sans font-medium truncate">{label}</span>
          {isModified && (
            <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" title={t.modified} />
          )}
        </div>
        <div className="text-xs text-[var(--color-muted)] truncate mt-0.5">
          {t.source}: {assumption.source}
        </div>
      </div>

      {/* Input / Select */}
      <div className="flex items-center gap-3 flex-shrink-0">
        {hasOptions ? (
          <select
            value={value}
            onChange={(e) => onChange(assumption.key, e.target.value, assumption)}
            onBlur={onBlur}
            aria-label={label}
            className="px-2 py-1 text-xs font-mono border border-[var(--color-border)] rounded bg-transparent focus:outline-none focus:border-[var(--color-text)]"
          >
            {assumption.options.map((opt) => (
              <option key={opt} value={opt}>{opt}</option>
            ))}
          </select>
        ) : (
          <input
            type="number"
            value={value}
            onChange={(e) => onChange(assumption.key, e.target.value, assumption)}
            onBlur={onBlur}
            step={assumption.range && assumption.range.max <= 1 ? 0.01 : 1}
            min={assumption.range?.min}
            max={assumption.range?.max}
            aria-label={label}
            className="w-24 px-2 py-1 text-xs font-mono text-right border border-[var(--color-border)] rounded bg-transparent focus:outline-none focus:border-[var(--color-text)]"
          />
        )}

        {/* Default value + Range info */}
        <div className="text-xs text-[var(--color-muted)] font-mono whitespace-nowrap hidden sm:block">
          <span title={t.defaultValue}>⌀ {formatValue(assumption.defaultValue)}</span>
          {assumption.range && (
            <span className="ml-2" title={t.range}>
              [{assumption.range.min}–{assumption.range.max}]
            </span>
          )}
        </div>
      </div>
    </div>
  );
}

/**
 * Format a value for display.
 */
function formatValue(val) {
  if (typeof val === 'number') {
    if (val < 1 && val > 0) return val.toFixed(3);
    if (Number.isInteger(val)) return val.toString();
    return val.toFixed(2);
  }
  return String(val);
}
