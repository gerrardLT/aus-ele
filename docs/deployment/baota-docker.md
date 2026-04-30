# Baota Docker Deployment

This project is prepared to run in Baota Docker alongside other existing projects.

## Design Goals

- No fixed `container_name`
- No fixed host ports
- Compose project name is configurable
- SQLite data stays on the host
- Frontend and backend can run behind a single exposed web port

## Files

- `docker-compose.yml`
- `.env.docker.example`
- `Dockerfile.backend`
- `web/Dockerfile`
- `deploy/nginx/default.conf`

## Local Usage

1. Copy the environment template:

```bash
cp .env.docker.example .env.docker
```

2. Adjust ports if they conflict with anything else on the host:

```bash
WEB_HOST_PORT=18080
API_HOST_PORT=18085
REDIS_HOST_PORT=16379
```

3. Start the stack:

```bash
docker compose --env-file .env.docker up -d --build
```

4. Open the app:

```text
http://127.0.0.1:18080
```

## Baota Deployment

### Option A: Import the compose project in Baota Docker

1. Upload the full project directory to the server.
2. In Baota Docker, create a new Compose project.
3. Use `docker-compose.yml` from this repository.
4. Create an env file from `.env.docker.example`.
5. Change these values before the first start:

```text
COMPOSE_PROJECT_NAME=aus-ele-prod
WEB_HOST_PORT=28080
API_HOST_PORT=28085
REDIS_HOST_PORT=26379
VITE_API_BASE=/api
NPM_REGISTRY=https://registry.npmjs.org/
```

Use different host ports if Baota already has other containers bound on the machine.

If your server is in mainland China and `registry.npmjs.org` is slow or blocked, switch `NPM_REGISTRY` to a reachable mirror such as:

```text
NPM_REGISTRY=https://registry.npmmirror.com/
```

If you want to turn on observability sinks in Baota later, also set:

```text
AUS_ELE_OTEL_ENABLED=true
AUS_ELE_OTEL_EXPORTER=otlp
AUS_ELE_OTEL_EXPORTER_OTLP_ENDPOINT=https://your-otel-collector.example/v1/traces
AUS_ELE_OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=https://your-otel-collector.example/v1/traces
AUS_ELE_OTEL_EXPORTER_OTLP_METRICS_ENDPOINT=https://your-otel-collector.example/v1/metrics
AUS_ELE_OTEL_METRICS_ENABLED=true
AUS_ELE_JSON_LOGS=true
AUS_ELE_LOG_AGGREGATION_ENABLED=true
AUS_ELE_LOG_AGGREGATION_SINK=file
AUS_ELE_LOG_AGGREGATION_FILE_PATH=/app/output/observability.jsonl
AUS_ELE_OPENLINEAGE_ENABLED=true
AUS_ELE_OPENLINEAGE_SINK=file
AUS_ELE_OPENLINEAGE_FILE_PATH=/app/output/openlineage-events.jsonl
```

This enables:

- request / job traces
- request / job metrics
- JSON structured logs with `trace_id / span_id`
- local JSONL structured log sink
- OpenLineage event sink

Use the per-signal OTLP endpoints when your collector expects separate ingestion paths for traces and metrics.

If you already have an external log collector, you can switch the structured log sink to HTTP instead:

```text
AUS_ELE_LOG_AGGREGATION_ENABLED=true
AUS_ELE_LOG_AGGREGATION_SINK=http
AUS_ELE_LOG_AGGREGATION_ENDPOINT=https://your-log-collector.example/ingest
```

6. Make sure the project directory includes writable `data/` and `output/` folders.
7. Start the stack with build enabled.

### Option B: Use Baota reverse proxy on top of the web container

If you already manage domains in Baota:

1. Map only the web container port to the host, for example `28080`.
2. Point the Baota site reverse proxy to:

```text
http://127.0.0.1:28080
```

The web container already proxies `/api/` to the backend container internally, so you do not need a second public reverse proxy for the backend.

## Notes About Existing Containers

- Do not reuse another project's compose project name.
- Do not reuse host ports already claimed by another container.
- Do not point multiple running stacks at the same SQLite database file.
- If you scale the backend beyond one container, disable the built-in scheduler on all but one instance:

```text
AUS_ELE_ENABLE_SCHEDULER=false
```

## Data Persistence

- SQLite database is stored in `./data`
- Redis persistence is stored in the `redis_data` named volume
- Generated outputs are stored in `./output`

Back up `data/` before upgrades or schema migrations.

## Useful Commands

View logs:

```bash
docker compose --env-file .env.docker logs -f
```

Rebuild after code changes:

```bash
docker compose --env-file .env.docker up -d --build
```

Stop the stack:

```bash
docker compose --env-file .env.docker down
```
