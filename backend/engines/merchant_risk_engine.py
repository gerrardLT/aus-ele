"""
Merchant Risk Quantifier Engine.

基于蒙特卡洛重采样生成收入概率分布（P10/P50/P90），
计算满足银行融资门槛所需的最低合约覆盖率。

方法: 从历史价格数据中计算每日套利收入（peak-trough spread），
随机抽取 365 天 × N 次模拟，加入高斯噪声扰动，
生成年度收入分布并计算银行融资所需合约覆盖率。

Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6, 4.7, 4.8
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from typing import Optional

import numpy as np

from database import DatabaseManager
from models.outlook_models import (
    MarketExample,
    MerchantRiskRequest,
    MerchantRiskResponse,
    RevenueDistribution,
)

logger = logging.getLogger(__name__)

# Default annual debt service estimate (AUD/MW) based on typical BESS capex
# Assumes ~$1.5M/MW capex, 70% debt, 20-year term, ~6% interest
DEFAULT_ANNUAL_DEBT_SERVICE_PER_MW = 80000.0

# Interval hours for NEM 5-minute dispatch
NEM_INTERVAL_HOURS = 5.0 / 60.0  # 5 minutes = 1/12 hour

# Number of histogram bins
HISTOGRAM_BINS = 20


class MerchantRiskEngine:
    """基于蒙特卡洛重采样生成收入概率分布。

    方法: 从历史价格数据中计算每日套利收入（peak-trough spread × power × interval × efficiency），
    随机抽取 365 天日收入样本，加入噪声扰动，生成 N 个年度收入情景，
    计算 P10/P50/P90 分位数和银行融资所需合约覆盖率。
    """

    def __init__(self, db: DatabaseManager):
        self.db = db

    def simulate(
        self,
        region: str,
        power_mw: float = 100.0,
        duration_hours: float = 4.0,
        round_trip_efficiency: float = 0.87,
        n_simulations: int = 1000,
        noise_std_pct: float = 0.10,
        dscr: float = 1.3,
        bank_contract_pct: float = 0.70,
        annual_debt_service: Optional[float] = None,
        seed: Optional[int] = None,
    ) -> MerchantRiskResponse:
        """执行蒙特卡洛模拟。

        Args:
            region: NEM 区域代码 (NSW1, QLD1, VIC1, SA1, TAS1)
            power_mw: BESS 功率 (MW)
            duration_hours: BESS 持续时间 (hours)
            round_trip_efficiency: 往返效率
            n_simulations: 模拟次数
            noise_std_pct: 日收入噪声标准差比例
            dscr: 债务偿还覆盖率
            bank_contract_pct: 银行要求合约覆盖比例
            annual_debt_service: 年度债务偿还额 (AUD/MW)，None 则使用默认值
            seed: 随机数种子（用于可重复性）

        Returns:
            MerchantRiskResponse 包含收入分布、合约覆盖率和结论
        """
        rng = np.random.default_rng(seed)

        # Load historical daily revenues from price data
        daily_revenues, years_used = self._load_historical_daily_revenues(
            region=region,
            power_mw=power_mw,
            duration_hours=duration_hours,
            round_trip_efficiency=round_trip_efficiency,
        )

        years_of_data = len(years_used)

        # Data warning if insufficient history
        data_warning: Optional[str] = None
        if years_of_data < 2:
            data_warning = (
                f"Only {years_of_data} year(s) of historical data available for {region}. "
                f"Distribution may not be statistically representative. "
                f"{len(daily_revenues)} daily scenarios used."
            )

        # Run Monte Carlo simulation: resample 365 days × N times
        annual_revenues = np.array([
            self.resample_daily_revenue(
                historical_daily_revenues=daily_revenues,
                days_per_year=365,
                noise_std_pct=noise_std_pct,
                rng=rng,
            )
            for _ in range(n_simulations)
        ])

        # Normalize to per-MW values
        annual_revenues_per_mw = annual_revenues / power_mw

        # Compute distribution statistics
        p10 = float(np.percentile(annual_revenues_per_mw, 10))
        p50 = float(np.percentile(annual_revenues_per_mw, 50))
        p90 = float(np.percentile(annual_revenues_per_mw, 90))
        mean_val = float(np.mean(annual_revenues_per_mw))
        std_val = float(np.std(annual_revenues_per_mw))
        min_val = float(np.min(annual_revenues_per_mw))
        max_val = float(np.max(annual_revenues_per_mw))

        distribution = RevenueDistribution(
            p10=round(p10, 2),
            p50=round(p50, 2),
            p90=round(p90, 2),
            mean=round(mean_val, 2),
            std=round(std_val, 2),
            min_observed=round(min_val, 2),
            max_observed=round(max_val, 2),
        )

        # Compute histogram bins
        histogram_bins = self._compute_histogram_bins(annual_revenues_per_mw)

        # Bankability analysis
        debt_service = annual_debt_service or DEFAULT_ANNUAL_DEBT_SERVICE_PER_MW

        min_contract_coverage_pct = self.compute_contract_coverage(
            p90_revenue=p10,  # Use P10 (worst case) for bankability
            debt_service=debt_service,
            dscr=dscr,
            bank_contract_pct=bank_contract_pct,
        )

        # Contract revenue needed = debt_service * dscr * bank_contract_pct
        contract_revenue_needed = debt_service * dscr * bank_contract_pct

        # Bankability met if P10 merchant revenue alone covers the non-contracted portion
        # i.e., P10 * (1 - contract_pct) + contract_revenue >= debt_service * dscr
        bankability_met = min_contract_coverage_pct <= bank_contract_pct * 100

        # Historical revenue range (from simulated distribution as proxy)
        if daily_revenues:
            hist_min = round(min_val, 2)
            hist_max = round(max_val, 2)
        else:
            hist_min = 0.0
            hist_max = 0.0

        historical_revenue_range = {
            "min": hist_min,
            "max": hist_max,
            "years_used": years_used,
        }

        # Load market examples
        market_examples = self._load_market_examples(region)

        # Generate conclusion
        conclusion = self._generate_conclusion(
            region=region,
            distribution=distribution,
            min_contract_coverage_pct=min_contract_coverage_pct,
            contract_revenue_needed=contract_revenue_needed,
            debt_service=debt_service,
            dscr=dscr,
        )

        # Build metadata
        metadata = {
            "market": "NEM",
            "region": region,
            "timezone": "Australia/Sydney",
            "currency": "AUD",
            "methodology_version": "1.0",
            "model": "monte_carlo_resampling",
            "formula": "daily_revenue = peak_trough_spread × power_mw × interval_hours × efficiency",
        }

        return MerchantRiskResponse(
            metadata=metadata,
            region=region,
            power_mw=power_mw,
            duration_hours=duration_hours,
            n_simulations=n_simulations,
            distribution=distribution,
            histogram_bins=histogram_bins,
            min_contract_coverage_pct=round(min_contract_coverage_pct, 2),
            contract_revenue_needed=round(contract_revenue_needed, 2),
            bankability_met=bankability_met,
            historical_revenue_range=historical_revenue_range,
            years_of_data=years_of_data,
            data_warning=data_warning,
            market_examples=market_examples,
            conclusion=conclusion,
        )

    def resample_daily_revenue(
        self,
        historical_daily_revenues: list[float],
        days_per_year: int = 365,
        noise_std_pct: float = 0.10,
        rng: Optional[np.random.Generator] = None,
    ) -> float:
        """从历史日收入中重采样生成一个年度收入情景。

        随机抽取 days_per_year 天的日收入（有放回），
        对每天加入 ±noise_std_pct 的高斯噪声扰动，
        求和得到年度总收入。

        Args:
            historical_daily_revenues: 历史每日收入列表 (AUD)
            days_per_year: 每年天数，默认 365
            noise_std_pct: 噪声标准差比例，默认 0.10
            rng: numpy 随机数生成器

        Returns:
            年度总收入 (AUD)
        """
        if not historical_daily_revenues:
            return 0.0

        if rng is None:
            rng = np.random.default_rng()

        revenues = np.array(historical_daily_revenues)
        n_days = len(revenues)

        # Randomly sample days_per_year indices with replacement
        indices = rng.integers(0, n_days, size=days_per_year)
        sampled_days = revenues[indices]

        # Add Gaussian noise: revenue * (1 + N(0, noise_std_pct))
        noise = rng.normal(0, noise_std_pct, size=days_per_year)
        noisy_days = sampled_days * (1.0 + noise)

        # Ensure non-negative daily revenues
        noisy_days = np.maximum(noisy_days, 0.0)

        return float(np.sum(noisy_days))

    def compute_contract_coverage(
        self,
        p90_revenue: float,
        debt_service: float,
        dscr: float,
        bank_contract_pct: float,
    ) -> float:
        """计算满足银行融资门槛所需的最低合约覆盖率。

        银行要求: contracted_revenue >= debt_service * dscr * bank_contract_pct
        最低合约覆盖率 = (debt_service * dscr * bank_contract_pct - merchant_p90 * (1 - x)) / total_revenue

        简化计算:
        如果 P10 收入 >= debt_service * dscr，则不需要合约覆盖（0%）
        否则，需要合约覆盖的比例 = 1 - (P10 / (debt_service * dscr))

        Args:
            p90_revenue: P10 收入（最差情景，AUD/MW/year）
            debt_service: 年度债务偿还额 (AUD/MW)
            dscr: 债务偿还覆盖率
            bank_contract_pct: 银行要求合约覆盖比例

        Returns:
            最低合约覆盖率百分比 (0-100)
        """
        required_revenue = debt_service * dscr

        if required_revenue <= 0:
            return 0.0

        if p90_revenue >= required_revenue:
            # Merchant revenue alone covers debt service with DSCR
            return 0.0

        # Need contract coverage to fill the gap
        # contract_coverage_pct = (required - merchant_p10) / required * 100
        coverage_pct = (required_revenue - p90_revenue) / required_revenue * 100.0

        # Clamp to [0, 100]
        return max(0.0, min(100.0, coverage_pct))

    def _load_historical_daily_revenues(
        self,
        region: str,
        power_mw: float,
        duration_hours: float,
        round_trip_efficiency: float,
    ) -> tuple[list[float], list[int]]:
        """从历史价格数据计算每日套利收入。

        每日收入 = (当日最高价 - 当日最低价) × power_mw × interval_hours × efficiency
        其中 interval_hours = min(duration_hours, 可用套利时间)

        简化模型：使用每日 peak-trough spread 作为套利机会代理。

        Args:
            region: 区域代码
            power_mw: BESS 功率 (MW)
            duration_hours: BESS 持续时间 (hours)
            round_trip_efficiency: 往返效率

        Returns:
            (daily_revenues, years_used) 元组
        """
        daily_revenues: list[float] = []
        years_used: list[int] = []

        current_year = datetime.now().year

        # Try to load from trading_price tables for recent years
        candidate_years = list(range(current_year - 5, current_year + 1))

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()

                for year in candidate_years:
                    table_name = f"trading_price_{year}"

                    # Check if table exists
                    cursor.execute(
                        "SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name=%s",
                        (table_name,),
                    )
                    if not cursor.fetchone():
                        continue

                    # Query daily peak and trough prices for the region
                    # settlement_date format: "YYYY-MM-DD HH:MM:SS" or "YYYY-MM-DDTHH:MM:SS"
                    cursor.execute(
                        f"""
                        SELECT
                            SUBSTR(settlement_date, 1, 10) as trading_date,
                            MAX(rrp_aud_mwh) as peak_price,
                            MIN(rrp_aud_mwh) as trough_price
                        FROM {table_name}
                        WHERE region_id = ?
                        GROUP BY SUBSTR(settlement_date, 1, 10)
                        HAVING COUNT(*) >= 4
                        """,
                        (region,),
                    )

                    rows = cursor.fetchall()
                    if not rows:
                        continue

                    years_used.append(year)

                    for row in rows:
                        _trading_date, peak_price, trough_price = row

                        # Daily revenue = spread × power × duration × efficiency
                        # The spread represents the arbitrage opportunity
                        spread = max(0.0, peak_price - trough_price)
                        daily_revenue = (
                            spread * power_mw * duration_hours * round_trip_efficiency
                        )
                        daily_revenues.append(daily_revenue)

        except Exception as e:
            logger.warning(f"Failed to load historical price data: {e}")

        return daily_revenues, years_used

    def _compute_histogram_bins(
        self, revenues_per_mw: np.ndarray
    ) -> list[dict]:
        """计算直方图分箱数据。

        Args:
            revenues_per_mw: 年度收入/MW 数组

        Returns:
            直方图分箱列表 [{bin_start, bin_end, count, frequency}]
        """
        if len(revenues_per_mw) == 0:
            return []

        counts, bin_edges = np.histogram(revenues_per_mw, bins=HISTOGRAM_BINS)
        total = len(revenues_per_mw)

        bins: list[dict] = []
        for i in range(len(counts)):
            bins.append({
                "bin_start": round(float(bin_edges[i]), 2),
                "bin_end": round(float(bin_edges[i + 1]), 2),
                "count": int(counts[i]),
                "frequency": round(float(counts[i]) / total, 4),
            })

        return bins

    def _load_market_examples(self, region: str) -> list[MarketExample]:
        """从 market_examples.json 加载商户风险相关的市场示例。

        Args:
            region: 区域代码

        Returns:
            MarketExample 列表
        """
        data_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
            "data",
            "market_examples.json",
        )

        try:
            with open(data_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to load market_examples.json: {e}")
            return []

        examples: list[MarketExample] = []
        merchant_examples = data.get("examples", {}).get("merchant_risk", [])

        for ex in merchant_examples:
            ex_region = ex.get("region", "")
            # Include examples matching the region or general examples
            if ex_region == region or ex_region == "NEM-wide":
                examples.append(
                    MarketExample(
                        region=ex_region,
                        description=ex.get("description", ""),
                        data_year=ex.get("data_year", 2024),
                        actual_value=ex.get("p50_observed", 0.0),
                        label=ex.get("label", "actual"),
                    )
                )

        return examples

    def _generate_conclusion(
        self,
        region: str,
        distribution: RevenueDistribution,
        min_contract_coverage_pct: float,
        contract_revenue_needed: float,
        debt_service: float,
        dscr: float,
    ) -> str:
        """生成合约策略建议结论。

        Args:
            region: 区域代码
            distribution: 收入分布统计
            min_contract_coverage_pct: 最低合约覆盖率
            contract_revenue_needed: 合约收入需求
            debt_service: 年度债务偿还额
            dscr: 债务偿还覆盖率

        Returns:
            纯文本结论字符串（中英双语）
        """
        p10_k = distribution.p10 / 1000.0
        p50_k = distribution.p50 / 1000.0
        p90_k = distribution.p90 / 1000.0
        contract_k = contract_revenue_needed / 1000.0

        # English conclusion
        en_parts = [
            f"P50 = ${p50_k:.0f}k/MW/yr, P10 = ${p10_k:.0f}k/MW/yr, P90 = ${p90_k:.0f}k/MW/yr.",
        ]

        if min_contract_coverage_pct > 0:
            en_parts.append(
                f"With P10 at ${p10_k:.0f}k/MW/yr, a minimum {min_contract_coverage_pct:.0f}% "
                f"contract coverage at ${contract_k:.0f}k/MW/yr is recommended for bankability "
                f"(DSCR {dscr:.1f}x)."
            )
        else:
            en_parts.append(
                f"Merchant revenue alone (P10 = ${p10_k:.0f}k/MW/yr) is sufficient to meet "
                f"bankability requirements (DSCR {dscr:.1f}x). No contract coverage required."
            )

        en_conclusion = " ".join(en_parts)

        # Chinese conclusion
        zh_parts = [
            f"P50 = ${p50_k:.0f}k/MW/年, P10 = ${p10_k:.0f}k/MW/年, P90 = ${p90_k:.0f}k/MW/年。",
        ]

        if min_contract_coverage_pct > 0:
            zh_parts.append(
                f"基于 P10 收入 ${p10_k:.0f}k/MW/年，建议最低 {min_contract_coverage_pct:.0f}% "
                f"合约覆盖率（合约收入 ${contract_k:.0f}k/MW/年）以满足银行融资要求"
                f"（DSCR {dscr:.1f}x）。"
            )
        else:
            zh_parts.append(
                f"纯商户收入（P10 = ${p10_k:.0f}k/MW/年）已足以满足银行融资要求"
                f"（DSCR {dscr:.1f}x），无需合约覆盖。"
            )

        zh_conclusion = " ".join(zh_parts)

        return f"{en_conclusion}\n\n{zh_conclusion}"
