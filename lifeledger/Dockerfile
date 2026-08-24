# =============================================================================
# LifeLedger Home Assistant Add-on — Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1: node:22-slim  → npm install --legacy-peer-deps + vite build
#   Stage 2: python:3.12-slim → pip install + copy built frontend dist
#
# Why node:22-slim (not alpine):
#   Some npm packages need python3 / make / g++ for native compilation.
#   Debian slim provides these via apt without extra config.
#
# Why --legacy-peer-deps:
#   recharts declares React 16-18 as peer deps; React 19 satisfies it at
#   runtime but npm strict mode refuses to install. --legacy-peer-deps skips
#   that check and installs successfully.
#
# Build context: lifeledger/  — no COPY from build context used here.
# All source comes from the git clone inside the image.
# REQUIREMENT: the GitHub repo must be public.
# =============================================================================

# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:22-slim AS frontend-build

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner

# python3 / make / g++ needed for npm packages with native bindings
RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 "${REPO_URL}" /src

WORKDIR /src/frontend

# Tune npm for reliability in containerised builds
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000

# --legacy-peer-deps: skip strict peer-dep enforcement (recharts + React 19)
RUN npm install --legacy-peer-deps

# tsc -b && vite build (as defined in package.json scripts.build)
RUN npm run build
# Produces: /src/frontend/dist/


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner

RUN apt-get update \
    && apt-get install -y --no-install-recommends git gcc g++ libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN git clone --depth=1 "${REPO_URL}" /app

WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get purge -y git gcc g++ libffi-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy the built React dist from Stage 1
# backend/main.py._serve_frontend() mounts this at runtime
COPY --from=frontend-build /src/frontend/dist /app/frontend/dist

RUN mkdir -p /app/data/scenarios/templates \
             /app/data/checkpoints \
             /app/data/exports

# Write startup script inline — no COPY from lifeledger/ build context needed
RUN cat > /run.sh << 'RUNSCRIPT'
#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/app
CONFIG_DIR=/config
DATA_DIR=/data
OPTIONS=${DATA_DIR}/options.json

echo "[LifeLedger] Starting add-on..."

opt() {
  python3 -c "
import json
try:
    d = json.load(open('${OPTIONS}'))
    print(d.get('$1', '$2'))
except Exception:
    print('$2')
" 2>/dev/null || echo "$2"
}

LOG_LEVEL=$(opt log_level INFO)
CURRENCY=$(opt base_currency GBP)
PROJ_START=$(opt projection_start_year 2025)
PROJ_END=$(opt projection_end_year 2075)
INFLATION=$(opt inflation_base_rate 0.025)
MC_SIMS=$(opt monte_carlo_simulations 1000)
MC_SEED=$(opt monte_carlo_seed 42)
DRIVE=$(opt drive_sync_enabled false)
DRIVE_IV=$(opt drive_sync_interval_minutes 5)

echo "[LifeLedger] currency=${CURRENCY} log=${LOG_LEVEL} mc_sims=${MC_SIMS}"

mkdir -p \
  "${CONFIG_DIR}/scenarios/templates" \
  "${CONFIG_DIR}/checkpoints" \
  "${CONFIG_DIR}/exports"

if [ -d "${APP_DIR}/data/scenarios/templates" ]; then
  for f in "${APP_DIR}/data/scenarios/templates"/*.yaml; do
    [ -f "$f" ] || continue
    dst="${CONFIG_DIR}/scenarios/templates/$(basename "$f")"
    [ -f "$dst" ] || cp "$f" "$dst"
  done
fi

cat > "${CONFIG_DIR}/lifeledger_config.yaml" << YAML
app:
  name: "LifeLedger"
  version: "1.0.3"
  base_currency: "${CURRENCY}"
  log_level: "${LOG_LEVEL}"
  log_file: "${CONFIG_DIR}/lifeledger.log"
  log_to_console: true
  log_to_file: true
projection:
  start_year: ${PROJ_START}
  end_year: ${PROJ_END}
  time_step: annual
inflation:
  base_rate: ${INFLATION}
  low_rate: 0.015
  high_rate: 0.040
  periods: []
fx:
  rates:
    GBP_USD: 1.27
    GBP_EUR: 1.17
  annual_drift:
    GBP_USD: 0.0
    GBP_EUR: 0.0
monte_carlo:
  enabled: true
  simulations: ${MC_SIMS}
  seed: ${MC_SEED}
  growth_std_dev: 0.12
  inflation_std_dev: 0.005
  sequence_of_returns_risk: true
  crash_window_years: 5
drive:
  enabled: ${DRIVE}
  sync_on_save: true
  auto_sync_interval_minutes: ${DRIVE_IV}
  folder_name: "LifeLedger"
  conflict_resolution: "prompt"
database:
  path: "${CONFIG_DIR}/lifeledger.db"
  cache_market_prices: true
  price_staleness_hours: 24
engine:
  income_auto_adds_to_networth: false
  checkpoint_boundary: true
paths:
  scenarios: "${CONFIG_DIR}/scenarios"
  checkpoints: "${CONFIG_DIR}/checkpoints"
  exports: "${CONFIG_DIR}/exports"
YAML

export LIFELEDGER_CONFIG="${CONFIG_DIR}/lifeledger_config.yaml"
export LIFELEDGER_DB="${CONFIG_DIR}/lifeledger.db"
export LIFELEDGER_LOG="${CONFIG_DIR}/lifeledger.log"
export PYTHONPATH="${APP_DIR}:${PYTHONPATH:-}"

echo "[LifeLedger] Launching uvicorn on :8000"
exec python3 -m uvicorn backend.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --log-level "$(echo "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')" \
  --workers 1 \
  --no-access-log
RUNSCRIPT

RUN chmod +x /run.sh

CMD ["/run.sh"]
