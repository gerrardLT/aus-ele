import csv
import datetime as dt
import hashlib
import io
import json
import logging
import re
from collections import defaultdict

import requests


logger = logging.getLogger(__name__)

NEM_REGIONS = ["NSW1", "QLD1", "SA1", "TAS1", "VIC1"]
STATE_TO_REGIONS = {
    "NSW": ["NSW1"],
    "QLD": ["QLD1"],
    "SA": ["SA1"],
    "TAS": ["TAS1"],
    "VIC": ["VIC1"],
    "WA": ["WEM"],
}
REGION_TO_STATE = {
    "NSW1": "NSW",
    "QLD1": "QLD",
    "SA1": "SA",
    "TAS1": "TAS",
    "VIC1": "VIC",
    "WEM": "WA",
}
BOM_AREA_CODES = {
    "NSW": "NSW_FA001",
    "QLD": "QLD_FA001",
    "SA": "SA_FA001",
    "TAS": "TAS_FA001",
    "VIC": "VIC_FA001",
    "WA": "WA_FA001",
}

STATE_LABELS = {
    "reserve_tightness": "Reserve Tightness",
    "security_intervention": "Security Intervention",
    "network_stress": "Network Stress",
    "supply_shock": "Supply Shock",
    "demand_weather_shock": "Demand / Weather Shock",
    "post_event_structural": "Post-event / Structural",
}

IMPACT_DOMAINS_BY_STATE = {
    "reserve_tightness": ["price_trend", "peak_analysis", "fcas_analysis", "revenue_stacking", "cycle_cost"],
    "security_intervention": ["price_trend", "fcas_analysis", "revenue_stacking", "cycle_cost"],
    "network_stress": ["price_trend", "peak_analysis", "revenue_stacking", "cycle_cost"],
    "supply_shock": ["price_trend", "peak_analysis", "fcas_analysis", "revenue_stacking", "cycle_cost"],
    "demand_weather_shock": ["price_trend", "peak_analysis", "cycle_cost"],
    "post_event_structural": ["price_trend"],
}

NEM_REQUIRED_SOURCES = {"nem_market_notice", "nem_high_impact_outage", "bom_warnings"}
WEM_CORE_SOURCES = {"wem_dispatch_advisory", "wem_realtime_outage", "bom_warnings"}

NEM_MARKET_NOTICE_LISTING_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/Market_Notice/"
NEM_HIGH_IMPACT_OUTAGES_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/HighImpactOutages/"
WEM_DISPATCH_ADVISORY_CSV_URL = "https://data.wa.aemo.com.au/public/public-data/datafiles/dispatch-advisory/dispatch-advisory.csv"
WEM_REALTIME_OUTAGES_CSV_URL = "https://data.wa.aemo.com.au/public/public-data/datafiles/realtime-outages/realtime-outages.csv"
BOM_WARNINGS_LIST_URL = "https://api.bom.gov.au/apikey/v1/warnings/list?area_type=aac&area_code={area_code}"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    )
}


def infer_market(region: str | None = None, market: str | None = None) -> str:
    if market in {"NEM", "WEM"}:
        return market
    return "WEM" if region == "WEM" else "NEM"


def _parse_datetime(value: str | None, *formats: str) -> str | None:
    if not value:
        return None
    normalized = " ".join(str(value).strip().split())
    for fmt in formats:
        try:
            parsed = dt.datetime.strptime(normalized, fmt)
            return parsed.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            continue
    return None


def _state_label(state_key: str) -> str:
    return STATE_LABELS.get(state_key, state_key.replace("_", " ").title())


def _extract_regions(text: str | None, market: str) -> list[str]:
    if market == "WEM":
        return ["WEM"]

    text_upper = (text or "").upper()
    regions = set(re.findall(r"\b(?:NSW1|QLD1|SA1|TAS1|VIC1)\b", text_upper))
    for state_code, state_regions in STATE_TO_REGIONS.items():
        if state_code == "WA":
            continue
        if re.search(rf"\b{state_code}\b", text_upper):
            regions.update(state_regions)
    return sorted(regions) if regions else list(NEM_REGIONS)


def _normalize_severity(text: str | None) -> str:
    haystack = (text or "").upper()
    if any(token in haystack for token in ["LOR3", "LOAD SHEDDING", "BLACK SYSTEM", "EMERGENCY"]):
        return "high"
    if any(token in haystack for token in ["LOR2", "INTERVENTION", "DIRECTION", "SYSTEM SECURITY", "FORCED"]):
        return "high"
    if any(token in haystack for token in ["LOR1", "OUTAGE", "CONSTRAINT", "TRIP", "SEVERE WEATHER", "FIRE WEATHER", "HEATWAVE"]):
        return "medium"
    return "low"


def _classify_state_types(text: str | None) -> list[str]:
    haystack = (text or "").upper()
    state_types = []

    if any(token in haystack for token in ["LOR1", "LOR2", "LOR3", "RESERVE NOTICE", "LOW RESERVE", "RESERVE CONDITION"]):
        state_types.append("reserve_tightness")
    if any(token in haystack for token in ["DIRECTION", "INTERVENTION", "SYSTEM SECURITY", "RECLASSIFICATION", "MARKET SUSPENSION", "LOAD SHEDDING"]):
        state_types.append("security_intervention")
    if any(token in haystack for token in ["OUTAGE", "INTERCONNECTOR", "LINE", "TRANSFORMER", "NETWORK", "CONSTRAINT", "TRANSMISSION"]):
        state_types.append("network_stress")
    if any(token in haystack for token in ["GENERATOR", "UNIT", "AVAILABILITY", "FORCED", "TRIP", "FACILITY", "OUT OF MERIT", "OUTAGE (MW)"]):
        state_types.append("supply_shock")
    if any(token in haystack for token in ["HEATWAVE", "FIRE WEATHER", "BUSHFIRE", "SEVERE WEATHER", "THUNDERSTORM", "CYCLONE", "STORM", "DEMAND"]):
        state_types.append("demand_weather_shock")
    if any(token in haystack for token in ["REPORT", "REVIEW", "INVESTIGATION", "FACT SHEET", "POST EVENT", "POST-EVENT"]):
        state_types.append("post_event_structural")

    return state_types


def _confidence_for_source(source: str) -> float:
    if source in {"nem_high_impact_outage", "wem_realtime_outage", "bom_warnings"}:
        return 0.9
    if source == "wem_dispatch_advisory":
        return 0.85
    return 0.75


def _state_id(*parts: str) -> str:
    joined = "|".join(parts)
    return "evt-" + hashlib.sha1(joined.encode("utf-8")).hexdigest()[:16]


def _collapse_multiline(value: str | None) -> str:
    return " ".join((value or "").replace("\r", " ").replace("\n", " ").split())


def parse_nem_market_notice_report(raw_notice: str, source_url: str) -> dict:
    def field(name: str) -> str | None:
        match = re.search(rf"^\s*{re.escape(name)}\s*:\s*(.*?)\s*$", raw_notice, flags=re.MULTILINE)
        return match.group(1).strip() if match else None

    notice_id = field("Notice ID")
    creation_date = field("Creation Date")
    issue_date = field("Issue Date")
    notice_type_id = field("Notice Type ID")
    notice_type_desc = field("Notice Type Description")
    external_reference = field("External Reference")

    body_match = re.search(r"Reason\s*:\s*(.*?)(?:END OF REPORT)", raw_notice, flags=re.DOTALL | re.IGNORECASE)
    body = body_match.group(1).strip() if body_match else ""
    body = re.sub(r"-{3,}", "", body).strip()

    summary = body or external_reference or notice_type_desc or "AEMO market notice"
    regions = _extract_regions(" ".join(filter(None, [external_reference, summary])), "NEM")
    published_at = _parse_datetime(creation_date, "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %I:%M:%S %p")
    effective_time = _parse_datetime(issue_date, "%d/%m/%Y")
    effective_start = published_at or effective_time

    return {
        "market": "NEM",
        "source": "nem_market_notice",
        "source_event_id": str(notice_id or hashlib.sha1(source_url.encode("utf-8")).hexdigest()[:12]),
        "title": external_reference or notice_type_desc or f"Market Notice {notice_id}",
        "summary": summary,
        "published_at": published_at,
        "effective_start": effective_start,
        "effective_end": effective_start,
        "region_scope": regions,
        "asset_scope": [],
        "event_class_raw": notice_type_id or notice_type_desc or "MARKET NOTICE",
        "severity_raw": _normalize_severity(" ".join(filter(None, [notice_type_id, notice_type_desc, external_reference, summary]))),
        "source_url": source_url,
        "raw_payload_json": {
            "notice_type_id": notice_type_id,
            "notice_type_description": notice_type_desc,
            "body": body,
        },
    }


def normalize_raw_event_to_states(raw_event: dict) -> list[dict]:
    text = " ".join(
        filter(
            None,
            [
                raw_event.get("title"),
                raw_event.get("summary"),
                raw_event.get("event_class_raw"),
                json.dumps(raw_event.get("raw_payload_json") or {}),
            ],
        )
    )
    state_types = _classify_state_types(text)
    if not state_types:
        return []

    market = raw_event.get("market") or infer_market(None, None)
    regions = raw_event.get("region_scope") or (["WEM"] if market == "WEM" else list(NEM_REGIONS))
    start_time = raw_event.get("effective_start") or raw_event.get("published_at")
    end_time = raw_event.get("effective_end") or start_time
    severity = raw_event.get("severity_raw") or _normalize_severity(text)
    confidence = _confidence_for_source(raw_event.get("source", ""))

    states = []
    for region in regions:
        for state_type in state_types:
            states.append(
                {
                    "state_id": _state_id(
                        raw_event.get("source", ""),
                        str(raw_event.get("source_event_id", "")),
                        region,
                        state_type,
                        start_time or "",
                        end_time or "",
                    ),
                    "market": market,
                    "region": region,
                    "state_type": state_type,
                    "start_time": start_time,
                    "end_time": end_time,
                    "severity": severity,
                    "confidence": confidence,
                    "headline": raw_event.get("title") or _state_label(state_type),
                    "impact_domains": IMPACT_DOMAINS_BY_STATE.get(state_type, ["price_trend"]),
                    "evidence_event_ids": [raw_event.get("id")] if raw_event.get("id") is not None else [],
                    "evidence_summary_json": [
                        {
                            "source": raw_event.get("source"),
                            "title": raw_event.get("title"),
                            "url": raw_event.get("source_url"),
                        }
                    ],
                }
            )
    return states


def merge_explanation_states(states: list[dict], gap_minutes: int = 360) -> list[dict]:
    if not states:
        return []

    def key_func(state: dict):
        return (
            state["market"],
            state["region"],
            state["state_type"],
            state["severity"],
            state["start_time"],
        )

    sorted_states = sorted(states, key=key_func)
    merged = []

    for state in sorted_states:
        if not merged:
            merged.append({**state})
            continue

        previous = merged[-1]
        if (
            previous["market"] == state["market"]
            and previous["region"] == state["region"]
            and previous["state_type"] == state["state_type"]
            and previous["severity"] == state["severity"]
        ):
            prev_end = dt.datetime.strptime(previous["end_time"], "%Y-%m-%d %H:%M:%S")
            current_start = dt.datetime.strptime(state["start_time"], "%Y-%m-%d %H:%M:%S")
            gap = (current_start - prev_end).total_seconds() / 60
            if gap <= gap_minutes:
                previous["end_time"] = max(previous["end_time"], state["end_time"])
                previous["confidence"] = round(max(previous.get("confidence", 0), state.get("confidence", 0)), 4)
                previous["impact_domains"] = sorted(set(previous.get("impact_domains", [])) | set(state.get("impact_domains", [])))
                previous["evidence_event_ids"] = sorted(set(previous.get("evidence_event_ids", [])) | set(state.get("evidence_event_ids", [])))
                previous["evidence_summary_json"] = previous.get("evidence_summary_json", []) + state.get("evidence_summary_json", [])
                continue

        merged.append({**state})

    for item in merged:
        item["state_id"] = _state_id(
            item["market"],
            item["region"],
            item["state_type"],
            item["start_time"],
            item["end_time"],
            ",".join(str(event_id) for event_id in item.get("evidence_event_ids", [])),
        )
    return merged


def parse_nem_high_impact_outage_rows(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text))
    records = []
    for row in reader:
        region = (row.get("Region") or "").strip().upper()
        if region not in STATE_TO_REGIONS or region == "WA":
            continue
        start_time = _parse_datetime(_collapse_multiline(row.get("Start")), "%d/%m/%Y %H:%M %A")
        end_time = _parse_datetime(_collapse_multiline(row.get("Finish")), "%d/%m/%Y %H:%M %A")
        asset = _collapse_multiline(row.get("Network Asset")) or "Network Asset"
        impact = _collapse_multiline(row.get("Impact"))
        status = _collapse_multiline(
            row.get("Status and\r\nMarket Notice")
            or row.get("Status and\nMarket Notice")
            or row.get("Status")
        )
        source_event_id = hashlib.sha1(f"{region}|{asset}|{start_time}|{end_time}".encode("utf-8")).hexdigest()[:16]
        records.append(
            {
                "market": "NEM",
                "source": "nem_high_impact_outage",
                "source_event_id": source_event_id,
                "title": f"High Impact Outage - {asset}",
                "summary": " ".join(filter(None, [impact, status])),
                "published_at": start_time,
                "effective_start": start_time,
                "effective_end": end_time or start_time,
                "region_scope": STATE_TO_REGIONS.get(region, []),
                "asset_scope": [asset],
                "event_class_raw": "High Impact Outage",
                "severity_raw": _normalize_severity(" ".join(filter(None, [impact, status]))),
                "source_url": NEM_HIGH_IMPACT_OUTAGES_URL,
                "raw_payload_json": row,
            }
        )
    return records


def parse_wem_dispatch_advisory_rows(csv_text: str, cutoff: str | None = None) -> list[dict]:
    cutoff_dt = dt.datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S") if cutoff else None
    reader = csv.DictReader(io.StringIO(csv_text))
    records = []
    for row in reader:
        start_time = _parse_datetime(row.get("Start Interval"), "%Y-%m-%d %H:%M:%S")
        issued_at = _parse_datetime(row.get("Issued At"), "%Y-%m-%d %H:%M:%S")
        compare_time = start_time or issued_at
        if cutoff_dt and compare_time:
            compare_dt = dt.datetime.strptime(compare_time, "%Y-%m-%d %H:%M:%S")
            if compare_dt < cutoff_dt:
                continue
        advisory_id = str(row.get("Dispatch Advisory ID") or "").strip()
        details = _collapse_multiline(row.get("Details"))
        summary = " ".join(
            filter(
                None,
                [
                    details,
                    _collapse_multiline(row.get("System Management Actions")),
                    _collapse_multiline(row.get("Required Market Participant and Network Operator Actions")),
                ],
            )
        )
        records.append(
            {
                "market": "WEM",
                "source": "wem_dispatch_advisory",
                "source_event_id": advisory_id or hashlib.sha1(summary.encode("utf-8")).hexdigest()[:16],
                "title": details or f"WEM Dispatch Advisory {advisory_id}",
                "summary": summary,
                "published_at": issued_at or start_time,
                "effective_start": start_time or issued_at,
                "effective_end": _parse_datetime(row.get("End Interval"), "%Y-%m-%d %H:%M:%S") or start_time or issued_at,
                "region_scope": ["WEM"],
                "asset_scope": [],
                "event_class_raw": "Dispatch Advisory",
                "severity_raw": _normalize_severity(summary),
                "source_url": WEM_DISPATCH_ADVISORY_CSV_URL,
                "raw_payload_json": row,
            }
        )
    return records


def parse_wem_realtime_outage_rows(csv_text: str, cutoff: str | None = None) -> list[dict]:
    cutoff_dt = dt.datetime.strptime(cutoff, "%Y-%m-%d %H:%M:%S") if cutoff else None
    reader = csv.DictReader(io.StringIO(csv_text))
    records = []
    for row in reader:
        start_time = _parse_datetime(row.get("Start Time"), "%Y-%m-%d %H:%M:%S")
        if cutoff_dt and start_time:
            compare_dt = dt.datetime.strptime(start_time, "%Y-%m-%d %H:%M:%S")
            if compare_dt < cutoff_dt:
                continue
        facility = (row.get("Facility Code") or "").strip() or "WEM Facility"
        summary = " ".join(
            filter(
                None,
                [
                    _collapse_multiline(row.get("Reason")),
                    _collapse_multiline(row.get("Description")),
                ],
            )
        )
        records.append(
            {
                "market": "WEM",
                "source": "wem_realtime_outage",
                "source_event_id": str(row.get("Outage ID") or hashlib.sha1(facility.encode("utf-8")).hexdigest()[:16]),
                "title": f"WEM Outage - {facility}",
                "summary": summary,
                "published_at": _parse_datetime(row.get("Amendment Time"), "%Y-%m-%d %H:%M:%S") or start_time,
                "effective_start": start_time,
                "effective_end": _parse_datetime(row.get("End Time"), "%Y-%m-%d %H:%M:%S") or start_time,
                "region_scope": ["WEM"],
                "asset_scope": [facility],
                "event_class_raw": "Realtime Outage",
                "severity_raw": _normalize_severity(summary),
                "source_url": WEM_REALTIME_OUTAGES_CSV_URL,
                "raw_payload_json": row,
            }
        )
    return records


def parse_bom_warning_payload(region: str, payload: dict) -> list[dict]:
    warnings = payload.get("warnings") or payload.get("data") or []
    records = []
    for item in warnings:
        title = item.get("title") or item.get("warning_type_name") or item.get("type") or "BOM Warning"
        summary = item.get("summary") or item.get("short_text") or item.get("description") or title
        warning_id = str(item.get("id") or item.get("warning_id") or hashlib.sha1(f"{region}|{title}|{summary}".encode("utf-8")).hexdigest()[:16])
        published_at = (
            _parse_datetime(item.get("issued_at"), "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")
            or _parse_datetime(item.get("issue_time"), "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")
        )
        effective_end = (
            _parse_datetime(item.get("expires_at"), "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")
            or _parse_datetime(item.get("expiry_time"), "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S")
            or published_at
        )
        source_url = item.get("url") or item.get("link") or "https://www.bom.gov.au/weather-and-climate/warnings-and-alerts"
        records.append(
            {
                "market": "WEM" if region == "WA" else "NEM",
                "source": "bom_warnings",
                "source_event_id": warning_id,
                "title": title,
                "summary": summary,
                "published_at": published_at,
                "effective_start": published_at,
                "effective_end": effective_end,
                "region_scope": STATE_TO_REGIONS.get(region, []),
                "asset_scope": [],
                "event_class_raw": item.get("warning_type_name") or item.get("type") or "Weather Warning",
                "severity_raw": _normalize_severity(title + " " + summary),
                "source_url": source_url,
                "raw_payload_json": item,
            }
        )
    return records


def rebuild_market_states(db_manager, market: str) -> list[dict]:
    with db_manager.get_connection() as conn:
        db_manager.ensure_event_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT id, market, source, source_event_id, title, summary, published_at, effective_start, effective_end,
                   region_scope_json, asset_scope_json, event_class_raw, severity_raw, source_url, raw_payload_json
            FROM {db_manager.GRID_EVENT_RAW_TABLE}
            WHERE market = ?
            ORDER BY COALESCE(effective_start, published_at) ASC
            """,
            (market,),
        )
        rows = cursor.fetchall()

    raw_events = []
    for row in rows:
        raw_events.append(
            {
                "id": row[0],
                "market": row[1],
                "source": row[2],
                "source_event_id": row[3],
                "title": row[4],
                "summary": row[5],
                "published_at": row[6],
                "effective_start": row[7],
                "effective_end": row[8],
                "region_scope": json.loads(row[9] or "[]"),
                "asset_scope": json.loads(row[10] or "[]"),
                "event_class_raw": row[11],
                "severity_raw": row[12],
                "source_url": row[13],
                "raw_payload_json": json.loads(row[14] or "{}"),
            }
        )

    states = []
    for raw_event in raw_events:
        states.extend(normalize_raw_event_to_states(raw_event))
    merged = merge_explanation_states(states)
    db_manager.replace_grid_event_states(market, merged)
    return merged


def get_event_overlay_response(
    db_manager,
    *,
    year: int,
    region: str,
    market: str | None = None,
    month: str | None = None,
    quarter: str | None = None,
    day_type: str | None = None,
):
    resolved_market = infer_market(region, market)
    with db_manager.get_connection() as conn:
        db_manager.ensure_event_tables(conn)
        cursor = conn.cursor()
        cursor.execute(
            f"""
            SELECT state_id, market, region, state_type, start_time, end_time, severity, confidence,
                   headline, impact_domains_json, evidence_event_ids_json, evidence_summary_json
            FROM {db_manager.GRID_EVENT_STATE_TABLE}
            WHERE market = ? AND region = ?
            ORDER BY start_time ASC, end_time ASC
            """,
            (resolved_market, region),
        )
        state_rows = cursor.fetchall()
        sync_states = db_manager.fetch_grid_event_sync_states()

    states = []
    event_id_to_states = defaultdict(set)
    for row in state_rows:
        item = {
            "state_id": row[0],
            "market": row[1],
            "region": row[2],
            "state_type": row[3],
            "start_time": row[4],
            "end_time": row[5],
            "severity": row[6],
            "confidence": row[7],
            "headline": row[8],
            "impact_domains": json.loads(row[9] or "[]"),
            "evidence_event_ids": json.loads(row[10] or "[]"),
            "evidence_summary_json": json.loads(row[11] or "[]"),
        }
        if _datetime_matches_filters(item["start_time"], year, month, quarter, day_type):
            states.append(item)
            for event_id in item["evidence_event_ids"]:
                event_id_to_states[event_id].add(item["state_type"])

    events = []
    if event_id_to_states:
        ids = sorted(event_id_to_states.keys())
        placeholders = ", ".join("?" for _ in ids)
        with db_manager.get_connection() as conn:
            db_manager.ensure_event_tables(conn)
            cursor = conn.cursor()
            cursor.execute(
                f"""
                SELECT id, source, source_url, title, summary, published_at, effective_start, effective_end,
                       event_class_raw, region_scope_json, asset_scope_json
                FROM {db_manager.GRID_EVENT_RAW_TABLE}
                WHERE id IN ({placeholders})
                ORDER BY COALESCE(effective_start, published_at) ASC
                """,
                tuple(ids),
            )
            event_rows = cursor.fetchall()
        for row in event_rows:
            event_id = row[0]
            events.append(
                {
                    "event_id": event_id,
                    "source": row[1],
                    "source_url": row[2],
                    "title": row[3],
                    "summary": row[4],
                    "published_at": row[5],
                    "effective_start": row[6],
                    "effective_end": row[7],
                    "raw_class": row[8],
                    "region_scope": json.loads(row[9] or "[]"),
                    "asset_scope": json.loads(row[10] or "[]"),
                    "normalized_states": sorted(event_id_to_states.get(event_id, [])),
                }
            )

    daily_rollup = _build_daily_rollup(states, year, month, quarter, day_type)
    sources_used = sorted({event["source"] for event in events})
    coverage_quality = _coverage_quality(resolved_market, sync_states)

    return {
        "metadata": {
            "market": resolved_market,
            "region": region,
            "coverage_quality": coverage_quality,
            "sources_used": sources_used,
            "time_granularity": "interval",
            "no_verified_event_explanation": len(states) == 0,
            "filters": {
                "year": year,
                "month": month,
                "quarter": quarter,
                "day_type": day_type,
            },
        },
        "states": [
            {
                "state_id": state["state_id"],
                "state_type": state["state_type"],
                "label": _state_label(state["state_type"]),
                "start_time": state["start_time"],
                "end_time": state["end_time"],
                "severity": state["severity"],
                "confidence": state["confidence"],
                "headline": state["headline"],
                "impact_domains": state["impact_domains"],
                "evidence_count": len(state["evidence_event_ids"]),
            }
            for state in states
        ],
        "daily_rollup": daily_rollup,
        "events": events,
    }


def _coverage_quality(market: str, sync_states: list[dict]) -> str:
    ok_sources = {row["source"] for row in sync_states if row.get("sync_status") == "ok"}
    if market == "WEM":
        return "core_only" if ok_sources & WEM_CORE_SOURCES else "none"
    if NEM_REQUIRED_SOURCES <= ok_sources:
        return "full"
    if ok_sources & NEM_REQUIRED_SOURCES:
        return "partial"
    return "none"


def _severity_rank(severity: str) -> int:
    return {"high": 3, "medium": 2, "low": 1}.get(severity, 0)


def _build_daily_rollup(states: list[dict], year: int, month: str | None, quarter: str | None, day_type: str | None) -> list[dict]:
    daily = defaultdict(list)
    for state in states:
        start_date = dt.datetime.strptime(state["start_time"][:19], "%Y-%m-%d %H:%M:%S").date()
        end_date = dt.datetime.strptime(state["end_time"][:19], "%Y-%m-%d %H:%M:%S").date()
        cursor = start_date
        while cursor <= end_date:
            date_str = cursor.strftime("%Y-%m-%d")
            if _date_matches_filters(date_str, year, month, quarter, day_type):
                daily[date_str].append(state)
            cursor += dt.timedelta(days=1)

    rollup = []
    for date_str, items in sorted(daily.items()):
        by_state = {}
        for item in items:
            bucket = by_state.setdefault(item["state_type"], {"count": 0, "severity": item["severity"]})
            bucket["count"] += 1
            if _severity_rank(item["severity"]) > _severity_rank(bucket["severity"]):
                bucket["severity"] = item["severity"]
        top_states = [
            {
                "key": key,
                "label": _state_label(key),
                "count": value["count"],
                "severity": value["severity"],
            }
            for key, value in sorted(
                by_state.items(),
                key=lambda pair: (-_severity_rank(pair[1]["severity"]), -pair[1]["count"], pair[0]),
            )
        ]
        rollup.append(
            {
                "date": date_str,
                "top_states": top_states,
                "highest_severity": top_states[0]["severity"] if top_states else "low",
                "event_count": len(items),
            }
        )
    return rollup


def _datetime_matches_filters(timestamp: str | None, year: int, month: str | None, quarter: str | None, day_type: str | None) -> bool:
    if not timestamp:
        return False
    current = dt.datetime.strptime(timestamp[:19], "%Y-%m-%d %H:%M:%S")
    if current.year != year:
        return False
    if month and len(month) == 2:
        if current.strftime("%m") != month:
            return False
    elif quarter in {"Q1", "Q2", "Q3", "Q4"}:
        quarter_map = {
            "Q1": {"01", "02", "03"},
            "Q2": {"04", "05", "06"},
            "Q3": {"07", "08", "09"},
            "Q4": {"10", "11", "12"},
        }
        if current.strftime("%m") not in quarter_map[quarter]:
            return False
    if day_type == "WEEKDAY" and current.weekday() >= 5:
        return False
    if day_type == "WEEKEND" and current.weekday() < 5:
        return False
    return True


def _date_matches_filters(date_str: str, year: int, month: str | None, quarter: str | None, day_type: str | None) -> bool:
    return _datetime_matches_filters(f"{date_str} 00:00:00", year, month, quarter, day_type)


def sync_event_sources(db_manager, days: int = 90) -> dict:
    now = dt.datetime.utcnow().replace(microsecond=0)
    cutoff = (now - dt.timedelta(days=days)).strftime("%Y-%m-%d %H:%M:%S")

    source_results = []
    for source_name, fetcher in (
        ("nem_market_notice", lambda: _fetch_nem_market_notices(cutoff)),
        ("nem_high_impact_outage", _fetch_nem_high_impact_outages),
        ("wem_dispatch_advisory", lambda: _fetch_wem_dispatch_advisories(cutoff)),
        ("wem_realtime_outage", lambda: _fetch_wem_realtime_outages(cutoff)),
        ("bom_warnings", _fetch_bom_warnings),
    ):
        try:
            records = fetcher()
            db_manager.upsert_grid_event_raw(records)
            source_results.append(
                {
                    "source": source_name,
                    "last_success_at": now.strftime("%Y-%m-%d %H:%M:%S"),
                    "cursor": None,
                    "last_backfill_at": cutoff,
                    "sync_status": "ok",
                }
            )
        except Exception as exc:
            logger.exception("Grid event sync failed for %s", source_name)
            source_results.append(
                {
                    "source": source_name,
                    "last_success_at": None,
                    "cursor": None,
                    "last_backfill_at": cutoff,
                    "sync_status": f"error:{type(exc).__name__}",
                }
            )

    db_manager.upsert_grid_event_sync_states(source_results)
    nem_states = rebuild_market_states(db_manager, "NEM")
    wem_states = rebuild_market_states(db_manager, "WEM")
    return {
        "synced_sources": source_results,
        "nem_states": len(nem_states),
        "wem_states": len(wem_states),
    }


def _fetch_text(url: str, timeout: int = 30) -> str:
    response = requests.get(url, timeout=timeout, headers=DEFAULT_HEADERS)
    response.raise_for_status()
    response.encoding = response.encoding or "utf-8"
    return response.text


def _fetch_nem_market_notices(cutoff: str) -> list[dict]:
    listing_html = _fetch_text(NEM_MARKET_NOTICE_LISTING_URL)
    links = re.findall(
        r'HREF="(/REPORTS/CURRENT/Market_Notice/NEMITWEB1_MKTNOTICE_(\d{8})\.R\d+)"',
        listing_html,
        flags=re.IGNORECASE,
    )
    cutoff_date = dt.datetime.strptime(cutoff[:10], "%Y-%m-%d").date()
    records = []
    for link, file_date in links:
        notice_date = dt.datetime.strptime(file_date, "%Y%m%d").date()
        if notice_date < cutoff_date:
            continue
        source_url = f"https://www.nemweb.com.au{link}"
        records.append(parse_nem_market_notice_report(_fetch_text(source_url), source_url))
    return records


def _fetch_nem_high_impact_outages() -> list[dict]:
    listing_html = _fetch_text(NEM_HIGH_IMPACT_OUTAGES_URL)
    links = re.findall(
        r'HREF="(/REPORTS/CURRENT/HighImpactOutages/7_days_High_Impact_Outages_[^"]+\.csv)"',
        listing_html,
        flags=re.IGNORECASE,
    )
    if not links:
        return []
    latest_link = sorted(links)[-1]
    return parse_nem_high_impact_outage_rows(_fetch_text(f"https://www.nemweb.com.au{latest_link}"))


def _fetch_wem_dispatch_advisories(cutoff: str) -> list[dict]:
    return parse_wem_dispatch_advisory_rows(_fetch_text(WEM_DISPATCH_ADVISORY_CSV_URL), cutoff)


def _fetch_wem_realtime_outages(cutoff: str) -> list[dict]:
    return parse_wem_realtime_outage_rows(_fetch_text(WEM_REALTIME_OUTAGES_CSV_URL), cutoff)


def _fetch_bom_warnings() -> list[dict]:
    records = []
    for region, area_code in BOM_AREA_CODES.items():
        response = requests.get(
            BOM_WARNINGS_LIST_URL.format(area_code=area_code),
            timeout=20,
            headers=DEFAULT_HEADERS,
        )
        response.raise_for_status()
        records.extend(parse_bom_warning_payload(region, response.json()))
    return records
