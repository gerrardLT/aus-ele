# Finland Market Board Design

> Goal: add a new `/finland` page as the primary Finland business-facing market board, combining Fingrid reserve and balancing signals with Finland spot-price context into one analysis-first workspace. The existing `/fingrid` page remains available as a source-level dataset browser and sync/debug surface.

## 1. Context

The current Finland product surface is split:

- `/fingrid` works well as a single-dataset analysis page
- `/api/fingrid/*` exposes source-level dataset and sync capabilities
- `/api/finland/market-model` already establishes Finland as a multi-source market model

That is no longer enough for the next Finland step. The user now wants to represent a real Finland market readout that can reproduce the practical working views shown in the supplied screenshots:

- hourly reserve-capacity prices
- 15-minute activation and imbalance prices
- daily average tables
- summary statistics
- field-level source and definition documentation

The key product shift is:

- **from** Fingrid dataset browser
- **to** Finland multi-source market board

This means the new page must not be designed around raw dataset ids such as `317`, `319`, `244`, `51`, or `52`. It must be designed around business views that analysts can read directly.

## 2. Product Positioning

### 2.1 Primary user

This page is for:

- internal analysts
- trading research users
- product and commercial users who still need a credible first-screen narrative

The chosen priority is:

- **support both internal analysis and external/demo readability**
- **but favor internal analysis when there is a tradeoff**

### 2.2 Page role

`/finland` becomes the Finland market-facing workspace.

`/fingrid` remains:

- source debugging page
- single-dataset analysis page
- sync status and raw dataset inspection page

This boundary is intentional and should remain stable. `/fingrid` should not continue drifting into the main Finland business page.

## 3. Design Decision

The page uses **Approach A: overview on top, workbench below**.

This was chosen over:

- a pure dashboard, which looks cleaner but weakens analytical closure
- a pure spreadsheet page, which supports analysis but is too heavy for first-screen product storytelling

The adopted direction is a hybrid:

1. top summary and source-health overview
2. central table-first market workbench
3. bottom linked chart and field-explanation area

This structure best matches the supplied Finland screenshots while still creating a stronger product surface than a plain exported-table clone.

## 4. Scope

### 4.1 In scope

- new `/finland` frontend page
- Finland market board experience with overview, tables, statistics, and field dictionary
- backend board-oriented Finland aggregation endpoints
- explicit separation between source-level interfaces and board-level interfaces
- support for the Finland data views represented in the screenshots

### 4.2 Out of scope

- replacing or deleting `/fingrid`
- unifying Finland directly into the Australia workbench
- building Finland BESS dispatch or investment workflows in this page
- turning the board into a full Europe router
- committing to a single future spot-price provider if multiple are still supported behind a stable field contract

## 5. Data Coverage Goal

The page is designed to support the following business views.

### 5.1 Hourly reserve-capacity price view

Columns:

- Helsinki time
- FCR-N capacity price
- FCR-D Up capacity price
- FCR-D Down capacity price
- aFRR capacity price up
- aFRR capacity price down
- mFRR capacity price up
- mFRR capacity price down
- Finland spot price

### 5.2 15-minute activation and settlement view

Columns:

- Helsinki time
- aFRR activation price up
- aFRR activation price down
- mFRR activation price up
- mFRR activation price down
- imbalance settlement price
- Finland spot price

### 5.3 Daily average views

Two modes inside one tab:

- daily capacity averages
- daily activation and settlement averages

### 5.4 Summary statistics view

Per field:

- field key
- field label
- unit
- granularity
- valid record count
- mean
- median
- max
- min
- standard deviation
- 25th percentile
- 75th percentile

### 5.5 Field dictionary view

Per field:

- category
- metric name
- unit
- granularity
- source system
- source dataset id or endpoint
- source type
- methodology note
- coverage
- current status

## 6. Page Information Architecture

The page has three vertical sections.

### 6.1 Top overview section

Purpose:

- answer within 5 to 10 seconds whether the board is usable
- show what is covered right now
- signal the dominant price context of the selected window

Content:

- page title: `Finland Market Board`
- concise subtitle clarifying it is a multi-source Finland reserve, balancing, and spot readout
- time-window controls
- timezone control, defaulting to `Europe/Helsinki`
- source status pills for `Fingrid`, `Nord Pool`, and `ENTSO-E`
- latest coverage time
- data completeness indicator
- refresh and export actions
- six summary cards

### 6.2 Central workbench section

Purpose:

- hold the main analytical tables
- reproduce the practical views represented in the screenshots

The section uses five tabs:

1. `capacity_1h`
2. `activation_settlement_15m`
3. `daily_averages`
4. `summary_stats`
5. `field_dictionary`

### 6.3 Bottom linked analysis section

Purpose:

- turn the board into an analytical workspace instead of a static table
- show trend and provenance for whichever field the user is inspecting

Content:

- single-series trend mode
- dual-series comparison mode
- spread mode
- field definition and source explanation panel

## 7. Top Overview Design

The overview is split into two layers.

### 7.1 Header and status strip

Contains:

- page title
- market subtitle
- time window controls: `1d`, `7d`, `30d`, `custom`
- timezone selector
- source-status pills
- latest update time
- completeness and join status
- refresh action
- export action

This strip is operational, not decorative. It must surface degraded states clearly.

### 7.2 Six summary cards

The overview uses exactly six cards:

1. FCR-N average capacity price
2. aFRR average activation price
3. mFRR average activation price
4. average imbalance price
5. average Finland spot price
6. join completeness and freshness

Each card includes:

- label
- current-window aggregate
- change vs previous comparable window when available
- granularity tag
- compact sparkline

This set was chosen to cover:

- reserve capacity market
- activation market
- balancing and settlement
- spot reference price
- data reliability

without overloading first-screen cognition.

## 8. Workbench Tabs

### 8.1 Tab 1: `capacity_1h`

This is the default tab.

Purpose:

- first-read horizontal comparison of reserve-capacity structure against Finland spot

Interaction:

- sticky first column
- sticky header
- sortable columns
- show/hide columns
- click column to drive the linked chart
- select two columns for comparison mode

### 8.2 Tab 2: `activation_settlement_15m`

Purpose:

- inspect short-cycle balancing, activation, and settlement dynamics

Interaction:

- default raw 15-minute view
- optional hourly roll-up mode
- explicit indication when hourly spot values are repeated across quarter-hour rows
- anomaly emphasis for negative prices or strong spikes

### 8.3 Tab 3: `daily_averages`

This tab contains an internal segmented control:

- `daily_capacity`
- `daily_activation_settlement`

Purpose:

- move from high-frequency market reading into more stable daily structure analysis

Interaction:

- mean and median toggle
- 7-day, 30-day, and full-history shortcuts
- selecting a field updates the bottom trend to day-level mode

### 8.4 Tab 4: `summary_stats`

Purpose:

- give analysts quick distribution and volatility understanding without separate export steps

Interaction:

- filter by category: `capacity`, `activation`, `settlement`, `spot`
- sort by volatility or data count
- export table

This stays a primary tab, not a modal or secondary drawer.

### 8.5 Tab 5: `field_dictionary`

Purpose:

- make every displayed number auditable and interpretable

Interaction:

- selecting a field row jumps back to its primary table view and highlights the related column
- non-Fingrid fields must be visibly marked as external source joins
- fields with multiple possible official definitions must state the chosen interpretation explicitly

This also remains a primary tab, not secondary help text.

## 9. Linked Analysis Zone

The bottom zone is split into two panes.

### 9.1 Left pane: chart analysis

Modes:

1. single field trend
2. dual field comparison
3. spread view

Recommended spread examples:

- `imbalance - spot`
- `mFRR up - spot`
- `aFRR up - spot`

The pane should support:

- raw vs daily view
- rolling mean toggle
- normalized comparison when dual axes are not ideal

### 9.2 Right pane: field and source detail

Shows for the selected field:

- field name
- unit
- granularity
- source system
- dataset id or endpoint
- source type: `live`, `external_join`, `derived`
- coverage
- current status
- methodology note

This prevents repeated ambiguity about which number is actually on screen.

## 10. Default Highlighting And Reading Order

### 10.1 Default highlighted fields

On first load:

- `spot_price_fi`
- `imbalance_price`

Within capacity reading:

- `fcr_n_price`
- `afrr_cap_up`
- `mfrr_cap_up`

Within activation reading:

- `afrr_act_up`
- `mfrr_act_up`
- `imbalance_price`

### 10.2 Recommended reading order

1. top overview
2. `capacity_1h`
3. `activation_settlement_15m`
4. `daily_averages`
5. `summary_stats`
6. `field_dictionary`

The page supports free navigation, but the layout should still imply this reading flow.

## 11. Backend Contract Strategy

The new page must not orchestrate raw dataset joins inside the frontend.

The frontend should consume board-oriented Finland endpoints, while source-level interfaces remain available underneath.

### 11.1 Keep the source-level endpoints

These stay available:

- `/api/fingrid/*`
- `/api/finland/market-model`

Roles:

- `/api/fingrid/*` = dataset-centric source inspection and sync control
- `/api/finland/market-model` = source readiness and capability context

### 11.2 Add board-level endpoints

Recommended route family:

- `GET /api/finland/board/overview`
- `GET /api/finland/board/table`
- `GET /api/finland/board/chart`
- `GET /api/finland/board/field-catalog`
- `GET /api/finland/board/readiness`

### 11.3 Endpoint responsibilities

#### `/api/finland/board/overview`

Returns:

- source status
- latest coverage
- completeness
- six summary cards
- current window context

#### `/api/finland/board/table`

Parameters:

- `view=capacity_hourly|activation_15m|daily_capacity|daily_activation|summary|dictionary`
- `start`
- `end`
- `tz`

Returns:

- `columns`
- `rows`
- `metadata`
- `warnings`

#### `/api/finland/board/chart`

Parameters:

- `fields`
- `mode=single|compare|spread`
- `granularity=raw|hour|day`

Returns:

- chart-ready series payload

#### `/api/finland/board/field-catalog`

Returns:

- field labels
- units
- granularities
- sources
- dataset ids or endpoints
- source type
- methodology notes
- coverage

#### `/api/finland/board/readiness`

Returns source-health state using:

- `live`
- `partial`
- `fallback`
- `missing`

### 11.4 Contract boundary

Board endpoints answer:

- what the user should read now

Source endpoints answer:

- what is connected underneath and what is currently healthy

This separation should remain stable.

## 12. Route And Product Boundary Decision

### 12.1 New route

Add a new page:

- `/finland`

### 12.2 Keep existing route

Keep:

- `/fingrid`

### 12.3 Product interpretation

`/finland`:

- market-facing Finland board
- multi-source analysis workspace
- foundation for later Nordic and Europe extension

`/fingrid`:

- source-level Fingrid dataset workspace
- debugging and sync operations surface
- independent raw analysis page

## 13. Frontend Component Strategy

Recommended new page-specific structure:

- `web/src/pages/FinlandPage.jsx`
- `web/src/components/finland/FinlandBoardHeader.jsx`
- `web/src/components/finland/FinlandOverviewCards.jsx`
- `web/src/components/finland/FinlandWorkbenchTabs.jsx`
- `web/src/components/finland/FinlandDataTable.jsx`
- `web/src/components/finland/FinlandLinkedChart.jsx`
- `web/src/components/finland/FinlandFieldDetailPanel.jsx`

Keep translation and default-text behavior aligned with the existing project pattern:

- all visible strings should flow through existing i18n or default-copy helpers
- do not hard-code user-facing text without considering current translation structure

## 14. UX Quality Bar

The page should not look like a generic AI dashboard.

Visual direction:

- analysis-first
- high information density but still readable
- strong hierarchy
- stable sticky table behavior
- restrained but intentional motion
- distinctive typography and tone aligned with existing workspace design language

Specific requirements:

- avoid card-inside-card nesting
- keep major sections full-width and operational
- make table headers and grouped columns visually legible
- preserve exportability and analyst trust over ornamental layout choices

## 15. Risks And Mitigations

### 15.1 Source mismatch risk

Risk:

- reserve, activation, settlement, and spot can come from different sources and granularities

Mitigation:

- explicit field catalog
- visible source type markers
- readiness endpoint
- warnings in table metadata

### 15.2 Definition ambiguity risk

Risk:

- some fields, especially aFRR-related values, can have multiple valid official interpretations

Mitigation:

- fix one chosen field definition per displayed metric
- expose methodology note in dictionary and side panel

### 15.3 Frontend ETL drift risk

Risk:

- too much joining or interpretation in the frontend will create invisible divergence

Mitigation:

- board endpoints aggregate on the backend
- page consumes board contracts, not raw source assembly

### 15.4 Product-boundary drift risk

Risk:

- `/fingrid` and `/finland` might slowly overlap until both become unclear

Mitigation:

- document route roles explicitly
- keep `/fingrid` source-centric and `/finland` business-centric

## 16. Final Decision Summary

This design adopts the following decisions:

1. create a new `/finland` page rather than upgrading `/fingrid` into the main Finland board
2. use overview-on-top plus workbench-below information architecture
3. anchor the page around five primary tabs
4. retain a linked bottom analysis zone for trend and provenance reading
5. keep `/fingrid` as a dataset-centric source page
6. keep `/api/finland/market-model` as readiness and capability context
7. add dedicated `/api/finland/board/*` endpoints for frontend consumption
8. prioritize internal analytical utility while preserving a credible first-screen product narrative

## 17. Implementation Readiness

This scope is ready to move into implementation planning.

The next planning stage should break work into:

- backend board contracts
- Finland field registry and aggregation mapping
- new `/finland` route and page shell
- workbench table interactions
- linked chart and field-detail behavior
- focused backend and frontend regression coverage
