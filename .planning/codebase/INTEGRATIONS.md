---
last_mapped: 2026-04-30
last_mapped_commit: d010a403e3997670cdce46c100b8d39438c4783d
---

# External Integrations

**Analysis Date:** 2026-04-30

## APIs & External Services

**Kalshi Trading API:**
- Async REST client: `src/predictions/kalshi_client.py` — `KalshiClient` class
- Base URL: `https://api.elections.kalshi.com/trade-api/v2`
- Auth: RSA-signed headers (KALSHI-ACCESS-KEY, KALSHI-ACCESS-SIGNATURE, KALSHI-ACCESS-TIMESTAMP)
- Key methods: `get_events()`, `get_markets()`, `get_series()`, `create_order()`, `get_balance()`, `get_market()`
- Price format: FixedPointDollars strings (e.g., `"0.9200"`) — normalized to integer cents in `extract_cents()`
- Order placement: still accepts integer cents for `yes_price` / `no_price`
- SDK: `httpx` (async HTTP client)
- Credentials: `KALSHI_API_KEY` (key ID), `KALSHI_PRIVATE_KEY` (RSA PEM) or `KALSHI_PRIVATE_KEY_PATH`

**Kalshi WebSocket v2:**
- Async WebSocket listener: `src/predictions/kalshi_client.py` — `KalshiWebSocket` class
- Path: `wss://api.elections.kalshi.com/ws-api/v2` (authenticated with same RSA headers)
- Handler: `on_lifecycle` in `src/predictions/scanner.py::run_scanner()` processes `market_lifecycle_v2` events
- Updates live market prices into module-level `market_prices` dict
- Triggers settlement checks when markets finalize
- SDK: `websockets` 16.0

**ESPN Scoreboards API:**
- Base URL: `https://site.api.elections.kalshi.com/apis/site/v2/sports/<path>/scoreboard`
- Client: `src/predictions/espn.py` — `get_scoreboard()` function
- Polling: 10-second intervals in `espn_loop()` within `run_scanner()`
- Purpose: Real-time game state (period, clock, score) to verify game is in final minutes
- Maps Kalshi series tickers to ESPN sport paths (e.g., `KXNBAGAME` → `basketball/nba`)
- Returns: `GameState` dataclass with home/away scores, period, clock seconds, status
- No auth required (undocumented public endpoint)
- SDK: `httpx` (sync calls in ESPN loop)

**API-Football v3:**
- Base URL: `https://api-football.com/v3/…`
- Purpose: Soccer match historical data and fixture details for backtest cache
- Client: `src/predictions/soccer_cache.py` — fetches finished matches and goal events
- Auth: `X-RapidAPI-Key: {API_FOOTBALL_KEY}` header
- Key credential: `API_FOOTBALL_KEY` (from `.env` or SST secrets)
- Plans quota: Free plan = 100 requests/day, 30 req/min
- Cached responses stored in separate SQLite DB (`soccer-cache.db`)
- SDK: `httpx` (async calls)

## Data Storage

**Databases:**

**Main DB — SQLite:**
- Location: `predictions.db` (repo root in dev), `/tmp/predictions.db` (ECS production)
- Connection: `src/predictions/db.py`
- ORM: SQLAlchemy 2 declarative models
- Tables:
  - `trades` — placed bets, settlement status, P&L
  - `opportunities` — detected high-probability markets
  - `stretch_opportunities` — near-misses for what-if analysis
  - `scans` — aggregated scan runs
  - `balance_snapshots` — portfolio balance history
  - `config` — runtime-tunable parameters (re-read every scan loop)
- Inline migrations: `_migrate_add_columns()` in `db.py` for schema evolution
- Durability: Snapshot via S3 every 30 minutes (see S3 Backups below)

**Soccer Cache DB — SQLite:**
- Location: `soccer-cache.db` (repo root in dev), `/tmp/soccer-cache.db` (ECS production)
- Connection: `src/predictions/soccer_cache.py`
- ORM: SQLAlchemy 2
- Tables:
  - `soccer_matches` — finished match results (home/away scores, kickoff time)
  - `soccer_goals` — chronological goal sequence per match (minute, scorer side, own-goal flag)
- Purpose: Backtesting historical soccer markets against API-Football
- No S3 backup — ephemeral (rebuilds on container start)

## File Storage

**S3 Bucket (DB Backups):**
- Service: AWS S3
- Bucket name: `{app_name}-DbBackups` (defined in `sst.config.ts`)
- Backup strategy:
  - **30-minute snapshots**: `backup_loop()` in `scanner.py` uploads to `backups/YYYY-MM-DD/HHMM-predictions.db`
  - **Latest symlink**: Also uploaded to `backups/latest.db` for quick recovery
  - **Startup**: `_download_db()` in `api.py` fetches `latest.db` before initializing
  - **Graceful shutdown**: `_backup_db_sync()` uploads final snapshot on container stop
- SDK: `boto3` (S3 client)
- Environment: `DB_BACKUP_BUCKET` env var (set in `sst.config.ts`)
- Access: IAM role attached to ECS task (S3 read/write permissions)

## Caching

**Module-level Dict:**
- `market_prices` dict in `src/predictions/scanner.py` — shared live market price cache
- Populated by WebSocket handler (`on_lifecycle`)
- Read by scanner loop to avoid re-fetching from REST API
- Ephemeral (lost on process restart)

## Authentication & Identity

**Kalshi API Auth:**
- Mechanism: RSA PSS + SHA256 signature on timestamp + HTTP method + path
- Headers: KALSHI-ACCESS-KEY (public key ID), KALSHI-ACCESS-SIGNATURE (base64-encoded signature), KALSHI-ACCESS-TIMESTAMP (milliseconds)
- Implementation: `_sign()` and `_headers()` in `KalshiClient`
- Credentials sourced: `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY` (or `KALSHI_PRIVATE_KEY_PATH`)

**Dashboard/API Auth:**
- Mechanism: Bearer token (shared secret)
- Header: `Authorization: Bearer {API_TOKEN}`
- Validation: `_check_token()` dependency in FastAPI endpoints
- Token storage: `.env` (local), SST secrets (production)
- Endpoints protected: All `/api/…` mutating endpoints (config set, backtest) require Bearer
- Public endpoints: `GET /` (health), `GET /api/stats` (read-only, but Bearer-gated per code)

**Dashboard Password:**
- Mechanism: Client-side form submission to server action (`login()` in `dashboard/app/actions.ts`)
- Hash: bcrypt (server-side, not exposed to client)
- Storage: `DASHBOARD_PASSWORD` env var (SST secret in production)
- Session: Next.js cookies after login
- Purpose: Single-user access control for read-only UI

## Monitoring & Observability

**Error Tracking:**
- Not integrated (no Sentry/DataDog)
- Errors logged to `scanner.log` file (streams to container stdout + file)

**Logs:**
- Python: `logging.basicConfig()` in `scanner.py` — StreamHandler + FileHandler (`scanner.log`)
- Format: `[TIMESTAMP] [LEVEL] message`
- Dashboard: Next.js server logs to stdout
- Production: Container logs streamed to ECS CloudWatch (via SST)

**Metrics:**
- No external metrics service (no Prometheus/CloudWatch)
- Balance snapshots recorded every scan loop for manual analysis

## CI/CD & Deployment

**Hosting:**
- AWS ECS Fargate (us-east-2 region, via SST v4)
- Container: Python 3.13-slim with uv, deployed from Dockerfile
- Service: Single ECS task (API + scanner both in one container) to save ~$9/month
- Load balancing: CloudFront (dashboard) + ALB (API)
- DNS: Cloudflare (pointed via `sst.cloudflare.dns()`)

**CI Pipeline:**
- Not integrated (no GitHub Actions/GitLab CI)
- Manual deployment: `pnpm sst:deploy` (uses `assume` + `direnv` for AWS credentials)
- Pre-commit hook: `scripts/pre-commit-check.sh` runs linting + formatting locally before push

## Environment Configuration

**Required env vars (local .env or SST secrets):**
- `KALSHI_API_KEY` — API key ID from Kalshi
- `KALSHI_PRIVATE_KEY` — RSA private key PEM (or `KALSHI_PRIVATE_KEY_PATH` to file)
- `API_TOKEN` — Bearer token for API/dashboard
- `DASHBOARD_PASSWORD` — Login password
- `DRY_RUN` — "true" for shadow trades, "false" for real
- `DATABASE_URL` — SQLite path (default: `sqlite:///predictions.db`)
- `DB_BACKUP_BUCKET` — S3 bucket name (optional; empty = no backups)
- `NEXT_PUBLIC_API_URL` — Dashboard API endpoint (e.g., `http://localhost:8000`)
- `API_FOOTBALL_KEY` — API-Football v3 key for soccer backtests

**Build-time env vars:**
- `CACHE_BUST` — Docker arg to bust build cache (set to current timestamp)

**Secrets location:**
- Local: `.env` file (gitignored)
- Production: SST secrets (set via `npx sst secret set KEY value`)
- Dashboard backend: Never exposes secrets to browser; server-side proxy injects Bearer token

## Webhooks & Callbacks

**Incoming:**
- None implemented — scanner pulls from Kalshi REST + WS

**Outgoing:**
- None implemented — no external notifications (email, Slack, etc.)

**Lifespan Hooks:**
- FastAPI lifespan context manager (`lifespan()` in `api.py`):
  - Startup: Download DB from S3, init schema, init soccer cache, spawn scanner loop
  - Shutdown: Upload final DB backup to S3

---

*Integration audit: 2026-04-30*
