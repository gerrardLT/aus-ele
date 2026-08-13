"""Unit tests for assumptions registry service (知识库 §2.2, 2026-08-12)."""

import json
import os
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from services.assumptions_registry import (
    _REGISTRY_PATH,
    get_assumption,
    get_assumption_value,
    list_assumptions,
)


class RegistryFileTests(unittest.TestCase):
    def test_registry_file_exists_and_loads(self):
        self.assertTrue(os.path.exists(_REGISTRY_PATH))
        with open(_REGISTRY_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.assertEqual(data["meta"]["schema_version"], 1)
        self.assertGreater(len(data["assumptions"]), 0)

    def test_ids_are_unique(self):
        ids = [item["id"] for item in list_assumptions()]
        self.assertEqual(len(ids), len(set(ids)))

    def test_required_entries_registered(self):
        for required in (
            "fcas_compression_factor",
            "benchmark_reference_battery",
            "contract_revenue_anchors",
        ):
            self.assertIsNotNone(get_assumption(required), f"缺少登记项: {required}")

    def test_entries_carry_audit_fields(self):
        for item in list_assumptions():
            self.assertIn("source", item, f"{item['id']} 缺 source")
            self.assertIn("last_calibrated", item, f"{item['id']} 缺 last_calibrated")


class RegistryServiceTests(unittest.TestCase):
    def test_fcas_compression_factor_value(self):
        self.assertAlmostEqual(
            float(get_assumption_value("fcas_compression_factor", default=0.3)), 0.3
        )

    def test_unknown_id_returns_default(self):
        sentinel = {"fallback": True}
        self.assertIs(get_assumption_value("no_such_assumption", default=sentinel), sentinel)
        self.assertIsNone(get_assumption("no_such_assumption"))

    def test_benchmark_engine_defaults_match_registry(self):
        # wired 项：引擎常量必须与登记表一致（防止改登记表忘改代码或反之）
        from engines import benchmark_engine

        ref = get_assumption_value("benchmark_reference_battery", default={})
        self.assertEqual(benchmark_engine.DEFAULT_POWER_MW, float(ref["power_mw"]))
        self.assertEqual(benchmark_engine.DEFAULT_ENERGY_MWH, float(ref["energy_mwh"]))
        self.assertEqual(benchmark_engine.DEFAULT_RTE, float(ref["round_trip_efficiency"]))


if __name__ == "__main__":
    unittest.main()
