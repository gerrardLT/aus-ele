# Agent 页面设计拆解与优化方案（2026-08-24）

> 对象：`web/src/pages/AgentPage.jsx`（1790 行）+ `web/src/components/agent/*`（6 信任组件）
> + `ExportPreviewModal.jsx`。方法：按「结构层 → 交互层 → 内容层 → 工程质量」逐块
> 拆解现状、指出问题、给出更优方案与优先级。结论摘要见文末第五节。

---

## 一、现状结构拆解

```
AgentPage（状态容器，~30 个 useState/useRef）
└── AgentLayout（纯视图，35 个 props）
    ├── 左侧栏 aside（220px，硬编码深色 #13161A）
    │   ├── Brand（AEMO Intelligence / 天枢）
    │   ├── 导航 <a href>（NEM/WEM/Finland/开发者门户）← 全页刷新跳转
    │   └── 执行历史（会话分组，最近 10 条）
    └── 主列（flex-col，h-screen）
        ├── 顶栏（标题｜区域 select｜AutonomyDial｜工作流 chips｜BESS 参数｜新对话｜返回）
        ├── BESS 参数面板（4 个 slider，可折叠）
        ├── 对话区（overflow-y-auto，强制自动滚底）
        │   ├── ComparisonPanel（对比视图，置顶）
        │   └── 消息流 max-w-1200/1360
        │       ├── UserBubble
        │       └── AssistantMessage
        │           ├── status_line（脉冲小圆点）
        │           ├── DegradedBanner / EscalationCard / PlanView
        │           └── 消息内双栏 grid [1fr | 420-520px]
        │               ├── 左栏：KPI 卡（≤4）+ 推理过程 Collapsible（默认展开）+ error
        │               └── 右栏：EvidencePanel（max-h-600 内滚）
        │                   ├── 轨迹 tab：ToolTrace + AuditTimeline
        │                   ├── 图表 tab：ChartRenderer[]
        │                   └── 报告 tab：ReportView（状态条/导出/RationalePanel/各节/Footer）
        └── Composer（textarea rows=2 固定 + 右下角 28px 发送/停止按钮）
```

关键事实：SSE 事件（start/status/token/tool_call/tool_result/plan/report/error/done）
全部 patch 到「当前流式消息」对象上；后端无状态，每轮全量回传 history。

---

## 二、逐模块分析

### 1. 布局模型：「每条消息自带双栏工作区」⭐ 最核心问题

**现状**：每条 AssistantMessage 内部都是 `xl:grid-cols-[1fr,420-520px]` 双栏，
EvidencePanel `max-h-600` 内滚，对话区外滚 → **双层滚动嵌套**；多轮追问时每轮
报告/轨迹独立堆叠，页面无限变长。

**问题**：
- 追问后「当前分析」失去视觉锚点：最新一轮的证据与历史轮平权混排；
- 用户向上翻历史时，流式输出把视图拉走（见 §6.3）；
- EvidencePanel 600px 内滚 + 外层滚动 = 两套滚动条互相打架，报告长内容体验差；
- 对比面板（ComparisonPanel）被新消息推走、消失于视野（见 §9）。

**更优方案：会话级工作台模型（对话流 + 常驻证据工作区）**
参考业界 agentic 产品（Canvas/Artifacts 模式）：

```
┌ 侧栏 220 ┬──── 对话流（轻）────┬─── 证据工作区（常驻，sticky）───┐
│ 会话历史  │ 用户问 / AI 答摘要卡 │  Tabs: 轨迹 | 图表 | 报告 | 审计 │
│（可搜索） │ 点某轮 → 工作区切换  │  显示所选中那轮的完整证据        │
└──────────┴─────────────────────┴──────────────────────────────┘
```

- 对话流只留「问答 + 结论摘要卡（状态/置信/KPI 三行）」，高度可控；
- 证据工作区**页级唯一、不随消息堆叠**，默认跟随最新轮，点历史消息可回看该轮；
- 审计时间线移入工作区第 4 个 tab（页级数据，天然归位）；
- 消灭双滚动嵌套：工作区独立滚动，对话流独立滚动，互不干扰。

**优先级：P1（结构性，建议作为重构主轴）**

---

### 2. 左侧栏

| 细节 | 问题 | 更优方案 |
|---|---|---|
| 硬编码 `bg-[#13161A]`/`text-white/60` | 不随 light/dark/print 主题，与主列 token 体系割裂 | 全部改 `var(--color-*)` token |
| 导航用 `<a href>` | SPA 里触发整页刷新，丢失对话状态 | 换 React Router `<Link>`（或把返回入口收敛到顶栏一处） |
| 历史仅最近 10 条、无搜索 | 多会话用户找不到旧分析 | 「加载更多」+ 文本过滤 + 日期分组（今天/昨天/更早） |
| 删除按钮 `span role=button` **嵌套在 button 内** | HTML 非法嵌套（交互按钮里套按钮），键盘/读屏语义错乱 | 重构条目结构：删除按钮改为兄弟节点 + hover 显示（见 §12.1） |
| 加载历史**直接替换**当前对话、无确认 | 用户正在输入的内容上下文被静默换掉 | 切换会话前若当前有消息 → 统一确认弹窗；或做成真正的多会话模型（会话列表即上下文本身） |
| 清空全部用 `window.confirm` | 原生弹窗脱离设计体系，且本站刚建了 IntentPreview 摩擦点范式 | 复用 IntentPreview 或统一 ConfirmDialog |

**优先级：嵌套按钮 P0；其余 P2**

### 3. 顶栏与上下文控制

**现状**：一行 flex-wrap 塞了 7 类元素——标题、区域 select、AutonomyDial（4 档）、
工作流 chips（数量不定）、BESS 参数开关、新对话、返回市场。

**问题**：
- 窄屏 wrap 后次序混乱，「新对话/返回」与「区域」这类不同性质的控制混排；
- **Autonomy Dial 是未接线的界面偏好**（组件注释已登记），却占据顶栏一级位置，
  用户会以为它影响执行 → 信任透支；
- `TOOL_MODES`（8 个工具子集）有 state 有 props 下发，但**页面上根本没有渲染
  任何控件**（lint 已报 toolMode/setToolMode unused）——死状态，纯噪音；
- `market` state 已由 region 推导（代码注释自己承认冗余），仍占一个 state 并下发
  （lint 报 market unused）。

**更优方案**：
- 顶栏分职责两层：**上下文层**（标题·区域·会话名）与**动作层**（新对话·设置·返回）；
- 工作流快捷方式移到 EmptyState 的起始卡片（空态本来就是它的舞台），顶栏只留
  「⚡ 工作流」下拉；
- Autonomy Dial 降级：后端门控接线前移入「实验特性」弹层并加 beta 标注，或禁用态
  + tooltip 说明「执行门控待后端契约」——**诚实性优先于功能展示**；
- 删除 `market`/`toolMode` 死状态；工具子集如需保留，收进「高级选项」折叠区。

**优先级：死状态清理 P0；顶栏重排 P1；拨盘降级 P1**

### 4. BESS 参数面板

**问题**：
- 参数语义是「下一次发送时覆盖」，但**改参数没有任何可见反馈**——用户不知道
  下一轮会用什么参数，也不知道已发送的消息用了什么参数；
- slider 无直接输入框，精确设值（如 CAPEX 387）只能拖；
- 无「恢复默认」入口。

**更优方案**：
- Composer 上方加**上下文 chips 条**：`NSW1 · 100MW/4h · CAPEX 400 · 折现 8%`，
  改参数即时更新，点 chip 可跳回面板；
- 每条消息头部渲染「该轮使用的参数快照」（可折叠），追问时参数变更一目了然；
- slider + 数字输入双控件；加「恢复默认」。

**优先级：P1（参数不可见是分析类产品的大忌）**

### 5. 消息结构与内容层级

**问题**：
- **结论被埋在过程里**：消息先渲染 status_line → KPI → 推理过程（默认展开、最大
  360px 内滚），结论/报告在右侧 tab 里还要点一下。分析产品应「结论先行」；
- **同类信息默认态相反**：消息左栏「推理过程」默认展开，ReportView 里
  RationalePanel「查看推理轨迹」默认折叠——同一份 trace 数据、两种相反的默认态，
  且是重复展示（去重原则自己定的，这里破了）；
- UserBubble/AssistantMessage 均无操作条：不能复制、不能编辑重发、不能重跑；
- 置信徽章只在报告内「综合建议」节，消息级的状态行没有置信信号。

**更优方案**：
- 消息重排为：**结论摘要卡**（状态徽章 + ConfidenceBadge + KPI 三行）→ 可展开的
  完整回答 → 证据入口。推理默认折叠（v2 规格本来如此）；
- 删除 RationalePanel 在报告内的重复实例（工作区轨迹 tab 是唯一展示位）；
- 消息 hover 操作条：复制 / 编辑重发（用户消息）/ 重跑（助手消息）/ 从该轮重开；
- ConfidenceBadge 提升到结论摘要卡。

**优先级：结论先行 + 去重 P1；操作条 P2**

### 6. 流式交互细节

| # | 细节 | 问题 | 更优方案 |
|---|---|---|---|
| 6.1 | **Ctrl+Enter 发送**，Enter 换行 | 违背所有主流聊天产品肌肉记忆（Enter 发送 / Shift+Enter 换行） | Enter 发送、Shift+Enter 换行 |
| 6.2 | textarea `rows=2` 固定、`resize-none` | 长问题只能在小窗内滚 | 自动增高（上限 ~8 行） |
| 6.3 | `useEffect([messages])` **无条件滚底** | 用户向上翻看历史时，流式 token 把视图拽回底部 | 「sticky bottom」：仅在用户贴底时跟随；离开底部出现「↓ 回到最新」浮钮 |
| 6.4 | 停止按钮 = 输入框右下 28px 的 ■ | 可发现性差；停止后行为（保留部分结果？）无反馈 | streaming 时发送区变为醒目的「停止生成」；停止后消息标注「已停止 · 已保留部分结果」+ 继续/重试 |
| 6.5 | status_line 只有一行小字 | 15 步 × 秒级的长分析没有耗时感知与预期管理 | 状态行 = 当前步骤名 + 已耗时 + `n/N` 进度（数据已有：totalSteps/doneCount） |
| 6.6 | 错误两处展示（Composer 上方 + 消息内），且**无重试入口** | 失败后用户只能手动重打一遍问题 | 错误归属到所属消息，附「重试」按钮（重发同一 query）；去掉全局 error 条 |
| 6.7 | 每个 token 触发全量 `messages.map()` patch | 长对话 + 高频 token 时 O(n) 全树重渲染，卡顿随会话增长 | token 按 rAF 批量合帧；流式消息隔离为独立订阅（工作区重构后自然达成） |

**优先级：6.1/6.3/6.6 P0；6.4/6.5 P1；6.2/6.7 P2**

### 7. EvidencePanel

**问题**：
- `useEffect(() => { if (report) setTab('report') }, [report])` **抢焦点**：用户
  正在看轨迹，报告到达瞬间被切走；
- 轨迹 tab 内 args 用 `truncate` 单行 + title 悬浮——审计透明化打了折扣；
- 报告 tab 内又嵌一层 `max-h-600` 滚动 + 边框卡片，视觉层级过深。

**更优方案**：
- 报告就绪只在 tab 上显示「● 报告就绪」指示，**不抢用户当前 tab**（仅当用户
  从未手动选过 tab 时才自动切换）；
- args 改为可展开的代码块（默认折叠，展开全量 JSON + 复制）；
- 工作区化后去掉 600px 内滚，报告占满工作区滚动。

**优先级：抢 tab P0（一行代码的修复）；其余随工作区重构**

### 8. 报告与导出流

**问题**：
- 导出链 **三跳**：导出 PDF → IntentPreview → ExportPreviewModal → 确认导出。
  Intent Preview 的 v2 语义是「不可逆操作前的摩擦点」，而 PDF 导出可重复生成、
  并非不可逆——摩擦用错了地方；
- 预览固定 794px 宽，小屏横向滚动，无缩放；
- 报告内 KPI 仅打印可见（屏幕唯一展示位在左栏）——逻辑正确但读者难理解「为什么
  屏幕上报告里没有 KPI」。

**更优方案**：
- 导出收敛为**一步**：点「导出 PDF」直接开预览弹窗；Intent Preview 保留给真正
  不可逆的动作（清空历史、未来的「执行/下单」类动作）。或把意图预览做成弹窗首屏
  的一个步骤条，而不是独立一层遮罩；
- 预览加缩放（fit-width / 100%）；
- 报告内 KPI 保持打印-only，但在报告头加一行「KPI 见左栏摘要卡」指引（工作区化
  后此问题自然消失）。

**优先级：导出链简化 P1；其余 P2**

### 9. 对比功能

**问题**：ComparisonPanel 挂在对话流顶部——新消息进来自动滚底后它直接消失；
`handleCompare` 超过 2 个时**静默丢弃最旧的**（`[prev[1], report]`），用户无感知。

**更优方案**：对比视图改为右侧抽屉/工作区的一个模式（与轨迹/报告平级的
「对比」tab）；第 3 个加入时 toast 提示「已替换最旧的对比项」。

**优先级：P2**

### 10. 信任组件落位 ⭐ 含一处明显缺陷

- **AuditTimeline 重复渲染（缺陷）**：`audit` prop 传给**每条** AssistantMessage，
  EvidencePanel 在每条消息的轨迹 tab 里都渲染同一个审计时间线——N 条消息 = N 份
  重复的同一份审计日志。且「清空对话」是页级操作，埋在首条消息的 tab 里找不到。
  **修复**：审计是页级数据，移入证据工作区第 4 个 tab（或侧栏底部），全页唯一实例。
- **AutonomyDial** 见 §3：未接线前不应占据顶栏一级位置。
- **EscalationCard**：点选项只是 `setInput(text)` 填进输入框、不发送——澄清问答
  多了一步手动发送。改为点击即发送（作为用户消息），保留编辑能力给「修改计划」。
- **ConfidenceBadge**：见 §5，提升到消息结论摘要卡。

**优先级：审计重复渲染 P0；Escalation 点击即发送 P1；其余见对应章节**

### 11. 可访问性与视觉体系

- 字号层级过密：10/10.5/11/12/13px 五档小字混用，信息密度过高、可读性差。
  建议收敛为三档（11 标签 / 13 正文 / 15 强调），关键数字用 `--font-mono-data`；
- 图标体系混杂：emoji 字符（✓ ⚠ ✕ ● ↺ ⏱ ▲ ■ ↓）与内联 svg 混用，跨平台渲染
  不一致。建议统一为 lucide-react（依赖已在）或一套自有 svg 集；
- 状态色双编码执行良好（色+图标恒同时出现），继续保持；
- 侧栏历史条目无 `aria-current`、tab 无 `role="tablist"` 语义，键盘导航缺失。

**优先级：P2（图标统一可随重构顺带做）**

### 12. 工程质量

- **单文件 1790 行、20+ 组件**：AgentPage.jsx 承载状态容器 + 布局 + 消息 + Markdown
  渲染器 + 报告视图。建议拆分：
  `pages/AgentPage.jsx`（状态容器，<400 行）
  + `components/agent/chat/`（Composer/MessageStream/UserBubble/AssistantMessage）
  + `components/agent/workspace/`（EvidenceWorkspace/ToolTrace/ReportView）
  + `components/agent/markdown/`（MarkdownText/Table/inline）；
- Markdown 渲染器手写（~150 行）：当前够用，但流式表格/代码块边界 case 会持续
  长债；若引依赖需评估 bundle（入口预算 850KB，当前 788.6KB，余量有限）——
  维持手写 + 补测试是更稳的路线；
- lint 存量 5 error（sessionIdRef 渲染期写 ref、refreshHistory 声明前使用等）
  属本文件，重构时一并清偿。

---

## 三、目标架构（重构蓝图）

```
AgentPage（状态容器：useReducer 收敛 messages/session/params）
├── SessionSidebar        会话历史（token 化、搜索、日期分组、SPA Link）
├── ConversationPane      轻量对话流：UserBubble + ConclusionCard（摘要）+ 流式状态
├── EvidenceWorkspace     页级唯一、sticky：[轨迹|图表|报告|审计] + 选中轮次指示
├── ContextBar            Composer 上方：区域/参数/工作流 chips（可见、可点回）
└── Composer              自动增高、Enter 发送、streaming 时「停止生成」
```

数据流不变（SSE patch 当前消息），仅展示层重组；`messages` 结构增加
`paramSnapshot`（发送时冻结）支撑 §4 参数可见性。

## 四、实施优先级汇总

**P0（明显缺陷，小改动）**
1. AuditTimeline 重复渲染 → 页级唯一实例
2. Enter 发送 / Shift+Enter 换行
3. 自动滚底改 sticky-bottom（向上翻看不再被拽走）
4. EvidencePanel 报告到达不再抢用户当前 tab
5. 错误归属消息 + 重试按钮，去掉全局 error 条
6. 历史删除按钮的 button 嵌套 button 结构修复
7. 清理死状态：`market`、`toolMode`（未渲染）、lint 存量 5 error

**P1（结构性重构，建议作为一个 epic）**
8. 会话级工作台：对话流 + 常驻证据工作区（消灭消息内双栏与双滚动嵌套）
9. 结论先行：ConclusionCard（状态+置信+KPI），推理默认折叠，删 RationalePanel 重复实例
10. 参数可见性：上下文 chips 条 + 消息参数快照
11. 顶栏两层化：工作流移入空态/下拉，AutonomyDial 降级入实验特性
12. 导出链三跳 → 一步（IntentPreview 只留给真正不可逆动作）
13. EscalationCard 选项点击即发送

**P2（打磨）**
14. 侧栏 token 化 + 历史搜索/日期分组/加载更多；统一 ConfirmDialog
15. Composer 自动增高、停止按钮显化、耗时+步骤进度上状态行
16. 对比视图移入工作区 tab + 替换提示
17. 字号三档收敛、图标体系统一（lucide）、tablist 键盘导航
18. 文件拆分（12 节目录结构）+ token 批量合帧性能优化

## 五、一句话结论

页面「功能很全但组织失序」：证据散落在每条消息里、结论埋在过程之后、
控制项堆在一行顶栏、信任组件落位错位（审计重复渲染是最明显的缺陷）。
重构主轴 = **从「每条消息自带工作区」转向「会话级对话流 + 常驻证据工作区」**，
配合「结论先行、参数可见、交互顺肌肉记忆」三条原则，P0 七项可先行小步修复。
