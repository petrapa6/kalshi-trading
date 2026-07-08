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

# ─── 2. Hardcoded environment (paths + ports; NOT user-toggleable) ───
# Dry-run mode is a runtime DB config value (`dry_run`), toggled from the
# dashboard — not an env var. Absence defaults to dry-run ON. The
# trading_paused=true first-boot seed below remains the safety floor.
export DATABASE_URL="sqlite:////data/predictions.db"
export SOCCER_CACHE_DB_PATH="/data/soccer-cache.db"
export STRATEGIES_PATH="/data/strategies.yaml"
# API_URL (not NEXT_PUBLIC_) so the dashboard's server-side proxy reads it at
# runtime; NEXT_PUBLIC_API_URL is baked into the bundle at build time and can't
# be overridden here.
export API_URL="http://127.0.0.1:8001"
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
