# aus-ele

Energy market analysis workspace for:

- Australian NEM/WEM market data
- Event overlays and forecast views
- BESS arbitrage / FCAS / investment analysis
- Fingrid reserve price data

## Repository Layout

- `backend/` FastAPI application, analysis engines, schedulers, and data APIs
- `scrapers/` AEMO and Fingrid ingestion scripts
- `data/` local SQLite databases and sync logs
- `tests/` Python regression tests
- `web/` React + Vite frontend
- `docs/` plans, specs, and project notes

## Backend

Install Python dependencies:

```bash
pip install -r requirements.txt
```

Run the API from the repo root:

```bash
cd backend
python -m uvicorn server:app --host 127.0.0.1 --port 8085
```

Key environment variables:

```bash
set AUS_ELE_DB_PATH=G:\\project\\aus-ele\\data\\aemo_data.db
set AUS_ELE_ENABLE_SCHEDULER=true
set AUS_ELE_CORS_ALLOW_ORIGINS=http://127.0.0.1:5173,http://localhost:5173
set AUS_ELE_CORS_ALLOW_CREDENTIALS=false
set REDIS_URL=redis://127.0.0.1:6379/0
set AUS_ELE_OTEL_ENABLED=false
set AUS_ELE_OTEL_METRICS_ENABLED=false
set AUS_ELE_JSON_LOGS=false
```

Notes:

- CORS now defaults to local Vite origins only.
- `.env` is ignored by git. Keep real secrets there, not in tracked docs.
- Scheduler can be disabled with `AUS_ELE_ENABLE_SCHEDULER=false`.
- Core analysis responses now expose a `metadata` object for freshness, source version, timezone, interval, and data quality grade.
- `/api/observability/status` now includes telemetry metrics/logs health plus centralized collection readiness.

Optional observability settings:

```bash
set AUS_ELE_OTEL_ENABLED=true
set AUS_ELE_OTEL_EXPORTER=otlp
set AUS_ELE_OTEL_EXPORTER_OTLP_ENDPOINT=https://otel-collector.example/v1/traces
set AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://otel-collector.example/v1/traces
set AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://otel-collector.example/v1/metrics
set AUS_ELE_OTEL_METRICS_ENABLED=true
set AUS_ELE_JSON_LOGS=true
set AUS_ELE_LOG_AGGREGATION_ENABLED=true
set AUS_ELE_LOG_AGGREGATION_SINK=file
set AUS_ELE_LOG_AGGREGATION_FILE_PATH=G:\\project\\aus-ele\\output\\observability.jsonl
set AUS_ELE_OPENLINEAGE_ENABLED=true
set AUS_ELE_OPENLINEAGE_SINK=file
set AUS_ELE_OPENLINEAGE_FILE_PATH=G:\\project\\aus-ele\\output\\openlineage-events.jsonl
```

Observability notes:

- `AUS_ELE_OTEL_EXPORTER=console` is best for local debugging only.
- `AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT` and `AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT` can override the generic OTLP endpoint per signal.
- `AUS_ELE_JSON_LOGS=true` emits JSON logs with `trace_id` and `span_id`.
- `AUS_ELE_LOG_AGGREGATION_ENABLED=true` with `AUS_ELE_LOG_AGGREGATION_SINK=file` writes structured logs to a JSONL sink file.
- `AUS_ELE_LOG_AGGREGATION_ENABLED=true` with `AUS_ELE_LOG_AGGREGATION_SINK=http` posts structured JSON logs to `AUS_ELE_LOG_AGGREGATION_ENDPOINT`.
- `telemetry.collection.mode` in `/api/observability/status` reports `local_only`, `partial`, or `centralized_ready`.

Key API additions:

- `GET /api/price-trend` now returns `metadata` alongside chart/stat payloads.
- `GET /api/peak-analysis` now returns unified `metadata` for unit, timezone, interval, freshness, and methodology version.
- `GET /api/hourly-price-profile` now returns unified `metadata` for heatmap/profile responses, including source version and interval.
- `GET /api/fcas-analysis` now returns unified `metadata`, including preview signaling for WEM slim-chain results.
- `POST /api/investment-analysis` now returns unified `metadata` and backtest traceability fields such as `backtest_reference` and `backtest_fallback_used`.
- `GET /api/fingrid/datasets/{dataset_id}/status` now returns `metadata` describing the dataset status snapshot.
- `POST /api/data-quality/refresh` recomputes market data quality snapshots from the current SQLite data sources.
- `GET /api/data-quality/summary` returns the latest cross-market quality summary.
- `GET /api/data-quality/markets` returns per-market quality snapshots.
- `GET /api/data-quality/issues` returns normalized issue rows, optionally filtered by market.

## API Contract

Primary analysis routes now follow a shared response-contract rule: each response includes a top-level `metadata` object with:

- `market`
- `region_or_zone`
- `timezone`
- `currency`
- `unit`
- `interval_minutes`
- `data_grade`
- `data_quality_score`
- `coverage`
- `freshness`
- `source_name`
- `source_version`
- `methodology_version`
- `warnings`

Route-specific metadata fields may still exist alongside the standard fields. For example:

- `GET /api/event-overlays` keeps `coverage_quality`, `sources_used`, and `time_granularity`
- `GET /api/grid-forecast` keeps `forecast_mode`, `coverage_quality`, `issued_at`, and `confidence_band`
- `POST /api/investment-analysis` adds top-level traceability fields such as `backtest_reference` and `backtest_fallback_used`

Detailed contract notes live in [docs/API响应契约说明.md](docs/API响应契约说明.md).

The same routes now expose basic `summary` / `description` text and standard 404/500 response notes in the FastAPI OpenAPI document.

## Frontend

```bash
cd web
npm install
npm run dev
```

Default frontend URL:

```text
http://127.0.0.1:5173
```

Optional API override:

```bash
set VITE_API_BASE=http://127.0.0.1:8085/api
```

## Fingrid

Copy `.env.example` to `.env` or set variables manually before using Fingrid sync or API routes:

```bash
set FINGRID_API_KEY=your-key-here
set FINGRID_BASE_URL=https://data.fingrid.fi/api
set FINGRID_REQUEST_INTERVAL_SECONDS=6.5
set FINGRID_TIMEOUT_SECONDS=30
set FINGRID_DEFAULT_BACKFILL_START=2014-01-01T00:00:00Z
set FINGRID_DEFAULT_INCREMENTAL_LOOKBACK_DAYS=30
set NORDPOOL_API_BASE_URL=https://data-api.nordpoolgroup.com
set NORDPOOL_ACCESS_TOKEN=your-nord-pool-access-token
set NORDPOOL_API_KEY=your-nord-pool-key
set NORDPOOL_TOKEN_URL=https://identity.nordpoolgroup.com/connect/token
set NORDPOOL_CLIENT_ID=your-client-id
set NORDPOOL_CLIENT_SECRET=your-client-secret
set ENTSOE_API_BASE_URL=https://web-api.tp.entsoe.eu/api
set ENTSOE_SECURITY_TOKEN=your-entsoe-token
set ENTSOE_TIMEOUT_SECONDS=30
```

`NORDPOOL_ACCESS_TOKEN` / `NORDPOOL_API_KEY` or a `NORDPOOL_TOKEN_URL + NORDPOOL_CLIENT_ID + NORDPOOL_CLIENT_SECRET` client-credentials flow can enable Nord Pool live access. `ENTSOE_SECURITY_TOKEN` enables ENTSO-E live access. When these are present, `/api/finland/market-model` will upgrade those external sources from `planned` to `configured`, and when fetch succeeds they move further to `live`.

Backfill dataset `317`:

```bash
python scrapers/fingrid_sync.py --dataset 317 --mode backfill
```

Incremental refresh:

```bash
python scrapers/fingrid_sync.py --dataset 317 --mode incremental
```

Fingrid frontend route:

```text
http://127.0.0.1:5173/fingrid
```

Current delivery boundary:

- WEM-related FCAS and forecast outputs still include preview-style interpretations rather than full investment-grade market reconstruction.
- Fingrid status metadata may report `analytical-preview` when the dataset is usable for analysis but not backed by a complete production-style data quality pipeline yet.
- `metadata.methodology_version` and `metadata.source_version` are the current internal response-contract version markers for downstream consumers.

## Verification

Backend tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Frontend checks:

```bash
cd web
node --test src/lib/*.test.js
npm run lint
npm run build
```
