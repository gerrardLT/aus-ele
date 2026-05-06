# Finland Price Workbench Redesign

## 1. Feature Summary

The Finland market board should shift from a table-first data surface into a price-first operator workbench. The page should help a user understand the current reserve-price regime at a glance, then use supporting comparisons such as spot, imbalance, and procured volume to explain the move before the user decides whether to inspect raw rows.

This redesign applies specifically to the Finland board workflow at `/finland`, with emphasis on the chart and analysis sections rather than the data ingestion layer.

## 2. Primary User Action

The primary user action is:

Understand whether the selected Finland reserve price is rising, falling, extreme, or diverging from spot and imbalance, within a few seconds of landing on the page.

Everything else should support that action rather than compete with it.

## 3. Design Direction

The page should feel closer to a compact trading terminal than a spreadsheet export. The current board successfully exposes real data and field selection, but it still asks the user to visually parse a dense table before understanding the market state. The redesign should invert that priority.

Visual rules:

- The main price chart is the dominant surface.
- Summary numbers are secondary but sharp and decision-oriented.
- Supporting comparisons should explain the main move, not become equal-weight charts.
- The raw table remains available but is visually and spatially de-emphasized.

This should remain consistent with the existing Finland page shell, translation-backed copy model, and current backend contracts.

## 4. Layout Strategy

The page should be reorganized into four layers.

### Layer A: Market Summary Strip

A thin summary band above the chart area should expose the selected market context:

- active primary price field
- latest value
- intraday high / low
- average
- simple volatility label
- simple spread-to-spot cue

This band should answer "what is happening now?" before the chart is read in detail.

### Layer B: Main Price Focus

This is the core of the page.

- One large primary chart
- Only one main reserve price series is visually emphasized at a time
- The selected field defines the chart
- The chart should use clear last-point emphasis, readable axis spacing, and restrained annotation

The primary chart is the first thing the eye should land on.

### Layer C: Supporting Comparison Rail

Below the main chart, show a compact secondary comparison area. This should not be another large equal-priority chart. It should be a supporting rail used to explain the main move.

Recommended default companions:

- spot price
- imbalance price
- procured volume

These can appear as one compact linked chart or two small aligned strips, but their role is explanatory, not primary.

### Layer D: Verification Layer

The current tabular data view remains available, but moves lower in the page and no longer defines the first visual impression.

The table becomes:

- a verification tool
- a detailed inspection tool
- a source-of-truth fallback

It should still support field selection and maintain existing backend alignment.

## 5. Information Hierarchy

The hierarchy should be strict:

1. Selected reserve price trend
2. Current state summary metrics
3. Supporting comparison context
4. Detailed rows
5. Dictionary and methodology support

This hierarchy is the main correction to the current page.

## 6. Key States

### Default State

- Default selected field should be `FCR-N Capacity Price`
- Main chart immediately renders this field
- Summary strip reflects this field
- Supporting comparison rail loads the predefined context series

### Field Switch State

- When the user selects another price field, the main chart and summary strip update immediately
- Supporting comparison rail persists, but its labels and highlighted spread logic adapt to the selected field

### No Selection State

- If nothing is selected, the page should fall back to the default price instead of showing an empty analysis area
- The current empty analysis experience is too passive for a price-first workbench

### Loading State

- Main chart area should reserve stable height
- Summary strip should reserve stable slots
- Supporting comparison rail should not jump layout
- The table should never appear to load before the main chart

### Empty Data State

- If a selected field has no data, the main chart should show a direct, compact explanation
- Supporting comparison rail should either hide or display only available context

### Error State

- Errors should stay close to the chart workbench
- A chart-specific failure should not collapse the rest of the page if summary data is still available

## 7. Interaction Model

### Default Flow

1. User lands on `/finland`
2. Page loads summary strip and primary chart for `FCR-N Capacity Price`
3. Supporting comparison rail loads spot, imbalance, and volume context
4. User can switch focus by selecting another price field
5. User can inspect details in the lower table if needed

### Field Selection Behavior

The existing "select from table header" behavior should remain, but it should no longer be the only practical way to drive the chart. The redesign should allow a cleaner primary-price focus control near the chart area.

Recommended behavior:

- keep current table-header selection support for power users
- add a simpler primary-field selector near the chart surface
- limit the primary chart to one emphasized field at a time

### Comparison Behavior

The supporting rail should update automatically and should not require the user to manually compose every comparison series.

### Table Behavior

The table remains useful, but it should stop dominating the workflow. It should load beneath the chart area and be treated as a scrollable evidence layer.

## 8. Content Requirements

The redesign requires the following visible content elements:

- primary field name
- latest price
- session high
- session low
- mean or rolling average
- volatility label
- spread vs spot
- spread vs imbalance where relevant
- data freshness cue

Microcopy should be concise and translation-backed. Avoid long instructional paragraphs above the chart.

## 9. Data and Calculation Notes

This redesign does not require a backend model rewrite. It should use the existing Finland board contracts where possible.

The current backend already supports:

- overview cards
- tabular views
- linked chart data
- field catalog
- readiness contract

Implementation should prefer deriving chart summary metrics from the already-returned price series unless there is a strong reason to add a dedicated backend summary payload.

## 10. Recommended UI Components

Recommended workbench composition:

- `Primary price selector`
- `Summary metric strip`
- `Main price chart`
- `Supporting comparison rail`
- `Compact field detail card`
- `De-emphasized detailed table`

The existing linked chart and field detail panel can be refactored into this structure rather than replaced wholesale.

## 11. Anti-Goals

The redesign should avoid:

- showing too many equal-weight price lines in the main chart
- making the page feel like a spreadsheet clone
- moving key insight below the fold
- forcing the user to understand reserve data through the table first
- decorative complexity that hurts interpretability

This should feel sharper and clearer, not busier.

## 12. Constraints

- Must preserve current internationalization patterns and translation-backed labels
- Must preserve compatibility with current live Finland API contracts
- Must work with the current `/finland` route and shell
- Must keep the table available for verification
- Must avoid reintroducing heavy payloads or rendering regressions

## 13. Open Questions

Resolved for implementation:

- primary emphasis style: price-first operator workbench
- chosen interaction pattern: dual-layer chart layout
- top priority data: price trends
- chosen layout direction: main price chart plus supporting comparison rail
- default primary field: `FCR-N Capacity Price`

Remaining implementation choices, not product questions:

- whether the supporting comparison rail is a single shared strip or two compact strips
- whether volatility is shown as a computed label only or also as a sparkline
- whether spread-to-spot should be a summary badge only or a dedicated small series

## 14. Recommended Implementation Direction

The recommended implementation is:

- make the analysis section the new visual center of the Finland page
- introduce a default primary price field on first load
- add a small primary-price selector near the chart
- convert the current chart area into a large main chart plus a compact comparison rail
- move the table below the chart workbench and tone down its visual dominance
- keep dictionary and methodology support, but treat them as support layers rather than the center of the experience

This is the most aligned direction for a Finland market board whose core value is fast understanding of price behavior.
