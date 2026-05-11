# syntax=docker/dockerfile:1.7

# ──────────────────────────────────────────────────────────────────
# Stage 1: Build Next.js dashboard → .next/standalone
# ──────────────────────────────────────────────────────────────────
FROM node:20-alpine AS dashboard-build

RUN corepack enable && corepack prepare pnpm@10.8.1 --activate
# Extract the semver line robustly; pnpm/corepack may emit warnings/banners
# before OR after the version on stdout. grep -E with the exact pattern
# isolates a single matching line.
RUN VER=$(pnpm --version 2>/dev/null | grep -E '^[0-9]+\.[0-9]+\.[0-9]+$' | head -1) \
    && test "$VER" = "10.8.1" \
    || (echo "ERROR: pnpm version mismatch — expected 10.8.1, got '$VER' (full output below)" >&2 && pnpm --version 2>&1 && exit 1)

WORKDIR /build

# Workspace metadata (cached layer — busts only on dep change)
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY dashboard/package.json ./dashboard/
COPY cli/package.json ./cli/

RUN pnpm install --frozen-lockfile --filter "dashboard..."

# Dashboard source (changes frequently — after install layer)
COPY dashboard/ ./dashboard/
# Season JSON data imported statically by the dashboard at build time
COPY resources/ ./resources/

RUN pnpm --filter dashboard build

# ──────────────────────────────────────────────────────────────────
# Stage 2: Install Python deps + project via uv
# ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm AS python-build

COPY --from=ghcr.io/astral-sh/uv:0.5.13 /uv /usr/local/bin/uv

WORKDIR /app

# Third-party deps only (cached layer)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Project source + install package itself
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# ──────────────────────────────────────────────────────────────────
# Stage 3: Runtime — Python 3.13 + Node 20 + tini + jq
# ──────────────────────────────────────────────────────────────────
FROM python:3.13-slim-bookworm AS runner

# Node 20 from NodeSource (Debian bookworm default is Node 18; Next 16 wants 20+)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates curl gnupg tini jq \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y --no-install-recommends nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python app (venv + src)
WORKDIR /app
COPY --from=python-build /app /app
COPY strategies.yaml ./

# Dashboard (Next.js standalone output)
# outputFileTracingRoot makes Next.js trace from the monorepo root, so the
# standalone layout mirrors the monorepo:
#   /build/dashboard/.next/standalone/dashboard/server.js  (app package)
#   /build/dashboard/.next/standalone/node_modules/        (shared pnpm store)
#
# At runtime we mirror this: /dashboard/server.js + /node_modules/ (parent).
# run.sh does: cd /dashboard && node server.js
WORKDIR /
COPY --from=dashboard-build /build/dashboard/.next/standalone/dashboard/ /dashboard/
COPY --from=dashboard-build /build/dashboard/.next/standalone/node_modules/ /node_modules/
# Static assets served by Next.js must be in the dashboard's .next/static dir
COPY --from=dashboard-build /build/dashboard/.next/static /dashboard/.next/static
COPY --from=dashboard-build /build/dashboard/public /dashboard/public

# Fail-fast if the standalone layout assumption is wrong (zero-row COPYs are silent)
RUN test -f /dashboard/server.js \
    && test -d /dashboard/.next/static \
    && test -d /dashboard/public \
    || (echo "ERROR: Next.js standalone copy layout mismatch — check '.next/standalone/...' paths" >&2 && ls -la /dashboard && exit 1)

# Entrypoint
COPY run.sh /run.sh
RUN chmod +x /run.sh

EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["/run.sh"]
