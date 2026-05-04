import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from finland_board_contracts import get_finland_board_field, get_finland_board_view


class FinlandBoardContractTests(unittest.TestCase):
    def test_capacity_hourly_view_declares_expected_columns_including_spot(self):
        view = get_finland_board_view("capacity_hourly")

        self.assertEqual(view["view_key"], "capacity_hourly")
        self.assertEqual(
            view["columns"],
            [
                "timestamp_local",
                "fcr_n_capacity_price",
                "fcr_d_up_capacity_price",
                "fcr_d_down_capacity_price",
                "day_ahead_spot_price",
            ],
        )

    def test_spot_field_is_marked_as_external_join(self):
        field_def = get_finland_board_field("day_ahead_spot_price")

        self.assertEqual(field_def["field_key"], "day_ahead_spot_price")
        self.assertEqual(field_def["source_type"], "external_join")
        self.assertEqual(field_def["granularity"], "1h")

    def test_unknown_view_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_finland_board_view("unknown_view")
