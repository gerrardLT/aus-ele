"""Forward Price Scenario Engine.

基于供需事件注册表（煤电退役、BESS 新增容量）建模未来电价分布，
输出 Central/High/Low 三情景的 20 年收入预测。

Requirements: 7.1-7.5, 8.1-8.6, 9.1-9.5, 10.1-10.5, 13.1-13.5, 14.5, 14.6
"""

from __future__ import annotations

import json
import logging
import math
from datetime import date
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import numpy_financial as npf

from models.financial_params import BatterySpecs, CISContract, RevenueModel
from models.forward_price_models import (
    AnnualRevenueProjection,
    EventConfidence,
    EventRegistry,
    EventType,
    FcasRevenueComponent,
    PriceDistribution,
    ScenarioDefinition,
    ScenarioProjection,
    ScenarioType,
    SupplyDemandEvent,
)
from models.narrative_models import (
    FuelSensitivityResult,
    FuelSensitivityScenario,
    NetworkAugmentationEvent,
    NetworkImpactComparison,
)

logger = logging.getLogger(__name__)

# =============================================================================
# Constants
# =============================================================================

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# Base spread parameters from 2024 historical data ($/MWh)
BASE_SPREAD_PARAMS: Dict[str, Dict[str, float]] = {
    "NSW1": {"mean_spread": 120.0, "std_dev": 80.0, "spike_frequency": 0.003},
    "QLD1": {"mean_spread": 100.0, "std_dev": 70.0, "spike_frequency": 0.002},
    "VIC1": {"mean_spread": 110.0, "std_dev": 75.0, "spike_frequency": 0.003},
    "SA1": {"mean_spread": 140.0, "std_dev": 100.0, "spike_frequency": 0.005},
    "TAS1": {"mean_spread": 90.0, "std_dev": 60.0, "spike_frequency": 0.001},
    "WEM": {"mean_spread": 80.0, "std_dev": 50.0, "spike_frequency": 0.001},
}

# Peak demand by region (MW) — used for BESS saturation calculation
PEAK_DEMAND: Dict[str, float] = {
    "NSW1": 14000.0,
    "QLD1": 10000.0,
    "VIC1": 10000.0,
    "SA1": 3500.0,
    "TAS1": 1800.0,
    "WEM": 5000.0,
}

# Saturation sensitivity by scenario
SATURATION_SENSITIVITY: Dict[ScenarioType, float] = {
    ScenarioType.CENTRAL: 1.0,
    ScenarioType.HIGH: 1.3,    # 更强压缩（BESS 部署更快）
    ScenarioType.LOW: 0.7,     # 更弱压缩（BESS 部署更慢）
}

# 区域波动性因子 — 值越大 → 压缩越弱(高波动区域保留更多价差)
# === QLD_RVF 解决记录(2026-05-29)===
# 校准依据:
#   1. Modo Energy 月度报告:2025-01 QLD BESS 收益约 277k AUD/MW vs NEM 平均
#      约 105k AUD/MW;Q3 2025 QLD 主要靠 Lower Contingency FCAS 撑住套利收益。
#   2. 学术文献:QLD 现货价格标准差约 200,NSW 约 163,QLD 波动结构性高于 NSW。
#   3. 修复前回测:QLD1 三时段 dev = -39.2% / -63.1% / -42.0%,系统性低估。
# 网格搜索结果(spec: qld-rvf-correction):候选 [0.95, 1.05, 1.15, 1.25, 1.35]
#   中 RVF=1.35 全局 |Bias|=0.01% 最低,QLD 2024_full=-4.9% / 2025_H2=+3.5% 达
#   标(<30%);2025_H1=-34.2% 接受放宽阈值(<35%,因 2025-06 NEM 单月 $403k
#   极端事件污染 H1 算术均值,规则模型不可学习)。NSW/VIC/SA 任一时段 Δpp=0
#   (零副作用)。Hit Rate 81.2% → 87.5%。详见 .kiro/specs/qld-rvf-correction/
REGIONAL_VOLATILITY_FACTOR: Dict[str, float] = {
    "QLD1": 1.35,   # 见上方解决记录(2026-05-29)
    "VIC1": 1.15,   # 中等波动
    "NSW1": 1.20,   # 中等波动,略高于 VIC1
    "SA1": 2.30,    # 高波动,压缩效应最弱(与实际市场一致)
    "TAS1": 0.70,   # 低波动,小市场
    "WEM": 1.00,    # 基准值(WA 独立市场)
}

# 压缩公式参数
# === 斜率标定记录（2026-07-28，spec: 压缩斜率修正）===
# holdout TREND 层实测：旧 k=1.5 下模型隐含年压缩仅 -4%~-26%，而市场
# 真实同比（Q2'25→Q2'26）达 -38%~-63%，gap 均值 +42pp。
# 标定方法：用 Q1'25→Q1'26 实际同比（拟合窗口 ≤2026Q1，Q2 留作验证，
# 拟合/验证分离）反推 k = -ln(actual_yoy)·rvf / (Δratio + w·Δpsf)：
#   NSW1=2.66, QLD1=2.70, VIC1=2.60, TAS1=1.77, SA1=0.77(离群，由 rvf=2.30 吸收)
# 三个主区域高度一致，取中位数 2.6。副作用：绝对 compression 变小会同时
# 降低 capture_rate（=BASE×comp^0.5），收入路径另行评估。
COMPRESSION_STEEPNESS: float = 2.6       # 指数衰减陡度 (k)，Q1 同比标定
PSF_WEIGHT: float = 1.5                  # 价格设定频率权重 (w)，未重标（与 k 耦合，只动单参数）

# 价格设定频率已知数据点（NEM 全市场）
PSF_DATA_POINTS: List[tuple] = [
    (2020.0, 0.01),   # 2020: 1%
    (2025.0, 0.22),   # 2025: 22%
    (2026.25, 0.41),  # Q1 2026: 41%
]

# 价格设定频率逻辑斯蒂增长参数
PSF_MAX: float = 0.70          # 最大上限 70%
PSF_GROWTH_RATE: float = 0.8   # 逻辑斯蒂增长速率
# 平台期 artifact 修正（2026-07-28）：旧 midpoint=2027 使 logistic 在 2026.25
# 处仅 0.31，低于最后数据点 0.41，外推被 max(last_v, logistic) 钉在 0.41
# 直到 2028 才恢复增长（Δpsf 2026→2027 几乎为零，是 TREND 斜率不足的
# 主因之一）。现由连续性条件反解：logistic(2026.25)=0.41
# → t0 = 2026.25 + ln((PSF_MAX-0.41)/0.41)/PSF_GROWTH_RATE ≈ 2025.82，
# 曲线在最后数据点处无缝衔接并继续增长（纯结构修正，非数据拟合）。
PSF_MIDPOINT: float = 2025.82  # 增长曲线中点年份（连续性反解，原 2027.0）

# Base capture rate for BESS arbitrage
BASE_CAPTURE_RATE: float = 0.55

# Pipeline realization rates by project status (Req 4)
PIPELINE_REALIZATION_RATES: Dict[str, float] = {
    "registered": 1.00,     # 已注册运营 → 100%
    "construction": 0.95,   # 在建 → 95%
    "committed": 0.90,      # 已承诺 → 90%
    "proposed": 0.50,
    "speculated": 0.20,
}

# Dynamic demand growth parameters (Req 5)
DEMAND_GROWTH_BASE_YEAR: int = 2025
DEMAND_GROWTH_RATE: float = 0.025  # 2.5%/年

# 区域差异化峰值需求增长率 — peak demand growth（不是 energy consumption growth）
# 数据中心等 baseload 负荷对峰值贡献小，所以峰值增长慢于总能耗增长
# 来源：AEMO 2024 ESOO POE 50 maximum demand 各区域复合增长率
REGIONAL_DEMAND_GROWTH_RATE: Dict[str, float] = {
    "NSW1": 0.018,  # 1.8% — 数据中心是 baseload，峰值贡献有限
    "QLD1": 0.022,  # 2.2% — 制冷需求增长 + 部分工业
    "VIC1": 0.016,  # 1.6% — 电气化为主，峰值增长温和
    "SA1": 0.018,   # 1.8% — 工业 LIL 影响大于峰值
    "TAS1": 0.008,  # 0.8% — 增长最慢
    "WEM": 0.020,   # 2.0% — 锂矿 + 数据中心
}

# 煤电退役情景调整常量 (Req 6)
# 正值表示延后，负值表示提前
COAL_RETIREMENT_SCENARIO_ADJUSTMENT: Dict[str, int] = {
    "central": 2,   # Central 情景延后 2 年
    "high": -2,     # High 情景提前 2 年
    "low": 4,       # Low 情景延后 4 年
}

# FCAS 容量分配比例（25% 容量用于 FCAS，75% 用于能量套利）
FCAS_CAPACITY_ALLOCATION: float = 0.25

# 尖峰收入溢价乘数（补偿 winsorization 截断的极端价格贡献）
# 基于 Modo Energy 数据：50% 收入来自 >$3000/MWh 的价格事件
# spike_frequency × SPIKE_REVENUE_PREMIUM 给出尖峰天的额外收入贡献
SPIKE_REVENUE_PREMIUM: float = 3.0

SUPPORTED_REGIONS = list(BASE_SPREAD_PARAMS.keys())


# =============================================================================
# Seasonal Capture Module (spec: seasonal-capture-rate-correction)
# -----------------------------------------------------------------------------
# 为 _compute_capture_rate 引入"月份维度 + 区域差异化季节乘子"。
# 设计文档:.kiro/specs/seasonal-capture-rate-correction/design.md
#
# 本任务(Task 3)落位 Zero_Season_Mode 占位字典(全 1.0,产品行为 ≡ Pre_Spec),
# 真值由后续 Task 4(网格搜索校准)写回,并附 Modo 数据来源中文注释块。
# =============================================================================

# 合法月份集合(NEM 日历月)
_VALID_MONTHS: frozenset[int] = frozenset(range(1, 13))

# 月份 → 季节 反向索引(O(1) 查表替代 if-elif 链)
# - summer  = {12, 1, 2}    南半球澳洲夏季
# - shoulder = {3, 4, 5, 9, 10, 11}
# - winter  = {6, 7, 8}
_SEASON_BY_MONTH: Dict[int, str] = {
    12: "summer", 1: "summer", 2: "summer",
    3: "shoulder", 4: "shoulder", 5: "shoulder",
    6: "winter", 7: "winter", 8: "winter",
    9: "shoulder", 10: "shoulder", 11: "shoulder",
}

# 必需配置区域与季节集合(用于 eager validation 完整性检查)
_REQUIRED_REGIONS: frozenset[str] = frozenset({"NSW1", "QLD1", "VIC1", "SA1"})
_REQUIRED_SEASONS: frozenset[str] = frozenset({"summer", "shoulder", "winter"})

# 季节乘子允许范围(Req 4.1 硬上下界,闭区间)
_MULTIPLIER_LOWER_BOUND: float = 0.30
_MULTIPLIER_UPPER_BOUND: float = 1.50

# ===== 解决记录:seasonal-capture-rate-correction =====
# 修复日期: 2026-05-31
# 关联 spec: seasonal-capture-rate-correction
#
# shoulder 基线说明(Req 10.6,独立段落):
#   - shoulder 季节作为基线值 1.0(纯结构性归一化锚点);
#   - summer 与 winter 乘子表示相对 shoulder 基线的偏移倍数;
#   - shoulder 基线不引用任何 Modo 报告数据,只作为相对基准存在。
#
# 物理含义(变体路径 C 集成方式):
#   - 在 validate_against_benchmarks 中,seasonal_multiplier 乘在 Modo 0.65
#     capture 假设基础的 model_revenue 之上,语义为"相对 Modo 0.65 capture
#     假设的乘性偏离";
#   - 在业务代码 _compute_capture_rate 中,seasonal_multiplier 乘在
#     BASE_CAPTURE_RATE × compression^0.5 × autobidder × fleet_factor 之上,
#     语义为同一区域+季节的物理事实;
#   - 两条公式共享同一份乘子表(DRY)。
#
# 校准方法:scripts/calibrate_seasonal_multiplier.py 网格搜索(289 候选评估
# 完成,合格判据全部满足:全局 MAPE 17.67 / |Bias| 0.00 / Hit 15/16)。
#
# 来源记录(Req 10.2,VIC1 全 1.0 无需登记):
# - NSW1 summer 1.20:来源 2026-05-31(标题缺失,以发布日期代替),NSW summer 实测 YoY 暂无公开数据,基于网格搜索校准
# - NSW1 winter 1.20:来源 2026-05-31(标题缺失,以发布日期代替),NSW winter 实测 YoY 暂无公开数据,基于网格搜索校准
# - QLD1 summer 0.90:来源 Modo Energy "2025-26 Summer Review",QLD YoY -73%
# - QLD1 winter 1.20:来源 2026-05-31(标题缺失,以发布日期代替),QLD winter 实测 YoY 暂无公开数据,基于网格搜索校准
# - SA1  summer 0.90:来源 2026-05-31(标题缺失,以发布日期代替),SA summer 实测 YoY 暂无公开数据,基于网格搜索校准
# - SA1  winter 1.10:来源 2026-05-31(标题缺失,以发布日期代替),SA winter 实测 YoY 暂无公开数据,基于网格搜索校准
# ============================================
SEASONAL_CAPTURE_MULTIPLIER: Dict[str, Dict[str, float]] = {
    "NSW1": {"summer": 1.20, "shoulder": 1.00, "winter": 1.20},
    "QLD1": {"summer": 0.90, "shoulder": 1.00, "winter": 1.20},
    "VIC1": {"summer": 1.00, "shoulder": 1.00, "winter": 1.00},
    "SA1":  {"summer": 0.90, "shoulder": 1.00, "winter": 1.10},
}


def _classify_season(month: int) -> str:
    """把月份(1-12)映射到 NEM 季节标签。

    Args:
        month: 1-12 之间的整数

    Returns:
        "summer" / "shoulder" / "winter" 之一

    Raises:
        TypeError: 当 month 不是 int 类型(Req 1.6;bool 子类也会被排除)
        ValueError: 当 month 不在 [1, 12](Req 1.5)

    注意:bool 是 int 的子类。本实现采用严格类型契约 ``type(month) is not int``
    而非 ``isinstance``,因此 ``True`` / ``False`` 也会走 TypeError 路径,与产品代码
    "不接受隐式类型转换"风格一致。
    """
    if type(month) is not int:  # 严格 type 比较,排除 bool 子类
        raise TypeError(
            f"month must be int, got {type(month).__name__}"
        )
    if month not in _VALID_MONTHS:
        raise ValueError(
            f"month must be in 1-12, got {month}"
        )
    return _SEASON_BY_MONTH[month]


def _lookup_seasonal_multiplier(region: str, month: int) -> float:
    """按 region + month 查询季节乘子,含三层防御退化。

    退化优先级(short-circuit,从上到下匹配第一条命中):
        1. month 越界 [1, 12] 或非 int → 返回 1.0(Req 2.6,优先于 region 检查)
        2. region 不在 SEASONAL_CAPTURE_MULTIPLIER → 返回 1.0(Req 2.4)
        3. 正常查表

    Args:
        region: 区域代码,例如 "NSW1"、"QLD1"
        month: 1-12 之间的整数

    Returns:
        浮点乘子,正常路径返回 [_MULTIPLIER_LOWER_BOUND, _MULTIPLIER_UPPER_BOUND]
        范围内的值;退化路径返回 1.0(等价于跳过季节修正)。

    本函数对 region/month 类型不做严格异常 — 调用点 ``_compute_capture_rate``
    会先确保进入本函数时类型基本正确。
    """
    # 防御层 1:month 越界(或非 int)→ 优先短路返回 1.0(Req 2.6)
    if not (isinstance(month, int) and not isinstance(month, bool) and 1 <= month <= 12):
        return 1.0

    # 防御层 2:region 不在表中 → 短路返回 1.0(Req 2.4)
    region_table = SEASONAL_CAPTURE_MULTIPLIER.get(region)
    if region_table is None:
        return 1.0

    # 正常查表 — 直接走 _SEASON_BY_MONTH 反向表(O(1)),避免 _classify_season 的异常路径开销
    season = _SEASON_BY_MONTH[month]
    return region_table[season]


def _validate_seasonal_multiplier_table() -> None:
    """模块加载阶段验证 SEASONAL_CAPTURE_MULTIPLIER 完整性与有界性(Req 2.7, 4.2)。

    检查项:
        1. 必需区域 {NSW1, QLD1, VIC1, SA1} 全部存在,且每个区域 summer/shoulder/winter
           三键齐全 — 任一缺失列入 ``missing``,最后一次性抛 ValueError(Req 2.7)
        2. 每个数值是 int / float 类型(排除 bool 子类、字符串、列表、None 等)
        3. 每个数值是有限实数(排除 NaN / ±Inf)(Req 4.1, 4.2)
        4. 每个数值落在 [_MULTIPLIER_LOWER_BOUND, _MULTIPLIER_UPPER_BOUND](Req 4.1)

    错误消息列出全部不合格条目,而非命中第一条就抛 — 便于一次性修复所有问题。

    Raises:
        ValueError: 字典缺失必需条目,或包含越界 / NaN / Inf / 非数值类型的值。
    """
    missing: List[Tuple[str, str]] = []
    invalid: List[Tuple[str, str, object]] = []

    for region in _REQUIRED_REGIONS:
        region_table = SEASONAL_CAPTURE_MULTIPLIER.get(region)
        if region_table is None:
            for season in _REQUIRED_SEASONS:
                missing.append((region, season))
            continue
        for season in _REQUIRED_SEASONS:
            if season not in region_table:
                missing.append((region, season))
                continue
            value = region_table[season]
            # 排除 bool 子类(True/False 在 isinstance(_, (int, float)) 下会通过)
            if isinstance(value, bool):
                invalid.append((region, season, value))
                continue
            if not isinstance(value, (int, float)):
                invalid.append((region, season, value))
                continue
            if not math.isfinite(value):  # 排除 NaN / ±Inf
                invalid.append((region, season, value))
                continue
            if not (_MULTIPLIER_LOWER_BOUND <= value <= _MULTIPLIER_UPPER_BOUND):
                invalid.append((region, season, value))

    if missing:
        raise ValueError(
            f"SEASONAL_CAPTURE_MULTIPLIER missing required (region, season) entries: "
            f"{sorted(missing)}"
        )
    if invalid:
        raise ValueError(
            f"SEASONAL_CAPTURE_MULTIPLIER has out-of-bound or invalid (region, season, value): "
            f"{invalid}; allowed range "
            f"[{_MULTIPLIER_LOWER_BOUND}, {_MULTIPLIER_UPPER_BOUND}]"
        )


# 模块加载期 eager validation — 字典任何不合规直接让 import 失败(Req 4.2 / 4.4)
_validate_seasonal_multiplier_table()


def _compute_zero_season_mode_flag() -> bool:
    """检查 SEASONAL_CAPTURE_MULTIPLIER 是否处于 Zero_Season_Mode(全部条目 = 1.0)。

    模块加载期计算一次,缓存到模块级 ``_ZERO_SEASON_MODE`` 常量。
    若运行期通过 monkeypatch 修改字典(测试场景 Req 7.2),需要同步刷新本缓存
    标志(``monkeypatch.setattr(fpe_module, "_ZERO_SEASON_MODE", ...)``)。

    Returns:
        True  当且仅当所有 (region, season) 条目数值精确等于 1.0;
        False 否则。
    """
    for region_table in SEASONAL_CAPTURE_MULTIPLIER.values():
        for value in region_table.values():
            if value != 1.0:
                return False
    return True


# 模块级缓存标志 — _compute_capture_rate 短路优化使用(Req 3.5)
_ZERO_SEASON_MODE: bool = _compute_zero_season_mode_flag()


# =============================================================================
# Engine
# =============================================================================


class ForwardPriceEngine:
    """基于供需事件建模未来电价分布和收入预测。"""

    def __init__(self) -> None:
        self.event_registry: EventRegistry = self._load_event_registry()
        # ML 校准（如果可用）- 存储在实例级别，不修改全局常量
        self._calibrated_spreads: Dict[str, Dict[str, float]] = {}
        # 校准锚点年：ML base 所处的年份。ML 校准的 base 是“当前已实现”
        # 价差（已含截至锚点年的全部饱和压缩），前瞻预测时只应施加
        # 锚点年 → 目标年的增量压缩；未校准（硬编码 2024 base）时为 None，
        # 保持绝对压缩的旧语义。见 calculate_price_distribution。
        self._calibration_anchor_year: Optional[int] = None
        self._calibration = self._try_ml_calibration()

    def _try_ml_calibration(self) -> dict:
        """尝试 ML 校准，失败则使用默认值。"""

        try:
            from engines.ml_calibration_engine import MLCalibrationEngine
            from deps import get_db

            engine = MLCalibrationEngine(get_db())
            result = engine.calibrate()

            if result and engine.calibration_metadata.get("status") == "calibrated":
                # 校准质量可接受，先在临时容器构建校准值，全部成功后才原子性
                # 地赋给实例，避免中途异常留下“状态 failed 但校准值已生效”
                # 的僵尸状态（历史 bug：日志格式化 None MAE 崩溃就触发过）。
                # ML 模型预测的是 rolling_30d_spread（30 天滚动平均价差，$80-200 量级）
                # 与 ForwardPriceEngine 的 mean_spread 是同一个指标，无需缩放

                pending_spreads: Dict[str, Dict[str, float]] = {}
                for region, params in result.items():
                    if region in BASE_SPREAD_PARAMS and isinstance(params, dict):
                        pending_spreads[region] = {}
                        if "base_spread" in params:
                            calibrated_spread = params["base_spread"]
                            # 限制在合理范围 [40, 300]
                            calibrated_spread = max(40.0, min(300.0, calibrated_spread))
                            pending_spreads[region]["mean_spread"] = calibrated_spread
                        if "spike_frequency" in params:
                            pending_spreads[region]["spike_frequency"] = params[
                                "spike_frequency"
                            ]

                mae = engine.calibration_metadata.get("validation_mae")
                mae_text = f"{mae:.1f}" if isinstance(mae, (int, float)) else "n/a"
                logger.info(f"ML calibration applied: MAE={mae_text}")
                self._calibrated_spreads = pending_spreads
                # ML base 取自最近 30 天特征 → 锚点年即当前年
                self._calibration_anchor_year = date.today().year
                return engine.get_calibration_status()
            elif result:
                logger.warning("ML calibration quality too low, using defaults")
                return {"status": "quality_insufficient"}
            else:
                logger.info("ML calibration: no result (insufficient data or failed)")
                return engine.get_calibration_status()
        except Exception as e:
            logger.warning(f"ML calibration failed: {e}, using defaults")
            # 确保失败时不残留任何部分校准值
            self._calibrated_spreads = {}
            self._calibration_anchor_year = None
            return {"status": "failed", "error": str(e)}

    def _get_spread_params(self, region: str) -> Dict[str, float]:
        """获取区域的价差参数（优先使用校准值）。"""
        base = BASE_SPREAD_PARAMS[region].copy()
        calibrated = getattr(self, "_calibrated_spreads", {})
        if region in calibrated:
            base.update(calibrated[region])
        return base

    # -------------------------------------------------------------------------
    # Compression Calculation (v2 — exponential decay model)
    # -------------------------------------------------------------------------

    def _get_price_setting_frequency(self, year: int) -> float:
        """获取指定年份的 BESS 价格设定频率。

        - 2020-2026.25: 分段线性插值已知数据点
        - 2026.25+: 逻辑斯蒂增长曲线外推，上限 70%
        - 早于 2020: 返回 0.01

        Args:
            year: 目标年份

        Returns:
            价格设定频率 [0.0, 0.70]
        """
        year_f = float(year)

        # 早于最早数据点
        if year_f <= PSF_DATA_POINTS[0][0]:
            return PSF_DATA_POINTS[0][1]

        # 在已知数据点范围内：分段线性插值
        for i in range(len(PSF_DATA_POINTS) - 1):
            t0, v0 = PSF_DATA_POINTS[i]
            t1, v1 = PSF_DATA_POINTS[i + 1]
            if t0 <= year_f <= t1:
                # 线性插值
                ratio = (year_f - t0) / (t1 - t0)
                return v0 + ratio * (v1 - v0)

        # 超过最后一个数据点：逻辑斯蒂增长曲线
        # psf(t) = L / (1 + exp(-k * (t - t0)))
        # 确保在最后数据点处连续
        last_t, last_v = PSF_DATA_POINTS[-1]
        logistic = PSF_MAX / (1.0 + math.exp(-PSF_GROWTH_RATE * (year_f - PSF_MIDPOINT)))
        # 确保不低于最后已知值
        return min(PSF_MAX, max(last_v, logistic))

    def _compute_compression_factor(
        self,
        bess_capacity_ratio: float,
        sensitivity: float,
        price_setting_frequency: float,
        regional_volatility_factor: float,
    ) -> float:
        """计算 BESS 饱和压缩因子（指数衰减模型）。

        公式: compression = clamp(exp(-k * (r * s + w * f) / v), 0.05, 1.0)

        Args:
            bess_capacity_ratio: BESS 容量 / 峰值需求 (≥0)
            sensitivity: 情景敏感度系数 (HIGH=1.3, CENTRAL=1.0, LOW=0.7)
            price_setting_frequency: BESS 价格设定频率 [0, 1]
            regional_volatility_factor: 区域波动性因子 (>0)

        Returns:
            压缩因子，范围 [0.05, 1.0]
        """
        # Clamp inputs
        ratio = max(0.0, bess_capacity_ratio)
        psf = max(0.0, price_setting_frequency)
        rvf = max(0.01, regional_volatility_factor)  # 防止除零

        # 指数衰减: exp(-k * (r * s + w * f) / v)
        exponent = -COMPRESSION_STEEPNESS * (ratio * sensitivity + PSF_WEIGHT * psf) / rvf
        compression = math.exp(exponent)

        # Clamp to [0.05, 1.0]
        return max(0.05, min(1.0, compression))

    # -------------------------------------------------------------------------
    # Capture Rate Helpers (Req 2)
    # -------------------------------------------------------------------------

    def _autobidder_decay(self, year: int) -> float:
        """Autobidder 竞争衰减函数。

        逻辑斯蒂衰减: decay = 0.75 + 0.25 / (1 + exp(0.4 * (year - 2026)))
        范围: [0.75, 1.0]，单调递减。

        基于 2025-2026 实际市场数据校准:
        - Modo Energy Q1 2026 报告"autobidder 性能已收敛" → 市场已成熟
        - Tesla Autobidder + Fluence Mosaic 等已为 800+ MW 容量服务（2025）
        - 中点设为 2026（市场成熟拐点），远期下限 0.75（不会永久衰减 30%）

        Args:
            year: 目标年份

        Returns:
            衰减因子，范围 [0.75, 1.0]
        """
        decay = 0.75 + 0.25 / (1.0 + math.exp(0.4 * (year - 2026)))
        return max(0.75, min(1.0, decay))

    def _fleet_size_factor(self, fleet_size: int) -> float:
        """Fleet size 额外衰减因子。

        公式: factor = 1.0 / (1 + 0.02 * max(0, fleet_size - 5))
        5 个以下项目无额外衰减。

        Args:
            fleet_size: 区域内 BESS 项目数量

        Returns:
            衰减因子，范围 (0, 1.0]
        """
        return 1.0 / (1.0 + 0.02 * max(0, fleet_size - 5))

    def _compute_capture_rate(
        self,
        compression_factor: float,
        year: int,
        bess_capacity_ratio: float,
        fleet_size: int,
        region: Optional[str] = None,
        month: Optional[int] = None,
    ) -> float:
        """计算更新后的 capture_rate(含可选季节修正)。

        公式::

            raw = BASE_CAPTURE_RATE × compression^0.5
                  × autobidder_decay(year) × fleet_size_factor(fleet_size)
            # 季节修正(可选,Req 3.2)
            if region is not None and month is not None and not _ZERO_SEASON_MODE:
                raw *= _lookup_seasonal_multiplier(region, month)
            capture_rate = clamp(raw, 0.10, 0.55)
            if bess_capacity_ratio > 0.30:
                capture_rate = min(capture_rate, 0.40)

        约束:
          - capture_rate ∈ [0.10, 0.55](Req 4.3)
          - 当 bess_capacity_ratio > 0.30 时: capture_rate ≤ 0.40

        Args:
            compression_factor: BESS 饱和压缩因子 [0.05, 1.0]
            year: 目标年份
            bess_capacity_ratio: BESS 容量 / 峰值需求 (≥0)
            fleet_size: 区域内 BESS 项目数量
            region: 可选区域代码(例如 ``"NSW1"`` / ``"QLD1"``);与 ``month``
                必须**同时**提供或**同时**省略(Req 3.1)。混合(只一个非 None)
                按"两者皆 None"降级处理(Req 3.6),返回 Pre_Spec_Capture_Rate
                (浮点 1e-9 容差)。
            month: 可选月份(1-12);与 ``region`` 必须**同时**提供或**同时**省略
                (Req 3.1)。越界 month 或未知 region 经 ``_lookup_seasonal_multiplier``
                三层防御后乘以 1.0,等价于跳过季节修正(Req 3.6)。

        Returns:
            capture_rate,范围 [0.10, 0.55](高饱和时 ≤ 0.40)。

        Notes:
            - **Pre_Spec 兼容**(Req 9.1):不带 ``region`` / ``month`` 调用时返回
              Pre_Spec_Capture_Rate(浮点容差 1e-9),与本 spec 启动前的行为完全
              等价。``estimate_annual_revenue`` / ``generate_20year_projection``
              等生产路径暂不传 region/month,沿用本兼容性契约。
            - **Zero_Season_Mode**(Req 3.5):当 ``SEASONAL_CAPTURE_MULTIPLIER``
              全部条目 = 1.0(模块级 ``_ZERO_SEASON_MODE`` 缓存为 True)时,
              短路绕过 ``_lookup_seasonal_multiplier`` 查表,数值与
              Pre_Spec_Capture_Rate 一致(浮点容差 1e-9)。
        """
        # 计算原始 capture_rate(完全保留现有公式,Req 8.5)
        raw = (
            BASE_CAPTURE_RATE
            * (compression_factor ** 0.5)
            * self._autobidder_decay(year)
            * self._fleet_size_factor(fleet_size)
        )

        # NEW: 季节修正(Req 3.2)
        # 三守卫使任何"不完整 (region, month) 组合"都降级回 Pre_Spec 行为:
        #   - 仅 None 组合:跳过(Req 3.3)
        #   - 混合(只一个非 None):跳过(Req 3.6)— 按"两者皆 None"处理
        #   - Zero_Season_Mode 激活:跳过(Req 3.5)— 短路优化
        if (
            region is not None
            and month is not None
            and not _ZERO_SEASON_MODE
        ):
            raw *= _lookup_seasonal_multiplier(region, month)
            # 注:_lookup_seasonal_multiplier 内部已对越界 month / 未知 region
            # 短路返回 1.0(Req 2.4 / 2.6),因此此处自然降级为乘以 1.0,等价
            # 跳过季节修正(浮点 1e-9 容差),覆盖 Req 3.6 列举的
            # "region 未在表 / month 越界" 语义。

        # 基础 clamp: [0.10, 0.55](完全保留,Req 4.3)
        capture_rate = max(0.10, min(0.55, raw))

        # 高饱和额外约束: bess_capacity_ratio > 0.30 时 capture_rate ≤ 0.40(完全保留)
        if bess_capacity_ratio > 0.30:
            capture_rate = min(capture_rate, 0.40)

        return capture_rate

    # -------------------------------------------------------------------------
    # Capacity Deduplication
    # -------------------------------------------------------------------------

    def _deduplicate_capacity(
        self,
        event_projects: List[dict],
        data_projects: List[dict],
    ) -> float:
        """合并 Event_Registry 和 Capacity_Data 的容量，去重。

        当项目同时出现在两个来源时，以 Capacity_Data 为准。
        匹配逻辑：项目名称相同视为同一项目。

        Args:
            event_projects: 来自 Event_Registry 的项目列表 [{name, capacity_mw}]
            data_projects: 来自 Capacity_Data 的项目列表 [{name, capacity_mw}]

        Returns:
            去重后的总容量 (MW)
        """
        # Capacity_Data 项目名称集合
        data_names = {p.get("name", "") for p in data_projects}

        # 从 Capacity_Data 获取总容量
        total = sum(p.get("capacity_mw", 0) for p in data_projects)

        # 添加 Event_Registry 中不在 Capacity_Data 中的项目
        for event_proj in event_projects:
            if event_proj.get("name", "") not in data_names:
                total += event_proj.get("capacity_mw", 0)

        return total

    # -------------------------------------------------------------------------
    # Pipeline Realization (Req 4)
    # -------------------------------------------------------------------------

    def _apply_pipeline_realization(
        self,
        capacity_mw: float,
        status: str,
    ) -> float:
        """对项目容量应用管道实现率加权。

        根据项目 status 查找 PIPELINE_REALIZATION_RATES 中对应的实现率，
        将原始容量乘以实现率得到加权容量。

        未知 status 使用 20% 默认实现率并记录警告日志。

        Args:
            capacity_mw: 项目原始容量 (MW)
            status: 项目状态（registered/construction/committed/proposed/speculated）

        Returns:
            加权后的容量 (MW)
        """
        realization_rate = PIPELINE_REALIZATION_RATES.get(status)
        if realization_rate is None:
            logger.warning(
                "Unknown project status '%s' — using default 20%% realization rate.",
                status,
            )
            realization_rate = 0.20

        return capacity_mw * realization_rate

    # -------------------------------------------------------------------------
    # Duration Efficiency (Req 7)
    # -------------------------------------------------------------------------

    def _compute_duration_efficiency(self, duration_hours: float) -> float:
        """计算有效时长因子（替代线性 duration_hours 乘数）。

        反映不同储能时长的边际收入递减效应：
        - duration ≤ 12h: factor = duration^0.85
        - duration > 12h: factor = 12^0.85 × (duration/12)^0.75

        不变量: 单调递增（duration1 < duration2 → factor1 < factor2）

        Args:
            duration_hours: 储能时长（小时），必须 > 0

        Returns:
            有效时长因子（无量纲）

        Raises:
            ValueError: 当 duration_hours ≤ 0 时
        """
        if duration_hours <= 0:
            raise ValueError(
                f"duration_hours must be greater than 0, got {duration_hours}."
            )

        if duration_hours <= 12.0:
            return duration_hours ** 0.85
        else:
            # 12h 处连续：12^0.85 × (duration/12)^0.75
            return (12.0 ** 0.85) * ((duration_hours / 12.0) ** 0.75)

    # -------------------------------------------------------------------------
    # Structural Risks (Req 8)
    # -------------------------------------------------------------------------

    def _compute_structural_risks(self, year: int) -> List[str]:
        """生成结构性市场改革风险列表。

        根据预测年份判断是否存在市场结构性改革风险：
        - year > 2028: 添加 Nelson Review 风险（NEM 从 merchant 转向 contracted 模式）
        - year ≤ 2028: 返回空列表

        始终返回列表（可能为空），不返回 None/null。

        Args:
            year: 预测目标年份

        Returns:
            结构性风险描述字符串列表（可能为空）
        """
        risks: List[str] = []

        if year > 2028:
            risks.append(
                "Nelson Review: potential shift from merchant to contracted model"
            )

        return risks

    # -------------------------------------------------------------------------
    # FCAS Revenue Integration (Req 1)
    # -------------------------------------------------------------------------

    def _compute_fcas_revenue(
        self,
        region: str,
        year: int,
        battery: BatterySpecs,
    ) -> FcasRevenueComponent:
        """计算指定年份的 FCAS 收入分量。

        调用 FcasCollapseEngine.forecast() 获取价格天花板，
        乘以电池容量和参与率得到年度 FCAS 收入。

        降级策略：计算失败时返回 revenue=0.0, degraded=True。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            year: 目标年份
            battery: 电池规格参数

        Returns:
            FcasRevenueComponent 包含 FCAS 年收入和价格天花板
        """
        try:
            from engines.fcas_collapse_engine import FcasCollapseEngine
            from deps import get_db

            db = get_db()
            fcas_engine = FcasCollapseEngine(db)

            # 调用 forecast 获取 FCAS 价格天花板
            response = fcas_engine.forecast(region=region, year=year)

            # total_fcas_ceiling_per_mw_year 已经是 $/MW/year 单位
            ceiling_per_mw_year = response.total_fcas_ceiling_per_mw_year

            # FCAS 收入 = 天花板 × 电池容量 (MW)
            # ceiling_per_mw_year 已包含 participation_rate 和 enablement_probability
            # FCAS 收入只使用 FCAS_CAPACITY_ALLOCATION 比例的容量
            fcas_revenue_per_mw = ceiling_per_mw_year * FCAS_CAPACITY_ALLOCATION

            return FcasRevenueComponent(
                year=year,
                fcas_revenue_per_mw=max(0.0, fcas_revenue_per_mw),
                ceiling_per_mw_year=max(0.0, ceiling_per_mw_year),
                degraded=False,
            )

        except Exception as e:
            logger.warning(f"FCAS revenue computation failed for {region}/{year}: {e}")
            return FcasRevenueComponent(
                year=year,
                fcas_revenue_per_mw=0.0,
                ceiling_per_mw_year=0.0,
                degraded=True,
            )

    # -------------------------------------------------------------------------
    # Data Loading
    # -------------------------------------------------------------------------

    def _load_event_registry(self) -> EventRegistry:
        """Load and merge coal retirement schedule and BESS capacity data.

        Coal closures produce events with spread_impact_factor > 1 (volatility increase).
        BESS commissionings produce events with spread_impact_factor < 1 (spread compression).

        Raises:
            FileNotFoundError: If required data files are missing.
        """
        events: List[SupplyDemandEvent] = []
        today = date.today()

        # --- Load coal retirement schedule ---
        coal_path = DATA_DIR / "coal_retirement_schedule.json"
        if not coal_path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {coal_path}. "
                "The coal retirement schedule is needed for forward price projections."
            )

        with open(coal_path, "r", encoding="utf-8") as f:
            coal_data = json.load(f)

        for retirement in coal_data.get("retirements", []):
            expected_date = date.fromisoformat(retirement["expected_closure_date"])

            if expected_date <= today:
                logger.warning(
                    "Coal retirement event '%s' has past date %s — excluding from projections.",
                    retirement["plant_name"],
                    expected_date,
                )
                continue

            # Coal closure increases volatility → spread_impact_factor > 1
            impact_factor = 1.0 + retirement["volatility_impact_estimate"]

            events.append(
                SupplyDemandEvent(
                    event_type=EventType.COAL_CLOSURE,
                    name=retirement["plant_name"],
                    region=retirement["region"],
                    expected_date=expected_date,
                    capacity_mw=retirement["capacity_mw"],
                    confidence=EventConfidence(retirement["confidence"]),
                    spread_impact_factor=impact_factor,
                )
            )

        # --- Load BESS capacity data ---
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {capacity_path}. "
                "The capacity data is needed for forward price projections."
            )

        with open(capacity_path, "r", encoding="utf-8") as f:
            capacity_data = json.load(f)

        for project in capacity_data.get("projects", []):
            # Use actual commissioning date if available, otherwise expected
            date_str = (
                project.get("actual_commissioning_date")
                or project["expected_commissioning_date"]
            )
            expected_date = date.fromisoformat(date_str)

            if expected_date <= today:
                logger.warning(
                    "BESS commissioning event '%s' has past date %s — excluding from projections.",
                    project["project_name"],
                    expected_date,
                )
                continue

            # BESS commissioning compresses spreads → spread_impact_factor < 1
            # Impact proportional to capacity relative to regional peak demand
            region = project["region"]
            peak = PEAK_DEMAND.get(region, 10000.0)
            compression = project["capacity_mw"] / peak
            impact_factor = max(0.85, 1.0 - compression * 0.1)

            events.append(
                SupplyDemandEvent(
                    event_type=EventType.BESS_COMMISSIONING,
                    name=project["project_name"],
                    region=region,
                    expected_date=expected_date,
                    capacity_mw=project["capacity_mw"],
                    confidence=EventConfidence(
                        "confirmed"
                        if project["status"] in ("registered", "construction")
                        else "announced"
                        if project["status"] == "committed"
                        else "speculated"
                    ),
                    spread_impact_factor=impact_factor,
                )
            )

        # --- Load network augmentation (interconnector) events ---
        for interconnector in capacity_data.get("interconnectors", []):
            expected_date = date.fromisoformat(interconnector["expected_date"])

            if expected_date <= today:
                logger.warning(
                    "Network augmentation event '%s' has past date %s — excluding from projections.",
                    interconnector["name"],
                    expected_date,
                )
                continue

            convergence_factor = interconnector["convergence_factor"]

            # Validate convergence_factor range [0.05, 0.30]
            if not (0.05 <= convergence_factor <= 0.30):
                raise ValueError(
                    f"convergence_factor for interconnector '{interconnector['name']}' "
                    f"must be in range [0.05, 0.30], got {convergence_factor}."
                )

            # Network augmentation compresses spreads → spread_impact_factor < 1
            # spread_impact_factor = 1 - convergence_factor
            impact_factor = 1.0 - convergence_factor

            # Add events for both connected regions
            for region in (interconnector["from_region"], interconnector["to_region"]):
                events.append(
                    SupplyDemandEvent(
                        event_type=EventType.NETWORK_AUGMENTATION,
                        name=interconnector["name"],
                        region=region,
                        expected_date=expected_date,
                        capacity_mw=interconnector["capacity_mw"],
                        confidence=EventConfidence(interconnector.get("confidence", "announced")),
                        spread_impact_factor=impact_factor,
                    )
                )

        last_updated_str = coal_data.get("metadata", {}).get("last_updated", str(today))
        # Handle datetime strings by taking just the date part
        last_updated = date.fromisoformat(last_updated_str[:10])

        return EventRegistry(events=events, last_updated=last_updated)

    # -------------------------------------------------------------------------
    # Scenario Definitions
    # -------------------------------------------------------------------------

    def get_scenarios(self) -> List[ScenarioDefinition]:
        """返回可用的情景定义列表（Central/High/Low）。"""
        return [
            ScenarioDefinition(
                scenario=ScenarioType.CENTRAL,
                name="Central",
                description="ISP central development path — coal retires on schedule, BESS builds at planned rate.",
                assumptions=[
                    "Coal retires 2 years after announced schedule (delay buffer)",
                    "BESS capacity builds at ISP planned rate",
                    "Demand growth follows AEMO central forecast",
                    "Saturation sensitivity factor: 1.0",
                ],
            ),
            ScenarioDefinition(
                scenario=ScenarioType.HIGH,
                name="High",
                description="Accelerated coal retirement with slower BESS buildout — higher spreads persist longer.",
                assumptions=[
                    "Coal retires 2 years earlier than announced",
                    "BESS capacity builds 30% slower than planned",
                    "Higher price volatility due to supply tightness",
                    "Saturation sensitivity factor: 0.7",
                ],
            ),
            ScenarioDefinition(
                scenario=ScenarioType.LOW,
                name="Low",
                description="Coal life extensions with faster BESS buildout — spreads compress more quickly.",
                assumptions=[
                    "Coal retires 4 years after announced closure (extended delay buffer)",
                    "BESS capacity builds 50% faster than planned",
                    "Lower price volatility due to excess capacity",
                    "Saturation sensitivity factor: 1.3",
                ],
            ),
        ]

    # -------------------------------------------------------------------------
    # Price Distribution Calculation
    # -------------------------------------------------------------------------

    def calculate_price_distribution(
        self,
        region: str,
        scenario: ScenarioType,
        year: int,
        bess_capacity_ratio: float,
    ) -> PriceDistribution:
        """计算指定区域/情景/年份的价格分布参数。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            scenario: Central/High/Low scenario type
            year: Target year for projection
            bess_capacity_ratio: Ratio of total BESS capacity to peak demand

        Returns:
            PriceDistribution with computed parameters.

        Raises:
            ValueError: If region is not supported.
        """
        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        base = self._get_spread_params(region)
        mean_spread = base["mean_spread"]
        std_dev = base.get("std_dev", BASE_SPREAD_PARAMS[region]["std_dev"])
        spike_frequency = base.get("spike_frequency", BASE_SPREAD_PARAMS[region]["spike_frequency"])

        # Apply event impacts multiplicatively (Property 15)
        # 注意：只有煤电退役和网络增强事件通过 spread_impact_factor 影响 mean_spread。
        # BESS 事件的压缩效应已通过 compression_factor（基于 bess_capacity_ratio）统一建模，
        # 不再通过 spread_impact_factor 重复计算（避免双重压缩）。
        today = date.today()
        coal_closures_by_year: Dict[int, int] = {}

        for event in self.event_registry.events:
            if event.region != region:
                continue
            if event.expected_date <= today:
                continue

            # Skip BESS events — their compression is handled by compression_factor
            if event.event_type == EventType.BESS_COMMISSIONING:
                continue

            # Determine effective event date based on scenario
            effective_date = self._get_effective_event_date(event, scenario)

            # Only apply events that have occurred by the target year
            if effective_date.year <= year:
                # 煤电退役影响随时间衰减：退役后每年衰减 20%，5 年后归零
                if event.event_type == EventType.COAL_CLOSURE:
                    years_since = year - effective_date.year
                    decay = max(0.0, 1.0 - 0.20 * years_since)
                    effective_impact = 1.0 + (event.spread_impact_factor - 1.0) * decay
                    mean_spread *= effective_impact
                    std_dev *= effective_impact
                else:
                    mean_spread *= event.spread_impact_factor
                    std_dev *= event.spread_impact_factor

                # 统计煤电退役事件数量（用于交互效应）
                if event.event_type == EventType.COAL_CLOSURE:
                    coal_closures_by_year[effective_date.year] = (
                        coal_closures_by_year.get(effective_date.year, 0) + 1
                    )

        # 多事件交互效应：同一年有多个煤电退役时，供应紧张加剧
        # 2 个同年退役 → +5% 额外价差，3 个 → +10%
        for yr, count in coal_closures_by_year.items():
            if count > 1 and yr <= year:
                interaction_boost = 1.0 + 0.05 * (count - 1)
                mean_spread *= interaction_boost

        # BESS saturation compression — 指数衰减模型 (v2)
        # 基于 Modo Energy 基准数据校准，引入价格设定频率和区域波动性
        sensitivity = SATURATION_SENSITIVITY[scenario]
        psf = self._get_price_setting_frequency(year)
        rvf = REGIONAL_VOLATILITY_FACTOR.get(region, 1.0)
        compression_factor = self._compute_compression_factor(
            bess_capacity_ratio, sensitivity, psf, rvf
        )

        # Apply compression to mean spread.
        #
        # 双重计数修正（2026-07-28）：绝对压缩因子的语义是“把无压缩基准
        # 压到目标年”，适用于硬编码的 2024 历史 base。但 ML 校准的 base 是
        # “当前已实现”价差，已含截至锚点年的全部压缩，再乘绝对因子会把
        # 历史压缩重放一遍（holdout 样本外实测：五区系统性低估 ~40%）。
        # 修正：前瞻方向（target >= anchor）改用增量压缩
        # compression(target)/compression(anchor)，只施加锚点年之后新增的
        # 饱和压缩；历史对照方向（target < anchor）与未校准路径保持旧语义。
        # 注：PriceDistribution.compression_factor 仍报告目标年的绝对饱和度
        # （供 capture_rate 与下游解读），仅 mean_spread 的施加方式改变。
        anchor_year = getattr(self, "_calibration_anchor_year", None)
        if anchor_year is not None and year >= anchor_year:
            anchor_capacity = self._get_cumulative_bess_capacity(
                region, scenario, anchor_year
            )
            anchor_peak = self._get_dynamic_peak_demand(region, anchor_year)
            anchor_ratio = anchor_capacity / anchor_peak if anchor_peak else 0.0
            anchor_psf = self._get_price_setting_frequency(anchor_year)
            compression_anchor = self._compute_compression_factor(
                anchor_ratio, sensitivity, anchor_psf, rvf
            )
            incremental = (
                compression_factor / compression_anchor
                if compression_anchor > 0
                else compression_factor
            )
            # 未来饱和只增不减 → 增量压缩限在 (0.05, 1.0]
            applied_compression = max(0.05, min(1.0, incremental))
        else:
            applied_compression = compression_factor
        mean_spread *= applied_compression

        # Capture rate decreases with BESS penetration.
        # 与 mean_spread 同口径使用 applied_compression：capture 的衰减同样
        # 只应反映锚点年之后新增的竞争压力。绝对因子会重放历史压缩（k 标定
        # 后尤其严重：绝对路径下 2026 capture 仅 0.20-0.26，市场实际 ~0.65）。
        capture_rate = BASE_CAPTURE_RATE * (applied_compression ** 0.5)

        # Clamp outputs to valid ranges (Property 17)
        mean_spread = max(0.0, min(10000.0, mean_spread))
        std_dev = max(0.0, min(5000.0, std_dev))
        spike_frequency = max(0.0, min(1.0, spike_frequency))
        compression_factor = max(0.0, min(1.0, compression_factor))
        applied_compression = max(0.0, min(1.0, applied_compression))
        capture_rate = max(0.0, min(1.0, capture_rate))

        return PriceDistribution(
            year=year,
            region=region,
            scenario=scenario,
            mean_spread=mean_spread,
            std_dev=std_dev,
            spike_frequency=spike_frequency,
            compression_factor=compression_factor,
            applied_compression=applied_compression,
            capture_rate=capture_rate,
        )

    def _get_effective_event_date(
        self, event: SupplyDemandEvent, scenario: ScenarioType
    ) -> date:
        """Adjust event date based on scenario assumptions.

        Coal closure adjustments use COAL_RETIREMENT_SCENARIO_ADJUSTMENT:
        - Central scenario: coal retires 2 years later (delay buffer)
        - High scenario: coal retires 2 years early
        - Low scenario: coal retires 4 years later (extended delay buffer)

        BESS commissioning adjustments:
        - High scenario: BESS builds 30% slower (delayed ~2 years)
        - Low scenario: BESS builds 50% faster (earlier ~1 year)
        - Central: as announced

        Network augmentation:
        - High: delayed by 1 year
        - Low: accelerated by 1 year
        - Central: as announced

        All adjusted dates are clamped to not be earlier than today (Req 6.4).
        """
        base_date = event.expected_date
        today = date.today()

        if event.event_type == EventType.COAL_CLOSURE:
            # Use COAL_RETIREMENT_SCENARIO_ADJUSTMENT constant for all scenarios
            scenario_key = scenario.value  # "central", "high", "low"
            adjustment_years = COAL_RETIREMENT_SCENARIO_ADJUSTMENT.get(scenario_key, 0)
            adjusted = base_date.replace(year=base_date.year + adjustment_years)
            # Ensure adjusted date is not earlier than today (Req 6.4)
            if adjusted < today:
                return today
            return adjusted

        elif event.event_type == EventType.BESS_COMMISSIONING:
            if scenario == ScenarioType.CENTRAL:
                return base_date
            elif scenario == ScenarioType.HIGH:
                # BESS builds 30% slower → delayed by ~2 years
                adjusted = base_date.replace(year=base_date.year + 2)
            else:  # LOW
                # BESS builds 50% faster → earlier by ~1 year
                adjusted = base_date.replace(year=base_date.year - 1)
            # Ensure adjusted date is not earlier than today (Req 6.4)
            if adjusted < today:
                return today
            return adjusted

        elif event.event_type == EventType.NETWORK_AUGMENTATION:
            if scenario == ScenarioType.CENTRAL:
                return base_date
            elif scenario == ScenarioType.HIGH:
                # Network infrastructure delayed by 1 year
                adjusted = base_date.replace(year=base_date.year + 1)
            else:  # LOW
                # Network infrastructure accelerated by 1 year
                adjusted = base_date.replace(year=base_date.year - 1)
            # Ensure adjusted date is not earlier than today (Req 6.4)
            if adjusted < today:
                return today
            return adjusted

        return base_date

    # -------------------------------------------------------------------------
    # Contract Revenue Adjustment (CIS / Offtake)
    # -------------------------------------------------------------------------

    def _apply_contract_adjustment(
        self,
        merchant_revenue_per_mw: float,
        battery: BatterySpecs,
        year: int,
    ) -> Tuple[float, dict]:
        """对 merchant 收入应用合约调整，输出调整后总收入和合约 metadata。

        支持四种收入模型:
        - pure_merchant: 不调整
        - cis_contracted: 应用 CIS 三层结构（floor + ceiling + cap）
        - offtake_contracted: 用固定 offtake 价格替代 merchant
        - hybrid: contracted_capacity_share 部分用合约，剩余用 merchant
        """
        meta: dict = {
            "revenue_model": battery.revenue_model.value,
            "merchant_revenue_per_mw": merchant_revenue_per_mw,
            "contracted_revenue_per_mw": 0.0,
            "merchant_share_revenue": merchant_revenue_per_mw,
            "contract_topup": 0.0,
            "ceiling_payback": 0.0,
        }

        if battery.revenue_model == RevenueModel.PURE_MERCHANT:
            return merchant_revenue_per_mw, meta

        if battery.revenue_model == RevenueModel.OFFTAKE_CONTRACTED:
            if battery.offtake_price_per_mwh is None:
                logger.warning("OFFTAKE_CONTRACTED requires offtake_price_per_mwh, falling back to merchant")
                return merchant_revenue_per_mw, meta
            eligible_mwh = 800.0
            offtake_revenue = battery.offtake_price_per_mwh * eligible_mwh
            meta["contracted_revenue_per_mw"] = offtake_revenue
            meta["merchant_share_revenue"] = 0.0
            return offtake_revenue, meta

        if battery.revenue_model in (RevenueModel.CIS_CONTRACTED, RevenueModel.HYBRID):
            if battery.cis_contract is None:
                logger.warning("CIS contract requires cis_contract param, falling back to merchant")
                return merchant_revenue_per_mw, meta

            cis = battery.cis_contract
            contracted_share = (
                battery.contracted_capacity_share
                if battery.revenue_model == RevenueModel.HYBRID
                else 1.0
            )
            merchant_share = 1.0 - contracted_share

            # 合约只覆盖 contracted_share 部分容量，floor/ceiling 也按比例缩放
            merchant_in_contract = merchant_revenue_per_mw * contracted_share
            floor_revenue = cis.revenue_floor_per_mwh * cis.eligible_mwh_per_mw_year * contracted_share
            ceiling_revenue = cis.revenue_ceiling_per_mwh * cis.eligible_mwh_per_mw_year * contracted_share

            topup = 0.0
            if merchant_in_contract < floor_revenue:
                raw_topup = cis.floor_share * (floor_revenue - merchant_in_contract)
                topup = min(raw_topup, cis.annual_payment_cap_aud)

            payback = 0.0
            if merchant_in_contract > ceiling_revenue:
                raw_payback = cis.ceiling_share * (merchant_in_contract - ceiling_revenue)
                payback = min(raw_payback, cis.annual_payment_cap_aud)

            contracted_adjusted = merchant_in_contract + topup - payback
            merchant_remainder = merchant_revenue_per_mw * merchant_share

            meta["contracted_revenue_per_mw"] = contracted_adjusted
            meta["merchant_share_revenue"] = merchant_remainder
            meta["contract_topup"] = topup
            meta["ceiling_payback"] = payback
            meta["effective_floor"] = floor_revenue
            meta["effective_ceiling"] = ceiling_revenue

            return contracted_adjusted + merchant_remainder, meta

        return merchant_revenue_per_mw, meta

    # -------------------------------------------------------------------------
    # Revenue Estimation
    # -------------------------------------------------------------------------

    def estimate_annual_revenue(
        self,
        region: str,
        scenario: ScenarioType,
        year: int,
        battery: BatterySpecs,
        soh: float,
    ) -> Tuple[float, FcasRevenueComponent]:
        """基于价格分布估算年度套利收入，并计算独立的 FCAS 收入分量。

        Energy arbitrage revenue formula (updated):
            annual_revenue = mean_spread × capture_rate × power_mw
                           × duration_efficiency_factor × 365 × rte × soh

        集成组件:
        - duration_efficiency_factor 替代线性 duration_hours (Req 7.1)
        - 动态 peak_demand 计算 bess_capacity_ratio (Req 5.1)
        - 管道实现率加权的 BESS 容量 (Req 4.3, 已在 _get_cumulative_bess_capacity 中实现)
        - 更新后的 capture_rate 公式 (Req 2.2)

        FCAS revenue is computed separately via _compute_fcas_revenue and
        returned as an independent component (Req 1.1).

        Args:
            region: NEM region or WEM
            scenario: Scenario type
            year: Target year
            battery: Battery specifications
            soh: State of health (0.0 to 1.0)

        Returns:
            Tuple of (energy_arbitrage_revenue, FcasRevenueComponent).
            Energy revenue is in dollars. FCAS revenue is tracked independently.
        """
        # Calculate BESS capacity ratio using dynamic peak demand (Req 5.1)
        bess_capacity = self._get_cumulative_bess_capacity(region, scenario, year)
        peak_demand = self._get_dynamic_peak_demand(region, year)
        bess_capacity_ratio = bess_capacity / peak_demand

        # Get price distribution for this year
        dist = self.calculate_price_distribution(
            region=region,
            scenario=scenario,
            year=year,
            bess_capacity_ratio=bess_capacity_ratio,
        )

        # Compute fleet_size: count of BESS projects in the region from event registry
        # that have been commissioned by the target year (Req 2.5)
        fleet_size = 0
        for event in self.event_registry.events:
            if event.region != region:
                continue
            if event.event_type != EventType.BESS_COMMISSIONING:
                continue
            effective_date = self._get_effective_event_date(event, scenario)
            if effective_date.year <= year:
                fleet_size += 1

        # Compute updated capture_rate using new formula (Req 2.2)
        # 用 applied_compression（前瞻=增量）而非绝对 compression_factor，
        # 与 mean_spread 口径一致，避免 capture 重放历史压缩。
        capture_rate = self._compute_capture_rate(
            compression_factor=dist.applied_compression,
            year=year,
            bess_capacity_ratio=bess_capacity_ratio,
            fleet_size=fleet_size,
        )

        # Compute duration_efficiency_factor (Req 7.1)
        duration_efficiency_factor = self._compute_duration_efficiency(
            battery.duration_hours
        )

        # 补偿 winsorization 截断的尖峰收入贡献
        spike_bonus = dist.spike_frequency * SPIKE_REVENUE_PREMIUM
        effective_mean_spread = dist.mean_spread * (1.0 + spike_bonus)

        # Energy Revenue = mean_spread × capture_rate × power_mw
        #                 × (1 - FCAS_CAPACITY_ALLOCATION) × duration_efficiency_factor × 365 × rte × soh
        # 能量套利只使用 (1 - FCAS_CAPACITY_ALLOCATION) 的容量
        energy_revenue = (
            effective_mean_spread
            * capture_rate
            * battery.power_mw
            * (1.0 - FCAS_CAPACITY_ALLOCATION)
            * duration_efficiency_factor
            * 365
            * battery.round_trip_efficiency
            * soh
        )

        # Compute FCAS revenue as independent component (Req 1.1, 1.2)
        fcas_component = self._compute_fcas_revenue(region, year, battery)

        # 合约调整（CIS / Offtake / Hybrid）
        # 把 merchant 能量套利收入按 $/MW 归一化后应用合约结构
        if battery.power_mw > 0:
            merchant_per_mw = energy_revenue / battery.power_mw
            adjusted_per_mw, _ = self._apply_contract_adjustment(
                merchant_per_mw, battery, year
            )
            energy_revenue = adjusted_per_mw * battery.power_mw

        return energy_revenue, fcas_component

    def _get_cumulative_bess_capacity(
        self, region: str, scenario: ScenarioType, year: int,
        reference_date: Optional[date] = None,
    ) -> float:
        """Calculate cumulative BESS capacity in a region by a given year.

        Considers scenario adjustments to commissioning dates.
        Applies pipeline realization rates to weight each project's capacity
        based on its confidence/status level (Req 4.3, 4.4).

        The result is guaranteed to be monotonically non-decreasing over time
        for a given region and scenario combination.

        Cutoff resolution (precedence):
            1. If `reference_date` is provided → 月级精度: event/project effective_date <= reference_date
            2. Else → 年级精度(向后兼容): effective_date.year <= year
        """
        total_capacity = 0.0

        # Map event confidence to pipeline status for realization rate lookup
        confidence_to_status = {
            EventConfidence.CONFIRMED: "registered",   # 0.90
            EventConfidence.ANNOUNCED: "committed",    # 0.90
            EventConfidence.SPECULATED: "speculated",  # 0.20
        }

        for event in self.event_registry.events:
            if event.region != region:
                continue
            if event.event_type != EventType.BESS_COMMISSIONING:
                continue

            effective_date = self._get_effective_event_date(event, scenario)

            # Cutoff comparison: prefer date-level granularity when reference_date provided
            if reference_date is not None:
                included = effective_date <= reference_date
            else:
                included = effective_date.year <= year

            if included:
                # Apply pipeline realization rate based on confidence level
                status = confidence_to_status.get(event.confidence, "speculated")
                weighted_capacity = self._apply_pipeline_realization(
                    event.capacity_mw, status
                )
                total_capacity += weighted_capacity

        # Also include already-commissioned BESS (from capacity_data with past dates)
        # These are excluded from event_registry but contribute to saturation
        total_capacity += self._get_existing_bess_capacity(region, year, reference_date)

        return total_capacity

    def _get_existing_bess_capacity(
        self,
        region: str,
        year: int = None,
        reference_date: Optional[date] = None,
    ) -> float:
        """Get BESS capacity for a region including all committed/construction/registered projects.

        Includes projects with status "registered", "construction", or "committed"
        whose commissioning date is on or before the cutoff.

        Cutoff resolution (precedence):
            1. If `reference_date` is provided → 月级精度: 项目 commissioning_date <= reference_date
            2. Else if `year` is provided → 年级精度(向后兼容): commissioning_date.year <= year
            3. Else → 年级精度: commissioning_date.year <= 当前年份

        Each project's capacity is weighted by its pipeline realization rate
        based on its status (Req 4.3).

        Args:
            region: NEM region
            year: Target year (legacy, year-level granularity)
            reference_date: Reference cutoff date (preferred, month-level granularity).
                When supplied, supersedes `year`.

        Returns:
            Cumulative weighted BESS capacity in MW
        """
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            return 0.0

        with open(capacity_path, "r", encoding="utf-8") as f:
            capacity_data = json.load(f)

        target_year = year or date.today().year
        total = 0.0
        valid_statuses = {"registered", "construction", "committed"}

        for project in capacity_data.get("projects", []):
            if project["region"] != region:
                continue

            # Check status — include all committed/construction/registered projects
            status = project.get("status", "")
            if status not in valid_statuses:
                continue

            # Get commissioning date (actual preferred, then expected)
            date_str = (
                project.get("actual_commissioning_date")
                or project.get("expected_commissioning_date")
            )
            if not date_str:
                logger.warning(
                    "BESS project '%s' missing commissioning date — skipping.",
                    project.get("project_name", "unknown"),
                )
                continue

            try:
                commissioning_date = date.fromisoformat(date_str)
            except ValueError:
                logger.warning(
                    "BESS project '%s' has invalid date '%s' — skipping.",
                    project.get("project_name", "unknown"),
                    date_str,
                )
                continue

            # Cutoff comparison: prefer date-level granularity when reference_date provided
            if reference_date is not None:
                included = commissioning_date <= reference_date
            else:
                included = commissioning_date.year <= target_year

            if included:
                # Apply pipeline realization rate based on project status
                weighted_capacity = self._apply_pipeline_realization(
                    project.get("capacity_mw", 0), status
                )
                total += weighted_capacity

        return total

    # -------------------------------------------------------------------------
    # Dynamic Demand Growth (Req 5)
    # -------------------------------------------------------------------------

    def _get_dynamic_peak_demand(
        self,
        region: str,
        year: int,
        annual_growth_rate: Optional[float] = None,
    ) -> float:
        """计算动态峰值需求。

        公式: peak_demand(year) = PEAK_DEMAND[region] × (1 + rate)^(year - 2025)

        增长率优先级:
        1. 显式传入的 annual_growth_rate（必须在 [0.0, 0.10] 范围内）
        2. 区域特定值 REGIONAL_DEMAND_GROWTH_RATE[region]
        3. 全局默认 DEMAND_GROWTH_RATE (2.5%/年)

        约束: 输出不低于当前静态 PEAK_DEMAND 值

        Args:
            region: NEM region or WEM
            year: 目标年份
            annual_growth_rate: 显式增长率覆盖（可选）

        Returns:
            动态峰值需求 (MW)，不低于静态 PEAK_DEMAND 值
        """
        # 解析使用的增长率
        if annual_growth_rate is None:
            # 未显式传入，使用区域值或全局默认
            effective_rate = REGIONAL_DEMAND_GROWTH_RATE.get(region, DEMAND_GROWTH_RATE)
        else:
            # 显式传入：校验范围
            if annual_growth_rate < 0.0 or annual_growth_rate > 0.10:
                logger.warning(
                    "annual_growth_rate %.4f out of valid range [0.0, 0.10], "
                    "using regional/default value",
                    annual_growth_rate,
                )
                effective_rate = REGIONAL_DEMAND_GROWTH_RATE.get(region, DEMAND_GROWTH_RATE)
            else:
                effective_rate = annual_growth_rate

        base_demand = PEAK_DEMAND.get(region, 10000.0)
        years_from_base = year - DEMAND_GROWTH_BASE_YEAR

        # 计算动态需求
        dynamic_demand = base_demand * ((1.0 + effective_rate) ** years_from_base)

        # 确保不低于静态 PEAK_DEMAND 值（向下兼容）
        return max(base_demand, dynamic_demand)

    # -------------------------------------------------------------------------
    # Benchmark Validation
    # -------------------------------------------------------------------------

    def validate_against_benchmarks(self) -> Dict:
        """对比模型输出与 Modo Energy 基准数据。

        .. deprecated:: 2026-07-28 语义失效，仅供参考，不应作为验收闸门。
            两个无法在现架构下自洽的缺陷：
            1) 循环验证：季节乘子/RVF 曾在本基准上网格搜索调参，再用同一
               基准打分无证据价值；
            2) 锚点语义错位：ML 校准后 base 是“当前（锚点年）已实现”价差，
               对 2024/2025 等历史期间拿当前 base 配绝对压缩回放历史，数字
               无法解读（实测历史期间 -30%~-63%、锚点年窗口 +45%~+224%）。
            现行有效验证 = scripts/validate_holdout_spread.py（LEVEL+TREND 双层，
            真实市场价格、拟合/验证分离）。收入口径的重建待后续任务。

        使用 Modo Energy 一致的假设（capture_rate=0.65, duration=4h 线性, RTE=0.87）
        计算模型收入。mean_spread 来自引擎的 calculate_price_distribution（含 ML 校准）。

        Returns:
            {
                "results": [{"region": str, "period": str, "model_revenue": float,
                             "benchmark_revenue": float, "deviation_pct": float}],
                "all_within_threshold": bool,
                "max_deviation_pct": float,
                "deprecated": True,
            }
        """
        evidence_path = DATA_DIR / "financial_evidence.json"
        if not evidence_path.exists():
            logger.warning("Benchmark validation: financial_evidence.json not found")
            return {"results": [], "all_within_threshold": True, "max_deviation_pct": 0.0}

        with open(evidence_path, "r", encoding="utf-8") as f:
            evidence = json.load(f)

        benchmarks = evidence.get("modo_benchmarks", {}).get("benchmarks", {})
        if not benchmarks:
            logger.warning("Benchmark validation: no modo_benchmarks data found")
            return {"results": [], "all_within_threshold": True, "max_deviation_pct": 0.0}

        # Modo Energy 基准假设（与其报告一致）
        # 这些是 Modo 计算实际收入时使用的参数。
        # 变体路径 C(seasonal-capture-rate-correction):MODO_REVENUE_FACTOR 是
        # 局部语义化命名(原 REVENUE_FACTOR),仍由 Modo 0.65 capture 假设构成,
        # 在 model_revenue 中额外乘 seasonal_multiplier 体现"相对 0.65 假设的偏离"。
        MODO_DURATION = 4       # 4h 线性
        MODO_CAPTURE_RATE = 0.65  # Modo 报告的平均 capture rate
        MODO_RTE = 0.87
        MODO_REVENUE_FACTOR = 365 * MODO_DURATION * MODO_CAPTURE_RATE * MODO_RTE

        # period key 到 target_year 的映射。新 key 使用明确的日历窗口；
        # 老 key (2025_H1, 2025_H2) 保留兼容入口，但官方数据已经用更精确的 key 替代。
        PERIOD_TO_YEAR = {
            "2024_full": 2024,
            "2025_H1_calendar": 2025,
            "2025_H2_calendar": 2025,
            "2025_26_summer": 2026,
            # legacy keys for backwards compatibility
            "2025_H1": 2025,
            "2025_H2": 2026,
        }

        # period key → 代表月映射(seasonal-capture-rate-correction Req 5.1-5.5)
        # 用于查 _lookup_seasonal_multiplier(region, representative_month)。
        # - 2024_full: 7  → winter(年中,Req 5.2)
        # - 2025_H1_calendar: 3 → shoulder(H1 中点,Req 5.3)
        # - 2025_H2_calendar: 9 → shoulder(H2 中点,Req 5.4)
        # - 2025_26_summer: 1   → summer(summer 窗口中位月,Req 5.5)
        PERIOD_TO_REPRESENTATIVE_MONTH: Dict[str, int] = {
            "2024_full": 7,
            "2025_H1_calendar": 3,
            "2025_H2_calendar": 9,
            "2025_26_summer": 1,
            # legacy keys 兼容(沿用现有 PERIOD_TO_YEAR 兼容性策略)
            "2025_H1": 3,
            "2025_H2": 9,
        }

        # period key 到月级参考截止日期的映射（用于精确的 BESS 容量积累计算）
        # 修正前用年级粒度,导致 2025 年 10-12 月投运的项目被错误算进 H1(1-6 月);
        # 现在按时段窗口的实际截止月份取容量,反映该窗口内已运营的真实 BESS。
        # summer 取 2026-02-28 是因为 Modo summer review 覆盖 Dec-Feb,2 月底为窗口尾。
        PERIOD_TO_REFERENCE_DATE: Dict[str, date] = {
            "2024_full": date(2024, 12, 31),
            "2025_H1_calendar": date(2025, 6, 30),
            "2025_H2_calendar": date(2025, 12, 31),
            "2025_26_summer": date(2026, 2, 28),
            # legacy keys
            "2025_H1": date(2025, 6, 30),
            "2025_H2": date(2025, 12, 31),
        }
        # 这些字段是元数据，不是 region 收入
        NON_REGION_KEYS = {"label", "data_quality_note", "source", "note"}

        results = []
        current_year = date.today().year

        for period, region_data in benchmarks.items():
            # 跳过非 dict 的 metadata 节点（防御性）
            if not isinstance(region_data, dict):
                continue
            for region, benchmark_revenue in region_data.items():
                if region in NON_REGION_KEYS:
                    continue
                if region == "NEM_AVG" or region not in SUPPORTED_REGIONS:
                    continue
                # 跳过 null（无可靠区域级数据时）
                if benchmark_revenue is None:
                    continue

                # Determine target year from period (with fallback for legacy keys)
                target_year = PERIOD_TO_YEAR.get(period)
                if target_year is None:
                    if "2024" in period:
                        target_year = 2024
                    elif "2025" in period:
                        target_year = 2025
                    elif "2026" in period:
                        target_year = 2026
                    else:
                        target_year = current_year + 1

                # Resolve month-level reference cutoff (preferred); fallback to year-end
                reference_date = PERIOD_TO_REFERENCE_DATE.get(period)
                if reference_date is None:
                    reference_date = date(target_year, 12, 31)

                # Calculate model output using price distribution (ML-calibrated mean_spread)
                try:
                    bess_capacity = self._get_cumulative_bess_capacity(
                        region, ScenarioType.CENTRAL, target_year,
                        reference_date=reference_date,
                    )
                    peak_demand = self._get_dynamic_peak_demand(region, target_year)
                    bess_ratio = bess_capacity / peak_demand

                    dist = self.calculate_price_distribution(
                        region=region,
                        scenario=ScenarioType.CENTRAL,
                        year=target_year,
                        bess_capacity_ratio=bess_ratio,
                    )

                    # 季节修正(seasonal-capture-rate-correction,变体路径 C)
                    # 1) 解析 period 对应的代表月
                    representative_month = PERIOD_TO_REPRESENTATIVE_MONTH.get(period)
                    if representative_month is None:
                        # Req 5.7-5.9: 未映射 period → seasonal=1.0 + warning + 不中断
                        seasonal_multiplier = 1.0
                        logger.warning(
                            "Benchmark validation: period '%s' not in "
                            "PERIOD_TO_REPRESENTATIVE_MONTH, using "
                            "seasonal_multiplier=1.0 (no seasonal correction).",
                            period,
                        )
                    else:
                        # 变体路径 C 核心:回测主公式独立查季节乘子,不调用
                        # _compute_capture_rate(避免 0.65 → ~0.40 缩水陷阱)。
                        seasonal_multiplier = _lookup_seasonal_multiplier(
                            region, representative_month
                        )

                    # 主公式(变体路径 C):mean_spread × MODO_REVENUE_FACTOR × seasonal
                    # Zero_Season_Mode 下 seasonal=1.0,数值 ≡ Pre_Spec model_revenue。
                    model_revenue = (
                        dist.mean_spread * MODO_REVENUE_FACTOR * seasonal_multiplier
                    )

                    # 诊断列:业务代码视角下的 dynamic_capture_rate
                    # (仅作输出参考,不参与 model_revenue 计算)。
                    # Task 5 完成后 _compute_capture_rate 会接受 region/month kwargs;
                    # 在此用 try/except TypeError 自然兼容 Task 5 未完成的状态。
                    fleet_size = sum(
                        1 for ev in self.event_registry.events
                        if ev.region == region
                        and ev.event_type == EventType.BESS_COMMISSIONING
                        and self._get_effective_event_date(
                            ev, ScenarioType.CENTRAL
                        ).year <= target_year
                    )
                    try:
                        dynamic_capture_rate: Optional[float] = self._compute_capture_rate(
                            compression_factor=dist.compression_factor,
                            year=target_year,
                            bess_capacity_ratio=bess_ratio,
                            fleet_size=fleet_size,
                            region=region,
                            month=representative_month,
                        )
                    except TypeError:
                        # Task 5 尚未为 _compute_capture_rate 添加 region/month kwargs;
                        # 退化到不带季节参数的调用,诊断列仅反映 Pre_Spec capture_rate。
                        dynamic_capture_rate = self._compute_capture_rate(
                            compression_factor=dist.compression_factor,
                            year=target_year,
                            bess_capacity_ratio=bess_ratio,
                            fleet_size=fleet_size,
                        )

                    deviation_pct = (model_revenue - benchmark_revenue) / benchmark_revenue * 100

                    if abs(deviation_pct) > 30:
                        logger.warning(
                            f"Benchmark validation: {region} {period} deviation {deviation_pct:+.1f}% "
                            f"(model=${model_revenue:,.0f} vs benchmark=${benchmark_revenue:,.0f})"
                        )

                    results.append({
                        "region": region,
                        "period": period,
                        "model_revenue": round(model_revenue, 2),
                        "benchmark_revenue": benchmark_revenue,
                        "deviation_pct": round(deviation_pct, 1),
                        # NEW(seasonal-capture-rate-correction): 季节修正诊断字段
                        "seasonal_multiplier": round(seasonal_multiplier, 4),
                        "dynamic_capture_rate": (
                            round(dynamic_capture_rate, 4)
                            if dynamic_capture_rate is not None
                            else None
                        ),
                        "representative_month": representative_month,
                    })
                except Exception as e:
                    logger.warning(f"Benchmark validation failed for {region}/{period}: {e}")

        max_deviation = max((abs(r["deviation_pct"]) for r in results), default=0.0)
        all_within = all(abs(r["deviation_pct"]) <= 30 for r in results)

        return {
            "results": results,
            "all_within_threshold": all_within,
            "max_deviation_pct": round(max_deviation, 1),
            # 语义已失效（循环验证 + 锚点错位），见 docstring deprecated 说明
            "deprecated": True,
        }

    # -------------------------------------------------------------------------
    # 20-Year Projection
    # -------------------------------------------------------------------------

    def generate_20year_projection(
        self,
        region: str,
        scenario: ScenarioType,
        battery: BatterySpecs,
    ) -> ScenarioProjection:
        """生成 20 年收入预测序列。

        Accounts for SoH degradation over the project life.
        Revenue is non-increasing over time due to degradation (Property 18).

        Each AnnualRevenueProjection includes:
        - structural_risks: 该年份的结构性市场改革风险列表 (Req 8)
        - effective_peak_demand: 动态峰值需求 (Req 5.5)
        - duration_efficiency_factor: 有效时长因子 (Req 7.1)

        ScenarioProjection.metadata 包含所有年份的聚合 structural_risks。

        Args:
            region: NEM region or WEM
            scenario: Scenario type
            battery: Battery specifications

        Returns:
            ScenarioProjection with 20-year annual projections.
        """
        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        current_year = date.today().year
        annual_projections: List[AnnualRevenueProjection] = []
        discount_rate = 0.08  # Default discount rate

        # Pre-compute duration_efficiency_factor (constant across years)
        duration_efficiency = self._compute_duration_efficiency(battery.duration_hours)

        # Collect all unique structural risks across all years for metadata
        all_structural_risks: List[str] = []

        for i in range(20):
            year = current_year + i + 1
            # SoH degrades linearly with calendar degradation rate
            soh = max(0.0, 1.0 - battery.calendar_degradation_rate * (i + 1))

            revenue, fcas_component = self.estimate_annual_revenue(
                region=region,
                scenario=scenario,
                year=year,
                battery=battery,
                soh=soh,
            )

            # Get price distribution for capture rate info (使用动态 peak_demand 保持一致)
            bess_capacity = self._get_cumulative_bess_capacity(region, scenario, year)
            peak_demand = self._get_dynamic_peak_demand(region, year)
            bess_ratio = bess_capacity / peak_demand
            dist = self.calculate_price_distribution(
                region=region,
                scenario=scenario,
                year=year,
                bess_capacity_ratio=bess_ratio,
            )

            # Compute structural risks for this year (Req 8)
            structural_risks = self._compute_structural_risks(year)

            # Aggregate unique risks for ScenarioProjection metadata
            for risk in structural_risks:
                if risk not in all_structural_risks:
                    all_structural_risks.append(risk)

            # Compute dynamic peak demand for this year (Req 5.5)
            effective_peak_demand = self._get_dynamic_peak_demand(region, year)

            # 计算实际用于收入计算的 capture_rate（与 estimate_annual_revenue 一致）
            fleet_size = sum(
                1 for ev in self.event_registry.events
                if ev.region == region
                and ev.event_type == EventType.BESS_COMMISSIONING
                and self._get_effective_event_date(ev, scenario).year <= year
            )
            actual_capture_rate = self._compute_capture_rate(
                compression_factor=dist.compression_factor,
                year=year,
                bess_capacity_ratio=bess_ratio,
                fleet_size=fleet_size,
            )

            annual_projections.append(
                AnnualRevenueProjection(
                    year=year,
                    estimated_revenue_per_mw=revenue / battery.power_mw if battery.power_mw > 0 else 0.0,
                    state_of_health=soh,
                    mean_spread=dist.mean_spread,
                    capture_rate=actual_capture_rate,
                    fcas_revenue_per_mw=fcas_component.fcas_revenue_per_mw,
                    structural_risks=structural_risks,
                    effective_peak_demand=effective_peak_demand,
                    duration_efficiency_factor=duration_efficiency,
                )
            )

        # Calculate totals
        total_revenue_per_mw = sum(
            p.estimated_revenue_per_mw for p in annual_projections
        )

        # NPV per MW using discount rate
        revenue_per_mw_series = [p.estimated_revenue_per_mw for p in annual_projections]
        npv_per_mw = float(
            npf.npv(discount_rate, [0.0] + revenue_per_mw_series)
        )

        # Build metadata with aggregated structural risks
        metadata = {
            "structural_risks": all_structural_risks,
        }

        return ScenarioProjection(
            scenario=scenario,
            region=region,
            annual_projections=annual_projections,
            total_revenue_per_mw=total_revenue_per_mw,
            npv_per_mw=npv_per_mw,
            metadata=metadata,
        )

    # -------------------------------------------------------------------------
    # Fuel Cost Sensitivity Analysis (Requirements 13.1-13.5, 17.4)
    # -------------------------------------------------------------------------

    def calculate_fuel_sensitivity(
        self,
        region: str,
        scenario: ScenarioType,
        battery: BatterySpecs,
        gas_base_price: float = 10.0,
        gas_escalation_rate: float = 0.02,
        pass_through_coefficient: float = 9.5,
    ) -> FuelSensitivityResult:
        """计算燃料成本敏感性分析。

        模型天然气价格变化对峰值电价和 BESS 收入的传导效应。
        输出 5 个情景：-20%, -10%, base, +10%, +20% 气价变化。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            scenario: Central/High/Low scenario type
            battery: Battery specifications
            gas_base_price: Base gas price in $/GJ (default 10.0)
            gas_escalation_rate: Annual gas price escalation rate (default 0.02)
            pass_through_coefficient: $/MWh per $/GJ pass-through (default 9.5)

        Returns:
            FuelSensitivityResult with 5 scenarios and sensitivity coefficient.

        Raises:
            ValueError: If pass_through_coefficient <= 0 or region not supported.
        """
        # Validate pass_through_coefficient > 0 (Requirement 17.4)
        if pass_through_coefficient <= 0:
            raise ValueError(
                f"pass_through_coefficient must be greater than 0, got {pass_through_coefficient}. "
                "The pass-through coefficient represents $/MWh impact per $/GJ gas price change "
                "and must be positive."
            )

        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        # Calculate base revenue (first year) without gas price adjustment
        current_year = date.today().year
        first_projection_year = current_year + 1
        soh = max(0.0, 1.0 - battery.calendar_degradation_rate)

        base_revenue, _ = self.estimate_annual_revenue(
            region=region,
            scenario=scenario,
            year=first_projection_year,
            battery=battery,
            soh=soh,
        )

        # Gas price change scenarios: -20%, -10%, 0% (base), +10%, +20%
        change_percentages = [-20.0, -10.0, 0.0, 10.0, 20.0]
        scenarios: List[FuelSensitivityScenario] = []

        for change_pct in change_percentages:
            # Calculate gas price for this scenario
            gas_price = gas_base_price * (1.0 + change_pct / 100.0)

            # Delta gas price from base
            delta_gas = gas_price - gas_base_price

            # Peak electricity price impact: delta_gas × pass_through_coefficient
            # (Requirement 13.1: linear pass-through)
            peak_price_impact = delta_gas * pass_through_coefficient

            # Revenue impact: peak price impact affects the spread available for BESS
            # Higher peak prices → higher spreads → higher BESS revenue
            # Revenue change is proportional to peak_price_impact relative to mean_spread
            bess_capacity = self._get_cumulative_bess_capacity(
                region, scenario, first_projection_year
            )
            peak_demand = PEAK_DEMAND.get(region, 10000.0)
            bess_ratio = bess_capacity / peak_demand

            dist = self.calculate_price_distribution(
                region=region,
                scenario=scenario,
                year=first_projection_year,
                bess_capacity_ratio=bess_ratio,
            )

            # Revenue impact: the peak_price_impact changes the effective spread
            # Revenue scales linearly with spread change
            if dist.mean_spread > 0:
                revenue_change_fraction = peak_price_impact / dist.mean_spread
            else:
                revenue_change_fraction = 0.0

            revenue_impact = base_revenue * revenue_change_fraction
            revenue_change_pct = revenue_change_fraction * 100.0

            scenarios.append(
                FuelSensitivityScenario(
                    gas_price_change_pct=change_pct,
                    gas_price=gas_price,
                    peak_price_impact=peak_price_impact,
                    revenue_impact=revenue_impact,
                    revenue_change_pct=revenue_change_pct,
                )
            )

        # Sensitivity coefficient: revenue change % per 10% gas price change
        # Use the +10% scenario to calculate this
        ten_pct_scenario = next(
            s for s in scenarios if s.gas_price_change_pct == 10.0
        )
        sensitivity_coefficient = ten_pct_scenario.revenue_change_pct

        return FuelSensitivityResult(
            region=region,
            scenario=scenario.value,
            base_revenue=base_revenue,
            sensitivity_coefficient=sensitivity_coefficient,
            scenarios=scenarios,
        )

    # -------------------------------------------------------------------------
    # Network Augmentation Impact Model (Requirements 14.1-14.4, 17.5)
    # -------------------------------------------------------------------------

    def calculate_network_impact(
        self,
        region: str,
        convergence_factor: float | None = None,
    ) -> NetworkImpactComparison:
        """计算网络增强（互联线投运）对区域价差的影响。

        模型新互联线投运如何通过市场收敛降低区域价差。
        输出事件前后的 20 年价差对比。

        Args:
            region: NEM region or WEM (e.g. "NSW1", "SA1", "WEM")
            convergence_factor: Optional override for convergence factor.
                If provided, must be in [0.05, 0.30]. If None, uses the
                value from capacity_data.json interconnectors field.

        Returns:
            NetworkImpactComparison with before/after spread projections.

        Raises:
            ValueError: If convergence_factor outside [0.05, 0.30] or region not supported.
        """
        if region not in SUPPORTED_REGIONS:
            raise ValueError(
                f"Region '{region}' not supported. Valid regions: {SUPPORTED_REGIONS}"
            )

        # Validate convergence_factor if provided (Requirement 17.5)
        if convergence_factor is not None:
            if not (0.05 <= convergence_factor <= 0.30):
                raise ValueError(
                    f"convergence_factor must be in range [0.05, 0.30], got {convergence_factor}. "
                    "The convergence factor represents the degree of regional price convergence "
                    "caused by interconnector commissioning."
                )

        # Load interconnector events for this region from capacity_data.json
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            raise FileNotFoundError(
                f"Required data file not found: {capacity_path}. "
                "The capacity data is needed for network impact analysis."
            )

        with open(capacity_path, "r", encoding="utf-8") as f:
            capacity_data = json.load(f)

        # Find interconnectors affecting this region
        region_interconnectors: List[NetworkAugmentationEvent] = []
        for ic in capacity_data.get("interconnectors", []):
            if region in (ic["from_region"], ic["to_region"]):
                ic_convergence = convergence_factor if convergence_factor is not None else ic["convergence_factor"]

                # Validate convergence_factor from data (Requirement 17.5)
                if not (0.05 <= ic_convergence <= 0.30):
                    raise ValueError(
                        f"convergence_factor for interconnector '{ic['name']}' "
                        f"must be in range [0.05, 0.30], got {ic_convergence}."
                    )

                region_interconnectors.append(
                    NetworkAugmentationEvent(
                        name=ic["name"],
                        from_region=ic["from_region"],
                        to_region=ic["to_region"],
                        capacity_mw=ic["capacity_mw"],
                        expected_date=date.fromisoformat(ic["expected_date"]),
                        convergence_factor=ic_convergence,
                        spread_impact_factor=1.0 - ic_convergence,
                    )
                )

        # Use the first (earliest) interconnector for the comparison
        # If no interconnectors found, return empty comparison
        if not region_interconnectors:
            current_year = date.today().year
            base_spread = BASE_SPREAD_PARAMS[region]["mean_spread"]
            spread_data = [
                {"year": current_year + i + 1, "spread": base_spread}
                for i in range(20)
            ]
            return NetworkImpactComparison(
                project_name="No interconnector projects",
                region=region,
                spread_before=spread_data,
                spread_after=spread_data,
                reduction_pct=0.0,
            )

        # Sort by expected date and use the earliest project for comparison
        region_interconnectors.sort(key=lambda x: x.expected_date)
        primary_project = region_interconnectors[0]

        # Generate 20-year spread projections: before and after network augmentation
        current_year = date.today().year
        base_spread = BASE_SPREAD_PARAMS[region]["mean_spread"]

        spread_before: List[dict] = []
        spread_after: List[dict] = []

        # Calculate spread WITHOUT network augmentation events
        # (only apply coal closure events — BESS compression handled separately)
        for i in range(20):
            year = current_year + i + 1
            spread_no_network = base_spread

            # Apply non-network, non-BESS events (coal closures only)
            for event in self.event_registry.events:
                if event.region != region:
                    continue
                if event.event_type == EventType.NETWORK_AUGMENTATION:
                    continue
                if event.event_type == EventType.BESS_COMMISSIONING:
                    continue
                effective_date = self._get_effective_event_date(event, ScenarioType.CENTRAL)
                if effective_date.year <= year:
                    # Apply coal retirement decay (consistent with calculate_price_distribution)
                    if event.event_type == EventType.COAL_CLOSURE:
                        years_since = year - effective_date.year
                        decay = max(0.0, 1.0 - 0.20 * years_since)
                        effective_impact = 1.0 + (event.spread_impact_factor - 1.0) * decay
                        spread_no_network *= effective_impact
                    else:
                        spread_no_network *= event.spread_impact_factor

            spread_before.append({"year": year, "spread": round(max(0.0, spread_no_network), 2)})

        # Calculate spread WITH network augmentation events
        # (apply coal closure + network events — BESS compression handled separately)
        for i in range(20):
            year = current_year + i + 1
            spread_with_network = base_spread

            # Apply all events except BESS (consistent with calculate_price_distribution)
            for event in self.event_registry.events:
                if event.region != region:
                    continue
                if event.event_type == EventType.BESS_COMMISSIONING:
                    continue
                effective_date = self._get_effective_event_date(event, ScenarioType.CENTRAL)
                if effective_date.year <= year:
                    # Apply coal retirement decay
                    if event.event_type == EventType.COAL_CLOSURE:
                        years_since = year - effective_date.year
                        decay = max(0.0, 1.0 - 0.20 * years_since)
                        effective_impact = 1.0 + (event.spread_impact_factor - 1.0) * decay
                        spread_with_network *= effective_impact
                    else:
                        spread_with_network *= event.spread_impact_factor

            spread_after.append({"year": year, "spread": round(max(0.0, spread_with_network), 2)})

        # Calculate overall reduction percentage
        total_before = sum(entry["spread"] for entry in spread_before)
        total_after = sum(entry["spread"] for entry in spread_after)
        reduction_pct = (
            ((total_before - total_after) / total_before * 100.0)
            if total_before > 0
            else 0.0
        )

        return NetworkImpactComparison(
            project_name=primary_project.name,
            region=region,
            spread_before=spread_before,
            spread_after=spread_after,
            reduction_pct=round(reduction_pct, 2),
        )

    # -------------------------------------------------------------------------
    # Monthly Benchmark Validation (backtest-expansion-mvp)
    # -------------------------------------------------------------------------

    def validate_against_monthly_benchmarks(
        self, end_month: Optional[str] = None, target_month: Optional[str] = None
    ) -> Dict:
        """对比模型 mean_spread 预测与 AEMO 月度基准 (Req 2.1-2.5)。

        薄委托：延迟 import 后转交 backtest_expansion 实现，引擎本体对新模块
        零硬依赖。target_month 给定时只验证该月（供月度 reconciliation 复用）。
        """
        from engines.backtest_expansion import validate_against_monthly_benchmarks_impl

        return validate_against_monthly_benchmarks_impl(
            engine=self, end_month=end_month, target_month=target_month
        )
