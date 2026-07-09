#!/usr/bin/env python3
"""
WEM 数据批量导入脚本 — PostgreSQL 版（服务器端运行）
=====================================================
处理 32GB+ WEM 原始数据（ZIP/JSON/CSV），导入到 PostgreSQL。

数据类型：
  1. reference_trading_price/  — 960 ZIP（交易电价，30分钟间隔）
  2. dispatch_solution/        — 109 ZIP（调度方案，5分钟间隔，33GB）
  3. fcess_capabilities.csv    — FCAS 能力数据

设计要点：
  - psycopg2 + COPY 协议（比 INSERT 快 100 倍）
  - 流式 ZIP 解压（逐个 JSON 处理，不全部加载到内存）
  - 断点续传：记录已完成文件，重跑自动跳过
  - 进度报告：实时显示进度和预估剩余时间

前置要求：
  pip3 install psycopg2-binary

用法：
    python3 wem_server_import.py
    python3 wem_server_import.py --dry-run          # 只扫描不写入
    python3 wem_server_import.py --skip-dispatch     # 跳过 33GB 调度数据
    python3 wem_server_import.py --skip-trading      # 跳过交易电价
"""

import argparse
import csv
import io
import json
import logging
import os
import sys
import time
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

# ── 配置 ──────────────────────────────────────────────────────────────
# BASE_DIR 和 PROGRESS_FILE 由 --base-dir 参数动态设置（支持宿主机和 Docker 两种模式）
BASE_DIR = None
PROGRESS_FILE = None

# PostgreSQL 连接（通过宿主机暴露的端口或 Docker 内网）
PG_DSN = "postgresql://aemo:{password}@{host}:{port}/aemo_data"

BATCH_SIZE = 50_000  # COPY 每批行数
AWST = timezone(timedelta(hours=8))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("wem_import")


# ── 工具函数 ──────────────────────────────────────────────────────────
def safe_float(v):
    if v in (None, "", "null", "NULL", "-", "N/A"):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def normalize_ts(raw: str) -> str:
    if not raw:
        return ""
    raw = raw.strip()
    try:
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is not None:
            dt = dt.astimezone(AWST)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except ValueError:
        return raw.replace("T", " ")[:19]


def load_progress() -> dict:
    if os.path.exists(PROGRESS_FILE):
        try:
            with open(PROGRESS_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, KeyError):
            pass
    return {"completed": [], "stats": {}}


def save_progress(progress: dict):
    os.makedirs(os.path.dirname(PROGRESS_FILE), exist_ok=True)
    with open(PROGRESS_FILE, "w") as f:
        json.dump(progress, f, indent=2)


# ── 数据库初始化 ──────────────────────────────────────────────────────
def init_pg(pg_conn):
    cur = pg_conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_capabilities (
            facility_code TEXT PRIMARY KEY,
            participant_code TEXT,
            participant_name TEXT,
            facility_class TEXT,
            max_accredited_regulation_raise DOUBLE PRECISION,
            max_accredited_regulation_lower DOUBLE PRECISION,
            max_accredited_contingency_raise DOUBLE PRECISION,
            max_accredited_contingency_lower DOUBLE PRECISION,
            max_accredited_rocof DOUBLE PRECISION,
            facility_speed_factor DOUBLE PRECISION,
            rocof_ride_through_capability DOUBLE PRECISION,
            extracted_at TEXT
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_market_price (
            dispatch_interval TEXT PRIMARY KEY,
            energy_price DOUBLE PRECISION,
            regulation_raise_price DOUBLE PRECISION,
            regulation_lower_price DOUBLE PRECISION,
            contingency_raise_price DOUBLE PRECISION,
            contingency_lower_price DOUBLE PRECISION,
            rocof_price DOUBLE PRECISION,
            available_regulation_raise DOUBLE PRECISION,
            available_regulation_lower DOUBLE PRECISION,
            available_contingency_raise DOUBLE PRECISION,
            available_contingency_lower DOUBLE PRECISION,
            available_rocof DOUBLE PRECISION,
            in_service_regulation_raise DOUBLE PRECISION,
            in_service_regulation_lower DOUBLE PRECISION,
            in_service_contingency_raise DOUBLE PRECISION,
            in_service_contingency_lower DOUBLE PRECISION,
            in_service_rocof DOUBLE PRECISION,
            requirement_regulation_raise DOUBLE PRECISION,
            requirement_regulation_lower DOUBLE PRECISION,
            requirement_contingency_raise DOUBLE PRECISION,
            requirement_contingency_lower DOUBLE PRECISION,
            requirement_rocof DOUBLE PRECISION,
            shortfall_regulation_raise DOUBLE PRECISION,
            shortfall_regulation_lower DOUBLE PRECISION,
            shortfall_contingency_raise DOUBLE PRECISION,
            shortfall_contingency_lower DOUBLE PRECISION,
            shortfall_rocof DOUBLE PRECISION,
            dispatch_total_regulation_raise DOUBLE PRECISION,
            dispatch_total_regulation_lower DOUBLE PRECISION,
            dispatch_total_contingency_raise DOUBLE PRECISION,
            dispatch_total_contingency_lower DOUBLE PRECISION,
            dispatch_total_rocof DOUBLE PRECISION,
            capped_regulation_raise INTEGER DEFAULT 0,
            capped_regulation_lower INTEGER DEFAULT 0,
            capped_contingency_raise INTEGER DEFAULT 0,
            capped_contingency_lower INTEGER DEFAULT 0,
            capped_rocof INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS wem_ess_constraint_summary (
            dispatch_interval TEXT PRIMARY KEY,
            binding_count INTEGER DEFAULT 0,
            near_binding_count INTEGER DEFAULT 0,
            binding_max_shadow_price DOUBLE PRECISION DEFAULT 0,
            near_binding_max_shadow_price DOUBLE PRECISION DEFAULT 0,
            max_formulation_shadow_price DOUBLE PRECISION DEFAULT 0,
            max_facility_shadow_price DOUBLE PRECISION DEFAULT 0,
            max_network_shadow_price DOUBLE PRECISION DEFAULT 0,
            max_generic_shadow_price DOUBLE PRECISION DEFAULT 0
        )
    """)

    pg_conn.commit()


def ensure_trading_table(pg_conn, year: int):
    table = f"trading_price_{year}"
    cur = pg_conn.cursor()
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS {table} (
            id BIGSERIAL PRIMARY KEY,
            settlement_date TEXT NOT NULL,
            region_id TEXT NOT NULL,
            rrp_aud_mwh DOUBLE PRECISION NOT NULL,
            raise1sec_rrp DOUBLE PRECISION, raise6sec_rrp DOUBLE PRECISION,
            raise60sec_rrp DOUBLE PRECISION, raise5min_rrp DOUBLE PRECISION,
            raisereg_rrp DOUBLE PRECISION,
            lower1sec_rrp DOUBLE PRECISION, lower6sec_rrp DOUBLE PRECISION,
            lower60sec_rrp DOUBLE PRECISION, lower5min_rrp DOUBLE PRECISION,
            lowerreg_rrp DOUBLE PRECISION,
            UNIQUE(settlement_date, region_id)
        )
    """)
    cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{table}_search ON {table}(region_id, settlement_date)")
    pg_conn.commit()


# ── COPY 工具 ─────────────────────────────────────────────────────────
def _pg_copy_insert(pg_conn, table: str, columns: str, rows: list[tuple]):
    """用 COPY 协议批量插入，失败时回退到 INSERT ... ON CONFLICT。"""
    if not rows:
        return
    cur = pg_conn.cursor()
    sio = io.StringIO()
    for row in rows:
        parts = []
        for v in row:
            if v is None:
                parts.append("\\N")
            else:
                parts.append(str(v))
        sio.write("\t".join(parts) + "\n")
    sio.seek(0)
    try:
        cur.copy_expert(
            f"COPY {table} ({columns}) FROM STDIN "
            f"WITH (FORMAT text, DELIMITER E'\\t', NULL '\\\\N')",
            sio,
        )
        pg_conn.commit()
    except Exception:
        pg_conn.rollback()
        # 回退: 逐行 INSERT OR REPLACE
        n_cols = len(rows[0])
        col_list = columns.split(",")
        placeholders = ",".join(["%s"] * n_cols)
        update_cols = ",".join(f"{c}=EXCLUDED.{c}" for c in col_list if c not in ("id",))
        pk = col_list[0] if col_list[0] != "id" else f"{col_list[1]},{col_list[2]}"
        sql = (
            f"INSERT INTO {table} ({columns}) VALUES ({placeholders}) "
            f"ON CONFLICT ({pk}) DO UPDATE SET {update_cols}"
        )
        for row in rows:
            try:
                cur.execute(sql, row)
            except Exception:
                pg_conn.rollback()
        pg_conn.commit()


# ═══════════════════════════════════════════════════════════════════════
# 1. 交易电价导入
# ═══════════════════════════════════════════════════════════════════════
def import_trading_prices(pg_conn, progress: dict, dry_run: bool):
    base = os.path.join(BASE_DIR, "reference_trading_price")
    if not os.path.isdir(base):
        log.warning("交易电价目录不存在: %s", base)
        return

    zips = sorted(f for f in os.listdir(base) if f.endswith(".zip"))
    completed = set(progress["completed"])
    pending = [f for f in zips if f"tp_{f}" not in completed]
    log.info("═══ 交易电价: %d 个 ZIP，%d 待处理 ═══", len(zips), len(pending))

    if not pending:
        log.info("交易电价: 全部已完成，跳过")
        return

    t0 = time.time()
    total_rows = 0
    created_tables: set[int] = set()

    for idx, fname in enumerate(pending, 1):
        fpath = os.path.join(base, fname)
        buf: list[tuple] = []

        try:
            with zipfile.ZipFile(fpath, "r") as zf:
                for name in zf.namelist():
                    if not name.endswith(".json"):
                        continue
                    raw = zf.read(name)
                    try:
                        payload = json.loads(raw)
                    except json.JSONDecodeError:
                        continue
                    prices = []
                    if isinstance(payload, list):
                        prices = payload
                    elif isinstance(payload, dict):
                        data = payload.get("data", payload)
                        prices = data.get("referenceTradingPrices", [])
                    for item in prices:
                        interval = normalize_ts(item.get("tradingInterval", ""))
                        price = safe_float(item.get("referenceTradingPrice"))
                        if interval and price is not None:
                            buf.append((interval, "WEM", round(price, 2)))
        except (zipfile.BadZipFile, OSError) as e:
            log.warning("[%d/%d] %s — 读取失败: %s", idx, len(pending), fname, e)
            continue

        if not dry_run and buf:
            by_year: dict[int, list] = {}
            for row in buf:
                y = int(row[0][:4])
                by_year.setdefault(y, []).append(row)
            for year, rows in by_year.items():
                if year not in created_tables:
                    ensure_trading_table(pg_conn, year)
                    created_tables.add(year)
                _pg_copy_insert(
                    pg_conn, f"trading_price_{year}",
                    "settlement_date,region_id,rrp_aud_mwh", rows,
                )

        total_rows += len(buf)
        if not dry_run:
            completed.add(f"tp_{fname}")
            progress["completed"] = sorted(completed)
            save_progress(progress)

        elapsed = time.time() - t0
        rate = idx / elapsed if elapsed > 0 else 0
        eta = (len(pending) - idx) / rate if rate > 0 else 0
        if idx % 50 == 0 or idx == len(pending):
            log.info("[%d/%d] %s: %d rows | %.0f files/s | ETA %.0fs",
                     idx, len(pending), fname, len(buf), rate, eta)

    log.info("交易电价完成: %d rows in %.1fs", total_rows, time.time() - t0)


# ═══════════════════════════════════════════════════════════════════════
# 2. 调度方案导入
# ═══════════════════════════════════════════════════════════════════════
_SVC_MAP = {
    "regulationRaise": "regulation_raise",
    "regulationLower": "regulation_lower",
    "contingencyRaise": "contingency_raise",
    "contingencyLower": "contingency_lower",
    "rocof": "rocof",
}
_AVAIL_MAP = {k: f"available_{v}" for k, v in _SVC_MAP.items()}
_IN_SVC_MAP = {k: f"in_service_{v}" for k, v in _SVC_MAP.items()}
_REQ_MAP = {k: f"requirement_{v}" for k, v in _SVC_MAP.items()}
_SHORT_MAP = {
    "regulationRaiseDeficit": "shortfall_regulation_raise",
    "regulationLowerDeficit": "shortfall_regulation_lower",
    "contingencyRaiseDeficit": "shortfall_contingency_raise",
    "contingencyLowerDeficit": "shortfall_contingency_lower",
    "rocofDeficit": "shortfall_rocof",
}
_DTOTAL_MAP = {k: f"dispatch_total_{v}" for k, v in _SVC_MAP.items()}
_CONSTRAINT_TYPE = {
    "formulation": "max_formulation_shadow_price",
    "facility": "max_facility_shadow_price",
    "network": "max_network_shadow_price",
    "generic": "max_generic_shadow_price",
}

_MARKET_COLS = (
    "dispatch_interval,energy_price,"
    "regulation_raise_price,regulation_lower_price,"
    "contingency_raise_price,contingency_lower_price,rocof_price,"
    "available_regulation_raise,available_regulation_lower,"
    "available_contingency_raise,available_contingency_lower,available_rocof,"
    "in_service_regulation_raise,in_service_regulation_lower,"
    "in_service_contingency_raise,in_service_contingency_lower,in_service_rocof,"
    "requirement_regulation_raise,requirement_regulation_lower,"
    "requirement_contingency_raise,requirement_contingency_lower,requirement_rocof,"
    "shortfall_regulation_raise,shortfall_regulation_lower,"
    "shortfall_contingency_raise,shortfall_contingency_lower,shortfall_rocof,"
    "dispatch_total_regulation_raise,dispatch_total_regulation_lower,"
    "dispatch_total_contingency_raise,dispatch_total_contingency_lower,"
    "dispatch_total_rocof,"
    "capped_regulation_raise,capped_regulation_lower,"
    "capped_contingency_raise,capped_contingency_lower,capped_rocof"
)


def _parse_dispatch_json(raw: bytes):
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, UnicodeDecodeError):
        return None, None

    wrapper = payload.get("data", payload)
    primary = normalize_ts(wrapper.get("primaryDispatchInterval", ""))
    solutions = wrapper.get("solutionData", [])

    market_row = None
    constraint_row = None

    for sol in solutions:
        scenario = sol.get("scenario")
        dtype = sol.get("dispatchType")
        if scenario not in (None, "", "Reference"):
            continue
        if dtype not in (None, "", "Dispatch"):
            continue
        di = normalize_ts(sol.get("dispatchInterval", ""))
        if not di:
            continue
        if primary and di != primary:
            continue

        raw_prices = sol.get("prices", {})
        if isinstance(raw_prices, list):
            prices = {}
            for e in raw_prices:
                if isinstance(e, dict):
                    svc = e.get("marketService")
                    val = safe_float(e.get("price"))
                    if svc and val is not None:
                        prices[svc] = val
        elif isinstance(raw_prices, dict):
            prices = {k: safe_float(v) for k, v in raw_prices.items()
                      if safe_float(v) is not None}
        else:
            prices = {}

        row = {"dispatch_interval": di, "energy_price": prices.get("energy")}
        for raw_k, db_k in _SVC_MAP.items():
            row[f"{db_k}_price"] = prices.get(raw_k)
        for mapping, src in (
            (_AVAIL_MAP, sol.get("availableQuantities") or {}),
            (_IN_SVC_MAP, sol.get("inServiceQuantities") or {}),
            (_REQ_MAP, sol.get("marketServiceRequirements") or {}),
            (_SHORT_MAP, sol.get("marketShortfalls") or {}),
            (_DTOTAL_MAP, sol.get("dispatchTotal") or {}),
        ):
            if not isinstance(src, dict):
                src = {}
            for raw_k, db_k in mapping.items():
                row[db_k] = safe_float(src.get(raw_k))
        capped = {}
        for entry in (sol.get("priceSetting") or []):
            if isinstance(entry, dict):
                svc = entry.get("marketService")
                if svc in _SVC_MAP:
                    capped[svc] = 1 if entry.get("isMarketServiceCapped") else 0
        for raw_k, db_k in _SVC_MAP.items():
            row[f"capped_{db_k}"] = capped.get(raw_k, 0)

        if any(row.get(f"{v}_price") is not None for v in _SVC_MAP.values()):
            market_row = row

        c_row = {
            "dispatch_interval": di,
            "binding_count": 0, "near_binding_count": 0,
            "binding_max_shadow_price": 0.0, "near_binding_max_shadow_price": 0.0,
            "max_formulation_shadow_price": 0.0, "max_facility_shadow_price": 0.0,
            "max_network_shadow_price": 0.0, "max_generic_shadow_price": 0.0,
        }
        for c in (sol.get("constraints") or []):
            if not isinstance(c, dict):
                continue
            sp = abs(safe_float(c.get("shadowPrice")) or 0.0)
            if c.get("bindingConstraintFlag"):
                c_row["binding_count"] += 1
                c_row["binding_max_shadow_price"] = max(c_row["binding_max_shadow_price"], sp)
                tk = (c.get("constraintType") or "").lower()
                fn = _CONSTRAINT_TYPE.get(tk)
                if fn:
                    c_row[fn] = max(c_row[fn], sp)
            if c.get("nearBindingConstraintFlag"):
                c_row["near_binding_count"] += 1
                c_row["near_binding_max_shadow_price"] = max(
                    c_row["near_binding_max_shadow_price"], sp)
        constraint_row = c_row
        break

    return market_row, constraint_row


def _market_tuple(m: dict) -> tuple:
    return (
        m["dispatch_interval"], m["energy_price"],
        m.get("regulation_raise_price"), m.get("regulation_lower_price"),
        m.get("contingency_raise_price"), m.get("contingency_lower_price"),
        m.get("rocof_price"),
        m.get("available_regulation_raise"), m.get("available_regulation_lower"),
        m.get("available_contingency_raise"), m.get("available_contingency_lower"),
        m.get("available_rocof"),
        m.get("in_service_regulation_raise"), m.get("in_service_regulation_lower"),
        m.get("in_service_contingency_raise"), m.get("in_service_contingency_lower"),
        m.get("in_service_rocof"),
        m.get("requirement_regulation_raise"), m.get("requirement_regulation_lower"),
        m.get("requirement_contingency_raise"), m.get("requirement_contingency_lower"),
        m.get("requirement_rocof"),
        m.get("shortfall_regulation_raise"), m.get("shortfall_regulation_lower"),
        m.get("shortfall_contingency_raise"), m.get("shortfall_contingency_lower"),
        m.get("shortfall_rocof"),
        m.get("dispatch_total_regulation_raise"), m.get("dispatch_total_regulation_lower"),
        m.get("dispatch_total_contingency_raise"), m.get("dispatch_total_contingency_lower"),
        m.get("dispatch_total_rocof"),
        m.get("capped_regulation_raise", 0), m.get("capped_regulation_lower", 0),
        m.get("capped_contingency_raise", 0), m.get("capped_contingency_lower", 0),
        m.get("capped_rocof", 0),
    )


def _constraint_tuple(c: dict) -> tuple:
    return (
        c["dispatch_interval"],
        c["binding_count"], c["near_binding_count"],
        c["binding_max_shadow_price"], c["near_binding_max_shadow_price"],
        c["max_formulation_shadow_price"], c["max_facility_shadow_price"],
        c["max_network_shadow_price"], c["max_generic_shadow_price"],
    )


def import_dispatch_solutions(pg_conn, progress: dict, dry_run: bool):
    base = os.path.join(BASE_DIR, "dispatch_solution")
    if not os.path.isdir(base):
        log.warning("调度方案目录不存在: %s", base)
        return

    zips = sorted(f for f in os.listdir(base) if f.endswith(".zip"))
    completed = set(progress["completed"])
    pending = [f for f in zips if f"ds_{f}" not in completed]
    log.info("═══ 调度方案: %d 个 ZIP（~33GB），%d 待处理 ═══", len(zips), len(pending))

    if not pending:
        log.info("调度方案: 全部已完成，跳过")
        return

    t0 = time.time()
    total_market = 0
    total_constraint = 0

    for idx, fname in enumerate(pending, 1):
        fpath = os.path.join(base, fname)
        market_buf: list[tuple] = []
        constraint_buf: list[tuple] = []
        file_market = 0
        file_constraint = 0
        errors = 0

        try:
            with zipfile.ZipFile(fpath, "r") as zf:
                for name in zf.namelist():
                    if not name.endswith(".json"):
                        continue
                    try:
                        raw = zf.read(name)
                        m_row, c_row = _parse_dispatch_json(raw)
                        if m_row:
                            market_buf.append(_market_tuple(m_row))
                        if c_row:
                            constraint_buf.append(_constraint_tuple(c_row))
                    except Exception:
                        errors += 1

                    if len(market_buf) >= BATCH_SIZE:
                        if not dry_run:
                            _pg_copy_insert(pg_conn, "wem_ess_market_price",
                                            _MARKET_COLS, market_buf)
                            _pg_copy_insert(pg_conn, "wem_ess_constraint_summary",
                                            "dispatch_interval,binding_count,near_binding_count,"
                                            "binding_max_shadow_price,near_binding_max_shadow_price,"
                                            "max_formulation_shadow_price,max_facility_shadow_price,"
                                            "max_network_shadow_price,max_generic_shadow_price",
                                            constraint_buf)
                        file_market += len(market_buf)
                        file_constraint += len(constraint_buf)
                        market_buf.clear()
                        constraint_buf.clear()
        except (zipfile.BadZipFile, OSError) as e:
            log.warning("[%d/%d] %s — ZIP 失败: %s", idx, len(pending), fname, e)
            continue

        if market_buf and not dry_run:
            _pg_copy_insert(pg_conn, "wem_ess_market_price", _MARKET_COLS, market_buf)
            _pg_copy_insert(pg_conn, "wem_ess_constraint_summary",
                            "dispatch_interval,binding_count,near_binding_count,"
                            "binding_max_shadow_price,near_binding_max_shadow_price,"
                            "max_formulation_shadow_price,max_facility_shadow_price,"
                            "max_network_shadow_price,max_generic_shadow_price",
                            constraint_buf)
        file_market += len(market_buf)
        file_constraint += len(constraint_buf)
        total_market += file_market
        total_constraint += file_constraint

        if not dry_run:
            completed.add(f"ds_{fname}")
            progress["completed"] = sorted(completed)
            save_progress(progress)

        elapsed = time.time() - t0
        rate = idx / elapsed if elapsed > 0 else 0
        eta = (len(pending) - idx) / rate if rate > 0 else 0
        fsize_mb = os.path.getsize(fpath) / 1024 / 1024
        log.info(
            "[%d/%d] %s (%.0fMB): m=%d c=%d err=%d | total_m=%d | "
            "%.2f f/s | ETA %.0fmin",
            idx, len(pending), fname, fsize_mb,
            file_market, file_constraint, errors, total_market,
            rate, eta / 60,
        )

    log.info("调度方案完成: market=%d, constraint=%d in %.1fs",
             total_market, total_constraint, time.time() - t0)


# ═══════════════════════════════════════════════════════════════════════
# 3. FCAS 能力数据导入
# ═══════════════════════════════════════════════════════════════════════
def import_fcess_capabilities(pg_conn, dry_run: bool):
    fpath = os.path.join(BASE_DIR, "fcess_capabilities.csv")
    if not os.path.exists(fpath):
        log.warning("FCAS 文件不存在: %s", fpath)
        return
    log.info("═══ FCAS 能力数据 ═══")
    records = []
    with open(fpath, "r", encoding="utf-8-sig", errors="replace") as f:
        reader = csv.DictReader(f)
        for row in reader:
            fc = (row.get("Facility Code") or "").strip()
            if not fc:
                continue
            records.append((
                fc,
                (row.get("Participant Code") or "").strip() or None,
                (row.get("Participant Name") or "").strip() or None,
                (row.get("Facility Class") or "").strip() or None,
                safe_float(row.get("Max Accredited Regulation Raise")),
                safe_float(row.get("Max Accredited Regulation Lower")),
                safe_float(row.get("Max Accredited Contingency Raise")),
                safe_float(row.get("Max Accredited Contingency Lower")),
                safe_float(row.get("Max Accredited ROCOF")),
                safe_float(row.get("Facility Speed Factor")),
                safe_float(row.get("RoCoF Ride-Through Capability")),
                (row.get("Extracted At") or "").strip() or None,
            ))
    if not dry_run and records:
        _pg_copy_insert(
            pg_conn, "wem_ess_capabilities",
            "facility_code,participant_code,participant_name,facility_class,"
            "max_accredited_regulation_raise,max_accredited_regulation_lower,"
            "max_accredited_contingency_raise,max_accredited_contingency_lower,"
            "max_accredited_rocof,facility_speed_factor,"
            "rocof_ride_through_capability,extracted_at",
            records,
        )
    log.info("FCAS: %d 条导入完成", len(records))


# (SQLite migration removed - PG only)

# ═══════════════════════════════════════════════════════════════════════
# Main
# ═══════════════════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(description="WEM 数据批量导入 PostgreSQL")
    parser.add_argument("--dry-run", action="store_true", help="只扫描不写入")
    parser.add_argument("--skip-dispatch", action="store_true", help="跳过调度方案（33GB）")
    parser.add_argument("--skip-trading", action="store_true", help="跳过交易电价")
    parser.add_argument("--skip-fcess", action="store_true", help="跳过 FCAS")
    parser.add_argument("--pg-password", default="aemo_pg_pass_2026", help="PG 密码")
    parser.add_argument("--pg-host", default="localhost", help="PG 主机地址（Docker 内用 postgres）")
    parser.add_argument("--pg-port", type=int, default=15432, help="PG 端口（宿主机 15432，Docker 内 5432）")
    parser.add_argument("--base-dir", default=None,
                        help="WEM 原始数据目录（默认自动检测）")
    parser.add_argument("--progress-file", default=None,
                        help="进度文件路径（默认写到可写目录，避开只读数据目录）")
    args = parser.parse_args()

    # 自动检测 BASE_DIR（声明 global 才能在函数内修改模块级变量）
    global BASE_DIR, PROGRESS_FILE
    if args.base_dir:
        BASE_DIR = args.base_dir
    elif os.path.isdir("/www/wwwroot/wem_raw_data"):
        BASE_DIR = "/www/wwwroot/wem_raw_data"
    elif os.path.isdir("/app/data/wem_raw_data"):
        BASE_DIR = "/app/data/wem_raw_data"
    else:
        print("错误: 找不到 WEM 数据目录，请用 --base-dir 指定", file=sys.stderr)
        sys.exit(1)

    # 进度文件需写入可写目录（BASE_DIR 可能是只读挂载）
    if args.progress_file:
        PROGRESS_FILE = args.progress_file
    else:
        for cand_dir in ("/app/data", "/www/wwwroot/aus-ele/data", "/tmp"):
            if os.path.isdir(cand_dir) and os.access(cand_dir, os.W_OK):
                PROGRESS_FILE = os.path.join(cand_dir, ".wem_import_progress.json")
                break
        else:
            PROGRESS_FILE = os.path.join(os.getcwd(), ".wem_import_progress.json")

    # 安装 psycopg2（如果需要）
    try:
        import psycopg2
    except ImportError:
        log.info("安装 psycopg2-binary...")
        os.system(f"{sys.executable} -m pip install psycopg2-binary -q")
        import psycopg2

    dsn = PG_DSN.format(password=args.pg_password, host=args.pg_host, port=args.pg_port)
    log.info("=" * 60)
    log.info("WEM 数据批量导入 → PostgreSQL")
    log.info("数据目录: %s", BASE_DIR)
    log.info("PG DSN:   %s", dsn.split("@")[0].replace(args.pg_password, "***") + "@...")
    log.info("模式:     %s", "DRY RUN" if args.dry_run else "正式导入")
    log.info("=" * 60)

    try:
        pg_conn = psycopg2.connect(dsn)
        pg_conn.autocommit = False
    except Exception as e:
        log.error("无法连接 PostgreSQL: %s", e)
        sys.exit(1)

    progress = load_progress()
    try:
        init_pg(pg_conn)

        if not args.skip_fcess:
            import_fcess_capabilities(pg_conn, args.dry_run)

        if not args.skip_trading:
            import_trading_prices(pg_conn, progress, args.dry_run)

        if not args.skip_dispatch:
            import_dispatch_solutions(pg_conn, progress, args.dry_run)

    finally:
        pg_conn.close()

    # 最终统计
    log.info("=" * 60)
    log.info("导入完成！")
    pg2 = psycopg2.connect(dsn)
    cur = pg2.cursor()
    for table in ("wem_ess_capabilities", "wem_ess_market_price", "wem_ess_constraint_summary"):
        try:
            cur.execute(f"SELECT count(*) FROM {table}")
            log.info("  %s: %d rows", table, cur.fetchone()[0])
        except Exception:
            pass
    cur.execute("SELECT tablename FROM pg_tables WHERE tablename LIKE 'trading_price_%'")
    for (tname,) in cur.fetchall():
        cur.execute(f"SELECT count(*) FROM {tname}")
        log.info("  %s: %d rows", tname, cur.fetchone()[0])
    pg2.close()
    log.info("=" * 60)


if __name__ == "__main__":
    main()
