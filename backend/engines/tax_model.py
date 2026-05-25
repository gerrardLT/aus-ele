"""Australian company tax calculation engine for BESS investment analysis.

Implements ATO-compliant depreciation (Diminishing Value and Prime Cost),
tax loss carry-forward, interest deductibility, and after-tax cash flow
generation with IRR/NPV metrics.

Requirements: 4.1-4.6, 5.1-5.6, 6.1-6.5
"""

from typing import List, Optional

import numpy as np
import numpy_financial as npf

from models.financial_params import CashFlowYear
from models.tax_models import (
    AfterTaxCashFlow,
    AfterTaxResult,
    AnnualTaxResult,
    DepreciationMethod,
    DepreciationResult,
    TaxConfig,
    TaxSummary,
)


class TaxModel:
    """澳大利亚公司税计算，含折旧和税损结转。

    Supports:
    - Standard entity (30%) and base rate entity (25%) tax rates
    - Diminishing Value and Prime Cost depreciation methods
    - Indefinite tax loss carry-forward
    - Interest expense deductibility
    - After-tax IRR/NPV calculation
    """

    def __init__(self, config: TaxConfig) -> None:
        self.config = config
        self.carried_loss: float = 0.0
        self._written_down_value: float = 0.0
        self._year_counter: int = 0

    def reset(self) -> None:
        """Reset internal state for a fresh calculation run."""
        self.carried_loss = 0.0
        self._written_down_value = 0.0
        self._year_counter = 0

    def calculate_depreciation(self, year: int, capex: float) -> DepreciationResult:
        """计算指定年份的折旧额和税盾。

        Diminishing Value: annual_dep = (2.0 / effective_life) × written_down_value
        Prime Cost: annual_dep = capex / effective_life (constant each year)

        Args:
            year: Project year (1-indexed).
            capex: Total capital expenditure for the asset.

        Returns:
            DepreciationResult with depreciation amount, written-down value, and tax shield.
        """
        effective_life = self.config.effective_life_years
        tax_rate = self.config.tax_rate

        # Initialize written-down value on first call or if capex changed
        if year == 1 or self._written_down_value == 0.0:
            self._written_down_value = capex

        if self.config.depreciation_method == DepreciationMethod.DIMINISHING_VALUE:
            # DV formula: (200% / effective_life) × written_down_value
            dv_rate = 2.0 / effective_life
            depreciation_amount = dv_rate * self._written_down_value
            # Cap depreciation at remaining WDV (can't go negative)
            depreciation_amount = min(depreciation_amount, self._written_down_value)
            self._written_down_value -= depreciation_amount
        else:
            # Prime Cost: constant annual depreciation = capex / effective_life
            depreciation_amount = capex / effective_life
            # Cap at remaining WDV
            depreciation_amount = min(depreciation_amount, self._written_down_value)
            self._written_down_value -= depreciation_amount

        # Ensure WDV doesn't go negative due to floating point
        self._written_down_value = max(0.0, self._written_down_value)

        tax_shield = depreciation_amount * tax_rate

        return DepreciationResult(
            year=year,
            depreciation_amount=depreciation_amount,
            written_down_value=self._written_down_value,
            tax_shield=tax_shield,
        )

    def calculate_annual_tax(
        self,
        year: int,
        revenue: float,
        opex: float,
        interest_expense: float,
        depreciation: float,
    ) -> AnnualTaxResult:
        """计算单年税务结果，含税损结转逻辑。

        Taxable income = revenue - opex - interest_expense - depreciation
        If negative: tax = 0, loss carried forward.
        If positive with carried loss: offset by min(income, loss_balance).

        Args:
            year: Project year (1-indexed).
            revenue: Total gross revenue for the year.
            opex: Total operating expenses for the year.
            interest_expense: Debt interest expense (tax-deductible).
            depreciation: Depreciation deduction for the year.

        Returns:
            AnnualTaxResult with full tax calculation breakdown.
        """
        tax_rate = self.config.tax_rate

        # Calculate taxable income before loss offset
        taxable_income_before_loss = revenue - opex - interest_expense - depreciation

        loss_offset_applied = 0.0
        taxable_income = taxable_income_before_loss
        tax_payable = 0.0

        if taxable_income_before_loss < 0:
            # Negative taxable income: accumulate loss, no tax payable
            self.carried_loss += abs(taxable_income_before_loss)
            taxable_income = 0.0
            tax_payable = 0.0
        elif taxable_income_before_loss > 0 and self.carried_loss > 0:
            # Positive income with existing carried loss: offset
            loss_offset_applied = min(taxable_income_before_loss, self.carried_loss)
            self.carried_loss -= loss_offset_applied
            taxable_income = taxable_income_before_loss - loss_offset_applied
            tax_payable = taxable_income * tax_rate
        else:
            # Positive income, no carried loss
            taxable_income = taxable_income_before_loss
            tax_payable = taxable_income * tax_rate

        return AnnualTaxResult(
            year=year,
            gross_revenue=revenue,
            operating_expenses=opex,
            interest_expense=interest_expense,
            depreciation=depreciation,
            taxable_income_before_loss=taxable_income_before_loss,
            loss_offset_applied=loss_offset_applied,
            taxable_income=taxable_income,
            tax_payable=tax_payable,
            carried_loss_balance=self.carried_loss,
        )

    def calculate_after_tax_cash_flows(
        self,
        pre_tax_cash_flows: List[CashFlowYear],
        capex: float,
        annual_debt_service: float,
        debt_tenor: int,
        cost_of_debt: float = 0.06,
        discount_rate: float = 0.08,
    ) -> AfterTaxResult:
        """从 pre-tax 现金流序列生成 after-tax 结果。

        Calculates depreciation, interest expense (from amortization schedule),
        annual tax, and after-tax cash flows for each year. Computes pre-tax
        and after-tax IRR/NPV metrics.

        Args:
            pre_tax_cash_flows: List of CashFlowYear from the financial model.
            capex: Total capital expenditure (used for depreciation base).
            annual_debt_service: Annual debt service payment (principal + interest).
            debt_tenor: Number of years for debt repayment.
            cost_of_debt: Annual interest rate on debt (default 6%).
            discount_rate: Discount rate for NPV calculations (default 8%).

        Returns:
            AfterTaxResult with complete tax summary and metrics.
        """
        # Reset state for fresh calculation
        self.reset()

        project_life = len(pre_tax_cash_flows)

        # Calculate initial debt principal from annuity formula
        # PV = PMT × [(1 - (1+r)^-n) / r]
        if annual_debt_service > 0 and cost_of_debt > 0 and debt_tenor > 0:
            remaining_principal = float(
                npf.pv(cost_of_debt, debt_tenor, -annual_debt_service, 0)
            )
            remaining_principal = max(0.0, remaining_principal)
        else:
            remaining_principal = 0.0

        annual_tax_results: List[AnnualTaxResult] = []
        after_tax_cash_flows: List[AfterTaxCashFlow] = []
        depreciation_results: List[DepreciationResult] = []

        for cf_year in pre_tax_cash_flows:
            year = cf_year.year

            # Calculate depreciation for this year
            dep_result = self.calculate_depreciation(year, capex)
            depreciation_results.append(dep_result)

            # Calculate interest expense from amortization schedule
            if year <= debt_tenor and remaining_principal > 0 and annual_debt_service > 0:
                interest_expense = remaining_principal * cost_of_debt
                principal_payment = annual_debt_service - interest_expense
                # Ensure principal payment doesn't exceed remaining balance
                principal_payment = min(principal_payment, remaining_principal)
                remaining_principal -= principal_payment
                remaining_principal = max(0.0, remaining_principal)
            else:
                interest_expense = 0.0

            # Calculate annual tax
            tax_result = self.calculate_annual_tax(
                year=year,
                revenue=cf_year.total_revenue,
                opex=cf_year.opex,
                interest_expense=interest_expense,
                depreciation=dep_result.depreciation_amount,
            )
            annual_tax_results.append(tax_result)

            # After-tax cash flow = pre_tax_cash_flow - tax_payable
            # Note: Depreciation is a non-cash deduction that reduces tax payable,
            # but does NOT need to be added back to cash flow because pre_tax_cash_flow
            # is already a cash-basis figure (not accounting profit).
            pre_tax_cf = cf_year.net_cash_flow
            after_tax_cf = pre_tax_cf - tax_result.tax_payable

            after_tax_cash_flows.append(
                AfterTaxCashFlow(
                    year=year,
                    pre_tax_cash_flow=pre_tax_cf,
                    tax_payable=tax_result.tax_payable,
                    depreciation_add_back=0.0,  # Not needed for cash-basis flows
                    after_tax_cash_flow=after_tax_cf,
                )
            )

        # Build cash flow arrays for IRR/NPV (include -capex as year 0)
        pre_tax_cf_array = [-capex] + [cf.net_cash_flow for cf in pre_tax_cash_flows]
        after_tax_cf_array = [-capex] + [atcf.after_tax_cash_flow for atcf in after_tax_cash_flows]

        # Pre-tax metrics
        pre_tax_npv = float(npf.npv(discount_rate, pre_tax_cf_array))
        if np.isnan(pre_tax_npv):
            pre_tax_npv = 0.0

        try:
            pre_tax_irr = float(npf.irr(pre_tax_cf_array))
            if np.isnan(pre_tax_irr) or np.isinf(pre_tax_irr):
                pre_tax_irr = None
        except Exception:
            pre_tax_irr = None

        # After-tax metrics
        after_tax_npv = float(npf.npv(discount_rate, after_tax_cf_array))
        if np.isnan(after_tax_npv):
            after_tax_npv = 0.0

        try:
            after_tax_irr = float(npf.irr(after_tax_cf_array))
            if np.isnan(after_tax_irr) or np.isinf(after_tax_irr):
                after_tax_irr = None
        except Exception:
            after_tax_irr = None

        # NPV of depreciation tax shield = Σ(dep_i × tax_rate / (1 + discount_rate)^i)
        npv_dep_tax_shield = sum(
            dep.tax_shield / ((1 + discount_rate) ** dep.year)
            for dep in depreciation_results
        )

        # Totals
        total_depreciation = sum(dep.depreciation_amount for dep in depreciation_results)
        total_tax_paid = sum(tr.tax_payable for tr in annual_tax_results)

        tax_summary = TaxSummary(
            entity_type=self.config.entity_type,
            tax_rate=self.config.tax_rate,
            depreciation_method=self.config.depreciation_method,
            effective_life_years=self.config.effective_life_years,
            total_depreciation=total_depreciation,
            total_tax_paid=total_tax_paid,
            npv_depreciation_tax_shield=npv_dep_tax_shield,
            after_tax_irr=after_tax_irr,
            after_tax_npv=after_tax_npv,
            annual_results=annual_tax_results,
            after_tax_cash_flows=after_tax_cash_flows,
        )

        return AfterTaxResult(
            tax_summary=tax_summary,
            pre_tax_irr=pre_tax_irr,
            pre_tax_npv=pre_tax_npv,
            after_tax_irr=after_tax_irr,
            after_tax_npv=after_tax_npv,
        )
