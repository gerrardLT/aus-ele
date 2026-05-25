/**
 * StageConclusion — 阶段结论面板
 *
 * 展示每个 FunnelStage 的核心结论：一句话摘要 + 2-4 个 KPI 指标卡片。
 * 根据 sentiment 应用左边框颜色（正向绿/负向红/中性灰）。
 * 加载态显示描述性消息和骨架动画。
 *
 * Requirements: 3.1, 3.2, 3.3, 3.4
 */

import KpiCard from './KpiCard';

/**
 * sentiment → 左边框颜色映射
 */
const BORDER_COLOR_MAP = {
  positive: 'border-l-[#22C55E]',  // var(--color-positive)
  negative: 'border-l-[#E53E3E]',  // var(--color-error)
  neutral: 'border-l-[var(--color-border)]',
};

function getBorderColor(sentiment) {
  return BORDER_COLOR_MAP[sentiment] || BORDER_COLOR_MAP.neutral;
}

/**
 * 加载态骨架组件
 */
function LoadingSkeleton({ loadingMessage }) {
  return (
    <div className="border-l-4 border-l-[var(--color-border)] pl-4 py-3 animate-pulse">
      {/* 加载消息 */}
      <p className="font-serif text-base text-[var(--color-muted)]">
        {loadingMessage}
      </p>

      {/* 骨架 KPI 卡片 */}
      <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
        {[1, 2, 3].map((i) => (
          <div
            key={i}
            className="border border-[var(--color-border)] rounded-lg p-4"
          >
            <div className="h-3 w-16 bg-[var(--color-border)] rounded mb-2" />
            <div className="h-5 w-12 bg-[var(--color-border)] rounded" />
          </div>
        ))}
      </div>
    </div>
  );
}

export default function StageConclusion({ data, isLoading, loadingMessage }) {
  // 加载态
  if (isLoading) {
    return <LoadingSkeleton loadingMessage={loadingMessage} />;
  }

  // 无数据时不渲染（动态渲染模式下结论由各模块自行展示）
  if (!data) {
    return null;
  }

  const { summary_text, kpis, sentiment } = data;
  const borderClass = getBorderColor(sentiment);

  return (
    <div className={`border-l-4 ${borderClass} pl-4 py-3`}>
      {/* 一句话摘要 — serif 字体 (Playfair Display) */}
      <p className="font-serif text-base text-[var(--color-text)]">
        {summary_text}
      </p>

      {/* KPI 卡片行 */}
      {kpis && kpis.length > 0 && (
        <div className="mt-3 grid grid-cols-2 gap-3 md:grid-cols-4">
          {kpis.map((kpi, index) => (
            <KpiCard
              key={`${kpi.label}-${index}`}
              label={kpi.label}
              value={kpi.value}
              unit={kpi.unit}
              sentiment={kpi.sentiment}
              size="sm"
            />
          ))}
        </div>
      )}
    </div>
  );
}
