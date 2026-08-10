/**
 * ScenarioSplit — U5: What-if 双栏对比面板
 *
 * 左栏"Pinned"基准 + 右栏"Alternative"调参结果 + 中间 delta。
 * 复用 ReactiveParamPanel 驱动 Alternative 请求。
 */

import { useState, useCallback, useEffect, useRef, Fragment } from 'react';
import { Pin } from 'lucide-react';
import { useFilters } from '../../contexts/FilterContext';
import { fetchJson } from '../../lib/apiClient';
import { getApiBase } from '../../lib/apiBase';
import { useDebounce } from '../../hooks/useDebounce';

const API_BASE = getApiBase();

const METRICS = [
  { key: 'npv', label: 'NPV', format: v => `$${Math.round(v).toLocaleString()}` },
  { key: 'irr', label: 'IRR', format: v => v != null ? `${(v * 100).toFixed(1)}%` : '--' },
  { key: 'payback_years', label: 'Payback', format: v => v != null ? `${v.toFixed(1)}y` : '--' },
  { key: 'llcr', label: 'LLCR', format: v => v != null ? v.toFixed(2) : '--' },
];

export default function ScenarioSplit({ lang = 'zh', region }) {
  const { filters } = useFilters();
  const [pinned, setPinned] = useState(null);
  const [altParams, setAltParams] = useState({ power_mw: 100, duration_hours: 4, capex_per_kwh: 350 });
  const [altResult, setAltResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const debouncedParams = useDebounce(altParams, 600);

  const runAlt = useCallback(async (p) => {
    const r = region || filters.region;
    if (!r) return;
    setLoading(true);
    try {
      const res = await fetchJson(`${API_BASE}/api/investment-analysis`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          region: r,
          battery: { power_mw: p.power_mw, duration_hours: p.duration_hours },
          financial: { capex_per_kwh: p.capex_per_kwh },
          backtest_years: [filters.year || 2025],
        }),
      });
      setAltResult(res?.base_metrics || null);
    } catch { setAltResult(null); }
    setLoading(false);
  }, [region, filters.region, filters.year]);

  // Auto-run on debounced param change (skip first render)
  const isFirstRender = useRef(true);
  useEffect(() => {
    if (isFirstRender.current) { isFirstRender.current = false; return; }
    runAlt(debouncedParams);
  }, [debouncedParams, runAlt]);

  function handlePin() {
    if (altResult) setPinned({ ...altResult, params: { ...altParams } });
  }

  function delta(key) {
    if (!pinned || !altResult) return null;
    const base = pinned[key];
    const alt = altResult[key];
    if (base == null || alt == null || base === 0) return null;
    return ((alt - base) / Math.abs(base)) * 100;
  }

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-5 panel-glass">
      <div className="flex items-center justify-between mb-4">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
          {lang === 'zh' ? 'What-if 对比' : 'What-if Comparison'}
        </span>
        <button
          onClick={handlePin}
          disabled={!altResult}
          className="flex items-center gap-1 px-2.5 py-1 text-[11px] rounded-full border border-[var(--color-border)] hover:border-[var(--color-primary)] text-[var(--color-muted)] hover:text-[var(--color-primary)] transition-colors disabled:opacity-40"
        >
          <Pin size={11} /> {lang === 'zh' ? '钉住当前' : 'Pin Current'}
        </button>
      </div>

      {/* Sliders */}
      <div className="grid grid-cols-3 gap-3 mb-4">
        {[
          { key: 'power_mw', label: 'MW', min: 10, max: 200, step: 5 },
          { key: 'duration_hours', label: 'h', min: 1, max: 8, step: 0.5 },
          { key: 'capex_per_kwh', label: '$/kWh', min: 200, max: 600, step: 10 },
        ].map(s => (
          <div key={s.key}>
            <div className="flex justify-between text-[10px] text-[var(--color-muted)] mb-1">
              <span>{s.label}</span><span className="font-mono">{altParams[s.key]}</span>
            </div>
            <input
              type="range" min={s.min} max={s.max} step={s.step}
              value={altParams[s.key]}
              onChange={e => {
                const v = parseFloat(e.target.value);
                setAltParams(prev => ({ ...prev, [s.key]: v }));
              }}
              className="w-full h-1 rounded-full appearance-none bg-[var(--color-border)] accent-[var(--color-primary)] cursor-pointer"
            />
          </div>
        ))}
      </div>

      {/* Comparison table */}
      <div className="grid grid-cols-[1fr_auto_1fr] gap-2 text-xs">
        <span className="text-[var(--color-muted)] font-bold">{lang === 'zh' ? '基准' : 'Pinned'}</span>
        <span className="text-[var(--color-muted)] font-bold text-center">Delta</span>
        <span className="text-[var(--color-muted)] font-bold text-right">{lang === 'zh' ? '替代' : 'Alternative'}</span>
        {METRICS.map(m => {
          const d = delta(m.key);
          return (
            <Fragment key={m.key}>
              <span className="font-mono text-[var(--color-text)]">
                {pinned ? m.format(pinned[m.key]) : '--'}
              </span>
              <span className={`text-center font-mono ${d == null ? 'text-[var(--color-muted)]' : d >= 0 ? 'text-[var(--color-positive)]' : 'text-[var(--color-negative)]'}`}>
                {d == null ? '--' : `${d >= 0 ? '+' : ''}${d.toFixed(1)}%`}
              </span>
              <span className="font-mono text-[var(--color-text)] text-right">
                {altResult ? m.format(altResult[m.key]) : '--'}
              </span>
            </Fragment>
          );
        })}
      </div>
    </div>
  );
}
