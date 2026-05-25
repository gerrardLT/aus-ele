/**
 * FunnelStage — 决策漏斗阶段容器
 *
 * 每个 FunnelStage 代表决策漏斗中的一个分析阶段，包含：
 * - 阶段头部：编号徽章 + 标题 + 核心问题（中文主体 + 英文注释）
 * - StageConclusion 面板（阶段结论）
 * - 子模块列表（CollapsibleModule 实例）
 * - "展开全部 / 收起全部" 切换按钮
 * - 滚动可见性检测（IntersectionObserver，用于 scroll-spy）
 * - 去强调状态（opacity-60，当后续阶段不再相关时）
 *
 * Requirements: 1.4, 4.4, 8.1, 8.2, 8.3
 */

import { useRef, useEffect, useState } from 'react';
import StageConclusion from './StageConclusion';

/**
 * 阶段编号 → 加载消息映射（双语）
 */
const LOADING_MESSAGES = {
  zh: {
    1: '正在分析价格趋势与套利空间...',
    2: '正在识别最优交易窗口...',
    3: '正在模拟储能收入...',
    4: '正在计算投资回报指标...',
    default: '正在加载数据...',
  },
  en: {
    1: 'Analyzing price trends and arbitrage spread...',
    2: 'Identifying optimal trading windows...',
    3: 'Simulating battery revenue...',
    4: 'Calculating investment return metrics...',
    default: 'Loading data...',
  },
};

export default function FunnelStage({
  stageId,
  stageNumber,
  title,
  coreQuestion,
  coreQuestionEn,
  children,
  conclusionData,
  isLoading,
  isDeemphasized,
  onVisible,
  lang = 'zh',
}) {
  const stageRef = useRef(null);
  const [allExpanded, setAllExpanded] = useState(false);

  // IntersectionObserver: 检测阶段进入视口，用于 scroll-spy 导航高亮
  useEffect(() => {
    const el = stageRef.current;
    if (!el || typeof onVisible !== 'function') return;

    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          onVisible(stageId);
        }
      },
      { rootMargin: '-20% 0px -60% 0px', threshold: 0 }
    );

    observer.observe(el);
    return () => observer.disconnect();
  }, [stageId, onVisible]);

  function handleToggleAll() {
    setAllExpanded((prev) => !prev);
  }

  const messages = LOADING_MESSAGES[lang] || LOADING_MESSAGES.zh;
  const loadingMessage = messages[stageNumber] || messages.default;

  return (
    <section
      ref={stageRef}
      id={stageId}
      className={`scroll-mt-16 transition-opacity duration-300 ${
        isDeemphasized ? 'opacity-60' : ''
      }`}
      aria-label={`${lang === 'zh' ? '阶段' : 'Stage'} ${stageNumber}: ${title}`}
    >
      {/* StageConclusion 面板 */}
      <StageConclusion
        data={conclusionData}
        isLoading={isLoading}
        loadingMessage={loadingMessage}
      />

      {/* 子模块容器 — 紧凑间距 */}
      <div className="space-y-2">
        {children}
      </div>
    </section>
  );
}
