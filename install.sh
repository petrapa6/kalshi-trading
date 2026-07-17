#!/usr/bin/env bash
# install.sh — one-command bootstrap for the Kalshi trading scanner.
#
# Idempotent: safe to re-run. Does not modify anything outside this repo
# except the Python venv and pnpm store (both managed by the tools below).

set -euo pipefail

cd "$(dirname "$0")"

log() { printf '[install] %s\n' "$*"; }
warn() { printf '[install] WARN: %s\n' "$*" >&2; }
fail() { printf '[install] FATAL: %s\n' "$*" >&2; exit 1; }

need() {
    local cmd=$1
    local hint=$2
    if ! command -v "$cmd" >/dev/null 2>&1; then
        fail "$cmd is required but not on PATH. Install it: $hint"
    fi
    log "found: $(command -v "$cmd")"
}

# ─── 1. Prerequisite check ──────────────────────────────────────────────────
log "checking prerequisites…"
need uv "curl -LsSf https://astral.sh/uv/install.sh | sh"
need pnpm "curl -fsSL https://get.pnpm.io/install.sh | sh  (or: npm i -g pnpm)"
need node "install Node.js >= 20 from https://nodejs.org"

node_major=$(node -v | sed -E 's/^v([0-9]+).*/\1/')
if [ "$node_major" -lt 20 ]; then
    fail "Node $node_major detected, but Node >= 20 is required by Next.js 16."
fi

if command -v docker >/dev/null 2>&1; then
    log "docker: $(docker --version)"
else
    warn "docker not found (optional — only needed for local container builds)"
fi

# ─── 2. Python install ──────────────────────────────────────────────────────
log "installing Python deps via uv…"
uv sync

# ─── 3. JS install ──────────────────────────────────────────────────────────
log "installing root JS deps…"
pnpm install --silent

log "installing dashboard deps…"
(cd dashboard && pnpm install --silent)

log "installing cli deps…"
(cd cli && pnpm install --silent)

# ─── 4. Env bootstrap ───────────────────────────────────────────────────────
if [ -f .env ]; then
    log ".env already exists — leaving untouched"
else
    if [ -f .env.example ]; then
        cp .env.example .env
        log "copied .env.example → .env  (edit it to add your Kalshi keys)"
    else
        warn ".env.example missing — skipping env bootstrap"
    fi
fi

# ─── 5. Pre-commit hook ─────────────────────────────────────────────────────
if [ -d .git/hooks ]; then
    hook_target=.git/hooks/pre-commit
    script=scripts/pre-commit-check.sh
    chmod +x "$script"
    if [ -L "$hook_target" ] && [ "$(readlink "$hook_target")" = "../../$script" ]; then
        log "pre-commit hook already installed"
    else
        ln -sf "../../$script" "$hook_target"
        log "installed pre-commit hook → $script"
    fi
else
    warn ".git/hooks missing — initialise git first, then rerun to install the hook"
fi

# ─── 6. Next steps ──────────────────────────────────────────────────────────
cat <<'EOF'

[install] done.

Next steps:
  1. Edit .env to fill in your secrets (Kalshi keys, API_TOKEN, …).
  2. Run the API + scanner locally:
         pnpm dev:api
  3. Run the dashboard locally (separate terminal):
         pnpm dev:dashboard
  4. Use the CLI (once API is running):
         pnpm cli config
         pnpm cli stats

To deploy for real, install this repo as a Home Assistant add-on —
see the "Deploy" section of README.md.
EOF
