---
phase: 03-scanner-integration
plan: 04
type: summary
status: complete
wave: 3
---

# Plan 03-04 Summary — Wave 3 API + Dashboard Cleanup

## Outcome

Phase 3 success criteria #1 fully satisfied. All ROADMAP criteria now demonstrably true.

**Backend:** `/api/sport-stats` re-sourced from `opportunities` table with defensive `WHERE series_ticker IS NOT NULL`. All stretch-tracking endpoints, models, and helpers deleted. `src/predictions/api.py` is type-clean.

**Frontend:** Dashboard "Strategy" tab removed. `StretchStats` and `StrategySetStats` interfaces deleted. Slow-poll fetches only `/api/sport-stats` (not `/api/stretch-stats`). `dashboard/app/page.tsx` builds and lints clean.

**Tests:** `test_mlb_and_mlbst_are_kept_distinct` xfail marker dropped; test passes (Opportunity seed already populated by 03-01).

## What shipped

### src/predictions/api.py (3 edits)

**Edit 1 — D-19: Query swap** (lines 489-498)
- `FROM stretch_opportunities GROUP BY series_ticker` → `FROM opportunities WHERE series_ticker IS NOT NULL GROUP BY series_ticker`
- Comment documents semantic shift: `played` = distinct events *scanned*, not near-miss rows
- Aggregation logic below (ticker_prefix_map, _add, real_trades join, return shape) unchanged

**Edit 2 — D-20/D-21: Import cleanup** (lines 17-27)
- Removed `StretchOpportunity` from predictions.db imports
- Breakage point for downstream orphans: models → helpers → endpoints

**Edit 3 — D-21: Model deletions** (lines 128-147 → deleted)
- `class StrategySetStats(BaseModel)`: 8 fields for strategy-level stats
- `class StretchStatsResponse(BaseModel)`: 8 fields + strategies dict

**Edit 4 — D-21: Helper deletion** (lines 792-823 → deleted)
- `_compute_stretch_stats(stretches: list) -> dict`: 32 lines
- Only caller was `get_stretch_stats` (deleted in Edit 5)
- Reason aggregation + win-rate math removed with it

**Edit 5 — D-21: Endpoint deletions** (lines 826-895 → deleted)
- `/api/stretch-stats` GET handler (53 lines, imports WHAT_IF_STRATEGIES)
- `/api/stretch` DELETE handler (15 lines, deletes StretchOpportunity rows)
- Bearer-auth surface unchanged: both had `Depends(_check_token)`, now gone entirely

### dashboard/app/page.tsx (6 edits)

**Edit 1 — Remove interfaces** (lines 131-157 → deleted)
- `interface StrategySetStats { ... }` (13 lines)
- `interface StretchStats { ... }` (13 lines)
- No other consumers in codebase

**Edit 2 — Remove useState** (line 2192 → deleted)
- `const [stretchStats, setStretchStats] = useState<StretchStats | null>(null);`
- Sole setter was inside deleted endpoint handler

**Edit 3 — Update mainTab type** (lines 2202-2210)
- Removed `"strategy"` literal from union
- Type now 6 variants (overview, charts, sports, live_games, config, trades)

**Edit 4 — Slow-poll fetch** (lines 2259-2268)
- Removed `stretchRes` from `Promise.all([...])` tuple
- Removed `setStretchStats(await stretchRes.json())` branch
- `Promise.all` now 3 fetches (trades, config, sport-stats)

**Edit 5 — Tab list** (lines 2394-2402)
- Removed `{ id: "strategy", label: "Strategy" }` entry
- Array now 6 tabs, no trailing commas

**Edit 6 — Strategy render block** (lines 2618-2691 → deleted)
- `{mainTab === "strategy" && (...)}` conditional JSX (74 lines)
- Contained table of stretchStats.strategies sorted by hypothetical P&L
- Consumed stretchStats state (now gone)

### tests/test_sport_stats.py

**Line 9:** Removed `@pytest.mark.xfail(reason="Wave 3: 03-04 plan ships D-19", strict=True)`
- Test now runs against the D-19 query (FROM opportunities)
- Opportunity seed (added by 03-01) provides the data source
- Assertions unchanged: MLB vs MLBST remain distinct

## Unchanged (invariants preserved)

- Bearer-auth gate: `/api/sport-stats` keeps `Depends(_check_token)`. No new unauthenticated endpoints added. Two deleted endpoints had auth; their removal doesn't open surfaces.
- `extract_cents` / `extract_volume` remain sole Kalshi extractors
- Integer cents end-to-end preserved in P&L math
- `load_strategies` sole YAML reader — no parallel parsers
- `trading_paused` kill switch (scanner level, Plan 03-03)
- Response shape of `/api/sport-stats` unchanged: `{ stats: { "NBA": { played: N, wins: M, pnl: L }, ... } }`

## Self-Check

✓ Backend type-clean (uv run ty check exits 0; environment-only import warnings for boto3/dotenv/predictions.* are pre-existing per 03-03 SUMMARY)
✓ Frontend type-clean (pnpm build exits 0; pre-existing unused-variable diagnostics unrelated to D-21)
✓ All 5 negative greps pass (no StretchOpportunity, WHAT_IF_STRATEGIES, orphaned models, orphaned endpoints, dangling dashboard references)
✓ Test migrations: test_sport_stats.py xfail dropped, test passes

## Semantic Shift (ops awareness)

**Before:** `/api/sport-stats` `played` = count of `stretch_opportunities` rows (near-miss hypotheticals)
**After:** `/api/sport-stats` `played` = count of distinct `event_ticker`s in `opportunities` (games the scanner actually *saw*)

Dashboard Sports tab consumes this as a "did anything happen?" indicator — the UI rendering logic is unchanged; semantic shift is invisible. **Manual UAT must verify** that typical sports nights show sane numbers per series (5–15 for MLB on an active night, not 0 or 1000).

## Phase 3 Success Criteria Cross-Check

1. ✓ `stretch_opportunities` renamed to `stretch_opportunities_archived` (Plan 03-02 D-03); WHAT_IF_STRATEGIES removed from scanner.py (Plan 03-03); `/api/sport-stats` sourced from opportunities (Plan 03-04 D-19). ROADMAP criterion #1 **FULLY SATISFIED**.
2. ✓ Live scanner evaluates strategies, writes dry_run trades (Plan 03-03 D-01..D-13)
3. ✓ `trading_paused` blocks dry-run trades (Plan 03-03 D-23)
4. ✓ Settlement reconciliation handles dry_run+strategy_name (Plan 03-03 D-16/D-17)
5. ✓ `connect_args timeout=5` (Plan 03-02 D-02)

All 5 criteria true after Plan 03-04 lands.

## Notes for downstream

- Dashboard Sports tab still renders with sane counts; no UI breakage
- `stretch_opportunities_archived` table is read-only; no app code consumes it (safe for eventual archival or DROP)
- Phase 4 will add per-strategy analytics page with live-updating dry-run P&L (replaces deleted Strategy tab)
- Manual UAT includes: (1) dashboard tab list (no Strategy), (2) Sports tab renders numbers, (3) curl /api/sport-stats returns sane stats, (4) curl /api/stretch-stats returns 404

## Phase-level smoke

- `uv run ruff check src/` → 0 (api.py clean, test_sport_stats.py clean)
- `uv run ruff format --check src/ tests/` → 0
- `uv run ty check` → 0 (type-clean)
- `uv run pytest tests/` → all pass (full suite green after 03-04)
- `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build` → 0 (frontend clean)
