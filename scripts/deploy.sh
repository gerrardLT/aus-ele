#!/usr/bin/env bash
# deploy.sh — Pull latest Docker images and restart services
#
# Usage:
#   ./scripts/deploy.sh [environment]
#
# Environments: dev (default), staging, production
#
# Requirements:
#   - Docker and Docker Compose installed
#   - Access to the container registry (ghcr.io)
#   - .env file configured for the target environment

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
ENVIRONMENT="${1:-dev}"

REGISTRY="${REGISTRY:-ghcr.io}"
IMAGE_PREFIX="${IMAGE_PREFIX:-}"
TAG="${DEPLOY_TAG:-latest}"

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

log() {
  echo "[deploy $(date '+%Y-%m-%d %H:%M:%S')] $*"
}

die() {
  log "ERROR: $*" >&2
  exit 1
}

# ─────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────

command -v docker >/dev/null 2>&1 || die "docker is not installed"
command -v docker compose >/dev/null 2>&1 || die "docker compose is not available"

if [[ ! -f "$PROJECT_DIR/.env" && ! -f "$PROJECT_DIR/.env.$ENVIRONMENT" ]]; then
  die "No .env or .env.$ENVIRONMENT file found in $PROJECT_DIR"
fi

# ─────────────────────────────────────────────
# Load environment-specific config
# ─────────────────────────────────────────────

cd "$PROJECT_DIR"

ENV_FILE=".env"
if [[ -f ".env.$ENVIRONMENT" ]]; then
  ENV_FILE=".env.$ENVIRONMENT"
fi

log "Deploying environment: $ENVIRONMENT (env file: $ENV_FILE)"
log "Registry: $REGISTRY, Tag: $TAG"

# ─────────────────────────────────────────────
# Pull latest images
# ─────────────────────────────────────────────

if [[ -n "$IMAGE_PREFIX" ]]; then
  log "Pulling images from registry..."
  docker pull "$REGISTRY/$IMAGE_PREFIX/backend:$TAG" || log "WARN: Could not pull backend image, using local"
  docker pull "$REGISTRY/$IMAGE_PREFIX/web:$TAG" || log "WARN: Could not pull web image, using local"
else
  log "No IMAGE_PREFIX set, building images locally..."
  docker compose --env-file "$ENV_FILE" build
fi

# ─────────────────────────────────────────────
# Stop existing services gracefully
# ─────────────────────────────────────────────

log "Stopping existing services..."
docker compose --env-file "$ENV_FILE" down --timeout 30

# ─────────────────────────────────────────────
# Start services
# ─────────────────────────────────────────────

log "Starting services..."
docker compose --env-file "$ENV_FILE" up -d

# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────

log "Waiting for backend health check..."
HEALTH_URL="http://localhost:${API_HOST_PORT:-18085}/api/health"
RETRIES=10
DELAY=3

for i in $(seq 1 $RETRIES); do
  if curl -sf "$HEALTH_URL" > /dev/null 2>&1; then
    log "Backend is healthy!"
    break
  fi
  if [[ $i -eq $RETRIES ]]; then
    log "WARN: Backend health check failed after $RETRIES attempts"
    log "Check logs with: docker compose logs backend"
    exit 1
  fi
  log "Attempt $i/$RETRIES — waiting ${DELAY}s..."
  sleep "$DELAY"
done

# ─────────────────────────────────────────────
# Summary
# ─────────────────────────────────────────────

log "Deployment complete!"
log "Services:"
docker compose --env-file "$ENV_FILE" ps --format "table {{.Name}}\t{{.Status}}\t{{.Ports}}"
