# HAOS Add-on Dry-Run Deploy — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the existing Kalshi scanner + dashboard as a Home Assistant OS add-on installable from the GitHub repo URL, running in dry-run mode only, reachable at `trading.petra-czech.cc` via the existing Cloudflared add-on.

**Architecture:** Single multi-stage Docker image with two processes (Next.js dashboard on `0.0.0.0:8000`, Python FastAPI+scanner on `127.0.0.1:8001`) supervised by `tini` + `wait -n` in `run.sh`. SQLite + caches live under `/data` (HA-backed-up). HA Supervisor reads typed secrets from `/data/options.json`. SST/AWS path stays runnable via renamed `Dockerfile.api`.

**Tech Stack:** Python 3.13 (uv) + Node 20 (pnpm 10.8.1), FastAPI/uvicorn, Next.js 16 standalone, SQLite, tini, jq, Home Assistant add-on spec, NodeSource Debian repo.

**Spec:** `docs/superpowers/specs/2026-05-11-haos-addon-deploy-design.md`

---

## File Structure

**Created:**
- `Dockerfile` — combined Python+Node runtime (new content; replaces the renamed file)
- `run.sh` — entrypoint reading `/data/options.json` (with env-var fallback for local Docker testing), seeds `/data/strategies.yaml` + `trading_paused=true` on first boot, supervises both processes
- `config.yaml` — HA add-on manifest (slug, ports, options schema)
- `build.yaml` — multi-arch base image declaration
- `repository.yaml` — declares the GitHub repo as a HA add-on repository
- `.dockerignore` — keep build context lean

**Modified:**
- `sst.config.ts` — change `dockerfile: "Dockerfile"` → `dockerfile: "Dockerfile.api"` (single line)
- `README.md` — add an "Install as Home Assistant add-on" section

**Renamed:**
- `Dockerfile` → `Dockerfile.api` (the existing Python-only image used by SST)

---

## Task 1: Rename existing Dockerfile and update SST config

**Files:**
- Rename: `Dockerfile` → `Dockerfile.api`
- Modify: `sst.config.ts:46`

The existing Python-only Dockerfile is used by SST for the AWS deploy. We're about to put the canonical HA add-on `Dockerfile` at the repo root, so move the old one out of the way first. Single-line SST config update keeps the AWS path runnable.

- [ ] **Step 1.1: Rename the file**

```bash
git mv Dockerfile Dockerfile.api
```

- [ ] **Step 1.2: Update sst.config.ts to point at the renamed file**

In `sst.config.ts`, find:

```ts
      image: {
        context: ".",
        dockerfile: "Dockerfile",
        buildArgs: { CACHE_BUST: Date.now().toString() },
      },
```

Change `dockerfile: "Dockerfile"` to `dockerfile: "Dockerfile.api"`. Final block:

```ts
      image: {
        context: ".",
        dockerfile: "Dockerfile.api",
        buildArgs: { CACHE_BUST: Date.now().toString() },
      },
```

- [ ] **Step 1.3: Fix the dashboard's API URL fallbacks**

`route.ts:4` and `actions.ts:41` both fall back to `http://localhost:8000` when `NEXT_PUBLIC_API_URL` is missing. That's the dashboard's own port — a missing env var would cause the proxy to loop into itself. Change the fallback to `http://127.0.0.1:8001` (the loopback API port the HAOS container actually uses) so the failure mode is a clean "connection refused" rather than a self-proxy.

In `dashboard/app/api/[...path]/route.ts`, find:

```ts
const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
```

Change to:

```ts
const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001").replace(/\/+$/, "");
```

In `dashboard/app/actions.ts`, find:

```ts
  const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000").replace(/\/+$/, "");
```

Change to:

```ts
  const apiUrl = (process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8001").replace(/\/+$/, "");
```

(Local dev `pnpm dev:api` listens on `8000` not `8001`, but it always sets `NEXT_PUBLIC_API_URL` explicitly via the dev script, so the fallback is unreachable in practice.)

- [ ] **Step 1.4: Type-check the SST config**

Run: `pnpm exec tsc --noEmit -p . 2>&1 | grep -v "node_modules" | head -20`

Expected: no errors mentioning `sst.config.ts`. (`tsc` may complain about other files; that's pre-existing and ignored here.)

- [ ] **Step 1.5: Verify the renamed Dockerfile still builds standalone (sanity check, no run)**

Run: `docker build -f Dockerfile.api -t kalshi-api:rename-check . --target=runner 2>&1 | tail -5`

If your `Dockerfile.api` doesn't declare a `runner` target (it doesn't — single-stage), drop `--target=runner`:

Run: `docker build -f Dockerfile.api -t kalshi-api:rename-check . 2>&1 | tail -5`

Expected: `Successfully tagged kalshi-api:rename-check` or similar. If it fails because of network/registry issues unrelated to the rename, that's acceptable — we are only verifying the path resolution.

- [ ] **Step 1.6: Commit**

```bash
git add -A
git commit -m "refactor: rename Dockerfile to Dockerfile.api for SST path

Make room at root for the new HAOS add-on Dockerfile that bundles both
the Python API and the Next.js dashboard. Also fix the dashboard's API
URL fallbacks (route.ts, actions.ts) to point at the loopback API port
(127.0.0.1:8001) instead of the dashboard's own port (localhost:8000),
preventing a silent proxy loop if NEXT_PUBLIC_API_URL is ever unset."
```

---

## Task 2: Add `.dockerignore`

**Files:**
- Create: `.dockerignore`

Keeps Docker build context small (the repo has `__pycache__`, `.venv`, `predictions.db`, `scanner.log` — none of which belong in the image).

- [ ] **Step 2.1: Create `.dockerignore`**

```
.git/
.venv/
node_modules/
**/node_modules/
__pycache__/
**/__pycache__/
.pytest_cache/
.ruff_cache/
.sst/
.planning/
.worktrees/
.claude/
predictions.db
predictions.db-*
soccer-cache.db
scanner.log
*.log
.next/
**/.next/
dashboard/.next/standalone
dashboard/.next/static
.env
.env.local
docs/
images/
```

- [ ] **Step 2.2: Commit**

```bash
git add .dockerignore
git commit -m "chore: add .dockerignore for HAOS combined image"
```

---

## Task 3: Write `run.sh` entrypoint

**Files:**
- Create: `run.sh`

This is the add-on entrypoint. It reads HA-managed options from `/data/options.json` when present (HAOS path), falls back to plain env vars when absent (local Docker testing path). Seeds `/data/strategies.yaml` and `trading_paused=true` on first boot. Supervises both processes via `wait -n` so either process exiting takes the container down — HA Supervisor restarts.

- [ ] **Step 3.1: Write the script**

Create `run.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

echo "[kalshi] Starting Kalshi Trading add-on..."

# Require bash 5.1+ for `wait -n PID...` supervision (Debian bookworm ships 5.2.15).
# Arithmetic (not string concat) so 5.10 doesn't collide with 5.1.
if [ "$(( BASH_VERSINFO[0] * 100 + BASH_VERSINFO[1] ))" -lt 501 ]; then
    echo "[kalshi] ERROR: bash 5.1+ required for 'wait -n PID...' supervision (have ${BASH_VERSION})" >&2
    exit 1
fi

# ─── 1. Load HA add-on options (or fall back to existing env vars) ───
CONFIG_PATH=/data/options.json
if [ -f "$CONFIG_PATH" ]; then
    echo "[kalshi] Reading options from $CONFIG_PATH"
    KALSHI_API_KEY=$(jq -r '.kalshi_api_key // empty' "$CONFIG_PATH"); export KALSHI_API_KEY
    KALSHI_PRIVATE_KEY=$(jq -r '.kalshi_private_key // empty' "$CONFIG_PATH"); export KALSHI_PRIVATE_KEY
    API_TOKEN=$(jq -r '.api_token // empty' "$CONFIG_PATH"); export API_TOKEN
    DASHBOARD_PASSWORD=$(jq -r '.dashboard_password // empty' "$CONFIG_PATH"); export DASHBOARD_PASSWORD
    API_FOOTBALL_KEY=$(jq -r '.api_football_key // empty' "$CONFIG_PATH"); export API_FOOTBALL_KEY
else
    echo "[kalshi] No $CONFIG_PATH — using existing environment variables"
fi

# ─── 2. Hardcoded environment (NOT user-toggleable) ───
export DRY_RUN=true
export DATABASE_URL="sqlite:////data/predictions.db"
export SOCCER_CACHE_DB_PATH="/data/soccer-cache.db"
export STRATEGIES_PATH="/data/strategies.yaml"
export NEXT_PUBLIC_API_URL="http://127.0.0.1:8001"
export PORT=8000
export HOSTNAME=0.0.0.0

# ─── 3. Validate required secrets ───
missing=()
[ -z "${API_TOKEN:-}" ] && missing+=("api_token")
[ -z "${DASHBOARD_PASSWORD:-}" ] && missing+=("dashboard_password")
[ -z "${KALSHI_API_KEY:-}" ] && missing+=("kalshi_api_key")
# Accept either inline PEM (KALSHI_PRIVATE_KEY) or filesystem path (KALSHI_PRIVATE_KEY_PATH).
# api.py:277 reads KALSHI_PRIVATE_KEY_PATH when KALSHI_PRIVATE_KEY is unset.
if [ -z "${KALSHI_PRIVATE_KEY:-}" ] && [ -z "${KALSHI_PRIVATE_KEY_PATH:-}" ]; then
    missing+=("kalshi_private_key_or_kalshi_private_key_path")
fi
if [ ${#missing[@]} -gt 0 ]; then
    echo "[kalshi] ERROR: missing required secrets: ${missing[*]}" >&2
    echo "[kalshi] Set them in the HA add-on options UI (or via --env for local docker run)." >&2
    exit 1
fi

# ─── 4. Ensure /data exists, is writable, and seed first-boot files ───
# Combined check: mkdir -p under `set -e` would abort with a confusing
# "Read-only file system" error before our friendly message; do both inside
# the same guarded block. Also remove the sentinel inline so a signal arriving
# between touch and rm can't leave a stray file behind.
if ! mkdir -p /data 2>/dev/null \
        || ! ( touch /data/.write_test && rm -f /data/.write_test ) 2>/dev/null; then
    echo "[kalshi] ERROR: /data is not writable (check 'map: data:rw' in config.yaml; bind-mount may be read-only)" >&2
    exit 1
fi

if [ ! -f /data/strategies.yaml ]; then
    echo "[kalshi] Seeding /data/strategies.yaml from image"
    cp /app/strategies.yaml /data/strategies.yaml
fi

# Seed trading_paused=true on first boot only (idempotent — leaves existing
# value alone so the user can unpause via the dashboard later).
echo "[kalshi] Initializing DB schema and checking trading_paused seed"
cd /app
if ! /app/.venv/bin/python - <<'PY'; then
import sys
try:
    from predictions.db import init_db, set_config, get_session, ConfigEntry
    init_db()
    session = get_session()
    existing = session.query(ConfigEntry).filter_by(key="trading_paused").first()
    session.close()
    if existing is None:
        set_config("trading_paused", "true")
        print("[kalshi] Seeded trading_paused=true (first boot)")
    else:
        print(f"[kalshi] trading_paused already set: {existing.value}")
except Exception as e:
    print(f"[kalshi] ERROR during DB init/seed: {type(e).__name__}: {e}", file=sys.stderr)
    sys.exit(1)
PY
    echo "[kalshi] ERROR: DB init / trading_paused seed failed" >&2
    exit 1
fi

# ─── 5. Set up signal handling before any process starts ───
API_PID=""
DASH_PID=""
cleanup() {
    echo "[kalshi] Shutting down (received signal)"
    [ -n "$API_PID" ] && kill -TERM "$API_PID" 2>/dev/null || true
    [ -n "$DASH_PID" ] && kill -TERM "$DASH_PID" 2>/dev/null || true
    # Wait only on the children we know about so a stale subprocess can't hang us.
    wait "$API_PID" "$DASH_PID" 2>/dev/null || true
}
trap cleanup SIGTERM SIGINT

# ─── 6. Start API+scanner in background on 127.0.0.1:8001 ───
cd /app
/app/.venv/bin/uvicorn predictions.api:app \
    --host 127.0.0.1 --port 8001 --log-level info &
API_PID=$!
echo "[kalshi] uvicorn started (PID $API_PID) on 127.0.0.1:8001"

# ─── 7. Start dashboard in background on 0.0.0.0:8000 ───
cd /dashboard
node server.js &
DASH_PID=$!
echo "[kalshi] next started (PID $DASH_PID) on 0.0.0.0:8000"

# ─── 8. Block until either child exits; then force container exit ───
# Force exit code >=1 on unexpected child death so HA Supervisor restarts us.
# A clean exit (status 0) from one child while the other is still healthy is
# still treated as failure — both processes are required for the add-on to work.
wait -n "$API_PID" "$DASH_PID"
EXIT=$?
echo "[kalshi] A child exited with status $EXIT — killing siblings and forcing restart"
kill -TERM "$API_PID" "$DASH_PID" 2>/dev/null || true
wait || true
# Treat any child exit as failure (force HA Supervisor restart)
exit $(( EXIT > 0 ? EXIT : 1 ))
```

- [ ] **Step 3.2: Make it executable**

```bash
chmod +x run.sh
```

- [ ] **Step 3.3: shellcheck it**

Run: `shellcheck run.sh`

If `shellcheck` isn't installed, skip and rely on the local smoke test in Task 5. Expected (when installed): no warnings, or only stylistic ones (e.g. SC2086 about word-splitting in the `${missing[*]}` join, which we want).

- [ ] **Step 3.4: Commit**

```bash
git add run.sh
git commit -m "feat: add HAOS add-on entrypoint with first-boot seeding

Reads /data/options.json on HA, falls back to env vars locally. Seeds
/data/strategies.yaml and trading_paused=true on first boot only.
Supervises uvicorn (loopback API) + node (public dashboard) via wait -n
so any process death takes the container down for HA Supervisor restart."
```

---

## Task 4: Write the combined `Dockerfile`

**Files:**
- Create: `Dockerfile` (combined runtime; sibling of the renamed `Dockerfile.api`)

Multi-stage:
1. `dashboard-build` — `node:20-alpine` + pnpm 10.8.1, build dashboard from workspace root → `.next/standalone`.
2. `python-build` — `python:3.13-slim-bookworm` + uv, install Python deps + project.
3. `runner` — `python:3.13-slim-bookworm` + NodeSource Node 20 + tini + jq, assemble both stages.

The dashboard build copies the workspace root files (`package.json`, `pnpm-workspace.yaml`, `pnpm-lock.yaml`) plus both workspace package manifests (`dashboard/package.json`, `cli/package.json`) because pnpm workspaces resolve the full graph during install. Then `pnpm install --filter dashboard...` installs only what dashboard needs (the trailing `...` includes workspace deps; in practice the dashboard has no workspace dep on `cli`, so this is just safety).

- [ ] **Step 4.1: Set Next.js standalone tracing root to the monorepo root**

`next build` with `output: "standalone"` traces module dependencies starting from the package directory. In a pnpm workspace where `node_modules/` is hoisted to the workspace root, that default tracing misses hoisted deps and produces an incomplete `.next/standalone/node_modules/`. The Dockerfile would then copy a partial node_modules and `node server.js` would crash at runtime with `MODULE_NOT_FOUND`.

In `dashboard/next.config.ts`, find:

```ts
import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  output: "standalone",
};

export default nextConfig;
```

Change to:

```ts
import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  output: "standalone",
  // Trace from the monorepo root so pnpm-hoisted node_modules end up in
  // .next/standalone/node_modules/ instead of being missed.
  outputFileTracingRoot: path.join(__dirname, ".."),
};

export default nextConfig;
```

Verify locally:

```bash
(cd dashboard && pnpm build 2>&1 | tail -10)
ls dashboard/.next/standalone/node_modules/ | head -5
```

Expected: `pnpm build` finishes without errors; `node_modules/` contains at least `next/`, `react/`, `react-dom/`.

(This is a build-correctness change; commit it as part of the Task 4 commit that introduces the Dockerfile, since the Dockerfile's standalone COPY assumes this layout.)

- [ ] **Step 4.2: Write the Dockerfile**

Create `Dockerfile`:

```dockerfile
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
WORKDIR /dashboard
COPY --from=dashboard-build /build/dashboard/.next/standalone/dashboard/ ./
COPY --from=dashboard-build /build/dashboard/.next/standalone/node_modules/ ./node_modules/
COPY --from=dashboard-build /build/dashboard/.next/static ./.next/static
COPY --from=dashboard-build /build/dashboard/public ./public

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
```

Note on the standalone copy paths: Next.js workspace builds put the standalone output at `.next/standalone/dashboard/` (the workspace package name) with hoisted `node_modules/` at `.next/standalone/node_modules/`. The Dockerfile copies both. If `pnpm --filter dashboard build` outputs a different layout for your Next 16 / pnpm 10 combo, fix the COPY paths and the next step will catch it.

- [ ] **Step 4.3: Probe the dashboard standalone output layout (required before full build)**

Different Next.js versions and pnpm workspace configurations produce different standalone layouts. Verify the assumed paths before committing the Dockerfile.

```bash
docker build -t kalshi-probe --target dashboard-build . 2>&1 | tail -5
docker run --rm kalshi-probe ls -la /build/dashboard/.next/standalone/ /build/dashboard/.next/standalone/dashboard/ 2>&1 | head -40
```

Expected: `/build/dashboard/.next/standalone/dashboard/` contains `server.js`. The hoisted `node_modules/` lives at either `/build/dashboard/.next/standalone/node_modules/` (workspace-hoisted) or `/build/dashboard/.next/standalone/dashboard/node_modules/`. If the layout differs, adjust the four `COPY --from=dashboard-build ...` lines in the runner stage of `Dockerfile` accordingly before the full build.

- [ ] **Step 4.4: Build the full image**

```bash
docker build -t kalshi-trading:smoke . 2>&1 | tail -30
```

Expected: ends with `=> => writing image sha256:...` and `=> => naming to kalshi-trading:smoke`. The `RUN test -f /dashboard/server.js` assertion in the Dockerfile fails fast if the COPY paths are wrong.

Common failures and fixes:
- `pnpm install` fails because lockfile mentions `cli` but its `package.json` wasn't copied → already handled by Step 4.2's `COPY cli/package.json ./cli/`.
- `uv sync` cannot find `strategies.yaml` → not needed for python-build stage (only copied to runner).
- NodeSource curl-pipe fails → check network on the build host; the script lives at `https://deb.nodesource.com/setup_20.x`.

- [ ] **Step 4.5: Verify image size sanity**

```bash
docker images kalshi-trading:smoke
```

Expected: image size between 500 MB and 1.5 GB. Anything dramatically larger (>2 GB) means apt caches weren't cleaned — re-check the `apt-get clean && rm -rf /var/lib/apt/lists/*` step.

- [ ] **Step 4.6: Commit**

```bash
git add Dockerfile dashboard/next.config.ts
git commit -m "feat: add combined Python+Node Dockerfile for HAOS add-on

Multi-stage build: alpine builds Next.js standalone, slim-bookworm
installs Python deps with uv, runner combines both with NodeSource Node 20,
tini, and jq. Image runs uvicorn (loopback API) + node (public dashboard)
supervised by run.sh. Also sets outputFileTracingRoot in next.config.ts
so the pnpm-hoisted node_modules end up in .next/standalone/node_modules/
where the Dockerfile expects them."
```

---

## Task 5: Add HA add-on manifests

**Files:**
- Create: `config.yaml`
- Create: `build.yaml`
- Create: `repository.yaml`

Three small YAML files. They aren't read until the repo is added to HA Supervisor, but we validate syntax locally.

- [ ] **Step 5.1: Write `config.yaml`**

```yaml
name: "Kalshi Trading"
version: "1.0.0"
slug: "kalshi_trading"
description: "Kalshi sports market scanner — dry-run only"
url: "https://github.com/petrapa6/kalshi-trading"
arch:
  - aarch64
  - amd64
ports:
  8000/tcp: 8000
ports_description:
  8000/tcp: "Dashboard web interface"
map:
  - data:rw
options:
  kalshi_api_key: ""
  kalshi_private_key: ""
  api_token: ""
  dashboard_password: ""
  api_football_key: ""
schema:
  kalshi_api_key: password
  kalshi_private_key: password
  api_token: password
  dashboard_password: password
  api_football_key: str?
startup: "application"
boot: "auto"
```

(`url:` uses the assumed `petrapa6/kalshi-trading` owner; the user said "same repo" but didn't confirm the GitHub org name. Adjust if the repo lives elsewhere — this is metadata only, doesn't affect runtime.)

- [ ] **Step 5.2: Write `build.yaml`**

```yaml
build_from:
  aarch64: "python:3.13-slim-bookworm"
  amd64: "python:3.13-slim-bookworm"
labels:
  org.opencontainers.image.title: "Kalshi Trading"
  org.opencontainers.image.source: "https://github.com/petrapa6/kalshi-trading"
```

- [ ] **Step 5.3: Write `repository.yaml`**

```yaml
name: Kalshi Trading
url: https://github.com/petrapa6/kalshi-trading
maintainer: Pavel
```

- [ ] **Step 5.4: Validate YAML syntax**

Run:

```bash
python3 -c "import yaml; [print(f, yaml.safe_load(open(f))) for f in ['config.yaml', 'build.yaml', 'repository.yaml']]"
```

Expected: three lines, each dumping the parsed dict. No tracebacks.

- [ ] **Step 5.5: Commit**

```bash
git add config.yaml build.yaml repository.yaml
git commit -m "feat: add Home Assistant add-on manifests

config.yaml declares ports, /data volume, and typed secret options.
build.yaml declares multi-arch (aarch64 + amd64) base image metadata.
repository.yaml lets HA Supervisor index this repo as an add-on source."
```

---

## Task 6: Local end-to-end smoke test

**Files:** (none new)

Run the image like HA would, but supply secrets via `--env` instead of `/data/options.json`. Verify the dashboard serves and the API is reachable from inside the container.

- [ ] **Step 6.1: Prepare a local data directory and env file**

```bash
mkdir -p .haos-smoke-data
cat > .haos-smoke.env <<'EOF'
KALSHI_API_KEY=<paste-from-.env>
KALSHI_PRIVATE_KEY=<paste-multiline-from-.env-or-mount-file>
API_TOKEN=<paste-from-.env>
DASHBOARD_PASSWORD=<paste-from-.env>
API_FOOTBALL_KEY=<paste-from-.env>
EOF
echo ".haos-smoke.env" >> .gitignore
echo ".haos-smoke-data/" >> .gitignore
git add .gitignore
git commit -m "chore: gitignore local smoke-test artifacts (.haos-smoke.env, .haos-smoke-data/)"
```

(Multi-line `KALSHI_PRIVATE_KEY` in an env file is fragile. If your private key has literal newlines, instead mount the key file into the container and adjust `run.sh` to read `KALSHI_PRIVATE_KEY_PATH` — already supported by `api.py:277`. For this smoke test alone, the simpler option is `docker run -e KALSHI_PRIVATE_KEY="$(cat secrets/kalshi.pem)" ...`.)

- [ ] **Step 6.2: Run the container**

If your `.env` stores `KALSHI_PRIVATE_KEY_PATH` (a path to a `.pem` file on disk), use that — it's the safe path for multi-line PEM keys:

```bash
docker run --rm \
    --name kalshi-smoke \
    -p 8000:8000 \
    -v "$(pwd)/.haos-smoke-data:/data" \
    -v "$(pwd)/secrets/kalshi.pem:/run/kalshi.pem:ro" \
    --env-file .haos-smoke.env \
    -e KALSHI_PRIVATE_KEY_PATH=/run/kalshi.pem \
    kalshi-trading:smoke 2>&1 | tee /tmp/kalshi-smoke.log
```

(Add `KALSHI_PRIVATE_KEY_PATH=` to your `.haos-smoke.env` instead of `KALSHI_PRIVATE_KEY=`, and leave the inline PEM line out of the env file.)

Only if you store the PEM inline in `.env` (multi-line value), use this fallback which reads it via a heredoc-safe expansion:

```bash
# Docker --env-file expects a real file path; process substitution (<(...))
# resolves to /dev/fd/N which is unreliable across Docker frontends. Write
# to a temp file with 0600 mode so other users on the dev machine cannot
# read the secrets, and clean it up on exit.
trap 'rm -f /tmp/kalshi-smoke.env' EXIT
( umask 077 && grep -v '^KALSHI_PRIVATE_KEY=' .haos-smoke.env > /tmp/kalshi-smoke.env )

docker run --rm \
    --name kalshi-smoke \
    -p 8000:8000 \
    -v "$(pwd)/.haos-smoke-data:/data" \
    --env-file /tmp/kalshi-smoke.env \
    -e KALSHI_PRIVATE_KEY="$(cat secrets/kalshi.pem)" \
    kalshi-trading:smoke 2>&1 | tee /tmp/kalshi-smoke.log
```

Run in one terminal; leave it streaming logs.

Expected stdout, in order:
```
[kalshi] Starting Kalshi Trading add-on...
[kalshi] No /data/options.json — using existing environment variables
[kalshi] Seeding /data/strategies.yaml from image
[kalshi] Initializing DB schema and checking trading_paused seed
[kalshi] Seeded trading_paused=true (first boot)
[kalshi] uvicorn started (PID ...) on 127.0.0.1:8001
[kalshi] next started (PID ...) on 0.0.0.0:8000
```

Followed by Next.js's `▲ Next.js 16.x.x` startup line and scanner log lines from the Python side.

- [ ] **Step 6.3: Hit the dashboard from the host**

In another terminal:

```bash
curl -sI http://localhost:8000/ | head -5
```

Expected:
```
HTTP/1.1 200 OK
Content-Type: text/html; ...
```

Then in a browser visit `http://localhost:8000/`. Verify:
- The login page renders.
- Entering the wrong password fails.
- Entering `$DASHBOARD_PASSWORD` succeeds and you see the main dashboard.

- [ ] **Step 6.4: Verify the proxy actually routes to the API**

Confirm `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001` is honored by the Next.js server-side proxy. After logging in (or simulating the session cookie), call a proxied endpoint:

```bash
# Wait for both the dashboard and the internal API to come up. Both processes
# start in parallel; uvicorn's first scan loop can take 3-8s and Next.js
# standalone has its own cold-start latency. Without this, the proxy curl
# races the API startup and returns 502 → false-negative test.
echo "[smoke] Waiting for dashboard to respond on :8000..."
for i in $(seq 1 30); do
    if curl -sf -o /dev/null --max-time 2 http://localhost:8000/; then
        echo "[smoke] Dashboard is up"
        break
    fi
    sleep 1
    [ "$i" -eq 30 ] && { echo "[smoke] Dashboard never responded" >&2; exit 1; }
done

# Quick check that the API is also reachable from inside the container.
# (We can't curl :8001 from the host — it's loopback-only inside the container —
# but if `docker exec` works the container itself is healthy.)
docker exec kalshi-smoke curl -sf -o /dev/null --max-time 2 http://127.0.0.1:8001/ \
    || { echo "[smoke] API not yet listening on 127.0.0.1:8001 inside the container" >&2; exit 1; }
echo "[smoke] API is up inside the container"

# First, get the session cookie by logging in:
curl -s -c /tmp/kalshi-cookies.txt -X POST http://localhost:8000/api/login \
    -H "Content-Type: application/json" \
    -d "{\"password\":\"$DASHBOARD_PASSWORD\"}" -o /dev/null -w "%{http_code}\n"
# Expected: 200

# Now use that cookie to hit a proxied API endpoint:
curl -s -b /tmp/kalshi-cookies.txt http://localhost:8000/api/stats | head -c 200
# Expected: a JSON body (e.g. {"open_positions":0,...}), NOT an empty proxy loop or 502.
```

(Note: the actual login endpoint path depends on how `actions.ts::login` is wired through Next's server actions — adjust the curl URL if `/api/login` doesn't exist as a proper route. If you can't easily replay the server-action handshake from curl, do this check in a browser instead: log in, open DevTools → Network, and confirm `/api/*` requests return non-empty bodies with status 200.)

- [ ] **Step 6.5: Verify the API is NOT reachable from the host**

```bash
curl -s -o /dev/null -w "%{http_code}\n" --max-time 2 http://localhost:8001/ || echo "exit=$?"
```

Expected: connection refused / timeout (the API binds to `127.0.0.1` inside the container — port 8001 is not mapped out). If you see `200`, the API is leaking — check the Dockerfile `EXPOSE` block and `docker run -p` flags.

- [ ] **Step 6.6: Verify trading_paused was seeded**

```bash
docker exec kalshi-smoke /app/.venv/bin/python -c "from predictions.db import get_config; print(get_config('trading_paused'))"
```

Expected: `true`

- [ ] **Step 6.7: Verify DB persistence across restarts**

```bash
# Manually flip the value (simulates the user unpausing later)
docker exec kalshi-smoke /app/.venv/bin/python -c "from predictions.db import set_config; set_config('trading_paused', 'false'); print('set')"

# Restart the container
docker stop kalshi-smoke
docker run --rm --name kalshi-smoke -p 8000:8000 \
    -v "$(pwd)/.haos-smoke-data:/data" \
    --env-file .haos-smoke.env \
    [...same -e flags as Step 6.2...] \
    kalshi-trading:smoke 2>&1 | head -20
```

Expected on the restart: `[kalshi] trading_paused already set: false` — confirms first-boot seeding is idempotent and didn't reset to `true`.

After confirming, stop the container (Ctrl-C) and reset `trading_paused` back to `true` for safety:

```bash
docker run --rm -v "$(pwd)/.haos-smoke-data:/data" --env-file .haos-smoke.env [...] kalshi-trading:smoke /app/.venv/bin/python -c "from predictions.db import set_config; set_config('trading_paused', 'true')"
```

(Skip this last reset if you intend to commit the `.haos-smoke-data/` to the gitignore and move on; it's already gitignored.)

- [ ] **Step 6.8: Cleanup**

```bash
docker stop kalshi-smoke 2>/dev/null || true
docker rm kalshi-smoke 2>/dev/null || true
```

- [ ] **Step 6.9: No commit needed** — this task only verifies the build. If you discovered fixes (e.g. wrong COPY paths in the Dockerfile), commit those as separate `fix:` commits.

---

## Task 7: Update README with HAOS install steps

**Files:**
- Modify: `README.md` (append a new section)

Document the four manual steps the user takes to get this running on their HA: add repo, install add-on, configure secrets, wire Cloudflare Tunnel + Access.

- [ ] **Step 7.1: Append section to README.md**

Add the following to the bottom of `README.md` (or under an existing "Deployment" section if one exists — check before appending):

```markdown
## Run as a Home Assistant add-on (dry-run only)

This repo ships as a HA add-on alongside the SST/AWS deploy. The add-on
runs the scanner and dashboard in a single container, exposes the
dashboard on port 8000, and stores SQLite + strategies under `/data`
(included in HA backups). `DRY_RUN=true` is hardcoded in `run.sh` and
`trading_paused=true` is seeded on first boot — three independent
locks prevent live orders.

### One-time setup

1. **Add the add-on repository.** In HA → Settings → Add-ons → Add-on
   Store → ⋮ (top right) → Repositories → paste:

   ```
   https://github.com/petrapa6/kalshi-trading
   ```

2. **Install "Kalshi Trading"** from the now-visible repo entry. HA
   Supervisor builds the image on-device (first build takes ~5–10 min on
   a Raspberry Pi).

3. **Configure secrets** in the add-on's Configuration tab:
   - `kalshi_api_key` — from Kalshi
   - `kalshi_private_key` — PEM contents, multi-line
   - `api_token` — generate with `openssl rand -hex 32`
   - `dashboard_password` — login password
   - `api_football_key` — optional, only for soccer backtest

4. **Start the add-on.** Watch the log for `[kalshi] Seeded
   trading_paused=true (first boot)` and `[kalshi] next started`.

### Expose via Cloudflare Tunnel

1. Install the [Cloudflared HA add-on](https://github.com/brenner-tobias/ha-addons)
   if not already installed.
2. In its config, add an ingress rule:

   ```yaml
   - hostname: trading.petra-czech.cc
     service: http://homeassistant.local:8000
   ```

3. In Cloudflare DNS, create a CNAME for `trading.petra-czech.cc`
   pointing at the tunnel UUID (Cloudflare's dashboard handles this
   automatically when you create the tunnel).

### Gate access with Cloudflare Access

1. In Cloudflare Zero Trust → Access → Applications → Add an application
   (Self-hosted).
2. Application domain: `trading.petra-czech.cc`.
3. Policy: include rule "Emails: petracekpav@gmail.com" (one-time PIN or
   Google OAuth).

Cloudflare Access is defense-in-depth. The dashboard password is the
second lock; if you skip Access setup entirely the add-on is still
protected by the password.

### Updates

`Settings → Add-ons → Kalshi Trading → ⋮ → Check for updates` pulls the
latest commit from `master` and rebuilds the image. `/data/predictions.db`
and `/data/strategies.yaml` survive upgrades.

### Local build (for HAOS parity testing)

```bash
docker build -t kalshi-trading:local .
docker run --rm -p 8000:8000 \
    -v "$(pwd)/.haos-smoke-data:/data" \
    --env-file .haos-smoke.env \
    kalshi-trading:local
```

Open `http://localhost:8000`. The existing `pnpm dev:api` + `pnpm
dev:dashboard` workflow is unchanged and remains the fast inner loop.
```

- [ ] **Step 7.2: Commit**

```bash
git add README.md
git commit -m "docs: add HAOS add-on install + Cloudflare Tunnel/Access guide"
```

---

## Self-Review (post-write)

**Spec coverage check:**

| Spec section | Tasks covering it |
|---|---|
| Architecture topology (loopback API + public dashboard) | Task 3 (run.sh ports), Task 4 (Dockerfile EXPOSE), Task 6.4 (verification) |
| Process supervision (`wait -n`) | Task 3.1 |
| Single-add-on-at-repo-root layout | Tasks 4, 5 |
| Rename `Dockerfile` → `Dockerfile.api` + SST update | Task 1 |
| Config.yaml options schema | Task 5.1 |
| build.yaml multi-arch | Task 5.2 |
| repository.yaml | Task 5.3 |
| `/data` persistence + HA backup inclusion | Task 3 (paths), Task 5.1 (`map: data:rw`), Task 6.6 (cross-restart verification) |
| Persistence & migration (S3 backup loop no-op, strategies.yaml seed) | Task 3.1 (`STRATEGIES_PATH` + first-boot copy), run.sh leaves `DB_BACKUP_BUCKET` unset → backup_loop becomes no-op (no code change) |
| Error handling & operations (restart on exit, log capture, HA backup) | Task 5.1 (`boot: auto` + `startup: application` in `config.yaml`; `map: data:rw` for HA backup), Task 3.1 (stdout/stderr from both processes) |
| Three dry-run locks | Task 3.1 (`DRY_RUN=true` + `trading_paused` seed), code-level DRY-01 is pre-existing |
| `NEXT_PUBLIC_API_URL` server-side runtime read | Task 1 (Step 1.3, fallback fix in route.ts + actions.ts), Task 3.1 (export in run.sh) |
| Cloudflare Access wired manually | Task 7.1 (README) |
| Local Docker test parity | Task 6 |

No gaps.

**Placeholder scan:** Searched for "TBD", "TODO", "fill in", "add error handling" — none present. The `<paste-from-.env>` placeholders in Task 6.1 are deliberate input fields the executor fills with their own secrets; that's not a plan-failure placeholder.

**Type consistency:** `API_PID`/`DASH_PID` names are consistent across run.sh and the spec. Port numbers 8000/8001 consistent across all tasks. Volume path `/data` consistent. `trading_paused` key spelled consistently. ✓

---

## Known limitations (deferred)

### `NEXT_PUBLIC_API_URL` is a build-time-baked variable

The dashboard's `actions.ts:41` and `app/api/[...path]/route.ts:4` both read `process.env.NEXT_PUBLIC_API_URL`. The `NEXT_PUBLIC_` prefix means Next.js inlines the value into the client bundle at `next build` time — but both call sites today are server-side (server actions + route handlers), which read from `process.env` at request time. So our runtime `export NEXT_PUBLIC_API_URL=http://127.0.0.1:8001` in `run.sh` is honored where it matters.

**Risk:** Any future PR that adds *client-side* code reading `process.env.NEXT_PUBLIC_API_URL` will silently use the build-time-baked fallback (after Step 1.3, that's `http://127.0.0.1:8001` — the loopback API port, which is also unreachable from the browser since it's container-internal), not the runtime value.

**Deferred fix (separate refactor):** Rename to `API_URL` (no `NEXT_PUBLIC_` prefix) in `actions.ts`, `route.ts`, `run.sh`, and `sst.config.ts`. Pure server-side reads don't need the prefix; removing it eliminates the bake hazard.
