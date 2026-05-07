import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

import server


class PriceTrendSamplingTests(unittest.TestCase):
    def test_sampling_stride_is_disabled_when_limit_covers_all_rows(self):
        self.assertIsNone(server._price_trend_sampling_stride(720, 720))
        self.assertIsNone(server._price_trend_sampling_stride(300, 720))
        self.assertIsNone(server._price_trend_sampling_stride(300, None))

    def test_sampling_stride_is_computed_for_large_price_trend_queries(self):
        stride = server._price_trend_sampling_stride(105120, 720)
        self.assertIsNotNone(stride)
        self.assertGreaterEqual(stride, 1)
        self.assertLessEqual((105120 // stride) + 2, 722)


if __name__ == "__main__":
    unittest.main()
