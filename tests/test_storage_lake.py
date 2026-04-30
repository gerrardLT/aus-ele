import json
import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from storage_lake import LocalArtifactLake


class LocalArtifactLakeTests(unittest.TestCase):
    def test_write_artifact_persists_payload_outside_sqlite(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            lake = LocalArtifactLake(tmpdir)

            artifact = lake.write_artifact(
                layer="raw",
                namespace="fingrid",
                partition="dataset=319/date=2026-04-27",
                payload={"dataset_id": "319", "rows": 24},
                metadata={"job_id": "job-1", "source": "fingrid"},
            )

            self.assertEqual(artifact["layer"], "raw")
            self.assertTrue(os.path.exists(artifact["payload_path"]))
            self.assertTrue(os.path.exists(artifact["metadata_path"]))

            with open(artifact["payload_path"], "r", encoding="utf-8") as handle:
                self.assertEqual(json.load(handle)["dataset_id"], "319")

            with open(artifact["metadata_path"], "r", encoding="utf-8") as handle:
                metadata = json.load(handle)
            self.assertEqual(metadata["job_id"], "job-1")
            self.assertEqual(metadata["source"], "fingrid")

