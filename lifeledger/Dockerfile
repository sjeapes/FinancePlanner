# ============================================================================
# LifeLedger Home Assistant Add-on
# ============================================================================
# Build context: lifeledger/  (HA uses the add-on subdirectory, not repo root)
#
# This Dockerfile has ZERO COPY instructions.
# The app code is obtained by git-cloning the repo during the build.
# The startup script is written inline with a shell heredoc.
# This makes the build immune to build-context path confusion.
#
# REQUIREMENT: the GitHub repository must be public.
# ============================================================================

FROM python:3.12-slim

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner

# System packages — git to clone, gcc/libffi for Python wheels
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Clone the app (shallow — no history, just latest commit)
RUN git clone --depth=1 "${REPO_URL}" /app

# Install Python dependencies from the cloned repo
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# Remove git to shrink the image
RUN apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Pre-create directories (user data mounts to /config, which HA bind-mounts)
RUN mkdir -p /app/data/scenarios/templates \
             /app/data/checkpoints \
             /app/data/exports

# Write startup script inline — no COPY, no external file dependency
RUN cat > /run.sh << 'RUNSCRIPT'
#!/usr/bin/env bash
# LifeLedger HA add-on entrypoint
set -euo pipefail

APP_DIR=/app
CONFIG_DIR=/config
DATA_DIR=/data
OPTIONS=${DATA_DIR}/options.json

echo "[LifeLedger] Starting add-on..."

# Read one option from /data/options.json (written by HA Supervisor)
opt() {
  python3 -c "
import json, sys
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

# Persistent data directories
mkdir -p \
  "${CONFIG_DIR}/scenarios/templates" \
  "${CONFIG_DIR}/checkpoints" \
  "${CONFIG_DIR}/exports"

# Copy bundled templates once
if [ -d "${APP_DIR}/data/scenarios/templates" ]; then
  for f in "${APP_DIR}/data/scenarios/templates"/*.yaml; do
    [ -f "$f" ] || continue
    dst="${CONFIG_DIR}/scenarios/templates/$(basename "$f")"
    [ -f "$dst" ] || cp "$f" "$dst"
  done
fi

# Write runtime config
cat > "${CONFIG_DIR}/lifeledger_config.yaml" << YAML
app:
  name: "LifeLedger"
  version: "1.0.0"
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
