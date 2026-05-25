"""Tax data models for Australian company tax calculation.

Provides Pydantic models for tax configuration, depreciation results,
annual tax results, after-tax cash flows, and summary outputs.
Supports standard (30%) and base rate (25%) entity types with
Diminishing Value and Prime Cost depreciation methods.
"""

from enum import Enum
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator


class DepreciationMethod(str, Enum):
    """ATO-compliant depreciation methods for BESS assets."""

    DIMINISHING_VALUE = "diminishing_value"
    PRIME_COST = "prime_cost"


class EntityType(str, Enum):
    """Australian company entity types for tax rate determination."""

    STANDARD = "standard"  # 30% tax rate
    BASE_RATE = "base_rate"  # 25% tax rate (turnover < $50M)


class TaxConfig(BaseModel):
    """税务计算配置。

    Attributes:
        entity_type: 实体类型，决定适用税率
        depreciation_method: 折旧方法（递减余额法或直线法）
        effective_life_years: 资产有效寿命（年），必须 > 0
        custom_tax_rate: 自定义税率，覆盖实体类型默认值，范围 [0, 1]
    """

    entity_type: EntityType = EntityType.STANDARD
    depreciation_method: DepreciationMethod = DepreciationMethod.DIMINISHING_VALUE
    effective_life_years: int = Field(default=20, gt=0)
    custom_tax_rate: Optional[float] = Field(default=None, ge=0.0, le=1.0)

    @field_validator("custom_tax_rate")
    @classmethod
    def validate_custom_tax_rate(cls, v: Optional[float]) -> Optional[float]:
        """Validate custom tax rate is within [0, 1] range."""
        if v is not None and (v < 0.0 or v > 1.0):
            raise ValueError("Tax rate must be between 0 and 1")
        return v

    @property
    def tax_rate(self) -> float:
        """Return applicable tax rate based on entity type or custom override.

        Returns:
            0.30 for standard entities, 0.25 for base rate entities,
            or the custom_tax_rate if specified.
        """
        if self.custom_tax_rate is not None:
            return self.custom_tax_rate
        return 0.30 if self.entity_type == EntityType.STANDARD else 0.25


class DepreciationResult(BaseModel):
    """单年折旧计算结果。

    Attributes:
        year: 项目年份
        depreciation_amount: 当年折旧额
        written_down_value: 年末账面余值
        tax_shield: 折旧税盾（depreciation_amount × tax_rate）
    """

    year: int
    depreciation_amount: float
    written_down_value: float
    tax_shield: float


class AnnualTaxResult(BaseModel):
    """单年税务计算结果。

    Attributes:
        year: 项目年份
        gross_revenue: 总收入
        operating_expenses: 运营费用
        interest_expense: 利息支出
        depreciation: 折旧额
        taxable_income_before_loss: 税损抵扣前应税收入
        loss_offset_applied: 本年应用的税损抵扣额
        taxable_income: 最终应税收入
        tax_payable: 应缴税额
        carried_loss_balance: 年末累计税损余额
    """

    year: int
    gross_revenue: float
    operating_expenses: float
    interest_expense: float
    depreciation: float
    taxable_income_before_loss: float
    loss_offset_applied: float
    taxable_income: float
    tax_payable: float
    carried_loss_balance: float


class AfterTaxCashFlow(BaseModel):
    """单年税后现金流。

    Attributes:
        year: 项目年份
        pre_tax_cash_flow: 税前现金流
        tax_payable: 应缴税额
        depreciation_add_back: 折旧加回（非现金项）
        after_tax_cash_flow: 税后现金流 = pre_tax - tax + depreciation_add_back
    """

    year: int
    pre_tax_cash_flow: float
    tax_payable: float
    depreciation_add_back: float
    after_tax_cash_flow: float


class TaxSummary(BaseModel):
    """税务计算汇总。

    Attributes:
        entity_type: 实体类型
        tax_rate: 适用税率
        depreciation_method: 折旧方法
        effective_life_years: 有效寿命
        total_depreciation: 项目生命周期总折旧额
        total_tax_paid: 项目生命周期总缴税额
        npv_depreciation_tax_shield: 折旧税盾净现值
        after_tax_irr: 税后内部收益率
        after_tax_npv: 税后净现值
        annual_results: 逐年税务结果
        after_tax_cash_flows: 逐年税后现金流
    """

    entity_type: EntityType
    tax_rate: float
    depreciation_method: DepreciationMethod
    effective_life_years: int
    total_depreciation: float
    total_tax_paid: float
    npv_depreciation_tax_shield: float
    after_tax_irr: Optional[float]
    after_tax_npv: float
    annual_results: List[AnnualTaxResult]
    after_tax_cash_flows: List[AfterTaxCashFlow]


class AfterTaxResult(BaseModel):
    """完整税后分析结果，包含税前/税后对比指标。

    Attributes:
        tax_summary: 税务计算汇总
        pre_tax_irr: 税前内部收益率
        pre_tax_npv: 税前净现值
        after_tax_irr: 税后内部收益率
        after_tax_npv: 税后净现值
    """

    tax_summary: TaxSummary
    pre_tax_irr: Optional[float]
    pre_tax_npv: float
    after_tax_irr: Optional[float]
    after_tax_npv: float
