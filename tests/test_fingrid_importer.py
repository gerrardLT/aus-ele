import tempfile
import unittest
from pathlib import Path

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from fingrid.importer import import_fingrid_csv


class FingridImporterTests(unittest.TestCase):
    def test_import_fingrid_csv_writes_rows_and_sync_state(self):
        with tempfile.TemporaryDirectory() as tempdir:
            csv_path = Path(tempdir) / "dataset-317.csv"
            db_path = Path(tempdir) / "test.db"
            csv_path.write_text(
                "startTime,endTime,value\n"
                "2026-04-01T00:00:00Z,2026-04-01T01:00:00Z,12.5\n"
                "2026-04-01T01:00:00Z,2026-04-01T02:00:00Z,13.75\n",
                encoding="utf-8",
            )

            db = DatabaseManager(str(db_path))
            result = import_fingrid_csv(db, dataset_id="317", csv_path=str(csv_path), ingested_at="2026-05-05T14:30:00Z")

            self.assertEqual(result["records_upserted"], 2)
            rows = db.fetch_fingrid_series(dataset_id="317")
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[0]["value"], 12.5)

            state = db.fetch_fingrid_sync_state("317")
            self.assertEqual(state["sync_status"], "ok")
            self.assertEqual(state["last_synced_timestamp_utc"], "2026-04-01T01:00:00Z")

    def test_import_fingrid_csv_supports_semicolon_and_value_column_override(self):
        with tempfile.TemporaryDirectory() as tempdir:
            csv_path = Path(tempdir) / "dataset-316.csv"
            db_path = Path(tempdir) / "test.db"
            csv_path.write_text(
                "Start Time;End Time;Procured MW\n"
                "2026-04-01T00:00:00Z;2026-04-01T01:00:00Z;101,5\n",
                encoding="utf-8",
            )

            db = DatabaseManager(str(db_path))
            result = import_fingrid_csv(
                db,
                dataset_id="316",
                csv_path=str(csv_path),
                value_column="Procured MW",
                delimiter=";",
                ingested_at="2026-05-05T14:30:00Z",
            )

            self.assertEqual(result["records_upserted"], 1)
            rows = db.fetch_fingrid_series(dataset_id="316")
            self.assertEqual(rows[0]["value"], 101.5)


if __name__ == "__main__":
    unittest.main()
