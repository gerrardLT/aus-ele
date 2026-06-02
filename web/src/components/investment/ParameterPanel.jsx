/**
 * ParameterPanel — 左侧参数面板
 * 包含 FIELD_GROUPS、FCAS 模式选择、Monte Carlo 开关、运行按钮
 * "Project Finance" 组默认折叠，Storage + Cost + Finance 默认展开
 */

import { useState } from 'react';
import { fmt } from '../../lib/formatters';

export const FIELD_GROUPS = [
  {
    titleKey: 'storage',
    defaultExpanded: true,
    fields: [
      { key: 'power_mw', labelKey: 'power_mw', step: 10, min: 1, suffix: 'MW' },
      { key: 'duration_hours', labelKey: 'duration_hours', step: 1, min: 1, suffix: 'h' },
      { key: 'degradation_rate', labelKey: 'degradation_rate', step: 0.005, min: 0, suffix: '%/yr', pct: true },
      { key: 'revenue_capture_rate', labelKey: 'revenue_capture_rate', step: 0.05, min: 0, max: 1, suffix: '%', pct: true },
    ],
  },
  {
    titleKey: 'cost',
    defaultExpanded: true,
    fields: [
      { key: 'capex_per_kwh', labelKey: 'capex_per_kwh', step: 10, min: 0, suffix: '$/kWh' },
      { key: 'fixed_om_per_mw_year', labelKey: 'fixed_om_per_mw_year', step: 1000, min: 0, suffix: '$/MW/yr' },
      { key: 'variable_om_per_mwh', labelKey: 'variable_om_per_mwh', step: 0.5, min: 0, suffix: '$/MWh' },
      { key: 'grid_connection_cost', labelKey: 'grid_connection_cost', step: 500000, min: 0, suffix: '$' },
      { key: 'land_lease_per_year', labelKey: 'land_lease_per_year', step: 50000, min: 0, suffix: '$/yr' },
    ],
  },
  {
    titleKey: 'finance',
    defaultExpanded: true,
    fields: [
      { key: 'discount_rate', labelKey: 'discount_rate', step: 0.01, min: 0, max: 1, suffix: '%', pct: true },
      { key: 'project_life_years', labelKey: 'project_life_years', step: 1, min: 1, suffix: 'yr' },
      { key: 'fcas_revenue_per_mw_year', labelKey: 'fcas_revenue_per_mw_year', step: 5000, min: 0, suffix: '$/MW/yr' },
      { key: 'capacity_payment_per_mw_year', labelKey: 'capacity_payment_per_mw_year', step: 10000, min: 0, suffix: '$/MW/yr' },
      { key: 'forecast_inefficiency', labelKey: 'forecast_inefficiency', step: 0.05, min: 0, max: 1, suffix: '%', pct: true },
      { key: 'fcas_activation_probability', labelKey: 'fcas_activation_probability', step: 0.05, min: 0, max: 1, suffix: '%', pct: true },
    ],
  },
  {
    titleKey: 'projectFinance',
    defaultExpanded: false,
    fields: [
      { key: 'cost_of_debt', labelKey: 'cost_of_debt', step: 0.01, min: 0, max: 1, suffix: '%', pct: true },
      { key: 'target_dscr', labelKey: 'target_dscr', step: 0.05, min: 1, max: 3, suffix: 'x' },
      { key: 'debt_tenor_years', labelKey: 'debt_tenor_years', step: 1, min: 1, suffix: 'yr' },
    ],
  },
];

export default function ParameterPanel({ params, setParams, loading, onRun, copy }) {
  const [expandedGroups, setExpandedGroups] = useState(() => {
    const initial = {};
    FIELD_GROUPS.forEach((g) => { initial[g.titleKey] = g.defaultExpanded; });
    return initial;
  });

  const capexPreview = (params.capex_per_kwh * params.power_mw * params.duration_hours * 1000) + params.grid_connection_cost;

  const updateNumericParam = (key, value) => {
    const nextValue = value === '' ? '' : Number(value);
    setParams((prev) => ({
      ...prev,
      [key]: Number.isNaN(nextValue) ? prev[key] : nextValue,
    }));
  };

  const toggleGroup = (titleKey) => {
    setExpandedGroups((prev) => ({ ...prev, [titleKey]: !prev[titleKey] }));
  };

  return (
    <div className="overflow-hidden rounded-lg border border-[var(--color-border)]">
      <div className="border-b border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <h3 className="text-sm font-bold uppercase tracking-wider">{copy.parameters}</h3>
      </div>

      <div className="space-y-4 p-4">
        {/* FCAS 模式选择 */}
        <div>
          <label htmlFor="inv-fcas-mode" className="mb-2 block text-xs font-bold uppercase tracking-widest text-[var(--color-muted)]">
            {copy.fcasRevenueMode}
          </label>
          <select
            id="inv-fcas-mode"
            value={params.fcas_revenue_mode}
            onChange={(e) => setParams((prev) => ({ ...prev, fcas_revenue_mode: e.target.value }))}
            className="w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm"
          >
            <option value="auto">{copy.modeAuto}</option>
            <option value="manual">{copy.modeManual}</option>
          </select>
        </div>

        {/* Monte Carlo 开关 */}
        <div>
          <label className="mb-2 block text-xs font-bold uppercase tracking-widest text-[var(--color-muted)] flex items-center gap-2">
            <input
              type="checkbox"
              checked={params.monte_carlo_enabled}
              onChange={(e) => setParams((prev) => ({ ...prev, monte_carlo_enabled: e.target.checked }))}
              className="rounded border-[var(--color-border)] text-[var(--color-primary)] focus:ring-[var(--color-primary)]"
            />
            {copy.monteCarloToggle}
          </label>
        </div>

        {/* 参数组 */}
        {FIELD_GROUPS.map((group) => (
          <div key={group.titleKey}>
            <button
              type="button"
              onClick={() => toggleGroup(group.titleKey)}
              className="mb-3 flex w-full items-center justify-between text-xs font-bold uppercase tracking-widest text-[var(--color-muted)] hover:text-[var(--color-text)] transition-colors"
            >
              <span>{copy.groups[group.titleKey]}</span>
              <span className="text-sm">{expandedGroups[group.titleKey] ? '▾' : '▸'}</span>
            </button>
            {expandedGroups[group.titleKey] && (
              <div className="space-y-3">
                {group.fields.map((field) => {
                  const disabled = field.key === 'fcas_revenue_per_mw_year' && params.fcas_revenue_mode !== 'manual';
                  const value = params[field.key];
                  return (
                    <label key={field.key} className={`block ${disabled ? 'opacity-50' : ''}`}>
                      <div className="mb-1 flex items-center justify-between text-xs">
                        <span className="text-[var(--color-muted)]">{copy.fields[field.labelKey] || copy.fieldLabels[field.labelKey]}</span>
                        <span className="font-mono font-bold">
                          {field.pct ? `${(value * 100).toFixed(2)}${field.suffix}` : `${Number(value).toLocaleString()} ${field.suffix}`}
                        </span>
                      </div>
                      <input
                        type="number"
                        min={field.min}
                        max={field.max}
                        step={field.step}
                        value={value}
                        disabled={disabled}
                        onChange={(e) => updateNumericParam(field.key, e.target.value)}
                        className="w-full rounded border border-[var(--color-border)] bg-transparent px-3 py-2 text-sm font-mono disabled:cursor-not-allowed"
                      />
                    </label>
                  );
                })}
              </div>
            )}
          </div>
        ))}
      </div>

      <div className="border-t border-[var(--color-border)] bg-[var(--color-surface)] p-4">
        <button
          onClick={onRun}
          disabled={loading}
          className="w-full bg-[var(--color-inverted)] py-3 text-sm font-bold uppercase tracking-wider text-[var(--color-inverted-text)] transition-opacity hover:opacity-90 disabled:opacity-50"
        >
          {loading ? copy.running : copy.runAnalysis}
        </button>
        <div className="mt-2 text-center text-xs text-[var(--color-muted)]">
          {copy.capexSummary} {fmt(capexPreview)} | {copy.sizeSummary} {params.power_mw}MW / {params.power_mw * params.duration_hours}MWh
        </div>
      </div>
    </div>
  );
}
