"""工具图表构建器单元测试（图表功能激活，2026-08-10）。

构建器为防御式纯函数：数据不足返回 None，绝不抛错。
"""

import sys
import unittest

from tests.support import ensure_repo_import_paths, stub_optional_dep

ensure_repo_import_paths()

stub_optional_dep("pulp")
stub_optional_dep("numpy_financial")

from agent.tools import (
    _CHART_MAX_POINTS,
    _chart_coopt_monthly,
    _chart_fcas_services,
    _chart_market_screening,
    _chart_price_trend,
    _downsample_chart_points,
)


class ChartBuilderTests(unittest.TestCase):
    # ── price trend ────────────────────────────────────────────────
    def test_price_trend_daily_aggregation(self):
        rows = [
            ("2025-01-01T00:00", 100.0),
            ("2025-01-01T00:30", 200.0),
            ("2025-01-02T00:00", 300.0),
            ("2025-01-02T00:30", 500.0),
        ]
        chart = _chart_price_trend(rows, "NSW1", 2025)
        self.assertEqual(chart["type"], "line")
        self.assertEqual(len(chart["data"]), 2)
        self.assertEqual(chart["data"][0]["y"], 150.0)  # 日均
        self.assertEqual(chart["data"][1]["y"], 400.0)

    def test_price_trend_insufficient_returns_none(self):
        self.assertIsNone(_chart_price_trend([], "NSW1", 2025))
        self.assertIsNone(_chart_price_trend([("2025-01-01T00:00", 100.0)], "NSW1", 2025))

    def test_price_trend_bad_values_skipped(self):
        rows = [
            ("2025-01-01T00:00", "not-a-number"),
            ("2025-01-01T00:30", 100.0),
            ("2025-01-02T00:00", 200.0),
        ]
        chart = _chart_price_trend(rows, "NSW1", 2025)
        self.assertEqual(len(chart["data"]), 2)

    # ── market screening ───────────────────────────────────────────
    def test_screening_sorted_top8(self):
        items = [
            {"label": f"R{i}", "overall_score": float(i)} for i in range(12)
        ]
        chart = _chart_market_screening({"items": items})
        self.assertEqual(chart["type"], "bar")
        self.assertEqual(len(chart["data"]), 8)
        self.assertEqual(chart["data"][0]["x"], "R11")  # 降序第一

    def test_screening_insufficient_returns_none(self):
        self.assertIsNone(_chart_market_screening({"items": []}))
        self.assertIsNone(_chart_market_screening(
            {"items": [{"label": "R1", "overall_score": 5.0}]}
        ))

    # ── fcas services ──────────────────────────────────────────────
    def test_fcas_service_averages(self):
        rows = [
            {"raisereg_rrp": 100.0, "lowerreg_rrp": 50.0},
            {"raisereg_rrp": 300.0, "lowerreg_rrp": 150.0},
        ]
        chart = _chart_fcas_services(rows)
        self.assertEqual(chart["type"], "bar")
        by_x = {p["x"]: p["y"] for p in chart["data"]}
        self.assertEqual(by_x["raisereg"], 200.0)
        self.assertEqual(by_x["lowerreg"], 100.0)

    def test_fcas_all_zero_returns_none(self):
        rows = [{"raisereg_rrp": 0.0, "lowerreg_rrp": 0.0}]
        self.assertIsNone(_chart_fcas_services(rows))
        self.assertIsNone(_chart_fcas_services([]))

    # ── co-opt monthly ─────────────────────────────────────────────
    def test_coopt_monthly_net_revenue(self):
        payload = {"monthly_breakdown": [
            {"month_index": 1, "total_net_revenue": 12345.6},
            {"month_index": 2, "total_net_revenue": -500.0},
            {"month_index": 3, "energy_revenue": 100.0, "fcas_revenue": 200.0},
        ]}
        chart = _chart_coopt_monthly(payload)
        self.assertEqual(chart["type"], "bar")
        self.assertEqual(len(chart["data"]), 3)
        self.assertEqual(chart["data"][0], {"x": "M1", "y": 12346.0})
        self.assertEqual(chart["data"][2], {"x": "M3", "y": 300.0})  # 无 net 时求和兜底

    def test_coopt_monthly_insufficient_returns_none(self):
        self.assertIsNone(_chart_coopt_monthly({}))
        self.assertIsNone(_chart_coopt_monthly({"monthly_breakdown": [
            {"month_index": 1, "total_net_revenue": 100.0},
        ]}))

    # ── downsample ─────────────────────────────────────────────────
    def test_downsample_caps_points_and_preserves_order(self):
        points = [{"x": i, "y": i} for i in range(600)]
        out = _downsample_chart_points(points)
        self.assertLessEqual(len(out), _CHART_MAX_POINTS)
        self.assertEqual(out[0]["x"], 0)
        ys = [p["y"] for p in out]
        self.assertEqual(ys, sorted(ys))  # 保序


if __name__ == "__main__":
    unittest.main()
