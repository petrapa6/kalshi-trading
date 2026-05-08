---
phase: 04-analytics-dashboard
plan: 01
subsystem: backend-api
tags:
  - fastapi
  - sqlalchemy
  - analytics-endpoints
  - dash-03

# Dependency graph
requires:
  - phase: 04-analytics-dashboard
    plan: 00
    provides: "tests/conftest.py::seed_trades helper; 7 xfail-marked stubs in tests/test_strategy_analytics.py"
  - phase: 03-scanner-integration
    provides: "Trade.strategy_name column (D-01); composite settlement filter dry_run==False OR (dry_run==True AND strategy_name IS NOT NULL) (D-16)"
provides:
  - "GET /api/strategy-analytics?strategy=<name> returning {stats, trades, pnl_curve}"
  - "GET /api/strategies-summary returning per-strategy mini-stats with YAML+DB merge (zero-trade strategies surfaced)"
  - "TradeResponse.strategy_name field exposing Phase 03 D-01 column on /api/trades JSON"
affects:
  - 04-02-implement-analytics-page
  - 04-03-cross-link-trades-page
  - dashboard/app/analytics/* (Wave 2 consumers)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "FastAPI Pydantic response model trio per endpoint (Stats / Trade / PnlPoint composed into Response)"
    - "Python-side cumulative running sum over settled rows (avoids SQLite version-dependent window functions per D-05)"
    - "YAML-first + DB-orphan merge pattern in /api/strategies-summary (D-11): YAML order preserved, then DB-only strategies appended"
    - "SQL CASE/SUM aggregation over GROUP BY for win/loss/pnl in a single query"
    - "StaticPool added to test isolated_db fixture to share :memory: SQLite across TestClient worker threads"

key-files:
  created: []
  modified:
    - src/predictions/api.py
    - tests/test_strategy_analytics.py
    - tests/conftest.py
    - pyproject.toml

key-decisions:
  - "Top-of-file `from sqlalchemy import case` (rather than function-local) to keep imports centralized; plan permitted either"
  - "StrategyAnalyticsTrade is a separate Pydantic model (subset of TradeResponse columns) to keep /api/strategy-analytics response stable even if TradeResponse evolves"
  - "Pnl_curve cumulative sum runs in Python to avoid SQLite version-dependent window functions (D-05)"
  - "Pnl_curve filter skips rows with NULL settled_at (Pitfall 5) — never plot points with x=None"
  - "tests/conftest.py isolated_db fixture upgraded to StaticPool — required so FastAPI TestClient worker threads see the same in-memory DB the test seeded; without it, queries hit a fresh empty :memory: DB"
  - "pyproject.toml ty.environment.root extended to include 'tests' so the type-checker resolves `from conftest import seed_trades`"
  - "Test datetime assertions use naive ISO format (`replace(tzinfo=None).isoformat()`) because SQLite drops tzinfo on round-trip — the seeded UTC datetime is returned as naive in JSON"

patterns-established:
  - "Read-only authenticated analytics endpoint pattern: `dependencies=[Depends(_check_token)]`, no `session.add` or `session.commit`, explicit `session.close()` before return"
  - "Composite filter symmetry across analytics + summary endpoints (`Trade.strategy_name == name` AND `or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))`)"
  - "YAML+DB merge for sidebar lists: dict-by-name lookup of DB aggregates, then iterate YAML in insertion order to preserve UI ordering, append orphaned DB rows last"

requirements-completed: [DASH-03]

# Metrics
duration: ~25min
completed: 2026-05-06
---

# Phase 04 Plan 01: Implement Analytics API Summary

**Two new authenticated read-only endpoints (`/api/strategy-analytics` + `/api/strategies-summary`) plus `TradeResponse.strategy_name` field — all 7 Wave 0 xfail stubs flipped green; full repo lint + type-check + tests pass.**

## Performance

- **Started:** 2026-05-06T20:48:00Z (approx)
- **Completed:** 2026-05-06T21:14:00Z (approx)
- **Tasks:** 3
- **Files modified:** 4 (3 source/test, 1 config)
- **Tests:** 86 passed (was 79), 0 xfailed (was 7), 1 skipped, 0 errors

## Accomplishments

- `TradeResponse.strategy_name` field exposed; `get_trades()` populates it from `Trade.strategy_name`. Existing /api/trades consumers see no behavior change for legacy rows (NULL → null in JSON).
- `GET /api/strategy-analytics?strategy=<name>` implemented with stat aggregates, full trade log (newest first), and per-trade-step running P&L curve over settled trades.
- `GET /api/strategies-summary` implemented with YAML+DB merge: zero-trade YAML strategies appear with all-zero stats; orphaned DB-only strategies are appended.
- All 7 Phase 04 test stubs flipped from `xfail` to passing assertions.
- Composite filter (Phase 03 D-16 symmetry) applied in both endpoints — `Trade.strategy_name.isnot(None) AND or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))`.
- SQL emitted by /api/strategy-analytics composite filter:
  ```sql
  WHERE trades.strategy_name = ?
    AND (trades.dry_run = 0 OR (trades.dry_run = 1 AND trades.strategy_name IS NOT NULL))
  ```
- SQL emitted by /api/strategies-summary GROUP BY:
  ```sql
  SELECT strategy_name,
         COUNT(id),
         SUM(CASE WHEN status = 'settled_win' THEN 1 ELSE 0 END),
         SUM(CASE WHEN status = 'settled_loss' THEN 1 ELSE 0 END),
         SUM(CASE WHEN pnl_cents IS NOT NULL THEN pnl_cents ELSE 0 END)
  FROM trades
  WHERE strategy_name IS NOT NULL
    AND (dry_run = 0 OR (dry_run = 1 AND strategy_name IS NOT NULL))
  GROUP BY strategy_name
  ```
- Pnl_curve cumulative sum runs in Python over `settled_rows ORDER BY settled_at` (D-05 — avoids SQLite window functions); rows with NULL `settled_at` are skipped (Pitfall 5).
- YAML+DB merge order: YAML strategies first (in YAML insertion order), then DB-only orphans appended afterwards.

## Task Commits

1. **Task 1: Add `strategy_name` to TradeResponse + get_trades constructor** — `0b340d0` (feat)
2. **Task 2: Implement GET /api/strategy-analytics + flip 4 xfail tests** — `91797e6` (feat)
3. **Task 3: Implement GET /api/strategies-summary + flip 3 xfail tests** — `2be87c0` (feat)

## Response model field shapes

```python
class TradeResponse(BaseModel):
    # ... existing 14 fields ...
    espn_clock_seconds: Optional[int] = None
    strategy_name: Optional[str] = None  # NEW

class StrategyAnalyticsStats(BaseModel):
    total_trades: int
    wins: int
    losses: int
    open_trades: int
    win_rate: float
    realized_pnl_cents: int

class StrategyAnalyticsTrade(BaseModel):
    id: int
    placed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    ticker: str
    yes_price: int
    count: int
    cost_cents: int
    pnl_cents: Optional[int] = None
    status: str

class StrategyAnalyticsPnlPoint(BaseModel):
    x: Optional[datetime] = None
    y: int
    ticker: str
    trade_pnl: int

class StrategyAnalyticsResponse(BaseModel):
    stats: StrategyAnalyticsStats
    trades: list[StrategyAnalyticsTrade]
    pnl_curve: list[StrategyAnalyticsPnlPoint]

class StrategySummaryEntry(BaseModel):
    name: str
    total_trades: int
    wins: int
    losses: int
    pnl_cents: int

class StrategiesSummaryResponse(BaseModel):
    strategies: list[StrategySummaryEntry]
```

## Decisions Made

- **`case` import location**: top-of-file (cleaner; plan permitted either).
- **StrategyAnalyticsTrade is a separate Pydantic model**: subset of TradeResponse columns. Keeps the analytics response stable even if TradeResponse evolves.
- **Pnl_curve cumulative sum in Python**: D-05 — SQLite window functions are version-dependent. Iterate `ORDER BY settled_at`, skip NULL settled_at (Pitfall 5).
- **YAML+DB merge order in /api/strategies-summary**: YAML first in insertion order (matches `/api/strategies` ordering convention), then orphan DB-only entries appended.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] StaticPool added to `tests/conftest.py` `isolated_db` and `isolated_soccer_db` fixtures**
- **Found during:** Task 2 — first run of `test_analytics_returns_correct_stats` failed with `sqlalchemy.exc.OperationalError: no such table: trades`.
- **Issue:** The fixture's `:memory:` SQLite engine uses SQLAlchemy's default pool (`SingletonThreadPool` for sqlite). `:memory:` databases are per-connection, so when the test thread seeds tables on connection A and the FastAPI TestClient runs the request body on a different worker thread (anyio), that thread opens a new connection B with a fresh empty `:memory:` DB. Tables and rows are invisible.
- **Fix:** Add `poolclass=StaticPool` to both `isolated_db` and `isolated_soccer_db` fixtures. StaticPool keeps a single connection across all sessions, so all threads see the same `:memory:` DB.
- **Files modified:** `tests/conftest.py` (2 fixtures, 4 lines added — import + 2 fixture changes).
- **Impact:** All existing tests still pass (StaticPool is strictly more sharing-friendly than SingletonThreadPool); 4 new tests in this plan now pass that previously could not.
- **Committed in:** `91797e6` (Task 2 commit).

**2. [Rule 3 - Blocking] `pyproject.toml` `ty.environment.root` extended to include `tests`**
- **Found during:** Task 2 — `uv run ty check` reported `error[unresolved-import]: Cannot resolve imported module 'conftest'` for `from conftest import seed_trades` in `tests/test_strategy_analytics.py`.
- **Issue:** The project's `ty` config sets `root = ["src"]`, so the type checker only searches `src/` for module imports. The plan-prescribed import `from conftest import seed_trades` works at pytest runtime (because pytest's rootdir adds `tests/` to `sys.path`) but is invisible to `ty`. Without this fix the verification gate `uv run ty check` cannot pass.
- **Fix:** Extend `root` from `["src"]` to `["src", "tests"]`. This mirrors the `[tool.ruff].src = ["src", "tests"]` line that already exists in the same file.
- **Files modified:** `pyproject.toml` (1 line — `root` array extended).
- **Impact:** `ty` now type-checks tests against `tests/` modules too. No behavior change; tests already passed at runtime.
- **Committed in:** `91797e6` (Task 2 commit).

**3. [Rule 1 - Bug] pnl_curve test datetime format**
- **Found during:** Task 2 — first run of `test_analytics_pnl_curve_running_sum` failed:
  ```
  AssertionError: assert [{'ticker': '...00', 'y': 60}] == [{'ticker': '...0Z', 'y': 60}]
  At index 0 diff: {'x': '2026-05-01T13:00:00', ...} != {'x': '2026-05-01T13:00:00Z', ...}
  ```
- **Issue:** SQLite drops tzinfo on round-trip — the seeded `datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)` is stored as a naive datetime and FastAPI/Pydantic serializes it without the `Z` suffix. The plan instructed `t.isoformat()` which produces `+00:00` for tz-aware datetimes; replacing `+00:00` with `Z` was incorrect.
- **Fix:** Use `t.replace(tzinfo=None).isoformat()` so the test asserts against the actual JSON shape SQLite produces.
- **Files modified:** `tests/test_strategy_analytics.py` (3 assertion lines).
- **Committed in:** `91797e6` (Task 2 commit).
- **Note:** This is a test-side fix — the endpoint behavior is correct. The dashboard consumer will need to handle naive UTC datetimes (or the schema can be re-typed to enforce tz storage in a future plan). Out of scope for this plan; recharts treats both formats identically for x-axis rendering.

**4. [Rule 1 - Bug] Auto-format moved `from conftest import seed_trades` below `fastapi.testclient`**
- **Found during:** Task 2 — `uv run ruff check . --fix` reorganized the import block (I001) so first-party `conftest` import is grouped after third-party imports.
- **Issue:** Ruff's import sorter classifies `conftest` as first-party once `ty.environment.root` and `[tool.ruff].src` include `tests`. The original ordering was un-sorted.
- **Fix:** Accepted ruff's auto-fix (cosmetic; semantics unchanged).
- **Files modified:** `tests/test_strategy_analytics.py`.
- **Committed in:** `91797e6` (Task 2 commit).

---

**Total deviations:** 4 — 2 Rule 3 (blocking infrastructure), 1 Rule 1 (test assertion), 1 cosmetic (ruff auto-fix).
**Impact on plan:** None on the contract. All deviations were mechanical / infrastructure issues uncovered when running the tests against the implementation. No endpoint behavior changes or scope additions.

## Issues Encountered

None beyond the documented Rule 3 blockers.

## Next Phase Readiness

- **Wave 2 (04-02 — implement analytics page):** the two endpoints are wired and Bearer-auth gated. Response shapes match the plan-locked schemas; the dashboard `/analytics` route can consume them directly via `fetch('/api/strategy-analytics?strategy=<name>')` and `fetch('/api/strategies-summary')` (with the existing `BackendApi` wrapper carrying the API_TOKEN).
- **Wave 3 (04-03 — cross-link trades page):** `TradeResponse.strategy_name` is now in the JSON. The dashboard's `/trades` consumers can read it; rows with NULL strategy_name continue to display unchanged.
- **No new dependencies, no Kalshi API touches, no scanner changes.** The endpoints are read-only and idempotent.
- **DRY-01 invariant unchanged:** no `place_order`, no `session.add`, no `session.commit` in the new handlers.

## Plan-level verification (final state)

```
$ uv run pytest tests/test_strategy_analytics.py -v
============================== 7 passed in 0.43s ==============================

$ uv run pytest tests/
======================== 86 passed, 1 skipped in 1.05s ========================

$ uv run ruff check . && uv run ruff format --check . && uv run ty check
All checks passed!
26 files already formatted
All checks passed!
```

## Self-Check: PASSED

Verified post-write:

```
$ ls .planning/phases/04-analytics-dashboard/04-01-SUMMARY.md
.planning/phases/04-analytics-dashboard/04-01-SUMMARY.md

$ git log --oneline -5
2be87c0 feat(04-01): implement GET /api/strategies-summary + flip 3 xfail tests
91797e6 feat(04-01): implement GET /api/strategy-analytics + flip 4 xfail tests
0b340d0 feat(04-01): add strategy_name to TradeResponse + get_trades constructor
6a03543 chore: merge executor worktree (worktree-agent-a51fb04cb07999082) for 04-00
3afb3f2 docs(04-00): complete wave 0 test scaffolding plan

$ uv run pytest tests/ 2>&1 | tail -1
======================== 86 passed, 1 skipped in 1.05s ========================
```

All 3 task commits present (0b340d0, 91797e6, 2be87c0); SUMMARY file exists; full suite green; 0 xfailed.

---
*Phase: 04-analytics-dashboard*
*Plan: 01*
*Completed: 2026-05-06*
