import os
import sys


def ensure_repo_import_paths():
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    for relative_path in ("backend", "scrapers"):
        path = os.path.join(repo_root, relative_path)
        if path not in sys.path:
            sys.path.insert(0, path)
