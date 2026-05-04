import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from finland_board_contracts import (
    FINLAND_BOARD_FIELDS,
    FINLAND_BOARD_VIEWS,
    get_finland_board_field,
    get_finland_board_view,
)


class FinlandBoardContractTests(unittest.TestCase):
    """Contract invariants for the Finland board field and view registries."""

    def test_capacity_hourly_view_declares_expected_columns_including_spot(self):
        view = get_finland_board_view("capacity_hourly")

        self.assertEqual(view["view_key"], "capacity_hourly")
        self.assertEqual(view["granularity"], "1h")
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

    def test_every_non_empty_view_column_exists_in_field_registry(self):
        for view_key in FINLAND_BOARD_VIEWS:
            view = get_finland_board_view(view_key)
            for column in view["columns"]:
                if column:
                    self.assertIn(column, FINLAND_BOARD_FIELDS, msg=f"{view_key}:{column}")

    def test_field_registry_keys_match_embedded_field_key_values(self):
        for field_key, field_def in FINLAND_BOARD_FIELDS.items():
            self.assertEqual(field_def["field_key"], field_key)

    def test_view_registry_keys_match_embedded_view_key_values(self):
        for view_key, view_def in FINLAND_BOARD_VIEWS.items():
            self.assertEqual(view_def["view_key"], view_key)

    def test_unknown_field_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_finland_board_field("unknown_field")

    def test_unknown_view_raises_key_error(self):
        with self.assertRaises(KeyError):
            get_finland_board_view("unknown_view")

    def test_returned_field_definition_is_safe_from_caller_mutation(self):
        first = get_finland_board_field("day_ahead_spot_price")
        first["label"] = "mutated"

        second = get_finland_board_field("day_ahead_spot_price")

        self.assertEqual(second["label"], "Day-ahead spot price")

    def test_returned_view_definition_is_safe_from_caller_mutation(self):
        first = get_finland_board_view("capacity_hourly")
        first["columns"].append("unexpected_column")
        first["label"] = "mutated"

        second = get_finland_board_view("capacity_hourly")

        self.assertEqual(second["label"], "Hourly capacity board")
        self.assertNotIn("unexpected_column", second["columns"])
