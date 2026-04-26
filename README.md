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
```

Notes:

- CORS now defaults to local Vite origins only.
- `.env` is ignored by git. Keep real secrets there, not in tracked docs.
- Scheduler can be disabled with `AUS_ELE_ENABLE_SCHEDULER=false`.

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
```

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

## Verification

Backend tests:

```bash
python -m unittest discover -s tests -p "test_*.py"
```

Frontend checks:

```bash
cd web
npm run lint
npm run build
```
