from __future__ import annotations

import json
from datetime import datetime, timezone
from urllib import request


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def default_webhook_sender(url: str, payload: dict) -> dict:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
    with request.urlopen(req, timeout=10) as response:
        text = response.read().decode("utf-8", errors="replace")
        return {"status_code": response.status, "response_text": text[:1000]}


def _latest_nem_price(db, region: str) -> dict | None:
    with db.get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name LIKE 'trading_price_%' ORDER BY name DESC")
        tables = [row[0] for row in cursor.fetchall()]
        for table_name in tables:
            row = conn.execute(
                f"""
                SELECT settlement_date, region_id, rrp_aud_mwh
                FROM {table_name}
                WHERE region_id = ?
                ORDER BY settlement_date DESC
                LIMIT 1
                """,
                (region,),
            ).fetchone()
            if row:
                return {"settlement_date": row[0], "region_id": row[1], "price": float(row[2] or 0.0), "table_name": table_name}
    return None


def _freshness_minutes(db) -> float | None:
    last_update = db.get_last_update_time()
    if not last_update:
        return None
    parsed = datetime.fromisoformat(last_update.replace("Z", "+00:00")) if "T" in last_update else datetime.strptime(last_update, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    return max(0.0, (_utc_now() - parsed.astimezone(timezone.utc)).total_seconds() / 60.0)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _wem_scarcity_score(db) -> float:
    with db.get_connection() as conn:
        db.ensure_wem_ess_tables(conn)
        cursor = conn.cursor()
        row = cursor.execute(
            f"""
            SELECT AVG(COALESCE(shortfall_regulation_raise, 0) + COALESCE(shortfall_contingency_raise, 0)),
                   AVG(COALESCE(binding_count, 0)),
                   MAX(COALESCE(binding_max_shadow_price, 0))
            FROM {db.WEM_ESS_MARKET_TABLE} m
            LEFT JOIN {db.WEM_ESS_CONSTRAINT_TABLE} c ON c.dispatch_interval = m.dispatch_interval
            """
        ).fetchone()
    shortfall_avg = float(row[0] or 0.0)
    binding_avg = float(row[1] or 0.0)
    shadow_max = float(row[2] or 0.0)
    return max(0.0, min(100.0, shortfall_avg * 6.0 + binding_avg * 10.0 + shadow_max / 8.0))


def evaluate_rule(db, rule: dict) -> dict:
    config = rule.get("config") or {}
    rule_type = rule["rule_type"]

    if rule_type == "price_threshold":
        latest = _latest_nem_price(db, rule["region_or_zone"])
        if not latest:
            return {"triggered": False, "value": None, "reason": "no_price_data"}
        operator = config.get("operator", "gt")
        threshold = float(config.get("threshold", 0))
        value = latest["price"]
        triggered = value > threshold if operator == "gt" else value < threshold
        return {"triggered": triggered, "value": value, "context": latest}

    if rule_type == "data_freshness":
        freshness = _freshness_minutes(db)
        threshold_minutes = float(config.get("threshold_minutes", 0))
        triggered = freshness is not None and freshness > threshold_minutes
        return {"triggered": triggered, "value": freshness, "context": {"threshold_minutes": threshold_minutes}}

    if rule_type == "wem_fcas_scarcity":
        score = _wem_scarcity_score(db)
        threshold_score = float(config.get("threshold_score", 0))
        return {"triggered": score > threshold_score, "value": score, "context": {"threshold_score": threshold_score}}

    raise ValueError(f"Unsupported alert rule_type: {rule_type}")


def evaluate_alert_rules(db, *, sender=None, workspace_id: str | None = None) -> dict:
    sender = sender or default_webhook_sender
    rules = db.fetch_alert_rules(enabled_only=True, workspace_id=workspace_id)
    evaluated = 0
    triggered = 0
    sent = 0
    now_iso = _utc_now_iso()

    for rule in rules:
        evaluated += 1
        result = evaluate_rule(db, rule)
        previous_state = db.fetch_alert_state(rule["rule_id"])
        previous_status = previous_state["current_status"] if previous_state else "ok"
        current_status = "triggered" if result["triggered"] else "ok"

        state_payload = {
            "rule_id": rule["rule_id"],
            "current_status": current_status,
            "last_evaluated_at": now_iso,
            "last_triggered_at": now_iso if result["triggered"] else (previous_state or {}).get("last_triggered_at"),
            "last_delivery_at": (previous_state or {}).get("last_delivery_at"),
            "organization_id": rule.get("organization_id"),
            "workspace_id": rule.get("workspace_id"),
            "last_value": result,
        }

        if result["triggered"]:
            triggered += 1

        if result["triggered"] and previous_status != "triggered":
            delivery_payload = {
                "rule_id": rule["rule_id"],
                "rule_name": rule["name"],
                "rule_type": rule["rule_type"],
                "market": rule["market"],
                "region_or_zone": rule.get("region_or_zone"),
                "result": result,
                "evaluated_at": now_iso,
            }
            response = sender(rule["channel_target"], delivery_payload)
            sent += 1
            db.insert_alert_delivery_log(
                {
                    "rule_id": rule["rule_id"],
                    "delivery_status": "sent",
                    "target": rule["channel_target"],
                    "payload": delivery_payload,
                    "response_code": response.get("status_code"),
                    "response_text": response.get("response_text"),
                    "organization_id": rule.get("organization_id"),
                    "workspace_id": rule.get("workspace_id"),
                    "delivered_at": now_iso,
                }
            )
            state_payload["last_delivery_at"] = now_iso

        db.upsert_alert_state(state_payload)

    return {
        "evaluated_rule_count": evaluated,
        "triggered_rule_count": triggered,
        "sent_delivery_count": sent,
    }
