"""ML Parameter Calibration Engine.

用 LightGBM 从历史价格数据学习 ForwardPriceEngine 的关键参数：
- base_spread: 各区域基础价差
- compression_factor: BESS 饱和压缩系数（非线性）
- spike_frequency: 价格尖峰频率

训练策略: 2020-2023 训练，2024-2025 验证（日度粒度）
验证指标: MAE, 方向准确率, R²

v4 改进:
- 目标变量: rolling_30d_spread（前 30 天 winsorized daily spread 的均值，$80-200 量级）
  与 ForwardPriceEngine 的 mean_spread 是同一个指标，平滑稳定，无需缩放因子。
- 输入特征: 日度粒度滞后特征（lag_1_spread, lag_7_spread, lag_30_spread 等），
  捕获短期动态，消除数据泄漏。
"""

from __future__ import annotations

import json
import logging
import math
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional

import numpy as np

logger = logging.getLogger(__name__)

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"

# NEM 区域列表
NEM_REGIONS = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]

# 区域编码映射
REGION_ENCODING: Dict[str, int] = {
    "NSW1": 0,
    "QLD1": 1,
    "VIC1": 2,
    "SA1": 3,
    "TAS1": 4,
}

# FCAS 价格成分占价差的估计比例（用于从 rolling_30d_spread 中剥离 FCAS 信号）
# 默认 5%，可在后续有独立 FCAS 价格数据时替换为精确计算
FCAS_SPREAD_FRACTION: float = 0.05


class MLCalibrationEngine:
    """ML 参数校准引擎。

    使用 LightGBM 从历史 trading_price 数据学习 ForwardPriceEngine 的关键参数。
    日度粒度：每天每区域一条记录，目标变量为 rolling_30d_spread（30 天滚动平均价差）。

    v4 改进:
    - 目标变量: rolling_30d_spread（前 30 天 winsorized daily spread 的均值，$80-200 量级），
      与 ForwardPriceEngine 的 mean_spread 是同一个指标，平滑稳定。
    - 输入特征: 日度粒度滞后特征（lag_1_spread, lag_7_spread, lag_30_spread 等），
      捕获短期动态，消除数据泄漏。
    """

    def __init__(self, db):
        self.db = db
        self.model = None       # P50 主模型
        self.model_p10 = None   # P10 悲观/下限模型
        self.model_p90 = None   # P90 乐观/上限模型
        self.calibration_metadata: Dict = {}
        self.calibrated_params: Dict = {}

    @staticmethod
    def _get_fcas_spread_fraction(year: int) -> float:
        """FCAS 占价差的比例随时间衰减（反映 FCAS 市场崩塌）。
        
        基于 Modo Energy 数据：
        - 2020: FCAS 收入 $384k/MW → 占总收入 ~25%
        - 2023: FCAS 收入 ~$50k/MW → 占总收入 ~10%
        - 2025+: FCAS 收入 $11k/MW → 占总收入 ~2%
        """
        if year <= 2020:
            return 0.25
        elif year >= 2025:
            return 0.02
        else:
            # 2020-2025 线性衰减: 0.25 → 0.02
            return 0.25 - (year - 2020) * 0.046

    def calibrate(self) -> dict:
        """主入口：执行完整校准流程。

        Returns:
            校准后的参数字典，按区域组织。
            如果校准失败或数据不足，返回空字典。
        """
        try:
            # 1. 提取日度特征
            features = self._extract_daily_features()

            if features is None or len(features) < 90:
                logger.warning("ML 校准: 数据不足 (需要至少 90 天数据)")
                self.calibration_metadata = {
                    "status": "insufficient_data",
                    "sample_count": len(features) if features is not None else 0,
                }
                return {}

            # 2. 训练模型
            self._train_model(features)

            if self.model is None:
                return {}

            # 3. 生成校准参数
            self._generate_calibrated_params(features)

            # 4. 返回校准结果
            return self.calibrated_params

        except ImportError as e:
            logger.warning(f"ML 校准: 依赖缺失 - {e}")
            self.calibration_metadata = {
                "status": "dependency_missing",
                "error": str(e),
            }
            return {}
        except Exception as e:
            logger.warning(f"ML 校准: 训练失败 - {e}")
            self.calibration_metadata = {
                "status": "failed",
                "error": str(e),
            }
            return {}

    def _extract_daily_features(self) -> Optional[List[dict]]:
        """从数据库提取日度特征。

        对每个区域、每天计算：
        - daily_spread: winsorized daily MAX-MIN（clip 到 [-100, 500] 后的极差）（中间变量）
        - avg_price: 当天均价（仅用于计算滞后特征，不直接作为输入）
        - max_price: 当天最高价
        - min_price: 当天最低价
        - spike_ratio: 当天 >$300 的比例（仅用于计算滞后特征）
        - interval_count: 间隔数量
        """
        records: List[dict] = []
        years = range(2020, 2027)

        # 加载 BESS 容量数据用于计算累计容量
        bess_timeline = self._build_bess_capacity_timeline()

        for year in years:
            table_name = f"trading_price_{year}"

            # 检查表是否存在
            if not self._table_exists(table_name):
                continue

            for region in NEM_REGIONS:
                daily_rows = self._query_daily_stats(table_name, region)

                if not daily_rows:
                    continue

                # 批量查询日内特征（evening_solar_spread, morning_ramp_spread）
                intraday_features_map = self._query_intraday_features_batch(
                    table_name, region
                )

                from engines.forward_price_engine import PEAK_DEMAND

                peak_demand = PEAK_DEMAND.get(region, 10000.0)

                for row in daily_rows:
                    trade_date = row["trade_date"]
                    # 解析日期
                    try:
                        dt = datetime.strptime(trade_date, "%Y-%m-%d")
                    except ValueError:
                        continue

                    month = dt.month
                    year_month = f"{dt.year}-{dt.month:02d}"

                    # 季节性特征
                    month_sin = math.sin(2 * math.pi * month / 12)
                    month_cos = math.cos(2 * math.pi * month / 12)

                    # 星期特征
                    day_of_week = dt.weekday()  # 0=Monday, 6=Sunday
                    is_weekend = 1.0 if day_of_week >= 5 else 0.0

                    # BESS 容量比（按月变化）
                    bess_capacity = bess_timeline.get(region, {}).get(
                        year_month, 0.0
                    )
                    bess_capacity_ratio = bess_capacity / peak_demand

                    # 日内特征（当天原始值，后续在 _add_lag_features 中转为滞后特征）
                    intraday = intraday_features_map.get(trade_date, {})
                    evening_solar_spread = intraday.get("evening_solar_spread", 0.0)
                    morning_ramp_spread = intraday.get("morning_ramp_spread", 0.0)

                    records.append(
                        {
                            "trade_date": trade_date,
                            "year": dt.year,
                            "month": month,
                            "region": region,
                            "region_encoded": REGION_ENCODING[region],
                            "daily_spread": row["daily_spread"],
                            "avg_price": row["avg_price"],
                            "max_price": row["max_price"],
                            "min_price": row["min_price"],
                            "spike_ratio": row["spike_ratio"],
                            "interval_count": row["interval_count"],
                            "day_of_week": day_of_week,
                            "month_sin": month_sin,
                            "month_cos": month_cos,
                            "is_weekend": is_weekend,
                            "bess_capacity_ratio": bess_capacity_ratio,
                            "evening_solar_spread": evening_solar_spread,
                            "morning_ramp_spread": morning_ramp_spread,
                        }
                    )

        if not records:
            return None

        # 按区域和时间排序，添加滞后特征
        records.sort(key=lambda r: (r["region"], r["trade_date"]))
        self._add_lag_features(records)

        return records

    def _query_intraday_features_batch(
        self, table_name: str, region: str
    ) -> Dict[str, dict]:
        """批量查询单个区域所有天的半小时价格并计算日内特征。

        Returns:
            {trade_date: {evening_solar_spread, morning_ramp_spread, incomplete_intraday}}
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT settlement_date, rrp_aud_mwh
                    FROM {table_name}
                    WHERE region_id = ?
                    ORDER BY settlement_date
                    """,
                    (region,),
                )
                rows = cursor.fetchall()

            if not rows:
                return {}

            # 按日期分组收集价格
            from collections import defaultdict
            daily_prices: Dict[str, List[tuple]] = defaultdict(list)
            for row in rows:
                if row[0] is None or row[1] is None:
                    continue
                settlement_date_str = str(row[0])
                trade_date = settlement_date_str[:10]  # YYYY-MM-DD
                # 提取时间部分用于排序
                daily_prices[trade_date].append(
                    (settlement_date_str, float(row[1]))
                )

            # 对每天计算日内特征
            result: Dict[str, dict] = {}
            for trade_date, price_entries in daily_prices.items():
                # 按时间排序
                price_entries.sort(key=lambda x: x[0])
                prices = [p[1] for p in price_entries]

                # 如果是 5 分钟数据（288 个间隔），需要聚合为半小时
                if len(prices) >= 288:
                    # 每 6 个 5 分钟间隔取平均得到半小时价格
                    half_hourly = []
                    for i in range(0, 288, 6):
                        chunk = prices[i:i+6]
                        half_hourly.append(float(np.mean(chunk)))
                    prices = half_hourly
                elif len(prices) >= 96:
                    # 每 2 个 15 分钟间隔取平均得到半小时价格
                    half_hourly = []
                    for i in range(0, len(prices), 2):
                        chunk = prices[i:i+2]
                        half_hourly.append(float(np.mean(chunk)))
                    prices = half_hourly

                # 调用已有方法计算日内特征
                features = self._compute_intraday_features(prices)
                result[trade_date] = features

            return result

        except Exception as e:
            logger.debug(f"查询 {table_name}/{region} 日内数据失败: {e}")
            return {}

    def _query_daily_stats(
        self, table_name: str, region: str
    ) -> List[dict]:
        """查询单个区域所有天的统计数据（批量查询优化）。

        daily_spread 为 winsorized daily MAX-MIN（价格先 clip 到 [-100, 500] 范围，再取 MAX-MIN），
        作为中间变量用于计算 rolling_30d_spread（目标变量）和滞后特征。
        """
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT
                        SUBSTR(settlement_date, 1, 10) as trade_date,
                        MAX(CASE WHEN rrp_aud_mwh > 500 THEN 500 WHEN rrp_aud_mwh < -100 THEN -100 ELSE rrp_aud_mwh END)
                        - MIN(CASE WHEN rrp_aud_mwh > 500 THEN 500 WHEN rrp_aud_mwh < -100 THEN -100 ELSE rrp_aud_mwh END)
                        as daily_spread,
                        AVG(rrp_aud_mwh) as avg_price,
                        MAX(rrp_aud_mwh) as max_price,
                        MIN(rrp_aud_mwh) as min_price,
                        AVG(CASE WHEN rrp_aud_mwh > 300 THEN 1.0 ELSE 0.0 END) as spike_ratio,
                        COUNT(*) as interval_count
                    FROM {table_name}
                    WHERE region_id = ?
                    GROUP BY SUBSTR(settlement_date, 1, 10)
                    HAVING COUNT(*) >= 48
                    ORDER BY trade_date
                    """,
                    (region,),
                )
                rows = cursor.fetchall()

                results = []
                for row in rows:
                    if row[0] is None:
                        continue
                    daily_spread = float(row[1]) if row[1] is not None else 0.0
                    results.append(
                        {
                            "trade_date": str(row[0]),
                            "daily_spread": daily_spread,
                            "avg_price": float(row[2]) if row[2] is not None else 0.0,
                            "max_price": float(row[3]) if row[3] is not None else 0.0,
                            "min_price": float(row[4]) if row[4] is not None else 0.0,
                            "spike_ratio": float(row[5]) if row[5] is not None else 0.0,
                            "interval_count": int(row[6]),
                        }
                    )
                return results
        except Exception as e:
            logger.debug(f"查询 {table_name}/{region} 日度数据失败: {e}")
            return []

    def _table_exists(self, table_name: str) -> bool:
        """检查数据库表是否存在。"""
        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
                    (table_name,),
                )
                return cursor.fetchone() is not None
        except Exception:
            return False

    def _build_bess_capacity_timeline(self) -> Dict[str, Dict[str, float]]:
        """从 capacity_data.json 构建各区域的 BESS 容量时间线。

        Returns:
            {region: {year_month: cumulative_capacity_mw}}
        """
        capacity_path = DATA_DIR / "capacity_data.json"
        if not capacity_path.exists():
            return {}

        try:
            with open(capacity_path, "r", encoding="utf-8") as f:
                capacity_data = json.load(f)
        except Exception:
            return {}

        # 收集每个区域的项目及其投运日期
        region_projects: Dict[str, List[tuple]] = {}
        for project in capacity_data.get("projects", []):
            region = project.get("region", "")
            if region not in NEM_REGIONS:
                continue

            date_str = project.get("actual_commissioning_date") or project.get(
                "expected_commissioning_date", ""
            )
            if not date_str:
                continue

            capacity_mw = project.get("capacity_mw", 0)
            region_projects.setdefault(region, []).append((date_str[:7], capacity_mw))

        # 构建累计时间线
        timeline: Dict[str, Dict[str, float]] = {}
        for region, projects in region_projects.items():
            projects.sort(key=lambda x: x[0])
            cumulative = 0.0
            monthly: Dict[str, float] = {}

            for ym, cap in projects:
                cumulative += cap
                monthly[ym] = cumulative

            # 填充后续月份
            if monthly:
                all_months = sorted(monthly.keys())
                last_ym = all_months[-1]
                last_cap = monthly[last_ym]

                # 向后填充到 2026-12
                current = last_ym
                while current <= "2026-12":
                    if current not in monthly:
                        monthly[current] = last_cap
                    year_int = int(current[:4])
                    month_int = int(current[5:7])
                    month_int += 1
                    if month_int > 12:
                        month_int = 1
                        year_int += 1
                    current = f"{year_int}-{month_int:02d}"

                # 向前填充（投运前容量为 0）
                first_ym = all_months[0]
                current = "2020-01"
                while current < first_ym:
                    monthly.setdefault(current, 0.0)
                    year_int = int(current[:4])
                    month_int = int(current[5:7])
                    month_int += 1
                    if month_int > 12:
                        month_int = 1
                        year_int += 1
                    current = f"{year_int}-{month_int:02d}"

                # 确保中间月份也有正确的累计值
                sorted_months = sorted(monthly.keys())
                prev_cap = 0.0
                for ym in sorted_months:
                    if monthly[ym] < prev_cap:
                        monthly[ym] = prev_cap
                    prev_cap = monthly[ym]

            timeline[region] = monthly

        return timeline

    def _add_lag_features(self, records: List[dict]) -> None:
        """为记录添加滞后特征（日度：前1天、前7天均值、前30天均值）。

        所有特征均使用滞后值，消除数据泄漏：
        - lag_1_avg_price: 前一天均价
        - lag_1_spike_ratio: 前一天尖峰比例
        - lag_1_spread: 前 1 天日均价差
        - lag_7_spread: 前 7 天日均价差均值
        - lag_30_spread: 前 30 天日均价差均值
        - rolling_7d_volatility: 前 7 天价差标准差（捕获波动率regime）
        - rolling_30d_spread: 前 30 天（含当天）daily_spread 均值（目标变量）
        """
        # 按区域分组
        by_region: Dict[str, List[dict]] = {}
        for r in records:
            by_region.setdefault(r["region"], []).append(r)

        for region, region_records in by_region.items():
            region_records.sort(key=lambda x: x["trade_date"])
            for i, rec in enumerate(region_records):
                # lag_1_avg_price: 前一天均价（替代当天均价，消除数据泄漏）
                rec["lag_1_avg_price"] = (
                    region_records[i - 1]["avg_price"] if i >= 1 else 0.0
                )

                # lag_1_spike_ratio: 前一天尖峰比例（替代当天尖峰比例）
                rec["lag_1_spike_ratio"] = (
                    region_records[i - 1]["spike_ratio"] if i >= 1 else 0.0
                )

                # lag_1_spread: 前 1 天日均价差
                rec["lag_1_spread"] = (
                    region_records[i - 1]["daily_spread"] if i >= 1 else 0.0
                )

                # lag_1_evening_solar_spread: 前一天的 evening_solar_spread
                rec["lag_1_evening_solar_spread"] = (
                    region_records[i - 1].get("evening_solar_spread", 0.0) if i >= 1 else 0.0
                )

                # lag_1_morning_ramp_spread: 前一天的 morning_ramp_spread
                rec["lag_1_morning_ramp_spread"] = (
                    region_records[i - 1].get("morning_ramp_spread", 0.0) if i >= 1 else 0.0
                )

                # lag_7_spread: 前 7 天日均价差均值
                if i >= 7:
                    recent_7 = [region_records[i - j]["daily_spread"] for j in range(1, 8)]
                    rec["lag_7_spread"] = float(np.mean(recent_7))
                    rec["rolling_7d_volatility"] = float(np.std(recent_7))
                else:
                    if i > 0:
                        past = [region_records[j]["daily_spread"] for j in range(i)]
                        rec["lag_7_spread"] = float(np.mean(past))
                        rec["rolling_7d_volatility"] = float(np.std(past)) if len(past) > 1 else 0.0
                    else:
                        rec["lag_7_spread"] = 0.0
                        rec["rolling_7d_volatility"] = 0.0

                # lag_30_spread: 前 30 天日均价差均值
                if i >= 30:
                    rec["lag_30_spread"] = float(
                        np.mean([region_records[i - j]["daily_spread"] for j in range(1, 31)])
                    )
                else:
                    rec["lag_30_spread"] = (
                        float(np.mean([region_records[j]["daily_spread"] for j in range(i)]))
                        if i > 0
                        else 0.0
                    )

                # rolling_30d_spread: 前 30 天（含当天）的 daily_spread 均值（目标变量）
                # 量级 $80-200，与 ForwardPriceEngine 的 mean_spread 一致
                # 这不是数据泄漏——使用的是截至今天的 30 天已知信息
                if i >= 29:
                    raw_rolling_30d = float(
                        np.mean([region_records[i - j]["daily_spread"] for j in range(30)])
                    )
                else:
                    raw_rolling_30d = (
                        float(np.mean([region_records[j]["daily_spread"] for j in range(i + 1)]))
                        if i >= 0
                        else 0.0
                    )

                # 剥离 FCAS 价格成分，仅保留能量套利价差信号 (Req 1.4)
                # FCAS 贡献估计为价差的固定比例，剥离后 clamp 到非负
                # 从记录的 trade_date 提取年份
                record_year = int(rec.get("trade_date", "2025")[:4])
                fcas_fraction = MLCalibrationEngine._get_fcas_spread_fraction(record_year)
                fcas_contribution = raw_rolling_30d * fcas_fraction
                rec["rolling_30d_spread"] = max(0.0, raw_rolling_30d - fcas_contribution)

    def _train_model(self, features: List[dict]) -> None:
        """训练 LightGBM Quantile Regression 模型（P10/P50/P90）。

        时间序列分割：2020-2024 训练，2025-2026.06 验证。
        使用 quantile objective 训练 3 个模型，输出置信区间。
        目标变量为 rolling_30d_spread（30 天滚动平均价差）。

        训练窗口扩展到 2024 末以包含 BESS 自相残杀阶段（Modo 2026-04 数据显示
        QLD BESS 收入 -73% YoY, NSW -51% YoY），让模型看到饱和压缩动态。
        """
        import lightgbm as lgb

        # 分割训练集和验证集
        # 训练: 2020-01 到 2024-12（包含 BESS 渗透率快速增长期）
        # 验证: 2025-01 到 2026-06（包含 BESS 饱和与价差崩塌）
        train_data = [r for r in features if r["trade_date"] < "2025-01-01" and r.get("rolling_30d_spread", 0) > 0]
        val_data = [
            r
            for r in features
            if r["trade_date"] >= "2025-01-01" and r["trade_date"] < "2026-07-01"
            and r.get("rolling_30d_spread", 0) > 0
        ]

        if len(train_data) < 90:
            logger.warning(f"ML 校准: 训练数据不足 ({len(train_data)} 条)")
            self.calibration_metadata = {
                "status": "insufficient_data",
                "train_samples": len(train_data),
            }
            return

        feature_cols = [
            "lag_1_avg_price",      # 前一天均价（替代当天均价，消除数据泄漏）
            "lag_1_spike_ratio",    # 前一天尖峰比例（替代当天尖峰比例）
            "day_of_week",
            "month_sin",
            "month_cos",
            "is_weekend",
            "bess_capacity_ratio",
            "lag_1_spread",
            "lag_7_spread",
            "rolling_7d_volatility",  # 前 7 天价差波动率（捕获高波动regime）
            "region_encoded",
            "lag_1_evening_solar_spread",   # 前一天晚峰-午间价差（日内结构特征）
            "lag_1_morning_ramp_spread",    # 前一天早间爬坡价差（日内结构特征）
        ]
        target_col = "rolling_30d_spread"  # 30 天滚动平均价差

        # 构建训练矩阵
        X_train = np.array([[r[c] for c in feature_cols] for r in train_data])
        y_train = np.array([r[target_col] for r in train_data])

        # 计算样本权重（时间衰减）
        sample_weights = self._compute_sample_weights(train_data)

        # 声明 region_encoded 为 categorical feature（LightGBM 原生支持）
        # 传入样本权重实现时间衰减加权训练
        train_dataset = lgb.Dataset(
            X_train, y_train,
            feature_name=feature_cols,
            categorical_feature=["region_encoded"],
            weight=sample_weights,
        )

        # 验证集（如果有）
        valid_sets = [train_dataset]
        valid_names = ["train"]
        X_val = None
        y_val = None

        if len(val_data) >= 30:
            X_val = np.array([[r[c] for c in feature_cols] for r in val_data])
            y_val = np.array([r[target_col] for r in val_data])
            val_dataset = lgb.Dataset(
                X_val, y_val,
                feature_name=feature_cols,
                categorical_feature=["region_encoded"],
            )
            valid_sets.append(val_dataset)
            valid_names.append("valid")

        # LightGBM 基础参数（含正则化，防止过拟合）
        # monotone_constraints: bess_capacity_ratio（索引 6）强制单调递减（-1）
        # 注意：LightGBM 不支持 quantile objective 与 monotone_constraints 同时使用，
        # 因此 P50 使用 regression objective + monotone_constraints，P10/P90 使用 quantile 不带约束
        base_params = {
            "num_leaves": 31,
            "learning_rate": 0.05,
            "feature_fraction": 0.8,
            "bagging_fraction": 0.8,
            "bagging_freq": 5,
            "min_data_in_leaf": 20,   # 防止过拟合到极端天
            "lambda_l1": 0.1,         # L1 正则化
            "lambda_l2": 0.1,         # L2 正则化
            "verbose": -1,
        }

        # P50 使用 regression + monotone_constraints（强制 bess_capacity_ratio 单调递减）
        params_p50 = {
            **base_params,
            "objective": "regression",
            "metric": "mae",
            "monotone_constraints": [0, 0, 0, 0, 0, 0, -1, 0, 0, 0, 0, 0, 0],
        }
        # P10/P90 使用 quantile objective（不支持 monotone_constraints）
        params_p10 = {**base_params, "objective": "quantile", "metric": "quantile", "alpha": 0.1}
        params_p90 = {**base_params, "objective": "quantile", "metric": "quantile", "alpha": 0.9}

        # 训练回调
        def _make_callbacks():
            cbs = []
            if len(val_data) >= 30:
                cbs.append(lgb.early_stopping(20, verbose=False))
            cbs.append(lgb.log_evaluation(period=0))
            return cbs

        # 训练 P50 主模型（中位数）
        model_p50 = lgb.train(
            params_p50,
            train_dataset,
            num_boost_round=300,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=_make_callbacks(),
        )

        # 训练 P10 模型（悲观/下限）
        model_p10 = lgb.train(
            params_p10,
            train_dataset,
            num_boost_round=300,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=_make_callbacks(),
        )

        # 训练 P90 模型（乐观/上限）
        model_p90 = lgb.train(
            params_p90,
            train_dataset,
            num_boost_round=300,
            valid_sets=valid_sets,
            valid_names=valid_names,
            callbacks=_make_callbacks(),
        )

        self.model = model_p50      # 主模型（用于校准参数）
        self.model_p10 = model_p10
        self.model_p90 = model_p90

        # 计算验证指标（基于 P50 主模型）
        if len(val_data) >= 30 and X_val is not None and y_val is not None:
            val_pred = self.model.predict(X_val)

            mae = float(np.mean(np.abs(val_pred - y_val)))
            ss_res = float(np.sum((y_val - val_pred) ** 2))
            ss_tot = float(np.sum((y_val - y_val.mean()) ** 2))
            r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0

            # 计算训练集 MAE（用于 concept drift 检测）
            train_pred = self.model.predict(X_train)
            train_mae = float(np.mean(np.abs(train_pred - y_train)))

            # Concept drift 检测：验证集 MAE > 2×训练集 MAE
            concept_drift_detected = False
            calibration_weight = 1.0
            if train_mae > 0 and mae > 2.0 * train_mae:
                concept_drift_detected = True
                calibration_weight = 0.5
                logger.warning(
                    f"ML 校准: Concept drift 检测触发 "
                    f"(val_MAE={mae:.2f} > 2×train_MAE={2*train_mae:.2f})，"
                    f"校准权重降低至 {calibration_weight}"
                )

            # 方向准确率
            if len(val_pred) > 1:
                direction_accuracy = float(
                    np.mean(
                        np.sign(np.diff(val_pred)) == np.sign(np.diff(y_val))
                    )
                )
            else:
                direction_accuracy = 0.0

            # 置信区间覆盖率（P10-P90 应覆盖约 80% 的实际值）
            val_pred_p10 = self.model_p10.predict(X_val)
            val_pred_p90 = self.model_p90.predict(X_val)
            coverage = float(np.mean((y_val >= val_pred_p10) & (y_val <= val_pred_p90)))

            # 计算各分位数的 pinball loss
            pinball_loss_p10 = self._compute_pinball_loss(y_val, val_pred_p10, 0.1)
            pinball_loss_p50 = self._compute_pinball_loss(y_val, val_pred, 0.5)
            pinball_loss_p90 = self._compute_pinball_loss(y_val, val_pred_p90, 0.9)

            # 质量检查：rolling_30d_spread（30 天滚动平均价差）量级为 $80-200，
            # R² > 0.3 为主要质量标准，方向准确率 > 0.45 为辅助标准
            quality_ok = r2 > 0.3 and direction_accuracy > 0.45
            quality_status = "calibrated" if quality_ok else "quality_insufficient"

            # R² > 0.85 提示可能存在残余过拟合（模型仍被接受）
            if r2 > 0.85:
                logger.warning(f"ML 校准: R²={r2:.3f} 可能存在残余过拟合")

            self.calibration_metadata = {
                "status": quality_status,
                "train_period": f"{train_data[0]['trade_date']} to {train_data[-1]['trade_date']}",
                "validation_period": f"{val_data[0]['trade_date']} to {val_data[-1]['trade_date']}",
                "validation_mae": mae,
                "train_mae": train_mae,
                "validation_r2": r2,
                "direction_accuracy": direction_accuracy,
                "confidence_interval_coverage": coverage,
                "train_samples": len(train_data),
                "val_samples": len(val_data),
                "calibrated_at": datetime.now().isoformat(),
                "sample_count": len(features),
                "concept_drift_detected": concept_drift_detected,
                "calibration_weight": calibration_weight,
                "pinball_loss": {
                    "p10": pinball_loss_p10,
                    "p50": pinball_loss_p50,
                    "p90": pinball_loss_p90,
                },
            }

            # 如果质量不足，不使用模型
            if quality_status == "quality_insufficient":
                logger.warning(
                    f"ML 校准: 模型质量不足 (R²={r2:.3f}, 方向={direction_accuracy:.3f})，降级为默认参数"
                )
                self.model = None
                self.model_p10 = None
                self.model_p90 = None
                return
        else:
            # 没有足够验证集，仅记录训练信息
            self.calibration_metadata = {
                "status": "calibrated",
                "train_period": f"{train_data[0]['trade_date']} to {train_data[-1]['trade_date']}",
                "validation_period": "N/A (insufficient validation data)",
                "validation_mae": None,
                "validation_r2": None,
                "direction_accuracy": None,
                "confidence_interval_coverage": None,
                "train_samples": len(train_data),
                "val_samples": 0,
                "calibrated_at": datetime.now().isoformat(),
                "sample_count": len(features),
            }

        logger.info(
            f"ML 校准完成: MAE={self.calibration_metadata.get('validation_mae')}, "
            f"R²={self.calibration_metadata.get('validation_r2')}, "
            f"CI覆盖率={self.calibration_metadata.get('confidence_interval_coverage')}, "
            f"训练样本={len(train_data)}, 验证样本={len(val_data)}"
        )

    def _generate_calibrated_params(self, features: List[dict]) -> None:
        """用训练好的模型生成校准参数（含 P10/P50/P90 置信区间）。

        对每个区域，用最近 30 天数据的平均特征预测 base_spread。
        P10/P50/P90 分别对应悲观/中位数/乐观预测。
        """
        if self.model is None:
            return

        feature_cols = [
            "lag_1_avg_price",
            "lag_1_spike_ratio",
            "day_of_week",
            "month_sin",
            "month_cos",
            "is_weekend",
            "bess_capacity_ratio",
            "lag_1_spread",
            "lag_7_spread",
            "rolling_7d_volatility",
            "region_encoded",
            "lag_1_evening_solar_spread",
            "lag_1_morning_ramp_spread",
        ]

        for region in NEM_REGIONS:
            # 获取该区域最近 30 天的数据
            region_records = [r for r in features if r["region"] == region]
            if not region_records:
                continue

            region_records.sort(key=lambda x: x["trade_date"], reverse=True)
            recent = region_records[:30]

            # 用最近 30 天数据的平均特征预测
            avg_features = []
            for col in feature_cols:
                avg_val = np.mean([r[col] for r in recent])
                avg_features.append(float(avg_val))

            # P50 主预测（中位数）
            predicted_p50 = float(self.model.predict([avg_features])[0])
            # rolling_30d_spread 量级 $80-200
            predicted_p50 = max(40.0, min(300.0, predicted_p50))

            # P10 悲观预测（下限）
            predicted_p10 = float(self.model_p10.predict([avg_features])[0])
            predicted_p10 = max(20.0, min(300.0, predicted_p10))

            # P90 乐观预测（上限）
            predicted_p90 = float(self.model_p90.predict([avg_features])[0])
            predicted_p90 = max(40.0, min(400.0, predicted_p90))

            # 确保 P10 <= P50 <= P90（quantile crossing 修正）
            predicted_p10 = min(predicted_p10, predicted_p50)
            predicted_p90 = max(predicted_p90, predicted_p50)

            # 估算尖峰频率（最近 30 天平均）
            avg_spike_ratio = float(np.mean([r["spike_ratio"] for r in recent]))

            self.calibrated_params[region] = {
                "base_spread": predicted_p50,           # 主校准值（P50 中位数）
                "base_spread_p10": predicted_p10,       # 悲观/下限
                "base_spread_p90": predicted_p90,       # 乐观/上限
                "spike_frequency": max(0.0, min(1.0, avg_spike_ratio)),
            }

        # 拟合压缩曲线
        self.calibrated_params["compression_curve"] = self._fit_compression_curve(
            features
        )

    def _fit_compression_curve(self, features: List[dict]) -> dict:
        """从历史数据拟合 BESS 容量与价差压缩的非线性关系。

        Returns:
            压缩曲线参数 {coefficient, exponent}
        """
        # 收集 (bess_ratio, spread) 数据点
        points = [
            (r["bess_capacity_ratio"], r["rolling_30d_spread"])
            for r in features
            if r["bess_capacity_ratio"] > 0 and r.get("rolling_30d_spread", 0) > 0
        ]

        if len(points) < 5:
            return {"coefficient": 1.0, "exponent": 1.0}

        ratios = np.array([p[0] for p in points])
        spreads = np.array([p[1] for p in points])

        # 归一化 spread（相对于最大值）
        max_spread = spreads.max()
        if max_spread <= 0:
            return {"coefficient": 1.0, "exponent": 1.0}

        normalized_spreads = spreads / max_spread

        # 简单线性回归 log(normalized_spread) ~ log(1 + ratio)
        # 即 spread ∝ (1 + ratio)^exponent
        try:
            log_ratios = np.log1p(ratios)
            log_spreads = np.log(np.clip(normalized_spreads, 0.01, 1.0))

            # 最小二乘拟合
            if np.std(log_ratios) > 0:
                slope = float(
                    np.sum(
                        (log_ratios - log_ratios.mean())
                        * (log_spreads - log_spreads.mean())
                    )
                    / np.sum((log_ratios - log_ratios.mean()) ** 2)
                )
                # 限制指数在合理范围
                exponent = max(-3.0, min(0.0, slope))
            else:
                exponent = -1.0

            return {
                "coefficient": float(max_spread),
                "exponent": exponent,
            }
        except Exception:
            return {"coefficient": 1.0, "exponent": 1.0}

    def _estimate_spike_frequency(self, region: str) -> float:
        """估算区域的尖峰频率。"""
        # 从最近一年的数据估算
        current_year = datetime.now().year
        table_name = f"trading_price_{current_year}"

        if not self._table_exists(table_name):
            table_name = f"trading_price_{current_year - 1}"
            if not self._table_exists(table_name):
                return 0.003  # 默认值

        try:
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute(
                    f"""
                    SELECT AVG(CASE WHEN rrp_aud_mwh > 300 THEN 1.0 ELSE 0.0 END)
                    FROM {table_name}
                    WHERE region_id = ?
                    """,
                    (region,),
                )
                row = cursor.fetchone()
                if row and row[0] is not None:
                    return max(0.0, min(1.0, float(row[0])))
        except Exception:
            pass

        return 0.003

    def _compute_sample_weights(self, records: List[dict]) -> np.ndarray:
        """计算时间衰减样本权重。

        策略:
        - 最近 12 个月: weight = 1.0
        - 12-24 个月: weight = 0.5
        - 24 个月以前: weight = 0.2

        Args:
            records: 记录列表，每条记录包含 'trade_date' 或 'date' 字段（格式 YYYY-MM-DD）

        Returns:
            numpy 数组，长度与 records 相同，每个元素为对应记录的权重
        """
        today = datetime.now()
        weights = np.empty(len(records), dtype=np.float64)

        for i, record in enumerate(records):
            # 支持 'trade_date' 和 'date' 两种字段名
            date_str = record.get("trade_date") or record.get("date", "")
            try:
                record_date = datetime.strptime(date_str, "%Y-%m-%d")
            except (ValueError, TypeError):
                # 无法解析日期时使用最低权重
                weights[i] = 0.2
                continue

            # 计算距今月数（近似：用天数 / 30.44）
            days_diff = (today - record_date).days
            months_diff = days_diff / 30.44

            if months_diff <= 12:
                weights[i] = 1.0
            elif months_diff <= 24:
                weights[i] = 0.5
            else:
                weights[i] = 0.2

        return weights

    def _detect_extrapolation(
        self,
        current_bess_ratio: float,
        train_max_ratio: float,
    ) -> bool:
        """检测 bess_capacity_ratio 是否超出训练集范围。

        Args:
            current_bess_ratio: 当前 BESS 容量比。
            train_max_ratio: 训练集中 bess_capacity_ratio 的最大值。

        Returns:
            True 表示当前值超出训练集范围（外推），需标注 extrapolation_warning。
        """
        return current_bess_ratio > train_max_ratio

    def _compute_regime_indicator(self, bess_ratio: float) -> str:
        """计算渗透率区间标识。

        根据 bess_capacity_ratio 将当前市场状态分为三个区间：
        - low: < 5%（BESS 渗透率低，价差压缩效应弱）
        - medium: 5-15%（中等渗透率，价差开始受压）
        - high: > 15%（高渗透率，价差显著压缩）

        Args:
            bess_ratio: BESS 容量与峰值需求的比值。

        Returns:
            渗透率区间标识字符串："low"、"medium" 或 "high"。
        """
        if bess_ratio < 0.05:
            return "low"
        elif bess_ratio <= 0.15:
            return "medium"
        else:
            return "high"

    def _apply_isotonic_regression(
        self,
        predictions_p10: np.ndarray,
        predictions_p50: np.ndarray,
        predictions_p90: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """Isotonic Regression 后处理消除 quantile crossing。

        对每个样本，将 [P10, P50, P90] 排序以确保 P10 ≤ P50 ≤ P90。
        排序后，若 P90 - P10 < 20 AUD/MWh，则围绕 P50 对称扩展至最小宽度 20。

        Args:
            predictions_p10: P10 分位数预测数组。
            predictions_p50: P50 分位数预测数组。
            predictions_p90: P90 分位数预测数组。

        Returns:
            修正后的 (p10, p50, p90) 数组元组。
        """
        p10 = np.array(predictions_p10, dtype=np.float64)
        p50 = np.array(predictions_p50, dtype=np.float64)
        p90 = np.array(predictions_p90, dtype=np.float64)

        n = len(p10)
        for i in range(n):
            # 排序确保 P10 ≤ P50 ≤ P90
            sorted_vals = sorted([p10[i], p50[i], p90[i]])
            p10[i] = sorted_vals[0]
            p50[i] = sorted_vals[1]
            p90[i] = sorted_vals[2]

            # 检查最小区间宽度
            width = p90[i] - p10[i]
            if width < 20.0:
                # 围绕 P50 对称扩展至最小 20 AUD/MWh
                half_min_width = 10.0
                p10[i] = p50[i] - half_min_width
                p90[i] = p50[i] + half_min_width

        return p10, p50, p90

    def _compute_intraday_features(self, half_hourly_prices: List[float]) -> dict:
        """计算日内价格结构特征。

        从半小时价格序列中提取晚峰-午间价差和早间爬坡价差，
        用于捕获日内价格结构变化趋势。

        Args:
            half_hourly_prices: 单日半小时价格列表（完整日应有 48 个间隔）。
                间隔索引对应时间：index 0 = 00:00-00:30, index 1 = 00:30-01:00, ...

        Returns:
            字典包含:
            - evening_solar_spread: 17:00-21:00 均价 - 10:00-14:00 均价
            - morning_ramp_spread: 06:00-09:00 均价 - 00:00-05:00 均价
            - incomplete_intraday: 数据不完整标记

        Notes:
            - 17:00-21:00 对应 intervals 34-41（8 个间隔）
            - 10:00-14:00 对应 intervals 20-27（8 个间隔）
            - 06:00-09:00 对应 intervals 12-17（6 个间隔）
            - 00:00-05:00 对应 intervals 0-9（10 个间隔）
        """
        if len(half_hourly_prices) < 48:
            return {
                "evening_solar_spread": 0.0,
                "morning_ramp_spread": 0.0,
                "incomplete_intraday": True,
            }

        # evening_solar_spread: avg(17:00-21:00) - avg(10:00-14:00)
        evening_prices = half_hourly_prices[34:42]   # intervals 34-41: 17:00-21:00
        solar_prices = half_hourly_prices[20:28]     # intervals 20-27: 10:00-14:00
        evening_solar_spread = float(
            np.mean(evening_prices) - np.mean(solar_prices)
        )

        # morning_ramp_spread: avg(06:00-09:00) - avg(00:00-05:00)
        morning_prices = half_hourly_prices[12:18]   # intervals 12-17: 06:00-09:00
        overnight_prices = half_hourly_prices[0:10]  # intervals 0-9:  00:00-05:00
        morning_ramp_spread = float(
            np.mean(morning_prices) - np.mean(overnight_prices)
        )

        return {
            "evening_solar_spread": evening_solar_spread,
            "morning_ramp_spread": morning_ramp_spread,
            "incomplete_intraday": False,
        }

    def _compute_pinball_loss(
        self,
        y_true: np.ndarray,
        y_pred: np.ndarray,
        alpha: float,
    ) -> float:
        """计算 pinball loss 指标。

        Pinball loss（又称 quantile loss）衡量分位数预测的准确性。
        公式: pinball = mean(α × max(y_true - y_pred, 0) + (1-α) × max(y_pred - y_true, 0))

        Args:
            y_true: 实际观测值数组。
            y_pred: 分位数预测值数组。
            alpha: 分位数水平，取值范围 (0, 1)。例如 alpha=0.1 对应 P10。

        Returns:
            所有样本的平均 pinball loss 值。
        """
        y_true = np.asarray(y_true, dtype=np.float64)
        y_pred = np.asarray(y_pred, dtype=np.float64)

        residual = y_true - y_pred
        loss = alpha * np.maximum(residual, 0.0) + (1.0 - alpha) * np.maximum(-residual, 0.0)
        return float(np.mean(loss))

    def _sqr_averaging(
        self,
        region_predictions: Dict[str, np.ndarray],
    ) -> np.ndarray:
        """Simple Quantile Regression Averaging 集成预测。

        对多个区域的预测结果取简单平均，作为集成预测值。
        当多个区域的模型可用时，通过平均降低单一区域模型的方差。

        Args:
            region_predictions: 字典，键为区域名称，值为该区域的预测数组。
                所有预测数组应具有相同长度。

        Returns:
            所有区域预测的逐元素平均值数组。
            如果输入为空字典，返回空数组。
        """
        if not region_predictions:
            return np.array([], dtype=np.float64)

        arrays = [np.asarray(arr, dtype=np.float64) for arr in region_predictions.values()]
        stacked = np.stack(arrays, axis=0)
        return np.mean(stacked, axis=0)

    def get_calibration_status(self) -> dict:
        """返回校准状态元数据（含置信区间信息）。"""
        status = self.calibration_metadata.get("status", "not_run")

        # 计算各区域 P10/P50/P90 均值
        confidence_interval = None
        if self.calibrated_params:
            p10_values = []
            p50_values = []
            p90_values = []
            for region in NEM_REGIONS:
                if region in self.calibrated_params:
                    p = self.calibrated_params[region]
                    p50_values.append(p.get("base_spread", 0))
                    p10_values.append(p.get("base_spread_p10", 0))
                    p90_values.append(p.get("base_spread_p90", 0))

            if p50_values:
                confidence_interval = {
                    "p10": round(float(np.mean(p10_values)), 2),
                    "p50": round(float(np.mean(p50_values)), 2),
                    "p90": round(float(np.mean(p90_values)), 2),
                }

        return {
            "status": status,
            "train_period": self.calibration_metadata.get("train_period", "N/A"),
            "validation_period": self.calibration_metadata.get(
                "validation_period", "N/A"
            ),
            "validation_mae": self.calibration_metadata.get("validation_mae"),
            "validation_r2": self.calibration_metadata.get("validation_r2"),
            "direction_accuracy": self.calibration_metadata.get("direction_accuracy"),
            "confidence_interval_coverage": self.calibration_metadata.get(
                "confidence_interval_coverage"
            ),
            "confidence_interval": confidence_interval,
            "calibrated_at": self.calibration_metadata.get("calibrated_at"),
            "sample_count": self.calibration_metadata.get("sample_count", 0),
        }
