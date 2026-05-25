# Implementation Plan: Financial Accuracy Modules

## Overview

实现三个财务精度增强模块（Cost Structure Engine、Tax Model、Forward Price Engine），通过新建数据模型、引擎逻辑、API 路由，并扩展现有 FinancialModel 和 InvestmentParams，使投资分析达到决策级精度。采用分层实现策略：先建模型层，再建引擎层，最后集成 API 和现有系统。

## Tasks

- [x] 1. Create data model files
  - [x] 1.1 Create cost structure data models
    - Create `backend/models/cost_structure_models.py` with all Pydantic models: `FeeType`, `ConnectionType`, `AemoParticipantFee`, `AemoRegistrationFee`, `TuosDemandCharge`, `TuosEnergyCharge`, `DuosCharge`, `MlfConfig`, `FppConfig`, `RegionalFeeConfig`, `CostStructureOverrides`, `CostLineItem`, `AnnualCostBreakdown`
    - Include field validators for range constraints (MLF 0.50-1.50, fee rates ≥ 0, etc.)
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 1.7, 2.5, 11.1, 14.1, 14.2_

  - [x] 1.2 Create tax data models
    - Create `backend/models/tax_models.py` with all Pydantic models: `DepreciationMethod`, `EntityType`, `TaxConfig`, `DepreciationResult`, `AnnualTaxResult`, `AfterTaxCashFlow`, `TaxSummary`, `AfterTaxResult`
    - Include `tax_rate` property logic (30% standard, 25% base rate)
    - Include field validators for tax rate [0, 1] and effective life > 0
    - _Requirements: 4.1, 4.2, 4.5, 5.3, 5.4, 12.1, 14.3, 14.4_

  - [x] 1.3 Create forward price data models
    - Create `backend/models/forward_price_models.py` with all Pydantic models: `ScenarioType`, `EventType`, `EventConfidence`, `SupplyDemandEvent`, `EventRegistry`, `PriceDistribution`, `AnnualRevenueProjection`, `ScenarioProjection`, `ScenarioDefinition`, `ScenarioComparisonResult`
    - Include field constraints for distribution bounds (mean_spread [0, 10000], std_dev [0, 5000], spike_frequency [0, 1], capture_rate [0, 1])
    - _Requirements: 7.2, 8.1, 8.2, 8.6, 9.1, 9.2, 9.3, 13.1_

  - [x] 1.4 Extend existing financial_params.py
    - Add optional fields to `InvestmentParams`: `cost_structure_overrides`, `tax_config`, `forward_scenario`
    - Extend `CashFlowYear` with tax fields: `depreciation`, `tax_payable`, `after_tax_cash_flow`
    - Extend `InvestmentAnalysisResponse` with optional fields: `cost_breakdown`, `tax_summary`, `scenario_projections`, `after_tax_metrics`
    - Maintain full backward compatibility — no existing fields removed
    - _Requirements: 6.5, 6.6, 15.2, 15.3, 15.5_

- [x] 2. Implement Cost Structure Engine
  - [x] 2.1 Implement CostStructureEngine core logic
    - Create `backend/engines/cost_structure_engine.py`
    - Implement `get_regional_defaults(region)` with default fee parameter sets for NSW1, QLD1, VIC1, SA1, TAS1, WEM
    - Implement `calculate_annual_costs()` with FIXED/VARIABLE classification, DUOS connection-type logic, gross energy calculation
    - Implement `apply_mlf()` as multiplicative price adjustment
    - Implement override merging logic (user overrides replace defaults, unmodified retain defaults)
    - _Requirements: 1.1-1.7, 2.1-2.5, 3.1-3.6_

  - [x]* 2.2 Write property tests for Cost Structure Engine (Properties 1-6, 24)
    - **Property 1: Variable Cost Linearity** — variable cost = rate × volume for AEMO Participant, TUOS Energy, DUOS
    - **Property 2: Fixed Cost Independence from Throughput** — fixed costs unchanged by energy throughput
    - **Property 3: DUOS Connection Type Invariant** — transmission = 0, distribution = rate × throughput
    - **Property 4: MLF Multiplicative Application** — adjusted_price = price × MLF, not additive
    - **Property 5: Cost Breakdown Summation Invariant** — line items sum = total, percentages sum = 100%
    - **Property 6: Regional Override Preservation** — overridden values applied, non-overridden retain defaults
    - **Property 24: Gross Energy Calculation** — gross_energy = charge + discharge
    - Create `tests/test_cost_structure_properties.py` using Hypothesis strategies
    - **Validates: Requirements 1.1, 1.3, 1.4, 1.5, 1.6, 2.4, 2.5, 3.2, 3.3, 3.4, 3.5**

  - [x]* 2.3 Write property test for serialization round-trip (Property 20)
    - **Property 20: Cost Structure Serialization Round-Trip** — serialize → deserialize = original
    - Add to `tests/test_cost_structure_properties.py`
    - **Validates: Requirements 11.1, 11.2, 11.3**

  - [x]* 2.4 Write unit tests for Cost Structure Engine
    - Create `tests/test_cost_structure_engine.py`
    - Test regional defaults for all 6 regions
    - Test DUOS exemption for transmission-connected BESS
    - Test FPP classification and range
    - Test validation errors for invalid MLF and negative rates
    - _Requirements: 1.5, 2.1, 14.1, 14.2_

- [x] 3. Checkpoint - Cost Structure Engine
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement Tax Model
  - [x] 4.1 Implement TaxModel core logic
    - Create `backend/engines/tax_model.py`
    - Implement `calculate_depreciation()` with Diminishing Value and Prime Cost methods
    - Implement `calculate_annual_tax()` with tax loss carry-forward logic
    - Implement `calculate_after_tax_cash_flows()` generating full after-tax result with IRR/NPV
    - Handle entity type selection (standard 30% / base rate 25%)
    - _Requirements: 4.1-4.6, 5.1-5.6, 6.1-6.5_

  - [x]* 4.2 Write property tests for Tax Model (Properties 7-14)
    - **Property 7: Tax Calculation Correctness** — tax = taxable_income × rate
    - **Property 8: Taxable Income Formula** — taxable_income = revenue − opex − interest − depreciation
    - **Property 9: Tax Loss Carry-Forward** — zero tax on negative income, accumulate losses, offset future income
    - **Property 10: Diminishing Value Depreciation Formula** — (2/L) × WDV
    - **Property 11: Prime Cost Depreciation Constancy** — constant C/L each year
    - **Property 12: Depreciation Tax Shield NPV** — Σ(dep_i × rate) / (1+d)^i
    - **Property 13: After-Tax Cash Flow Formula** — P − T + D
    - **Property 14: After-Tax IRR Consistency** — NPV at IRR ≈ 0
    - Create `tests/test_tax_model_properties.py` using Hypothesis strategies
    - **Validates: Requirements 4.1-4.6, 5.1-5.6, 6.1-6.3**

  - [x]* 4.3 Write property test for Tax Model serialization (Property 21)
    - **Property 21: Tax Model Serialization Round-Trip** — serialize → deserialize = original
    - Add to `tests/test_tax_model_properties.py`
    - **Validates: Requirements 12.1, 12.2, 12.3**

  - [x]* 4.4 Write unit tests for Tax Model
    - Create `tests/test_tax_model.py`
    - Test entity type selection and default tax rates
    - Test default effective life (20 years)
    - Test depreciation method switching
    - Test validation errors for invalid tax rate and effective life
    - _Requirements: 4.5, 5.3, 5.4, 14.3, 14.4_

- [x] 5. Checkpoint - Tax Model
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. Implement Forward Price Engine
  - [x] 6.1 Implement ForwardPriceEngine core logic
    - Create `backend/engines/forward_price_engine.py`
    - Implement `_load_event_registry()` integrating `coal_retirement_schedule.json` and `capacity_data.json`
    - Implement `get_scenarios()` returning Central/High/Low definitions
    - Implement `calculate_price_distribution()` with event impact composition, BESS saturation compression, and capture rate
    - Implement `estimate_annual_revenue()` accounting for RTE, duration, cycle limits, and SoH degradation
    - Implement `generate_20year_projection()` for full scenario projection
    - Handle past-date events (log warning, exclude) and missing data files (descriptive error)
    - _Requirements: 7.1-7.5, 8.1-8.6, 9.1-9.5, 10.1-10.5, 14.5, 14.6_

  - [x]* 6.2 Write property tests for Forward Price Engine (Properties 15-19)
    - **Property 15: Event Impact Multiplicative Composition** — final_spread = base × Π(impact_factors)
    - **Property 16: BESS Saturation Compression Monotonicity** — higher ratio → lower compression factor
    - **Property 17: Price Distribution Output Bounds** — all outputs within defined ranges
    - **Property 18: Revenue Degradation Monotonicity** — revenue non-increasing over time with constant prices
    - **Property 19: Revenue Efficiency Metamorphic Property** — higher RTE → higher revenue
    - Create `tests/test_forward_price_properties.py` using Hypothesis strategies
    - **Validates: Requirements 8.3, 8.4, 8.5, 8.6, 10.2, 10.3**

  - [x]* 6.3 Write property test for Forward Price serialization (Property 22)
    - **Property 22: Forward Price Serialization Round-Trip** — serialize → deserialize = original
    - Add to `tests/test_forward_price_properties.py`
    - **Validates: Requirements 13.1, 13.2, 13.3**

  - [x]* 6.4 Write unit tests for Forward Price Engine
    - Create `tests/test_forward_price_engine.py`
    - Test scenario definitions (Central/High/Low) and their assumptions
    - Test region coverage (all 6 regions)
    - Test data file loading and missing file error handling
    - Test past-date event exclusion with warning
    - _Requirements: 9.1-9.5, 14.5, 14.6_

- [x] 7. Checkpoint - Forward Price Engine
  - Ensure all tests pass, ask the user if questions arise.

- [x] 8. Implement API routes and Financial Model integration
  - [x] 8.1 Create cost structure API route
    - Create `backend/routes/cost_structure_routes.py`
    - Implement `GET /api/cost-structure/{region}` returning default fee breakdown
    - Register route in FastAPI app
    - _Requirements: 15.1_

  - [x] 8.2 Create forward price API route
    - Create `backend/routes/forward_price_routes.py`
    - Implement `GET /api/forward-scenarios` returning available scenarios and summary parameters
    - Register route in FastAPI app
    - _Requirements: 15.4_

  - [x] 8.3 Extend investment-analysis endpoint
    - Modify `backend/routes/investment_routes.py`
    - Accept `cost_structure_overrides`, `tax_config`, `forward_scenario` parameters
    - Integrate CostStructureEngine into opex calculation (replace single combined network fee)
    - Integrate TaxModel to produce after-tax cash flows and metrics
    - Integrate ForwardPriceEngine when `forward_scenario` is specified
    - Return `cost_breakdown`, `tax_summary`, `scenario_projections`, `after_tax_metrics` in response
    - Maintain backward compatibility — omitted params use current default behavior
    - _Requirements: 3.6, 6.5, 10.5, 15.2, 15.3, 15.5, 15.6_

  - [x] 8.4 Integrate CostStructureEngine into FinancialModel
    - Modify `backend/engines/financial_model.py`
    - Replace current `fixed_om + var_om` simplified opex with CostStructureEngine component-level calculation
    - Ensure cost breakdown flows through to CashFlowYear records
    - _Requirements: 3.6_

  - [x]* 8.5 Write property test for input validation (Property 23)
    - **Property 23: Input Validation Rejection** — invalid inputs (MLF outside range, negative rates, bad tax rate, life ≤ 0) raise ValidationError
    - Add to appropriate test files (`test_cost_structure_properties.py`, `test_tax_model_properties.py`)
    - **Validates: Requirements 14.1, 14.2, 14.3, 14.4**

  - [x]* 8.6 Write integration tests
    - Create `tests/test_financial_accuracy_integration.py`
    - Test end-to-end flow: cost structure → tax → forward price → financial model
    - Test backward compatibility (no new params → same behavior as before)
    - Create `tests/test_financial_accuracy_api.py`
    - Test GET/POST endpoints, response format, HTTP error codes
    - _Requirements: 15.1-15.6_

- [x] 9. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- Each task references specific requirements for traceability
- Checkpoints ensure incremental validation between major phases
- Property tests validate all 24 correctness properties from the design document
- Unit tests validate specific examples and edge cases
- The design uses Python (FastAPI + Pydantic), all implementations use Python
- Existing `hypothesis` library is already in project dependencies
- Frontend components (CostBreakdownPanel, TaxSummaryPanel, ScenarioSelector) are not included as they belong to a separate frontend spec

## Task Dependency Graph

```json
{
  "waves": [
    { "id": 0, "tasks": ["1.1", "1.2", "1.3"] },
    { "id": 1, "tasks": ["1.4"] },
    { "id": 2, "tasks": ["2.1", "4.1", "6.1"] },
    { "id": 3, "tasks": ["2.2", "2.3", "2.4", "4.2", "4.3", "4.4", "6.2", "6.3", "6.4"] },
    { "id": 4, "tasks": ["8.1", "8.2", "8.4"] },
    { "id": 5, "tasks": ["8.3"] },
    { "id": 6, "tasks": ["8.5", "8.6"] }
  ]
}
```
