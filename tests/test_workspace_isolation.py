import os
import sys
import tempfile
import types
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

sys.modules.setdefault("pulp", types.SimpleNamespace())
sys.modules.setdefault("numpy_financial", types.SimpleNamespace())

from database import DatabaseManager
import server


class WorkspaceIsolationTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        self.original_orchestrator_db = server.job_orchestrator.db
        server.db = self.db
        server.job_orchestrator.db = self.db

        self.db.upsert_organization({"organization_id": "org_a", "name": "Org A", "created_at": "2026-04-27T00:00:00Z", "updated_at": "2026-04-27T00:00:00Z"})
        self.db.upsert_workspace({"workspace_id": "ws_a", "organization_id": "org_a", "name": "WS A", "created_at": "2026-04-27T00:00:00Z", "updated_at": "2026-04-27T00:00:00Z"})
        self.db.upsert_organization({"organization_id": "org_b", "name": "Org B", "created_at": "2026-04-27T00:00:00Z", "updated_at": "2026-04-27T00:00:00Z"})
        self.db.upsert_workspace({"workspace_id": "ws_b", "organization_id": "org_b", "name": "WS B", "created_at": "2026-04-27T00:00:00Z", "updated_at": "2026-04-27T00:00:00Z"})

        server.seed_external_api_client(self.db, client_id="client-a", api_key="key-a", client_name="Client A", plan="internal", organization_id="org_a", workspace_id="ws_a")
        server.seed_external_api_client(self.db, client_id="client-b", api_key="key-b", client_name="Client B", plan="internal", organization_id="org_b", workspace_id="ws_b")

    def tearDown(self):
        server.db = self.original_db
        server.job_orchestrator.db = self.original_orchestrator_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_v1_client_cannot_read_job_from_other_workspace(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )

        with self.assertRaises(HTTPException) as ctx:
            server.get_v1_job(job_id=job["job_id"], x_api_key="key-b")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_v1_client_can_read_own_workspace_job(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )

        payload = server.get_v1_job(job_id=job["job_id"], x_api_key="key-a")
        self.assertEqual(payload["data"]["job"]["job_id"], job["job_id"])
        self.assertEqual(payload["meta"]["workspace_id"], "ws_a")

    def test_v1_client_job_list_is_filtered_to_own_workspace(self):
        server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="QLD1",
            month="04",
            workspace_id="ws_b",
            organization_id="org_b",
        )

        payload = server.list_v1_jobs(x_api_key="key-a", limit=100)
        self.assertEqual(len(payload["data"]["items"]), 1)
        self.assertEqual(payload["data"]["items"][0]["workspace_id"], "ws_a")

    def test_v1_client_cannot_read_lineage_from_other_workspace(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )

        with self.assertRaises(HTTPException) as ctx:
            server.get_v1_job_lineage(job_id=job["job_id"], x_api_key="key-b")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_job_route_rejects_other_workspace_access_scope(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        scope = {
            "organization_id": "org_b",
            "workspace_id": "ws_b",
            "allowed_regions": [],
            "allowed_markets": [],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_job_route(job["job_id"], access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_job_list_is_filtered_by_access_scope(self):
        server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="QLD1",
            month="04",
            workspace_id="ws_b",
            organization_id="org_b",
        )
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": [],
            "allowed_markets": [],
        }
        payload = server.list_jobs_route(status=None, queue_name=None, limit=100, access_scope=scope)
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["workspace_id"], "ws_a")

    def test_internal_job_lineage_rejects_other_workspace_access_scope(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        scope = {
            "organization_id": "org_b",
            "workspace_id": "ws_b",
            "allowed_regions": [],
            "allowed_markets": [],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_job_lineage_route(job["job_id"], access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_job_events_reject_other_workspace_access_scope(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        scope = {
            "organization_id": "org_b",
            "workspace_id": "ws_b",
            "allowed_regions": [],
            "allowed_markets": [],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_job_events_route(job["job_id"], access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_job_cancel_rejects_other_workspace_access_scope(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        scope = {
            "organization_id": "org_b",
            "workspace_id": "ws_b",
            "allowed_regions": [],
            "allowed_markets": [],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.cancel_job_route(job["job_id"], access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_job_retry_rejects_other_workspace_access_scope(self):
        job = server.enqueue_report_generation_job(
            report_type="monthly_market_report",
            year=2025,
            region="NSW1",
            month="04",
            workspace_id="ws_a",
            organization_id="org_a",
        )
        server.cancel_job_route(job["job_id"])
        scope = {
            "organization_id": "org_b",
            "workspace_id": "ws_b",
            "allowed_regions": [],
            "allowed_markets": [],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.retry_job_route(job["job_id"], access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_v1_prices_route_rejects_region_outside_workspace_policy(self):
        self.db.upsert_workspace_policy(
            {
                "workspace_id": "ws_a",
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

        with self.assertRaises(HTTPException) as ctx:
            server.get_v1_prices(year=2025, region="QLD1", x_api_key="key-a", offset=0, limit=10)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_v1_events_route_rejects_market_outside_workspace_policy(self):
        self.db.upsert_workspace_policy(
            {
                "workspace_id": "ws_a",
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

        with self.assertRaises(HTTPException) as ctx:
            server.get_v1_events(year=2025, region="WEM", market="WEM", x_api_key="key-a", offset=0, limit=10)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_v1_data_quality_route_rejects_market_outside_workspace_policy(self):
        self.db.upsert_workspace_policy(
            {
                "workspace_id": "ws_a",
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )

        with self.assertRaises(HTTPException) as ctx:
            server.get_v1_data_quality(market="WEM", issue_offset=0, issue_limit=10, x_api_key="key-a")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_internal_query_guard_rejects_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server._assert_scope_allows_internal_query(scope, region="QLD1", market="NEM")
        self.assertEqual(ctx.exception.status_code, 403)

    def test_client_access_scope_uses_workspace_policy(self):
        self.db.upsert_workspace_policy(
            {
                "workspace_id": "ws_a",
                "allowed_regions_json": ["NSW1"],
                "allowed_markets_json": ["NEM"],
                "updated_at": "2026-04-28T00:00:00Z",
            }
        )
        scope = server._build_client_access_scope(
            {
                "organization_id": "org_a",
                "workspace_id": "ws_a",
            }
        )
        self.assertEqual(scope["workspace_id"], "ws_a")
        self.assertIn("NSW1", scope["allowed_regions"])
        self.assertIn("NEM", scope["allowed_markets"])

    def test_price_trend_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_price_trend(year=2025, region="QLD1", limit=10, access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_event_overlays_reject_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_event_overlays(year=2025, region="WEM", market="WEM", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_fcas_analysis_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_fcas_analysis(year=2025, region="WEM", aggregation="daily", capacity_mw=100, access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_data_quality_issues_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_data_quality_issues(market="WEM", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_grid_forecast_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_grid_forecast(market="WEM", region="WEM", horizon="24h", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_grid_forecast_coverage_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_grid_forecast_coverage(market="WEM", region="WEM", horizon="24h", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_peak_analysis_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_peak_analysis(year=2025, region="WEM", aggregation="monthly", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_hourly_profile_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_hourly_price_profile(year=2025, region="WEM", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bess_backtest_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        params = server.BessBacktestParams(
            market="WEM",
            region="WEM",
            year=2025,
            power_mw=1.0,
            energy_mwh=2.0,
            duration_hours=2.0,
        )
        with self.assertRaises(HTTPException) as ctx:
            server.run_bess_backtest(params, access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_bess_backtest_coverage_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        with self.assertRaises(HTTPException) as ctx:
            server.get_bess_backtest_coverage(market="WEM", region="WEM", year=2025, access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)

    def test_investment_analysis_rejects_internal_scope_violation(self):
        scope = {
            "organization_id": "org_a",
            "workspace_id": "ws_a",
            "allowed_regions": ["NSW1"],
            "allowed_markets": ["NEM"],
        }
        params = server.InvestmentParams(region="WEM", power_mw=100, duration_hours=4, backtest_years=[2025])
        with self.assertRaises(HTTPException) as ctx:
            server.investment_analysis(params, access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)
