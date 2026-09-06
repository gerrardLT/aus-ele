"""R4.2：co_optimized 基线 6× 降采样（2026-09-06）。

验证的不是降采样算法本身，而是它对调用方的承诺：

1. 收入守恒 —— 引擎按 ``energy_prices[t]["interval_hours"]`` 同时计能量与 FCAS
   时长（co_optimization_engine.py 目标函数），所以「均值价 × 0.5h」必须等于
   原始 6 段 × 5min 的收入，降采样只允许平滑峰值、不允许缩水收入。
2. 防御 —— 数据量不足 min_intervals、数据已是 30min（WEM 结算）时原样返回，
   不允许把 30min 数据再降成 3h。
3. coopt_resolution 默认 precise（数值零回归），fast 合法、非法值被拒绝。
4. 接线 —— fast 才降采样：precise 模式下 _compute_co_optimized_baseline
   传给引擎的数据分辨率不变。
"""

import unittest
from unittest import mock

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from models.financial_params import InvestmentParams  # noqa: E402
from routes.coopt_routes import downsample_to_30min  # noqa: E402

NEM_INTERVAL_HOURS = 5.0 / 60.0
HALF_HOUR_HOURS = 0.5


def _make_prices(n_intervals: int, interval_hours: float = NEM_INTERVAL_HOURS):
    return [
        {
            "timestamp": f"2025-01-01T{i:05d}",
            "price": float(i % 97),
            "interval_hours": interval_hours,
        }
        for i in range(n_intervals)
    ]


class DownsampleTo30MinTests(unittest.TestCase):
    """downsample_to_30min 的守恒与防御边界。"""

    def test_below_min_intervals_returns_unchanged(self):
        energy = _make_prices(100)
        fcas = {"raisereg": [1.0] * 100}
        # 默认 min_intervals=2000：100 点远低于阈值，必须原样返回
        out_energy, out_fcas = downsample_to_30min(energy, fcas)
        self.assertEqual(out_energy, energy, "小数据集降采样不划算，必须原样返回")
        self.assertEqual(out_fcas, fcas)

    def test_empty_inputs_return_empty(self):
        out_energy, out_fcas = downsample_to_30min([], None, min_intervals=6)
        self.assertEqual(out_energy, [])
        self.assertEqual(out_fcas, {})

    def test_30min_data_is_not_downsampled_again(self):
        energy = _make_prices(2400, interval_hours=HALF_HOUR_HOURS)
        out_energy, _ = downsample_to_30min(energy, {}, min_intervals=6)
        self.assertEqual(
            len(out_energy), 2400, "已粗于 5min 的数据（如 WEM 30min 结算）不得再降"
        )

    def test_energy_revenue_conservation(self):
        energy = _make_prices(2400)
        out_energy, _ = downsample_to_30min(energy, {}, min_intervals=6)
        self.assertEqual(len(out_energy), 400, "2400 × 5min → 400 × 30min")
        before = sum(p["price"] * p["interval_hours"] for p in energy)
        after = sum(p["price"] * p["interval_hours"] for p in out_energy)
        self.assertAlmostEqual(before, after, places=6, msg="能量收入必须守恒")

    def test_fcas_revenue_conservation(self):
        # FCAS 列表与 energy 用同一个 interval_hours 计价（引擎约定），所以
        # sum(price) × ih 必须守恒：序列缩 6×、时长扩 6×，乘积不变。
        fcas = {"raisereg": [float(i) for i in range(2400)]}
        _, out_fcas = downsample_to_30min(_make_prices(2400), fcas, min_intervals=6)
        before = sum(fcas["raisereg"]) * NEM_INTERVAL_HOURS
        after = sum(out_fcas["raisereg"]) * HALF_HOUR_HOURS
        self.assertAlmostEqual(before, after, places=6, msg="FCAS 收入必须守恒")

    def test_bucket_mean_and_interval_hours(self):
        energy = _make_prices(12)  # prices = 0..11
        out_energy, _ = downsample_to_30min(energy, None, min_intervals=6)
        self.assertEqual(len(out_energy), 2)
        self.assertEqual(out_energy[0]["price"], 2.5)  # (0+1+2+3+4+5)/6
        self.assertEqual(out_energy[0]["timestamp"], energy[0]["timestamp"])
        self.assertEqual(out_energy[0]["interval_hours"], HALF_HOUR_HOURS)

    def test_short_fcas_series_kept_as_is(self):
        # 短 FCAS 序列不降采样（引擎对越界索引按 0 计价，安全）。
        # 与 coopt 路由的原内联行为一致。
        fcas = {"raisereg": [float(i) for i in range(2400)], "raise6sec": [1.0, 2.0]}
        _, out_fcas = downsample_to_30min(_make_prices(2400), fcas, min_intervals=6)
        self.assertEqual(len(out_fcas["raisereg"]), 400)
        self.assertEqual(out_fcas["raise6sec"], [1.0, 2.0])


class CooptResolutionParamTests(unittest.TestCase):
    """InvestmentParams.coopt_resolution 的默认值与校验。"""

    def test_default_is_precise(self):
        self.assertEqual(InvestmentParams(region="SA1").coopt_resolution, "precise")

    def test_fast_accepted(self):
        params = InvestmentParams(region="SA1", coopt_resolution="fast")
        self.assertEqual(params.coopt_resolution, "fast")

    def test_invalid_rejected(self):
        with self.assertRaises(Exception):
            InvestmentParams(region="SA1", coopt_resolution="turbo")


class ComputeCoOptimizedBaselineWiringTests(unittest.TestCase):
    """接线测试：fast 才降采样，precise 传给引擎的数据分辨率不变。"""

    N = 2400  # > min_intervals，保证会触发降采样分支

    def _run(self, resolution):
        from routes.investment_routes import _compute_co_optimized_baseline

        captured = {}

        def fake_derive(params, yearly_price_data, *, fcas_services=None):
            captured["sizes"] = [len(y["energy_prices"]) for y in yearly_price_data]
            return mock.Mock(years_used=1, status="optimal")

        with (
            mock.patch(
                "routes.coopt_routes._load_energy_prices",
                lambda *a, **k: _make_prices(self.N),
            ),
            mock.patch(
                "routes.coopt_routes._load_fcas_prices",
                lambda *a, **k: {"raisereg": [1.0] * self.N},
            ),
            mock.patch("routes.investment_routes.get_db", lambda: mock.Mock()),
            mock.patch(
                "services.investment_baseline.derive_co_optimized_baseline", fake_derive
            ),
        ):
            params = InvestmentParams(
                region="NSW1",
                backtest_years=[2025],
                revenue_baseline_mode="co_optimized",
                coopt_resolution=resolution,
            )
            _compute_co_optimized_baseline(params)
        return captured["sizes"]

    def test_precise_keeps_original_resolution(self):
        self.assertEqual(self._run("precise"), [self.N], "precise 必须零回归")

    def test_fast_downsamples_by_6x(self):
        self.assertEqual(self._run("fast"), [self.N // 6])


if __name__ == "__main__":
    unittest.main()
