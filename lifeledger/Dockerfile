# ============================================================================
# LifeLedger Home Assistant Add-on — Dockerfile
# ============================================================================
# Build context: lifeledger/  (HA uses the add-on directory, not the repo root)
#
# Files in lifeledger/ that are available to COPY:
#   config.json   run.sh   Dockerfile   (this file)
#
# Everything else (backend/, config/, requirements.txt) lives at the repo
# root, which is NOT the build context.  We clone the repo inside the image
# so the full app is available without duplicating files.
#
# REQUIREMENT: the GitHub repository must be public so the clone succeeds.
# ============================================================================

FROM python:3.12-slim

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner

# ── System packages ───────────────────────────────────────────────────────────
# git    — to clone the app at build time
# gcc/g++ / libffi — needed by some Python wheels (cryptography, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        git \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# ── Clone app source ──────────────────────────────────────────────────────────
# --depth=1 keeps the image small (no history, just latest commit).
# The REPO_URL build arg can be overridden for forks or local testing.
RUN git clone --depth=1 "${REPO_URL}" /app

# ── Install Python dependencies ───────────────────────────────────────────────
WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# ── Tidy up ───────────────────────────────────────────────────────────────────
# Remove git now that the clone is done — saves ~30 MB in the final image.
RUN apt-get purge -y git \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# ── Create directories ────────────────────────────────────────────────────────
# Persistent user data lives in /config (HA bind-mounts it from the host).
# /app/data holds bundled templates that are copied to /config on first run.
RUN mkdir -p /app/data/scenarios/templates \
             /app/data/checkpoints \
             /app/data/exports

# ── Add-on entrypoint ─────────────────────────────────────────────────────────
# run.sh is in the lifeledger/ directory = the build context root, so this COPY works.
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
