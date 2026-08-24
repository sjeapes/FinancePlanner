# ============================================================================
# LifeLedger Home Assistant Add-on
# ============================================================================
# Uses python:3.12-slim directly so the add-on builds without needing
# arch-specific HA base images. Works on amd64, aarch64 (Pi 4/5), armv7.
# ============================================================================

FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        gcc \
        g++ \
        libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY backend/  ./backend/
COPY config/   ./config/

# Create required directories (scenario data lives in /config, mounted by HA)
RUN mkdir -p /app/data/scenarios/templates \
             /app/data/checkpoints \
             /app/data/exports \
             /app/logs

# Copy add-on entrypoint
COPY lifeledger/run.sh /run.sh
RUN chmod +x /run.sh

# HA passes the entrypoint via CMD
CMD ["/run.sh"]
