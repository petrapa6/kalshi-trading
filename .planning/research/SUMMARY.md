# Research Summary — v1.2 Strategy Engine

**Project:** Kalshi Trading Scanner
**Synthesized:** 2026-04-29
**Confidence:** HIGH

---

## Executive Summary

v1.2 replaces the hardcoded `WHAT_IF_STRATEGIES` dict and `stretch_opportunities` shadow-betting system with a YAML-driven strategy engine. Strategies are defined as OR-of-AND trigger conditions in `strategies.yaml`, loaded once at startup, and evaluated per scan loop. Each strategy fires dry-run trades (stored as `Trade` rows with `strategy_name` set and `dry_run=True`) so performance can be tracked before any strategy goes live. An analytics dashboard page completes the feedback loop.

**Recommended build order:** (1) fix contract-based P&L math in backtest, (2) build `strategies.py` and validate against backtest data, (3) wire into scanner + DB migration + remove stretch system, (4) analytics API + dashboard page.

**Dominant risk:** Kalshi API has no `dry_run` order flag — DRY-01 must be clarified before Phase 3 begins.

---

## Stack Additions

- **`pyyaml>=6.0.2`** (Python) — parse `strategies.yaml` at startup; Pydantic v2 is already in `uv.lock`
- **`strategy_name VARCHAR NULL`** column on `trades` table — one `ALTER TABLE` via `_migrate_add_columns()`
- **No new JS dependencies** — recharts + `setInterval` polling at 15s covers analytics page
- **SSE is not feasible** — `[...path]/route.ts` proxy buffers full JSON responses, cannot forward event streams

---

## Feature Table Stakes

### Strategy YAML Schema (OR-of-AND)

```yaml
strategies:
  - name: early_soccer_blowout
    label: "Early Soccer Blowout"
    enabled: true
    triggers:
      - sport: soccer          # AND: all fields must pass
        min_lead: 3
        min_minute: 65
        min_yes_price: 90
      - sport: soccer          # OR: any trigger block can fire
        min_lead: 2
        min_minute: 80
        min_yes_price: 92
```

Per-trigger fields: `sport`, `min_yes_price`, `max_yes_price`, `min_lead`, `lead_pct`, `min_minute`, `max_countdown_secs`, `series_ticker`. Missing field = no constraint (pass-through).

### Contract-Based P&L Math (BT-06)

```
contracts  = floor(stake_cents / price_cents)
win profit = contracts × (100 − price_cents)
loss       = −contracts × price_cents
```

Removes `avg_win_yield` slider from backtest UI — yield is derived from price, not a user input.

### Analytics Page Must-Haves

- Strategy selector (tabs or dropdown)
- Cumulative P&L line chart (recharts `LineChart`, x = `placed_at`, y = running P&L sum)
- Summary stat cards: total trades, wins, losses, win rate, realized P&L, open positions
- Trade log table: date, ticker, price, contracts, P&L, status
- 15s auto-refresh via `setInterval` + `useEffect`
- Auth gate via `checkAuth()`

### Defer to v2+

Sharpe ratio, max drawdown, multi-strategy overlay charts, CSV export, hot-reload of `strategies.yaml`, per-strategy `bet_percent` override, editable config in UI.

---

## Architecture Guidance

### New Module: `src/predictions/strategies.py`

Owns Pydantic models (`Condition`, `Strategy`, `StrategiesConfig`), `load_strategies(path)`, and `evaluate_strategy(strategy, game, yes_ask) -> bool`. Stateless — no DB or market-price imports.

### Load Point

`lifespan` in `api.py` loads strategies at startup alongside `init_db()` and `KalshiClient` construction. Passes list into `run_scanner()` as a parameter (no module-level global).

### New API Endpoints

- `GET /api/analytics/strategies` — per-strategy aggregate stats + P&L curve; includes strategies with zero trades
- `GET /api/analytics/strategies/{name}/trades` — paginated trade log, filtered `dry_run=True AND strategy_name=X`

### STR-04 Side Effects to Catch

| Affected Endpoint | Issue | Fix |
|-------------------|-------|-----|
| `GET /api/stretch-stats` | Imports `WHAT_IF_STRATEGIES` from `scanner.py` — breaks when removed | Update import to `strategies.py` or return empty |
| `GET /api/sport-stats` | Counts distinct tickers from `stretch_opportunities` — goes to zero | Switch to `opportunities` table |

### Build Order

```
Phase 1: BT-06 — contract math in backtest.ts (self-contained, no dependencies)
Phase 2: STR-01 + STR-02 + STR-03 — strategies.py + strategies.yaml + backtest integration
Phase 3: STR-04 + DRY-01 + DRY-02 — DB migration + scanner wiring + stretch removal
Phase 4: DASH-03 + DASH-04 — analytics API endpoints + dashboard page
```

---

## Critical Pitfalls

### 1 — Kalshi has no `dry_run` API flag [Critical — DRY-01]

`POST /portfolio/orders` accepts no `dry_run` parameter. "Real API calls, dry_run=True flag" is unimplementable as written. Options:
- **(a) Local simulation** — existing behavior, DB row written, no API call (recommended, zero cost)
- **(b) Kalshi demo environment** — separate `BASE_URL` + credentials, real API calls

**Must be resolved before Phase 3 begins.**

### 2 — `DRY_RUN=false` causes real strategy orders [Critical — DRY-01]

`DRY_RUN` env var flows from `api.py` → `run_scanner()` → `place_bet()`. In production with `DRY_RUN=false`, strategy-evaluated orders would be real-money orders. Strategy evaluation path must hardcode `dry_run=True` unconditionally, regardless of process-level flag.

### 3 — Settlement reconciliation excludes dry-run trades [Critical — DRY-02]

`check_settlements()` filters `Trade.dry_run == False`. Strategy trades (`dry_run=True`) never receive P&L — analytics P&L curve stays flat. DRY-02 must add a parallel settlement path targeting `dry_run=True AND strategy_name IS NOT NULL`.

### 4 — STR-04 must RENAME, not DROP [Critical — STR-04]

```sql
ALTER TABLE stretch_opportunities RENAME TO stretch_opportunities_archived;
```

`DROP TABLE` is irreversible; S3 backup overwrites every 30 minutes. Test migration against a copy of the S3 backup before deploying.

### 5 — YAML schema drift: backtest vs scanner field names [High — STR-01]

Backtest uses `minute`/`goal_diff` (soccer); scanner uses `clock_seconds`/`score_diff` (all sports). Condition fields must be sport-scoped, or a translation layer must map between contexts. Design the vocabulary explicitly in STR-01 before any code.

### 6 — SQLite busy timeout is 0ms [Moderate — DASH-04]

No `timeout` in `connect_args`. Analytics polling from multiple tabs + scanner writes every 5s = immediate `SQLITE_BUSY` / 500 errors. Fix: add `"timeout": 5` to `connect_args` in `db.py`. Poll analytics at 10–15s minimum.

### 7 — OR-of-AND edge cases [High — STR-02]

- Empty AND-set: `all([]) == True` fires on everything → `min_length=1` in Pydantic + explicit length check
- Boundary exactness: `min_minute >= 75` must fire at minute 75, not 76
- Write unit tests before scanner integration

---

## Open Questions

1. **DRY-01:** Local simulation (current behavior) or Kalshi demo environment? *(Must resolve before Phase 3)*
2. **`strategies.yaml` deployment:** Commit to repo (simple, versioned) or mount via S3 at container start?
3. **Historical stretch data:** After `RENAME TO stretch_opportunities_archived`, old rows are orphaned. Is historical data loss for the analytics page acceptable?
4. **Orphaned strategy names:** If a strategy is renamed/deleted from YAML, its historical `Trade` rows reference a name no longer in the config. How should the analytics endpoint handle these?

---
*Ready for requirements: yes*
