# Phase 3: Scanner Integration - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in 03-CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-01
**Phase:** 03-scanner-integration
**Mode:** Auto Mode session — Claude auto-selected recommended defaults; no
interactive AskUserQuestion prompts. User can review/override before
planning by editing 03-CONTEXT.md or running `/gsd-discuss-phase 3`
again without auto mode.
**Areas auto-resolved:** schema migration; strategy evaluation hook & cadence;
sport family ↔ sport_path mapping & game-clock minute semantics;
per-strategy dedupe & multi-strategy fire policy; strategy-driven dry-run
path; settlement reconciliation; `/api/sport-stats` migration; legacy
removal scope.

---

## Schema migration (D-01, D-02, D-03)

| Option | Description | Selected |
|--------|-------------|----------|
| Add `Trade.strategy_name` via existing `_migrate_add_columns()` ALTER pattern | Mirrors how `espn_clock_seconds` and `fee_cents` were added; idempotent | ✓ |
| Add via Alembic migration framework | Heavier; project has no Alembic today; introduces a new dep | |
| Drop+recreate the trades table | Destructive; loses prod history; rejected outright | |

**Selected:** Existing ALTER pattern. **Rationale:** Project has no migration
framework; the existing `_migrate_add_columns()` scaffold is the established
pattern (CONVENTIONS.md). Add `index=True` because Phase 4 analytics will
filter and aggregate by `strategy_name` on a 5-min auto-refresh cadence.

**`stretch_opportunities` archival:**

| Option | Description | Selected |
|--------|-------------|----------|
| `RENAME TO stretch_opportunities_archived` inside `_migrate_add_columns()` | Reversible; preserves data; aligns with ROADMAP success criterion #1 | ✓ |
| `DROP TABLE` per the original REQUIREMENTS.md wording | Destructive; data is intentionally archival per STATE.md decision | |
| Leave the table in place but stop reading from it | Half-measure; still surfaces in inspector tooling as live | |

**Notes:** ROADMAP supersedes REQUIREMENTS — explicitly chose RENAME over
DROP. Pre-deploy gate per STATE.md decision STR-04: test against an S3
backup copy before pushing to prod.

---

## DB connect_args timeout (D-02)

| Option | Description | Selected |
|--------|-------------|----------|
| `connect_args={"check_same_thread": False, "timeout": 5}` | Single-line fix; matches ROADMAP success criterion #5 | ✓ |
| Make timeout configurable via env var | Adds a knob nobody will tune; YAGNI | |
| WAL mode + larger timeout | More invasive; changes durability semantics | |

**Selected:** Hardcode 5s. **Rationale:** Phase 4 analytics polls every
5 min — 5s lock window is wide enough for any contention but short enough
that real deadlocks aren't masked.

---

## Strategy evaluation hook & cadence (D-04, D-05, D-06)

| Option | Description | Selected |
|--------|-------------|----------|
| New `evaluate_strategies()` function called inside `kalshi_scan_loop` | Reuses existing `_evaluate_what_if_strategies` slot; same cadence; no new asyncio task | ✓ |
| Spawn a 5th asyncio loop dedicated to strategy evaluation | New concurrency surface; risks race with `place_bet` budget computation | |
| Run evaluation in a separate thread/process | Conflicts with single-threaded asyncio architecture (ARCHITECTURE.md) | |

**Selected:** Inline in the existing scan loop. **Rationale:** Scanner's
existing concurrency model is "everything in `kalshi_scan_loop` runs serially
per tick"; adding a 5th loop creates new race surface. Reuse the scan loop
pacing (5s) — strategies fire on the same tick as live trades.

**Strategy load cadence:**

| Option | Description | Selected |
|--------|-------------|----------|
| `load_strategies()` once per scan iteration | Cheap; mirrors `get_config_int` re-read pattern; supports hand-edits during testing | ✓ |
| Load once at startup, never reload | No way to test config changes without restart | |
| File-watch + signal-based reload | Hot-reload bookkeeping is deferred (REQUIREMENTS Future Requirements) | |

**Selected:** Per-iteration. **Rationale:** YAML parse + Pydantic validate
is cheap relative to ESPN/Kalshi I/O. No caching, no hot-reload bookkeeping.
Phase 4 may revisit if profiling shows cost matters.

---

## Sport family ↔ sport_path + min_minute (D-07, D-08, D-09)

| Option | Description | Selected |
|--------|-------------|----------|
| `SPORT_FAMILY_TO_PATHS` constant + `SPORT_GAME_LENGTH_SECS` constant in `scanner.py` | Authoritative, co-located with `KALSHI_TO_ESPN`; single drift point | ✓ |
| Extract to `src/predictions/sports.py` module | Possibly cleaner if helpers grow >100 lines (Claude's discretion) | |
| Compute family from sport_path string parsing | Fragile; "soccer/" prefix isn't stable across leagues | |

**Selected:** Constants in `scanner.py`. **Rationale:** Phase 2 D-02 OVERRIDE
locked sport-family literals; needed a reverse mapping. Co-locating with
existing per-sport catalogs keeps the call graph local. Extract only if
helpers grow.

**`min_minute` semantics for clockless sports (baseball, tennis):**

| Option | Description | Selected |
|--------|-------------|----------|
| Log + skip the trigger; do not crash | Matches log-and-continue pattern; documents as known limitation | ✓ |
| Crash with clear error on YAML load if `min_minute` set on clockless sport | Fails loud at startup but trips even when the trigger isn't reachable | |
| Treat innings/sets as "minutes" via mapping | Ambiguous semantics; defer until user actually asks | |

**Selected:** Log + skip. **Rationale:** Permissive logging is the
established scanner pattern. Phase 4+ revisits if real demand emerges.

---

## Per-strategy dedupe & multi-strategy fire policy (D-10, D-11, D-12)

| Option | Description | Selected |
|--------|-------------|----------|
| Dedupe by `(strategy_name, ticker)` — once per strategy per market lifetime | Mirrors how a real position blocks re-entry; per-strategy independence for Phase 4 analytics | ✓ |
| Global ticker dedupe (one trade per market across all strategies) | Loses per-strategy P&L attribution; conflicts with DASH-03 intent | |
| Time-bucketed dedupe (e.g., one fire per strategy per hour) | Adds time-window semantics for unclear benefit | |

**Selected:** Per-`(strategy, ticker)` dedupe. **Rationale:** DRY-02 and
Phase 4 analytics require independent per-strategy trade rows.

**Multi-trigger fire-within-strategy:**

| Option | Description | Selected |
|--------|-------------|----------|
| First-trigger-wins (YAML order) | Mirrors backtest engine D-12 (Phase 2); deterministic | ✓ |
| Best-trigger-wins (e.g., highest min_yes_price match) | Adds preference logic; ambiguous when triggers are orthogonal | |
| Fire on every matching trigger (multiple Trade rows per market per strategy) | Pollutes analytics; conflicts with `(strategy_name, ticker)` dedupe | |

**Selected:** First-trigger-wins, evaluation in YAML order, per Phase 2 D-12.

---

## Strategy-driven dry-run path (D-13, D-14, D-15)

| Option | Description | Selected |
|--------|-------------|----------|
| New `place_strategy_trade()` sibling to `place_bet()`, hardcoded `dry_run=True`, no Kalshi REST | Two distinct code paths for two distinct intents; settlement filter stays unambiguous | ✓ |
| Reuse `place_bet()`'s `dry_run=True` branch | Conflates process-level DRY_RUN debug toggle with strategy analytics dry-run | |
| Compose: `place_bet(..., strategy_name=..., force_dry=True)` | Adds optional kwargs that change semantics; adds risk of misconfiguration in real-trading path | |

**Selected:** New sibling function. **Rationale:** Two intentionally distinct
dry-run modes — one for ops debugging (`DRY_RUN` env), one for strategy
analytics (`strategy_name IS NOT NULL`). Settlement filter (D-16)
distinguishes them. Don't unify.

**Bet sizing:**

| Option | Description | Selected |
|--------|-------------|----------|
| Same `bet_percent × current_balance` as live trades | Matches live-trade budgeting; per-strategy sizing deferred per REQUIREMENTS | ✓ |
| Per-strategy `bet_percent` override in YAML | Future Requirements (REQUIREMENTS.md); deferred | |
| Fixed dollar amount per strategy | Loses bankroll scaling; conflicts with capital-based simulation | |

**`trading_paused` check location:**

| Option | Description | Selected |
|--------|-------------|----------|
| Inside `place_strategy_trade` | Mirrors live-trade pattern; preserves loop-level evaluation bookkeeping | ✓ |
| Loop-level early-exit before evaluation | Slightly cheaper per tick; loses any chance of "would have fired" diagnostics | |

**Selected:** Inside the trade function. **Notes:** Planner should verify
exact paused check location in current `place_bet` flow and mirror that
placement consistently — goal is parity with live trades, not a new pattern.

---

## Settlement reconciliation (D-16, D-17, D-18)

| Option | Description | Selected |
|--------|-------------|----------|
| Single combined OR filter: `dry_run=False OR (dry_run=True AND strategy_name IS NOT NULL)` | One query, both code paths in lockstep, no risk of drift | ✓ |
| Two separate query methods (real settlements + strategy settlements) | Doubles maintenance surface; symmetric behavior is a correctness requirement | |
| Add a new status enum value | Conflicts with the existing `dry_run` status convention | |

**Selected:** Single combined filter. **Rationale:** Settlement duality (WS
primary + REST fallback) means both code paths must update the same set of
trades. Single query enforces this; the WS `on_lifecycle` handler gets the
same filter logic.

**P&L math:**

| Option | Description | Selected |
|--------|-------------|----------|
| Mirror real-trade math: `count × (100 − yes_price)` win, `−count × yes_price` loss; no fee | Same formulas as Phase 1 backtest; analytics can union/aggregate cleanly | ✓ |
| Subtract a synthetic Kalshi-style fee | Adds calibration burden; not needed for v1.2 dry-run analytics | |

---

## /api/sport-stats migration (D-19)

| Option | Description | Selected |
|--------|-------------|----------|
| `SELECT series_ticker, COUNT(DISTINCT event_ticker) FROM opportunities GROUP BY series_ticker` | Aligns with STR-04 ("derive from `opportunities`"); endpoint name matches the new semantic | ✓ |
| Read from `stretch_opportunities_archived` to preserve byte-identical numbers | Archive is intended to be inert; conflicts with STR-04 wording | |
| Drop the endpoint entirely | Dashboard consumes this for per-series indicators | |

**Selected:** Re-source from `opportunities` with `COUNT(DISTINCT
event_ticker)`. **Notes:** This is a behavior change — old number was
"near-miss events per series", new number is "distinct games scanned per
series". Flag in PLAN.md and verify dashboard consumer treats the new
number as still meaningful.

---

## Legacy removal scope (D-20)

Removed list locked in CONTEXT.md D-20. **Notes:**

- `WHAT_IF_STRATEGIES` dict, `_evaluate_what_if_strategies()`,
  `stretch_opps` accumulator, `meets_stretch_lead` branches,
  `_evaluate_what_if_strategies(...)` call site, `StretchOpportunity`
  ORM class, stretch_opportunities migration ALTER columns.
- Removals must pass `uv run ty check` cleanly. Planner flags any
  callers found that aren't on the list.

---

## Claude's Discretion

Captured in 03-CONTEXT.md `<decisions>` § "Claude's Discretion":

- Module location for sport mapping helpers (inline in `scanner.py` vs
  extract to `src/predictions/sports.py`)
- `evaluate_strategies` test seam (functional vs class method)
- Logging cadence for skipped/already-fired entries
- Whether to add `trigger_index` to Trade now (Phase 3) or wait for
  Phase 4
- Concrete error-handling shape for malformed `strategies.yaml` at
  scan time
- Whether `evaluate_strategies` runs even if `trading_paused == true`
  (loop-level early-exit vs in-trade gate — both acceptable as long
  as success criterion #3 holds)

---

## Deferred Ideas

Captured in 03-CONTEXT.md `<deferred>`:

- Per-strategy `bet_percent` override (REQUIREMENTS Future)
- `lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields
  (REQUIREMENTS Future)
- Hot-reload of `strategies.yaml` (REQUIREMENTS Future)
- `trigger_index` on Trade (Phase 4 may pick up)
- `min_minute` for clockless sports (baseball, tennis)
- Per-strategy `enabled: false` flag in YAML
- Eventual drop of `stretch_opportunities_archived` — explicitly NOT
  a follow-up; rename is intended to be permanent
- Removing the process-level `DRY_RUN` env var entirely (post-Phase 4
  cleanup, requires ops-script migration plan)

---

*Auto-resolved 2026-05-01. Edit 03-CONTEXT.md to override any decision
before running `/gsd-plan-phase 3`.*
