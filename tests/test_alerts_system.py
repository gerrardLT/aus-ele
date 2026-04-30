import os
import tempfile
import unittest

from tests.support import ensure_repo_import_paths

ensure_repo_import_paths()

from database import DatabaseManager
import server
from fastapi import HTTPException


class FakeWebhookSender:
    def __init__(self):
        self.calls = []

    def __call__(self, url: str, payload: dict):
        self.calls.append((url, payload))
        return {"status_code": 200, "response_text": "ok"}


class AlertSystemTests(unittest.TestCase):
    def setUp(self):
        handle, self.db_path = tempfile.mkstemp(suffix=".db")
        os.close(handle)
        self.db = DatabaseManager(self.db_path)
        self.original_db = server.db
        server.db = self.db

    def tearDown(self):
        server.db = self.original_db
        if os.path.exists(self.db_path):
            os.remove(self.db_path)

    def _seed_nem_price(self):
        self.db.batch_insert(
            [
                {
                    "settlement_date": "2025-01-01 00:00:00",
                    "region_id": "NSW1",
                    "rrp_aud_mwh": 650.0,
                    "raise1sec_rrp": 0.0,
                    "raise6sec_rrp": 0.0,
                    "raise60sec_rrp": 0.0,
                    "raise5min_rrp": 0.0,
                    "raisereg_rrp": 0.0,
                    "lower1sec_rrp": 0.0,
                    "lower6sec_rrp": 0.0,
                    "lower60sec_rrp": 0.0,
                    "lower5min_rrp": 0.0,
                    "lowerreg_rrp": 0.0,
                }
            ]
        )
        self.db.set_last_update_time("2025-01-01 00:10:00")

    def _seed_wem_scarcity(self):
        with self.db.get_connection() as conn:
            self.db.ensure_wem_ess_tables(conn)
            conn.execute(
                f"""
                INSERT INTO {self.db.WEM_ESS_MARKET_TABLE} (
                    dispatch_interval, energy_price, regulation_raise_price, regulation_lower_price,
                    contingency_raise_price, contingency_lower_price, rocof_price,
                    available_regulation_raise, available_regulation_lower,
                    available_contingency_raise, available_contingency_lower, available_rocof,
                    in_service_regulation_raise, in_service_regulation_lower,
                    in_service_contingency_raise, in_service_contingency_lower, in_service_rocof,
                    requirement_regulation_raise, requirement_regulation_lower,
                    requirement_contingency_raise, requirement_contingency_lower, requirement_rocof,
                    shortfall_regulation_raise, shortfall_regulation_lower,
                    shortfall_contingency_raise, shortfall_contingency_lower, shortfall_rocof,
                    dispatch_total_regulation_raise, dispatch_total_regulation_lower,
                    dispatch_total_contingency_raise, dispatch_total_contingency_lower, dispatch_total_rocof,
                    capped_regulation_raise, capped_regulation_lower, capped_contingency_raise,
                    capped_contingency_lower, capped_rocof
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
                """,
                (
                    "2025-01-01 08:00:00", 95.0, 15.0, 11.0, 6.0, 4.0, 3.0,
                    100.0, 100.0, 100.0, 100.0, 100.0,
                    100.0, 100.0, 100.0, 100.0, 100.0,
                    500.0, 500.0, 500.0, 500.0, 500.0,
                    10.0, 0.0, 10.0, 0.0, 0.0,
                    80.0, 80.0, 80.0, 80.0, 80.0,
                    1, 1, 1, 0, 0,
                ),
            )
            conn.commit()

    def test_alert_rules_can_be_created_evaluated_and_logged(self):
        self._seed_nem_price()
        sender = FakeWebhookSender()

        price_rule = server.create_alert_rule(
            server.AlertRuleUpsert(
                name="NSW1 high price",
                rule_type="price_threshold",
                market="NEM",
                region_or_zone="NSW1",
                config={"operator": "gt", "threshold": 500},
                channel_type="webhook",
                channel_target="https://example.com/hook",
            )
        )

        evaluation = server.evaluate_alert_rules(sender=sender)

        self.assertEqual(price_rule["rule_type"], "price_threshold")
        self.assertEqual(evaluation["evaluated_rule_count"], 1)
        self.assertEqual(evaluation["triggered_rule_count"], 1)
        self.assertEqual(len(sender.calls), 1)

        rules = server.list_alert_rules()
        states = server.list_alert_states()
        logs = server.list_alert_delivery_logs()

        self.assertEqual(len(rules["items"]), 1)
        self.assertEqual(states["items"][0]["current_status"], "triggered")
        self.assertEqual(logs["items"][0]["delivery_status"], "sent")

    def test_freshness_and_wem_scarcity_rules_are_supported(self):
        self._seed_nem_price()
        self._seed_wem_scarcity()
        sender = FakeWebhookSender()

        server.create_alert_rule(
            server.AlertRuleUpsert(
                name="NEM freshness delayed",
                rule_type="data_freshness",
                market="NEM",
                region_or_zone="NSW1",
                config={"threshold_minutes": 5},
                channel_type="webhook",
                channel_target="https://example.com/hook-1",
            )
        )
        server.create_alert_rule(
            server.AlertRuleUpsert(
                name="WEM scarcity spike",
                rule_type="wem_fcas_scarcity",
                market="WEM",
                region_or_zone="WEM",
                config={"threshold_score": 70},
                channel_type="webhook",
                channel_target="https://example.com/hook-2",
            )
        )

        evaluation = server.evaluate_alert_rules(sender=sender)

        self.assertEqual(evaluation["evaluated_rule_count"], 2)
        self.assertEqual(evaluation["triggered_rule_count"], 2)
        self.assertEqual(len(sender.calls), 2)

    def test_alert_reads_and_evaluation_can_be_scoped_to_workspace(self):
        self._seed_nem_price()
        sender = FakeWebhookSender()

        server.create_alert_rule(
            server.AlertRuleUpsert(
                name="Scoped A",
                rule_type="price_threshold",
                market="NEM",
                region_or_zone="NSW1",
                config={"operator": "gt", "threshold": 500},
                channel_type="webhook",
                channel_target="https://example.com/hook-a",
                organization_id="org_a",
                workspace_id="ws_a",
            )
        )
        server.create_alert_rule(
            server.AlertRuleUpsert(
                name="Scoped B",
                rule_type="price_threshold",
                market="NEM",
                region_or_zone="NSW1",
                config={"operator": "gt", "threshold": 500},
                channel_type="webhook",
                channel_target="https://example.com/hook-b",
                organization_id="org_b",
                workspace_id="ws_b",
            )
        )

        evaluation = server.evaluate_alert_rules(sender=sender, workspace_id="ws_a")
        rules = server.list_alert_rules(workspace_id="ws_a")
        states = server.list_alert_states(workspace_id="ws_a")
        logs = server.list_alert_delivery_logs(workspace_id="ws_a")

        self.assertEqual(evaluation["evaluated_rule_count"], 1)
        self.assertEqual(len(sender.calls), 1)
        self.assertEqual(len(rules["items"]), 1)
        self.assertEqual(rules["items"][0]["workspace_id"], "ws_a")
        self.assertEqual(len(states["items"]), 1)
        self.assertEqual(states["items"][0]["workspace_id"], "ws_a")
        self.assertEqual(len(logs["items"]), 1)
        self.assertEqual(logs["items"][0]["workspace_id"], "ws_a")

    def test_alert_reads_default_to_access_scope_workspace(self):
        self._seed_nem_price()
        server.create_alert_rule(
            server.AlertRuleUpsert(
                name="Scoped A",
                rule_type="price_threshold",
                market="NEM",
                region_or_zone="NSW1",
                config={"operator": "gt", "threshold": 500},
                channel_type="webhook",
                channel_target="https://example.com/hook-a",
                organization_id="org_a",
                workspace_id="ws_a",
            )
        )
        server.create_alert_rule(
            server.AlertRuleUpsert(
                name="Scoped B",
                rule_type="price_threshold",
                market="NEM",
                region_or_zone="NSW1",
                config={"operator": "gt", "threshold": 500},
                channel_type="webhook",
                channel_target="https://example.com/hook-b",
                organization_id="org_b",
                workspace_id="ws_b",
            )
        )
        scope = {"organization_id": "org_a", "workspace_id": "ws_a"}

        rules = server.list_alert_rules(access_scope=scope)
        states = server.list_alert_states(access_scope=scope)
        logs = server.list_alert_delivery_logs(access_scope=scope)

        self.assertEqual(len(rules["items"]), 1)
        self.assertEqual(rules["items"][0]["workspace_id"], "ws_a")
        self.assertEqual(states["items"], [])
        self.assertEqual(logs["items"], [])

    def test_alert_reads_reject_workspace_scope_mismatch(self):
        scope = {"organization_id": "org_a", "workspace_id": "ws_a"}

        with self.assertRaises(HTTPException) as ctx:
            server.list_alert_rules(workspace_id="ws_b", access_scope=scope)
        self.assertEqual(ctx.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
