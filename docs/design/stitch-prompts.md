# Stitch Prompt 包：AEMO Intelligence Agent 界面（2026-08-24 增补 v2）

> 用法：在 stitch.withgoogle.com 标准模式（Web 画布）逐屏生成；
> 依据 Stitch 最佳实践：**英文 prompt 生成更稳**，生成后可用中文指令微调语言/细节；
> 每次生成后对照 `docs/design/DESIGN-v2.md` 的 Do's and Don'ts 人工复核；
> 建议先在 Stitch 中导入本项目的 DESIGN-v2.md（Import design rules），使生成结果遵循 token；
> 校验命令：`npx -p @google/design.md designmd lint DESIGN-v2.md`（Windows 用 designmd 别名）。
> 每条 prompt 末尾的 ANTI-PATTERN 段是"防 AI 味"反模式指令（来源：Stitch 实践指南）。

---

## Screen 1：Agent Workspace — 对话流 + 证据面板（核心屏）

```
Design a dark-themed professional analytics web application screen: an AI agent workspace for electricity market investment analysis. Two-pane layout on desktop (min 1280px).

LEFT PANE (conversation): header with serif page title "AI 编排分析"; control bar with segmented market toggle (NEM / WEM), region dropdown, analysis-mode dropdown, and a row of pill-shaped workflow chips; below, a chat stream showing user messages and assistant messages; assistant messages contain streaming markdown analysis with key metrics; bottom input bar with textarea and a single high-contrast send button.

RIGHT PANE (evidence panel): tab bar with four tabs: Trace / Charts / Report / Evidence. Trace tab active: a vertical execution checklist, each item shows a status icon (green check, amber clock, red cross), a tool name label, a monospaced duration value, and a small retry counter; one item is highlighted as running with a subtle pulse.

Style: instrument-grade terminal aesthetic, dark blue-charcoal background (oklch hue ~260), three tonal surface layers instead of shadows, hairline 1px borders, monospaced tabular figures for ALL numbers, 4px corner radius on controls, 8px on cards, exactly ONE near-white filled primary button visible.

ANTI-PATTERN: no purple-blue gradients; no drop shadows; no emoji icons; no glassmorphism blur; no zebra-striped tables; no rounded-2xl bubbles; avoid identical linear-style icon sets repeated everywhere.
```

## Screen 2：执行清单三态细节（Dynamic Checklist 状态全集）

```
Design a component detail sheet on the same dark terminal theme: the agent execution checklist showing ALL possible step states stacked vertically:
1. completed step — green check icon, tool label "price_trend_analysis", monospaced "1.2s"
2. running step — pulsing dot, tool "market_screening", elapsed "12s" counting, highlighted background
3. pending step — hollow circle, muted label "investment_analysis"
4. timeout step — amber clock icon, "co_optimized_backtest", note "90s budget exceeded"
5. error step — red cross icon, "data_query", attribution note "价格表 trading_price_2025 尚未同步" (blames the external data source, not the AI)
6. cached step — muted refresh icon, "saturation_check", note "served from session cache"
Below the list: a collapsed "查看推理轨迹" toggle button (chevron) and a note that raw reasoning is hidden by default.
Monospaced tabular figures for all durations. Status always icon + label, never color alone.
ANTI-PATTERN: no gradients, no glow on text, no emoji, no color-only state encoding.
```

## Screen 3：执行工作台 — 跨执行对比（交叉验证新增核心场景）

```
Design a dark-themed execution workbench screen for comparing historical agent runs:
LEFT RAIL: run history list — each row shows timestamp, query summary truncated to one line, status badge (completed green / partial amber / failed red with icons), and total duration in monospace. Two rows are selected with checkbox marks.
CENTER: side-by-side comparison of the two selected runs — metric table with rows for total tokens, duration, tool calls, NPV result, IRR result, confidence level; each row shows value A, value B, and a delta column with signed colored deltas (green positive, red negative with minus sign and parentheses).
TOP BAR: actions "重新运行" and "导出对比 CSV".
Style: same instrument terminal theme, hairline table borders, right-aligned numeric columns, monospaced tabular figures, 36px table rows, sticky header.
ANTI-PATTERN: no card shadows, no alternating row colors, no 3D charts, no color-only deltas.
```

## Screen 4：报告视图（浅色 + 溯源两级）

```
Design the final analysis report view in LIGHT theme (for printing and investor-committee PDF export), while the app around it stays dark:
A centered report card on light warm-gray background: serif title "SA1 BESS 投资可行性分析报告", meta row (date, region, market, confidence badge), executive summary section, key metrics grid of KPI cards (NPV, IRR, payback years, annual revenue) with monospaced tabular figures, a recommendations section, risk flags list with amber warning icons, and a data-quality notes section.
KEY METRICS carry small evidence badges (pill with tool name like "price_trend_analysis") ONLY on the four headline KPIs — not on every number. Bottom of report: an "展开全部证据" disclosure listing every tool call with status, duration and download links.
Negative values rendered red with minus sign and parentheses. Clean print-friendly typography, no decorative graphics.
ANTI-PATTERN: no gradients, no dark sections inside the report, no badges on body-copy numbers, no emoji.
```

## Screen 5：部分成功 + 降级状态横幅

```
Design two notification patterns on the dark terminal theme:
PATTERN A (partial success): a report header strip listing per-tool outcomes as compact rows — "data_quality_check ✓ 0.8s", "market_screening ✓ 20.3s", "forward_spread_projection ⏱ 90s timeout", "investment_analysis ✓ 41.2s" — plus a calm summary line "3/4 分析完成，前瞻价差分析超时，结论置信度相应降低". No big red failure banner.
PATTERN B (degraded mode): a slim amber banner at top of workspace: "LLM 服务不可用，已降级为确定性模板模式（llm_degraded）" with a small warning icon and a "重试连接" ghost button.
Both patterns use icon + text, amber/red reserved strictly for state, monospaced durations.
ANTI-PATTERN: no alarm-red full-width banners for partial failures, no emoji, no modal popups blocking the workspace.
```

## Screen 6：窄屏适配（<1280px 抽屉态）

```
Design the narrow-viewport (1100px wide) adaptation of the agent workspace: single-column conversation layout; the evidence panel is hidden and replaced by a floating action button labeled "查看证据" with a small badge showing tool count; tapping it opens a right-side overlay drawer (70% width) containing the same Trace/Charts/Report/Evidence tabs; drawer has a close button and dims the conversation behind it. Same dark instrument theme, same status iconography.
ANTI-PATTERN: do not squeeze tables below readable width; no bottom navigation bars; no hamburger menus for the evidence drawer.
```

---

## Screen 7：意图预览 + 自主性拨盘（v2 信任模式核心屏）

```
Design a dark-themed agent workspace moment on the same instrument terminal theme: the AI agent has just proposed a plan BEFORE executing it.
CENTER: an intent preview card on surface tone — plain-language plan title "SA1 BESS 投资分析计划", four sequential numbered steps in monospaced numerals (1. 拉取价格数据 2. 市场筛选 3. FCAS 收入建模 4. 财务测算), a monospaced estimate "预计 3–5 分钟 · 12 个工具调用", and a footer with exactly THREE actions: one near-white filled primary button "继续执行", and two ghost buttons "修改计划" and "我自己处理".
TOP CONTROL BAR: a four-option segmented autonomy dial labeled 仅提醒 / 计划需确认 / 确认后执行 / 自动执行, with "计划需确认" active (surface-hover fill), options on panel tone, 4px radius.
No red anywhere. Monospaced tabular figures for the step numbers and duration.
ANTI-PATTERN: no auto-dismissing toasts for the plan preview; no modal blocking the conversation; no color-only state encoding; no purple-blue gradients; no drop shadows.
```

## Screen 8：置信度信号 + 升级求助（v2 信任模式状态屏）

```
Design two trust patterns on the same dark terminal theme:
PATTERN A (confidence signal): an analysis conclusion block — a headline KPI row (NPV, IRR, payback) in monospaced tabular figures, each headline KPI carrying a small confidence badge pill: green check icon + "置信度 0.86" for the NPV card, amber question-mark icon + "置信度 0.62" for the IRR card; below, a conclusion sentence with an inline confidence badge on the verdict phrase. Green for high confidence, amber for low — never red.
PATTERN B (escalation): an escalation card with a 2px amber left border on panel tone — title "需要您确认", a plain statement of the ambiguity "NSW1 与 QLD1 数据完整度差异较大，无法自动选择基准区域", and three ghost option buttons "以 NSW1 为基准" / "以 QLD1 为基准" / "标记给分析师".
ANTI-PATTERN: no full-width red error banners; no emoji; no color-only confidence encoding; no drop shadows.
```

## Screen 9：行动审计时间线 + 撤销（v2 信任模式安全网屏）

```
Design the Evidence tab extended with an action audit timeline on the same dark terminal theme:
a vertical chronological list of agent-initiated actions, each row (panel tone, 4px radius, monospaced durations) shows: timestamp, action description in plain language ("导出 SA1 投资报告 PDF", "覆盖保存视图 我的基准", "删除过期回测运行"), a status badge with icon (✓ 已完成 / ↺ 已撤销), and a ghost "撤销" button ONLY where reversal is possible — rows for irreversible actions show muted text "不可撤销（已在执行前告知）" instead.
Top of the timeline: filter chips 全部 / 可撤销 / 不可逆.
ANTI-PATTERN: no destructive actions without a prior intent preview; no hover-lift transforms on rows; no color-only status; no emoji.
```

---

## 生成后验收清单（人工复核）

1. 所有数字是否等宽表格数字（tabular figures）？
2. 每个视图是否只有一个近白主按钮？
3. 状态是否全部 icon+颜色双编码？
4. 负值是否三重编码（红+负号+括号）？
5. 是否出现紫蓝渐变/阴影/emoji 等 AI 味元素？
6. 报告屏是否为浅色（打印态）？
7. 对照 DESIGN-v2.md token 色值抽查主色/背景/状态三色是否一致。
8. （v2）意图预览是否提供 继续/修改/自己处理 三选一并默认不自动执行？
9. （v2）低置信度是否为琥珀色+问号图标（绝不红色）？
10. （v2）审计行是否只在可逆操作上出现撤销按钮？
