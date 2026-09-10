#!/usr/bin/env bash
# ============================================================================
# LifeLedger Home Assistant Add-on — Entrypoint
# ============================================================================
# HA Supervisor writes add-on options to /data/options.json.
# This script reads them with Python (no bashio dependency needed),
# writes a runtime lifeledger_config.yaml, seeds the persistent data
# directory on first run only, and starts uvicorn.
#
# IMPORTANT — this is the ONLY copy of this script. The Dockerfile COPYs it
# in rather than embedding a duplicate heredoc. A previous version of the
# Dockerfile had its own separately-maintained copy that silently drifted
# out of sync with this file (missing fixes made here never actually
# shipped) — never reintroduce that duplication.
# ============================================================================

set -euo pipefail

APP_DIR="/app"
CONFIG_DIR="/config"       # HA bind-mounts /config here (map: config:rw) —
                            # this is the ONLY thing that survives a version
                            # update (a plain container restart also keeps
                            # the container's own filesystem, but any update
                            # or reinstall rebuilds the image and discards
                            # everything NOT under this mount).
DATA_DIR="/data"           # HA internal add-on data directory (options.json only)
OPTIONS_FILE="${DATA_DIR}/options.json"

CONFIG_FILE="${CONFIG_DIR}/config/lifeledger_config.yaml"
LOG_FILE="${CONFIG_DIR}/logs/lifeledger.log"
DB_FILE="${CONFIG_DIR}/data/lifeledger.db"

echo "[LifeLedger] Add-on starting..."

# ── Read options from /data/options.json ──────────────────────────────────────
read_option() {
    local key="$1"
    local default="$2"
    python3 -c "
import json, sys
try:
    with open('${OPTIONS_FILE}') as f:
        d = json.load(f)
    print(d.get('${key}', '${default}'))
except Exception:
    print('${default}')
"
}

LOG_LEVEL=$(read_option log_level INFO)
BASE_CURRENCY=$(read_option base_currency GBP)
PROJ_START=$(read_option projection_start_year 2025)
PROJ_END=$(read_option projection_end_year 2075)
INFLATION=$(read_option inflation_base_rate 0.025)
MC_SIMS=$(read_option monte_carlo_simulations 1000)
MC_SEED=$(read_option monte_carlo_seed 42)
DRIVE_ENABLED=$(read_option drive_sync_enabled false)
DRIVE_INTERVAL=$(read_option drive_sync_interval_minutes 5)

# ── Guard against a stale projection_start_year ───────────────────────────────
# The add-on option ships with a fixed default (see config.json) and, once
# HA Supervisor bakes it into options.json at install time, never advances on
# its own — every year that passes without the user manually bumping it in
# the Configuration tab silently shifts every projected year's label behind
# the real calendar, and makes "year 0" of any projection a stale year rather
# than "now". If the configured value has fallen behind the current year,
# override it and say so in the log, rather than quietly projecting from the
# past. An explicitly future-dated value is left alone.
CURRENT_YEAR=$(date +%Y)
if [ "${PROJ_START}" -lt "${CURRENT_YEAR}" ]; then
    echo "[LifeLedger] WARNING: projection_start_year option (${PROJ_START}) is behind the current year (${CURRENT_YEAR}) — using ${CURRENT_YEAR} instead. Update the option in the add-on's Configuration tab to silence this."
    PROJ_START="${CURRENT_YEAR}"
fi

echo "[LifeLedger] log_level=${LOG_LEVEL}  currency=${BASE_CURRENCY}  MC_sims=${MC_SIMS}"

# ── Create the persistent data layout under /config ───────────────────────────
# This mirrors EXACTLY the project_root-relative paths every backend API
# route module already expects (data/scenarios, data/checkpoints, etc.) —
# see backend/main.py's LIFELEDGER_DATA_ROOT handling. Do not rename these
# without also checking every route module that resolves scenario_path,
# backup paths, etc. relative to app.state.project_root.
mkdir -p \
    "${CONFIG_DIR}/config" \
    "${CONFIG_DIR}/logs" \
    "${CONFIG_DIR}/data/scenarios/templates" \
    "${CONFIG_DIR}/data/checkpoints" \
    "${CONFIG_DIR}/data/comments" \
    "${CONFIG_DIR}/data/reports_output" \
    "${CONFIG_DIR}/data/backups"

# ── Seed the persistent scenario data on FIRST RUN ONLY ───────────────────────
# Never overwrite an existing base.yaml — that would silently discard real
# user data on every restart/update, which is exactly the bug this whole
# rewrite exists to fix. Only copy the image's shipped default if the
# persistent copy doesn't exist yet (i.e. this is truly a fresh install).
SCENARIOS_SRC="${APP_DIR}/data/scenarios"
SCENARIOS_DST="${CONFIG_DIR}/data/scenarios"
if [ ! -f "${SCENARIOS_DST}/base.yaml" ] && [ -f "${SCENARIOS_SRC}/base.yaml" ]; then
    cp "${SCENARIOS_SRC}/base.yaml" "${SCENARIOS_DST}/base.yaml"
    echo "[LifeLedger] First run: seeded ${SCENARIOS_DST}/base.yaml from the shipped default."
fi
if [ -d "${SCENARIOS_SRC}/templates" ]; then
    for f in "${SCENARIOS_SRC}/templates"/*.yaml; do
        [ -f "${f}" ] || continue
        dst="${SCENARIOS_DST}/templates/$(basename "${f}")"
        if [ ! -f "${dst}" ]; then
            cp "${f}" "${dst}"
            echo "[LifeLedger] Installed template: $(basename "${f}")"
        fi
    done
fi

# ── Write runtime lifeledger_config.yaml ──────────────────────────────────────
cat > "${CONFIG_FILE}" << YAML_EOF
# LifeLedger runtime config — generated by HA add-on
# Edit options via the Home Assistant Add-on Configuration tab.
# This file is regenerated on each add-on restart.

app:
  name: "LifeLedger"
  base_currency: "${BASE_CURRENCY}"
  log_level: "${LOG_LEVEL}"
  log_file: "${LOG_FILE}"
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
  enabled: ${DRIVE_ENABLED}
  sync_on_save: true
  auto_sync_interval_minutes: ${DRIVE_INTERVAL}
  folder_name: "LifeLedger"
  conflict_resolution: "prompt"

engine:
  income_auto_adds_to_networth: false
  checkpoint_boundary: true

backup:
  include_paths:
    - "config"
    - "data/scenarios"
    - "data/checkpoints"
    - "data/comments"
    - "data/reports_output"
  include_database: true
  include_api_keys_in_export: false
  max_backups_retained: 10
  backup_dir: "data/backups"
  enforce_version_match: false
YAML_EOF

echo "[LifeLedger] Config written to ${CONFIG_FILE}"

# ── Environment ───────────────────────────────────────────────────────────────
# LIFELEDGER_DATA_ROOT is the one that matters: backend/main.py uses it as
# app.state.project_root, which every API route module already resolves
# scenario/checkpoint/comment/backup/db paths relative to — this single
# variable redirects ALL of that to the persistent volume with no changes
# needed anywhere else. LIFELEDGER_CONFIG/DB/LOG are kept for direct
# reference/debugging but the app itself only reads LIFELEDGER_DATA_ROOT.
export LIFELEDGER_DATA_ROOT="${CONFIG_DIR}"
export LIFELEDGER_CONFIG="${CONFIG_FILE}"
export LIFELEDGER_DB="${DB_FILE}"
export LIFELEDGER_LOG="${LOG_FILE}"
export PYTHONPATH="${APP_DIR}:${PYTHONPATH:-}"

# ── Start uvicorn ─────────────────────────────────────────────────────────────
echo "[LifeLedger] Starting on port 8000..."
exec python3 -m uvicorn backend.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --log-level "$(echo "${LOG_LEVEL}" | tr '[:upper:]' '[:lower:]')" \
    --workers 1 \
    --no-access-log
