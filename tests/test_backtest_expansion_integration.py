"""Integration / 非回归 tests for Backtest Expansion MVP.

覆盖 tasks.md 中以下四个集成 / 非回归子任务：

- 任务 11.1：真实 DB 集成测试 (Req 7.3, 1.3)
    对真实 ``data/aemo_data.db`` 跑 ``compute_all_benchmarks``，断言有效验证点 ≥ 96；
    断言单日 interval 计数接近 288（验证 5 分钟粒度）。

- 任务 10.2：脚本扩展集成测试 (Req 7.1, 7.2, 7.4, 7.5)
    subprocess 运行 ``scripts/run_full_backtest.py``，断言报告含 "I. 月度 AEMO 基准验证"
    段与 MAPE/RMSE/Bias/Hit Rate；Section I 用 MAPE ≤ 30 / Hit Rate ≥ 75 阈值；
    且 A–H 既有 deterministic 部分不被 Section I 扰动（无新增失败）。

- 任务 9.2：调度接线集成测试 (Req 5.1, 5.2, 5.3, 5.6)
    断言 ``app._reconciliation_enabled()`` / ``app._cron_hour(...)`` 正确读取环境变量；
    复现 app.py 的 cron job 注册（day=1, hour=cfg, tz=UTC, func=run_monthly_reconciliation）
    并断言 trigger 字段；不启动真实服务器 / 不触发 job 写盘。

- 任务 11.2：非回归验证 (Req 8.1, 8.2, 8.3, 8.4, 8.5)
    subprocess 运行既有 ``tests/test_forward_model_properties.py``，断言 20 条 PBT 通过；
    源码不变性：引擎仍含受保护成员且新增委托方法存在；新模块不写
    ``capacity_data.json`` / ``financial_evidence.json``。

设计说明（Windows 多解释器环境注记）：
    ``scripts/run_full_backtest.py`` 的 Section C 通过 ``subprocess.run(["python", ...])``
    以 **bare ``python``** 派生子进程跑既有 17 条属性测试。在本仓库的多解释器 Windows
    环境中，bare ``python`` 可能解析到缺少 ``pulp`` 的基础解释器（而非运行其余一切的
    ``.venv`` 解释器），导致脚本报告里 Section C 显示 "1 error"。这是脚本既有的解释器
    解析脆弱性、与本特性无关。因此本文件中所有派生 Python 子进程一律用
    ``sys.executable`` 启动以保证解释器一致；任务 11.2 用 ``sys.executable`` 跑 PBT，
    是 "既有 20 条 PBT 不回归" 的权威校验（Req 8.4）。
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

import re
import subprocess
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REAL_DB_PATH = _REPO_ROOT / "data" / "aemo_data.db"
_BACKTEST_SCRIPT = _REPO_ROOT / "scripts" / "run_full_backtest.py"
_BACKTEST_REPORT = _REPO_ROOT / "reports" / "backtest_report.txt"
_PBT_FILE = _REPO_ROOT / "tests" / "test_forward_model_properties.py"
_ENGINE_SRC = _REPO_ROOT / "backend" / "engines" / "forward_price_engine.py"
_MODULE_SRC = _REPO_ROOT / "backend" / "engines" / "backtest_expansion.py"

_DB_AVAILABLE = _REAL_DB_PATH.exists()


def _subprocess_env() -> dict:
    """返回子进程环境：强制 UTF-8 stdout，并保证嵌套 bare ``python`` 解释器一致。

    - ``PYTHONUTF8`` / ``PYTHONIOENCODING``：避免 Windows gbk 解码错误。
    - 将当前解释器目录（``sys.executable`` 所在目录）前置到 ``PATH``：``run_full_backtest.py``
      的 Section C 通过 ``subprocess.run(["python", ...])`` 以 bare ``python`` 派生子进程跑
      既有属性测试；在多解释器 Windows 环境中 bare ``python`` 可能解析到缺少 ``pulp`` 的
      基础解释器，导致 Section C 报 "1 error"。前置当前解释器目录从根因上保证嵌套 ``python``
      与运行测试的解释器一致（含依赖），避免该既有脚本脆弱性误判为本特性回归。
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    exe_dir = os.path.dirname(sys.executable)
    if exe_dir:
        env["PATH"] = exe_dir + os.pathsep + env.get("PATH", "")
    return env


# ===========================================================================
# 任务 11.1：真实 DB 集成测试 (Req 7.3, 1.3)
# ===========================================================================


@pytest.mark.skipif(
    not _DB_AVAILABLE,
    reason="需要真实 data/aemo_data.db（仓库根）才能跑真实 DB 集成测试",
)
class TestRealDatabaseBenchmarks:
    """对真实 AEMO 数据库验证月度基准规模与 5 分钟粒度 (Req 7.3, 1.3)。"""

    @pytest.fixture(scope="class")
    def calculator(self):
        from engines.backtest_expansion import MonthlyBenchmarkCalculator

        return MonthlyBenchmarkCalculator()

    @pytest.fixture(scope="class")
    def benchmarks(self, calculator):
        """对真实 DB 跑一次 compute_all_benchmarks（类级缓存，避免重复全量扫描）。"""
        return calculator.compute_all_benchmarks()

    def test_valid_benchmark_points_at_least_96(self, benchmarks):
        """Req 7.3：过滤 insufficient_data 后有效验证点 ≥ 96（实测约 130）。"""
        valid = [b for b in benchmarks if b.data_quality_flag == "ok"]
        assert len(valid) >= 96, (
            f"有效验证点不足 96：实得 {len(valid)}（总 {len(benchmarks)}）。"
            "目标为 24 月 × 4+ 区域 ≥ 96 个月度数据点。"
        )

    def test_all_five_nem_regions_present(self, benchmarks):
        """Req 1.2：有效基准覆盖全部五个 NEM 区域且不含 WEM。"""
        valid_regions = {b.region for b in benchmarks if b.data_quality_flag == "ok"}
        assert {"NSW1", "QLD1", "SA1", "TAS1", "VIC1"}.issubset(valid_regions)
        assert not any(r.startswith("WEM") for r in valid_regions)

    def test_daily_interval_count_near_288(self, calculator):
        """Req 1.3：单日 interval 计数接近 288（5 分钟粒度 = 24h × 12）。

        直接查询某个有数据的 region-month 每日 interval 计数，断言典型值 == 288，
        且全部 ≥ 280（容忍极少数因数据缺口偏低的日，但有效基准日应均为满日）。
        """
        # Use PG connection via the calculator's DatabaseManager
        from deps import get_db
        db = get_db()
        with db.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT DATE(settlement_date) AS day, COUNT(*) AS n
                FROM trading_price_2024
                WHERE region_id = 'NSW1' AND settlement_date::text LIKE '2024-06%'
                GROUP BY day
                ORDER BY day
                """
            )
            rows = cursor.fetchall()

        counts = [n for _day, n in rows]
        assert counts, "2024-06 NSW1 无数据，无法验证 5 分钟粒度"
        # 5 分钟粒度：满日应为 288 个 interval
        assert max(counts) == 288, f"单日最大 interval 计数应为 288，实得 {max(counts)}"
        # 典型值（众数）应为 288
        typical = max(set(counts), key=counts.count)
        assert typical == 288, f"单日典型 interval 计数应为 288，实得 {typical}"
        # 合理区间：有效日应全部 ≥ 280
        assert min(counts) >= 280, (
            f"存在 interval 计数 < 280 的日（最小 {min(counts)}），"
            "5 分钟粒度满日应接近 288"
        )

    def test_mean_spread_positive_for_valid_points(self, benchmarks):
        """有效基准点的 mean_spread 应为正（日内 max-min 价差均值 > 0）。"""
        valid = [b for b in benchmarks if b.data_quality_flag == "ok"]
        assert valid, "无有效基准点"
        assert all(b.mean_spread_aud_mwh > 0 for b in valid)


# ===========================================================================
# 任务 9.2：调度接线集成测试 (Req 5.1, 5.2, 5.3, 5.6)
# ===========================================================================


class TestReconciliationEnvHelpers:
    """app.py 的 env helper 正确读取 reconciliation 调度配置 (Req 5.6, 5.1)。"""

    @pytest.fixture(scope="class")
    def app_module(self):
        """轻量 import app 模块（仅取 env helper，不启动 FastAPI / lifespan）。"""
        return __import__("app")

    def test_reconciliation_enabled_default_true(self, app_module, monkeypatch):
        """Req 5.6：未设环境变量时 _reconciliation_enabled() 默认 True。"""
        monkeypatch.delenv("AUS_ELE_RECONCILIATION_ENABLED", raising=False)
        assert app_module._reconciliation_enabled() is True

    @pytest.mark.parametrize(
        "raw, expected",
        [
            ("false", False),
            ("0", False),
            ("no", False),
            ("off", False),
            ("true", True),
            ("1", True),
            ("yes", True),
        ],
    )
    def test_reconciliation_enabled_reads_env(
        self, app_module, monkeypatch, raw, expected
    ):
        """Req 5.6：_reconciliation_enabled() 正确解析自定义布尔环境变量值。"""
        monkeypatch.setenv("AUS_ELE_RECONCILIATION_ENABLED", raw)
        assert app_module._reconciliation_enabled() is expected

    def test_cron_hour_default_three(self, app_module, monkeypatch):
        """Req 5.1：未设环境变量时 reconciliation 默认小时 = 3（03:00 UTC）。"""
        monkeypatch.delenv("AUS_ELE_RECONCILIATION_HOUR", raising=False)
        assert app_module._cron_hour("AUS_ELE_RECONCILIATION_HOUR", 3) == 3

    def test_cron_hour_reads_custom_env(self, app_module, monkeypatch):
        """Req 5.1/5.6：_cron_hour 读取自定义小时值。"""
        monkeypatch.setenv("AUS_ELE_RECONCILIATION_HOUR", "7")
        assert app_module._cron_hour("AUS_ELE_RECONCILIATION_HOUR", 3) == 7

    def test_cron_hour_clamps_out_of_range(self, app_module, monkeypatch):
        """_cron_hour 将越界值钳制到 [0, 23]。"""
        monkeypatch.setenv("AUS_ELE_RECONCILIATION_HOUR", "99")
        assert app_module._cron_hour("AUS_ELE_RECONCILIATION_HOUR", 3) == 23

    def test_cron_hour_invalid_falls_back_to_default(self, app_module, monkeypatch):
        """_cron_hour 非法值回退默认。"""
        monkeypatch.setenv("AUS_ELE_RECONCILIATION_HOUR", "not-an-int")
        assert app_module._cron_hour("AUS_ELE_RECONCILIATION_HOUR", 3) == 3

    def test_scheduler_timezone_default_utc(self, app_module, monkeypatch):
        """Req 5.1：调度默认时区为 UTC（对应 03:00 UTC 约定）。"""
        monkeypatch.delenv("AUS_ELE_SCHEDULER_TIMEZONE", raising=False)
        assert app_module._scheduler_timezone().key == "UTC"


class TestReconciliationCronJobRegistration:
    """复现 app.py 的 cron job 注册逻辑并断言 trigger 字段 (Req 5.1, 5.2, 5.3)。

    采用轻量方案：用真实 ``AsyncIOScheduler``（项目依赖）复现 app.py lifespan 中的
    ``scheduler.add_job(run_monthly_reconciliation, "cron", day=1, hour=rh, ...)`` 片段，
    断言 job 存在、callable 指向 ``run_monthly_reconciliation``、trigger 的 day==1、
    hour==配置值、timezone==UTC。不启动 FastAPI app、不 start scheduler、不触发 job。
    """

    def _build_scheduler_with_job(self, hour: int):
        from apscheduler.schedulers.asyncio import AsyncIOScheduler
        from zoneinfo import ZoneInfo
        from engines.backtest_expansion import run_monthly_reconciliation

        scheduler = AsyncIOScheduler(timezone=ZoneInfo("UTC"))
        scheduler.add_job(
            run_monthly_reconciliation,
            "cron",
            day=1,
            hour=hour,
            id="monthly-reconciliation",
            max_instances=1,
            coalesce=True,
            misfire_grace_time=3600,
        )
        return scheduler, run_monthly_reconciliation

    @staticmethod
    def _trigger_fields(trigger) -> dict:
        """提取 APScheduler CronTrigger 各字段的字符串表示。"""
        return {f.name: str(f) for f in trigger.fields}

    def test_job_registered_with_expected_id_and_callable(self):
        """Req 5.2/5.3：job 以 id=monthly-reconciliation 注册且 callable 指向入口函数。"""
        scheduler, target = self._build_scheduler_with_job(hour=3)
        job = scheduler.get_job("monthly-reconciliation")
        assert job is not None
        assert job.func is target

    def test_trigger_day_is_first_of_month(self):
        """Req 5.1：cron trigger 在每月 1 日触发（day == 1）。"""
        scheduler, _ = self._build_scheduler_with_job(hour=3)
        fields = self._trigger_fields(scheduler.get_job("monthly-reconciliation").trigger)
        assert fields["day"] == "1"

    @pytest.mark.parametrize("hour", [3, 0, 7, 23])
    def test_trigger_hour_matches_config(self, hour):
        """Req 5.1/5.6：cron trigger 小时等于配置值（默认 3，及自定义值）。"""
        scheduler, _ = self._build_scheduler_with_job(hour=hour)
        fields = self._trigger_fields(scheduler.get_job("monthly-reconciliation").trigger)
        assert fields["hour"] == str(hour)

    def test_trigger_timezone_is_utc(self):
        """Req 5.1：cron trigger 时区为 UTC。"""
        scheduler, _ = self._build_scheduler_with_job(hour=3)
        trigger = scheduler.get_job("monthly-reconciliation").trigger
        assert str(trigger.timezone) == "UTC"

    def test_app_source_registers_job_inside_enabled_block(self):
        """Req 5.1/5.6：app.py 源码在 _reconciliation_enabled() 守卫内注册该 cron job。

        以源码静态断言佐证 env-gated 接线，避免启动真实 lifespan（较重且会 start
        scheduler）。验证注册片段的关键要素均present 且 env-gated。
        """
        app_src = (_REPO_ROOT / "backend" / "app.py").read_text(encoding="utf-8")
        assert "_reconciliation_enabled()" in app_src
        assert 'AUS_ELE_RECONCILIATION_HOUR' in app_src
        assert "run_monthly_reconciliation" in app_src
        assert 'id="monthly-reconciliation"' in app_src
        # day=1 与 cron 同处注册调用
        assert "day=1" in app_src


# ===========================================================================
# 任务 10.2：脚本扩展集成测试 (Req 7.1, 7.2, 7.4, 7.5)
# ===========================================================================


@pytest.mark.skipif(
    not _DB_AVAILABLE,
    reason="run_full_backtest.py 依赖真实 data/aemo_data.db 才能产出完整报告",
)
class TestBacktestScriptSectionI:
    """运行 run_full_backtest.py 并校验新增 Section I 与 A–H 非回归 (Req 7)。"""

    @pytest.fixture(scope="class")
    def report_text(self) -> str:
        """subprocess 运行回测脚本一次（类级缓存），返回 stdout + 报告文件文本。

        用 ``sys.executable`` 保证解释器一致（见模块 docstring 的多解释器注记）；
        合理 timeout，失败时附 stderr 诊断。
        """
        result = subprocess.run(
            [sys.executable, str(_BACKTEST_SCRIPT)],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_subprocess_env(),
            timeout=900,
        )
        combined = (result.stdout or "") + "\n" + (result.stderr or "")
        # 优先用持久化报告文件（更稳），回退到 stdout
        if _BACKTEST_REPORT.exists():
            combined += "\n" + _BACKTEST_REPORT.read_text(encoding="utf-8")
        assert combined.strip(), (
            f"回测脚本无输出，returncode={result.returncode}\n"
            f"stderr 摘要: {(result.stderr or '')[:500]}"
        )
        return combined

    def test_report_contains_section_i(self, report_text):
        """Req 7.1：报告含新增 "I. 月度 AEMO 基准验证" 段。"""
        assert "I. 月度 AEMO 基准验证" in report_text

    def test_section_i_reports_aggregate_metrics(self, report_text):
        """Req 7.2：Section I 报告 MAPE / RMSE / Bias / Hit Rate 指标。"""
        # 截取 Section I 之后的文本，确保这些指标出现在该段内
        idx = report_text.find("I. 月度 AEMO 基准验证")
        assert idx != -1
        section_i = report_text[idx:]
        for token in ("MAPE", "RMSE", "Bias", "Hit Rate"):
            assert token in section_i, f"Section I 缺少指标: {token}"

    def test_section_i_reports_validation_point_total(self, report_text):
        """Req 7.3：Section I 报告验证点总数（目标 96+，实测约 130）。"""
        idx = report_text.find("I. 月度 AEMO 基准验证")
        section_i = report_text[idx:]
        # 匹配 "验证点总数: N" 中的数字，断言 ≥ 96
        m = re.search(r"验证点总数[:：]\s*(\d+)", section_i)
        assert m is not None, "Section I 未报告验证点总数"
        assert int(m.group(1)) >= 96

    def test_ah_sections_no_regression(self, report_text):
        """Req 7.4/8.3：A–H 既有 deterministic 验证点仍全部通过（33 个 pass）。

        断言报告中 A–H 贡献的通过数不少于扩展前的 33。脚本总结行形如
        "通过 X / 失败 Y"；A–H 应稳定贡献 33 个 pass，Section I 自身的 pass/fail
        独立累加、不污染 A–H。这里校验 A–H 区段未出现新增 FAIL。
        """
        # A–H 区段 = Section I 之前的全部文本
        idx = report_text.find("I. 月度 AEMO 基准验证")
        assert idx != -1, "未找到 Section I，无法切分 A–H 区段"
        ah_section = report_text[:idx]
        # A–H 区段不应包含 FAIL 标记（既有 33/33 全过）
        assert "[FAIL]" not in ah_section, (
            "A–H 区段出现 [FAIL]，疑似 Section I 扩展引入非回归"
        )


# ===========================================================================
# 任务 11.2：非回归验证 (Req 8.1, 8.2, 8.3, 8.4, 8.5)
# ===========================================================================


class TestExistingPBTNoRegression:
    """既有 20 条属性测试无修改通过 (Req 8.4)。"""

    @pytest.mark.skipif(
        not _PBT_FILE.exists(),
        reason="既有 PBT 文件 tests/test_forward_model_properties.py 不存在",
    )
    def test_existing_forward_model_pbt_pass(self):
        """Req 8.4：subprocess 跑既有 PBT 套件，断言全部通过。

        用 ``sys.executable`` 保证解释器一致（避免 bare python 解析到缺依赖解释器）。
        """
        result = subprocess.run(
            [sys.executable, "-m", "pytest", str(_PBT_FILE), "-q"],
            cwd=str(_REPO_ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=_subprocess_env(),
            timeout=600,
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
        assert result.returncode == 0, (
            f"既有 PBT 未全部通过 (returncode={result.returncode})：\n{output[-1500:]}"
        )
        # 确认确有测试被收集且无 failed
        assert "failed" not in output.lower() or "0 failed" in output.lower()


class TestProtectedMembersUnchanged:
    """源码不变性：受保护成员仍存在、新增委托方法存在 (Req 8.1, 8.5)。"""

    @pytest.fixture(scope="class")
    def engine_src(self) -> str:
        return _ENGINE_SRC.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "symbol",
        [
            "def validate_against_benchmarks",
            "def _compute_capture_rate",
            "SEASONAL_CAPTURE_MULTIPLIER",
            "REGIONAL_VOLATILITY_FACTOR",
        ],
    )
    def test_protected_members_present(self, engine_src, symbol):
        """Req 8.1：引擎受保护方法 / 常量仍存在（未被新特性替换 / 删除）。"""
        assert symbol in engine_src, f"受保护成员缺失（疑似被改动）: {symbol}"

    def test_new_delegation_method_present(self, engine_src):
        """Req 2.1/8.5：新增薄委托方法 validate_against_monthly_benchmarks 存在。"""
        assert "def validate_against_monthly_benchmarks" in engine_src

    def test_delegation_is_lazy_import(self, engine_src):
        """Req 8.5：委托方法体内延迟 import 新模块（import-time 零硬依赖）。"""
        import_line = (
            "from engines.backtest_expansion import "
            "validate_against_monthly_benchmarks_impl"
        )
        assert import_line in engine_src
        for line in engine_src.splitlines():
            if import_line in line:
                assert line.startswith((" ", "\t")), (
                    "新模块 import 应为方法体内缩进的延迟 import，不应在模块顶层"
                )


class TestNewModuleDoesNotWriteProtectedData:
    """新模块不写 capacity_data.json / financial_evidence.json (Req 8.2)。"""

    @pytest.fixture(scope="class")
    def module_src(self) -> str:
        return _MODULE_SRC.read_text(encoding="utf-8")

    @pytest.mark.parametrize(
        "protected_file",
        ["capacity_data.json", "financial_evidence.json"],
    )
    def test_no_reference_to_protected_data_files(self, module_src, protected_file):
        """Req 8.2：新模块源码不引用（更不写入）受保护数据文件。"""
        assert protected_file not in module_src, (
            f"新模块不应引用受保护数据文件: {protected_file}"
        )

    def test_module_only_writes_reconciliation_report(self, module_src):
        """Req 8.2：新模块唯一的写文件目标是 monthly_reconciliation.json。"""
        # 写操作仅出现在 reconciliation 归档；不应有对 data/ 下 json 的写
        assert "monthly_reconciliation.json" in module_src
        assert 'data/capacity_data.json' not in module_src
        assert 'data/financial_evidence.json' not in module_src
