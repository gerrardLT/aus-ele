import importlib.util
import os
import sys
import unittest

from tests.support import ensure_repo_import_paths


class ImportPathBootstrapTests(unittest.TestCase):
    def test_ensure_repo_import_paths_exposes_backend_and_scrapers_modules(self):
        repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        backend_path = os.path.join(repo_root, "backend")
        scrapers_path = os.path.join(repo_root, "scrapers")

        sys.path = [entry for entry in sys.path if os.path.abspath(entry or os.getcwd()) not in {backend_path, scrapers_path}]
        sys.modules.pop("database", None)
        sys.modules.pop("aemo_wem_ess_scraper", None)

        self.assertIsNone(importlib.util.find_spec("database"))
        self.assertIsNone(importlib.util.find_spec("aemo_wem_ess_scraper"))

        ensure_repo_import_paths()

        self.assertIsNotNone(importlib.util.find_spec("database"))
        self.assertIsNotNone(importlib.util.find_spec("aemo_wem_ess_scraper"))


if __name__ == "__main__":
    unittest.main()
