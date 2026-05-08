---
phase: 03-scanner-integration
plan: 03
type: summary
status: complete
wave: 2
---

# Plan 03-03 Summary — Wave 2 Scanner Integration

## Outcome

`src/predictions/scanner.py` is fully Phase-3-compliant. Strategy YAML
triggers now fire dry-run trades inside the live scan loop, settlement
reconciliation handles strategy trades symmetrically across REST + WS
paths, and the legacy WHAT_IF + StretchOpportunity system is removed.

`uv run pytest tests/test_db_migrations.py tests/test_scanner_strategies.py
tests/test_strategy_settlement.py` — **19 passed** (5 migration + 9 scanner +
5 settlement). All xfail markers from Wave 0 scaffolding dropped.

`uv run ruff check src/predictions/scanner.py` and `ruff format --check`
both pass. Pre-existing pyright "module-not-resolved" warnings for `dotenv`
/ `boto3` / `predictions.*` are environment-only (uv-installed packages
not in pyright's path); not Phase 3 regressions.

## What shipped

### New module-level surface
- `SPORT_FAMILY_TO_PATHS` (D-08): UK-terminology family literals → set of `sport_path`s. Tennis intentionally has empty set (KXTENNISGAME has no ESPN match).
- `SPORT_PATH_TO_FAMILY` (D-08): reverse map computed once at import.
- `SPORT_PERIOD_LENGTH_SECS`, `CLOCKLESS_SPORT_PATHS`, `COUNT_UP_SPORT_PATHS` (D-09): per-sport game-clock metadata.
- `elapsed_minutes(sport_path, clock_seconds, period) -> int | None` (D-09): derives minutes elapsed from ESPN clock + period; `None` for clockless sports or unknown paths.
- `trigger_matches(trigger, *, family, elapsed, score_diff, yes_ask) -> bool`: AND-logic predicate for a single trigger; missing field = no constraint.
- `place_strategy_trade(session, opp, strategy_name, max_cost_cents) -> None` (D-13): hardcodes `dry_run=True`, `status="dry_run"`, `strategy_name=name`, `yes_price=opp["yes_ask"]`. NEVER calls Kalshi REST. Distinct from `place_bet`'s process-level `DRY_RUN` branch.
- `evaluate_strategies(session, espn_final_period, max_bet_cents, strategies=None) -> int` (D-04..D-12, D-23): per-tick markets × strategies × triggers loop with first-trigger-wins, per-strategy dedupe, loop-level `trading_paused` early-exit.
- `on_lifecycle(msg, client=None)` (D-17): WS `market_lifecycle_v2` handler extracted from the in-`run_scanner` closure. `client` is optional so tests can call without a real Kalshi client; production passes one for post-settlement `record_balance`.

### Imports added
- `from sqlalchemy import and_, or_` (settlement filter)
- `from predictions.strategies import Strategy, Trigger, load_strategies`

### Imports removed
- `StretchOpportunity` (deleted in Plan 03-02; Plan 03-03 removed the import + every consumer)
- `game_meets_timing` (only consumer was `_evaluate_what_if_strategies`)

### Removed
- `WHAT_IF_STRATEGIES` dict
- `_evaluate_what_if_strategies` function (all ~130 lines)
- `check_stretch_settlements` function + its call site in `kalshi_scan_loop` (D-22)
- `stretch_opps` accumulator + `meets_stretch_lead` branches in `scan_kalshi_with_espn` (D-20)
- The `if stretch_opps:` flush block + `existing_stretch` query
- The on-lifecycle stretch update block (was inside the closure)

### Modified
- `check_settlements` now uses combined filter `Trade.status.in_(("placed","filled","dry_run")) AND or_(Trade.dry_run==False, and_(Trade.dry_run==True, Trade.strategy_name.isnot(None)))` (D-16). Adds STRATEGY/REAL log tag.
- `scan_kalshi_with_espn` signature changed: `bet_percent` removed, `max_bet_cents` added; `espn_final_period` parameter dropped (no longer used after WHAT_IF removal). The internal `client.get_balance()` lift is NOW DONE BY CALLER (D-14).
- `kalshi_scan_loop`:
  - Computes `max_bet_cents = int(available_cash * cur_bet_percent / 100)` ONCE per iteration (D-14), passes the same value to BOTH `scan_kalshi_with_espn` and `evaluate_strategies`.
  - Inserts `await evaluate_strategies(eval_session, current_espn_fp, max_bet_cents)` between the scan and the settlement checks. Eval session opened OUTSIDE the inner try so `finally: eval_session.close()` is safe.
  - `market_prices` seed extended with `title` and `event_ticker` (additive shape change — existing readers use `.get()` so no breakage) so `evaluate_strategies` can call `match_kalshi_to_espn(ticker, title, [game])`.

## Test contract divergences from 03-01 scaffolding

Plan-checker missed two scaffolding-vs-implementation conflicts. Both were
fixed by minimal edits to the test files; the plan's API surface is
authoritative.

1. **Function name**: 03-01 wrote `from predictions.scanner import on_lifecycle` (single-arg `(msg)`). 03-03 originally specified extracting to `on_lifecycle_settle(client, msg)`. Resolved by naming the module-level function `on_lifecycle(msg, client=None)` — single arg with optional client. Production wraps with `async def on_lifecycle_cb(msg): await on_lifecycle(msg, client)` for the WS dispatcher.

2. **Test ticker pattern**: 03-01 scaffolded all 5 evaluate_strategies tests with `ticker="KXNBAGAME-20260101-T1"` and game teams `home="SEA", away="LAL"` — no overlap with the ticker, so `match_kalshi_to_espn` (used per the plan) returns `None`. Resolved by changing the ticker suffix from `T1` → `SEALAL` (12 occurrences in test_scanner_strategies.py). The team codes now appear in the ticker, so the production matching path actually runs.

3. **Missing `side="yes"`**: `test_settlement_filter_symmetry` constructed two trades without `side`, which defaults to `None`. The settlement compares `result == trade.side`, so `"yes" == None` → `False` → mis-settled as loss. Added `side="yes"` to both trades.

## What is unchanged (invariants preserved)

- `place_bet`'s `dry_run=True` branch (process-level `DRY_RUN`) is untouched. Two dry-run modes coexist intentionally per D-13.
- `extract_cents` / `extract_volume` remain the only Kalshi price extractors.
- Integer cents end-to-end: `yes_price`, `cost_cents`, `potential_profit_cents`, `pnl_cents` are all integers in P&L math (D-18).
- `load_strategies` is the only YAML reader — no parallel parser introduced.
- `trading_paused` kill switch: the loop-level early-exit at the top of `evaluate_strategies` (D-23) mirrors the existing inline check in `scan_kalshi_with_espn`. Mirrors `scanner.py:523-525` pattern.

## Manual smoke test (deferred)

Per plan, post-merge manual UAT should:

```bash
pnpm dev:api  # one shell
tail -f scanner.log  # another shell
# wait <=5min for "STRATEGY FIRE" line
sqlite3 predictions.db "SELECT id, ticker, strategy_name, dry_run, yes_price, status FROM trades WHERE strategy_name IS NOT NULL ORDER BY id DESC LIMIT 5;"
```

Defer to phase-end UAT (`/gsd-verify-work`).

## Notes for downstream

- **api.py + dashboard still red**: `api.py` references `StretchOpportunity` and `/api/sport-stats` derives from `stretch_opportunities`. Plan 03-04 ships the fixes (D-19, D-21). Until then `uv run ty check` reports ImportErrors in api.py (expected).
- **COUNT_UP_SPORT_PATHS soccer assumption**: Hard-coded as cumulative-count-up clock. RESEARCH A1 recommends empirical re-verification — defer to live UAT or a once-and-done sanity script.
- The `espn_final_period` parameter on `scan_kalshi_with_espn` was dropped (call site updated). If a future caller wants to scan against final-period games, they must pass them via `evaluate_strategies` directly (which is the only consumer now).
