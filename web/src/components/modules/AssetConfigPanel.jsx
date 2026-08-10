/**
 * AssetConfigPanel — 资产配置面板
 *
 * 用户定义项目特定参数（region、power_mw、duration_hours、round_trip_efficiency、mlf、connection_point），
 * 前端验证参数范围，保存配置调用 POST /api/v1/narrative/asset-config，
 * 配置变更触发所有下游模块重新计算，结果标签显示用户资产参数。
 * Requirements: 8.1, 8.2, 8.3, 8.4, 8.5, 8.6
 */

import { useEffect, useState, useCallback } from 'react';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';

const API_BASE = getApiBase();

const REGIONS = ['NSW1', 'QLD1', 'VIC1', 'SA1', 'TAS1', 'WEM'];

const VALIDATION = {
  power_mw: { min: 1, max: 2000, step: 1, unit: 'MW' },
  duration_hours: { min: 0.5, max: 12, step: 0.5, unit: 'h' },
  round_trip_efficiency: { min: 0.70, max: 0.95, step: 0.01, unit: '' },
  mlf: { min: 0.80, max: 1.10, step: 0.01, unit: '' },
};

const DEFAULT_CONFIG = {
  region: 'NSW1',
  power_mw: 100,
  duration_hours: 4,
  round_trip_efficiency: 0.85,
  mlf: 0.99,
  connection_point: '',
};

const LABELS = {
  zh: {
    title: '资产配置面板',
    subtitle: '定义您的 BESS 项目参数，所有分析结果将基于此配置',
    loading: '加载中...',
    error: '配置加载失败',
    retry: '重试',
    save: '保存配置',
    saving: '保存中...',
    saved: '已保存',
    reset: '恢复默认',
    region: '区域',
    power_mw: '额定功率',
    duration_hours: '储能时长',
    round_trip_efficiency: '往返效率 (RTE)',
    mlf: '边际损耗因子 (MLF)',
    connection_point: '接入点标识',
    capacity: '储能容量',
    assetLabel: '资产标签',
    validationError: '参数超出有效范围',
    saveError: '保存失败，请重试',
    projectSpecific: '项目特定分析',
    marketWide: '市场整体分析',
  },
  en: {
    title: 'Asset Configuration',
    subtitle: 'Define your BESS project parameters — all results will reflect this configuration',
    loading: 'Loading...',
    error: 'Failed to load configuration',
    retry: 'Retry',
    save: 'Save Configuration',
    saving: 'Saving...',
    saved: 'Saved',
    reset: 'Reset to Defaults',
    region: 'Region',
    power_mw: 'Power Capacity',
    duration_hours: 'Storage Duration',
    round_trip_efficiency: 'Round-Trip Efficiency (RTE)',
    mlf: 'Marginal Loss Factor (MLF)',
    connection_point: 'Connection Point',
    capacity: 'Energy Capacity',
    assetLabel: 'Asset Label',
    validationError: 'Parameter out of valid range',
    saveError: 'Save failed, please retry',
    projectSpecific: 'Project-Specific Analysis',
    marketWide: 'Market-Wide Analysis',
  },
};

/**
 * Validate a single field value against its range constraints.
 * Returns an error message string or null if valid.
 */
function validateField(key, value) {
  const rule = VALIDATION[key];
  if (!rule) return null;
  const num = parseFloat(value);
  if (isNaN(num)) return `Must be a number`;
  if (num < rule.min || num > rule.max) {
    return `Valid range: ${rule.min}–${rule.max} ${rule.unit}`;
  }
  return null;
}

/**
 * Validate the entire config object.
 * Returns an object mapping field names to error messages (empty if all valid).
 */
function validateConfig(config) {
  const errors = {};
  for (const key of Object.keys(VALIDATION)) {
    const err = validateField(key, config[key]);
    if (err) errors[key] = err;
  }
  return errors;
}

/**
 * Generate the asset label string from config.
 */
function generateLabel(config) {
  return `For YOUR ${config.power_mw}MW/${config.duration_hours}h BESS at ${config.region}`;
}

export default function AssetConfigPanel({ lang = 'zh', onConfigChange }) {
  const t = LABELS[lang] || LABELS.en;
  const [config, setConfig] = useState(DEFAULT_CONFIG);
  const [errors, setErrors] = useState({});
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState(false);
  const [saving, setSaving] = useState(false);
  const [saveStatus, setSaveStatus] = useState(null); // 'saved' | 'error' | null

  // Load existing config on mount
  useEffect(() => {
    setLoading(true);
    setLoadError(false);
    fetchJson(`${API_BASE}/v1/narrative/asset-config`)
      .then((res) => {
        if (res && res.region) {
          setConfig(res);
        }
        setLoading(false);
      })
      .catch(() => {
        setLoadError(true);
        setLoading(false);
      });
  }, []);

  const handleFieldChange = useCallback((key, rawValue) => {
    const value = VALIDATION[key] ? parseFloat(rawValue) || rawValue : rawValue;
    setConfig((prev) => {
      const next = { ...prev, [key]: value };
      // Validate on change
      const fieldErr = validateField(key, value);
      setErrors((prevErrors) => {
        const updated = { ...prevErrors };
        if (fieldErr) {
          updated[key] = fieldErr;
        } else {
          delete updated[key];
        }
        return updated;
      });
      return next;
    });
    setSaveStatus(null);
  }, []);

  const handleRegionChange = useCallback((value) => {
    setConfig((prev) => ({ ...prev, region: value }));
    setSaveStatus(null);
  }, []);

  const handleConnectionPointChange = useCallback((value) => {
    setConfig((prev) => ({ ...prev, connection_point: value }));
    setSaveStatus(null);
  }, []);

  const handleSave = useCallback(async () => {
    // Full validation before save
    const validationErrors = validateConfig(config);
    if (Object.keys(validationErrors).length > 0) {
      setErrors(validationErrors);
      return;
    }

    setSaving(true);
    setSaveStatus(null);
    try {
      const result = await fetchJson(`${API_BASE}/v1/narrative/asset-config`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(config),
      });
      setSaveStatus('saved');
      // Trigger downstream recalculation
      if (onConfigChange) {
        onConfigChange(result || config);
      }
    } catch {
      setSaveStatus('error');
    } finally {
      setSaving(false);
    }
  }, [config, onConfigChange]);

  const handleReset = useCallback(() => {
    setConfig(DEFAULT_CONFIG);
    setErrors({});
    setSaveStatus(null);
  }, []);

  if (loading) {
    return (
      <div data-testid="asset-config-panel" className="h-48 flex items-center justify-center text-[var(--color-muted)] font-serif">
        {t.loading}
      </div>
    );
  }

  if (loadError) {
    return (
      <div data-testid="asset-config-panel" className="h-48 flex flex-col items-center justify-center gap-3">
        <span className="text-[var(--color-muted)]">{t.error}</span>
        <button
          onClick={() => { setLoadError(false); setLoading(true); }}
          className="px-4 py-1.5 text-sm border border-[var(--color-border)] rounded hover:border-[var(--color-text)]"
        >
          {t.retry}
        </button>
      </div>
    );
  }

  const hasErrors = Object.keys(errors).length > 0;
  const capacityMwh = (config.power_mw || 0) * (config.duration_hours || 0);
  const label = generateLabel(config);

  return (
    <div data-testid="asset-config-panel" className="mt-3">
      <h3 className="text-xl font-serif font-bold mb-1">{t.title}</h3>
      <p className="text-xs text-[var(--color-muted)] font-sans mb-4">{t.subtitle}</p>

      {/* Asset Label Preview（主题 token：dark: 变体不跟随应用主题开关，已废弃） */}
      <div className="mb-4 p-3 rounded border border-[var(--color-primary)]/40 bg-[var(--color-primary)]/8">
        <p className="text-xs text-[var(--color-muted)] mb-1">{t.assetLabel}</p>
        <p className="text-sm font-serif font-bold text-[var(--color-primary)]">
          {label}
        </p>
        <p className="text-xs text-[var(--color-muted)] mt-1">
          {t.capacity}: {capacityMwh.toFixed(1)} MWh
        </p>
      </div>

      {/* Configuration Form */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
        {/* Region Select */}
        <div>
          <label htmlFor="asset-region" className="block text-xs font-sans text-[var(--color-muted)] mb-1">
            {t.region}
          </label>
          <select
            id="asset-region"
            value={config.region}
            onChange={(e) => handleRegionChange(e.target.value)}
            className="w-full px-3 py-2 text-sm border border-[var(--color-border)] rounded bg-transparent focus:outline-none focus:border-blue-500"
          >
            {REGIONS.map((r) => (
              <option key={r} value={r}>{r}</option>
            ))}
          </select>
        </div>

        {/* Power MW */}
        <div>
          <label htmlFor="asset-power-mw" className="block text-xs font-sans text-[var(--color-muted)] mb-1">
            {t.power_mw} ({VALIDATION.power_mw.min}–{VALIDATION.power_mw.max} {VALIDATION.power_mw.unit})
          </label>
          <input
            id="asset-power-mw"
            type="number"
            min={VALIDATION.power_mw.min}
            max={VALIDATION.power_mw.max}
            step={VALIDATION.power_mw.step}
            value={config.power_mw}
            onChange={(e) => handleFieldChange('power_mw', e.target.value)}
            className={`w-full px-3 py-2 text-sm border rounded bg-transparent focus:outline-none ${
              errors.power_mw
                ? 'border-red-500 focus:border-red-500'
                : 'border-[var(--color-border)] focus:border-blue-500'
            }`}
          />
          {errors.power_mw && (
            <p className="text-xs text-red-500 mt-0.5">{errors.power_mw}</p>
          )}
        </div>

        {/* Duration Hours */}
        <div>
          <label htmlFor="asset-duration-hours" className="block text-xs font-sans text-[var(--color-muted)] mb-1">
            {t.duration_hours} ({VALIDATION.duration_hours.min}–{VALIDATION.duration_hours.max} {VALIDATION.duration_hours.unit})
          </label>
          <input
            id="asset-duration-hours"
            type="number"
            min={VALIDATION.duration_hours.min}
            max={VALIDATION.duration_hours.max}
            step={VALIDATION.duration_hours.step}
            value={config.duration_hours}
            onChange={(e) => handleFieldChange('duration_hours', e.target.value)}
            className={`w-full px-3 py-2 text-sm border rounded bg-transparent focus:outline-none ${
              errors.duration_hours
                ? 'border-red-500 focus:border-red-500'
                : 'border-[var(--color-border)] focus:border-blue-500'
            }`}
          />
          {errors.duration_hours && (
            <p className="text-xs text-red-500 mt-0.5">{errors.duration_hours}</p>
          )}
        </div>

        {/* Round Trip Efficiency */}
        <div>
          <label htmlFor="asset-rte" className="block text-xs font-sans text-[var(--color-muted)] mb-1">
            {t.round_trip_efficiency} ({VALIDATION.round_trip_efficiency.min}–{VALIDATION.round_trip_efficiency.max})
          </label>
          <input
            id="asset-rte"
            type="number"
            min={VALIDATION.round_trip_efficiency.min}
            max={VALIDATION.round_trip_efficiency.max}
            step={VALIDATION.round_trip_efficiency.step}
            value={config.round_trip_efficiency}
            onChange={(e) => handleFieldChange('round_trip_efficiency', e.target.value)}
            className={`w-full px-3 py-2 text-sm border rounded bg-transparent focus:outline-none ${
              errors.round_trip_efficiency
                ? 'border-red-500 focus:border-red-500'
                : 'border-[var(--color-border)] focus:border-blue-500'
            }`}
          />
          {errors.round_trip_efficiency && (
            <p className="text-xs text-red-500 mt-0.5">{errors.round_trip_efficiency}</p>
          )}
        </div>

        {/* MLF */}
        <div>
          <label htmlFor="asset-mlf" className="block text-xs font-sans text-[var(--color-muted)] mb-1">
            {t.mlf} ({VALIDATION.mlf.min}–{VALIDATION.mlf.max})
          </label>
          <input
            id="asset-mlf"
            type="number"
            min={VALIDATION.mlf.min}
            max={VALIDATION.mlf.max}
            step={VALIDATION.mlf.step}
            value={config.mlf}
            onChange={(e) => handleFieldChange('mlf', e.target.value)}
            className={`w-full px-3 py-2 text-sm border rounded bg-transparent focus:outline-none ${
              errors.mlf
                ? 'border-red-500 focus:border-red-500'
                : 'border-[var(--color-border)] focus:border-blue-500'
            }`}
          />
          {errors.mlf && (
            <p className="text-xs text-red-500 mt-0.5">{errors.mlf}</p>
          )}
        </div>

        {/* Connection Point */}
        <div>
          <label htmlFor="asset-connection-point" className="block text-xs font-sans text-[var(--color-muted)] mb-1">
            {t.connection_point}
          </label>
          <input
            id="asset-connection-point"
            type="text"
            value={config.connection_point}
            onChange={(e) => handleConnectionPointChange(e.target.value)}
            placeholder="e.g. SYDW1"
            className="w-full px-3 py-2 text-sm border border-[var(--color-border)] rounded bg-transparent focus:outline-none focus:border-blue-500"
          />
        </div>
      </div>

      {/* Section Distinction: Project-Specific vs Market-Wide */}
      <div className="mb-4 p-3 rounded border border-[var(--color-border)] bg-[var(--color-bg-secondary,transparent)]">
        <div className="flex items-center gap-2 mb-1">
          <span className="inline-block w-2 h-2 rounded-full bg-blue-500" />
          <span className="text-xs font-sans font-bold">{t.projectSpecific}</span>
        </div>
        <p className="text-xs text-[var(--color-muted)] ml-4">
          {label} | RTE: {((config.round_trip_efficiency || 0) * 100).toFixed(0)}% | MLF: {config.mlf}
        </p>
      </div>

      {/* Action Buttons */}
      <div className="flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving || hasErrors}
          className={`px-5 py-2 text-sm font-sans rounded transition-colors ${
            hasErrors
              ? 'bg-[var(--color-surface-hover)] text-[var(--color-muted)] cursor-not-allowed'
              : saving
                ? 'bg-[var(--color-primary)]/60 text-white cursor-wait'
                : 'bg-[var(--color-primary)] text-white hover:opacity-90'
          }`}
        >
          {saving ? t.saving : t.save}
        </button>

        <button
          onClick={handleReset}
          className="px-4 py-2 text-sm font-sans border border-[var(--color-border)] rounded hover:border-[var(--color-text)] transition-colors"
        >
          {t.reset}
        </button>

        {/* Save Status Feedback */}
        {saveStatus === 'saved' && (
          <span className="text-xs text-[var(--color-status-success)] font-sans">✓ {t.saved}</span>
        )}
        {saveStatus === 'error' && (
          <span className="text-xs text-red-500 font-sans">✗ {t.saveError}</span>
        )}
      </div>
    </div>
  );
}
