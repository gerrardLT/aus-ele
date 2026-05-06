import tempfile
import unittest
from pathlib import Path

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from fingrid.yearly_market_seed import seed_fingrid_yearly_market_rows


class FingridYearlyMarketSeedTests(unittest.TestCase):
    def test_seed_writes_yearly_market_rows_to_official_datasets(self):
        with tempfile.TemporaryDirectory() as tempdir:
            db = DatabaseManager(str(Path(tempdir) / "test.db"))
            result = seed_fingrid_yearly_market_rows(db, ingested_at="2026-05-05T15:00:00Z")

            self.assertEqual(result["dataset_counts"]["288"], 5)
            self.assertEqual(result["dataset_counts"]["290"], 5)
            self.assertEqual(result["dataset_counts"]["321"], 5)

            fcrn_rows = db.fetch_fingrid_series(dataset_id="288")
            self.assertEqual(len(fcrn_rows), 5)
            self.assertEqual(fcrn_rows[0]["value"], 102.8)
            self.assertEqual(fcrn_rows[-1]["value"], 0.0)


if __name__ == "__main__":
    unittest.main()
