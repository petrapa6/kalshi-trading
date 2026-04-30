---
last_mapped: 2026-04-30
last_mapped_commit: d010a403e3997670cdce46c100b8d39438c4783d
---

# Architecture

**Analysis Date:** 2026-04-30

## System Overview

```text
┌─────────────────────────────────────────────────────────────────┐
│  Clients (Dashboard + CLI)                                       │
│  `dashboard/app/page.tsx` (Next.js SPA)                         │
│  `cli/src/index.tsx` (React-ink TUI)                            │
└────────────────────┬────────────────────────────────────────────┘
                     │ HTTP Bearer token
                     ▼
┌─────────────────────────────────────────────────────────────────┐
│  FastAPI Application Layer                                      │
│  `src/predictions/api.py` — Health, stats, trades, config       │
│  Endpoints: /api/stats, /api/trades, /api/config, /api/backtest │
│  Bearer token validation on all mutating operations             │
└─────┬───────────────────────────┬───────────────────────────────┘
      │                           │
      │                     ╔═════╩═════╗
      │                     │ Startup   │
      │                     ║(lifespan) ║
      │                     ╚═════╦═════╝
      │                           ▼
      │                    Download DB from S3
      │                    Init SQLite schema
      │                    Load Kalshi credentials
      │                    Spawn run_scanner task
      ▼                           ▼
┌──────────────────────────────────────────────────────────────────┐
│  Scanner (Four Concurrent Async Loops)                          │
│  `src/predictions/scanner.py::run_scanner`                      │
├─────────────────────┬─────────────────┬──────────┬────────────┤
│ espn_loop           │ kalshi_loop     │ ws_loop  │backup_loop │
│ 10s refresh         │ 5s scan+trade   │ Listen   │ 30m backup │
│ ESPN live state     │ Market matching │ Lifecycle│ DB → S3    │
└─────────┬───────────┴────────┬────────┴──────────┴────────────┘
          │                    │
          ▼                    ▼
    ┌─────────────┐    ┌──────────────────┐
    │ ESPN REST   │    │ Kalshi REST v3.10│
    │ scoreboards │    │ events, markets, │
    │ (live games)│    │ orders, balance  │
    └─────────────┘    └──────────────────┘
                            │
                            ▼ (real-time prices + settlement)
                    ┌──────────────────┐
                    │ Kalshi WebSocket │
                    │ ticker updates   │
                    │ market_lifecycle │
                    └──────────────────┘
                            │
                    ╔═══════╩════════╗
                    ▼                ▼
            ┌─────────────┐  ┌──────────────┐
            │ market_      │  │ on_lifecycle │
            │ prices dict │  │ settlement   │
            │ (real-time) │  │ handler      │
            └─────────────┘  └──────────────┘
                    │                │
                    └────────┬───────┘
                             ▼
            ┌───────────────────────────────────┐
            │  SQLite trades+opportunities+      │
            │  stretch_opportunities+config      │
            │  `src/predictions/db.py`           │
            └───────────────────────────────────┘
                             │
                             ▼ (30m backups)
                    ┌──────────────────┐
                    │ S3 DbBackups     │
                    │ Durability layer │
                    └──────────────────┘
```

## Component Responsibilities

| Component | Responsibility | File |
|-----------|----------------|------|
| **FastAPI app** | HTTP endpoints (stats, trades, config, backtest); Bearer token validation | `src/predictions/api.py` |
| **run_scanner** | Four-loop orchestration; ESPN polling; Kalshi discovery; WebSocket lifecycle handling; trade settlement | `src/predictions/scanner.py` |
| **KalshiClient** | RSA-signed REST API calls; rate limiting; price extraction from string/integer formats | `src/predictions/kalshi_client.py` |
| **KalshiWebSocket** | Persistent WS connection; ticker updates; market_lifecycle_v2 events | `src/predictions/kalshi_client.py` |
| **ESPN data layer** | Live game state polling; team abbrev matching; final-minutes detection | `src/predictions/espn.py` |
| **SQLAlchemy models** | Trade, Opportunity, StretchOpportunity, Scan, BalanceSnapshot, ConfigEntry schemas | `src/predictions/db.py` |
| **Config K-V store** | Runtime tunable parameters (min_yes_price, leads by sport, final_seconds, trading_paused) | `src/predictions/db.py::get_config_int` |
| **Dashboard** | Read-only Next.js SPA; real-time stats, trade history, live game watch list | `dashboard/app/page.tsx` |
| **CLI** | React-ink TUI; config view/set; stats display; trade inspection | `cli/src/` |

## Pattern Overview

**Overall:** Event-driven polling + WebSocket listener architecture. Four async loops in one event loop, shared via:
- Module-level `market_prices` dict for real-time WS ticker updates
- SQLAlchemy `SessionLocal` session factory
- `asyncio.Lock` protecting ESPN cache during ESPN/Kalshi loop coordination

**Key Characteristics:**
- ESPN 10s poll → Kalshi discover/subscribe 5s → WS listen (primary settlement) + REST fallback (check_settlements every 5s)
- Integer cents everywhere internally; `extract_cents()` and `extract_volume()` are drift boundaries for Kalshi's string-based API
- Runtime config re-read every Kalshi scan loop (~5s) — no hardcoded tunables
- `trading_paused == "true"` is the kill switch; checked before every order placement
- Dry-run vs real trades distinguished by `Trade.dry_run` boolean and `DRY_RUN` env (process-level, not runtime-tunable)

## Layers

**Presentation (HTTP):**
- Purpose: Serve stats, trade history, config; accept config mutations; backtest endpoints
- Location: `src/predictions/api.py`
- Contains: FastAPI app, Pydantic response models, Bearer token validation
- Depends on: SQLAlchemy session factory, KalshiClient (global), logging
- Used by: Dashboard (`dashboard/app/page.tsx`), CLI (`cli/src/`), curl/scripts

**Scanning & Trading Logic:**
- Purpose: Poll ESPN, discover Kalshi markets, match games to markets, place bets, settle trades
- Location: `src/predictions/scanner.py`
- Contains: Four async loops (`espn_loop`, `kalshi_scan_loop`, `ws_loop`, `backup_loop`), bet placement, settlement logic, what-if strategy backtesting
- Depends on: KalshiClient, ESPN API, SQLAlchemy, `get_config_int()`
- Used by: API lifespan spawns as background task

**Data Access (SQLAlchemy ORM):**
- Purpose: Persistent schema; transaction management; K-V config store
- Location: `src/predictions/db.py`
- Contains: Model classes (Trade, Opportunity, StretchOpportunity, Scan, BalanceSnapshot, ConfigEntry), session factory, schema migrations, config helpers
- Depends on: SQLite file path from `DATABASE_URL` env
- Used by: api.py, scanner.py

**External APIs:**
- **Kalshi REST:** `src/predictions/kalshi_client.py::KalshiClient._get/_post` — RSA-signed requests, rate limiting (100ms between calls)
- **Kalshi WebSocket:** `src/predictions/kalshi_client.py::KalshiWebSocket` — Persistent connection, ticker + market_lifecycle_v2 events
- **ESPN:** `src/predictions/espn.py::get_scoreboard` — Async httpx call to ESPN undocumented scoreboards API

## Data Flow

### Primary Request Path (Happy Path)

Full sequence diagram in `CLAUDE.md` "Trading data flow" section. Summary:

1. **ESPN poll (10s):** `espn_loop()` calls `get_categorized_games()` → updates `espn_cache` dict
2. **Kalshi discover (5s):** `kalshi_scan_loop()` fetches open events/markets for active sports → discovers new tickers → subscribes via WS
3. **Market price updates (real-time):** `on_ticker` handler receives WS ticker msgs → updates module-level `market_prices` dict
4. **Match & evaluate (5s):** `kalshi_scan_loop()` calls `scan_kalshi_with_espn()` → matches each open Kalshi market to ESPN game → checks filters (yes_ask ≥ min_price, score_lead ≥ min_lead, in final minutes) → calls `place_bet()`
5. **Order placement:** `place_bet()` creates `Trade` row with `status="placed"` → calls `client.create_order()` → logs fee
6. **Settlement (real-time via WS primary, 5s REST fallback):**
   - **WS path:** `on_lifecycle` handler receives `market_lifecycle_v2` with `status="finalized"` → updates Trade/StretchOpportunity with final status + P&L
   - **REST path:** `check_settlements()` called every Kalshi loop iteration as backstop if WS missed event

### Settlement Duality

Two paths to settle the same market:

```mermaid
sequenceDiagram
    participant W as Kalshi WS
    participant S as Scanner
    participant DB as SQLite
    participant R as REST Check
    
    W->>S: market_lifecycle_v2 ticker=X status=finalized result=yes
    S->>S: on_lifecycle handler fires (fast, usually 1-2s after settlement)
    S->>DB: UPDATE Trade ticker=X status=settled_win pnl_cents=...
    S->>DB: UPDATE StretchOpportunity ticker=X status=settled_win pnl_cents=...
    
    Note over S,DB: 5 seconds later...
    R->>S: check_settlements() poll
    R->>DB: SELECT * FROM trades WHERE status=placed
    alt Market already settled via WS
        R->>R: on_lifecycle already updated it; skip
    else WS missed (rare)
        R->>DB: UPDATE Trade status=settled_win/loss
    end
```

**Why duality matters:**
- WS is the fast path (real-time) but can miss events (network glitch, reconnect during settlement)
- REST fallback ensures no trade is left orphaned in "placed" status forever
- P&L calculation differs slightly: WS uses `on_lifecycle` result field; REST fetches market status again

### Config Re-read Loop

Every Kalshi scan iteration:
1. `cur_price = get_config_int("min_yes_price")` → reads SQLite `config` table
2. `cur_lead = get_config_int(f"lead:{sport_path}")` → sport-specific override or fallback to `MIN_SCORE_LEAD` dict
3. `final_secs = get_config_int(f"final_seconds:{sport_path}")` → clock threshold per sport

Runtime config changes (via `/api/config` endpoint or CLI) take effect within ~5 seconds.

### What-If Strategy Evaluation

Parallel to real trading, `_evaluate_what_if_strategies()` runs on final-period games against 5 parameter sets:
- `low_price`: min_ask=90c (vs real 92c)
- `loose_leads`: lead_pct=50 (vs real 100)
- `early_entry`: countdown_secs=600 (vs real 300)
- `yolo`: all loose (85c, 50% lead, early)
- `default`: near-miss bucket for games that missed exactly one filter

Results feed `StretchOpportunity` table with `strategy_set` label and hypothetical P&L to backtest parameter relaxations on live data.

## Key Abstractions

**GameState (`src/predictions/espn.py`):**
- Purpose: Wrap ESPN raw game JSON into typed object with convenience properties
- Properties: `is_live`, `is_final_period`, `is_in_final_minutes`, `score_diff`, `leading_team`
- Encapsulates period/clock logic per sport (baseball has no clock, soccer counts up, others count down)

**Trade Model (`src/predictions/db.py`):**
- Status flow: `placed` → (`filled` or `placed`) → (`settled_win` | `settled_loss` | `error` | `dry_run`)
- P&L computed at settlement: `pnl_cents = potential_profit_cents - fee_cents` (win) or `-cost_cents - fee_cents` (loss)
- Dry-run trades: `dry_run=True`, `status="dry_run"`, excluded from stats aggregation

**StretchOpportunity Model (`src/predictions/db.py`):**
- Records near-miss markets + what-if strategies for backtesting
- Fields: `reason` (price|score_lead|timing), `strategy_set` (name), `hypothetical_count`, `side` (always yes today)
- Dedupe key: `(ticker, strategy_set)` — only first sighting of each market under each strategy recorded
- Hypothetical P&L calculated same as real trades: `(100 - yes_ask) * hypothetical_count` (win) or `-(yes_ask * hypothetical_count)` (loss)

**KalshiClient (`src/predictions/kalshi_client.py`):**
- RSA signature generation on every API call (timestamp + method + path)
- Rate limiting: 100ms between any two API calls (enforced by `_rate_limit()`)
- Price extraction: `extract_cents()` handles both old integer fields and new FixedPointDollars strings from v3.10

**KalshiWebSocket (`src/predictions/kalshi_client.py`):**
- Event-driven callback registration: `.on("ticker", callback)` and `.on("market_lifecycle_v2", callback)`
- Subscription management: `.subscribe()` and `.update_subscription()` for dynamic ticker lists
- Auto-reconnect on failure (caught by `ws_loop()`)

## Entry Points

**API startup (`src/predictions/api.py::lifespan`):**
- Location: `src/predictions/api.py` lines 215–241
- Triggers: FastAPI app start
- Responsibilities: Download latest DB from S3, initialize schema, load Kalshi credentials, spawn `run_scanner()` task

**Scanner task (`src/predictions/scanner.py::run_scanner`):**
- Location: `src/predictions/scanner.py` lines 779–1019
- Triggers: API lifespan
- Responsibilities: Initialize DB, load client, spawn four concurrent loops

**HTTP endpoints (`src/predictions/api.py`):**
- `/api/stats` — Aggregated P&L, win rate, open positions
- `/api/trades` — Recent settled/placed trades with pagination
- `/api/config` — Get/set K-V config
- `/api/backtest/{sport}` — Backtest soccer strategies
- `/` — Health check

**CLI entry (`cli/src/index.tsx`):**
- Meow arg parsing → routes to config/stats/trades view
- Requires `API_TOKEN` env or `--token` flag
- Calls API with Bearer auth

**Dashboard entry (`dashboard/app/page.tsx`):**
- Next.js `/page.tsx` — Single SPA component (102 KB, known maintainability concern)
- Proxies fetches via `/api/[...path]` server action to inject Bearer token server-side

## Architectural Constraints

- **Threading:** Single-threaded `asyncio` event loop. No thread pools. All concurrency is async/await. HTTP server and four scanner loops all in one event loop.
- **Global state:** 
  - Module-level `market_prices: dict[str, dict]` in `scanner.py` — shared between all four loops without locking (reads are atomic in CPython)
  - Global `_kalshi_client: KalshiClient | None` in `api.py` — instantiated once in lifespan, reused for all API endpoints and scanner
  - SQLAlchemy `SessionLocal` session factory — creates new sessions on demand; threads-safe with SQLite's `check_same_thread=False`
- **Circular imports:** `scanner.py` imports from `api.py` (to spawn task in lifespan) but doesn't use it; `api.py` imports from `scanner.py` (for MIN_SCORE_LEAD) but task is spawned via module import
- **Database durability:** SQLite file is ephemeral in Fargate container (`/tmp/predictions.db`); durability via S3 snapshots every 30 min; data-loss window up to 30 min on crash
- **Rate limiting:** Kalshi API enforces 100ms between calls; handled by `KalshiClient._rate_limit()` globally (not per-thread, so shared limit across scanner + API endpoints)
- **ESPN API:** Undocumented, hit every 10s; no rate limit observed in practice; may be fragile if ESPN changes endpoint structure

## Anti-Patterns

### Monolithic Dashboard Component

**What happens:** `dashboard/app/page.tsx` is a single 102 KB `"use client"` component doing auth, fetching, state management, charts, and tables in one file.

**Why it's wrong:** 
- No component reusability (charts are hardcoded into the page)
- Difficult to test individual features
- State management (auth, config form, tab switching) scattered throughout
- Hard to optimize rendering (entire page re-renders on any hook change)

**Do this instead:** Break `page.tsx` into sub-components (`<StatsPanel>`, `<ConfigForm>`, `<TradeTable>`, `<LiveGames>`), extract shared hooks (`useAuth`, `useFetch`), and organize by feature folder.

### Multiple Price Extraction Paths

**What happens:** `extract_cents()` and `extract_volume()` exist to handle both old integer and new string FixedPointDollars formats. But similar extraction logic may be duplicated in tests or adhoc queries.

**Why it's wrong:** API schema drift isn't isolated to one place; future maintainers may add another extraction path instead of using the canonical one.

**Do this instead:** Always use `extract_cents()` and `extract_volume()` for any Kalshi JSON. No exceptions. If you need raw prices, call the extraction functions explicitly.

### Configuration Hardcoding in Code

**What happens:** Default values like `MIN_SCORE_LEAD` dict and `WHAT_IF_STRATEGIES` are in `scanner.py` as fallbacks, but runtime config is in the DB. Some code checks the DB first; some doesn't.

**Why it's wrong:** Two sources of truth; unclear which takes precedence.

**Do this instead:** Always call `get_config_int(key)` first; use code defaults only as fallback if the key doesn't exist in the DB. Make this explicit: `db_value or code_default`.

## Error Handling

**Strategy:** Permissive logging + graceful degradation. No hard failures; every exception is caught at loop level and logged as warning.

**Patterns:**
- `espn_loop()`: ESPN API errors don't stop Kalshi scanning; old cache is reused
- `kalshi_scan_loop()`: Individual series errors (e.g., one sport offline) don't block others; loop continues after logging
- `on_lifecycle` handler: Settlement errors are logged but don't propagate; both WS and REST fallback handle failures independently
- `check_settlements()`: Market query errors don't crash; loop retries next iteration
- Order placement (`place_bet()`): API failures set `Trade.status = "error"`, logged, and excluded from stats

**Why:** Prediction markets are live 24/7; a few minutes of downtime in one component (e.g., ESPN API slow) shouldn't kill the entire scanner.

## Cross-Cutting Concerns

**Logging:**
- Python: `logging` module with `StreamHandler` (stdout) + `FileHandler` (scanner.log); no structured JSON logging
- TypeScript: `console` methods; no centralized logger
- Scanner logs are rotated via container restart (ECS Fargate)

**Validation:**
- Boundary: Kalshi API → `extract_cents()` / `extract_volume()` normalize formats
- Boundary: ESPN API → `GameState` validates sport_path exists in `KALSHI_TO_ESPN` mapping
- No schema validation framework (Pydantic for API responses only, not internal data)

**Authentication:**
- API: Bearer token in `Authorization` header; validated by `_check_token()` on every mutating endpoint
- Kalshi: RSA-signed requests; signature computed on-demand per call (no token cache)
- ESPN: No auth required (public API)
- Dashboard & CLI: Token held in env (`API_TOKEN`) or passed as flag; transmitted via HTTPS to proxy

---

*Architecture analysis: 2026-04-30*
