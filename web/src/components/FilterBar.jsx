/**
 * FilterBar — 筛选器控件组件
 *
 * 渲染 region、年份、季度、日类型筛选按钮。
 * 通过 FilterContext 读写状态。
 *
 * Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6
 */

import { useState, useRef } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { useFilters } from '../contexts/FilterContext';
import { translations } from '../translations';

const QUARTERS = ['ALL', 'Q1', 'Q2', 'Q3', 'Q4'];
const DAY_TYPES = ['ALL', 'WEEKDAY', 'WEEKEND'];

export default function FilterBar({ config, years, lang }) {
  const { filters, setFilter } = useFilters();
  const [showAdvanced, setShowAdvanced] = useState(true);
  const isFirstRender = useRef(true);
  const t = translations[lang]?.filters || {};

  const btnBase = 'px-3.5 py-1.5 min-h-[36px] text-[13px] font-sans transition-colors rounded-full border';
  const btnActive = 'bg-[var(--color-inverted)] text-[var(--color-inverted-text)] border-[var(--color-inverted)]';
  const btnInactive = 'bg-transparent text-[var(--color-text)] border-[var(--color-border)] hover:border-[var(--color-text)]';

  return (
    <div className="rounded-3xl border border-[var(--color-border)] bg-[var(--color-bg)]/80 backdrop-blur-md p-4">
      {/* Primary row: Year + Region */}
      <div className="flex flex-col gap-3 xl:flex-row xl:items-center xl:justify-between">
        <div className="flex flex-col gap-3 xl:flex-row xl:items-center">
          {/* Year buttons */}
          <div className="flex flex-col gap-2">
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
              {t.yearSelect || 'YEAR'}
            </span>
            <div className="flex flex-wrap gap-2">
              {years.map(y => (
                <button
                  key={y}
                  onClick={() => setFilter('year', y)}
                  className={`px-3 py-1 text-xs rounded-full ${
                    filters.year === y ? btnActive : `border border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]`
                  }`}
                >
                  {y}
                </button>
              ))}
            </div>
          </div>

          {/* Region buttons */}
          <div className="flex flex-col gap-2 xl:ml-6">
            <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
              {t.regionSelect || 'REGION'}
            </span>
            <div className="flex flex-wrap gap-2">
              {config.regions.map(r => (
                <button
                  key={r}
                  onClick={() => setFilter('region', r)}
                  className={`px-3 py-1 text-xs font-mono rounded-full border ${
                    filters.region === r ? btnActive : 'border-[var(--color-border)] text-[var(--color-muted)] hover:text-[var(--color-text)]'
                  }`}
                >
                  {r.replace('1', '')}
                </button>
              ))}
            </div>
          </div>
        </div>

        {/* Toggle advanced filters */}
        <button
          onClick={() => setShowAdvanced(prev => !prev)}
          className="rounded-full border border-[var(--color-border)] px-4 py-2 text-xs font-bold uppercase tracking-[0.18em] text-[var(--color-text)] transition-colors hover:border-[var(--color-text)] xl:self-start"
        >
          {showAdvanced ? (lang === 'zh' ? '收起筛选' : 'Hide Filters') : (lang === 'zh' ? '更多筛选' : 'More Filters')}
        </button>
      </div>

      {/* Advanced filters: Quarter + DayType */}
      <AnimatePresence>
        {showAdvanced && (
          <motion.div
            // eslint-disable-next-line react-hooks/refs -- initial is only consumed on mount
            initial={isFirstRender.current ? false : { height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
            onAnimationComplete={() => { isFirstRender.current = false; }}
          >
            <div className="mt-4 border-t border-dashed border-[var(--color-border)] pt-4 flex flex-col gap-4 md:flex-row md:gap-8">
              {/* Quarter */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
                  {t.quarterSelect || 'QUARTER'}
                </span>
                <div className="flex flex-wrap gap-2">
                  {QUARTERS.map(q => (
                    <button
                      key={q}
                      onClick={() => setFilter('quarter', q)}
                      className={`${btnBase} ${filters.quarter === q ? btnActive : btnInactive}`}
                    >
                      {q === 'ALL' ? (t.allQuarters || 'ALL') : (t[q.toLowerCase()] || q)}
                    </button>
                  ))}
                </div>
              </div>

              {/* Day Type */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold uppercase tracking-[0.18em] text-[var(--color-muted)]">
                  {t.dayTypeSelect || 'DAY TYPE'}
                </span>
                <div className="flex flex-wrap gap-2">
                  {DAY_TYPES.map(d => (
                    <button
                      key={d}
                      onClick={() => setFilter('dayType', d)}
                      className={`${btnBase} ${filters.dayType === d ? btnActive : btnInactive}`}
                    >
                      {d === 'ALL' ? (t.allDays || 'ALL') : (t[d.toLowerCase()] || d)}
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
