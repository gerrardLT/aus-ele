/**
 * AnomalyBadge — U4: 异常主动推送徽章
 *
 * 轮询 /api/v1/anomalies，有异常时在 Context Bar 显示脉冲红点。
 * 点击展开下拉列表，可跳转对应分析阶段。
 */

import { useState, useRef, useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { motion, AnimatePresence } from 'framer-motion';
import { AlertTriangle, Zap, TrendingDown, X } from 'lucide-react';
import { useFilters } from '../contexts/FilterContext';
import { getApiBase } from '../lib/apiBase';

const API_BASE = getApiBase();

const TYPE_ICONS = {
  price_spike: Zap,
  fcas_collapse: TrendingDown,
  negative_price_frequency: AlertTriangle,
};

export default function AnomalyBadge({ lang = 'zh', onNavigate }) {
  const { filters } = useFilters();
  const [open, setOpen] = useState(false);
  const ref = useRef(null);

  const { data } = useQuery({
    queryKey: ['anomalies', filters.region, filters.year],
    queryFn: async () => {
      const res = await fetch(`${API_BASE}/api/v1/anomalies/${filters.region}?year=${filters.year || 2025}`);
      return res.json();
    },
    refetchInterval: 5 * 60 * 1000, // 5 min
    enabled: !!filters.region,
  });

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e) {
      if (ref.current && !ref.current.contains(e.target)) setOpen(false);
    }
    document.addEventListener('mousedown', handleClick);
    return () => document.removeEventListener('mousedown', handleClick);
  }, []);

  const anomalies = data?.anomalies || [];
  if (anomalies.length === 0) return null;

  return (
    <div className="relative" ref={ref}>
      {/* Pulse badge */}
      <button
        onClick={() => setOpen(!open)}
        className="relative flex items-center justify-center w-7 h-7 rounded-full border border-[var(--color-status-error)]/50 bg-red-500/10 hover:bg-red-500/20 transition-colors"
        aria-label={`${anomalies.length} anomalies detected`}
      >
        <motion.span
          animate={{ scale: [1, 1.3, 1], opacity: [0.7, 0.3, 0.7] }}
          transition={{ repeat: Infinity, duration: 2 }}
          className="absolute w-2 h-2 rounded-full bg-red-500"
        />
        <span className="text-[10px] font-bold text-red-500">{anomalies.length}</span>
      </button>

      {/* Dropdown */}
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0, y: -4, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -4, scale: 0.95 }}
            className="absolute right-0 top-9 z-50 w-72 rounded-xl border border-[var(--color-border)] bg-[var(--color-panel)] p-3 shadow-xl panel-glass"
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-[10px] font-bold uppercase tracking-wider text-[var(--color-muted)]">
                {lang === 'zh' ? '市场异常' : 'Market Anomalies'}
              </span>
              <button onClick={() => setOpen(false)} className="text-[var(--color-muted)] hover:text-[var(--color-text)]">
                <X size={12} />
              </button>
            </div>
            <div className="space-y-2">
              {anomalies.map((a, i) => {
                const Icon = TYPE_ICONS[a.type] || AlertTriangle;
                return (
                  <button
                    key={i}
                    onClick={() => { onNavigate?.(a.related_stage); setOpen(false); }}
                    className="w-full flex items-start gap-2 rounded-lg p-2 text-left hover:bg-[var(--color-surface-hover)] transition-colors"
                  >
                    <Icon size={14} className={a.severity === 'high' ? 'text-red-500 mt-0.5' : 'text-amber-500 mt-0.5'} />
                    <div>
                      <p className="text-xs text-[var(--color-text)]">{a.description}</p>
                      <p className="text-[10px] text-[var(--color-muted)] mt-0.5">
                        {a.severity} · {a.timestamp}
                      </p>
                    </div>
                  </button>
                );
              })}
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
