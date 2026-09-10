# =============================================================================
# LifeLedger Home Assistant Add-on — Dockerfile
# =============================================================================
# Multi-stage build:
#   Stage 1 (node:22-slim)     — download source, npm install, vite build
#   Stage 2 (python:3.12-slim) — download source, pip install, copy dist
#
# Source download strategy: curl -k (not git clone)
# -------------------------------------------------------
# git clone uses libcurl under the hood. In HA's Docker build environment,
# libcurl has no CA bundle (CAfile: none) and the SSL handshake to GitHub
# fails. Solution: download the repo as a tarball with curl -k (-k skips
# SSL certificate verification). No git, no CA bundle needed.
#
# Docker layer cache busting
# -------------------------------------------------------
# Docker caches each RUN layer by the command string. The curl tarball URL
# never changes, so Docker always reuses the cached download layer even when
# the repo content has changed. To force a fresh download on every release,
# BUILD_VERSION is embedded in the RUN echo command — when BUILD_VERSION changes,
# Docker sees a different command string and re-runs curl, fetching new source.
#
# IMPORTANT: the ARG name here MUST be BUILD_VERSION, not anything else.
# HA Supervisor invokes `docker buildx build --build-arg BUILD_VERSION=<version>
# --build-arg BUILD_ARCH=<arch> ...` unconditionally — those are the exact
# names it passes, and Docker silently ignores any --build-arg whose name
# doesn't match a declared ARG in this file. A previous version of this
# Dockerfile declared `ARG APP_VERSION` instead: Supervisor's BUILD_VERSION
# was silently dropped, the RUN echo command string never changed between
# builds, and every "version bump" install/update/rebuild from
# 1.4.3 onward was actually still running the exact code that was live when
# this Dockerfile was first written — Supervisor's reported installed
# version was correct, but the container's actual code was frozen. Verified
# via the running container's own logs still throwing the pre-fix
# `%,.0f` logging bug that had already been fixed several versions earlier
# in source. If you ever rename this ARG again, confirm the running
# container's code actually changed (e.g. check a log line only the new
# code emits) — don't trust the Supervisor-reported version number alone.
# =============================================================================

# ── Stage 1: build the React frontend ────────────────────────────────────────
FROM node:22-slim AS frontend-build

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner/archive/refs/heads/main.tar.gz
# Bump BUILD_VERSION with every release to bust the Docker download cache
ARG BUILD_VERSION=1.4.3

# curl    — download repo tarball
# python3 / make / g++ — node-gyp native build tools (some npm packages need these)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl python3 make g++ \
    && rm -rf /var/lib/apt/lists/*

# BUILD_VERSION in the echo busts the cache — Docker re-downloads on version bump
RUN echo "Downloading LifeLedger ${BUILD_VERSION}" \
    && mkdir -p /src \
    && curl -fsSLk "${REPO_URL}" | tar -xz --strip-components=1 -C /src

WORKDIR /src/frontend

# Increase timeouts for containerised npm registry access
RUN npm config set fetch-retries 5 \
    && npm config set fetch-retry-mintimeout 20000 \
    && npm config set fetch-retry-maxtimeout 120000

# --legacy-peer-deps: recharts declares React 16-18 as peers; React 19 works
# at runtime but npm strict mode refuses without this flag.
RUN npm install --legacy-peer-deps

# package.json scripts.build = "tsc -b && vite build"
# vite.config.ts sets base: './' — produces relative asset paths for Ingress
RUN npm run build


# ── Stage 2: Python runtime ───────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ARG REPO_URL=https://github.com/sjeapes/FinancePlanner/archive/refs/heads/main.tar.gz
ARG BUILD_VERSION=1.4.3

# curl    — download repo tarball
# gcc/g++ / libffi-dev — some Python wheels need native compilation
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl gcc g++ libffi-dev \
    && rm -rf /var/lib/apt/lists/*

RUN echo "Downloading LifeLedger ${BUILD_VERSION}" \
    && mkdir -p /app \
    && curl -fsSLk "${REPO_URL}" | tar -xz --strip-components=1 -C /app

WORKDIR /app
RUN pip install --no-cache-dir -r requirements.txt

# Strip build tools to keep the final image lean
RUN apt-get purge -y curl gcc g++ libffi-dev \
    && apt-get autoremove -y \
    && rm -rf /var/lib/apt/lists/*

# Copy the built React dist from Stage 1
COPY --from=frontend-build /src/frontend/dist /app/frontend/dist

RUN mkdir -p /app/data/scenarios/templates \
             /app/data/checkpoints \
             /app/data/exports

# The entrypoint lives at lifeledger/run.sh in the repo and is COPYed in
# rather than duplicated here — a previous version embedded its own copy
# via a heredoc, which silently drifted out of sync (fixes made to run.sh
# never actually shipped, since Supervisor's Docker build never read that
# file at all). Single source of truth now.
COPY run.sh /run.sh
RUN chmod +x /run.sh

CMD ["/run.sh"]
