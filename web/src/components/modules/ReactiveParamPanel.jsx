/**
 * ReactiveParamPanel — U2: 实时参数滑块面板
 *
 * 3 个核心参数 slider（power/duration/capex），拖动时 500ms debounce 后
 * 自动触发投资分析重算，消灭"填参→提交→等待"的割裂感。
 */

import { useEffect, useRef } from 'react';
import { motion } from 'framer-motion';
import { useDebounce } from '../../hooks/useDebounce';

const SLIDERS = [
  { key: 'power_mw', label: { zh: '功率', en: 'Power' }, unit: 'MW', min: 10, max: 200, step: 5 },
  { key: 'duration_hours', label: { zh: '时长', en: 'Duration' }, unit: 'h', min: 1, max: 8, step: 0.5 },
  { key: 'capex_per_kwh', label: { zh: 'CAPEX', en: 'CAPEX' }, unit: '$/kWh', min: 200, max: 600, step: 10 },
];

export default function ReactiveParamPanel({ params, setParams, onRun, lang = 'zh', loading }) {
  const debouncedParams = useDebounce(params, 500);
  const prevDebounced = useRef(debouncedParams);

  // Auto-run when debounced params change (skip initial render)
  useEffect(() => {
    const prev = prevDebounced.current;
    const changed = SLIDERS.some(s => prev[s.key] !== debouncedParams[s.key]);
    prevDebounced.current = debouncedParams;
    if (changed && onRun) {
      onRun(debouncedParams);
    }
  }, [debouncedParams, onRun]);

  return (
    <div className="rounded-xl border border-[var(--color-border)] bg-[var(--color-surface)] p-4">
      <div className="mb-3 flex items-center justify-between">
        <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
          {lang === 'zh' ? '快速调参' : 'Quick Tune'}
        </span>
        {loading && (
          <motion.span
            animate={{ opacity: [0.4, 1, 0.4] }}
            transition={{ repeat: Infinity, duration: 1.2 }}
            className="text-[10px] text-[var(--color-primary)]"
          >
            {lang === 'zh' ? '计算中...' : 'Computing...'}
          </motion.span>
        )}
      </div>

      <div className="space-y-4">
        {SLIDERS.map(({ key, label, unit, min, max, step }) => (
          <div key={key}>
            <div className="mb-1 flex items-center justify-between text-xs">
              <span className="text-[var(--color-muted)]">{label[lang] || label.en}</span>
              <span className="font-mono font-bold text-[var(--color-text)]">
                {params[key]} <span className="font-normal text-[var(--color-muted)]">{unit}</span>
              </span>
            </div>
            <input
              type="range"
              min={min}
              max={max}
              step={step}
              value={params[key]}
              onChange={e => setParams(prev => ({ ...prev, [key]: parseFloat(e.target.value) }))}
              className="w-full h-1.5 rounded-full appearance-none cursor-pointer
                bg-[var(--color-border)] accent-[var(--color-primary)]
                [&::-webkit-slider-thumb]:appearance-none
                [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                [&::-webkit-slider-thumb]:rounded-full
                [&::-webkit-slider-thumb]:bg-[var(--color-primary)]
                [&::-webkit-slider-thumb]:shadow-[0_0_6px_var(--color-primary)]
                [&::-webkit-slider-thumb]:transition-transform
                [&::-webkit-slider-thumb]:hover:scale-125"
            />
          </div>
        ))}
      </div>

      <p className="mt-3 text-[10px] text-[var(--color-muted)]">
        {lang === 'zh'
          ? '拖动滑块后自动重算（500ms 防抖）'
          : 'Auto-recalculates after slider change (500ms debounce)'}
      </p>
    </div>
  );
}
