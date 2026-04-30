import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server


class WemEssOpportunityScoreTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_cache = server.response_cache
        server.db = self.db

    def tearDown(self):
        server.db = self.original_db
        server.response_cache = self.original_cache
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_wem_fcas_analysis_exposes_preview_scoring_summary(self):
        with self.db.get_connection() as conn:
            self.db.ensure_wem_ess_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.db.WEM_ESS_MARKET_TABLE} (
                    dispatch_interval,
                    energy_price,
                    regulation_raise_price,
                    regulation_lower_price,
                    contingency_raise_price,
                    contingency_lower_price,
                    rocof_price,
                    available_regulation_raise,
                    available_regulation_lower,
                    available_contingency_raise,
                    available_contingency_lower,
                    available_rocof,
                    in_service_regulation_raise,
                    in_service_regulation_lower,
                    in_service_contingency_raise,
                    in_service_contingency_lower,
                    in_service_rocof,
                    requirement_regulation_raise,
                    requirement_regulation_lower,
                    requirement_contingency_raise,
                    requirement_contingency_lower,
                    requirement_rocof,
                    shortfall_regulation_raise,
                    shortfall_regulation_lower,
                    shortfall_contingency_raise,
                    shortfall_contingency_lower,
                    shortfall_rocof,
                    dispatch_total_regulation_raise,
                    dispatch_total_regulation_lower,
                    dispatch_total_contingency_raise,
                    dispatch_total_contingency_lower,
                    dispatch_total_rocof,
                    capped_regulation_raise,
                    capped_regulation_lower,
                    capped_contingency_raise,
                    capped_contingency_lower,
                    capped_rocof
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "2026-04-13 08:00:00",
                    96.12,
                    15.0,
                    11.0,
                    6.0,
                    4.0,
                    3.0,
                    435.296,
                    437.024,
                    329.771,
                    331.636,
                    5966.0,
                    979.74,
                    979.74,
                    980.4,
                    1055.398,
                    12124.5,
                    110.0,
                    110.0,
                    258.268,
                    72.308,
                    12124.5,
                    3.0,
                    0.0,
                    4.0,
                    0.0,
                    0.0,
                    110.0,
                    110.0,
                    268.853,
                    72.308,
                    12124.5,
                    1,
                    0,
                    0,
                    0,
                    0,
                ),
            )
            conn.execute(
                f"""
                INSERT INTO {self.db.WEM_ESS_CONSTRAINT_TABLE} (
                    dispatch_interval,
                    binding_count,
                    near_binding_count,
                    binding_max_shadow_price,
                    near_binding_max_shadow_price,
                    max_formulation_shadow_price,
                    max_facility_shadow_price,
                    max_network_shadow_price,
                    max_generic_shadow_price
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                ("2026-04-13 08:00:00", 1, 2, 96.12, 96.12, 96.12, 0.0, 0.0, 0.0),
            )
            conn.commit()

        result = server.get_fcas_analysis(
            year=2026,
            region="WEM",
            aggregation="daily",
            capacity_mw=100,
        )

        self.assertIn("scarcity_score", result["summary"])
        self.assertIn("opportunity_score", result["summary"])
        self.assertIn("quality_score", result["summary"])
        self.assertIn("preview_caveat", result["summary"])
        self.assertGreaterEqual(result["summary"]["scarcity_score"], 0)
        self.assertLessEqual(result["summary"]["scarcity_score"], 100)
        self.assertIn("preview", result["summary"]["preview_caveat"].lower())


if __name__ == "__main__":
    unittest.main()
