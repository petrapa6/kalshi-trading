---
status: complete
phase: 03-scanner-integration
source: [03-01-SUMMARY.md, 03-02-SUMMARY.md, 03-03-SUMMARY.md, 03-04-SUMMARY.md]
started: 2026-05-04T00:00:00Z
updated: 2026-05-04T09:35:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: |
  Kill any running API server. Start fresh:

      pnpm dev:api

  Server boots without errors, idempotent migrations apply, GET
  http://localhost:8000/ returns {"status":"ok"}.
result: pass
evidence: |
  Background `pnpm dev:api` came up; `curl http://localhost:8000/`
  returned {"status":"ok"}. No `error|traceback|exception` lines in
  /tmp/claude/dev-api.log.

### 2. DB Schema Post-Migration
expected: |
  After boot:
    sqlite3 predictions.db ".tables"  → contains stretch_opportunities_archived,
                                         does NOT contain stretch_opportunities
    sqlite3 predictions.db "PRAGMA table_info(trades);" | grep strategy_name
                                         returns the column row
    sqlite3 predictions.db "SELECT name FROM sqlite_master WHERE
      type='index' AND name='ix_trades_strategy_name';"
                                         returns one row
result: pass
evidence: |
  ".tables" → opportunities, stretch_opportunities_archived, trades
              (stretch_opportunities ABSENT)
  PRAGMA → `19|strategy_name|VARCHAR|0||0`
  index  → ix_trades_strategy_name

### 3. Source-Level Cleanup Complete
expected: |
  Negative greps return zero hits:
    - WHAT_IF_STRATEGIES, StretchOpportunity, check_stretch_settlements,
      _evaluate_what_if_strategies in src/predictions/scanner.py
    - StretchOpportunity, /api/stretch-stats, /api/stretch", _compute_stretch_stats,
      class StretchStatsResponse, class StrategySetStats in src/predictions/api.py
    - StretchStats, StrategySetStats, stretchStats, stretch-stats, "strategy"
      tab id in dashboard/app/page.tsx
  Positive surface present in scanner.py: evaluate_strategies, on_lifecycle,
  elapsed_minutes, place_strategy_trade, trigger_matches, SPORT_PATH_TO_FAMILY.
result: pass
evidence: |
  All negative greps return zero hits. scanner.py defines async
  evaluate_strategies (L475), async on_lifecycle (L327), elapsed_minutes
  (L130), trigger_matches (L393), place_strategy_trade (L423),
  SPORT_PATH_TO_FAMILY (L91). api.py imports `from sqlalchemy import
  and_, or_` (L27) and uses `FROM opportunities WHERE series_ticker IS
  NOT NULL` (api.py:476-477). dashboard tab list has 6 entries; no
  "strategy" id.

### 4. /api/sport-stats endpoint serves opportunities-derived stats
expected: |
  curl -H "Authorization: Bearer $API_TOKEN" \
       http://localhost:8000/api/sport-stats
  → 200 OK
  → JSON shape: {"stats": {"<series_label>": {"played": int, "wins": int,
    "pnl": int}, ...}}
  → played counts are distinct event_tickers from opportunities table
    (sane numbers: 0–dozens per series, not thousands).
result: pass
evidence: |
  curl returned 200 with body `{"stats":{}}`. Shape correct (top-level
  `stats` object). Empty result is consistent with `SELECT COUNT(*)
  FROM opportunities` = 0 in this dev DB — no scanner activity yet
  means no series_ticker buckets to aggregate. The "sane numbers"
  semantic check requires live scanner traffic and is covered by
  Test 9 (live strategy fire).

### 5. /api/stretch-stats endpoint deleted (returns 404)
expected: |
  curl -H "Authorization: Bearer $API_TOKEN" \
       http://localhost:8000/api/stretch-stats
  → 404 Not Found
result: pass
evidence: HTTP 404 returned.

### 6. /api/stretch DELETE endpoint deleted (returns 404 or 405)
expected: |
  curl -X DELETE -H "Authorization: Bearer $API_TOKEN" \
       http://localhost:8000/api/stretch
  → 404 or 405
result: pass
evidence: HTTP 404 returned.

### 7. Dashboard tab list has no "Strategy" tab
expected: |
  Open http://localhost:3777 in browser. Tab bar shows exactly:
  Overview, Charts, Sports, Live Games, Config, Recent Trades.
  No "Strategy" tab.
result: pass
evidence: |
  User confirmed: 6 tabs visible, no "Strategy" tab. The
  "Strategy Backtest →" button above the tab bar is a separate Phase 2
  link to /backtest (page.tsx:2314-2317, href="/backtest"), unrelated
  to the deleted Phase 3 stretch-stats Strategy tab.

### 8. Dashboard Sports tab renders sane per-series stats
expected: |
  Click "Sports" tab. Per-series rows render with `played` numbers
  reflecting distinct events scanned (e.g., 5–15 for active sports
  on a typical night; 0 for off-night sports). No JS errors in console.
  No layout regression vs Phase 2.
result: pass
evidence: |
  User confirmed Sports tab renders cleanly against an empty
  `opportunities` table on this fresh dev DB. No layout regression
  flagged. Semantic shift (D-19: `played` now = distinct events
  scanned, not stretch_opportunities rows) noted for live-data
  validation in a future session with active scanner traffic.

### 9. Live scanner fires dry-run strategy trade
expected: |
  Tail scanner.log during a live game whose ticker matches a strategy
  family in strategies.yaml. Within ~5 minutes, log line:
    STRATEGY FIRE strategy=<name> ticker=<...> yes_price=<...>
  Then:
    sqlite3 predictions.db "SELECT id, ticker, strategy_name, dry_run,
      yes_price, status FROM trades WHERE strategy_name IS NOT NULL
      ORDER BY id DESC LIMIT 5;"
  → returns rows with strategy_name set, dry_run=1, status='dry_run'.
result: skipped
reason: |
  No live games at verification time (2026-05-04 09:33 local —
  GET /api/live-games returned {"games":[]}). User opted to skip
  rather than block-and-wait. Static surface verified in Test 3:
  evaluate_strategies, place_strategy_trade, on_lifecycle, and the
  D-13 hardcoded `dry_run=True` / `status="dry_run"` / `strategy_name`
  setter all exist. Unit tests `test_scanner_strategies.py` (9/9
  passing per 03-03 SUMMARY) cover the firing path with synthetic
  state. Live observation deferred to next session with active games.

### 10. trading_paused kill switch blocks new strategy trades
expected: |
  Set trading_paused=true via config CLI / DB. Wait one scan cycle.
  Count of strategy trades in DB stays constant — no new strategy_name
  rows inserted while paused. Set back to false; firing resumes.
result: skipped
reason: |
  Depends on Test 9 baseline (a strategy-fireable game in progress);
  same live-games blocker. D-23 loop-level early-exit verified in
  source: scanner.py:475+ (evaluate_strategies). Unit test
  `test_scanner_strategies.py::test_trading_paused_blocks_strategy_fire`
  passing per 03-03 SUMMARY. Live observation deferred.

## Summary

total: 10
passed: 8
issues: 0
pending: 0
skipped: 2

## Gaps

[none yet]
