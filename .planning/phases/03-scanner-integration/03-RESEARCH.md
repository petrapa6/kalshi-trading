# Phase 3: Scanner Integration - Research

**Researched:** 2026-05-01
**Domain:** Live scanner integration of YAML strategies + dry-run trade path + settlement reconciliation + decommission of `WHAT_IF_STRATEGIES`/`stretch_opportunities`
**Confidence:** HIGH (brownfield project; all decisions already locked in 03-CONTEXT.md and verified against actual code)

## Summary

Phase 3 wires the Phase 2 `strategies.yaml` loader into the live scanner's
Kalshi loop, adds a strategy-driven dry-run path that bypasses Kalshi REST,
extends settlement reconciliation to cover dry-run strategy trades on both
WS and REST paths, adds a 5s SQLite lock timeout, and decommissions the
legacy `WHAT_IF_STRATEGIES` system (rename `stretch_opportunities` table,
delete `WHAT_IF_STRATEGIES` dict and `_evaluate_what_if_strategies`,
re-source `/api/sport-stats` from `opportunities`).

The phase has zero locked alternatives — D-01 through D-20 in
`03-CONTEXT.md` are all selected. Research's job is to (a) verify the
locked decisions against the actual code, (b) **surface orphan callers
that D-20 missed**, (c) prove the per-sport `elapsed_minutes()` helper is
implementable from existing `GameState` fields, and (d) define the
validation architecture (Nyquist gate).

**Primary recommendation:** Plan around the **three orphan callers** that
D-20 does not list: `api.py::/api/stretch-stats` (line 826), `api.py::DELETE
/api/stretch` (line 881), and `tests/test_sport_stats.py` (lines 27, 35).
The `StretchOpportunity` ORM model deletion (D-20) breaks all three. The
dashboard's "What If? Strategy Comparison" tab (`page.tsx:2618-2674`)
consumes `/api/stretch-stats` — that UI must either be removed or the
endpoint must be ported to read from `Trade` rows filtered by
`strategy_name`. **Surface this to the user before writing the plan.**

## User Constraints (from CONTEXT.md)

### Locked Decisions

**Schema migration (D-01..D-03):**
- D-01: `Trade.strategy_name = Column(String, nullable=True, index=True)`. Indexed because Phase 4 analytics will filter/aggregate by it. ALTER TABLE via existing `_migrate_add_columns()` pattern at `db.py:152`.
- D-02: `db.py:19` adds `"timeout": 5` to `connect_args`. Single-line change, no env override.
- D-03: `stretch_opportunities` → `stretch_opportunities_archived` rename inside `_migrate_add_columns()`, guarded by `inspector.get_table_names()`. `StretchOpportunity` ORM class deleted (table physically lives for archival only). **Pre-deploy gate:** test rename against current S3 backup copy locally.

**Strategy evaluation in scan loop (D-04..D-06):**
- D-04: New `evaluate_strategies(session, client, espn_final_period, max_bet_cents)` in `scanner.py`, called inside `kalshi_scan_loop` after `scan_kalshi_with_espn` returns, before `check_settlements`. Same iteration cadence (~5s); no new asyncio loop. Replaces (not appends to) the `_evaluate_what_if_strategies` slot at `scanner.py:575`.
- D-05: `load_strategies()` invoked **once per scan loop iteration**. Errors short-circuit: log + skip evaluation this tick (do not raise).
- D-06: Iterate **markets × strategies × triggers**; first-trigger-wins per `(strategy, market)` tick; per-strategy dedupe via DB query before fire.

**Sport family ↔ sport_path + clock semantics (D-07..D-09):**
- D-07: **Phase 2 D-02 OVERRIDE governs.** `trigger.sport` is a sport-family literal (`football`, `basketball`, `baseball`, `tennis`, `american_football`, `hockey` — UK terminology, never `soccer`).
- D-08: New module-level `SPORT_FAMILY_TO_PATHS: dict[str, frozenset[str]]` in `scanner.py` (next to `KALSHI_TO_ESPN`); reverse `path → family` map computed once at import.
- D-09: New per-sport `SPORT_GAME_LENGTH_SECS` constant + `elapsed_minutes(sport_path, espn_clock_seconds, period)` helper. Soccer (count-up): `clock // 60` plus period offset. Count-down sports: `(period_offset + (period_length_secs - clock_seconds)) // 60`. Baseball/tennis (no clock): log + skip the trigger.

**Per-strategy dedupe + multi-strategy fire (D-10..D-12):**
- D-10: Per-strategy dedupe `(strategy_name, ticker)` via `SELECT 1 FROM trades WHERE strategy_name=:s AND ticker=:t LIMIT 1`. Skip if a row exists regardless of status.
- D-11: Multiple distinct strategies CAN fire on the same ticker (each gets its own Trade row).
- D-12: First-trigger-wins per `(strategy, market)` tick.

**Strategy-driven dry-run path (D-13..D-15):**
- D-13: New `place_strategy_trade(session, opp, strategy_name, max_cost_cents)`. Hardcoded `dry_run=True`, `status="dry_run"`, `strategy_name=<name>`, `yes_price = opp["yes_ask"]` (live cache), `count = max_cost_cents // yes_price`. **Does NOT reuse `place_bet`'s dry_run branch** — distinct intent (analytics vs. ops debug).
- D-14: `max_bet_cents = bet_percent × current_balance` — same balance source as live trades, computed once per scan iteration.
- D-15: `trading_paused` check inside `place_strategy_trade` (mirrors live-trade kill-switch pattern). **Verified against current code:** `scanner.py:523` checks `trading_paused` at the **loop level inside `scan_kalshi_with_espn`**, not inside `place_bet`. The locked decision says "mirror existing pattern" — see Pitfall #2 below.

**Settlement reconciliation (D-16..D-18):**
- D-16: Single combined filter in `check_settlements`: `Trade.status.in_(("placed","filled","dry_run"))` + `or_(Trade.dry_run==False, and_(Trade.dry_run==True, Trade.strategy_name.isnot(None)))`. Excludes legacy process-level dry-runs (`dry_run=True AND strategy_name IS NULL`).
- D-17: WS `on_lifecycle` handler (`scanner.py:828–880`) gains the same combined filter when querying `Trade` rows by ticker on `market_lifecycle_v2` events. Symmetry is a correctness requirement.
- D-18: P&L for strategy dry-runs: win = `count × (100 − yes_price)`, loss = `−count × yes_price` (no fee — no real order). Status flow: `dry_run` → (`settled_win` | `settled_loss` | `error`). Same enum values as real trades.

**`/api/sport-stats` migration (D-19):**
- Replace `SELECT series_ticker, COUNT(*) FROM stretch_opportunities GROUP BY series_ticker` with `SELECT series_ticker, COUNT(DISTINCT event_ticker) FROM opportunities GROUP BY series_ticker`. **Behavior change** — old: rows in stretch table; new: distinct games scanned per series. Flag in PLAN.md.

**Removal scope (D-20):** Listed in 03-CONTEXT.md. **Incomplete — see Open Questions below.**

### Claude's Discretion

- Module location for sport mapping helpers (`scanner.py` inline vs. `src/predictions/sports.py`) — extract if helpers cross 100 lines; otherwise inline.
- `evaluate_strategies` test seam — pure function with `session` + `strategies: list[Strategy]` injected (lean toward functional, matches scanner.py).
- Logging cadence — log every fire (one line); suppress repeated "skipped" / "already fired" entries. Log first skip per `(strategy, ticker)` if at all.
- Trade `trigger_index` column — Phase 4 deferral is fine; planner may judge it cheaper to add now.
- Error handling cadence for malformed `strategies.yaml` at scan time — log + skip this tick; whether to rate-limit warnings is planner's call.
- Whether `evaluate_strategies` runs even if `trading_paused == true` — D-15 says gate is inside `place_strategy_trade`; planner may judge loop-level early-exit cleaner. Both acceptable as long as success criterion #3 holds.

### Deferred Ideas (OUT OF SCOPE)

- Per-strategy `bet_percent` override
- `lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields
- Hot-reload of `strategies.yaml` without container restart
- `trigger_index` column on Trade (Phase 4 may add)
- `min_minute` for clockless sports (baseball, tennis) — log + skip
- Per-strategy `enabled: false` flag in YAML
- Cleanup follow-up to drop `stretch_opportunities_archived` (intended permanent)
- Removing process-level `DRY_RUN` env var entirely

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STR-04 | `stretch_opportunities` table dropped/archived; `WHAT_IF_STRATEGIES` removed; `/api/sport-stats` re-sourced from `opportunities` table | D-03 (rename), D-19 (re-source), D-20 (removals). **Note:** ROADMAP supersedes REQUIREMENTS — rename, not drop. |
| DRY-01 | Live scanner evaluates strategies each loop; trigger fire records live `yes_ask` as entry price; no Kalshi API call; hardcoded `dry_run=True` regardless of process-level `DRY_RUN` | D-04 (loop integration), D-06 (eval shape), D-13 (no-API path), D-14 (sizing) |
| DRY-02 | Dry-run trades stored with `strategy_name` column; contract-math P&L on settlement; WS primary + REST fallback | D-01 (schema), D-16/D-17 (settlement filter), D-18 (P&L math) |

## Project Constraints (from CLAUDE.md)

Directives that the planner MUST verify the implementation honors:

1. **Integer cents invariant.** All Kalshi prices are integer cents internally; dollar strings cross only at `kalshi_client.py::extract_cents`. `place_strategy_trade` reads `yes_ask` from `market_prices` (already extracted) — no parallel extractor.
2. **`trading_paused == "true"` is the kill switch.** Must be checked before every order placement (existing pattern at `scanner.py:523`). D-15 mirrors this for strategy trades.
3. **`get_config_int()` first, code defaults as fallback.** Never hardcode tunables. `evaluate_strategies` reads `bet_percent` and `trading_paused` via the existing helpers each loop.
4. **No new Python deps.** Pure-stdlib + already-installed packages. (No new deps needed for Phase 3 anyway — uses existing `sqlalchemy`, `pyyaml` via `load_strategies`.)
5. **Permissive logging + log-and-continue.** YAML errors during eval, missing `market_prices` entries, missing game-length entries: log warning, skip the relevant unit, continue the loop. **No raises out of the scan loop.**
6. **Verification gate before claiming done:** `uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest tests/`. Plus manual `pnpm dev:api` smoke test on the affected endpoint.
7. **Never commit `.env`, `predictions.db`, `scanner.log`.** Manual secret scan before every commit (pre-commit hook does NOT scan secrets).
8. **No new abstractions or features beyond what the task requires.** Don't unify `place_bet` and `place_strategy_trade` "for cleanliness" — duplication is intentional (D-13).
9. **Flag blast radius before touching shared interfaces.** `Trade` schema is shared (CLI, dashboard, scanner). Adding `strategy_name` is additive (nullable, indexed) — low blast radius — but call out in PLAN.md.

## Architectural Responsibility Map

Phase 3 is purely backend Python — no frontend tier work in scope.

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|--------------|----------------|-----------|
| Strategy YAML parse | Backend (Python loader) | — | Already lives in `src/predictions/strategies.py` (Phase 2). Scanner imports `load_strategies` directly. |
| Strategy evaluation against live markets | Backend (scanner async loop) | — | Reuses `kalshi_scan_loop`'s 5s tick + `market_prices` cache + ESPN cache. No new loop. |
| Dry-run trade row write | Backend (`db.py` ORM via `place_strategy_trade`) | — | Single SQLAlchemy session per call; mirrors `place_bet`'s session lifecycle. |
| Settlement update on dry-run trades | Backend (WS handler + REST fallback) | — | Both paths in `scanner.py`; combined filter (D-16) keeps them in lockstep. |
| Schema migration | Backend (`db.py::_migrate_add_columns`) | — | Idempotent ALTER TABLE pattern. Runs on `init_db()` (called from API lifespan startup). |
| Stretch system removal (code) | Backend (`scanner.py`, `db.py`) | — | Pure deletes per D-20. |
| `/api/sport-stats` re-source | Backend (`api.py`) | Frontend consumer (read-only) | Endpoint shape unchanged; semantic of `played` count shifts (D-19). Dashboard consumer at `page.tsx:2263` displays as a number — semantic shift is invisible to the UI. |
| Stretch endpoints removal/migration | Backend (`api.py`) + Frontend (`page.tsx`) | — | **Surfaced as Open Question.** D-20 does not list `/api/stretch-stats` or `/api/stretch` DELETE — these endpoints break when `StretchOpportunity` ORM class is deleted. Dashboard "What If? Strategy Comparison" tab (`page.tsx:2618`) consumes the response. Either remove the endpoints + UI, or port to read from `Trade` rows filtered by `strategy_name`. |

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| `sqlalchemy` | 2.0.48 | ORM + raw SQL via `text()` | Already locked in `pyproject.toml`. `or_` and `and_` available from `sqlalchemy` top-level import (verified). [VERIFIED: `pyproject.toml` line 13, `uv run python -c "import sqlalchemy"` returns 2.0.48] |
| `pyyaml` | 6.0+ | Strategy YAML parse via `yaml.safe_load` | Already locked Phase 2; reused via `load_strategies()`. No direct YAML access in scanner. [VERIFIED: `pyproject.toml` line 12] |
| `pydantic` | (transitive via FastAPI) | Strategy schema validation | Already used in `strategies.py` for `Strategy`/`Trigger` models. [VERIFIED: `src/predictions/strategies.py:16`] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| `pytest` | >=8.0 | Test runner | All Phase 3 tests |
| `pytest-asyncio` | >=0.24 | Async test support, `asyncio_mode = "auto"` | If any test exercises async scanner code |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| `or_`/`and_` from sqlalchemy | Python boolean expression on `Trade.dry_run` then post-filter in Python | Rejected — query MUST be DB-side for index use; Python post-filter would defeat the index on `strategy_name` (D-01). |
| New module `src/predictions/sports.py` | Inline constants in `scanner.py` next to `KALSHI_TO_ESPN` | Inline preferred unless helpers cross 100 lines (D-08 instruction). Per-sport game-length + family map likely <50 lines combined. |

**Installation:** No new deps — Phase 3 uses only existing packages.

**Version verification:**
```bash
uv run python -c "import sqlalchemy; print(sqlalchemy.__version__)"
# 2.0.48 — verified 2026-05-01
uv run python -c "from sqlalchemy import or_, and_; print('ok')"
# ok — verified 2026-05-01
```

## Architecture Patterns

### System Architecture Diagram (Phase 3 changes)

```
┌────────────────────────────────────────────────────────┐
│ kalshi_scan_loop (existing — 5s tick)                 │
│                                                        │
│  1. Re-read config (min_yes_price, bet_percent, …)    │
│  2. Snapshot espn_cache + espn_final_period_cache     │
│  3. Discover Kalshi markets, subscribe via WS         │
│  4. ╔═════════════════════════════════════════╗       │
│     ║ scan_kalshi_with_espn (existing)        ║       │
│     ║   ─ writes Opportunity rows             ║       │
│     ║   ─ calls place_bet (real trades)       ║       │
│     ║   ─ checks trading_paused at loop level ║       │
│     ╚═════════════════════════════════════════╝       │
│  5. ╔═════════════════════════════════════════╗ NEW   │
│     ║ evaluate_strategies (Phase 3, D-04)     ║       │
│     ║   ─ load_strategies() once per tick     ║       │
│     ║   ─ for market in current_open_markets: ║       │
│     ║       espn_game = match_kalshi_to_espn  ║       │
│     ║       for strategy in strategies:       ║       │
│     ║         if (strategy_name, ticker) in   ║       │
│     ║            existing_strategy_trades:    ║       │
│     ║           continue   # D-10 dedupe      ║       │
│     ║         for trigger in strategy.triggers║       │
│     ║           if trigger_matches(...):      ║       │
│     ║             place_strategy_trade(...)   ║       │
│     ║             break    # D-12 first-fire  ║       │
│     ╚═════════════════════════════════════════╝       │
│  6. check_settlements  (REST fallback — UPDATED filter)│
│  7. record_balance                                    │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ ws_loop / on_lifecycle (existing — UPDATED filter)    │
│                                                        │
│  market_lifecycle_v2 → status=finalized result=yes/no │
│  ─ Query Trade WHERE ticker=X AND combined_filter     │
│  ─ For each trade: settled_win / settled_loss + P&L   │
│  ─ Symmetry with REST check_settlements (D-17)        │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ db.py (UPDATED)                                        │
│  ─ engine connect_args += "timeout": 5  (D-02)        │
│  ─ Trade.strategy_name column (D-01)                  │
│  ─ _migrate_add_columns:                              │
│      • ADD COLUMN trades.strategy_name               │
│      • RENAME stretch_opportunities → ..._archived   │
│      • DROP stretch ALTER stubs (D-20)                │
│  ─ StretchOpportunity ORM class DELETED (D-20)        │
└────────────────────────────────────────────────────────┘

┌────────────────────────────────────────────────────────┐
│ DELETED: WHAT_IF_STRATEGIES dict, _evaluate_what_if_   │
│ strategies, stretch_opps accumulator, meets_stretch_   │
│ lead branches, the if stretch_opps flush block,       │
│ check_stretch_settlements helper                      │
└────────────────────────────────────────────────────────┘
```

### Recommended Project Structure

No new directories. All changes confined to existing files:

```
src/predictions/
├── scanner.py        # MODIFY: add evaluate_strategies, place_strategy_trade,
│                     # SPORT_FAMILY_TO_PATHS, SPORT_GAME_LENGTH_SECS,
│                     # elapsed_minutes; remove WHAT_IF_STRATEGIES,
│                     # _evaluate_what_if_strategies, stretch_opps branches,
│                     # check_stretch_settlements; UPDATE check_settlements
│                     # filter; UPDATE on_lifecycle filter
├── db.py             # MODIFY: add strategy_name column, timeout=5,
│                     # rename stretch table, remove StretchOpportunity ORM
├── api.py            # MODIFY: re-source /api/sport-stats from opportunities;
│                     # decision pending on /api/stretch-stats and DELETE /api/stretch
├── strategies.py     # UNCHANGED (Phase 2 output)
├── espn.py           # UNCHANGED — read existing GameState fields only
└── kalshi_client.py  # UNCHANGED — extract_cents/extract_volume reused

tests/
├── test_scanner_strategies.py  # NEW — evaluate_strategies + helpers
├── test_strategy_settlement.py # NEW — D-16/D-17 symmetry
├── test_db_migrations.py       # NEW — idempotent rename + column add
├── test_sport_stats.py         # MODIFY — drop StretchOpportunity rows
│                                 (after planner decides on /api/stretch-stats)
└── conftest.py                 # UNCHANGED — isolated_db fixture sufficient
```

### Pattern 1: Idempotent migration via `_migrate_add_columns`

**What:** SQLite ALTER TABLE wrapped in `inspector.get_columns()` / `inspector.get_table_names()` guards.
**When to use:** Any schema change in this codebase. Already used twice for `Trade.espn_clock_seconds`, `Trade.fee_cents`, and `StretchOpportunity.strategy_set`/`side`.
**Example (D-01 + D-03):**
```python
# Source: src/predictions/db.py:152 (existing pattern)
def _migrate_add_columns():
    from sqlalchemy import inspect, text
    inspector = inspect(engine)

    if "trades" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("trades")}
        if "strategy_name" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN strategy_name VARCHAR"))
                conn.execute(text(
                    "CREATE INDEX IF NOT EXISTS ix_trades_strategy_name "
                    "ON trades (strategy_name)"
                ))

    table_names = inspector.get_table_names()
    if (
        "stretch_opportunities" in table_names
        and "stretch_opportunities_archived" not in table_names
    ):
        with engine.begin() as conn:
            conn.execute(text(
                "ALTER TABLE stretch_opportunities "
                "RENAME TO stretch_opportunities_archived"
            ))
```

**SQLite caveats verified:**
- `ALTER TABLE ... RENAME TO` is supported in SQLite 3.25+ and works inside an explicit transaction (`engine.begin()`). [VERIFIED: SQLAlchemy 2.0 docs; SQLite docs lang_altertable]
- `inspector.get_columns()` does NOT cache between calls; each call hits sqlite_master. Re-instantiate `inspector = inspect(engine)` only once at function start.
- A SQLAlchemy `engine.begin()` transaction issues a single COMMIT at exit. ALTER TABLE in SQLite is autocommit-safe even mid-transaction (SQLite quirk).

### Pattern 2: Combined filter via `or_` / `and_` (D-16)

**What:** SQLAlchemy 2.0 expression-language `or_(…, and_(…))` for the settlement filter.
**When to use:** Whenever a single query must match disjoint conditions and you want index utilization.
**Example:**
```python
# Source: SQLAlchemy 2.0 ORM tutorial (verified import path)
from sqlalchemy import or_, and_

open_trades = session.query(Trade).filter(
    Trade.status.in_(("placed", "filled", "dry_run")),
    or_(
        Trade.dry_run == False,                                          # noqa: E712
        and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),    # noqa: E712
    ),
).all()
```
- `# noqa: E712` is unnecessary because `pyproject.toml:32` already ignores E712 globally. [VERIFIED]
- The combined filter is index-eligible on `(status, dry_run, strategy_name)`. The `strategy_name` index from D-01 covers the strategy-name leg.

### Pattern 3: Per-sport elapsed-minutes derivation (D-09)

`GameState` exposes:
- `clock_seconds: float` — soccer counts UP from 0; basketball/football/hockey count DOWN within each period
- `period: int` — 1-indexed period number
- `sport_path: str` — e.g., `basketball/nba`, `soccer/eng.1`

**Verified semantics from existing code:**
- `espn.py:87` — soccer `clock_seconds` is checked with `>= final_secs` (4500s = 75min) → confirms count-up.
- `espn.py:89` — non-soccer, non-baseball uses `<= final_secs` (300s = 5min) → confirms count-down.
- `espn.py:201` — baseball: "no clock" — `is_in_final_minutes` returns true purely on `is_final_period`.
- `espn.py:31-42` — `SPORT_FINAL_PERIOD`: NBA=4, NHL=3, NFL=4, MLB=9, NCAAMB=2, NCAAFB=4, MMA=5, soccer=2.

**Per-sport period structure (canonical values, verified from `SPORT_FINAL_PERIOD`):**

| sport_path | Periods | Period length | Total game | Clock direction |
|------------|--------:|--------------:|-----------:|-----------------|
| `basketball/nba` | 4 | 12 min | 48 min | count-down |
| `basketball/mens-college-basketball` | 2 | 20 min | 40 min | count-down |
| `football/nfl` | 4 | 15 min | 60 min | count-down |
| `football/college-football` | 4 | 15 min | 60 min | count-down |
| `hockey/nhl` | 3 | 20 min | 60 min | count-down |
| `soccer/eng.1` | 2 | 45 min | 90 min | count-up |
| `soccer/esp.1` | 2 | 45 min | 90 min | count-up |
| `soccer/usa.1` | 2 | 45 min | 90 min | count-up |
| `baseball/mlb` | 9 innings | n/a | n/a | NO CLOCK |
| `mma/ufc` | 5 rounds | 5 min | 25 min | count-down |

**Helper implementation:**
```python
# Period length per sport (seconds within one period, NOT total game seconds)
SPORT_PERIOD_LENGTH_SECS: dict[str, int] = {
    "basketball/nba": 12 * 60,
    "basketball/mens-college-basketball": 20 * 60,
    "football/nfl": 15 * 60,
    "football/college-football": 15 * 60,
    "hockey/nhl": 20 * 60,
    "soccer/eng.1": 45 * 60,
    "soccer/esp.1": 45 * 60,
    "soccer/usa.1": 45 * 60,
    "mma/ufc": 5 * 60,
}

CLOCKLESS_SPORT_PATHS: frozenset[str] = frozenset({
    "baseball/mlb",  # innings, no clock
    # Tennis would go here once a Kalshi tennis market matches an ESPN game
})

COUNT_UP_SPORT_PATHS: frozenset[str] = frozenset({
    "soccer/eng.1", "soccer/esp.1", "soccer/usa.1",
    # ... add other soccer leagues if KALSHI_TO_ESPN expands
})


def elapsed_minutes(sport_path: str, clock_seconds: float, period: int) -> int | None:
    """Return game-clock minutes elapsed since start, or None if not derivable.

    Returns None for clockless sports (baseball, tennis) — caller should
    skip min_minute triggers for these.
    """
    if sport_path in CLOCKLESS_SPORT_PATHS:
        return None  # caller logs + skips trigger
    period_secs = SPORT_PERIOD_LENGTH_SECS.get(sport_path)
    if period_secs is None:
        return None  # unknown sport — caller logs + skips
    if sport_path in COUNT_UP_SPORT_PATHS:
        # Soccer: clock_seconds counts up from 0 within the match.
        # ESPN reports clock as a single running counter (45:00 at half,
        # 90:00 at full time). No period offset needed — clock is already
        # cumulative on ESPN.
        return int(clock_seconds // 60)
    # Count-down: completed periods + (period_secs - clock_seconds in current period)
    completed_periods = max(0, period - 1)
    elapsed_in_current = max(0, period_secs - int(clock_seconds))
    return (completed_periods * period_secs + elapsed_in_current) // 60
```

⚠️ **Soccer clock semantics caveat:** I assert above that ESPN's soccer clock is already cumulative (45:00 at half, 90:00 at full). This is consistent with `espn.py:88`'s threshold check `clock_seconds >= 4500` (75 min into a 90-min match) — that comparison only makes sense on a cumulative clock. **Planner must verify this empirically against a live ESPN soccer scoreboard JSON sample before locking the formula.** The Phase 2 D-01 promise was "per-sport `total_game_seconds` / period-length lookup" — the cumulative-clock assumption simplifies the soccer math. If empirically the clock resets to 0 at half, switch to `45 + (clock_seconds // 60)` for period 2. [ASSUMED — empirical check needed]

### Pattern 4: Module-level `frozenset` for sport family → paths (D-08)

```python
SPORT_FAMILY_TO_PATHS: dict[str, frozenset[str]] = {
    "football": frozenset({"soccer/eng.1", "soccer/esp.1", "soccer/usa.1"}),
    # NOTE: Phase 2 02-CONTEXT.md D-02 OVERRIDE says "football" maps to
    # multiple soccer leagues. The CONTEXT D-08 listed eng.1/esp.1/ger.1/
    # ita.1/fra.1/usa.1/uefa.champions, but the codebase TODAY only has
    # eng.1/esp.1/usa.1 in KALSHI_TO_ESPN. Plan to ship D-08 with ONLY
    # the leagues currently present in KALSHI_TO_ESPN; expand when new
    # Kalshi series are added.
    "basketball": frozenset({"basketball/nba", "basketball/mens-college-basketball"}),
    "baseball": frozenset({"baseball/mlb"}),  # KXMLBSTGAME also maps here
    "american_football": frozenset({"football/nfl", "football/college-football"}),
    "hockey": frozenset({"hockey/nhl"}),
    "tennis": frozenset(),  # KXTENNISGAME exists in SPORTS_GAME_SERIES but
                            # NOT in KALSHI_TO_ESPN — no ESPN matching today
}

# Reverse map computed once at import
SPORT_PATH_TO_FAMILY: dict[str, str] = {
    path: family
    for family, paths in SPORT_FAMILY_TO_PATHS.items()
    for path in paths
}
```

**Verified sport_paths in current codebase** (cross-reference KALSHI_TO_ESPN, lead:* config keys, MIN_SCORE_LEAD):

| sport_path | KALSHI_TO_ESPN | MIN_SCORE_LEAD | lead:* default | family literal |
|------------|:--------------:|:--------------:|:--------------:|:--------------:|
| `basketball/nba` | ✓ | ✓ | ✓ | basketball |
| `basketball/mens-college-basketball` | ✓ | ✓ | ✓ | basketball |
| `hockey/nhl` | ✓ | ✓ | ✓ | hockey |
| `football/nfl` | ✓ | ✓ | ✓ | american_football |
| `football/college-football` | ✓ | ✓ | ✓ | american_football |
| `baseball/mlb` | ✓ | ✓ | ✓ | baseball |
| `soccer/eng.1` | ✓ | ✓ | ✓ | football |
| `soccer/esp.1` | ✓ | ✓ | ✓ | football |
| `soccer/usa.1` | ✓ | ✓ | ✓ | football |
| `mma/ufc` | ✗ (commented out) | ✓ | ✓ | — (no Kalshi mapping today) |

[VERIFIED via grep at `src/predictions/espn.py:16-28`, `scanner.py:62-73`, `db.py:217-244`]

### Anti-Patterns to Avoid

- **Adding a parallel YAML parser.** `load_strategies` from `predictions.strategies` is the single boundary. Any direct `yaml.safe_load` in `scanner.py` is a bug.
- **Adding a parallel price extractor.** `market_prices[ticker]["yes_ask"]` is already extracted by `on_ticker` (`scanner.py:813-826`) and the kalshi-loop seed (`scanner.py:954`). Both routes go through `extract_cents`. Don't re-extract.
- **Spawning a 5th asyncio loop.** D-04 is explicit: `evaluate_strategies` is called inline inside `kalshi_scan_loop` — no `asyncio.gather` extension, no new background task. The current 4-loop architecture (espn / kalshi_scan / ws / backup) is preserved.
- **"Cleaning up" the duplication between `place_bet`'s dry_run branch and `place_strategy_trade`.** Intentional duplication (D-13). One is for ops debug (`DRY_RUN` env), the other for analytics. Conflating them ambiguates settlement filtering.
- **Inheriting backtest engine semantics for `min_yes_price`/`max_yes_price`.** The backtest engine **ignores** these fields (Phase 2 D-11 retraction); the live scanner **filters on them** (per DRY-01). Asymmetry is intentional.
- **Loop-level early-exit on `trading_paused`.** D-15 says check inside `place_strategy_trade`. **But also note** that `scanner.py:523` checks at the loop level inside `scan_kalshi_with_espn` for `place_bet` — see Pitfall #2 for which pattern to mirror.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing in scanner | Direct `yaml.safe_load` | `predictions.strategies.load_strategies()` | Single boundary; Pydantic validated; Phase 2's locked contract. |
| Kalshi price extraction | Re-parsing `yes_ask` from raw market dicts | Read `market_prices[ticker]["yes_ask"]` (already extracted) | `extract_cents` is the single drift point per `kalshi_client.py:19`. |
| Trade row write | New ORM session pattern | Mirror `place_bet`'s session lifecycle (open / add / commit / close) | Established pattern at `scanner.py:149-200`. |
| Sport-family → paths lookup | String matching loops | `SPORT_FAMILY_TO_PATHS` dict + reverse `SPORT_PATH_TO_FAMILY` map | O(1) lookup; computed once at import; matches `KALSHI_TO_ESPN` style. |
| Idempotent migration | Hand-rolled "if exists" with raw SQL | `inspector.get_columns()` / `inspector.get_table_names()` guard pattern from `_migrate_add_columns` | Already proven idempotent; existing tests don't probe migrations directly but `init_db()` runs on every API startup without errors. |
| Combined OR/AND filter | Python post-filter after raw `Trade.status.in_(...)` query | `from sqlalchemy import or_, and_` and compose at the query level | Index utilization; one round-trip; no risk of stale data between query+filter steps. |
| Per-strategy dedupe | In-memory `set` of seen `(strategy, ticker)` | `SELECT 1 FROM trades WHERE strategy_name=:s AND ticker=:t LIMIT 1` | Survives scanner restart; D-01's index makes this O(log n). |

**Key insight:** Phase 3 is a "compose existing primitives" phase, not a "build new abstractions" phase. The codebase already has every primitive needed; the work is wiring them together.

## Runtime State Inventory

This phase **renames a table** (`stretch_opportunities` → `stretch_opportunities_archived`) and **adds a column** (`Trade.strategy_name`). The grep audit (D-20) covers code references but does NOT cover runtime state. Per the rename/refactor protocol:

| Category | Items Found | Action Required |
|----------|-------------|------------------|
| Stored data | (a) **Local SQLite `predictions.db`:** `stretch_opportunities` table contains rows from production v1.0 onwards. After rename, those rows live under `stretch_opportunities_archived`. (b) **`Trade` table:** existing rows have NULL `strategy_name` (legacy real trades + legacy process-level dry-runs) — D-16's filter excludes them from settlement reconciliation. | (a) Rename via D-03 migration, no data migration. (b) Schema add via D-01 ALTER, NULL backfill is implicit. |
| Live service config | (a) **SQLite `config` table:** Has `lead:<sport_path>` and `final_seconds:<sport_path>` keys (`db.py:225-244`). Phase 3 does NOT modify any config keys — `bet_percent`, `trading_paused`, `min_yes_price` are all reused as-is. (b) **No external service stores the table name `stretch_opportunities`** — only the codebase did. | None. |
| OS-registered state | None — this is a Python application running in a single Fargate container. No systemd / cron / pm2 / launchd registrations involve the renamed table. | None. |
| Secrets and env vars | (a) `STRATEGIES_PATH` — already documented in Phase 2; no Phase 3 changes. (b) `DRY_RUN` env var — referenced but its semantics do NOT change in Phase 3 (still controls `place_bet`'s real-vs-dry path). (c) `DATABASE_URL`, `API_TOKEN`, `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY` — unaffected. | None — code rename only, no env var rename. |
| Build artifacts / installed packages | (a) **S3 backup (`s3://${DB_BACKUP_BUCKET}/backups/latest.db`):** snapshots of `predictions.db` taken every 30 min by `backup_loop` (`scanner.py:1015-1019`). Old backups still reference the OLD table name. After deploy, the next backup will contain the new schema. (b) **API lifespan startup** (`api.py:237`) downloads the **latest** S3 backup before `init_db()` runs — this is the critical path: an old backup gets the migration applied at startup. (c) No compiled binaries, no pip egg-info — `predictions` is installed via `hatchling` from `src/`, not via a build step that produces stale artifacts. | (a) **The pre-deploy gate from STR-04 / D-03 is exactly this concern.** Test the rename migration against a downloaded current S3 backup locally: `python -c "from predictions.db import init_db; init_db()"` against a copy of `latest.db`, then `sqlite3 latest.db ".tables"` should show `stretch_opportunities_archived`. (b) After deploy, monitor first backup_loop iteration in scanner.log for any errors. |

**Operational meaning of D-03's "test against an S3 backup copy locally":**

```bash
# Download current production backup (read-only)
aws s3 cp s3://${DB_BACKUP_BUCKET}/backups/latest.db /tmp/prod-backup.db --no-progress

# Apply Phase 3 migration locally
DATABASE_URL="sqlite:////tmp/prod-backup.db" uv run python -c "from predictions.db import init_db; init_db()"

# Verify rename happened, no data lost, original table is gone
sqlite3 /tmp/prod-backup.db ".tables" | tr ' ' '\n' | sort
# Expect: stretch_opportunities_archived (PRESENT), stretch_opportunities (ABSENT)

sqlite3 /tmp/prod-backup.db "SELECT COUNT(*) FROM stretch_opportunities_archived;"
# Expect: same count as production stretch_opportunities pre-migration

sqlite3 /tmp/prod-backup.db "PRAGMA table_info(trades);" | grep strategy_name
# Expect: line showing strategy_name column was added
```

The migration is intended to be **idempotent**, so running `init_db()` twice should be a no-op the second time. Verify:

```bash
DATABASE_URL="sqlite:////tmp/prod-backup.db" uv run python -c "from predictions.db import init_db; init_db()"
# Should run cleanly; rename guard prevents double-rename
```

## Common Pitfalls

### Pitfall 1: Settlement filter type-safety under SQLAlchemy with `dry_run==False`

**What goes wrong:** `Trade.dry_run == False` triggers `ruff` E712 by default (comparison to False). The current code uses `Trade.dry_run == False` with `# noqa: E712` or relies on the global ignore.
**Why it happens:** `is False` doesn't generate the SQL the ORM needs; the `==` form is required for SQL emission, but Python's `==` operator on a `Boolean` column expression is what produces the correct WHERE clause.
**How to avoid:** [VERIFIED] `pyproject.toml:32` already lists E712 in `[tool.ruff.lint] ignore`, so no `# noqa` is needed. Use `Trade.dry_run == False` and `Trade.dry_run == True` directly.
**Warning signs:** Lint passes locally but a CI environment with stricter ruff config flags it. If you see E712 errors, do NOT switch to `Trade.dry_run.is_(False)` — that emits `IS FALSE`, which is non-portable on SQLite.

### Pitfall 2: `trading_paused` check placement — D-15 vs. existing pattern

**What goes wrong:** D-15 says the gate happens "inside `place_strategy_trade`, not at the loop level." But the existing live-trade pattern at `scanner.py:523` checks `trading_paused` at the **loop level**, inside `scan_kalshi_with_espn`, BEFORE calling `place_bet`. The note in D-15 says "verify exact paused check location in current `place_bet` flow; if it's loop-level today, mirror that placement consistently. Goal is parity with live trades, not a new pattern."
**Why it happens:** Two valid placements (loop-level vs. callee-level) have different observability profiles. Loop-level has fewer DB writes when paused (no Trade row); callee-level keeps strategy evaluation simpler.
**How to avoid:** [VERIFIED] Existing pattern at `scanner.py:523` is **loop-level inside `scan_kalshi_with_espn`** for live trades. To preserve the "parity with live trades" goal stated in D-15's note, implement `trading_paused` at the **loop level inside `evaluate_strategies`**, identical placement to `scan_kalshi_with_espn:523`. The CONTEXT.md prose ("inside place_strategy_trade") is in tension with the verified existing pattern. Suggest the planner pick the parity option (loop-level), and document the deviation from D-15's prose explicitly in PLAN.md so Discuss can re-affirm.
**Warning signs:** Two `trading_paused` checks (loop-level + callee-level) — that's worse than either single placement, because you can pause between the check and the write.

### Pitfall 3: Idempotent rename — running on a freshly-created DB

**What goes wrong:** On a fresh `predictions.db` (e.g., a new dev environment), `Base.metadata.create_all(engine)` runs FIRST and the `stretch_opportunities` table will exist (because the ORM model is still mapped at first DB init). After D-20 deletes the model, `create_all` won't create the table on a truly fresh DB — but the rename guard `if "stretch_opportunities" in inspector.get_table_names()` will be False, so no rename happens. That is the intended behavior — a fresh DB has nothing to archive.
**Why it happens:** Migration guards are pre-conditions on existing tables. On fresh DBs, there's nothing to migrate.
**How to avoid:** Order matters in `init_db()`:
1. `Base.metadata.create_all(engine)` — creates all currently-mapped tables (the new state, no `StretchOpportunity`).
2. `_migrate_add_columns()` — applies idempotent migrations to existing DBs.
On a fresh DB, the `stretch_opportunities_archived` table does NOT get created (no ORM mapping for it), and the rename guard is false. Both correct.
**Warning signs:** Test asserts that `stretch_opportunities_archived` exists on a fresh DB — that test would be wrong; the table only exists on upgraded DBs.

### Pitfall 4: SQLAlchemy session/connection holding old table handle during rename

**What goes wrong:** SQLite supports `ALTER TABLE ... RENAME TO` but other open connections holding a prepared statement against the old name will get a "no such table" error on next reuse.
**Why it happens:** SQLite's compiled prepared statements bind table names at compile time.
**How to avoid:** [VERIFIED] `_migrate_add_columns` runs inside `init_db()`, which runs on API lifespan startup BEFORE the scanner is spawned. There are no concurrent connections at that moment — the FastAPI app hasn't started accepting requests yet, and the scanner async task is created AFTER `init_db()` returns (`api.py:238 → asyncio.create_task(_run_scanner_loop())`). [VERIFIED at `api.py:234-256`]
**Warning signs:** Any new code that calls `init_db()` from a non-startup path (e.g., a "force rerun migrations" endpoint).

### Pitfall 5: `evaluate_strategies` running on `current_open_markets` — what does that set look like?

**What goes wrong:** Phase 3 D-04 says `evaluate_strategies` reuses `market_prices` cache and ESPN cache, but `scan_kalshi_with_espn` already filters markets by `has_liquidity`, expiration time, and price-range — those filters happen at lines 351-374 of `scan_kalshi_with_espn`. If `evaluate_strategies` iterates a different "current_open_markets" set, it could match markets that the live-trade path already excluded.
**Why it happens:** "Markets" is ambiguous in the locked decisions. D-06's pseudocode says `for market in current_open_markets:` without specifying what builds that list.
**How to avoid:** Iterate `market_prices` (the WS-populated dict). Filter inline:
- `yes_ask` present in cache (skip if `market_prices[ticker]` is empty)
- volume sanity (`volume >= MIN_VOLUME` — same threshold as live trades)
- ticker matches a Kalshi market currently in `subscribed_tickers`
- ESPN game found via `match_kalshi_to_espn(ticker, ?, espn_games)` — note the second argument is `kalshi_title`; the WS cache doesn't carry titles, so either reconstruct from event lookup or carry titles in `market_prices[ticker]`. **This is a real edge** — see Open Questions.
**Warning signs:** `evaluate_strategies` writes Trade rows for tickers that have stale prices (no recent WS update) or for markets that are no longer "open."

### Pitfall 6: First-trigger-wins vs. log-on-skip

**What goes wrong:** D-12's "first-trigger-wins per (strategy, market) tick" + D-10's "per-strategy dedupe" interact. After a fire, subsequent ticks for the same `(strategy, ticker)` skip via DB query (D-10) — that's fine. But within ONE tick, if trigger #2 of the same strategy ALSO matches, D-12 says we've already broken; trigger #2 doesn't fire.
**Why it happens:** The combined dedupe + first-fire logic must short-circuit at the right scope.
**How to avoid:** Match the YAML order: `for trigger in strategy.triggers: if trigger_matches(...): fire; break`. This is YAML-order-dependent — the order strategies appear in `triggers:` matters. [VERIFIED: `strategies.py` preserves YAML insertion order via Python 3.7+ dict iteration, lines 96-100.]
**Warning signs:** Test that two triggers in one strategy match the same market and BOTH fire (would produce two Trade rows for the same `(strategy, ticker)` — wrong).

### Pitfall 7: `match_kalshi_to_espn` requires `kalshi_title`; `market_prices` cache doesn't have it

**What goes wrong:** `match_kalshi_to_espn(kalshi_ticker, kalshi_title, espn_games)` (`espn.py:232`) uses BOTH the ticker AND the title to disambiguate (e.g., for soccer fuzzy matching). The `market_prices` dict only stores prices, not titles. `evaluate_strategies` calling `match_kalshi_to_espn(ticker, ???, espn_games)` lacks the title.
**Why it happens:** The WS ticker stream doesn't carry market titles; titles come from REST `/events`.
**How to avoid:** Two options:
1. Carry `title` in `market_prices[ticker]` — extend `on_ticker` and the kalshi-loop seed to populate it. **Adds a field to a shared cache** — flag blast radius.
2. Pass empty string for title; rely on ticker-only matching. May miss soccer fuzzy fallback (`espn.py:261-278`).

The cleanest path is #1 — add `"title": title` and `"event_ticker": event_ticker` to the `market_prices` seed at `scanner.py:954-957` (kalshi loop already has both available). Document as a small additive shape change.
**Warning signs:** soccer triggers fire less often than expected because fuzzy-title fallback doesn't activate.

## Code Examples

### Example 1: `evaluate_strategies` skeleton (D-04, D-06, D-10, D-12, D-15)

```python
# Source: composes existing scanner.py patterns (lines 469-527)
async def evaluate_strategies(
    session,
    espn_final_period: dict,
    max_bet_cents: int,
):
    """Per-iteration: evaluate every loaded strategy against every live market.

    Mirrors scan_kalshi_with_espn's session/loop discipline. Errors
    inside the loop are logged and the loop continues — no raise.
    """
    if get_config("trading_paused") == "true":
        log.info("evaluate_strategies: trading paused via config — skipping tick")
        return  # parity with live-trade path; mirrors scanner.py:523

    try:
        strategies = load_strategies()
    except Exception as e:
        # load_strategies catches its own errors and returns []; this except
        # is defense-in-depth.
        log.warning("evaluate_strategies: failed to load strategies: %s", e)
        return
    if not strategies:
        return

    # Pre-load existing (strategy_name, ticker) tuples for dedupe (D-10)
    existing = {
        (sn, t)
        for (sn, t) in session.query(Trade.strategy_name, Trade.ticker)
        .filter(Trade.strategy_name.isnot(None))
        .all()
    }

    fired_this_tick = 0
    for series_ticker, espn_games in espn_final_period.items():
        for game in espn_games:
            sport_path = game.sport_path
            family = SPORT_PATH_TO_FAMILY.get(sport_path)
            elapsed = elapsed_minutes(sport_path, game.clock_seconds, game.period)

            # Find the market(s) for this game from market_prices cache
            for ticker, prices in list(market_prices.items()):
                yes_ask = prices.get("yes_ask")
                volume = prices.get("volume", 0)
                if not yes_ask or volume < MIN_VOLUME:
                    continue

                # Match this market to this game (mirrors scan_kalshi_with_espn)
                title = prices.get("title", "")  # see Pitfall #7
                if not match_kalshi_to_espn(ticker, title, [game]):
                    continue

                for strategy in strategies:
                    if (strategy.name, ticker) in existing:
                        continue  # D-10 dedupe

                    for trigger in strategy.triggers:
                        if not trigger_matches(
                            trigger,
                            family=family,
                            sport_path=sport_path,
                            elapsed_minutes=elapsed,
                            score_diff=game.score_diff,
                            yes_ask=yes_ask,
                        ):
                            continue
                        # Fire. D-12 first-trigger-wins.
                        try:
                            place_strategy_trade(
                                session=session,
                                opp={
                                    "ticker": ticker,
                                    "event_ticker": prices.get("event_ticker", ""),
                                    "title": title,
                                    "yes_ask": yes_ask,
                                    "espn_clock_seconds": int(game.clock_seconds),
                                },
                                strategy_name=strategy.name,
                                max_cost_cents=max_bet_cents,
                            )
                            existing.add((strategy.name, ticker))
                            fired_this_tick += 1
                        except Exception as e:
                            log.warning(
                                "place_strategy_trade failed for "
                                "strategy=%s ticker=%s: %s",
                                strategy.name, ticker, e,
                            )
                        break  # D-12: stop scanning triggers in this strategy

    if fired_this_tick:
        log.info("evaluate_strategies: fired %d strategy trades", fired_this_tick)


def trigger_matches(
    trigger,
    *,
    family: str | None,
    sport_path: str,
    elapsed_minutes: int | None,
    score_diff: int,
    yes_ask: int,
) -> bool:
    """All-AND match. Missing field on trigger = no constraint (Phase 2 D-03)."""
    if trigger.sport is not None and trigger.sport != family:
        return False
    if trigger.min_minute is not None:
        if elapsed_minutes is None:
            # Clockless sport — log + skip THIS trigger (not the strategy)
            return False
        if elapsed_minutes < trigger.min_minute:
            return False
    if trigger.min_lead is not None and score_diff < trigger.min_lead:
        return False
    if trigger.min_yes_price is not None and yes_ask < trigger.min_yes_price:
        return False
    if trigger.max_yes_price is not None and yes_ask > trigger.max_yes_price:
        return False
    return True
```

### Example 2: `place_strategy_trade` (D-13, D-14, D-18 entry math)

```python
# Source: mirrors scanner.py:127-200 (place_bet) for session lifecycle
def place_strategy_trade(
    session,
    opp: dict,
    strategy_name: str,
    max_cost_cents: int,
):
    """Write a dry-run Trade row from a strategy fire. Never calls Kalshi REST.

    No fee_cents (no real order). status='dry_run' until settlement.
    """
    yes_price = opp["yes_ask"]
    if not yes_price:
        log.warning("place_strategy_trade: missing yes_ask for %s", opp["ticker"])
        return
    count = max_cost_cents // yes_price
    if count < 1:
        log.info(
            "place_strategy_trade %s: cannot afford any contracts at %dc "
            "(budget %dc)",
            strategy_name, yes_price, max_cost_cents,
        )
        return

    total_cost = count * yes_price
    total_profit = count * (100 - yes_price)
    log.info(
        "STRATEGY FIRE %s: BUY %dx YES %s @ %dc = $%.2f cost, $%.2f potential",
        strategy_name, count, opp["ticker"], yes_price,
        total_cost / 100, total_profit / 100,
    )

    trade = Trade(
        ticker=opp["ticker"],
        event_ticker=opp.get("event_ticker", ""),
        title=opp.get("title", ""),
        side="yes",
        action="buy",
        count=count,
        yes_price=yes_price,
        cost_cents=total_cost,
        potential_profit_cents=total_profit,
        status="dry_run",
        dry_run=True,
        strategy_name=strategy_name,
        espn_clock_seconds=opp.get("espn_clock_seconds"),
    )
    session.add(trade)
    session.commit()
```

### Example 3: D-16 combined filter applied to `check_settlements`

```python
# Source: scanner.py:203-239 (current); D-16 modification
from sqlalchemy import or_, and_

async def check_settlements(client: KalshiClient):
    """Check open trades for settlement and update P&L."""
    session = get_session()
    open_trades = (
        session.query(Trade)
        .filter(
            Trade.status.in_(("placed", "filled", "dry_run")),
            or_(
                Trade.dry_run == False,
                and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),
            ),
        )
        .all()
    )

    for trade in open_trades:
        try:
            market = await client.get_market(trade.ticker)
            status = market.get("status", "")
            result = market.get("result", "")

            if status not in ("finalized", "settled"):
                continue

            fee = trade.fee_cents or 0  # 0 for strategy dry-runs (D-18)
            if result == trade.side:
                trade.status = "settled_win"
                trade.pnl_cents = trade.potential_profit_cents - fee
                log.info(
                    "  %s WIN: %s | P&L: +$%.2f",
                    "STRATEGY" if trade.strategy_name else "REAL",
                    trade.ticker, trade.pnl_cents / 100,
                )
            else:
                trade.status = "settled_loss"
                trade.pnl_cents = -trade.cost_cents - fee
                log.info(
                    "  %s LOSS: %s | P&L: -$%.2f",
                    "STRATEGY" if trade.strategy_name else "REAL",
                    trade.ticker, abs(trade.pnl_cents) / 100,
                )
        except Exception as e:
            log.warning("  Failed to check %s: %s", trade.ticker, e)

    session.commit()
    session.close()
```

### Example 4: D-17 mirroring filter in `on_lifecycle`

```python
# Source: scanner.py:828-880 (current); D-17 modification
async def on_lifecycle(msg: dict):
    data = msg.get("msg", {})
    ticker = data.get("market_ticker", "")
    new_status = data.get("market_status", "")
    result = data.get("result", "")

    if new_status not in ("finalized", "settled") or not ticker:
        return

    log.info("WS lifecycle: %s -> %s result=%s", ticker, new_status, result)
    session = get_session()
    open_trades = (
        session.query(Trade)
        .filter(
            Trade.ticker == ticker,
            Trade.status.in_(("placed", "filled", "dry_run")),
            or_(
                Trade.dry_run == False,
                and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),
            ),
        )
        .all()
    )
    for trade in open_trades:
        fee = trade.fee_cents or 0
        if result == trade.side:
            trade.status = "settled_win"
            trade.pnl_cents = trade.potential_profit_cents - fee
        else:
            trade.status = "settled_loss"
            trade.pnl_cents = -trade.cost_cents - fee
    # NOTE: stretch opportunities update block deleted per D-20
    session.commit()
    session.close()
    await record_balance(client)
```

### Example 5: D-19 `/api/sport-stats` re-source

```python
# Source: api.py:484-554; D-19 modification
@app.get("/api/sport-stats", dependencies=[Depends(_check_token)])
def get_total_sport_stats():
    session = get_session()
    from sqlalchemy import text

    seen_matches = session.execute(
        text(
            "SELECT series_ticker, COUNT(DISTINCT event_ticker) "
            "FROM opportunities "
            "WHERE series_ticker IS NOT NULL "
            "GROUP BY series_ticker"
        )
    ).fetchall()

    real_trades = (
        session.query(Trade.ticker, Trade.status, Trade.pnl_cents)
        .filter(Trade.status.in_(("settled_win", "settled_loss")))
        .filter(Trade.dry_run == False)
        .all()
    )
    session.close()
    # Aggregation logic below is unchanged from current implementation.
```

The `WHERE series_ticker IS NOT NULL` is defensive — `Opportunity.series_ticker` is populated by `scan_kalshi_with_espn` (`scanner.py:495`) on every row written, so in practice all rows have it. But the column is nullable in the schema (`db.py:43`), so the filter is correct.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded `WHAT_IF_STRATEGIES` dict in scanner.py | YAML-driven `strategies.yaml` + Pydantic loader | Phase 2 (2026-04-30) | Phase 3 deletes the hardcoded dict and the parallel evaluation function. |
| `StretchOpportunity` table for both near-miss tracking AND what-if shadow trades | `Trade` rows with `strategy_name` for what-if; `Opportunity` for opportunities | Phase 3 (this phase) | Single source of truth per concept; settlement logic unifies. |
| `dry_run==False` in settlement filters | Combined `or_(dry_run==False, and_(dry_run==True, strategy_name IS NOT NULL))` | Phase 3 D-16/D-17 | Strategy dry-runs settle alongside real trades. Process-level dry-runs (debug toggle) remain diagnostic-only. |
| `connect_args={"check_same_thread": False}` only | `+ "timeout": 5` | Phase 3 D-02 | Prevents `SQLITE_BUSY` under analytics polling (Phase 4). |

**Deprecated/outdated:**
- `_evaluate_what_if_strategies` (`scanner.py:580`) — replaced by `evaluate_strategies` + `place_strategy_trade`.
- `check_stretch_settlements` (`scanner.py:710`) — no callers after D-20 removes the call site at `scanner.py:998`. **D-20 doesn't list this function explicitly** — see Open Questions. Verified at `scanner.py:710-747`.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | ESPN soccer `clock_seconds` is cumulative across the match (45:00 at half, 90:00 at full), not period-relative. | Architecture Patterns / Pattern 3 | If wrong, soccer triggers with `min_minute >= 45` would never fire in second half. Empirical check needed against a live ESPN soccer scoreboard. Mitigation: existing `espn.py:88` already uses `clock_seconds >= 4500` (75 min) as a threshold — that comparison only makes sense if the clock is cumulative, so the assumption is corroborated by current production code. |
| A2 | `KXTENNISGAME` series exists in `SPORTS_GAME_SERIES` but is unmatched against ESPN today (no `tennis/atp` or `tennis/wta` in `KALSHI_TO_ESPN`). | Standard Stack / sport_paths table | If a future Kalshi tennis market matches, the family→path map needs a tennis entry. Not blocking for Phase 3. |
| A3 | The pre-deploy gate "test against an S3 backup copy locally" means: download `s3://${DB_BACKUP_BUCKET}/backups/latest.db`, apply `init_db()` against it, verify rename happened. | Runtime State Inventory | If the user intended a different test (e.g., a separate `mode='replica'` SQLite session), the gate is wrong. Low risk — the operational meaning above is the natural reading. |
| A4 | The dashboard's "What If? Strategy Comparison" UI block (`page.tsx:2618-2674`) consuming `/api/stretch-stats` is something the user wants to keep functional. | Open Questions Q1 | If the user has already decided the UI block is dead alongside the WHAT_IF removal, the path is simpler (delete the endpoint + UI). Surface to user. |

## Open Questions (RESOLVED)

> All six open questions below have been resolved by user decisions in 03-CONTEXT.md (D-21, D-22, D-23) and pitfall mitigations carried into Plan 03-03. Resolutions are appended at the end of each question.

1. **`/api/stretch-stats` and `/api/stretch` DELETE endpoints — D-20 does not list them, but they break when `StretchOpportunity` is deleted.**
   - What we know: `api.py:826-878` (`get_stretch_stats`) imports `WHAT_IF_STRATEGIES` and queries `StretchOpportunity` directly. `api.py:881-895` (`clear_stretch_opportunities`) queries the same model. The dashboard `page.tsx:2618-2674` consumes `/api/stretch-stats` to render the "What If? Strategy Comparison" tab.
   - What's unclear: Does the user want to (a) delete these endpoints + the dashboard tab now, (b) port `/api/stretch-stats` to read from `Trade` rows filtered by `strategy_name` (which Phase 4 will consume anyway via DASH-03), or (c) leave them functional against `stretch_opportunities_archived` as an audit-only read path?
   - Recommendation: **Surface to user (Discuss-style follow-up).** Option (a) is the cleanest if Phase 4 will replace the UI. Option (b) is a Phase-3-vs-Phase-4 boundary question — DASH-03 (Phase 4) will build a new analytics page anyway, so porting these endpoints now is throw-away work. The plan should explicitly choose; default recommendation is **(a) delete — let Phase 4 build the replacement**, and add a one-line dashboard hide for the `mainTab === "strategy"` block.

2. **`tests/test_sport_stats.py` imports `StretchOpportunity` (lines 4, 27, 35).**
   - What we know: The test seeds two `StretchOpportunity` rows to verify `/api/sport-stats`'s MLB/MLBST distinction.
   - What's unclear: After D-19 re-sources from `opportunities`, the test seed needs to use `Opportunity` rows instead. Trivial change but **D-20 doesn't list this test file**.
   - Recommendation: Plan task to migrate `test_sport_stats.py` to seed `Opportunity` rows. Update assertions to reflect `COUNT(DISTINCT event_ticker)` semantics.

3. **`check_stretch_settlements` function (`scanner.py:710-747`) is called at `scanner.py:998` — D-20 lists removing line 998's call but not the function definition.**
   - What we know: The function queries `StretchOpportunity` directly. After `StretchOpportunity` is deleted, the function won't import.
   - Recommendation: Add to D-20 removal list explicitly. Plan task should grep for `check_stretch_settlements` and confirm zero remaining callers.

4. **`market_prices` cache lacks `title` and `event_ticker` (Pitfall #7).**
   - What we know: `match_kalshi_to_espn(ticker, title, espn_games)` uses both. The kalshi loop seed (`scanner.py:954-957`) has both available; the WS `on_ticker` (`scanner.py:813-826`) does not.
   - What's unclear: Whether to extend `market_prices` shape (additive) or pass empty title (degraded soccer matching).
   - Recommendation: Extend `market_prices[ticker]` with `"title"` and `"event_ticker"` at the kalshi-loop seed. WS updates won't backfill these but the seed always runs first and never gets cleared. Document the shape change as additive (no consumer breaks — existing readers use `.get()` semantics).

5. **`current_open_markets` set construction in `evaluate_strategies` (Pitfall #5).**
   - What we know: D-06 pseudocode iterates `current_open_markets` without specifying the source.
   - Recommendation: Iterate `market_prices` (WS-populated, scanner.py module-level), filter by volume + ESPN match (matches the live-trade pipeline's eligibility checks). Document the filter set in PLAN.md.

6. **D-15 prose vs. existing pattern (Pitfall #2) — `trading_paused` placement.**
   - What we know: D-15 prose says "inside `place_strategy_trade`"; existing live-trade pattern is loop-level inside `scan_kalshi_with_espn:523`.
   - Recommendation: Pick loop-level (parity with live trades). Document the deviation from D-15's prose in PLAN.md so the planner-checker can confirm.

### Resolutions (per 03-CONTEXT.md and Plan 03-03)

| Q | Resolved by | Implementation |
|---|-------------|----------------|
| Q1 — `/api/stretch-stats` + `/api/stretch` DELETE + dashboard tab | **D-21** (option a) | Plan 03-04 deletes both endpoints, the `StretchStatsResponse` + `StrategySetStats` models, the `_compute_stretch_stats` helper, and the dashboard "Strategy" tab + `stretchStats` state. Phase 4 (DASH-03) will build the replacement analytics surface. |
| Q2 — `tests/test_sport_stats.py` imports `StretchOpportunity` | **D-22** (covered by D-19/D-21 scope) | Plan 03-04 migrates the test seed from `StretchOpportunity` to `Opportunity` rows; assertions updated to `COUNT(DISTINCT event_ticker)` semantics. |
| Q3 — `check_stretch_settlements` function definition orphaned | **D-22** (added explicitly to D-20 removal list) | Plan 03-03 Task 3 Edit 3 deletes the entire `check_stretch_settlements` function body alongside the call-site removal in Task 2b. Verified by negative grep in Task 3 verify command. |
| Q4 — `market_prices` cache lacks `title` and `event_ticker` (Pitfall #7) | **Pitfall #7 mitigation** in Plan 03-03 Task 2b Edit 1 | The `kalshi_scan_loop` market_prices seed is extended to include `title` and `event_ticker` from the events response. Additive shape change — existing `.get()` consumers unbroken. Documented in plan's must_haves and SUMMARY. |
| Q5 — `current_open_markets` source for D-06 iteration (Pitfall #5) | **Pitfall #5 mitigation** in Plan 03-03 Task 2b Edit 2 | `evaluate_strategies` iterates `market_prices.items()` (WS-populated, scanner.py module-level), filters by volume ≥ MIN_VOLUME, then by ESPN match via `match_kalshi_to_espn`. Documented in the function docstring. |
| Q6 — `trading_paused` placement (D-15 prose vs. existing pattern, Pitfall #2) | **D-23** (supersedes D-15) | Plan 03-03 places the `get_config("trading_paused") == "true"` early-return at the TOP of `evaluate_strategies` (loop-level, mirrors the live-trade pattern at scanner.py:523-525). D-23 is the binding decision; D-15's prose is governed by D-23. |

## Environment Availability

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| `uv` | Python tooling, ruff/ty/pytest | ✓ | (project locked) | — |
| `python` | Runtime | ✓ | 3.13 (per pyproject) | — |
| `sqlalchemy` | ORM + or_/and_/text() | ✓ | 2.0.48 | — |
| `pyyaml` | Strategy loader | ✓ | >=6.0 (locked Phase 2) | — |
| `pydantic` | Strategy schema | ✓ | (transitive via FastAPI) | — |
| `pytest` + `pytest-asyncio` | Test runner | ✓ | >=8.0 / >=0.24 | — |
| AWS CLI / `aws` command | D-03 pre-deploy gate (S3 backup test) | unverified | — | Skip gate, document in DEPLOY checklist instead. **Planner should verify locally.** |
| `sqlite3` CLI | D-03 pre-deploy gate verification | typically present on Linux/macOS dev boxes | — | Use `python -c "import sqlite3"` shell instead. |
| Live ESPN scoreboard sample (soccer) | A1 verification (cumulative-clock) | unverified at research time | — | Manual fetch via curl during planning, or accept the assumption with the caveat documented. |

**Missing dependencies with no fallback:** None (all critical deps present).

**Missing dependencies with fallback:** AWS CLI for the pre-deploy gate. If absent, the gate's S3 download step needs a fallback (boto3 Python script) — but `boto3` IS in pyproject.toml deps, so a 5-line Python script using `boto3.client('s3').download_file` is trivial.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | `pytest` >= 8.0 + `pytest-asyncio` >= 0.24 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` (lines 39-41) |
| Quick run command | `uv run pytest tests/test_scanner_strategies.py -x` (per-task) |
| Full suite command | `uv run pytest tests/` (per-wave merge + phase gate) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STR-04 | `stretch_opportunities` renamed (not dropped); table `stretch_opportunities_archived` exists with same row count | unit (migration) | `uv run pytest tests/test_db_migrations.py::test_rename_stretch_opportunities -x` | ❌ Wave 0 |
| STR-04 | `_migrate_add_columns()` is idempotent — running it twice on a renamed DB is a no-op | unit (migration) | `uv run pytest tests/test_db_migrations.py::test_rename_idempotent -x` | ❌ Wave 0 |
| STR-04 | `WHAT_IF_STRATEGIES` is no longer importable from `predictions.scanner` | unit (deletion) | `uv run pytest tests/test_scanner_strategies.py::test_what_if_strategies_removed -x` | ❌ Wave 0 |
| STR-04 | `/api/sport-stats` returns counts derived from `opportunities`, with `COUNT(DISTINCT event_ticker)` semantics | unit (API) | `uv run pytest tests/test_sport_stats.py -x` | ✓ (modify existing) |
| DRY-01 | Strategy trigger fire writes `Trade(dry_run=True, strategy_name=<name>, yes_price=<live yes_ask>)` and does NOT call Kalshi REST | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_evaluate_strategies_fires_dry_run_trade -x` | ❌ Wave 0 |
| DRY-01 | Process-level `DRY_RUN` env var does NOT change strategy fire behavior (always `dry_run=True`) | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_strategy_fire_independent_of_dry_run_env -x` | ❌ Wave 0 |
| DRY-01 | First-trigger-wins per `(strategy, market)` tick — only one Trade row per fire even when multiple triggers match | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_first_trigger_wins -x` | ❌ Wave 0 |
| DRY-01 | Per-strategy dedupe — re-evaluation of the same `(strategy, ticker)` does NOT write a second Trade row | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_per_strategy_dedupe -x` | ❌ Wave 0 |
| DRY-01 | Multiple distinct strategies CAN fire on the same ticker (one Trade row each) | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_multi_strategy_fire_same_ticker -x` | ❌ Wave 0 |
| DRY-01 | `trading_paused == "true"` blocks strategy trade writes (success criterion #3) | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_trading_paused_blocks_strategy_fire -x` | ❌ Wave 0 |
| DRY-01 | `elapsed_minutes()` returns correct values for soccer (count-up), basketball (count-down), and `None` for baseball | unit (pure) | `uv run pytest tests/test_scanner_strategies.py::test_elapsed_minutes_per_sport -x` | ❌ Wave 0 |
| DRY-01 | `SPORT_PATH_TO_FAMILY` lookup returns `football` for soccer paths, `basketball` for NBA, etc. | unit (pure) | `uv run pytest tests/test_scanner_strategies.py::test_sport_path_to_family -x` | ❌ Wave 0 |
| DRY-02 | New `Trade.strategy_name` column accepts NULL (legacy rows) and string (new rows); index exists | unit (schema) | `uv run pytest tests/test_db_migrations.py::test_strategy_name_column -x` | ❌ Wave 0 |
| DRY-02 | `check_settlements` (REST fallback) updates `dry_run=True AND strategy_name IS NOT NULL` rows | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_check_settlements_updates_strategy_trades -x` | ❌ Wave 0 |
| DRY-02 | `on_lifecycle` (WS primary) updates the same trade set as `check_settlements` (D-17 symmetry) | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_on_lifecycle_updates_strategy_trades -x` | ❌ Wave 0 |
| DRY-02 | Win P&L: `count × (100 − yes_price)`; loss P&L: `−count × yes_price`; no fee | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_strategy_pnl_math -x` | ❌ Wave 0 |
| DRY-02 | `check_settlements` does NOT update legacy process-level dry-runs (`dry_run=True AND strategy_name IS NULL`) | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_legacy_dry_runs_not_settled -x` | ❌ Wave 0 |
| (success #5) | `engine.connect_args` includes `"timeout": 5` | unit (config) | `uv run pytest tests/test_db_migrations.py::test_engine_timeout -x` | ❌ Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_scanner_strategies.py tests/test_strategy_settlement.py tests/test_db_migrations.py -x` (the three new files; quick gate, ~5s)
- **Per wave merge:** `uv run pytest tests/` (full suite — includes Phase 1 backtest tests, Phase 2 strategies tests, Phase 3 new tests; <30s)
- **Phase gate:** Full suite green AND `uv run ruff check . && uv run ruff format --check . && uv run ty check` AND a manual smoke test of the scanner against the local DB (boot `pnpm dev:api`, watch scanner.log for one strategy fire, verify Trade row written with `strategy_name`).

### Wave 0 Gaps
- [ ] `tests/test_scanner_strategies.py` — covers DRY-01 (eval, dedupe, paused, helpers)
- [ ] `tests/test_strategy_settlement.py` — covers DRY-02 (WS + REST symmetry, P&L math)
- [ ] `tests/test_db_migrations.py` — covers STR-04 (rename) + DRY-02 (column add) + success #5 (timeout)
- [ ] `tests/test_sport_stats.py` — MODIFY existing to seed `Opportunity` instead of `StretchOpportunity`
- [ ] **No new fixtures needed** — `tests/conftest.py::isolated_db` covers all the above. Tests construct `Trade`, `Opportunity`, `Strategy` (Pydantic) inline.
- [ ] **No framework install needed** — pytest + pytest-asyncio already in `[dependency-groups] dev` (`pyproject.toml:43-49`).

### Manual / Out-of-band Verification (NOT automated)

These cannot be unit-tested in CI because they require live external state:

1. **D-03 pre-deploy gate** (S3 backup roundtrip) — manual `aws s3 cp` + local `init_db()` against backup copy. Documented in PLAN.md as a deploy-time checklist item.
2. **A1 — soccer cumulative-clock assumption** — manual `curl https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard` and inspect `displayClock` and `period` fields on a live second-half match.
3. **End-to-end strategy fire on production-like data** — boot scanner with `strategies.yaml` containing one wide-trigger strategy (e.g., `min_minute: 30, min_lead: 1`), watch `scanner.log` for a fire, verify `Trade` row written.
4. **Dashboard `/api/sport-stats` rendering** — load dashboard, navigate to "Sports" tab, verify the chart still renders sane numbers after the COUNT(DISTINCT event_ticker) semantic shift.

## Security Domain

`security_enforcement` is not explicitly set in this project (no `.planning/config.json` exists — verified). Treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes — `/api/sport-stats` is behind `Depends(_check_token)` | Bearer token via `_check_token()` (`api.py:277-285`); unchanged in Phase 3. |
| V3 Session Management | no | No new session surfaces. |
| V4 Access Control | yes (low-impact) | All API endpoints already require Bearer auth; Phase 3 doesn't add unauthenticated endpoints. |
| V5 Input Validation | yes | `strategies.yaml` is validated at load by Pydantic (`extra="forbid"`, `min_length=1` on triggers). Phase 2 already locked this. No new external input surface in Phase 3. |
| V6 Cryptography | no | No new crypto. |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML deserialization arbitrary code execution (`!!python/object`) | Tampering | `yaml.safe_load` (already used in `strategies.py:69`); rejects `!!python/*` tags. Verified by `tests/test_strategies.py::test_yaml_safe_load_rejects_python_object_tags`. |
| SQL injection in raw `text()` queries | Tampering | The `/api/sport-stats` query uses static SQL with no user input. The settlement filter uses ORM expression language (parameterized). Phase 3 introduces no user-input → SQL paths. |
| Index-aware DoS via large `Trade.strategy_name` column | Resource | The `strategy_name` column is bounded by YAML strategy keys (typically <100 entries); no user input → DB. Index is fine. |
| Race between WS `on_lifecycle` and REST `check_settlements` updating the same trade twice | Information disclosure / data integrity | Both code paths transition `placed/filled/dry_run` → `settled_*`. The status check `if status not in ("finalized","settled"): continue` filters terminal states; if one path settles first, the other re-runs the math but the result is identical (same `result` from Kalshi). No double-settlement risk. Optional defense: add `Trade.status.in_(("placed","filled","dry_run"))` filter (already present per D-16). |
| Leaking `STRATEGIES_PATH` value via logs | Information disclosure | Log line `Loaded %d strategies from %s` (`strategies.py:102`) prints the path. Phase 2 reviewed; not a secret in this codebase. |

## Sources

### Primary (HIGH confidence)
- `src/predictions/scanner.py` (1043 lines) — full read; behavioral baseline.
- `src/predictions/db.py` (290 lines) — full read; schema + migration patterns.
- `src/predictions/strategies.py` (104 lines) — full read; Phase 2 loader.
- `src/predictions/espn.py` (280 lines) — full read; GameState + clock semantics.
- `src/predictions/kalshi_client.py:1-80` — extract_cents/extract_volume verified.
- `src/predictions/api.py` (relevant sections, lines 1-280, 484-560, 820-905) — endpoint shapes; consumer of `StretchOpportunity`.
- `tests/conftest.py`, `tests/test_strategies.py`, `tests/test_sport_stats.py` — test patterns + orphan caller of `StretchOpportunity`.
- `dashboard/app/page.tsx:130-160, 2180-2280, 2615-2675` — consumers of `/api/sport-stats` and `/api/stretch-stats`.
- `pyproject.toml` — dep versions, ruff config (E712 globally ignored).
- `.planning/REQUIREMENTS.md`, `.planning/ROADMAP.md`, `.planning/PROJECT.md`, `.planning/STATE.md` — phase scope and constraints.
- `.planning/phases/02-strategy-engine-core/02-CONTEXT.md` lines 482-520 — D-02 OVERRIDE and D-11 retraction.
- `.planning/phases/03-scanner-integration/03-CONTEXT.md` — full D-01..D-20 lock.
- `.planning/codebase/ARCHITECTURE.md`, `.planning/codebase/CONVENTIONS.md`, `.planning/codebase/TESTING.md`, `.planning/codebase/STRUCTURE.md` — last mapped 2026-04-30, commit `d010a40`.
- Live verification: `uv run python -c "import sqlalchemy; print(sqlalchemy.__version__)"` → 2.0.48.

### Secondary (MEDIUM confidence)
- SQLite `ALTER TABLE ... RENAME TO` semantics (3.25+, supported in transactions). Standard SQLAlchemy 2.0 behavior on autocommit.
- SQLAlchemy 2.0 `or_`/`and_` import path (`from sqlalchemy import or_, and_`) — standard import; verified to be importable.

### Tertiary (LOW confidence)
- A1: Soccer ESPN cumulative clock — inferred from `espn.py:88` threshold check (cumulative comparison only makes sense if clock is cumulative). Not empirically verified at research time. Recommend manual probe before locking the formula.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all deps already locked, versions verified live.
- Architecture (loop integration, settlement filter, schema migration): HIGH — composes existing primitives; current scanner.py serves as the verified baseline.
- Pitfalls: HIGH — derived from reading the actual current code, not training data.
- Sport family / clock semantics: MEDIUM — sport_path enumeration verified across `KALSHI_TO_ESPN`, `MIN_SCORE_LEAD`, and `_CONFIG_DEFAULTS` (3-way agreement); soccer cumulative-clock assumption flagged as A1.
- Orphan callers in D-20: HIGH — direct grep results presented in Open Questions.
- Validation Architecture: HIGH — uses existing fixtures + framework; gap list is concrete and shippable.

**Research date:** 2026-05-01
**Valid until:** 2026-05-31 (stable scope; Phase 2 outputs locked; only A1 needs an empirical verification before plan execution)

---

*Phase: 03-scanner-integration*
*Researcher: Claude (Opus 4.7 1M)*
*Auto Mode: continuous, autonomous research per user directive*
