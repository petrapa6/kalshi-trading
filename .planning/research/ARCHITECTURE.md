# Architecture Research — v1.2 Strategy Engine Integration

**Project:** Kalshi Trading Scanner
**Researched:** 2026-04-29
**Confidence:** HIGH — derived from reading actual codebase

---

## 1. strategies.yaml Loading

**Decision: Load once at startup, not hot-reloaded.**

Create `src/predictions/strategies.py` as the new module owning all strategy types and logic. Loading happens in the `lifespan` function in `api.py` (where `init_db()` and `KalshiClient` construction already live). Pass the parsed strategy list as a parameter into `run_scanner()` — do not use a module-level global (avoids the awkward import pattern `WHAT_IF_STRATEGIES` currently creates).

YAML file lives at repo root, path configurable via `STRATEGIES_PATH` env var. Missing file → log warning, proceed with empty list (degrades gracefully; real trading continues).

`strategies.py` owns:
- `Condition`, `ConditionSet`, `Strategy` Pydantic models
- `load_strategies(path) -> list[Strategy]`
- `evaluate_strategy(strategy, game, yes_ask) -> bool` — the OR-of-AND evaluator

Hot-reload deferred: open dry-run trades placed under a strategy that later changes definition would have mismatched state. Future-milestone problem.

---

## 2. Per-Strategy Dry-Run Trade Storage

**Decision: Extend `Trade` table with `strategy_name VARCHAR NULL`.**

One ALTER TABLE migration consistent with `_migrate_add_columns()` in `db.py`. No new table. No polymorphic inheritance.

NULL = default live/dry-run trade (backward compatible). strategy_name string = strategy-tagged dry-run. `GROUP BY strategy_name WHERE dry_run=true` covers all analytics queries.

Do NOT extend `StretchOpportunity` — it is being retired (STR-04). Its `hypothetical_count`/`pnl_cents` are post-hoc values with no actual API call; the new system writes real `Trade` rows.

Deduplication: at scan loop start, build `set[(event_ticker, strategy_name)]` from open `Trade` rows with `dry_run=True AND status IN ("placed","filled","dry_run")`.

---

## 3. Analytics API Shape

**Decision: REST polling every 10–15s. No SSE.**

The existing `[...path]/route.ts` proxy buffers every response via `await res.json()`. It cannot pass through a `text/event-stream` without a new proxy route. Per-strategy trade data updates at most once per 5s scan loop; 10-15s polling is adequate.

Two new endpoints:

**`GET /api/analytics/strategies`** — per-strategy summary with `pnl_curve` array (cumulative P&L over settled dry-run trades, ordered by `placed_at`). Returns all strategies defined in loaded YAML even if zero trades — avoids needing a separate "list strategies" endpoint.

**`GET /api/analytics/strategies/{strategy_name}/trades`** — paginated trade log for one strategy, same `TradeResponse` shape as `/api/trades` but filtered to `dry_run=True AND strategy_name=X`.

Keep as separate routes from `/api/trades` — existing trades endpoint is consumed by `page.tsx` and changes there have wider blast radius.

---

## 4. Impact on Existing Endpoints (STR-04)

| Endpoint | Impact |
|----------|--------|
| `GET /api/stretch-stats` | Imports `WHAT_IF_STRATEGIES` from `scanner.py` — **breaks** when that dict is removed. Update import to `strategies.py` or return empty. |
| `DELETE /api/stretch` | No-op on empty table after migration. Safe to leave. |
| `GET /api/sport-stats` | Derives "games seen" from `stretch_opportunities` via `COUNT(DISTINCT event_ticker)`. Goes to zero after STR-04. Fix: switch query to use `opportunities` table (same columns, written every loop). |
| `GET /api/config` | Unaffected. |

Scanner internals to remove: `_evaluate_what_if_strategies()`, `check_stretch_settlements()`, stretch block in `on_lifecycle()`, `stretch_opps` accumulation in `scan_kalshi_with_espn()`. The `on_lifecycle` handler needs a new settlement block for `dry_run=True AND strategy_name IS NOT NULL` trades.

**Historical data preserved:** `stretch_opportunities` table rows stay in DB as dead storage (SQLite can't reliably DROP COLUMN anyway). No migration of old rows to `Trade` needed.

---

## 5. Suggested Build Order

```
Phase 1: Contract-based P&L math (BT-06)
  Files: dashboard/app/backtest/backtest.ts only
  Self-contained. Verifiable against known season data. No dependencies.

Phase 2: Strategy engine core (STR-01, STR-02, STR-03)
  Files: src/predictions/strategies.py (new), strategies.yaml (new),
         dashboard/app/backtest/backtest.ts (updated to use Strategy objects)
  Gate: backtest engine uses Strategy objects before wiring into live scanner.

Phase 3: DB migration + scanner integration (STR-04, DRY-01, DRY-02)
  Files: src/predictions/db.py, src/predictions/scanner.py, src/predictions/api.py
  Depends on: Phase 2 (Strategy type must exist)
  Includes: strategy_name column, remove WHAT_IF_STRATEGIES + stretch_opportunities writes,
            update /api/stretch-stats import, fix /api/sport-stats table reference,
            settlement reconciliation for strategy dry-run trades.

Phase 4: Analytics API + dashboard page (DASH-03, DASH-04)
  Files: src/predictions/api.py (new endpoints), dashboard/app/analytics/page.tsx (new)
  Depends on: Phase 3 (strategy_name must be in Trade rows to have data to display)
```

---

## 6. Component Boundaries

| Component | Owns | Does NOT own |
|-----------|------|-------------|
| `strategies.py` (new) | Pydantic models, YAML loading, condition evaluation | DB, scanner state, market prices |
| `scanner.py` | Asyncio loops, market price cache, orchestration | Strategy definitions, condition logic |
| `db.py` | Schema, migrations, config KV | Business logic |
| `api.py` | HTTP routing, auth, lifespan, analytics aggregation | Scanner state (read via DB only) |
| Analytics page | Polling, charts, trade log display | Backend queries |

---

## 7. Critical Risk: Kalshi Dry-Run API Behavior

The current `place_bet(dry_run=True)` in `scanner.py` does NOT call the Kalshi API at all — it writes a DB row and returns `{"dry_run": True}`. DRY-01 says the scanner should "place dry-run orders via Kalshi API per each defined strategy (real API calls, dry_run=True flag)."

**Verify whether `POST /portfolio/orders` accepts a `dry_run` parameter before Phase 3.** If it does not, "real API call with dry_run=True" is not achievable — the current behavior (skip API, write DB row) is the correct implementation of DRY-01. The requirement needs clarification.

---

## Open Questions

1. Does `POST /portfolio/orders` accept a `dry_run` flag, or must dry-run trades be DB-only?
2. Should `strategies.yaml` be committed to the repo (versioned) or mounted at deploy time?
3. Should analytics page show strategies no longer in the loaded YAML (historical trades from renamed/deleted strategies)?
