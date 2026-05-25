"""Unit tests for backend/data_completeness.py"""

import os
import sys
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from data_completeness import DataCompletenessStatus, get_module_completeness
from database import DatabaseManager


class TestDataCompletenessStatus(unittest.TestCase):
    """Tests for the DataCompletenessStatus Pydantic model."""

    def test_model_fields(self):
        status = DataCompletenessStatus(
            module="wem_ess",
            status="complete",
            label="完整数据",
            last_sync="2024-06-01T12:00:00Z",
            pipeline_connected=True,
        )
        self.assertEqual(status.module, "wem_ess")
        self.assertEqual(status.status, "complete")
        self.assertEqual(status.label, "完整数据")
        self.assertEqual(status.last_sync, "2024-06-01T12:00:00Z")
        self.assertTrue(status.pipeline_connected)

    def test_model_with_none_last_sync(self):
        status = DataCompletenessStatus(
            module="wem_fcas",
            status="preview",
            label="预览 — FCAS 数据有限",
            last_sync=None,
            pipeline_connected=False,
        )
        self.assertIsNone(status.last_sync)
        self.assertFalse(status.pipeline_connected)


class TestGetModuleCompleteness(unittest.TestCase):
    """Tests for get_module_completeness function with real database."""

    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_wem_ess_preview_when_no_sync(self):
        """ESS module should be 'preview' when no sync has occurred."""
        result = get_module_completeness("wem_ess", self.db)
        self.assertEqual(result.module, "wem_ess")
        self.assertEqual(result.status, "preview")
        self.assertEqual(result.label, "预览 — ESS 管道未连接")
        self.assertIsNone(result.last_sync)
        self.assertFalse(result.pipeline_connected)

    def test_wem_ess_complete_when_marked(self):
        """ESS module should be 'complete' when data_completeness is set."""
        self.db.set_system_status("wem_ess_data_completeness", "complete")
        self.db.set_system_status("wem_ess_last_sync", "2024-06-01T12:00:00Z")
        result = get_module_completeness("wem_ess", self.db)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.label, "完整数据")
        self.assertEqual(result.last_sync, "2024-06-01T12:00:00Z")
        self.assertTrue(result.pipeline_connected)

    def test_wem_fcas_preview_when_no_sync(self):
        """FCAS module should be 'preview' when no sync has occurred."""
        result = get_module_completeness("wem_fcas", self.db)
        self.assertEqual(result.module, "wem_fcas")
        self.assertEqual(result.status, "preview")
        self.assertEqual(result.label, "预览 — FCAS 数据有限")
        self.assertIsNone(result.last_sync)
        self.assertFalse(result.pipeline_connected)

    def test_wem_fcas_complete_when_marked(self):
        """FCAS module should be 'complete' when data_completeness is set."""
        self.db.set_system_status("wem_fcas_data_completeness", "complete")
        self.db.set_system_status("wem_fcas_last_sync", "2024-03-15T08:30:00Z")
        result = get_module_completeness("wem_fcas", self.db)
        self.assertEqual(result.status, "complete")
        self.assertEqual(result.label, "完整数据")
        self.assertEqual(result.last_sync, "2024-03-15T08:30:00Z")
        self.assertTrue(result.pipeline_connected)

    def test_invalid_module_raises_value_error(self):
        """Unknown module names should raise ValueError."""
        with self.assertRaises(ValueError) as ctx:
            get_module_completeness("invalid_module", self.db)
        self.assertIn("Unknown module", str(ctx.exception))

    def test_pipeline_connected_true_when_last_sync_exists(self):
        """pipeline_connected should be True if last_sync is set, even without completeness."""
        self.db.set_system_status("wem_ess_last_sync", "2024-01-01T00:00:00Z")
        result = get_module_completeness("wem_ess", self.db)
        self.assertTrue(result.pipeline_connected)
        # Still preview because data_completeness is not "complete"
        self.assertEqual(result.status, "preview")

    def test_status_transitions_from_preview_to_complete(self):
        """Status should transition when completeness marker is updated."""
        result1 = get_module_completeness("wem_ess", self.db)
        self.assertEqual(result1.status, "preview")

        self.db.set_system_status("wem_ess_data_completeness", "complete")
        self.db.set_system_status("wem_ess_last_sync", "2024-06-01T00:00:00Z")

        result2 = get_module_completeness("wem_ess", self.db)
        self.assertEqual(result2.status, "complete")


if __name__ == "__main__":
    unittest.main()
