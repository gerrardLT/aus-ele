---
version: alpha
name: AEMO Intelligence Terminal
description: Dark-first professional terminal for BESS investment analysis agents (NEM/WEM electricity markets). Verifiable over decorative.
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
  negative-value: "#FF6B6B"
  chart-price: "#4FA3FF"
  chart-revenue: "#2EC27E"
  chart-fcas: "#F5A524"
  chart-risk: "#E5484D"
  chart-forecast: "#A78BFA"
  chart-saturation: "#4CC9F0"
typography:
  display-lg:
    fontFamily: Inter
    fontSize: 36px
    fontWeight: "600"
    lineHeight: 1.15
    letterSpacing: -0.02em
  headline-md:
    fontFamily: Inter
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
    fontFamily: Inter
    fontSize: 16px
    fontWeight: "400"
    lineHeight: 26px
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: "400"
    lineHeight: 22px
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: "400"
    lineHeight: 18px
  label-md:
    fontFamily: Inter
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
---

# AEMO Intelligence Terminal

## Overview

AEMO Intelligence is a dark-first, professional analysis terminal for battery
energy storage (BESS) investors in Australian electricity markets (NEM/WEM).
Its primary surfaces are an **agentic analysis workspace** (multi-turn chat
driving a ReAct agent over 30+ analysis tools) and an **execution workbench**
(historical runs, side-by-side comparison, audit trails).

The emotional register is **instrument-grade trust, not consumer delight**:
dense tabular data, monospaced tabular numerals, restrained color used only
for state and signal. Every visual decision serves two goals — **verifiability**
(can the user check where a number came from?) and **operational efficiency**
(can a user running 20 analyses a day move fast?). Decoration that serves
neither is removed.

Brand personality: precise, evidence-driven, calm under risk. The interface
should feel like a well-calibrated instrument, never like a marketing page.

## Colors

The palette is a low-chroma blue-violet neutral ramp (hue 250–260) inherited
from the production theme, with color reserved for three jobs: primary action,
execution state, and data-viz series identity.

- **Primary (oklch 0.65 0.18 260):** Blue-violet used sparingly — active
  focus rings, links, evidence badges, chart emphasis. Never used for large
  surface fills.
- **Background/Panel/Surface ramp:** Three tonal layers (0.13 → 0.16 → 0.19
  lightness) create hierarchy without shadows. Content cards sit on `surface`;
  the page is `background`; navigation and evidence panes use `panel`.
- **Inverted (oklch 0.92):** Near-white used for the single primary action per
  view (filled button) and active chips — the highest-contrast element on
  screen always marks "the thing to do next".
- **Status triad:** Green (success), amber (timeout), red (error) — always
  paired with icons (✓/⏱/✕) so color is never the only channel (color-blind
  safety is mandatory for financial tooling).
- **Negative values:** Rendered as red + explicit minus sign + parentheses,
  e.g. `(123.45)` — triple encoding prevents misreading a minus sign on dark
  backgrounds, where a single wrong sign is a costly error.
- **Report/print:** All exported reports and print views switch to the light
  palette (investor-committee PDFs are read on paper and projectors).

## Typography

Two voices with strict role separation, plus a data voice:

- **Headlines:** Source Serif 4 Semi-Bold for page titles only — an
  institutional, report-like voice inherited from the production brand.
- **Body & UI:** Inter (400/600) for narrative text, labels, and controls.
  Labels are uppercase with 0.08em tracking for instrument-panel legibility.
- **Data voice (critical):** JetBrains Mono with `tnum` tabular figures for
  ALL numbers — KPIs, table cells, chart axes, trace durations. Tabular
  figures keep columns aligned and make magnitude comparison glanceable.
  KPI numbers at 28px/600; table data at 13px/500.

## Layout

Desktop-first terminal layout (min 1280px), degrading to stacked drawers below.

- **Agent workspace:** Two-pane. Left pane (flex, min 420px): conversation
  stream + input + control bar (market / region / analysis mode / workflow
  chips). Right pane (min 480px): evidence panel with tabs — Trace
  (checklist), Charts, Report, Evidence (tool audit list).
- **Execution workbench:** Three-zone. Left rail: run history list with
  status badges. Center: run detail (report + metrics). Right (on demand):
  side-by-side comparison of two selected runs, metric-by-metric deltas.
- **Spacing scale:** Strict 8px scale (4px half-step). Card padding 20px,
  panel gaps 16px, page margins 32px. Density is a feature: table rows at
  36px height, no zebra striping — use hairline borders (1px `border`).
- **Narrow screens (<1280px):** Evidence panel collapses to an overlay drawer
  opened by a "查看证据" button; never squeeze tables below readable width.

## Elevation & Depth

Flat tonal layering only — no drop shadows. Hierarchy is expressed through the
three-step surface ramp (background → panel → surface) and hairline borders.
The only glow permitted is the existing brand glow on primary KPI cards in
dark mode, at opacity ≤ 0.15, never on text or table content (glow reduces
fine-grained numeric legibility).

## Shapes

Instrument sharpness: 4px radius for interactive controls (buttons, inputs,
badges), 8px for cards, 12px for modal/drawer containers, full-round only for
chips and status pills. Do not mix radii within one component. Dividers are
1px hairlines in `border` color; dashed borders only for empty/lazy-load states.

## Components

- **Primary button:** `inverted` fill, `inverted-text` label, 4px radius.
  Exactly one per visible area. Disabled: 40% opacity, no state change.
- **Ghost button:** Transparent, hairline border, muted label; hover raises
  label to `on-surface`. Used for secondary actions (新对话, 返回市场).
- **Workflow chip:** Full-round pill, hairline border; active chip =
  `inverted` fill. Chips wrap in the control bar.
- **Execution checklist (Dynamic Checklist):** Vertical list of steps. Each
  item: status icon (✓ done / ● running pulse / ○ pending / ⏱ timeout / ✕
  error), tool label, duration in mono, retry count when >0. Running item
  highlighted with `surface-hover` background; the list supports three data
  shapes (pre-known static steps, incrementally discovered steps, wave-grouped
  plan steps).
- **Thinking toggle:** Chevron button labeled 查看推理轨迹; expands a
  collapsible panel with the sanitized trace (no raw prompt text). Default
  collapsed.
- **Evidence badge:** Small `panel`-bg pill with primary-colored tool name
  (e.g. `price_trend_analysis`), attached only to key conclusion metrics;
  click opens the corresponding tool result in the Evidence tab.
- **Status badge:** Pill with icon + label, triad colors above.
- **KPI card:** Surface card, uppercase muted label (label-md), mono 28px
  value, delta row with signed colored delta (green positive / red negative
  triple-encoded).
- **Trace item:** Panel-colored row for the Evidence tab: tool name, args
  summary, status badge, duration, retry count, artifact download link when
  present.
- **Input field:** Transparent bg, hairline border, focus ring 1px `primary`.

## Do's and Don'ts

- Do use monospaced tabular figures for every number, without exception
- Do pair every status color with an icon (color-blind safety)
- Do triple-encode negative values: red + minus sign + parentheses
- Do keep exactly one primary (inverted-fill) action per visible area
- Do switch report/export/print views to the light palette
- Do collapse the evidence pane to a drawer below 1280px width
- Don't use drop shadows; use the tonal surface ramp for hierarchy
- Don't apply glow effects to text, tables, or chart content
- Don't attach evidence badges to more than the key conclusion metrics
- Don't show raw LLM reflection/self-doubt text by default
- Don't use color as the only channel for any state or trend direction
- Do maintain WCAG AA contrast (4.5:1 body text) in both themes

## Data Visualization (extension)

Chart palette is fixed at six series colors chosen for dark-background
separation and deuteranopia safety (blue/green/amber/red/violet/cyan — red
and green are never adjacent series in the same chart legend order):

- Price/energy series: `chart-price` (#4FA3FF)
- Revenue series: `chart-revenue` (#2EC27E)
- FCAS/ancillary: `chart-fcas` (#F5A524)
- Risk/loss: `chart-risk` (#E5484D)
- Forecast/projection: `chart-forecast` (#A78BFA), dashed stroke
- Saturation/capacity: `chart-saturation` (#4CC9F0)

Chart rules: axis labels in `label-md` muted; tick values in mono 12px;
negative price areas shaded below zero-line at 10% `negative-value` opacity;
no gradients, no 3D, no area fills above 15% opacity. Tables: 36px rows,
right-aligned numeric columns, hairline dividers, sticky header on scroll;
sort indicators as mono arrows, never color-only.

## Execution State System (extension)

Agent execution states map 1:1 to backend SSE events and trajectory buckets:

| State | Color | Icon | Meaning |
|---|---|---|---|
| running | primary pulse | ● | tool in flight; show elapsed seconds in mono |
| success | status-success | ✓ | completed, data usable |
| timeout | status-timeout | ⏱ | exceeded budget; partial data may exist |
| error | status-error | ✕ | failed; render error_bucket attribution |
| cached | muted | ↺ | served from session cache (A5) |
| degraded | status-timeout | ⚠ | LLM unavailable, template fallback active |

Error attribution wording must separate tool failure from agent capability
(e.g. "价格表 trading_price_2025 尚未同步" not "分析失败"). Partial-success
reports list each tool row with its own state — never one binary banner.
