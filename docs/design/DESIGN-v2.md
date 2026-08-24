---
version: 1.0
name: AEMO Intelligence Terminal
description: Dark-first agentic analysis terminal for BESS investment decisions (NEM/WEM). Trust-engineered over decorative.
colors:
  primary: "oklch(0.65 0.18 260)"
  primary-light: "oklch(0.50 0.2 260)"
  on-primary: "oklch(0.14 0.012 260)"
  background: "oklch(0.13 0.012 260)"
  panel: "oklch(0.16 0.01 258)"
  surface: "oklch(0.19 0.008 256)"
  surface-hover: "oklch(0.22 0.012 254)"
  on-surface: "oklch(0.92 0.01 250)"
  muted: "oklch(0.60 0.015 252)"
  border: "oklch(0.28 0.015 255)"
  inverted: "oklch(0.92 0.01 250)"
  inverted-text: "oklch(0.14 0.012 260)"
  error: "oklch(0.62 0.2 25)"
  status-success: "oklch(0.72 0.15 155)"
  status-timeout: "oklch(0.78 0.14 80)"
  status-error: "oklch(0.66 0.21 25)"
  confidence-high: "oklch(0.72 0.15 155)"
  confidence-low: "oklch(0.78 0.14 80)"
  negative-value: "#FF6B6B"
  chart-price: "#4FA3FF"
  chart-revenue: "#2EC27E"
  chart-fcas: "#F5A524"
  chart-risk: "#E5484D"
  chart-forecast: "#A78BFA"
  chart-saturation: "#4CC9F0"
typography:
  display-lg:
    fontFamily: Archivo
    fontSize: 36px
    fontWeight: "600"
    lineHeight: 1.15
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Archivo
    fontSize: 24px
    fontWeight: "600"
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-serif:
    fontFamily: Source Serif 4
    fontSize: 24px
    fontWeight: "600"
    lineHeight: 32px
  body-lg:
    fontFamily: Archivo
    fontSize: 16px
    fontWeight: "400"
    lineHeight: 26px
  body-md:
    fontFamily: Archivo
    fontSize: 14px
    fontWeight: "400"
    lineHeight: 22px
  body-sm:
    fontFamily: Archivo
    fontSize: 12px
    fontWeight: "400"
    lineHeight: 18px
  label-md:
    fontFamily: Archivo
    fontSize: 12px
    fontWeight: "600"
    lineHeight: 16px
    letterSpacing: 0.08em
  mono-data:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: "500"
    lineHeight: 20px
    fontFeature: tnum
  mono-kpi:
    fontFamily: JetBrains Mono
    fontSize: 28px
    fontWeight: "600"
    lineHeight: 34px
    fontFeature: tnum
rounded:
  sm: 4px
  md: 8px
  lg: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 16px
  lg: 24px
  xl: 32px
  2xl: 48px
  page-margin: 32px
  panel-gap: 16px
  card-padding: 20px
components:
  button-primary:
    backgroundColor: "{colors.inverted}"
    textColor: "{colors.inverted-text}"
    typography: "{typography.label-md}"
    rounded: "{rounded.sm}"
    padding: 12px
  button-primary-hover:
    backgroundColor: "{colors.on-surface}"
  button-ghost:
    backgroundColor: transparent
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: 12px
  button-ghost-hover:
    textColor: "{colors.on-surface}"
  chip-workflow:
    backgroundColor: transparent
    textColor: "{colors.muted}"
    rounded: "{rounded.full}"
    padding: 10px
  chip-workflow-active:
    backgroundColor: "{colors.inverted}"
    textColor: "{colors.inverted-text}"
  card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.md}"
    padding: "{spacing.card-padding}"
  card-hover:
    backgroundColor: "{colors.surface-hover}"
  status-badge-success:
    backgroundColor: "{colors.status-success}"
    textColor: "{colors.background}"
    rounded: "{rounded.full}"
  status-badge-timeout:
    backgroundColor: "{colors.status-timeout}"
    textColor: "{colors.background}"
    rounded: "{rounded.full}"
  status-badge-error:
    backgroundColor: "{colors.status-error}"
    textColor: "{colors.background}"
    rounded: "{rounded.full}"
  evidence-badge:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.primary}"
    rounded: "{rounded.sm}"
    padding: 4px
  trace-item:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
  kpi-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.mono-kpi}"
    rounded: "{rounded.md}"
    padding: "{spacing.lg}"
  input-field:
    backgroundColor: transparent
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.sm}"
    padding: 12px
  intent-preview-card:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.card-padding}"
  confidence-badge-high:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.confidence-high}"
    rounded: "{rounded.sm}"
    padding: 4px
  confidence-badge-low:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.confidence-low}"
    rounded: "{rounded.sm}"
    padding: 4px
  autonomy-dial-option:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.muted}"
    rounded: "{rounded.sm}"
    padding: "{spacing.sm}"
  autonomy-dial-option-active:
    backgroundColor: "{colors.surface-hover}"
    textColor: "{colors.on-surface}"
  escalation-card:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-md}"
    rounded: "{rounded.md}"
    padding: "{spacing.card-padding}"
  audit-row:
    backgroundColor: "{colors.panel}"
    textColor: "{colors.on-surface}"
    typography: "{typography.body-sm}"
    rounded: "{rounded.sm}"
    padding: "{spacing.md}"
---

# AEMO Intelligence Terminal

## Overview

AEMO Intelligence is a dark-first, professional analysis terminal for battery
energy storage (BESS) investors in Australian electricity markets (NEM/WEM).
Its primary surfaces are an **agentic analysis workspace** (multi-turn chat
driving a ReAct agent over 30+ analysis tools), a **market funnel**
(price-spread → FCAS → cash-flow decision stages) and an **execution
workbench** (historical runs, side-by-side comparison, audit trails).

The emotional register is **instrument-grade trust, not consumer delight**:
dense tabular data, monospaced tabular numerals, restrained color used only
for state and signal. Every visual decision serves two goals — **verifiability**
(can the user check where a number came from?) and **operational efficiency**
(can a user running 20 analyses a day move fast?). Decoration that serves
neither is removed.

v2 positioning (2026-08-24): the terminal is additionally a
**trust-engineered agentic surface**. Per 2025–2026 agentic UX research,
trustworthiness is an output of the design process, not the model: the agent
previews intent before acting, exposes calibrated confidence, explains its
rationale, keeps a full action audit, and escalates ambiguity instead of
guessing. These six patterns are first-class components in this system.

Brand personality: precise, evidence-driven, calm under risk. The interface
should feel like a well-calibrated instrument, never like a marketing page.

## Colors

The palette is a low-chroma blue-violet neutral ramp (hue 250–260), with
color reserved for four jobs: primary action, execution state, data-viz
series identity, and confidence signaling. Research finding (NN/g): a single
accent guiding attention improves key-information location speed ~39% —
therefore `primary` remains the ONLY accent for emphasis.

- **Primary (oklch 0.65 0.18 260):** Blue-violet used sparingly — active
  focus rings, links, evidence badges, chart emphasis. Never for large fills.
- **Background/Panel/Surface ramp:** Three tonal layers (0.13 → 0.16 → 0.19)
  create hierarchy without shadows (Material 3 dark-theme tonal-elevation
  pattern adapted flat). Cards sit on `surface`; page is `background`;
  navigation and evidence panes use `panel`.
- **Inverted (oklch 0.92):** Near-white used for the single primary action
  per view and active chips — the highest-contrast element on screen always
  marks "the thing to do next".
- **Status triad:** Green (success), amber (timeout), red (error) — always
  paired with icons (✓/⏱/✕); color is never the only channel (color-blind
  safety is mandatory for financial tooling).
- **Confidence pair (new in v2):** `confidence-high` (green) and
  `confidence-low` (amber) mark agent certainty on conclusions. Never red —
  low confidence is a scrutiny signal, not a failure. Always icon-paired
  (✓ high / ? low) and always shown with the numeric score in mono.
- **Negative values:** Red + explicit minus sign + parentheses, e.g.
  `(123.45)` — triple encoding prevents misreading a sign on dark
  backgrounds, where one wrong sign is a costly error.
- **Report/print:** All exported reports switch to the light palette
  (investor-committee PDFs are read on paper and projectors).

## Typography

Two voices with strict role separation, plus a data voice:

- **Headlines:** Source Serif 4 Semi-Bold for page titles only — an
  institutional, report-like voice inherited from the production brand.
- **Body & UI:** Archivo (400/500/600/700) for narrative text, labels, and
  controls. Labels are uppercase with 0.08em tracking for instrument-panel
  legibility. NOTE (2026-08-24): Archivo is the ratified sans stack
  (root DESIGN.md v1.1, 2026-08-20); Inter is deprecated for this product.
- **Data voice (critical):** JetBrains Mono with `tnum` tabular figures for
  ALL numbers — KPIs, table cells, chart axes, trace durations, confidence
  scores, plan-step counts. KPI numbers at 28px/600; table data at 13px/500.
  Tabular figures keep columns aligned and make magnitude comparison
  glanceable.

## Layout

Desktop-first terminal layout (min 1280px), degrading to stacked drawers
below.

- **Agent workspace:** Two-pane. Left pane (flex, min 420px): conversation
  stream + input + control bar (market / region / analysis mode / workflow
  chips). Right pane (min 480px): evidence panel with tabs — Trace, Charts,
  Report, Evidence.
- **Market funnel:** Sticky stage tab bar under a persistent context strip
  (region / year / day-type chips). Stage tabs are numbered, mark visited
  stages with a check, and keep exactly one active indicator line.
- **Execution workbench:** Three-zone. Left rail: run history with status
  badges. Center: run detail. Right (on demand): side-by-side run
  comparison with per-metric deltas.
- **KPI zones use a bento grid (v2):** headline KPIs occupy 2×1 or 2×2
  cells; secondary metrics 1×1. Grid gaps 16px, cells never narrower than
  the widest mono number they contain. Bento grouping follows the
  price-spread → FCAS → cash-flow funnel order left-to-right, top-to-bottom.
- **Spacing scale:** Strict 8px scale (4px half-step). Card padding 20px,
  panel gaps 16px, page margins 32px. Density is a feature: table rows
  36px, no zebra striping — hairline borders (1px `border`) only.
- **Narrow screens (<1280px):** Evidence panel collapses to an overlay
  drawer opened by a "查看证据" button; never squeeze tables below readable
  width.

## Elevation & Depth

Flat tonal layering only — no drop shadows, no hover-lift transforms, no
text glow. Hierarchy is expressed through the three-step surface ramp
(background → panel → surface) and hairline borders. Hover feedback is a
surface step-up (`surface` → `surface-hover`) or a border lightening,
never elevation. The only glow permitted is the brand glow on primary KPI
cards in dark mode at opacity ≤ 0.15, applied to the card edge only — never
on text or table content (glow destroys fine-grained numeric legibility).

## Shapes

Instrument sharpness: 4px radius for interactive controls (buttons, inputs,
badges), 8px for cards and bento cells, 12px for modal/drawer containers,
full-round only for chips and status pills. Do not mix radii within one
component. Dividers are 1px hairlines in `border` color; dashed borders only
for empty/lazy-load states.

## Components

- **Primary button:** `inverted` fill, `inverted-text` label, 4px radius.
  Exactly one per visible area. Disabled: 40% opacity, no state change.
- **Ghost button:** Transparent, hairline border, muted label; hover raises
  label to `on-surface`. Secondary actions (新对话, 返回市场).
- **Workflow chip:** Full-round pill, hairline border; active = `inverted`
  fill. Chips wrap in the control bar.
- **Execution checklist (Dynamic Checklist):** Vertical steps. Each item:
  status icon (✓ done / ● running pulse / ○ pending / ⏱ timeout / ✕ error /
  ↺ cached), tool label, duration in mono, retry count when >0. Running item
  uses `surface-hover` background.
- **Thinking toggle:** Chevron button 查看推理轨迹; collapsible panel with the
  sanitized trace (no raw prompt text). Default collapsed.
- **Evidence badge:** `panel`-bg pill, primary-colored tool name, attached
  ONLY to key conclusion metrics; click opens the tool result in Evidence.
- **Status badge:** Pill with icon + label, triad colors.
- **KPI card:** Surface card, uppercase muted label (label-md), mono 28px
  value, delta row with signed colored delta triple-encoded.
- **Trace item / Audit row:** Panel-colored row: tool name, args summary,
  status badge, duration, retry count, artifact link.
- **Input field:** Transparent bg, hairline border, focus ring 1px `primary`.
- **Intent preview card (new in v2):** Before any significant agent action,
  a surface card states the plan in plain language with sequential steps,
  each step numbered in mono. Footer offers exactly three actions: primary
  继续执行, ghost 修改计划, ghost 我自己处理. This is an intentional friction
  point, never auto-dismissed, never collapsed into a toast.
- **Confidence badge (new in v2):** Small pill, icon + mono percentage —
  ✓ green ≥ 0.8, ? amber < 0.8. Attached to conclusion sentences and the
  four headline KPIs; clicking it opens the evidence trail behind the score.
- **Autonomy dial (new in v2):** Four-option segmented control on the
  workspace control bar — 仅提醒 / 计划需确认 / 确认后执行 / 自动执行 —
  persisted per user, defaults to 计划需确认. Options are
  `autonomy-dial-option` panels; active option is `surface-hover` fill.
- **Escalation card (new in v2):** When the agent is uncertain it asks
  instead of guessing: a panel card with the ambiguity stated plainly,
  2–3 concrete options as ghost buttons, and a "标记给分析师" fallback.
  Amber left border (2px), never a full red banner.
- **Action audit & undo (new in v2):** Every destructive or export action
  writes an `audit-row` in the Evidence tab timeline with status and a ghost
  撤销 button where reversal is possible; irreversible actions state their
  irreversibility in the intent preview, never discovered afterward.

## Do's and Don'ts

- Do use monospaced tabular figures for every number, without exception
- Do pair every status/confidence color with an icon (color-blind safety)
- Do triple-encode negative values: red + minus sign + parentheses
- Do keep exactly one primary (inverted-fill) action per visible area
- Do preview intent before any export, delete, or commit-grade action
- Do surface calibrated confidence on conclusions and headline KPIs
- Do escalate ambiguity with options instead of confident guessing
- Do switch report/export/print views to the light palette
- Do collapse the evidence pane to a drawer below 1280px width
- Don't use drop shadows, hover-lift transforms, or text glow
- Don't apply backdrop-blur to content panels or chart areas — solid
  backgrounds only; exactly one notch of `backdrop-blur-sm` is permitted on
  sticky toolbars/tab bars (near-solid background) and on full-screen modal
  scrims, and nowhere else
- Don't use color as the only channel for any state, trend, or confidence
- Don't attach evidence badges to more than the key conclusion metrics
- Don't show raw LLM reflection/self-doubt text by default
- Don't auto-execute multi-step plans without an accepted intent preview
- Don't use red for low confidence (reserve red for failure states only)
- Do maintain WCAG AA contrast (4.5:1 body text) in both themes

## Data Visualization (extension)

Charts exploit preattentive processing (NN/g / Cleveland–McGill): encode
quantities with **length and 2D position only** (bar, line, scatter). Never
encode magnitude with area, angle, or color — so pie/donut charts, radial
gauges, treemaps and 3D projections are prohibited on this surface. Color
and shape carry **categorical** identity only.

Chart palette is fixed at six series colors chosen for dark-background
separation and deuteranopia safety (red and green are never adjacent series
in the same legend):

- Price/energy series: `chart-price` (#4FA3FF)
- Revenue series: `chart-revenue` (#2EC27E)
- FCAS/ancillary: `chart-fcas` (#F5A524)
- Risk/loss: `chart-risk` (#E5484D)
- Forecast/projection: `chart-forecast` (#A78BFA), dashed stroke
- Saturation/capacity: `chart-saturation` (#4CC9F0)

Data-ink discipline (Tufte): maximize the share of pixels that carry data —
no gridlines darker than `border`, no axis arrows, no legend boxes (labels
direct where ≤ 3 series), and prefer small multiples over one overloaded
chart when comparing regions. Chart rules: axis labels in `label-md` muted;
tick values in mono 12px; negative price areas shaded below zero-line at 10%
`negative-value` opacity; no gradients, no area fills above 15% opacity.
Tables: 36px rows, right-aligned numeric columns, hairline dividers, sticky
header on scroll; sort indicators as mono arrows, never color-only.

## Execution State System (extension)

Agent execution states map 1:1 to backend SSE events and trajectory buckets:

| State | Color | Icon | Meaning |
|---|---|---|---|
| running | primary pulse | ● | tool in flight; show elapsed seconds in mono |
| success | status-success | ✓ | completed, data usable |
| timeout | status-timeout | ⏱ | exceeded budget; partial data may exist |
| error | status-error | ✕ | failed; render error_bucket attribution |
| cached | muted | ↺ | served from session cache |
| degraded | status-timeout | ⚠ | LLM unavailable, template fallback active |

Error attribution wording must separate tool failure from agent capability
(e.g. "价格表 trading_price_2025 尚未同步" not "分析失败"). Partial-success
reports list each tool row with its own state — never one binary banner.

## Agentic Trust Patterns (extension, v2)

Six patterns from the 2025–2026 agentic UX literature, mapped to this
terminal. Each pattern ships with a measurable acceptance metric:

| Pattern | Where it lives | Acceptance metric |
|---|---|---|
| Intent Preview | Before report export / view overwrite / irreversible ops | Plans accepted without edit > 85% |
| Autonomy Dial | Workspace control bar (per-user persisted) | Setting churn monitored monthly |
| Explainable Rationale | Evidence badges + 查看推理轨迹 | Rationale rated helpful in micro-survey |
| Confidence Signal | Conclusion sentences + headline KPIs | Low-confidence results reviewed longer |
| Action Audit & Undo | Evidence tab timeline | Reversion rate < 5% |
| Escalation Pathway | Ambiguous multi-market / missing-data cases | Escalation frequency 5–15%, recovery > 90% |

The agent workspace defaults to the "Plan & Propose" tier: the agent always
formulates a visible plan (checklist preview in the Trace tab) and the user
approves execution. Full autonomy is opt-in per workflow, never global.
