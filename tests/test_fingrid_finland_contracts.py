import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from fingrid.catalog import get_dataset_config, list_dataset_configs
from finland_board_contracts import get_finland_board_field, get_finland_board_view


class FingridCatalogCoverageTests(unittest.TestCase):
    def test_hourly_fcr_and_imbalance_datasets_are_registered(self):
        dataset_ids = {item["dataset_id"] for item in list_dataset_configs()}
        self.assertTrue({"281", "283", "315", "316", "317", "318", "319"}.issubset(dataset_ids))

    def test_yearly_plan_datasets_are_registered(self):
        dataset_ids = {item["dataset_id"] for item in list_dataset_configs()}
        self.assertTrue({"288", "290", "321"}.issubset(dataset_ids))

    def test_fcrd_down_price_dataset_id_is_corrected(self):
        field = get_finland_board_field("fcr_d_down_price_eur_mw")
        self.assertEqual(field["source_dataset_id"], "283")
        dataset = get_dataset_config("283")
        self.assertEqual(dataset["unit"], "EUR/MW")

    def test_capacity_view_includes_price_and_volume_columns(self):
        columns = get_finland_board_view("capacity_hourly")["columns"]
        self.assertIn("fcr_n_volume_mw", columns)
        self.assertIn("fcr_d_up_volume_mw", columns)
        self.assertIn("fcr_d_down_volume_mw", columns)


if __name__ == "__main__":
    unittest.main()
