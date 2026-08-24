/**
 * CollapsibleModule — 可折叠分析模块容器
 *
 * 用于 FunnelStage 内部，包裹各分析模块（PriceChart、FcasAnalysis 等）。
 * 折叠态显示标题 + 一行指标摘要；展开态显示完整模块内容。
 * 展开/折叠状态持久化到 sessionStorage。
 *
 * Requirements: 4.1, 4.2, 4.3, 4.5
 */

import { useState, useEffect, Suspense } from 'react';
import { motion, AnimatePresence } from 'framer-motion';
import { ChevronDown } from 'lucide-react';

/**
 * sessionStorage key 格式: funnel-module-{moduleId}
 */
function getStorageKey(moduleId) {
  return `funnel-module-${moduleId}`;
}

/**
 * 从 sessionStorage 读取持久化的展开状态。
 * 如果没有持久化值，返回 defaultExpanded。
 */
function loadPersistedState(moduleId, defaultExpanded) {
  try {
    const stored = sessionStorage.getItem(getStorageKey(moduleId));
    if (stored !== null) {
      return stored === 'true';
    }
  } catch {
    // sessionStorage 不可用时静默降级
  }
  return defaultExpanded;
}

/**
 * 将展开状态写入 sessionStorage。
 */
function persistState(moduleId, isExpanded) {
  try {
    sessionStorage.setItem(getStorageKey(moduleId), String(isExpanded));
  } catch {
    // sessionStorage 不可用时静默降级
  }
}

export default function CollapsibleModule({
  moduleId,
  title,
  metricSummary,
  defaultExpanded = false,
  lang = 'zh',
  children,
}) {
  const [isExpanded, setIsExpanded] = useState(() =>
    loadPersistedState(moduleId, defaultExpanded)
  );
  // 追踪是否曾经展开过（用于 lazy-loading）
  const [hasExpanded, setHasExpanded] = useState(() =>
    loadPersistedState(moduleId, defaultExpanded)
  );

  // 当 moduleId 变化时重新读取持久化状态
  useEffect(() => {
    const persisted = loadPersistedState(moduleId, defaultExpanded);
    setIsExpanded(persisted);
    if (persisted) {
      setHasExpanded(true);
    }
  }, [moduleId, defaultExpanded]);

  function handleToggle() {
    const next = !isExpanded;
    setIsExpanded(next);
    persistState(moduleId, next);
    if (next && !hasExpanded) {
      setHasExpanded(true);
    }
  }

  return (
    <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
      {/* 折叠行：标题 + 指标摘要 + 展开图标 */}
      <button
        type="button"
        className="w-full flex items-center p-4 cursor-pointer hover:bg-[var(--color-surface-hover)] transition-colors text-left"
        onClick={handleToggle}
        aria-expanded={isExpanded}
        aria-controls={`module-content-${moduleId}`}
      >
        {/* 标题 */}
        <span className="text-sm font-bold text-[var(--color-text)]">
          {title}
        </span>

        {/* 指标摘要 */}
        <span className="text-xs text-[var(--color-muted)] ml-auto mr-3">
          {metricSummary}
        </span>

        {/* Chevron 图标，展开时旋转 180° */}
        <motion.span
          animate={{ rotate: isExpanded ? 180 : 0 }}
          transition={{ duration: 0.2 }}
          className="flex-shrink-0 text-[var(--color-muted)]"
        >
          <ChevronDown size={16} />
        </motion.span>
      </button>

      {/* 展开内容区域 */}
      <AnimatePresence initial={false}>
        {isExpanded && (
          <motion.div
            id={`module-content-${moduleId}`}
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: 'auto', opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            transition={{ duration: 0.2 }}
            className="overflow-hidden"
          >
            <div className="mt-4 px-4 pb-4">
              {/* Suspense 包裹：支持 React.lazy 子组件的懒加载 */}
              <Suspense
                fallback={
                  <div className="h-32 flex items-center justify-center">
                    <span className="font-serif text-sm text-[var(--color-muted)]">
                      {lang === 'zh' ? '正在加载模块内容...' : 'Loading module content...'}
                    </span>
                  </div>
                }
              >
                {hasExpanded && children}
              </Suspense>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
