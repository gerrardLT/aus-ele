"""实测调度效率折扣表（后视回测 → 可达成收入口径）。

来源（2026-08-05，任务记录-2026-08-05-P0实施-基线对照与滚动回测闭环）:
    用 NEMWeb Archive 历史 pre-dispatch 真实预测（表
    predispatch_price_forecast）做三周×五区闭环滚动回测
    （scripts/backtest_rolling_predispatch.py，协议：30min 再优化、
    12h 视野、$10/MWh 价差门槛）：

        efficiency = 滚动预测驱动收入 / 完美前瞻收入
        全表均值 31.4%（n=15），区间 -20.8% ~ 51.3%

    完美前瞻（hindsight）回测收入系统性高估可达成套利收入约 3 倍。
    本模块把实测 efficiency 固化为生产收入口径的折扣表。

口径说明:
    - 折扣仅作用于**能量套利**收入；FCAS 等辅助服务收入不适用
      （本回测未建模 FCAS 投标）。
    - 样本为 100MW/2h 规格、2025-12/2026-03/2026-06 三周；外推到
      其他时长（如 4h 长时储能）前需另行验证。
    - WEM 无实测样本，统一按保守口径（P10）处理并附警告。
"""

from __future__ import annotations

from typing import Dict

# 区域实测均值（三周平均，见任务记录 6.2 节）
REGIONAL_EFFICIENCY_MEAN: Dict[str, float] = {
    "NSW1": 0.280,
    "QLD1": 0.354,
    "VIC1": 0.452,
    "SA1": 0.287,
    "TAS1": 0.195,
}

# 全局分位数口径（全表 15 点的 P10/P50/P90，见任务记录 6.4 节）
EFFICIENCY_PERCENTILES: Dict[str, float] = {
    "p10": 0.20,
    "p50": 0.31,
    "p90": 0.45,
}

# 低波动市场（TAS1 类）实测 efficiency 可为负：按预测交易不如不交易。
# 折扣表下限截断到 0，可达成口径不应出现负收入（止损=不交易）。
_FLOOR = 0.0

# 实测口径标记，写入 API 响应便于审计
METHODOLOGY_NOTE = (
    "achievable_caliber_v1: hindsight revenue discounted by realized "
    "rolling pre-dispatch efficiency (3 weeks x 5 regions, 2026-08-05)"
)


def get_realized_efficiency(region: str, caliber: str = "p50") -> tuple[float, list[str]]:
    """返回指定区域与口径的实测效率折扣及警告列表。

    Args:
        region: NEM 区域或 WEM。
        caliber: "p10"（保守）/ "p50"（中央）/ "p90"（乐观）/
                 "regional"（区域实测均值，截断到非负）。

    Returns:
        (discount, warnings)：discount ∈ [0, 1]；warnings 记录外推与
        低波动市场风险。
    """
    warnings: list[str] = []

    if caliber == "regional":
        if region in REGIONAL_EFFICIENCY_MEAN:
            value = REGIONAL_EFFICIENCY_MEAN[region]
            if value < EFFICIENCY_PERCENTILES["p10"]:
                warnings.append(
                    "low_volatility_market: realized efficiency near or below "
                    "zero in some weeks; achievable arbitrage may be negligible"
                )
            return max(_FLOOR, value), warnings
        warnings.append("no_regional_sample: falling back to p10")
        return EFFICIENCY_PERCENTILES["p10"], warnings

    if caliber not in EFFICIENCY_PERCENTILES:
        raise ValueError(f"unknown caliber '{caliber}'; use p10/p50/p90/regional")

    value = EFFICIENCY_PERCENTILES[caliber]
    if region == "WEM":
        warnings.append("wem_no_sample: WEM not covered by rolling backtest; using global percentile")
    if region == "TAS1":
        warnings.append("tas1_negative_weeks: realized efficiency was negative in shoulder weeks")
    return value, warnings
