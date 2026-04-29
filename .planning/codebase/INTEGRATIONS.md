---
title: INTEGRATIONS
focus: tech
last_mapped: 2026-04-29
last_mapped_commit: f2c2f78
---

# External Integrations

The system depends on four external services for data and one for storage. Each is encapsulated in a single Python module so the rest of the codebase doesn't see protocol details.

## Map

| Integration | Direction | Module / file | Auth | Notes |
|---|---|---|---|---|
| Kalshi REST v3.10 | outbound | `src/predictions/kalshi_client.py` (`KalshiClient`) | RSA-PSS-signed headers per request | Markets, events, orders, balance |
| Kalshi WebSocket v2 | outbound (persistent) | `src/predictions/kalshi_client.py` (`KalshiWebSocket`) | RSA-PSS-signed handshake | Live ticker + `market_lifecycle_v2` |
| ESPN scoreboards | outbound (read-only, undocumented) | `src/predictions/espn.py::get_scoreboard` | none | Polled every 10 s |
| API-Football v3 | outbound (read-only) | `src/predictions/soccer_cache.py::ApiFootballClient` | `x-apisports-key` header | Backtest historical match data; rate-limited (free tier 100/day, 30/min) |
| AWS S3 | outbound | `src/predictions/api.py::_download_db`, `_backup_db_sync`; `src/predictions/scanner.py::backup_db` | IAM via SST link to `DbBackups` bucket | DB snapshots every ~30 min + restore on container start |
| AWS / Cloudflare (deploy) | infra | `sst.config.ts` | SST + `assume` for AWS profile | Cluster, Vpc, S3, Cloudflare DNS |

## Inbound HTTP

The FastAPI app (`src/predictions/api.py`) is the only inbound surface:

- Public health: `GET /` → `{"status":"ok"}` (no auth — `src/predictions/api.py:269-271`).
- Everything else is protected by `_check_token` (`src/predictions/api.py:258-267`), a `Depends`-based Bearer-token check against `os.getenv("API_TOKEN")`.
- CORS allows `http://localhost:3777`, `http://localhost:3000`, plus the comma-separated `CORS_ORIGINS` env (`src/predictions/api.py:248-256`).

Endpoints (all `Depends(_check_token)` unless noted):

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/stats` | Aggregate trade stats |
| GET | `/api/trades?limit&offset` | Paginated trades |
| GET | `/api/histogram-trades?limit` | Bulk trades for histograms |
| GET | `/api/sport-stats` | Per-sport breakdown |
| GET | `/api/opportunities?limit&offset` | Recent opportunities (incl. near-misses) |
| GET | `/api/balance-history?limit` | Balance snapshots |
| GET | `/api/scans?limit` | Scan loop telemetry |
| GET | `/api/live-games` | Live game state (joins ESPN + Kalshi market) |
| GET | `/api/stretch-stats` | Backtested what-if strategies |
| DELETE | `/api/stretch` | Wipe `stretch_opportunities` |
| GET | `/api/config` | Runtime config (DB) |
| PUT | `/api/config` | Update one config key |
| DELETE | `/api/config` | Reset all config to defaults |
| POST | `/api/backtest/soccer` | Run a soccer backtest (`BacktestRequest` → `BacktestResponse`) |

## Kalshi (REST + WebSocket)

`src/predictions/kalshi_client.py` is the **single drift point** between Kalshi's wire format and the rest of the codebase.

- Base URL `https://api.elections.kalshi.com`, path prefix `/trade-api/v2`.
- Auth: every request is signed by an RSA-PSS signature over `<timestamp_ms> + <method> + <path>`, base64-encoded into `KALSHI-ACCESS-SIGNATURE`. Key is loaded from PEM in `from_key_file` or `from_key_string` (`src/predictions/kalshi_client.py:54-71`).
- Price normalization: `extract_cents(d, prefix)` (lines 19-27) reads `<prefix>_dollars` (string, e.g. `"0.9200"`) and rounds to integer cents; falls back to legacy integer `<prefix>` if present. `extract_volume` (lines 30-38) does the same via `volume_fp`. **Internal code only ever sees integer cents.**
- WebSocket: `KalshiWebSocket` (line 209) connects to `wss://api.elections.kalshi.com/trade-api/ws/v2`. Subscriptions used by the scanner: `ticker` and `market_lifecycle_v2` (`src/predictions/scanner.py:894-906`). Reconnection / resubscribe handled in `ws_loop` inside `run_scanner`.
- Order placement: `POST /portfolio/orders` still takes integer `yes_price`/`no_price` despite reads being dollar strings — see `src/predictions/scanner.py::place_bet` (line 127).

## ESPN

`src/predictions/espn.py`. Undocumented public scoreboard:

`https://site.api.espn.com/apis/site/v2/sports/<sport_path>/scoreboard`

- `KALSHI_TO_ESPN` map (lines 16-29) connects Kalshi series tickers (e.g. `KXNBAGAME`) to ESPN sport paths (e.g. `basketball/nba`).
- `SPORT_FINAL_PERIOD` (lines 31-44) tells the scanner which period number is "final" per sport (4 for NBA, 9 for MLB, etc).
- `get_scoreboard(sport_path)` returns a `list[GameState]` (`espn.py:104`).
- `match_kalshi_to_espn(ticker, game)` (line 232) is the fuzzy team-abbrev matcher.
- No auth, no rate-limit hint — caller's only protection is the 10 s polling cadence.

## API-Football v3 (soccer backtest)

`src/predictions/soccer_cache.py`. Used only by the `/api/backtest/soccer` endpoint via `src/predictions/backtest.py`.

- Base URL `https://v3.football.api-sports.io`, header `x-apisports-key: <API_FOOTBALL_KEY>`.
- Free-tier limits: 100 requests/day, 30/min. The client raises `RateLimitedError` on HTTP 429 (`soccer_cache.py:96`).
- Cache: a separate SQLite at `SOCCER_CACHE_DB_PATH` (default `./soccer-cache.db`, `/tmp/soccer-cache.db` in production via SST). Tables `soccer_matches`, `soccer_goals` defined at `soccer_cache.py:36-61`.
- Provider was swapped from football-data.org to API-Football on branch `feat/soccer-backtest` (commits `e82a4c4`, `2e0c2c5`, `86604b4`, `cb60e60`, `f2c2f78`). The new provider supports batched fixture-detail calls (up to 20 ids per request).

## S3 backups (durability)

The production SQLite lives at `/tmp/predictions.db` (ECS task-local, lost on restart), so durability is provided by S3 snapshots.

- Bucket name comes from env `DB_BACKUP_BUCKET` (set by SST link to `DbBackups`).
- `src/predictions/scanner.py::backup_db` (line 747) copies the DB to a tmp file (so SQLite isn't read mid-write), then uploads to `s3://<bucket>/backups/YYYY-MM-DD/HHMM-predictions.db` and overwrites `backups/latest.db`.
- The backup loop runs every ~30 minutes (interval inside `run_scanner`).
- On startup, `_download_db()` (`src/predictions/api.py:176`) restores from `backups/latest.db` before `init_db()` runs.
- `_backup_db_sync()` (`src/predictions/api.py:192`) also runs in the lifespan `finally` to flush on graceful shutdown.

## Auth Surfaces (summary)

| Caller | Credential | Where it's read |
|---|---|---|
| Dashboard browser → Next.js | Password cookie (sha256 of `DASHBOARD_PASSWORD + "salt123"`) | `dashboard/app/actions.ts` (`login`, `checkAuth`) |
| Next.js server → API | `Authorization: Bearer ${API_TOKEN}` | `dashboard/app/api/[...path]/route.ts:18-21` and `dashboard/app/actions.ts::updateConfig` |
| CLI → API | `Authorization: Bearer <token>` (env `API_TOKEN` or `--token`) | `cli/src/api.ts` |
| API → Kalshi | RSA-PSS signature header | `src/predictions/kalshi_client.py::_sign` |
| API → ESPN | none | n/a |
| API → API-Football | `x-apisports-key` | `src/predictions/soccer_cache.py::ApiFootballClient` |

The browser **never** sees `API_TOKEN`; the dashboard server-side proxy at `dashboard/app/api/[...path]/route.ts` injects it.
