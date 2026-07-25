/**
 * DynamicStage — 通用阶段渲染器
 *
 * 根据 stageDefinition.modules 动态加载并渲染模块组件。
 * 过滤 enabled: true 的模块，按 loadPriority 排序后交由 ModuleRenderer 渲染。
 * S6/F2: 接收父级传入的 conclusionData/isSummaryLoading 驱动 StageConclusion。
 *
 * Requirements: 1.2, 1.3, 11.3
 */

import FunnelStage from './FunnelStage';
import ModuleRenderer from './ModuleRenderer';

export default function DynamicStage({
  stageDefinition,
  stageNumber,
  config,
  lang,
  onVisible,
  conclusionData = null,
  isSummaryLoading = false,
}) {
  const enabledModules = stageDefinition.modules.filter(m => m.enabled);
  const sortedModules = [...enabledModules].sort((a, b) => a.loadPriority - b.loadPriority);

  return (
    <FunnelStage
      stageId={stageDefinition.id}
      stageNumber={stageNumber}
      title={stageDefinition.title[lang]}
      coreQuestion={stageDefinition.coreQuestion[lang]}
      isLoading={isSummaryLoading}
      conclusionData={conclusionData}
      onVisible={onVisible}
      lang={lang}
    >
      {sortedModules.map(moduleEntry => (
        <ModuleRenderer
          key={moduleEntry.component}
          moduleEntry={moduleEntry}
          config={config}
          lang={lang}
        />
      ))}
    </FunnelStage>
  );
}
