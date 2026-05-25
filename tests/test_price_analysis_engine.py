"""Unit tests for PriceAnalysisEngine — statistical calculation correctness."""

import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from engines.price_analysis_engine import PriceAnalysisEngine


class PriceAnalysisEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = PriceAnalysisEngine()

    # --- Statistics correctness ---

    def test_mean_calculation(self):
        prices = [{"price": 10.0}, {"price": 20.0}, {"price": 30.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["mean"], 20.0)

    def test_median_odd_count(self):
        prices = [{"price": 5.0}, {"price": 15.0}, {"price": 25.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["median"], 15.0)

    def test_median_even_count(self):
        prices = [{"price": 10.0}, {"price": 20.0}, {"price": 30.0}, {"price": 40.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["median"], 25.0)

    def test_percentile_p25(self):
        # 4 values: sorted = [10, 20, 30, 40]
        # p25 with linear interpolation: k = 0.25 * 3 = 0.75 -> 10 + 0.75*(20-10) = 17.5
        prices = [{"price": 10.0}, {"price": 20.0}, {"price": 30.0}, {"price": 40.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["p25"], 17.5)

    def test_percentile_p75(self):
        # 4 values: sorted = [10, 20, 30, 40]
        # p75 with linear interpolation: k = 0.75 * 3 = 2.25 -> 30 + 0.25*(40-30) = 32.5
        prices = [{"price": 10.0}, {"price": 20.0}, {"price": 30.0}, {"price": 40.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["p75"], 32.5)

    def test_max_and_min(self):
        prices = [{"price": -5.0}, {"price": 100.0}, {"price": 50.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["max"], 100.0)
        self.assertAlmostEqual(result.statistics["min"], -5.0)

    def test_single_value(self):
        prices = [{"price": 42.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["mean"], 42.0)
        self.assertAlmostEqual(result.statistics["median"], 42.0)
        self.assertAlmostEqual(result.statistics["p25"], 42.0)
        self.assertAlmostEqual(result.statistics["p75"], 42.0)
        self.assertAlmostEqual(result.statistics["max"], 42.0)
        self.assertAlmostEqual(result.statistics["min"], 42.0)

    def test_empty_prices_returns_zeros(self):
        result = self.engine.analyze([], region="NSW1", market="NEM")
        for key in ("mean", "median", "p25", "p75", "max", "min"):
            self.assertAlmostEqual(result.statistics[key], 0.0)

    def test_negative_prices(self):
        prices = [{"price": -100.0}, {"price": -50.0}, {"price": -10.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertAlmostEqual(result.statistics["mean"], -160.0 / 3.0)
        self.assertAlmostEqual(result.statistics["median"], -50.0)
        self.assertAlmostEqual(result.statistics["min"], -100.0)
        self.assertAlmostEqual(result.statistics["max"], -10.0)

    # --- Metadata correctness ---

    def test_metadata_unit_is_dollar_per_mwh(self):
        prices = [{"price": 50.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertEqual(result.metadata.unit, "$/MWh")

    def test_metadata_market_and_region(self):
        prices = [{"price": 50.0}]
        result = self.engine.analyze(prices, region="QLD1", market="WEM")
        self.assertEqual(result.metadata.market, "WEM")
        self.assertEqual(result.metadata.region_or_zone, "QLD1")

    def test_metadata_interval_minutes(self):
        prices = [{"price": 50.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM", interval_minutes=30)
        self.assertEqual(result.metadata.interval_minutes, 30)

    # --- Distribution ---

    def test_distribution_bins_sum_to_total_count(self):
        prices = [{"price": float(i)} for i in range(100)]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        total_count = sum(b["count"] for b in result.distribution)
        self.assertEqual(total_count, 100)

    def test_distribution_single_value_produces_one_bin(self):
        prices = [{"price": 50.0}, {"price": 50.0}, {"price": 50.0}]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertEqual(len(result.distribution), 1)
        self.assertEqual(result.distribution[0]["count"], 3)

    # --- Time series ---

    def test_time_series_preserves_order_and_values(self):
        prices = [
            {"price": 10.0, "timestamp": "2025-01-01T00:00:00Z"},
            {"price": 20.0, "timestamp": "2025-01-01T00:05:00Z"},
        ]
        result = self.engine.analyze(prices, region="NSW1", market="NEM")
        self.assertEqual(len(result.time_series), 2)
        self.assertAlmostEqual(result.time_series[0]["price"], 10.0)
        self.assertAlmostEqual(result.time_series[1]["price"], 20.0)
        self.assertEqual(result.time_series[0]["timestamp"], "2025-01-01T00:00:00Z")


if __name__ == "__main__":
    unittest.main()
