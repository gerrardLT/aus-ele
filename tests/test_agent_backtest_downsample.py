"""co_optimized_backtest 降采样（OOM 修复）单元测试。

背景：生产 dmesg 实证 "cbc invoked oom-killer"——PuLP 全量 8760 步 MILP
撑爆 backend 容器 cgroup（1200m），worker 被杀导致前端 network error。
修复为等间距降采样（≤2160 区间），本测试锁定降采样行为。
"""

import sys
import types
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from agent.tools import (
    _COPT_MAX_INTERVALS,
    _downsample_backtest_rows,
)


def _rows(n):
    return [{"settlement_date": f"2025-01-01T{i:05d}", "rrp_aud_mwh": float(i)} for i in range(n)]


class DownsampleBacktestRowsTests(unittest.TestCase):
    def test_no_downsample_under_cap(self):
        rows = _rows(1000)
        sampled, stride = _downsample_backtest_rows(rows, _COPT_MAX_INTERVALS)
        self.assertEqual(stride, 1)
        self.assertEqual(len(sampled), 1000)

    def test_downsample_full_year_to_cap(self):
        rows = _rows(8760)
        sampled, stride = _downsample_backtest_rows(rows, _COPT_MAX_INTERVALS)
        self.assertGreater(stride, 1)
        self.assertLessEqual(len(sampled), _COPT_MAX_INTERVALS)
        # 等间距采样保留首行，且价格序列未被篡改
        self.assertEqual(sampled[0]["rrp_aud_mwh"], 0.0)
        self.assertEqual(sampled[1]["rrp_aud_mwh"], float(stride))

    def test_stride_covers_memory_reduction(self):
        """8760 → ≤2160 意味着至少 4 倍内存/建模耗时下降。"""
        _, stride = _downsample_backtest_rows(_rows(8760), _COPT_MAX_INTERVALS)
        self.assertGreaterEqual(stride, 4)

    def test_invalid_max_intervals_falls_back_to_noop(self):
        rows = _rows(5000)
        sampled, stride = _downsample_backtest_rows(rows, 0)
        self.assertEqual(stride, 1)
        self.assertEqual(len(sampled), 5000)

    def test_exact_cap_boundary(self):
        rows = _rows(_COPT_MAX_INTERVALS)
        sampled, stride = _downsample_backtest_rows(rows, _COPT_MAX_INTERVALS)
        self.assertEqual(stride, 1)
        self.assertEqual(len(sampled), _COPT_MAX_INTERVALS)


if __name__ == "__main__":
    unittest.main()
