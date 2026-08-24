# 任务记录：AgentPage P0 七项修复

- 日期：2026-08-24
- 类型：前端缺陷修复 + 工程卫生（承接《Agent页面设计拆解与优化方案》P0 清单）
- 前置文档：`docs/design/Agent页面设计拆解与优化方案.md`、`docs/tasks/任务记录-2026-08-24-V2转正与信任组件落地.md`
- 范围纪律：全部改动集中在 `web/src/pages/AgentPage.jsx`（不拆文件，拆分属 P1 epic）；不动 SSE 事件结构

## 一、修复明细（实施顺序：#2 → #6 → #1+#4 → #3 → #5 → #7）

### #2 Enter 发送语义

- `handleKeyDown`：Enter 发送 / Shift+Enter 换行（Ctrl/Cmd+Enter 保留为别名路径）
- **IME 组合守门**：`isComposing` + keyCode 229 兜底——中文输入中 Enter 是候选确认而非发送（中文 UI 的主流路径，非边界 case）
- 发送时 `preventDefault()` 阻止换行插入；placeholder 与发送按钮 title 文案同批更新

### #6 历史条目 button 嵌套 button

- 外层 `<button>` → `<div role="button" tabIndex={0}>`（Enter/Space 键盘激活，`e.target !== e.currentTarget` 守门忽略删除按钮按键冒泡）
- 删除按钮 `span role="button"` → 平级真 `<button>`（保留 stopPropagation、绝对定位、hover 样式），补 `aria-label`

### #1 AuditTimeline 页级唯一（含原缺陷修复）

- 移除 AssistantMessage/EvidencePanel 的 `audit` prop 传递链与轨迹 tab 内的重复实例（原 N 条消息 = N 份同一审计日志）
- 页级 `<AuditTimeline>` 渲染在对话滚动区内、**messages 三元分支之外**——清空对话后消息区为空，审计仍可见、撤销仍可达
- 这修复了一个审查时未发现的既有缺陷：原实现下「清空对话」后审计随消息一起消失，撤销入口在最需要时不可见
- **保留** `onAudit={audit.log}` 经 AssistantMessage → EvidencePanel → ReportView 的通道（PDF 导出审计依赖）

### #4 报告到达不抢 tab

- EvidencePanel 增加 `userTouched` 标记：用户手动点过 tab 后，报告到达不再强制切换
- 历史回载消息带 report 挂载时 untouched → 仍自动切（保持原行为）
- 报告就绪「●」指示渲染在报告 tab 上（含流式期间 disabled 态，否则指示不可见）

### #3 sticky-bottom 滚动

- `pinnedRef` + scroll 监听：距底 ≤80px 视为贴底；仅贴底时流式跟随，向上翻历史不再被拽走
- 非贴底时对话区底部浮出「↓ 回到最新」按钮（滚动容器外包一层 relative wrapper，浮钮不随内容滚动）
- 整批替换场景强制回贴：发送、清空对话、历史回载、审计撤销、重试

### #5 错误归属 + 重试（语义先定死）

- 全局 error 条移除；流式/SSE 错误只归属所属消息，附「↺ 重试」按钮（streaming 时 disabled；手动停止 aborted 不提供）
- **重试语义**：`stripFailedTurn`（抽至 `web/src/lib/agentChatSupport.js`）成对移除失败 assistant 及其前一条 user，再用原文重发——
  `historyPayload` 从 messages 全量重建，只删 assistant 会让该 user turn 在 history 尾部 + query 中双发污染多轮上下文；
  部分流式回答随失败消息丢弃；`sendMessage` 增加 `baseMessages` 参数避开闭包旧值
- 重试按当前区域与参数执行（接受语义，按钮 title 已注明）
- 侧栏失败不静默：删除/清空历史失败改由历史区 `sidebarError` 本地提示（下次操作清除）

### #7 死状态清理 + lint 清偿

- `market` state 删除 → 由 region 派生（`region === 'WEM' ? 'WEM' : 'NEM'`）；请求参数行为不变
- `toolMode` state、`TOOL_MODES` 常量、请求 spread 全删（UI 从未渲染控件、setToolMode 无调用方）；
  后端 `enable_tool_routing`/`tool_profile` 能力保留，未来重开只需新增控件；`MARKETS` 无引用常量一并删除
- lint 5 error → 0：sessionIdRef 渲染期写 ref → `useState(newSessionId)` 惰性初始化，**三处写入全部迁移**
  （初始化、handleReset 轮转、handleLoadHistory 续接）；refreshHistory 声明前使用 → 定义前移；memoization 警告随依赖修正消除
- 顺带修：清空对话撤销现同时恢复原 session_id（原实现撤销后对话脱离原历史分组）

## 二、验证结果

| 验证项 | 结果 |
|---|---|
| npm test（vitest） | ✅ 66/66（基线 57 + 新增守门 9） |
| npm run test:node | ✅ 317/317 |
| eslint（AgentPage + 新文件） | ✅ 0 error / 0 warning（存量 5 error 清偿） |
| npm run build | ✅ 构建成功 |
| check_bundle_budget.mjs | ✅ PASS：入口 raw 788.6KB ≤ 850KB（与修复前持平） |

新增守门（`web/src/components/agent/__tests__/agentP0Guards.test.jsx`，9 项）：
stripFailedTurn 成对裁剪/不可变/未命中 ×4；报告不抢手动 tab + ● 指示、未触碰仍自动切 ×2；
Enter 发送/Shift+Enter 不发送、清空后审计可撤销、重试不双发 history ×3。
其中重试用例断言第二次请求 `history` 为空 + `query` 为原文——直接守门双发缺陷。

EvidencePanel 为供守门改为具名导出（组件导出不触发 react-refresh 告警）；
stripFailedTurn 放 `src/lib/agentChatSupport.js`（页面文件只导出组件，规避 fast-refresh 告警）。

## 三、审查质疑的落实（structured-questioner 独立挑战）

- 审计移位破坏清空后可见性 → 已按「三元分支之外渲染」修复（并发现这是既有缺陷）
- 重试双发 user turn → 成对裁剪 + baseMessages 参数 + 守门测试断言
- sessionId 三处写入漏迁移 → 全部迁移 + 撤销恢复旧 session_id
- 侧栏失败静默 → sidebarError 本地提示同批落地
- tool-routing 灰度 → 保守处理：仅删 UI 死状态，后端能力保留并注释登记

## 四、遗留后续任务（P1/P2，见设计方案）

1. P1 epic：会话级工作台重构（对话流 + 常驻证据工作区，消灭消息内双栏与双滚动嵌套）
2. P1：结论先行 ConclusionCard、参数可见性 chips、顶栏两层化、导出链三跳→一步、EscalationCard 点击即发送
3. P2：侧栏 token 化/历史搜索、Composer 自动增高、对比视图入工作区、字号/图标收敛、文件拆分 + token 合帧

## 五、文件清单

新增：`web/src/lib/agentChatSupport.js`、`web/src/components/agent/__tests__/agentP0Guards.test.jsx`、
`docs/design/Agent页面设计拆解与优化方案.md`（此前产出，本次入库）、本文档

修改：`web/src/pages/AgentPage.jsx`（1790 → 1890 行，+守门导出与注释）、
`docs/tasks/任务记录-2026-08-24-V2转正与信任组件落地.md`（补第八节推送验证记录）
