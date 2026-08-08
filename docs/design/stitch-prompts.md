# Stitch Prompt 包：AEMO Intelligence Agent 界面（2026-08-08）

> 用法：在 stitch.withgoogle.com 标准模式（Web 画布）逐屏生成；
> 依据 Stitch 最佳实践：**英文 prompt 生成更稳**，生成后可用中文指令微调语言/细节；
> 每次生成后对照 `docs/design/DESIGN.md` 的 Do's and Don'ts 人工复核；
> 建议先在 Stitch 中导入本项目的 DESIGN.md（Import design rules），使生成结果遵循 token。
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

## 生成后验收清单（人工复核）

1. 所有数字是否等宽表格数字（tabular figures）？
2. 每个视图是否只有一个近白主按钮？
3. 状态是否全部 icon+颜色双编码？
4. 负值是否三重编码（红+负号+括号）？
5. 是否出现紫蓝渐变/阴影/emoji 等 AI 味元素？
6. 报告屏是否为浅色（打印态）？
7. 对照 DESIGN.md token 色值抽查主色/背景/状态三色是否一致。
