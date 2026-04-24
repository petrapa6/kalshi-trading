# Spec — get-rich-slow

## Overview
A sports-market trading bot that scans Kalshi prediction markets, cross-references ESPN live game data, and places bets on nearly-over games where the outcome is ~certain (yes price ≥ 88–92¢).

## Architecture

- **`kalshi_client.py`**: Async REST + WebSocket client for Kalshi API v2
- **`scanner.py`**: Core scanning loop — polls ESPN & Kalshi, places bets, tracks settlements
- **`api.py`**: FastAPI backend — serves dashboard data, runs scanner in background
- **`db.py`**: SQLAlchemy models + config store (SQLite / configurable URL, backed up to S3)
- **`espn.py`**: ESPN scoreboard scraper, game matching logic
- **`dashboard/`**: Next.js front-end dashboard
  - Uses `dashboard/app/api/.../route.ts` proxy to securely inject `API_TOKEN` for unauthenticated browser fetches. All FastAPI backend endpoints are strictly authenticated via `Depends(_check_token)` except for the root health check.
  - Sport Stats Charts panel: pulls from `/api/sport-stats` — unique match counts from `stretch_opportunities` plus real P&L/wins from `Trade`.
- **Key API endpoints**:
  - `DELETE /api/stretch` — wipe all shadow tracking history remotely.
  - `GET /api/sport-stats` — per-sport aggregate stats (matches seen, wins, P&L).
  - `GET /api/histogram-trades` — optimised column-only query including `ticker` and `event_ticker`.
  - `GET /api/trades` — paginated recent trades query, deduplicates `error` state trades by event.
## Kalshi API Notes (as of 2026-03-16, API v3.10.0)

### Market object price format
All prices in Market REST responses are now **FixedPointDollars strings**:
- `yes_ask_dollars`: `"0.9200"` (was integer `yes_ask: 92`)
- `yes_bid_dollars`: `"0.9100"` (was integer `yes_bid: 91`)
- `volume_fp`: `"500.00"` (was integer `volume: 500`)

Use `extract_cents(d, "yes_ask")` and `extract_volume(d)` from `kalshi_client.py` for all price extraction. These fall back to old integer fields to remain compatible with WebSocket messages.

### Balance endpoint
`GET /portfolio/balance` still returns integer cents:
- `balance`: int (cents)
- `portfolio_value`: int (cents)

### Order creation
`POST /portfolio/orders` v2 requirements:
- Kalshi requires `yes_price` and `no_price` in **integer cents** (e.g. `99`), despite read endpoints now using string dollars.
- `type: "limit"` and `client_order_id` (uuid string) are strictly required.
- `time_in_force` validation uses abbreviations and requires exactly `"good_till_canceled"` (not `"gtc"` or `"good_till_cancel"`).
- Kalshi charges trading fees parsed from the response `order.fee` (or `order.fee_dollars`) via `extract_cents()`, stored in DB.

## Trading Strategy

1. ESPN confirms game is in final minutes (≤5 min remaining, final period)
2. Score lead meets minimum threshold per sport
3. Kalshi yes price ≥ configured minimum (default 92¢)
4. Market has sufficient volume (≥50 contracts)
5. No existing open position on same event
6. Trading is not paused via config (`trading_paused` == "false")

## Internal Price Convention
All prices stored in DB and passed between components are **integer cents** (0–100).
Only the Kalshi REST API boundary uses dollar strings — converted by extractors at ingest.
