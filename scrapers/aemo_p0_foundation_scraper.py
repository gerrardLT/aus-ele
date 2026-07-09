import argparse
import io
import json
import os
import re
import sys
import time
import zipfile
from datetime import datetime, timedelta, UTC
from ftplib import FTP
from pathlib import Path
from typing import Any
import xml.etree.ElementTree as ET

import requests


try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}

OD_ACTUAL_URL = "https://nemweb.com.au/Reports/Current/Operational_Demand/ACTUAL_HH/"
OD_FORECAST_URL = "https://nemweb.com.au/Reports/Current/Operational_Demand/FORECAST_HH/"
ROOFTOP_ACTUAL_URL = "https://nemweb.com.au/Reports/Current/ROOFTOP_PV/ACTUAL/"
ROOFTOP_FORECAST_URL = "https://nemweb.com.au/Reports/Current/ROOFTOP_PV/FORECAST/"
DISPATCH_URL = "https://nemweb.com.au/Reports/Current/DispatchIS_Reports/"
PREDISPATCH_URL = "https://nemweb.com.au/Reports/Current/PredispatchIS_Reports/"
PDPASA_DUID_AVAILABILITY_URL = "https://www.nemweb.com.au/REPORTS/CURRENT/PDPASA_DUIDAvailability/"
MMSDM_ARCHIVE_ROOT_URL = "https://nemweb.com.au/Data_Archive/Wholesale_Electricity/MMSDM/"

OD_ACTUAL_RE = re.compile(r"PUBLIC_ACTUAL_OPERATIONAL_DEMAND_HH_[^\"\s>]+\.zip", re.I)
OD_FORECAST_RE = re.compile(r"PUBLIC_FORECAST_OPERATIONAL_DEMAND_HH_[^\"\s>]+\.zip", re.I)
ROOFTOP_ACTUAL_RE = re.compile(r"PUBLIC_ROOFTOP_PV_ACTUAL_MEASUREMENT_[^\"\s>]+\.zip", re.I)
ROOFTOP_FORECAST_RE = re.compile(r"PUBLIC_ROOFTOP_PV_FORECAST_[^\"\s>]+\.zip", re.I)
DISPATCH_RE = re.compile(r"PUBLIC_DISPATCHIS_[^\"\s>]+\.zip", re.I)
PREDISPATCH_RE = re.compile(r"PUBLIC_PREDISPATCHIS_[^\"\s>]+\.zip", re.I)
PDPASA_DUID_AVAILABILITY_RE = re.compile(r"PUBLIC_PDPASA_DUIDAVAILABILITY_[^\"\s>]+\.zip", re.I)

BOM_REGION_FILES = {
    "NSW1": "IDN60920.xml",
    "QLD1": "IDQ60920.xml",
    "SA1": "IDS60920.xml",
    "TAS1": "IDT60920.xml",
    "VIC1": "IDV60920.xml",
}

WEATHER_CACHE_MAX_AGE_HOURS = 24

OPEN_METEO_REGION_CONFIG = {
    "NSW1": {"latitude": -33.8593, "longitude": 151.2048, "timezone": "Australia/Sydney", "station_name": "Sydney - Observatory Hill"},
    "QLD1": {"latitude": -27.4808, "longitude": 153.0389, "timezone": "Australia/Brisbane", "station_name": "Brisbane"},
    "SA1": {"latitude": -34.9257, "longitude": 138.5832, "timezone": "Australia/Adelaide", "station_name": "Adelaide"},
    "TAS1": {"latitude": -42.8897, "longitude": 147.3278, "timezone": "Australia/Hobart", "station_name": "Hobart"},
    "VIC1": {"latitude": -37.8255, "longitude": 144.9816, "timezone": "Australia/Melbourne", "station_name": "Melbourne (Olympic Park)"},
}


def fetch_text(url: str) -> str:
    response = requests.get(url, headers=HEADERS, timeout=60)
    response.raise_for_status()
    return response.text


def fetch_recent_zip_names(base_url: str, pattern: re.Pattern[str], limit: int) -> list[str]:
    html = fetch_text(base_url)
    matches = sorted(set(pattern.findall(html)))
    return matches[-limit:]


def fetch_archive_listing(base_url: str) -> list[str]:
    html = fetch_text(base_url)
    return sorted(set(re.findall(r'HREF="([^"]+)"', html)))


def fetch_zip_lines(base_url: str, name: str) -> list[str]:
    response = requests.get(base_url + name, headers=HEADERS, timeout=60)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        file_name = zf.namelist()[0]
        return zf.read(file_name).decode("utf-8", errors="replace").splitlines()


def fetch_archive_zip_lines(archive_url: str) -> tuple[str, list[str]]:
    response = requests.get(archive_url, headers=HEADERS, timeout=120)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        file_name = zf.namelist()[0]
        lines = zf.read(file_name).decode("utf-8", errors="replace").splitlines()
    return file_name, lines


def parse_aemo_report(lines: list[str]) -> tuple[list[str], list[dict[str, str]]]:
    headers: list[str] = []
    rows: list[dict[str, str]] = []
    for line in lines:
        parts = [part.strip().strip('"') for part in line.split(",")]
        if not parts:
            continue
        row_type = parts[0].upper()
        if row_type == "I":
            headers = parts
            continue
        if row_type != "D" or not headers:
            continue
        if len(parts) < len(headers):
            continue
        rows.append({headers[idx]: parts[idx] for idx in range(len(headers))})
    return headers, rows


def ensure_tables(conn: Any):
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS operational_demand_actual_hh (
            region_id TEXT NOT NULL,
            interval_datetime TEXT NOT NULL,
            operational_demand REAL,
            operational_demand_adjustment REAL,
            wdr_estimate REAL,
            lastchanged TEXT,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, interval_datetime)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS operational_demand_forecast_hh (
            region_id TEXT NOT NULL,
            interval_datetime TEXT NOT NULL,
            load_date TEXT NOT NULL,
            operational_demand_poe10 REAL,
            operational_demand_poe50 REAL,
            operational_demand_poe90 REAL,
            lastchanged TEXT,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, interval_datetime, load_date)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rooftop_pv_actual_measurement (
            region_id TEXT NOT NULL,
            interval_datetime TEXT NOT NULL,
            power REAL,
            qi REAL,
            source_type TEXT,
            lastchanged TEXT,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, interval_datetime)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS rooftop_pv_forecast (
            region_id TEXT NOT NULL,
            interval_datetime TEXT NOT NULL,
            version_datetime TEXT NOT NULL,
            powermean REAL,
            powerpoe50 REAL,
            powerpoelow REAL,
            powerpoehigh REAL,
            lastchanged TEXT,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, interval_datetime, version_datetime)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dispatch_region_summary (
            region_id TEXT NOT NULL,
            settlement_date TEXT NOT NULL,
            ss_solar_uigf REAL,
            ss_wind_uigf REAL,
            ss_solar_clearedmw REAL,
            ss_wind_clearedmw REAL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, settlement_date)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS predispatch_region_solution (
            region_id TEXT NOT NULL,
            interval_datetime TEXT NOT NULL,
            run_datetime TEXT NOT NULL,
            ss_solar_uigf REAL,
            ss_wind_uigf REAL,
            ss_solar_clearedmw REAL,
            ss_wind_clearedmw REAL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, interval_datetime, run_datetime)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS dispatch_interconnector_flow (
            interconnector_id TEXT NOT NULL,
            settlement_date TEXT NOT NULL,
            from_regionid TEXT NOT NULL,
            to_regionid TEXT NOT NULL,
            mwflow REAL,
            meteredmwflow REAL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (interconnector_id, settlement_date)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bom_weather_observation (
            region_id TEXT NOT NULL,
            station_name TEXT NOT NULL,
            observation_time_utc TEXT NOT NULL,
            observation_time_local TEXT,
            air_temperature_c REAL,
            wind_speed_mps REAL,
            cloud_cover_pct REAL,
            apparent_temperature_c REAL,
            relative_humidity_pct REAL,
            rainfall_mm REAL,
            pressure_hpa REAL,
            source_file TEXT NOT NULL,
            PRIMARY KEY (region_id, observation_time_utc)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS bom_weather_source_cache (
            region_id TEXT NOT NULL PRIMARY KEY,
            source_file TEXT NOT NULL,
            payload_xml TEXT NOT NULL,
            fetched_at_utc TEXT NOT NULL,
            fetch_mode TEXT NOT NULL,
            last_error TEXT
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS pdpasa_duid_availability (
            run_datetime TEXT NOT NULL,
            duid TEXT NOT NULL,
            interval_datetime TEXT NOT NULL,
            generation_max_availability REAL,
            generation_pasa_availability REAL,
            generation_recall_period REAL,
            load_max_availability REAL,
            load_pasa_availability REAL,
            load_recall_period REAL,
            lastchanged TEXT,
            source_file TEXT NOT NULL,
            PRIMARY KEY (run_datetime, duid, interval_datetime)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS du_detail_summary (
            duid TEXT NOT NULL,
            start_date TEXT NOT NULL,
            end_date TEXT NOT NULL,
            dispatch_type TEXT,
            connection_point_id TEXT,
            region_id TEXT,
            station_id TEXT,
            participant_id TEXT,
            schedule_type TEXT,
            source_file TEXT NOT NULL,
            PRIMARY KEY (duid, start_date, end_date)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS wem_reserve_shortfall_snapshot (
            interval_start_utc TEXT NOT NULL,
            interval_end_utc TEXT NOT NULL,
            reserve_service TEXT NOT NULL,
            shortfall_mw REAL NOT NULL,
            severity TEXT NOT NULL,
            source_table TEXT NOT NULL,
            source_interval TEXT NOT NULL,
            PRIMARY KEY (interval_start_utc, reserve_service)
        )
        """
    )
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS aemo_source_sync_state (
            source_id TEXT PRIMARY KEY,
            last_success_at TEXT,
            last_attempt_at TEXT,
            sync_status TEXT NOT NULL,
            last_error TEXT,
            detail_json TEXT NOT NULL DEFAULT '{}'
        )
        """
    )
    conn.commit()


def _utc_now_iso() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _upsert_aemo_source_sync_state(
    conn: Any,
    *,
    source_id: str,
    sync_status: str,
    last_success_at: str | None = None,
    last_attempt_at: str | None = None,
    last_error: str | None = None,
    detail: dict | None = None,
):
    conn.execute(
        """
        INSERT INTO aemo_source_sync_state (
            source_id,
            last_success_at,
            last_attempt_at,
            sync_status,
            last_error,
            detail_json
        ) VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id) DO UPDATE SET
            last_success_at=excluded.last_success_at,
            last_attempt_at=excluded.last_attempt_at,
            sync_status=excluded.sync_status,
            last_error=excluded.last_error,
            detail_json=excluded.detail_json
        """,
        (
            source_id,
            last_success_at,
            last_attempt_at,
            sync_status,
            last_error,
            json.dumps(detail or {}),
        ),
    )
    conn.commit()


def _fetch_bom_ftp_bytes(path: str) -> bytes:
    last_error: Exception | None = None
    for passive_mode in (True, False):
        for _ in range(3):
            ftp = None
            try:
                ftp = FTP("ftp.bom.gov.au", timeout=60)
                ftp.set_pasv(passive_mode)
                ftp.login()
                ftp.cwd("/anon/gen/fwo")
                buffer = io.BytesIO()
                ftp.retrbinary(f"RETR {path}", buffer.write)
                return buffer.getvalue()
            except Exception as exc:
                last_error = exc
                time.sleep(0.5)
            finally:
                if ftp is not None:
                    try:
                        ftp.quit()
                    except Exception:
                        pass
    raise last_error if last_error is not None else RuntimeError(f"Unable to fetch BOM file: {path}")


def _fetch_bom_registered_bytes(path: str) -> bytes:
    registered_root = os.environ.get("BOM_REGISTERED_WEATHER_DIR", "").strip()
    if not registered_root:
        raise FileNotFoundError("BOM_REGISTERED_WEATHER_DIR is not configured")
    candidate = Path(registered_root) / path
    if not candidate.exists():
        raise FileNotFoundError(f"Registered BOM payload not found: {candidate}")
    return candidate.read_bytes()


def _store_bom_weather_cache(
    conn: Any,
    *,
    region_id: str,
    source_file: str,
    payload_xml: bytes,
    fetch_mode: str,
    last_error: str | None = None,
):
    conn.execute(
        """
        INSERT INTO bom_weather_source_cache
        (region_id, source_file, payload_xml, fetched_at_utc, fetch_mode, last_error)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id) DO UPDATE SET source_file=EXCLUDED.source_file, payload_xml=EXCLUDED.payload_xml, fetched_at_utc=EXCLUDED.fetched_at_utc, fetch_mode=EXCLUDED.fetch_mode, last_error=EXCLUDED.last_error
        """,
        (
            region_id,
            source_file,
            payload_xml.decode("utf-8", errors="replace"),
            datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            fetch_mode,
            last_error,
        ),
    )
    conn.commit()


def _load_bom_weather_cache(
    conn: Any,
    *,
    region_id: str,
    max_age_hours: int = WEATHER_CACHE_MAX_AGE_HOURS,
) -> tuple[bytes, str, str] | None:
    row = conn.execute(
        """
        SELECT payload_xml, source_file, fetched_at_utc
        FROM bom_weather_source_cache
        WHERE region_id = ?
        """,
        (region_id,),
    ).fetchone()
    if not row:
        return None
    payload_xml, source_file, fetched_at_utc = row
    try:
        fetched_at = datetime.fromisoformat(str(fetched_at_utc).replace("Z", "+00:00"))
    except ValueError:
        return None
    age_hours = (datetime.now(UTC) - fetched_at).total_seconds() / 3600.0
    if age_hours > max_age_hours:
        return None
    return payload_xml.encode("utf-8"), source_file, fetched_at_utc


def _fetch_open_meteo_weather_records(region_id: str) -> list[tuple]:
    config = OPEN_METEO_REGION_CONFIG[region_id]
    response = requests.get(
        "https://api.open-meteo.com/v1/forecast",
        params={
            "latitude": config["latitude"],
            "longitude": config["longitude"],
            "current": "temperature_2m,relative_humidity_2m,apparent_temperature,precipitation,pressure_msl,wind_speed_10m,cloud_cover",
            "timezone": "UTC",
            "forecast_days": 1,
        },
        headers=HEADERS,
        timeout=60,
    )
    response.raise_for_status()
    payload = response.json()
    current = payload.get("current") or {}
    observation_time_utc = current.get("time")
    if not observation_time_utc:
        return []
    if len(observation_time_utc) == 16:
        observation_time_utc = f"{observation_time_utc}:00Z"
    elif observation_time_utc.endswith("Z"):
        observation_time_utc = observation_time_utc
    else:
        observation_time_utc = f"{observation_time_utc}Z"
    return [
        (
            region_id,
            config["station_name"],
            observation_time_utc,
            "",
            float(current.get("temperature_2m") or 0.0),
            float(current.get("wind_speed_10m") or 0.0) / 3.6 if current.get("wind_speed_10m") is not None else 0.0,
            float(current.get("cloud_cover")) if current.get("cloud_cover") is not None else None,
            float(current.get("apparent_temperature")) if current.get("apparent_temperature") is not None else None,
            float(current.get("relative_humidity_2m")) if current.get("relative_humidity_2m") is not None else None,
            float(current.get("precipitation")) if current.get("precipitation") is not None else None,
            float(current.get("pressure_msl")) if current.get("pressure_msl") is not None else None,
            "open_meteo_api",
        )
    ]


def _parse_bom_observation_file(payload: bytes, *, region_id: str, source_file: str) -> list[tuple]:
    root = ET.fromstring(payload.decode("utf-8", errors="replace"))
    station = root.find(".//station")
    if station is None:
        return []

    station_name = station.attrib.get("description") or station.attrib.get("stn-name") or region_id
    records: list[tuple] = []
    for period in station.findall("./period"):
        level = period.find("./level")
        if level is None:
            continue
        metrics: dict[str, str] = {}
        for element in level.findall("./element"):
            metric_type = element.attrib.get("type")
            if metric_type:
                metrics[metric_type] = (element.text or "").strip()
        time_utc = period.attrib.get("time-utc")
        if not time_utc:
            continue
        records.append(
            (
                region_id,
                station_name,
                time_utc,
                period.attrib.get("time-local", ""),
                float(metrics.get("air_temperature") or 0.0),
                float(metrics.get("wind_spd_kmh") or 0.0) / 3.6 if metrics.get("wind_spd_kmh") else 0.0,
                float(metrics.get("cloud") or 0.0) if metrics.get("cloud") else None,
                float(metrics.get("apparent_temp") or 0.0) if metrics.get("apparent_temp") else None,
                float(metrics.get("rel-humidity") or 0.0) if metrics.get("rel-humidity") else None,
                float(metrics.get("rain_hour") or 0.0) if metrics.get("rain_hour") else None,
                float(metrics.get("msl_pres") or 0.0) if metrics.get("msl_pres") else None,
                source_file,
            )
        )
    return records


def sync_bom_weather_observations(conn: Any):
    records = []
    fallback_region_count = 0
    cached_region_count = 0
    failed_region_count = 0
    provider_failures: dict[str, list[str]] = {}
    for region_id, file_name in BOM_REGION_FILES.items():
        provider_errors: list[str] = []
        try:
            payload = _fetch_bom_registered_bytes(file_name)
            _store_bom_weather_cache(
                conn,
                region_id=region_id,
                source_file=file_name,
                payload_xml=payload,
                fetch_mode="bom_registered",
            )
            records.extend(_parse_bom_observation_file(payload, region_id=region_id, source_file=file_name))
            time.sleep(0.05)
            continue
        except Exception as exc:
            provider_errors.append(f"registered={exc}")

        try:
            payload = _fetch_bom_ftp_bytes(file_name)
            _store_bom_weather_cache(
                conn,
                region_id=region_id,
                source_file=file_name,
                payload_xml=payload,
                fetch_mode="bom_anonymous_ftp",
            )
            records.extend(_parse_bom_observation_file(payload, region_id=region_id, source_file=file_name))
            time.sleep(0.05)
            continue
        except Exception as exc:
            provider_errors.append(f"anonymous_ftp={exc}")

        try:
            records.extend(_fetch_open_meteo_weather_records(region_id))
            fallback_region_count += 1
            if provider_errors:
                provider_failures[region_id] = list(provider_errors)
            print(f"[warn] weather fallback provider used for {region_id}: {'; '.join(provider_errors)}")
            time.sleep(0.05)
            continue
        except Exception as exc:
            provider_errors.append(f"open_meteo={exc}")

        cached = _load_bom_weather_cache(conn, region_id=region_id)
        if cached is not None:
            cached_payload, cached_source_file, fetched_at_utc = cached
            cached_region_count += 1
            if provider_errors:
                provider_failures[region_id] = list(provider_errors)
            print(
                f"[warn] live weather providers failed for {region_id}; "
                f"using cached payload from {fetched_at_utc}: {'; '.join(provider_errors)}"
            )
            records.extend(
                _parse_bom_observation_file(
                    cached_payload,
                    region_id=region_id,
                    source_file=cached_source_file,
                )
            )
        else:
            failed_region_count += 1
            if provider_errors:
                provider_failures[region_id] = list(provider_errors)
            print(f"[warn] weather fetch failed for {region_id}: {'; '.join(provider_errors)}")
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO bom_weather_observation
        (region_id, station_name, observation_time_utc, observation_time_local, air_temperature_c, wind_speed_mps, cloud_cover_pct, apparent_temperature_c, relative_humidity_pct, rainfall_mm, pressure_hpa, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, observation_time_utc) DO UPDATE SET station_name=EXCLUDED.station_name, observation_time_local=EXCLUDED.observation_time_local, air_temperature_c=EXCLUDED.air_temperature_c, wind_speed_mps=EXCLUDED.wind_speed_mps, cloud_cover_pct=EXCLUDED.cloud_cover_pct, apparent_temperature_c=EXCLUDED.apparent_temperature_c, relative_humidity_pct=EXCLUDED.relative_humidity_pct, rainfall_mm=EXCLUDED.rainfall_mm, pressure_hpa=EXCLUDED.pressure_hpa, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    status = "ok"
    last_error = None
    if failed_region_count:
        status = "error"
        last_error = f"{failed_region_count} regions failed without live or cached payload"
    elif fallback_region_count or cached_region_count:
        status = "degraded"
        degraded_segments: list[str] = []
        if fallback_region_count:
            degraded_segments.append(f"{fallback_region_count} fallback provider regions")
        if cached_region_count:
            degraded_segments.append(f"{cached_region_count} cached payload regions")
        last_error = ", ".join(degraded_segments) if degraded_segments else "weather source degraded"
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_weather",
        sync_status=status,
        last_success_at=_utc_now_iso() if records else None,
        last_attempt_at=_utc_now_iso(),
        last_error=last_error,
        detail={
            "row_count": len(records),
            "fallback_region_count": fallback_region_count,
            "cached_region_count": cached_region_count,
            "failed_region_count": failed_region_count,
            "provider_failures": provider_failures,
        },
    )
    return len(records)


def sync_pdpasa_duid_availability(conn: Any, limit: int):
    names = fetch_recent_zip_names(PDPASA_DUID_AVAILABILITY_URL, PDPASA_DUID_AVAILABILITY_RE, limit)
    records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(PDPASA_DUID_AVAILABILITY_URL, name))
        for row in rows:
            records.append(
                (
                    row["RUN_DATETIME"],
                    row["DUID"],
                    row["INTERVAL_DATETIME"],
                    float(row.get("GENERATION_MAX_AVAILABILITY") or 0.0),
                    float(row.get("GENERATION_PASA_AVAILABILITY") or 0.0),
                    float(row.get("GENERATION_RECALL_PERIOD") or 0.0),
                    float(row.get("LOAD_MAX_AVAILABILITY") or 0.0),
                    float(row.get("LOAD_PASA_AVAILABILITY") or 0.0),
                    float(row.get("LOAD_RECALL_PERIOD") or 0.0),
                    row.get("LASTCHANGED", ""),
                    name,
                )
            )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO pdpasa_duid_availability
        (run_datetime, duid, interval_datetime, generation_max_availability, generation_pasa_availability, generation_recall_period, load_max_availability, load_pasa_availability, load_recall_period, lastchanged, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (run_datetime, duid, interval_datetime) DO UPDATE SET generation_max_availability=EXCLUDED.generation_max_availability, generation_pasa_availability=EXCLUDED.generation_pasa_availability, generation_recall_period=EXCLUDED.generation_recall_period, load_max_availability=EXCLUDED.load_max_availability, load_pasa_availability=EXCLUDED.load_pasa_availability, load_recall_period=EXCLUDED.load_recall_period, lastchanged=EXCLUDED.lastchanged, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_unit_availability",
        sync_status="ok",
        last_success_at=_utc_now_iso(),
        last_attempt_at=_utc_now_iso(),
        last_error=None,
        detail={"row_count": len(records)},
    )
    return len(records)


def _latest_mmsdm_archive_month_url() -> str:
    year_links = [item for item in fetch_archive_listing(MMSDM_ARCHIVE_ROOT_URL) if re.search(r"/\d{4}/$", item)]
    if not year_links:
        raise RuntimeError("Unable to locate MMSDM archive years")
    latest_year_url = sorted(year_links)[-1]
    month_links = [item for item in fetch_archive_listing(f"https://nemweb.com.au{latest_year_url}") if re.search(r"/MMSDM_\d{4}_\d{2}/$", item)]
    if not month_links:
        raise RuntimeError("Unable to locate MMSDM archive months")
    latest_month_url = sorted(month_links)[-1]
    return f"https://nemweb.com.au{latest_month_url}MMSDM_Historical_Data_SQLLoader/DATA/"


def sync_du_detail_summary(conn: Any):
    data_url = _latest_mmsdm_archive_month_url()
    listing = fetch_archive_listing(data_url)
    candidates = [item for item in listing if "DUDETAILSUMMARY" in item.upper() and item.lower().endswith(".zip")]
    if not candidates:
        raise RuntimeError("Unable to locate DUDETAILSUMMARY archive file")
    archive_ref = sorted(candidates)[-1]
    archive_name = archive_ref.split("/")[-1]
    archive_url = f"{data_url}{archive_name.replace('#', '%23')}"
    source_file, lines = fetch_archive_zip_lines(archive_url)
    _, rows = parse_aemo_report(lines)
    records = [
        (
            row["DUID"],
            row["START_DATE"],
            row["END_DATE"],
            row.get("DISPATCHTYPE", ""),
            row.get("CONNECTIONPOINTID", ""),
            row.get("REGIONID", ""),
            row.get("STATIONID", ""),
            row.get("PARTICIPANTID", ""),
            row.get("SCHEDULE_TYPE", ""),
            source_file,
        )
        for row in rows
        if row.get("DUID") and row.get("REGIONID")
    ]
    conn.executemany(
        """
        INSERT INTO du_detail_summary
        (duid, start_date, end_date, dispatch_type, connection_point_id, region_id, station_id, participant_id, schedule_type, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (duid, start_date, end_date) DO UPDATE SET dispatch_type=EXCLUDED.dispatch_type, connection_point_id=EXCLUDED.connection_point_id, region_id=EXCLUDED.region_id, station_id=EXCLUDED.station_id, participant_id=EXCLUDED.participant_id, schedule_type=EXCLUDED.schedule_type, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_du_detail_summary",
        sync_status="ok" if records else "error",
        last_success_at=_utc_now_iso() if records else None,
        last_attempt_at=_utc_now_iso(),
        last_error=None if records else "no du_detail_summary rows synced",
        detail={"row_count": len(records), "source_file": source_file},
    )
    return len(records)


def sync_wem_reserve_shortfall_snapshot(conn: Any):
    cursor = conn.cursor()
    cursor.execute("DELETE FROM wem_reserve_shortfall_snapshot")
    try:
        rows = cursor.execute(
            """
            SELECT dispatch_interval,
                   shortfall_regulation_raise,
                   shortfall_regulation_lower,
                   shortfall_contingency_raise,
                   shortfall_contingency_lower,
                   shortfall_rocof
            FROM wem_ess_market_price
            WHERE COALESCE(shortfall_regulation_raise, 0)
                + COALESCE(shortfall_regulation_lower, 0)
                + COALESCE(shortfall_contingency_raise, 0)
                + COALESCE(shortfall_contingency_lower, 0)
                + COALESCE(shortfall_rocof, 0) > 0
            ORDER BY dispatch_interval DESC
            LIMIT 288
            """
        ).fetchall()
    except Exception:
        conn.commit()
        _upsert_aemo_source_sync_state(
            conn,
            source_id="aemo_wem_reserve_shortfall",
            sync_status="error",
            last_success_at=None,
            last_attempt_at=_utc_now_iso(),
            last_error="wem_ess_market_price unavailable",
            detail={"row_count": 0},
        )
        return 0

    service_columns = [
        ("REGULATION_RAISE", 1),
        ("REGULATION_LOWER", 2),
        ("CONTINGENCY_RAISE", 3),
        ("CONTINGENCY_LOWER", 4),
        ("ROCOF", 5),
    ]
    inserts = []
    for row in rows:
        start_dt = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").replace(tzinfo=UTC)
        end_dt = start_dt + timedelta(minutes=5)
        for service_name, idx in service_columns:
            value = float(row[idx] or 0.0)
            if value <= 0:
                continue
            inserts.append(
                (
                    start_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    end_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    service_name,
                    value,
                    "market_shortfall",
                    "wem_ess_market_price",
                    row[0],
                )
            )
    cursor.executemany(
        """
        INSERT INTO wem_reserve_shortfall_snapshot
        (interval_start_utc, interval_end_utc, reserve_service, shortfall_mw, severity, source_table, source_interval)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (interval_start_utc, reserve_service) DO UPDATE SET interval_end_utc=EXCLUDED.interval_end_utc, shortfall_mw=EXCLUDED.shortfall_mw, severity=EXCLUDED.severity, source_table=EXCLUDED.source_table, source_interval=EXCLUDED.source_interval
        """,
        inserts,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_wem_reserve_shortfall",
        sync_status="ok",
        last_success_at=_utc_now_iso(),
        last_attempt_at=_utc_now_iso(),
        last_error=None,
        detail={"row_count": len(inserts), "source_table": "wem_ess_market_price"},
    )
    return len(inserts)


def sync_operational_demand_actual(conn: Any, limit: int):
    names = fetch_recent_zip_names(OD_ACTUAL_URL, OD_ACTUAL_RE, limit)
    records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(OD_ACTUAL_URL, name))
        for row in rows:
            records.append(
                (
                    row["REGIONID"],
                    row["INTERVAL_DATETIME"],
                    float(row["OPERATIONAL_DEMAND"] or 0.0),
                    float(row.get("OPERATIONAL_DEMAND_ADJUSTMENT") or 0.0),
                    float(row.get("WDR_ESTIMATE") or 0.0),
                    row.get("LASTCHANGED", ""),
                    name,
                )
            )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO operational_demand_actual_hh
        (region_id, interval_datetime, operational_demand, operational_demand_adjustment, wdr_estimate, lastchanged, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, interval_datetime) DO UPDATE SET operational_demand=EXCLUDED.operational_demand, operational_demand_adjustment=EXCLUDED.operational_demand_adjustment, wdr_estimate=EXCLUDED.wdr_estimate, lastchanged=EXCLUDED.lastchanged, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_load_actual",
        sync_status="ok" if records else "error",
        last_success_at=_utc_now_iso() if records else None,
        last_attempt_at=_utc_now_iso(),
        last_error=None if records else "no operational demand actual rows synced",
        detail={"row_count": len(records)},
    )
    return len(records)


def sync_operational_demand_forecast(conn: Any, limit: int):
    names = fetch_recent_zip_names(OD_FORECAST_URL, OD_FORECAST_RE, limit)
    records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(OD_FORECAST_URL, name))
        for row in rows:
            records.append(
                (
                    row["REGIONID"],
                    row["INTERVAL_DATETIME"],
                    row["LOAD_DATE"],
                    float(row["OPERATIONAL_DEMAND_POE10"] or 0.0),
                    float(row["OPERATIONAL_DEMAND_POE50"] or 0.0),
                    float(row["OPERATIONAL_DEMAND_POE90"] or 0.0),
                    row.get("LASTCHANGED", ""),
                    name,
                )
            )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO operational_demand_forecast_hh
        (region_id, interval_datetime, load_date, operational_demand_poe10, operational_demand_poe50, operational_demand_poe90, lastchanged, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, interval_datetime, load_date) DO UPDATE SET operational_demand_poe10=EXCLUDED.operational_demand_poe10, operational_demand_poe50=EXCLUDED.operational_demand_poe50, operational_demand_poe90=EXCLUDED.operational_demand_poe90, lastchanged=EXCLUDED.lastchanged, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_load_forecast",
        sync_status="ok" if records else "error",
        last_success_at=_utc_now_iso() if records else None,
        last_attempt_at=_utc_now_iso(),
        last_error=None if records else "no operational demand forecast rows synced",
        detail={"row_count": len(records)},
    )
    return len(records)


def sync_rooftop_pv_actual(conn: Any, limit: int):
    names = fetch_recent_zip_names(ROOFTOP_ACTUAL_URL, ROOFTOP_ACTUAL_RE, limit)
    records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(ROOFTOP_ACTUAL_URL, name))
        for row in rows:
            records.append(
                (
                    row["REGIONID"],
                    row["INTERVAL_DATETIME"],
                    float(row["POWER"] or 0.0),
                    float(row.get("QI") or 0.0),
                    row.get("TYPE", ""),
                    row.get("LASTCHANGED", ""),
                    name,
                )
            )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO rooftop_pv_actual_measurement
        (region_id, interval_datetime, power, qi, source_type, lastchanged, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, interval_datetime) DO UPDATE SET power=EXCLUDED.power, qi=EXCLUDED.qi, source_type=EXCLUDED.source_type, lastchanged=EXCLUDED.lastchanged, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_rooftop_pv",
        sync_status="ok" if records else "error",
        last_success_at=_utc_now_iso() if records else None,
        last_attempt_at=_utc_now_iso(),
        last_error=None if records else "no rooftop pv actual rows synced",
        detail={"row_count": len(records)},
    )
    return len(records)


def sync_rooftop_pv_forecast(conn: Any, limit: int):
    names = fetch_recent_zip_names(ROOFTOP_FORECAST_URL, ROOFTOP_FORECAST_RE, limit)
    records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(ROOFTOP_FORECAST_URL, name))
        for row in rows:
            records.append(
                (
                    row["REGIONID"],
                    row["INTERVAL_DATETIME"],
                    row["VERSION_DATETIME"],
                    float(row["POWERMEAN"] or 0.0),
                    float(row["POWERPOE50"] or 0.0),
                    float(row["POWERPOELOW"] or 0.0),
                    float(row["POWERPOEHIGH"] or 0.0),
                    row.get("LASTCHANGED", ""),
                    name,
                )
            )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO rooftop_pv_forecast
        (region_id, interval_datetime, version_datetime, powermean, powerpoe50, powerpoelow, powerpoehigh, lastchanged, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, interval_datetime, version_datetime) DO UPDATE SET powermean=EXCLUDED.powermean, powerpoe50=EXCLUDED.powerpoe50, powerpoelow=EXCLUDED.powerpoelow, powerpoehigh=EXCLUDED.powerpoehigh, lastchanged=EXCLUDED.lastchanged, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_rooftop_pv_forecast",
        sync_status="ok" if records else "error",
        last_success_at=_utc_now_iso() if records else None,
        last_attempt_at=_utc_now_iso(),
        last_error=None if records else "no rooftop pv forecast rows synced",
        detail={"row_count": len(records)},
    )
    return len(records)


def sync_dispatch_summary(conn: Any, limit: int):
    names = fetch_recent_zip_names(DISPATCH_URL, DISPATCH_RE, limit)
    region_records = []
    interconnector_records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(DISPATCH_URL, name))
        for row in rows:
            if "REGIONID" in row and "SETTLEMENTDATE" in row and "SS_SOLAR_UIGF" in row and "SS_WIND_UIGF" in row:
                region_records.append(
                    (
                        row["REGIONID"],
                        row["SETTLEMENTDATE"],
                        float(row.get("SS_SOLAR_UIGF") or 0.0),
                        float(row.get("SS_WIND_UIGF") or 0.0),
                        float(row.get("SS_SOLAR_CLEAREDMW") or 0.0),
                        float(row.get("SS_WIND_CLEAREDMW") or 0.0),
                        name,
                    )
                )
            elif "FROM_REGIONID" in row and "TO_REGIONID" in row and "MWFLOW" in row and "METEREDMWFLOW" in row:
                interconnector_id = f"{row['FROM_REGIONID']}-{row['TO_REGIONID']}"
                interconnector_records.append(
                    (
                        interconnector_id,
                        row["SETTLEMENTDATE"],
                        row["FROM_REGIONID"],
                        row["TO_REGIONID"],
                        float(row.get("MWFLOW") or 0.0),
                        float(row.get("METEREDMWFLOW") or 0.0),
                        name,
                    )
                )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO dispatch_region_summary
        (region_id, settlement_date, ss_solar_uigf, ss_wind_uigf, ss_solar_clearedmw, ss_wind_clearedmw, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, settlement_date) DO UPDATE SET ss_solar_uigf=EXCLUDED.ss_solar_uigf, ss_wind_uigf=EXCLUDED.ss_wind_uigf, ss_solar_clearedmw=EXCLUDED.ss_solar_clearedmw, ss_wind_clearedmw=EXCLUDED.ss_wind_clearedmw, source_file=EXCLUDED.source_file
        """,
        region_records,
    )
    conn.executemany(
        """
        INSERT INTO dispatch_interconnector_flow
        (interconnector_id, settlement_date, from_regionid, to_regionid, mwflow, meteredmwflow, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (interconnector_id, settlement_date) DO UPDATE SET from_regionid=EXCLUDED.from_regionid, to_regionid=EXCLUDED.to_regionid, mwflow=EXCLUDED.mwflow, meteredmwflow=EXCLUDED.meteredmwflow, source_file=EXCLUDED.source_file
        """,
        interconnector_records,
    )
    conn.commit()
    dispatch_success_at = _utc_now_iso()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_wind_actual",
        sync_status="ok" if region_records else "error",
        last_success_at=dispatch_success_at if region_records else None,
        last_attempt_at=dispatch_success_at,
        last_error=None if region_records else "no dispatch region rows synced",
        detail={"row_count": len(region_records), "metric": "ss_wind_clearedmw"},
    )
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_solar_actual",
        sync_status="ok" if region_records else "error",
        last_success_at=dispatch_success_at if region_records else None,
        last_attempt_at=dispatch_success_at,
        last_error=None if region_records else "no dispatch region rows synced",
        detail={"row_count": len(region_records), "metric": "ss_solar_clearedmw"},
    )
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_interconnector_flow",
        sync_status="ok" if interconnector_records else "error",
        last_success_at=dispatch_success_at if interconnector_records else None,
        last_attempt_at=dispatch_success_at,
        last_error=None if interconnector_records else "no interconnector flow rows synced",
        detail={"row_count": len(interconnector_records)},
    )
    return len(region_records), len(interconnector_records)


def sync_predispatch_summary(conn: Any, limit: int):
    names = fetch_recent_zip_names(PREDISPATCH_URL, PREDISPATCH_RE, limit)
    records = []
    for name in names:
        _, rows = parse_aemo_report(fetch_zip_lines(PREDISPATCH_URL, name))
        for row in rows:
            if "REGIONID" in row and "DATETIME" in row and "SS_SOLAR_UIGF" in row and "SS_WIND_UIGF" in row:
                records.append(
                    (
                        row["REGIONID"],
                        row["DATETIME"],
                        row["LASTCHANGED"],
                        float(row.get("SS_SOLAR_UIGF") or 0.0),
                        float(row.get("SS_WIND_UIGF") or 0.0),
                        float(row.get("SS_SOLAR_CLEAREDMW") or 0.0),
                        float(row.get("SS_WIND_CLEAREDMW") or 0.0),
                        name,
                    )
                )
        time.sleep(0.05)
    conn.executemany(
        """
        INSERT INTO predispatch_region_solution
        (region_id, interval_datetime, run_datetime, ss_solar_uigf, ss_wind_uigf, ss_solar_clearedmw, ss_wind_clearedmw, source_file)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT (region_id, interval_datetime, run_datetime) DO UPDATE SET ss_solar_uigf=EXCLUDED.ss_solar_uigf, ss_wind_uigf=EXCLUDED.ss_wind_uigf, ss_solar_clearedmw=EXCLUDED.ss_solar_clearedmw, ss_wind_clearedmw=EXCLUDED.ss_wind_clearedmw, source_file=EXCLUDED.source_file
        """,
        records,
    )
    conn.commit()
    predispatch_success_at = _utc_now_iso()
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_wind_forecast",
        sync_status="ok" if records else "error",
        last_success_at=predispatch_success_at if records else None,
        last_attempt_at=predispatch_success_at,
        last_error=None if records else "no predispatch rows synced",
        detail={"row_count": len(records), "metric": "ss_wind_uigf"},
    )
    _upsert_aemo_source_sync_state(
        conn,
        source_id="aemo_nem_solar_forecast",
        sync_status="ok" if records else "error",
        last_success_at=predispatch_success_at if records else None,
        last_attempt_at=predispatch_success_at,
        last_error=None if records else "no predispatch rows synced",
        detail={"row_count": len(records), "metric": "ss_solar_uigf"},
    )
    return len(records)


def sync_all(actual_limit: int, forecast_limit: int):
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))
    from deps import get_db
    db = get_db()
    with db.get_connection() as conn:
        ensure_tables(conn)
        conn.commit()
        print("[sync] operational demand actual")
        print(sync_operational_demand_actual(conn, actual_limit))
        print("[sync] operational demand forecast")
        print(sync_operational_demand_forecast(conn, forecast_limit))
        print("[sync] rooftop pv actual")
        print(sync_rooftop_pv_actual(conn, actual_limit))
        print("[sync] rooftop pv forecast")
        print(sync_rooftop_pv_forecast(conn, forecast_limit))
        print("[sync] dispatch summary")
        print(sync_dispatch_summary(conn, actual_limit))
        print("[sync] predispatch summary")
        print(sync_predispatch_summary(conn, forecast_limit))
        print("[sync] bom weather")
        print(sync_bom_weather_observations(conn))
        print("[sync] pdpasa duid availability")
        print(sync_pdpasa_duid_availability(conn, forecast_limit))
        print("[sync] du detail summary")
        print(sync_du_detail_summary(conn))
        print("[sync] wem reserve shortfall snapshot")
        print(sync_wem_reserve_shortfall_snapshot(conn))


def main():
    parser = argparse.ArgumentParser(description="Sync AEMO P0 foundation datasets into landing tables.")
    parser.add_argument("--actual-limit", type=int, default=192)
    parser.add_argument("--forecast-limit", type=int, default=24)
    args = parser.parse_args()
    sync_all(args.actual_limit, args.forecast_limit)


if __name__ == "__main__":
    main()
