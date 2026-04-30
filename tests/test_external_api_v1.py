import os
import tempfile
import unittest

from fastapi import HTTPException

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
from external_api_v1 import (
    authenticate_external_api_key,
    build_external_api_billing_ledger,
    build_external_api_billing_summary,
    build_external_sla_status,
    check_external_api_quota,
    meter_external_api_usage,
    paginate_items,
    seed_external_api_client,
    summarize_external_api_quota,
    seed_external_api_client,
    wrap_external_response,
)


class ExternalApiV1Tests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)

    def tearDown(self):
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def test_authenticate_external_api_key_rejects_missing_key(self):
        with self.assertRaises(HTTPException) as ctx:
            authenticate_external_api_key(self.db, None)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_authenticate_external_api_key_accepts_seeded_client(self):
        self.db.upsert_organization(
            {
                "organization_id": "org_1",
                "name": "Acme Energy",
                "created_at": "2026-04-27T00:00:00Z",
                "updated_at": "2026-04-27T00:00:00Z",
            }
        )
        self.db.upsert_workspace(
            {
                "workspace_id": "ws_1",
                "organization_id": "org_1",
                "name": "Primary",
                "created_at": "2026-04-27T00:00:00Z",
                "updated_at": "2026-04-27T00:00:00Z",
            }
        )
        seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Test Client",
            plan="internal",
            organization_id="org_1",
            workspace_id="ws_1",
        )

        client = authenticate_external_api_key(self.db, "test-key")
        self.assertEqual(client["client_id"], "client-1")
        self.assertEqual(client["plan"], "internal")
        self.assertEqual(client["organization_id"], "org_1")
        self.assertEqual(client["workspace_id"], "ws_1")

    def test_paginate_items_returns_items_and_next_offset(self):
        payload = paginate_items(list(range(10)), offset=2, limit=3)
        self.assertEqual(payload["items"], [2, 3, 4])
        self.assertEqual(payload["pagination"]["offset"], 2)
        self.assertEqual(payload["pagination"]["limit"], 3)
        self.assertEqual(payload["pagination"]["returned"], 3)
        self.assertEqual(payload["pagination"]["total"], 10)
        self.assertEqual(payload["pagination"]["next_offset"], 5)

    def test_meter_external_api_usage_persists_usage_row(self):
        seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Test Client",
            plan="internal",
        )

        meter_external_api_usage(
            self.db,
            client_id="client-1",
            endpoint="/api/v1/prices",
            http_method="GET",
            status_code=200,
            request_units=3,
            latency_ms=28,
            api_version="v1",
        )

        rows = self.db.fetch_external_api_usage(client_id="client-1")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["endpoint"], "/api/v1/prices")
        self.assertEqual(rows[0]["request_units"], 3)

    def test_build_external_sla_status_reports_job_and_data_summary(self):
        self.db.set_last_update_time("2026-04-27 10:00:00")
        sla = build_external_sla_status(self.db, api_version="v1")

        self.assertEqual(sla["api_version"], "v1")
        self.assertIn(sla["status"], {"operational", "degraded"})
        self.assertIn("job_summary", sla)
        self.assertIn("freshness", sla)

    def test_wrap_external_response_adds_version_contract(self):
        response = wrap_external_response(
            endpoint="prices",
            data={"items": [1, 2]},
            api_version="v1",
            pagination={"offset": 0, "limit": 2, "returned": 2, "total": 2, "next_offset": None},
            meta={"plan": "internal"},
        )

        self.assertEqual(response["api_version"], "v1")
        self.assertEqual(response["endpoint"], "prices")
        self.assertEqual(response["data"]["items"], [1, 2])
        self.assertEqual(response["pagination"]["total"], 2)
        self.assertEqual(response["meta"]["plan"], "internal")

    def test_check_external_api_quota_rejects_when_daily_unit_limit_is_exceeded(self):
        seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Test Client",
            plan="starter",
        )
        for _ in range(10):
            meter_external_api_usage(
                self.db,
                client_id="client-1",
                endpoint="/api/v1/prices",
                http_method="GET",
                status_code=200,
                request_units=100,
                latency_ms=20,
                api_version="v1",
            )

        client = self.db.fetch_external_api_client("client-1")
        with self.assertRaises(HTTPException) as ctx:
            check_external_api_quota(self.db, client=client, request_units=1)

        self.assertEqual(ctx.exception.status_code, 429)
        self.assertEqual(ctx.exception.detail["code"], "quota_exceeded")

    def test_summarize_external_api_quota_reports_plan_limit_usage_and_remaining(self):
        seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Test Client",
            plan="starter",
        )
        meter_external_api_usage(
            self.db,
            client_id="client-1",
            endpoint="/api/v1/prices",
            http_method="GET",
            status_code=200,
            request_units=250,
            latency_ms=20,
            api_version="v1",
        )

        client = self.db.fetch_external_api_client("client-1")
        quota = summarize_external_api_quota(self.db, client=client)

        self.assertEqual(quota["plan"], "starter")
        self.assertEqual(quota["daily_unit_limit"], 1000)
        self.assertEqual(quota["used_units"], 250)
        self.assertEqual(quota["remaining_units"], 750)

    def test_build_external_api_billing_summary_groups_usage_by_client_with_quota_snapshot(self):
        seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Starter Client",
            plan="starter",
        )
        meter_external_api_usage(
            self.db,
            client_id="client-1",
            endpoint="/api/v1/prices",
            http_method="GET",
            status_code=200,
            request_units=200,
            latency_ms=20,
            api_version="v1",
        )
        meter_external_api_usage(
            self.db,
            client_id="client-1",
            endpoint="/api/v1/events",
            http_method="GET",
            status_code=429,
            request_units=50,
            latency_ms=25,
            api_version="v1",
        )

        payload = build_external_api_billing_summary(self.db)

        self.assertEqual(payload["totals"]["request_units"], 250)
        self.assertEqual(payload["totals"]["request_count"], 2)
        self.assertEqual(payload["items"][0]["client_id"], "client-1")
        self.assertEqual(payload["items"][0]["quota"]["remaining_units"], 750)
        self.assertEqual(payload["items"][0]["success_count"], 1)
        self.assertEqual(payload["items"][0]["non_success_count"], 1)

    def test_build_external_api_billing_ledger_returns_recent_usage_rows_with_estimated_cost(self):
        seed_external_api_client(
            self.db,
            client_id="client-1",
            api_key="test-key",
            client_name="Starter Client",
            plan="starter",
        )
        meter_external_api_usage(
            self.db,
            client_id="client-1",
            endpoint="/api/v1/prices",
            http_method="GET",
            status_code=200,
            request_units=250,
            latency_ms=20,
            api_version="v1",
        )

        payload = build_external_api_billing_ledger(self.db, client_id="client-1", limit=10)

        self.assertEqual(payload["items"][0]["client_id"], "client-1")
        self.assertEqual(payload["items"][0]["request_units"], 250)
        self.assertEqual(payload["items"][0]["plan"], "starter")
        self.assertGreaterEqual(payload["items"][0]["estimated_cost_usd"], 0)
