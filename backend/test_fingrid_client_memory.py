import os
import sys
import unittest

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()


class FingridClientMemorySafetyTests(unittest.TestCase):
    def test_https_fallback_avoids_repeated_bytes_concatenation(self):
        client_path = os.path.join(REPO_ROOT, "backend", "fingrid", "client.py")
        with open(client_path, "r", encoding="utf-8") as handle:
          source = handle.read()

        self.assertIn("chunks = []", source)
        self.assertIn("chunks.append(chunk)", source)
        self.assertIn('response_bytes = b"".join(chunks)', source)
        self.assertNotIn("response_bytes += chunk", source)


if __name__ == "__main__":
    unittest.main()
