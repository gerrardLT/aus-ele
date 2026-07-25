"""Pytest bootstrap for the backend test suite.

Ensures the repo ``.env`` (PostgreSQL connection settings) is loaded before any
test module imports ``database`` and initialises the connection pool. CI sets
these variables explicitly and has no ``.env`` file, so this is a no-op there.

Note: CI runs the suite via ``python -m unittest discover``, which does not load
``conftest.py``; the same ``ensure_repo_import_paths()`` call is also invoked at
the top of every test module, so unittest-based runs get identical behaviour.
"""

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()
