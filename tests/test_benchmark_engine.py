"""Unit tests for benchmark_engine — NEM BESS revenue benchmark (Phase 1, 2026-08-12)."""

import unittest
from datetime import date

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.benchmark_engine import (
    BENCHMARK_COVERAGE_MODE,
    INTERVALS_PER_DAY,
    NEM_BENCHMARK_REGIONS,
    _compute_month_index,
    _expected_intervals,
    build_month_window,
    build_nem_bess_benchmark,
    build_nem_bess_region_compare,
)


# ---------------------------------------------------------------------------
# Fake DB (no real connection needed)
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows):
        self._rows = rows
        self._months = None

    def execute(self, sql, params=None):
        # 模拟按查询参数过滤：params = (region, *month_keys)
        self._months = set(params[1:]) if params else None

    def fetchall(self):
        if not self._months:
            return self._rows
        return [r for r in self._rows if str(r[0])[:7] in self._months]


class _FakeConn:
    def __init__(self, rows):
        self._rows = rows

    def cursor(self):
        return _FakeCursor(self._rows)


class _ConnCtx:
    def __init__(self, conn):
        self._conn = conn

    def __enter__(self):
        return self._conn

    def __exit__(self, *exc):
        return False


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    def get_connection(self):
        return _ConnCtx(_FakeConn(self._rows))

    def _table_exists(self, conn, name):
        return True


def _rows_for_month(month_key: str, days: int, price: float = 100.0, vary: bool = False):
    """生成指定月份前 ``days`` 天的 30 分钟结算价行。

    vary=True 时奇偶时段交替 50/150，形成套利空间（避免净收益为 0）。
    """
    rows = []
    for day in range(1, days + 1):
        for slot in range(INTERVALS_PER_DAY):
            hour, minute = divmod(slot * 30, 60)
            p = (50.0 if slot % 2 == 0 else 150.0) if vary else price
            rows.append((f"{month_key}-{day:02d} {hour:02d}:{minute:02d}:00", p))
    return rows


class MonthWindowTests(unittest.TestCase):
    def test_window_excludes_current_month(self):
        window = build_month_window(date(2026, 8, 12), 12)
        self.assertEqual(len(window), 12)
        self.assertEqual(window[0], "2025-08")
        self.assertEqual(window[-1], "2026-07")
        self.assertNotIn("2026-08", window)

    def test_window_single_month(self):
        self.assertEqual(build_month_window(date(2026, 8, 12), 1), ["2026-07"])

    def test_window_crosses_year_boundary(self):
        window = build_month_window(date(2026, 2, 15), 4)
        self.assertEqual(window, ["2025-10", "2025-11", "2025-12", "2026-01"])

    def test_invalid_months_raises(self):
        with self.assertRaises(ValueError):
            build_month_window(date(2026, 8, 12), 0)


class MonthIndexTests(unittest.TestCase):
    def test_index_formula_daily_cycle_arbitrage(self):
        # 1 天数据：47 个 @100 + 1 个 @50，RTE=1.0，cycle_intervals=4
        # 放电 top4 均价 = 100；充电 bottom4 均价 = (50+100×3)/4 = 87.5
        # 日净收入 = 200 MWh × 100 − 200 MWh × 87.5 = 2,500 AUD
        # 年化 /MW = 2500 / 100 × 12 = 300 → 0.3 kAUD/MW/年
        rows = _rows_for_month("2026-07", days=1)
        rows[-1] = (rows[-1][0], 50.0)
        idx = _compute_month_index(
            "2026-07", rows, power_mw=100.0, energy_mwh=200.0, rte=1.0
        )
        self.assertAlmostEqual(idx.index_k_aud_per_mw_year, 0.3, places=4)
        self.assertEqual(idx.interval_count, 48)
        self.assertIn("incomplete_month", idx.warnings)

    def test_flat_price_day_yields_zero_revenue(self):
        # 全天同价：无套利空间，日净收入为 0
        rows = _rows_for_month("2026-07", days=1)
        idx = _compute_month_index(
            "2026-07", rows, power_mw=100.0, energy_mwh=200.0, rte=0.85
        )
        self.assertAlmostEqual(idx.index_k_aud_per_mw_year, 0.0, places=4)

    def test_empty_month_flagged_no_data(self):
        idx = _compute_month_index(
            "2026-07", [], power_mw=100.0, energy_mwh=200.0, rte=0.85
        )
        self.assertEqual(idx.index_k_aud_per_mw_year, 0.0)
        self.assertIn("no_data", idx.warnings)

    def test_expected_intervals_matches_month_length(self):
        self.assertEqual(_expected_intervals("2026-07"), 31 * INTERVALS_PER_DAY)
        self.assertEqual(_expected_intervals("2026-06"), 30 * INTERVALS_PER_DAY)


class BenchmarkPayloadTests(unittest.TestCase):
    def test_rejects_non_benchmark_region(self):
        with self.assertRaises(ValueError):
            build_nem_bess_benchmark(_FakeDB([]), "WEM", 12)
        with self.assertRaises(ValueError):
            build_nem_bess_benchmark(_FakeDB([]), "TAS1", 12)

    def test_payload_structure_and_caveats(self):
        rows = _rows_for_month("2026-07", days=31, vary=True)
        payload = build_nem_bess_benchmark(_FakeDB(rows), "NSW1", 12, today=date(2026, 8, 12))

        self.assertEqual(payload["region"], "NSW1")
        self.assertEqual(len(payload["monthly"]), 12)
        self.assertEqual(payload["coverage_mode"], BENCHMARK_COVERAGE_MODE)
        self.assertTrue(payload["caveats"])

        summary = payload["summary"]
        self.assertEqual(summary["latest_month"], "2026-07")
        self.assertEqual(summary["months_with_data"], 1)
        self.assertGreater(summary["latest_index_k_aud_per_mw_year"], 0.0)

        # 缺数据月份带告警且指数为 0
        empty_month = next(m for m in payload["monthly"] if m["month"] == "2025-08")
        self.assertIn("no_data", empty_month["warnings"])
        self.assertEqual(empty_month["index_k_aud_per_mw_year"], 0.0)

        # 完整月份（31 天全量数据）不应有完整性告警
        full_month = next(m for m in payload["monthly"] if m["month"] == "2026-07")
        self.assertEqual(full_month["warnings"], [])
        self.assertAlmostEqual(full_month["completeness_pct"], 100.0, places=1)

    def test_reference_battery_defaults(self):
        payload = build_nem_bess_benchmark(_FakeDB([]), "SA1", 3, today=date(2026, 8, 12))
        ref = payload["reference_battery"]
        self.assertEqual(ref["power_mw"], 100.0)
        self.assertEqual(ref["energy_mwh"], 200.0)
        self.assertEqual(ref["round_trip_efficiency"], 0.85)

    def test_region_compare_ranks_all_mainland_regions(self):
        rows = _rows_for_month("2026-07", days=31, vary=True)
        payload = build_nem_bess_region_compare(_FakeDB(rows), today=date(2026, 8, 12))
        self.assertEqual(payload["month"], "2026-07")
        regions = [item["region"] for item in payload["items"]]
        self.assertEqual(sorted(regions), sorted(NEM_BENCHMARK_REGIONS))
        # 同数据下各区指数相同，排序结果仍覆盖全部区域
        indexes = [item["index_k_aud_per_mw_year"] for item in payload["items"]]
        self.assertEqual(indexes, sorted(indexes, reverse=True))

    def test_region_compare_no_data_yields_warnings(self):
        payload = build_nem_bess_region_compare(_FakeDB([]), today=date(2026, 8, 12))
        for item in payload["items"]:
            self.assertIsNone(item["index_k_aud_per_mw_year"])
            self.assertIn("no_complete_month_in_window", item["warnings"])


if __name__ == "__main__":
    unittest.main()
