/**
 * KpiCard — 关键指标卡片组件
 *
 * 展示单个聚合数值及其语义状态。用于 ExecutiveSummary (md) 和 StageConclusion (sm)。
 * 纯 UI 组件，不包含数据获取逻辑。
 */

/**
 * 语义色映射：sentiment → Tailwind 颜色类
 */
const SENTIMENT_COLOR_MAP = {
  positive: 'text-[#22C55E]',  // var(--color-positive)
  negative: 'text-[#E53E3E]',  // var(--color-error)
  warning: 'text-[#F59E0B]',   // var(--color-warning)
  neutral: 'text-[var(--color-text)]',
};

/**
 * 根据 sentiment 返回对应的颜色类名。
 * 导出以便属性测试可以直接验证映射逻辑。
 */
export function getSentimentColor(sentiment) {
  return SENTIMENT_COLOR_MAP[sentiment] || SENTIMENT_COLOR_MAP.neutral;
}

export default function KpiCard({ label, value, unit, sentiment = 'neutral', onClick, size = 'md' }) {
  const colorClass = getSentimentColor(sentiment);
  const isClickable = typeof onClick === 'function';

  // 尺寸变体：md 用于 ExecutiveSummary，sm 用于 StageConclusion
  const valueSize = size === 'sm' ? 'text-lg' : 'text-2xl';

  const containerClasses = [
    'border border-[var(--color-border)] p-4 rounded-lg',
    isClickable && 'cursor-pointer hover:border-[var(--color-text)] transition-colors',
  ]
    .filter(Boolean)
    .join(' ');

  return (
    <div
      className={containerClasses}
      onClick={isClickable ? onClick : undefined}
      role={isClickable ? 'button' : undefined}
      tabIndex={isClickable ? 0 : undefined}
      onKeyDown={
        isClickable
          ? (e) => {
              if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                onClick();
              }
            }
          : undefined
      }
    >
      {/* 标签 */}
      <span className="block text-xs text-[var(--color-muted)] uppercase tracking-wider">
        {label}
      </span>

      {/* 数值 + 单位 */}
      <div className="mt-1 flex items-baseline">
        <span className={`${valueSize} font-bold font-mono glow-kpi ${colorClass}`}>
          {value ?? '--'}
        </span>
        {unit && (
          <span className="text-xs text-[var(--color-muted)] ml-1">
            {unit}
          </span>
        )}
      </div>
    </div>
  );
}
