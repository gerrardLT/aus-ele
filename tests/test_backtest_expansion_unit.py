"""Unit / example tests for Backtest Expansion MVP (非属性测试).

覆盖 tasks.md 中以下四个示例 / 单元测试子任务：

- 任务 2.8：MonthlyBenchmarkCalculator 错误处理边界 (Req 9.1, 9.2, 9.3, 9.5)
- 任务 4.8：CaptureRateCalculator 告警边界 (Req 4.4)
- 任务 6.5：ForwardPriceEngine 月度验证委托方法接口 (Req 2.1, 2.5, 8.5)
- 任务 7.4：reconciliation 归档格式与告警边界 (Req 5.5, 6.1, 6.3, 6.4)

所有写盘测试均使用 ``tmp_path`` 隔离，绝不触碰真实
``reports/monthly_reconciliation.json``。与既有 12 条属性测试
(``tests/test_backtest_expansion_properties.py``) 互补，验证具体示例与边界场景。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import json
import logging
from pathlib import Path

import pytest

import engines.backtest_expansion as bx
from engines.backtest_expansion import (
    MonthlyBenchmarkCalculator,
    CaptureRateCalculator,
    MonthlyBenchmark,
    CaptureRateResult,
    CaptureRateComparison,
    MonthlyValidationResult,
    DEVIATION_ALERT_THRESHOLD_PCT,
    is_deviation_alert,
    validate_against_monthly_benchmarks_impl,
    run_monthly_reconciliation,
    _load_existing_records,
    _write_reconciliation_record,
    _reconciliation_report_path,
)


# Real AEMO database path; used to skip engine-delegation tests when absent.
_REAL_DB_PATH = Path(__file__).resolve().parent.parent / "data" / "aemo_data.db"


# ---------------------------------------------------------------------------
# 辅助：构造最小临时 AEMO db (已废弃 - PG only)
# ---------------------------------------------------------------------------


def _make_temp_db(tmp_path, rows, table="trading_price_2024"):
    """DEPRECATED: 已迁移到 PG，此辅助函数不再使用。"""
    raise NotImplementedError("SQLite no longer supported; use PG test fixtures")


def _day_rows(day, region, n=288, base_price=50.0):
    """生成单日 ``n`` 个 5 分钟 interval 行（价格围绕 base_price 上下浮动）。"""
    rows = []
    for i in range(n):
        hh = (i * 5) // 60
        mm = (i * 5) % 60
        ts = f"{day} {hh:02d}:{mm:02d}:00"
        # 价格随时段波动，确保有非零价差
        price = base_price + (i % 24) * 2.0
        rows.append((ts, region, price))
    return rows


# ===========================================================================
# 任务 1.2：dataclass schema 与模块存在性 (Req 1.6, 2.5, 8.5)
# ===========================================================================


class TestDataclassSchema:
    """四个 dataclass 字段齐全、类型正确，模块可被 import (Req 1.6, 2.5, 8.5)。"""

    def test_module_importable(self):
        """backtest_expansion 模块可被正常 import（Req 8.5）。"""
        assert bx is not None
        assert hasattr(bx, "MonthlyBenchmarkCalculator")
        assert hasattr(bx, "CaptureRateCalculator")

    def test_monthly_benchmark_fields(self):
        """MonthlyBenchmark 字段齐全且构造 / 取值正确（Req 1.6）。"""
        from dataclasses import fields, is_dataclass

        assert is_dataclass(MonthlyBenchmark)
        names = {f.name for f in fields(MonthlyBenchmark)}
        assert names == {
            "region",
            "year_month",
            "mean_spread_aud_mwh",
            "sample_days",
            "data_quality_flag",
        }
        b = MonthlyBenchmark("NSW1", "2024-01", 123.4, 25, "ok")
        assert b.region == "NSW1"
        assert b.mean_spread_aud_mwh == 123.4
        assert b.sample_days == 25
        assert b.data_quality_flag == "ok"

    def test_capture_rate_result_fields(self):
        """CaptureRateResult 字段齐全（Req 3）。"""
        from dataclasses import fields, is_dataclass

        assert is_dataclass(CaptureRateResult)
        names = {f.name for f in fields(CaptureRateResult)}
        assert names == {
            "region",
            "year_month",
            "monthly_actual_revenue",
            "perfect_foresight_capture_rate",
            "capped",
            "sample_days",
        }
        r = CaptureRateResult("SA1", "2024-02", 1000.0, 0.78, False, 28)
        assert r.capped is False
        assert r.perfect_foresight_capture_rate == 0.78

    def test_capture_rate_comparison_fields(self):
        """CaptureRateComparison 字段齐全，efficiency_ratio 允许 None（Req 4）。"""
        from dataclasses import fields, is_dataclass

        assert is_dataclass(CaptureRateComparison)
        names = {f.name for f in fields(CaptureRateComparison)}
        assert names == {
            "region",
            "year_month",
            "model_capture_rate",
            "perfect_foresight_capture_rate",
            "efficiency_ratio",
            "violation",
            "low_efficiency_warning",
        }
        c = CaptureRateComparison("QLD1", "2024-03", 0.5, 0.8, None, True, False)
        assert c.efficiency_ratio is None
        assert c.violation is True

    def test_monthly_validation_result_fields(self):
        """MonthlyValidationResult 字段齐全（Req 2.5 兼容字段）。"""
        from dataclasses import fields, is_dataclass

        assert is_dataclass(MonthlyValidationResult)
        names = {f.name for f in fields(MonthlyValidationResult)}
        assert names == {
            "region",
            "year_month",
            "model_mean_spread",
            "benchmark_mean_spread",
            "deviation_pct",
        }
        v = MonthlyValidationResult("VIC1", "2024-04", 100.0, 110.0, -9.09)
        assert v.benchmark_mean_spread == 110.0


# ===========================================================================
# 任务 2.8：MonthlyBenchmarkCalculator 错误处理边界 (Req 9.1, 9.2, 9.3, 9.5)
# ===========================================================================


@pytest.mark.xfail(reason="SQLite removed; needs PG test fixtures", run=False)
class TestMonthlyBenchmarkErrorHandling:
    """月度基准计算器的优雅降级与边界场景 (Req 9)。"""

    def test_nonexistent_db_compute_all_returns_empty(self, tmp_path):
        """Req 9.1：不存在的 db 路径 → compute_all_benchmarks 返回 []，不抛异常。"""
        missing = str(tmp_path / "does_not_exist.db")
        calc = MonthlyBenchmarkCalculator(db_path=missing)
        assert calc.compute_all_benchmarks() == []

    def test_nonexistent_db_compute_monthly_returns_none(self, tmp_path):
        """Req 9.1：不存在的 db 路径 → compute_monthly_benchmark 返回 None。"""
        missing = str(tmp_path / "does_not_exist.db")
        calc = MonthlyBenchmarkCalculator(db_path=missing)
        assert calc.compute_monthly_benchmark("NSW1", "2024-01") is None

    def test_missing_table_year_returns_none(self, tmp_path):
        """Req 9.2：请求年份对应表缺失（trading_price_2099 不存在）→ 返回 None。"""
        db_path = _make_temp_db(tmp_path, _day_rows("2024-01-01", "NSW1"))
        calc = MonthlyBenchmarkCalculator(db_path=db_path)
        # 数据库仅含 trading_price_2024；请求 2099 触发 "no such table"
        assert calc.compute_monthly_benchmark("NSW1", "2099-01") is None

    def test_empty_region_month_returns_none(self, tmp_path):
        """Req 9.3：表存在但目标 region-month 零行 → 排除该点，返回 None。"""
        # 仅插入 VIC1 2024-05 数据，查询 NSW1 2024-01 应得零行
        db_path = _make_temp_db(tmp_path, _day_rows("2024-05-10", "VIC1"))
        calc = MonthlyBenchmarkCalculator(db_path=db_path)
        assert calc.compute_monthly_benchmark("NSW1", "2024-01") is None

    def test_query_timeout_returns_none(self, tmp_path, monkeypatch):
        """Req 9.5：查询超时 → 中止该 region-month，记 warning 返回 None，不抛异常。

        通过 monkeypatch ``_install_timeout`` 注入一个 "立即超时" 的 progress
        handler（首次回调即置位 timed_out 并返回非零中止查询），稳定触发超时分支，
        避免依赖真实耗时而导致 flaky。
        """

        def _immediate_timeout(conn, timeout_seconds):
            state = {"timed_out": False}

            def _handler():
                state["timed_out"] = True
                return 1  # 非零 -> 中止查询，触发 OperationalError

            conn.set_progress_handler(_handler, 1)
            return state

        monkeypatch.setattr(bx, "_install_timeout", _immediate_timeout)

        db_path = _make_temp_db(tmp_path, _day_rows("2024-01-01", "NSW1"))
        calc = MonthlyBenchmarkCalculator(db_path=db_path)
        # 不应抛异常，超时被优雅处理为 None
        assert calc.compute_monthly_benchmark("NSW1", "2024-01") is None

    def test_valid_temp_db_produces_benchmark(self, tmp_path):
        """正向对照：有效临时 db（>=20 有效日）应返回 ok 基准，确保边界用例非平凡。"""
        rows = []
        for day in range(1, 26):  # 25 个有效日，每日 288 interval
            rows.extend(_day_rows(f"2024-01-{day:02d}", "NSW1"))
        db_path = _make_temp_db(tmp_path, rows)
        calc = MonthlyBenchmarkCalculator(db_path=db_path)
        bench = calc.compute_monthly_benchmark("NSW1", "2024-01")
        assert bench is not None
        assert bench.data_quality_flag == "ok"
        assert bench.sample_days == 25
        assert bench.mean_spread_aud_mwh > 0


# ===========================================================================
# 任务 4.8：CaptureRateCalculator 告警边界 (Req 4.4)
# ===========================================================================


class TestCaptureRateLowEfficiencyWarning:
    """efficiency_ratio 跨 0.40 阈值时的告警标志与日志 (Req 4.4)。"""

    def test_below_threshold_sets_warning_flag(self):
        """ratio < 0.40 → low_efficiency_warning 为 True。"""
        calc = CaptureRateCalculator()
        cmp = calc.compare_with_model(
            model_capture_rate=0.30,
            perfect_foresight_rate=1.0,
            region="NSW1",
            year_month="2024-01",
        )
        assert cmp.violation is False
        assert cmp.efficiency_ratio == pytest.approx(0.30)
        assert cmp.low_efficiency_warning is True

    def test_below_threshold_emits_warning_log(self, caplog):
        """ratio < 0.40 → 触发 logger.warning（Req 4.4）。"""
        calc = CaptureRateCalculator()
        with caplog.at_level(logging.WARNING, logger="engines.backtest_expansion"):
            calc.compare_with_model(
                model_capture_rate=0.30,
                perfect_foresight_rate=1.0,
                region="NSW1",
                year_month="2024-01",
            )
        assert any(
            "efficiency_ratio" in rec.message and rec.levelno == logging.WARNING
            for rec in caplog.records
        )

    def test_at_or_above_threshold_no_warning(self):
        """ratio >= 0.40 → low_efficiency_warning 为 False（含 0.45 与边界 0.40）。"""
        calc = CaptureRateCalculator()

        above = calc.compare_with_model(
            model_capture_rate=0.45, perfect_foresight_rate=1.0
        )
        assert above.efficiency_ratio == pytest.approx(0.45)
        assert above.low_efficiency_warning is False

        # 边界：ratio 恰好 0.40，阈值判定为严格小于，故不告警
        boundary = calc.compare_with_model(
            model_capture_rate=0.40, perfect_foresight_rate=1.0
        )
        assert boundary.efficiency_ratio == pytest.approx(0.40)
        assert boundary.low_efficiency_warning is False

    def test_at_or_above_threshold_no_warning_log(self, caplog):
        """ratio >= 0.40 → 不产生低效率 warning 日志。"""
        calc = CaptureRateCalculator()
        with caplog.at_level(logging.WARNING, logger="engines.backtest_expansion"):
            calc.compare_with_model(
                model_capture_rate=0.45,
                perfect_foresight_rate=1.0,
                region="QLD1",
                year_month="2024-02",
            )
        assert not any(
            "efficiency_ratio" in rec.message for rec in caplog.records
        )


# ===========================================================================
# 任务 6.5：ForwardPriceEngine 月度验证委托方法接口 (Req 2.1, 2.5, 8.5)
# ===========================================================================


@pytest.mark.skipif(
    not _REAL_DB_PATH.exists(),
    reason="需要真实 data/aemo_data.db 才能驱动引擎月度验证委托方法",
)
class TestEngineDelegationInterface:
    """引擎委托方法 validate_against_monthly_benchmarks 的存在性与返回结构 (Req 2.1, 2.5)。"""

    @pytest.fixture(scope="class")
    def engine(self):
        from engines.forward_price_engine import ForwardPriceEngine

        return ForwardPriceEngine()

    def test_method_exists_and_callable(self, engine):
        """Req 2.1：引擎实例含可调用的 validate_against_monthly_benchmarks 方法。"""
        assert hasattr(engine, "validate_against_monthly_benchmarks")
        assert callable(engine.validate_against_monthly_benchmarks)

    def test_return_structure_keys(self, engine):
        """Req 2.5：返回 dict 含 results / summary / all_within_threshold / max_deviation_pct。"""
        result = engine.validate_against_monthly_benchmarks(target_month="2024-06")
        assert isinstance(result, dict)
        for key in ("results", "summary", "all_within_threshold", "max_deviation_pct"):
            assert key in result, f"缺少顶层字段: {key}"

        summary = result["summary"]
        for key in ("mape", "rmse", "bias", "hit_rate", "count"):
            assert key in summary, f"summary 缺少字段: {key}"

        # results 为 per-point 列表；非空时每项含兼容字段
        assert isinstance(result["results"], list)
        for point in result["results"]:
            for key in (
                "region",
                "year_month",
                "model_mean_spread",
                "benchmark_mean_spread",
                "deviation_pct",
            ):
                assert key in point, f"per-point 缺少字段: {key}"


class TestEngineDelegationIsLazyImport:
    """委托方法为延迟 import：模块导入期不硬依赖 backtest_expansion (Req 8.5)。"""

    def test_impl_function_importable(self):
        """backtest_expansion 提供 validate_against_monthly_benchmarks_impl 供委托转交。"""
        assert callable(validate_against_monthly_benchmarks_impl)

    def test_engine_module_import_does_not_require_backtest_expansion(self):
        """引擎模块源码中委托方法体内延迟 import（import-time 不依赖新模块）。

        断言引擎源码里 ``from engines.backtest_expansion import ...`` 出现在方法体内
        （缩进行）而非模块顶层，从而证明零 import-time 硬依赖（Req 8.5）。
        """
        engine_src = (
            Path(__file__).resolve().parent.parent
            / "backend"
            / "engines"
            / "forward_price_engine.py"
        ).read_text(encoding="utf-8")

        import_line = "from engines.backtest_expansion import validate_against_monthly_benchmarks_impl"
        assert import_line in engine_src

        # 模块顶层 import 不应以空白起始；委托方法体内的延迟 import 必为缩进行
        for line in engine_src.splitlines():
            if import_line in line:
                assert line.startswith(" ") or line.startswith("\t"), (
                    "backtest_expansion 应为方法体内延迟 import（缩进行），"
                    "不应出现在模块顶层"
                )


# ===========================================================================
# 任务 7.4：reconciliation 归档格式与告警边界 (Req 5.5, 6.1, 6.3, 6.4)
# ===========================================================================


class TestDeviationAlertBoundary:
    """is_deviation_alert 在 40% 阈值的严格大于判定 (Req 5.5)。"""

    def test_threshold_constant(self):
        assert DEVIATION_ALERT_THRESHOLD_PCT == 40.0

    @pytest.mark.parametrize(
        "deviation_pct, expected",
        [
            (39.9, False),
            (40.0, False),   # 严格大于：恰好 40% 不触发
            (40.1, True),
            (-50.0, True),   # 负向偏差取绝对值
            (-40.0, False),  # 负向边界同样严格大于
            (0.0, False),
        ],
    )
    def test_is_deviation_alert(self, deviation_pct, expected):
        assert is_deviation_alert(deviation_pct) is expected


class TestReconciliationArchive:
    """归档文件读写：初始化、损坏重建、字段往返 (Req 6.1, 6.2, 6.3, 6.4)。"""

    def test_missing_file_load_returns_empty(self, tmp_path):
        """Req 6.4：缺失归档文件 → _load_existing_records 返回 []。"""
        missing = tmp_path / "monthly_reconciliation.json"
        assert _load_existing_records(missing) == []

    def test_write_creates_json_array_with_one_record(self, tmp_path):
        """Req 6.4：写入后文件存在且为含一条记录的 JSON 数组。"""
        report = tmp_path / "monthly_reconciliation.json"
        record = {"target_month": "2024-06", "results": [], "summary": {}}
        written = _write_reconciliation_record(record, report)

        assert Path(written).exists()
        with open(written, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["target_month"] == "2024-06"

    def test_corrupt_json_rebuilds_empty_with_warning(self, tmp_path, caplog):
        """Req 6.2：损坏 JSON → _load_existing_records 返回 [] 且记 warning。"""
        report = tmp_path / "monthly_reconciliation.json"
        report.write_text("{ this is not valid json ]", encoding="utf-8")

        with caplog.at_level(logging.WARNING, logger="engines.backtest_expansion"):
            records = _load_existing_records(report)

        assert records == []
        assert any(rec.levelno == logging.WARNING for rec in caplog.records)

    def test_corrupt_json_write_preserves_new_record(self, tmp_path):
        """Req 6.2：损坏文件上 append 不丢失本次新记录（以空数组重建后追加）。"""
        report = tmp_path / "monthly_reconciliation.json"
        report.write_text("not json at all", encoding="utf-8")

        record = {"target_month": "2024-07", "results": [], "summary": {}}
        _write_reconciliation_record(record, report)

        with open(report, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert data == [record]

    def test_record_fields_roundtrip(self, tmp_path):
        """Req 6.1, 6.3：写盘 / 读回后顶层与 per-region 字段齐全。

        手写一条符合 run_monthly_reconciliation 输出结构的 fake record（不真跑引擎 /
        DB），验证写 / 读往返字段完整性。
        """
        report = tmp_path / "monthly_reconciliation.json"
        record = {
            "run_date": "2024-07-01T03:00:00+00:00",
            "target_month": "2024-06",
            "results": [
                {
                    "region": "NSW1",
                    "model_mean_spread": 120.0,
                    "actual_mean_spread": 110.0,
                    "deviation_pct": 9.1,
                    "capture_rate_comparison": {
                        "model": 0.62,
                        "perfect_foresight": 0.80,
                        "efficiency_ratio": 0.775,
                        "violation": False,
                    },
                    "alert_triggered": False,
                }
            ],
            "summary": {"mape": 9.1, "max_deviation": 9.1, "violation_count": 0},
        }

        _write_reconciliation_record(record, report)
        with open(report, "r", encoding="utf-8") as fh:
            loaded = json.load(fh)

        assert len(loaded) == 1
        top = loaded[0]
        # 顶层字段 (Req 6.1)
        for key in ("run_date", "target_month", "results", "summary"):
            assert key in top, f"顶层缺少字段: {key}"
        # summary 字段 (Req 6.1)
        for key in ("mape", "max_deviation", "violation_count"):
            assert key in top["summary"], f"summary 缺少字段: {key}"
        # per-region 字段 (Req 6.3)
        region_result = top["results"][0]
        for key in (
            "region",
            "model_mean_spread",
            "actual_mean_spread",
            "deviation_pct",
            "capture_rate_comparison",
            "alert_triggered",
        ):
            assert key in region_result, f"per-region 缺少字段: {key}"

    def test_append_preserves_history(self, tmp_path):
        """Req 6.2：多次 append 保留历史记录，按顺序追加。"""
        report = tmp_path / "monthly_reconciliation.json"
        r1 = {"target_month": "2024-05", "results": [], "summary": {}}
        r2 = {"target_month": "2024-06", "results": [], "summary": {}}

        _write_reconciliation_record(r1, report)
        _write_reconciliation_record(r2, report)

        with open(report, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        assert [rec["target_month"] for rec in data] == ["2024-05", "2024-06"]

    def test_default_report_path_points_to_repo_reports(self):
        """归档默认路径指向 <repo>/reports/monthly_reconciliation.json（不在此写入）。"""
        path = _reconciliation_report_path()
        assert path.name == "monthly_reconciliation.json"
        assert path.parent.name == "reports"
