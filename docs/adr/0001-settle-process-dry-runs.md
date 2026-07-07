# 0001. Settle process dry-runs in both settlement paths

Date: 2026-07-07
Status: accepted

## Context

The D-16 composite settlement filter (`dry_run == False OR (dry_run == True
AND strategy_name IS NOT NULL)`) excluded process dry-runs from
`check_settlements` (REST) and `on_lifecycle` (WS). But the open-positions
count in `scan_kalshi_with_espn` used only `Trade.dry_run == dry_run`, so
process dry-runs entered the count and never left. With process-level
`DRY_RUN=true` (production mode during the dry-run milestone), the scanner
permanently hit `max_positions` after 20 fires and silently stopped placing
dry-run trades (issue #2).

Alternatives considered:

- Exclude process dry-runs from the open-positions count only. Minimal, but
  DRY_RUN mode would never exercise the `max_positions` cap and rows would
  sit at `status="dry_run"` forever.
- Remove the process-level DRY_RUN path. Deferred while the milestone is
  dry-run only.

## Decision

Both settlement paths settle every trade with status `placed`, `filled`, or
`dry_run` — no population filter. Process dry-runs get the full lifecycle:
`settled_win`/`settled_loss`, `pnl_cents`, `settled_at`, and they free
`max_positions` slots at settlement, mirroring real-money behavior.

`countable_trades()` (db.py) survives as the analytics-population predicate
only, used by the `/api/strategy-analytics` read paths. This narrows D-16:
its composite filter no longer gates settlement, only analytics.

## Consequences

- DRY_RUN mode simulates the full trade lifecycle and no longer self-clogs;
  stale `status="dry_run"` rows backfill-settle on the next
  `check_settlements` pass.
- Global `/api/stats` wins/losses/total P&L include settled process
  dry-runs (they already included strategy dry-run fires).
- Strategy analytics are unaffected: those endpoints filter on
  `strategy_name`, which is NULL for process dry-runs.
- `settle_trade` logs process dry-runs with the `REAL` tag (tag derives from
  `strategy_name` presence) — cosmetic, accepted.
