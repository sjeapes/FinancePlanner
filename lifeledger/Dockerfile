# =============================================================================
# LifeLedger Home Assistant Add-on — Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (node:22-slim)    — npm install + vite build
#   Stage 2 (python:3.12-slim) — pip install + frontend dist copied in
#
# SSL fix: slim Debian images ship without a CA bundle.
#   1. Install ca-certificates
#   2. Run update-ca-certificates (regenerates /etc/ssl/certs/ca-certificates.crt)
#   3. Set GIT_SSL_CAINFO so git/libcurl finds the bundle regardless of how
#      libcurl was compiled (it may have no compiled-in default path).
# =============================================================================

# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:22-slim AS frontend-build

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates git python3 make g++ \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Tell git/libcurl exactly where the CA bundle is.
# Required when libcurl has no compiled-in default (common in slim images).
ENV GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt

RUN git clone --depth=1 "${REPO_URL}" /src

WORKDIR /src/frontend

RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000

# --legacy-peer-deps: recharts declares React 16-18 as peers; React 19 works
# at runtime but npm strict mode refuses without this flag.
RUN npm install --legacy-peer-deps

# package.json build script: tsc -b && vite build
RUN npm run build


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates git gcc g++ libffi-dev \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Same SSL fix for the Python stage git clone
ENV GIT_SSL_CAINFO=/etc/ssl/certs/ca-certificates.crt

RUN git clone --depth=1 "${REPO_URL}" /app

WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

RUN apt-get purge -y git gcc g++ libffi-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy built React dist from Stage 1
COPY --from=frontend-build /src/frontend/dist /app/frontend/dist

RUN mkdir -p /app/data/scenarios/templates \
             /app/data/checkpoints \
             /app/data/exports

# Startup script inline — no COPY from build context
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
  version: "1.0.5"
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
