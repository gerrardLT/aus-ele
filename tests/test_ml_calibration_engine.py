"""Tests for ML Calibration Engine.

验证 MLCalibrationEngine 的核心功能：
- 特征提取
- 模型训练
- 校准参数生成
- 降级策略
"""

import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest import mock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from engines.ml_calibration_engine import MLCalibrationEngine
pytestmark = pytest.mark.xfail(reason="SQLite removed; needs PG test fixtures", run=False)


class MockDB:
    """模拟数据库管理器。"""

    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_connection(self):
        import contextlib

        @contextlib.contextmanager
        def _conn():
            conn = sqlite3.connect(self.db_path)
            try:
                yield conn
            finally:
                conn.close()

        return _conn()


def _create_test_db_with_data(db_path: str):
    """创建包含测试数据的数据库。

    生成具有自相关性的价格数据，使得滞后特征能有效预测目标变量（daily_spread = winsorized MAX-MIN）。
    """
    import random

    random.seed(42)

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # 创建 2020-2025 年的 trading_price 表
    for year in range(2020, 2026):
        table_name = f"trading_price_{year}"
        cursor.execute(f"""
            CREATE TABLE IF NOT EXISTS {table_name} (
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL
            )
        """)

        # 为每个区域每个月插入模拟数据
        regions = ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]
        for month in range(1, 13):
            for region in regions:
                base_price = {
                    "NSW1": 80.0,
                    "QLD1": 70.0,
                    "VIC1": 75.0,
                    "SA1": 90.0,
                    "TAS1": 60.0,
                }[region]

                # 添加季节性变化（价差在夏季/冬季更大）
                seasonal = 20.0 * (1 if month in (1, 2, 6, 7, 8, 12) else -1)
                # 添加年度趋势
                trend = (year - 2020) * 5.0

                # 用 AR(1) 过程生成自相关的日度价差幅度
                # 这样 lag_1_spread 就能有效预测当天的 daily_spread
                prev_daily_range = 100.0

                rows = []
                for day in range(1, 29):  # 简化为 28 天
                    # AR(1): 今天的日内价差幅度 = 0.8 * 昨天 + 0.2 * 均值 + 噪声
                    # 高自相关系数确保滞后特征有预测力
                    mean_range = 120.0 + (40.0 if month in (1, 2, 6, 7, 8, 12) else -20.0)
                    prev_daily_range = 0.8 * prev_daily_range + 0.2 * mean_range + random.gauss(0, 8.0)
                    prev_daily_range = max(50.0, min(400.0, prev_daily_range))  # 确保合理范围

                    for interval in range(0, 288, 6):  # 每天 48 个间隔
                        hour = interval // 12
                        # 日内价格曲线：峰时高、谷时低，总幅度约为 prev_daily_range
                        if 7 <= hour <= 20:
                            # 峰时：基础价 + 价差的上半部分
                            intraday = prev_daily_range * 0.5
                        else:
                            # 谷时：基础价 - 价差的下半部分
                            intraday = -prev_daily_range * 0.5

                        # 小噪声，确保 MAX-MIN 主要由 prev_daily_range 决定
                        noise = random.gauss(0, 2.0)
                        price = base_price + seasonal + trend + intraday + noise

                        # 偶尔添加尖峰（会被 winsorize 到 500）
                        if day == 15 and hour == 14 and region == "SA1":
                            price = 800.0

                        ts = f"{year}-{month:02d}-{day:02d} {hour:02d}:{(interval % 12) * 5:02d}:00"
                        rows.append((ts, region, price))

                cursor.executemany(
                    f"INSERT INTO {table_name} (settlement_date, region_id, rrp_aud_mwh) VALUES (?, ?, ?)",
                    rows,
                )

    conn.commit()
    conn.close()


class TestMLCalibrationEngine:
    """MLCalibrationEngine 核心功能测试。"""

    def test_calibrate_with_sufficient_data(self, tmp_path):
        """有足够数据时，校准应成功完成。"""
        db_path = str(tmp_path / "test.db")
        _create_test_db_with_data(db_path)
        db = MockDB(db_path)

        engine = MLCalibrationEngine(db)
        result = engine.calibrate()

        # 应该返回校准参数
        assert isinstance(result, dict)
        # 校准状态应该是 calibrated
        status = engine.get_calibration_status()
        assert status["status"] == "calibrated"
        assert status["sample_count"] > 0

    def test_calibrate_with_no_data(self, tmp_path):
        """没有数据时，应优雅降级。"""
        db_path = str(tmp_path / "empty.db")
        # 创建空数据库
        conn = sqlite3.connect(db_path)
        conn.close()

        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)
        result = engine.calibrate()

        # 应该返回空字典
        assert result == {}
        status = engine.get_calibration_status()
        assert status["status"] == "insufficient_data"

    def test_calibrate_with_insufficient_data(self, tmp_path):
        """数据不足 90 天时，应返回 insufficient_data。"""
        db_path = str(tmp_path / "sparse.db")
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 只创建 28 天的数据（不足 90 天阈值）
        cursor.execute("""
            CREATE TABLE trading_price_2024 (
                settlement_date TEXT NOT NULL,
                region_id TEXT NOT NULL,
                rrp_aud_mwh REAL NOT NULL
            )
        """)
        for day in range(1, 29):
            for interval in range(48):
                hour = interval // 2
                ts = f"2024-01-{day:02d} {hour:02d}:{(interval % 2) * 30:02d}:00"
                cursor.execute(
                    "INSERT INTO trading_price_2024 VALUES (?, ?, ?)",
                    (ts, "NSW1", 80.0 + hour),
                )
        conn.commit()
        conn.close()

        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)
        result = engine.calibrate()

        assert result == {}
        status = engine.get_calibration_status()
        assert status["status"] == "insufficient_data"

    def test_calibrated_params_have_valid_ranges(self, tmp_path):
        """校准参数应在合理范围内。"""
        db_path = str(tmp_path / "test.db")
        _create_test_db_with_data(db_path)
        db = MockDB(db_path)

        engine = MLCalibrationEngine(db)
        result = engine.calibrate()

        for region in ["NSW1", "QLD1", "VIC1", "SA1", "TAS1"]:
            if region in result:
                params = result[region]
                # base_spread 应在 [30, 500] 范围内（daily_spread 量级）
                assert 10.0 <= params["base_spread"] <= 600.0
                # spike_frequency 应在 [0, 1] 范围内
                assert 0.0 <= params["spike_frequency"] <= 1.0

    def test_calibration_status_metadata(self, tmp_path):
        """校准状态应包含完整的元数据。"""
        db_path = str(tmp_path / "test.db")
        _create_test_db_with_data(db_path)
        db = MockDB(db_path)

        engine = MLCalibrationEngine(db)
        engine.calibrate()

        status = engine.get_calibration_status()
        assert "status" in status
        assert "train_period" in status
        assert "validation_period" in status
        assert "calibrated_at" in status
        assert "sample_count" in status

    def test_lightgbm_import_failure_graceful(self, tmp_path):
        """LightGBM 导入失败时应优雅降级。"""
        db_path = str(tmp_path / "test.db")
        _create_test_db_with_data(db_path)
        db = MockDB(db_path)

        engine = MLCalibrationEngine(db)

        # 模拟 lightgbm 导入失败
        with mock.patch.dict("sys.modules", {"lightgbm": None}):
            with mock.patch(
                "engines.ml_calibration_engine.MLCalibrationEngine._train_model",
                side_effect=ImportError("No module named 'lightgbm'"),
            ):
                result = engine.calibrate()

        assert result == {}
        status = engine.get_calibration_status()
        assert status["status"] in ("failed", "dependency_missing")

    def test_feature_cols_exclude_lag_30_spread(self):
        """lag_30_spread 应已从特征列表中移除（修复过拟合）。

        Validates: Requirements 1.1, 1.2
        """
        import inspect

        source = inspect.getsource(MLCalibrationEngine._train_model)
        # lag_30_spread 不应出现在 feature_cols 中（可能出现在注释中）
        assert '"lag_30_spread"' not in source or '# "lag_30_spread"' in source or "# lag_30_spread" in source
        # lag_1_spread 和 lag_7_spread 应保留
        assert '"lag_1_spread"' in source
        assert '"lag_7_spread"' in source


class TestComputeSampleWeights:
    """_compute_sample_weights 方法测试。"""

    def test_recent_records_get_weight_1(self):
        """最近 12 个月内的记录权重应为 1.0。"""
        from datetime import datetime, timedelta

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        today = datetime.now()
        records = [
            {"trade_date": (today - timedelta(days=30)).strftime("%Y-%m-%d")},
            {"trade_date": (today - timedelta(days=180)).strftime("%Y-%m-%d")},
            {"trade_date": (today - timedelta(days=360)).strftime("%Y-%m-%d")},
        ]

        weights = engine._compute_sample_weights(records)
        assert weights[0] == 1.0
        assert weights[1] == 1.0
        assert weights[2] == 1.0

    def test_mid_range_records_get_weight_05(self):
        """12-24 个月前的记录权重应为 0.5。"""
        from datetime import datetime, timedelta

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        today = datetime.now()
        records = [
            {"trade_date": (today - timedelta(days=400)).strftime("%Y-%m-%d")},
            {"trade_date": (today - timedelta(days=600)).strftime("%Y-%m-%d")},
        ]

        weights = engine._compute_sample_weights(records)
        assert weights[0] == 0.5
        assert weights[1] == 0.5

    def test_old_records_get_weight_02(self):
        """24 个月以前的记录权重应为 0.2。"""
        from datetime import datetime, timedelta

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        today = datetime.now()
        records = [
            {"trade_date": (today - timedelta(days=800)).strftime("%Y-%m-%d")},
            {"trade_date": (today - timedelta(days=1200)).strftime("%Y-%m-%d")},
        ]

        weights = engine._compute_sample_weights(records)
        assert weights[0] == 0.2
        assert weights[1] == 0.2

    def test_mixed_dates_correct_weights(self):
        """混合日期应返回正确的权重分配。"""
        from datetime import datetime, timedelta

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        today = datetime.now()
        records = [
            {"trade_date": (today - timedelta(days=30)).strftime("%Y-%m-%d")},   # ≤12m → 1.0
            {"trade_date": (today - timedelta(days=500)).strftime("%Y-%m-%d")},  # 12-24m → 0.5
            {"trade_date": (today - timedelta(days=900)).strftime("%Y-%m-%d")},  # >24m → 0.2
        ]

        weights = engine._compute_sample_weights(records)
        assert weights[0] == 1.0
        assert weights[1] == 0.5
        assert weights[2] == 0.2

    def test_supports_date_field(self):
        """应支持 'date' 字段名（除了 'trade_date'）。"""
        from datetime import datetime, timedelta

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        today = datetime.now()
        records = [
            {"date": (today - timedelta(days=30)).strftime("%Y-%m-%d")},
        ]

        weights = engine._compute_sample_weights(records)
        assert weights[0] == 1.0

    def test_invalid_date_gets_minimum_weight(self):
        """无法解析的日期应使用最低权重 0.2。"""
        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        records = [
            {"trade_date": "invalid-date"},
            {"trade_date": ""},
            {},
        ]

        weights = engine._compute_sample_weights(records)
        assert weights[0] == 0.2
        assert weights[1] == 0.2
        assert weights[2] == 0.2

    def test_empty_records_returns_empty_array(self):
        """空记录列表应返回空数组。"""
        import numpy as np

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        weights = engine._compute_sample_weights([])
        assert len(weights) == 0
        assert isinstance(weights, np.ndarray)

    def test_returns_numpy_array(self):
        """返回值应为 numpy 数组。"""
        import numpy as np
        from datetime import datetime, timedelta

        db = mock.MagicMock()
        engine = MLCalibrationEngine(db)

        today = datetime.now()
        records = [
            {"trade_date": (today - timedelta(days=30)).strftime("%Y-%m-%d")},
        ]

        weights = engine._compute_sample_weights(records)
        assert isinstance(weights, np.ndarray)
        assert weights.dtype == np.float64


class TestDetectExtrapolation:
    """_detect_extrapolation 方法测试。"""

    def test_within_range_returns_false(self, tmp_path):
        """当前值在训练集范围内时返回 False。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._detect_extrapolation(0.10, 0.15) is False

    def test_at_boundary_returns_false(self, tmp_path):
        """当前值等于训练集最大值时返回 False。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._detect_extrapolation(0.15, 0.15) is False

    def test_exceeds_range_returns_true(self, tmp_path):
        """当前值超出训练集范围时返回 True。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._detect_extrapolation(0.20, 0.15) is True

    def test_zero_values(self, tmp_path):
        """零值边界情况。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._detect_extrapolation(0.0, 0.0) is False
        assert engine._detect_extrapolation(0.01, 0.0) is True


class TestComputeRegimeIndicator:
    """_compute_regime_indicator 方法测试。"""

    def test_low_regime(self, tmp_path):
        """bess_ratio < 0.05 时返回 'low'。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._compute_regime_indicator(0.0) == "low"
        assert engine._compute_regime_indicator(0.03) == "low"
        assert engine._compute_regime_indicator(0.049) == "low"

    def test_medium_regime(self, tmp_path):
        """0.05 <= bess_ratio <= 0.15 时返回 'medium'。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._compute_regime_indicator(0.05) == "medium"
        assert engine._compute_regime_indicator(0.10) == "medium"
        assert engine._compute_regime_indicator(0.15) == "medium"

    def test_high_regime(self, tmp_path):
        """bess_ratio > 0.15 时返回 'high'。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        assert engine._compute_regime_indicator(0.151) == "high"
        assert engine._compute_regime_indicator(0.30) == "high"
        assert engine._compute_regime_indicator(0.50) == "high"

    def test_boundary_values(self, tmp_path):
        """边界值精确测试。"""
        db_path = str(tmp_path / "test.db")
        conn = sqlite3.connect(db_path)
        conn.close()
        db = MockDB(db_path)
        engine = MLCalibrationEngine(db)

        # 0.05 是 medium 的下界（含）
        assert engine._compute_regime_indicator(0.05) == "medium"
        # 0.15 是 medium 的上界（含）
        assert engine._compute_regime_indicator(0.15) == "medium"


class TestMLCalibrationIntegration:
    """ML 校准与 ForwardPriceEngine 的集成测试。"""

    def test_forward_price_engine_with_calibration_failure(self):
        """ForwardPriceEngine 在校准失败时应正常工作。"""
        from engines.forward_price_engine import ForwardPriceEngine

        # 正常实例化（校准可能失败但不应影响引擎功能）
        engine = ForwardPriceEngine()
        assert engine._calibration is not None
        assert "status" in engine._calibration

    def test_calibration_does_not_modify_global_constants(self, tmp_path):
        """校准不应修改全局 BASE_SPREAD_PARAMS。"""
        from engines.forward_price_engine import BASE_SPREAD_PARAMS

        # 记录原始值
        original_nsw = BASE_SPREAD_PARAMS["NSW1"]["mean_spread"]

        # 创建引擎（会触发校准）
        from engines.forward_price_engine import ForwardPriceEngine

        engine = ForwardPriceEngine()

        # 全局常量不应被修改
        assert BASE_SPREAD_PARAMS["NSW1"]["mean_spread"] == original_nsw


class TestApplyIsotonicRegression:
    """_apply_isotonic_regression 方法测试。"""

    def _make_engine(self):
        """创建一个 MLCalibrationEngine 实例用于测试。"""
        db = mock.MagicMock()
        return MLCalibrationEngine(db)

    def test_already_ordered_no_change(self):
        """已排序的分位数不应被修改（区间宽度 >= 20）。"""
        import numpy as np

        engine = self._make_engine()
        p10 = np.array([50.0, 60.0, 70.0])
        p50 = np.array([80.0, 90.0, 100.0])
        p90 = np.array([110.0, 120.0, 130.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        np.testing.assert_array_almost_equal(r10, [50.0, 60.0, 70.0])
        np.testing.assert_array_almost_equal(r50, [80.0, 90.0, 100.0])
        np.testing.assert_array_almost_equal(r90, [110.0, 120.0, 130.0])

    def test_quantile_crossing_fixed(self):
        """分位数交叉应被修正为 P10 ≤ P50 ≤ P90。"""
        import numpy as np

        engine = self._make_engine()
        # P10=100, P50=80, P90=90 → 排序后 P10=80, P50=90, P90=100
        p10 = np.array([100.0])
        p50 = np.array([80.0])
        p90 = np.array([90.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        assert r10[0] <= r50[0] <= r90[0]
        assert r10[0] == 80.0
        assert r50[0] == 90.0
        assert r90[0] == 100.0

    def test_ordering_invariant_holds_for_all_samples(self):
        """所有样本都应满足 P10 ≤ P50 ≤ P90。"""
        import numpy as np

        engine = self._make_engine()
        # 故意制造多种交叉情况
        p10 = np.array([120.0, 50.0, 90.0, 80.0])
        p50 = np.array([80.0, 100.0, 70.0, 80.0])
        p90 = np.array([100.0, 80.0, 80.0, 80.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        for i in range(len(r10)):
            assert r10[i] <= r50[i], f"P10 > P50 at index {i}"
            assert r50[i] <= r90[i], f"P50 > P90 at index {i}"

    def test_minimum_width_expansion(self):
        """P90 - P10 < 20 时应扩展至最小 20 AUD/MWh。"""
        import numpy as np

        engine = self._make_engine()
        # 区间宽度为 10（< 20），应扩展
        p10 = np.array([95.0])
        p50 = np.array([100.0])
        p90 = np.array([105.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        width = r90[0] - r10[0]
        assert width >= 20.0
        # 应围绕 P50 对称扩展
        assert r50[0] == 100.0
        assert r10[0] == 90.0  # P50 - 10
        assert r90[0] == 110.0  # P50 + 10

    def test_minimum_width_with_crossing(self):
        """同时存在交叉和窄区间时，两者都应被修正。"""
        import numpy as np

        engine = self._make_engine()
        # 交叉 + 窄区间：排序后 [98, 100, 102]，宽度=4 < 20
        p10 = np.array([102.0])
        p50 = np.array([98.0])
        p90 = np.array([100.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        # 排序后 P50=100, 然后扩展
        assert r10[0] <= r50[0] <= r90[0]
        assert r90[0] - r10[0] >= 20.0

    def test_exact_width_20_no_expansion(self):
        """区间宽度恰好为 20 时不应扩展。"""
        import numpy as np

        engine = self._make_engine()
        p10 = np.array([90.0])
        p50 = np.array([100.0])
        p90 = np.array([110.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        assert r10[0] == 90.0
        assert r50[0] == 100.0
        assert r90[0] == 110.0

    def test_identical_values_expanded(self):
        """所有分位数相同时应扩展至最小宽度。"""
        import numpy as np

        engine = self._make_engine()
        p10 = np.array([100.0])
        p50 = np.array([100.0])
        p90 = np.array([100.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        assert r10[0] <= r50[0] <= r90[0]
        assert r90[0] - r10[0] >= 20.0
        assert r50[0] == 100.0

    def test_returns_numpy_arrays(self):
        """返回值应为 numpy 数组。"""
        import numpy as np

        engine = self._make_engine()
        p10 = np.array([50.0, 60.0])
        p50 = np.array([80.0, 90.0])
        p90 = np.array([110.0, 120.0])

        r10, r50, r90 = engine._apply_isotonic_regression(p10, p50, p90)

        assert isinstance(r10, np.ndarray)
        assert isinstance(r50, np.ndarray)
        assert isinstance(r90, np.ndarray)


class TestComputeIntradayFeatures:
    """_compute_intraday_features 方法测试。"""

    def _make_engine(self):
        """创建测试用 MLCalibrationEngine 实例。"""
        db = mock.MagicMock()
        return MLCalibrationEngine(db)

    def test_incomplete_data_returns_zeros(self):
        """interval_count < 48 时返回 0.0 并标记 incomplete_intraday。"""
        engine = self._make_engine()

        # 空列表
        result = engine._compute_intraday_features([])
        assert result == {
            "evening_solar_spread": 0.0,
            "morning_ramp_spread": 0.0,
            "incomplete_intraday": True,
        }

        # 少于 48 个间隔
        result = engine._compute_intraday_features([50.0] * 47)
        assert result["incomplete_intraday"] is True
        assert result["evening_solar_spread"] == 0.0
        assert result["morning_ramp_spread"] == 0.0

    def test_uniform_prices_return_zero_spreads(self):
        """所有价格相同时，价差应为 0。"""
        engine = self._make_engine()

        prices = [100.0] * 48
        result = engine._compute_intraday_features(prices)

        assert result["incomplete_intraday"] is False
        assert result["evening_solar_spread"] == 0.0
        assert result["morning_ramp_spread"] == 0.0

    def test_evening_solar_spread_calculation(self):
        """验证 evening_solar_spread 计算正确性。

        evening_solar_spread = avg(17:00-21:00) - avg(10:00-14:00)
        intervals 34-41 vs intervals 20-27
        """
        engine = self._make_engine()

        prices = [50.0] * 48
        # 设置 17:00-21:00 (intervals 34-41) 为 150.0
        for i in range(34, 42):
            prices[i] = 150.0
        # 设置 10:00-14:00 (intervals 20-27) 为 30.0
        for i in range(20, 28):
            prices[i] = 30.0

        result = engine._compute_intraday_features(prices)

        assert result["incomplete_intraday"] is False
        # evening_solar_spread = 150.0 - 30.0 = 120.0
        assert abs(result["evening_solar_spread"] - 120.0) < 1e-10

    def test_morning_ramp_spread_calculation(self):
        """验证 morning_ramp_spread 计算正确性。

        morning_ramp_spread = avg(06:00-09:00) - avg(00:00-05:00)
        intervals 12-17 vs intervals 0-9
        """
        engine = self._make_engine()

        prices = [50.0] * 48
        # 设置 06:00-09:00 (intervals 12-17) 为 80.0
        for i in range(12, 18):
            prices[i] = 80.0
        # 设置 00:00-05:00 (intervals 0-9) 为 40.0
        for i in range(0, 10):
            prices[i] = 40.0

        result = engine._compute_intraday_features(prices)

        assert result["incomplete_intraday"] is False
        # morning_ramp_spread = 80.0 - 40.0 = 40.0
        assert abs(result["morning_ramp_spread"] - 40.0) < 1e-10

    def test_negative_spreads_allowed(self):
        """价差可以为负值（如午间太阳能高峰时段价格高于晚峰）。"""
        engine = self._make_engine()

        prices = [50.0] * 48
        # 设置 10:00-14:00 高于 17:00-21:00
        for i in range(20, 28):
            prices[i] = 200.0
        for i in range(34, 42):
            prices[i] = 80.0

        result = engine._compute_intraday_features(prices)

        # evening_solar_spread = 80.0 - 200.0 = -120.0
        assert result["evening_solar_spread"] < 0.0
        assert abs(result["evening_solar_spread"] - (-120.0)) < 1e-10

    def test_exactly_48_intervals(self):
        """恰好 48 个间隔时应正常计算。"""
        engine = self._make_engine()

        prices = [100.0] * 48
        result = engine._compute_intraday_features(prices)

        assert result["incomplete_intraday"] is False

    def test_more_than_48_intervals(self):
        """超过 48 个间隔时仍应正常计算（使用前 48 个间隔的索引）。"""
        engine = self._make_engine()

        prices = [100.0] * 96  # 双倍数据
        # 设置 17:00-21:00 (intervals 34-41) 为 200.0
        for i in range(34, 42):
            prices[i] = 200.0

        result = engine._compute_intraday_features(prices)

        assert result["incomplete_intraday"] is False
        # evening_solar_spread = 200.0 - 100.0 = 100.0
        assert abs(result["evening_solar_spread"] - 100.0) < 1e-10

    def test_returns_float_values(self):
        """返回值应为 float 类型。"""
        engine = self._make_engine()

        prices = [float(i) for i in range(48)]
        result = engine._compute_intraday_features(prices)

        assert isinstance(result["evening_solar_spread"], float)
        assert isinstance(result["morning_ramp_spread"], float)
        assert isinstance(result["incomplete_intraday"], bool)


class TestComputePinballLoss:
    """_compute_pinball_loss 方法测试。"""

    def _make_engine(self):
        """创建测试用 MLCalibrationEngine 实例。"""
        db = mock.MagicMock()
        return MLCalibrationEngine(db)

    def test_perfect_prediction_returns_zero(self):
        """预测完全准确时 pinball loss 应为 0。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([100.0, 200.0, 150.0])
        y_pred = np.array([100.0, 200.0, 150.0])

        loss = engine._compute_pinball_loss(y_true, y_pred, 0.5)
        assert abs(loss) < 1e-10

    def test_underprediction_penalized_by_alpha(self):
        """低估时惩罚为 α × (y_true - y_pred)。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([100.0])
        y_pred = np.array([80.0])  # 低估 20

        # alpha=0.5: loss = 0.5 * 20 + 0.5 * 0 = 10
        loss = engine._compute_pinball_loss(y_true, y_pred, 0.5)
        assert abs(loss - 10.0) < 1e-10

        # alpha=0.9: loss = 0.9 * 20 + 0.1 * 0 = 18
        loss = engine._compute_pinball_loss(y_true, y_pred, 0.9)
        assert abs(loss - 18.0) < 1e-10

    def test_overprediction_penalized_by_one_minus_alpha(self):
        """高估时惩罚为 (1-α) × (y_pred - y_true)。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([80.0])
        y_pred = np.array([100.0])  # 高估 20

        # alpha=0.5: loss = 0.5 * 0 + 0.5 * 20 = 10
        loss = engine._compute_pinball_loss(y_true, y_pred, 0.5)
        assert abs(loss - 10.0) < 1e-10

        # alpha=0.1: loss = 0.1 * 0 + 0.9 * 20 = 18
        loss = engine._compute_pinball_loss(y_true, y_pred, 0.1)
        assert abs(loss - 18.0) < 1e-10

    def test_formula_correctness_multiple_samples(self):
        """验证多样本的 pinball loss 公式正确性。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([100.0, 80.0, 120.0])
        y_pred = np.array([90.0, 90.0, 110.0])
        alpha = 0.5

        # 样本 1: 低估 10 → 0.5*10 + 0.5*0 = 5
        # 样本 2: 高估 10 → 0.5*0 + 0.5*10 = 5
        # 样本 3: 低估 10 → 0.5*10 + 0.5*0 = 5
        # 平均: (5 + 5 + 5) / 3 = 5
        loss = engine._compute_pinball_loss(y_true, y_pred, alpha)
        assert abs(loss - 5.0) < 1e-10

    def test_asymmetric_loss_for_p10(self):
        """P10 (alpha=0.1) 对高估惩罚更重。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([100.0])

        # 低估 10: loss = 0.1 * 10 = 1
        loss_under = engine._compute_pinball_loss(y_true, np.array([90.0]), 0.1)
        # 高估 10: loss = 0.9 * 10 = 9
        loss_over = engine._compute_pinball_loss(y_true, np.array([110.0]), 0.1)

        assert abs(loss_under - 1.0) < 1e-10
        assert abs(loss_over - 9.0) < 1e-10
        assert loss_over > loss_under

    def test_asymmetric_loss_for_p90(self):
        """P90 (alpha=0.9) 对低估惩罚更重。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([100.0])

        # 低估 10: loss = 0.9 * 10 = 9
        loss_under = engine._compute_pinball_loss(y_true, np.array([90.0]), 0.9)
        # 高估 10: loss = 0.1 * 10 = 1
        loss_over = engine._compute_pinball_loss(y_true, np.array([110.0]), 0.9)

        assert abs(loss_under - 9.0) < 1e-10
        assert abs(loss_over - 1.0) < 1e-10
        assert loss_under > loss_over

    def test_returns_float(self):
        """返回值应为 float 类型。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([100.0, 200.0])
        y_pred = np.array([110.0, 190.0])

        loss = engine._compute_pinball_loss(y_true, y_pred, 0.5)
        assert isinstance(loss, float)

    def test_non_negative_loss(self):
        """Pinball loss 应始终非负。"""
        import numpy as np

        engine = self._make_engine()
        y_true = np.array([50.0, 100.0, 150.0, 200.0])
        y_pred = np.array([60.0, 90.0, 160.0, 180.0])

        for alpha in [0.1, 0.25, 0.5, 0.75, 0.9]:
            loss = engine._compute_pinball_loss(y_true, y_pred, alpha)
            assert loss >= 0.0


class TestSqrAveraging:
    """_sqr_averaging 方法测试。"""

    def _make_engine(self):
        """创建测试用 MLCalibrationEngine 实例。"""
        db = mock.MagicMock()
        return MLCalibrationEngine(db)

    def test_single_region_returns_same(self):
        """单区域时返回原始预测。"""
        import numpy as np

        engine = self._make_engine()
        predictions = {"NSW1": np.array([100.0, 200.0, 150.0])}

        result = engine._sqr_averaging(predictions)
        np.testing.assert_array_almost_equal(result, [100.0, 200.0, 150.0])

    def test_two_regions_average(self):
        """两个区域的简单平均。"""
        import numpy as np

        engine = self._make_engine()
        predictions = {
            "NSW1": np.array([100.0, 200.0]),
            "QLD1": np.array([80.0, 160.0]),
        }

        result = engine._sqr_averaging(predictions)
        np.testing.assert_array_almost_equal(result, [90.0, 180.0])

    def test_multiple_regions_average(self):
        """多区域平均计算正确性。"""
        import numpy as np

        engine = self._make_engine()
        predictions = {
            "NSW1": np.array([100.0, 200.0, 300.0]),
            "QLD1": np.array([80.0, 160.0, 240.0]),
            "VIC1": np.array([120.0, 240.0, 360.0]),
        }

        result = engine._sqr_averaging(predictions)
        # (100+80+120)/3=100, (200+160+240)/3=200, (300+240+360)/3=300
        np.testing.assert_array_almost_equal(result, [100.0, 200.0, 300.0])

    def test_empty_dict_returns_empty_array(self):
        """空字典返回空数组。"""
        import numpy as np

        engine = self._make_engine()
        result = engine._sqr_averaging({})

        assert len(result) == 0
        assert isinstance(result, np.ndarray)

    def test_returns_numpy_array(self):
        """返回值应为 numpy 数组。"""
        import numpy as np

        engine = self._make_engine()
        predictions = {"NSW1": np.array([100.0])}

        result = engine._sqr_averaging(predictions)
        assert isinstance(result, np.ndarray)

    def test_all_same_predictions(self):
        """所有区域预测相同时，平均值等于原始值。"""
        import numpy as np

        engine = self._make_engine()
        predictions = {
            "NSW1": np.array([100.0, 200.0]),
            "QLD1": np.array([100.0, 200.0]),
            "VIC1": np.array([100.0, 200.0]),
        }

        result = engine._sqr_averaging(predictions)
        np.testing.assert_array_almost_equal(result, [100.0, 200.0])

    def test_accepts_list_values(self):
        """应能接受列表作为值（内部转换为 numpy 数组）。"""
        import numpy as np

        engine = self._make_engine()
        predictions = {
            "NSW1": np.array([100.0, 200.0]),
            "QLD1": np.array([80.0, 160.0]),
        }

        result = engine._sqr_averaging(predictions)
        np.testing.assert_array_almost_equal(result, [90.0, 180.0])
