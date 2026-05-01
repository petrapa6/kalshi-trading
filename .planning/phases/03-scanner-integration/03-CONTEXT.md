# Phase 3: Scanner Integration - Context

**Gathered:** 2026-05-01
**Status:** Ready for planning
**Mode:** Auto-selected recommended defaults (Auto Mode session)

<domain>
## Phase Boundary

Wire `strategies.yaml` (built in Phase 2) into the live scanner. The scanner
evaluates each loaded strategy every Kalshi scan iteration; when a trigger
fires for a live market, it writes a `Trade` row with `dry_run=True` and
`strategy_name=<name>` — **without** calling the Kalshi API. The legacy
`WHAT_IF_STRATEGIES` system is decommissioned (`stretch_opportunities` table
renamed-not-dropped; `_evaluate_what_if_strategies` removed; `/api/sport-stats`
re-sourced from `opportunities`). DB engine gains a 5s lock timeout to
survive Phase 4 analytics polling.

**In scope (Phase 3):**

- `Trade.strategy_name` column added via the existing `_migrate_add_columns()`
  pattern in `db.py`
- `connect_args` in `db.py` gains `"timeout": 5`
- New `evaluate_strategies(session, ...)` step in the kalshi scan loop —
  per-iteration, after `scan_kalshi_with_espn` returns
- Sport-family ↔ sport_path mapping + per-sport game-length lookup so the
  scanner can convert ESPN clock state into the `min_minute` ("game-clock
  minutes elapsed since start") semantics defined in Phase 2 D-01
- Strategy-driven dry-run path in `place_bet` (or sibling) that **never**
  calls Kalshi REST — distinct from process-level `DRY_RUN`
- `check_settlements` and `on_lifecycle` updated to settle dry-run strategy
  trades alongside real trades — single combined filter
- `stretch_opportunities` table renamed to `stretch_opportunities_archived`
  via `_migrate_add_columns()` (idempotent, S3-backup-tested)
- `WHAT_IF_STRATEGIES` dict + `_evaluate_what_if_strategies()` + `stretch_opps`
  scan-loop accumulator removed from `scanner.py`
- `/api/sport-stats` re-derived from the `opportunities` table

**Out of scope (deferred to Phase 4):**

- New analytics dashboard page / per-strategy analytics endpoints
  (DASH-03, DASH-04)
- Hot-reload of `strategies.yaml` without container restart (REQUIREMENTS
  Future Requirements)
- Per-trigger analytics breakdown (`trigger_index` on `Trade`) — picked up
  in Phase 4 if useful
- Real-money trading — milestone is dry-run only; `trading_paused` kill
  switch remains in place
- CLI commands for strategy management

</domain>

<spec_lock>
## Success Criteria (Locked by ROADMAP.md § Phase 3)

These are pre-decided and downstream agents must verify each:

1. `stretch_opportunities` → `stretch_opportunities_archived` (RENAME, not
   DROP); `WHAT_IF_STRATEGIES` removed from `scanner.py`;
   `GET /api/sport-stats` returns correct game counts derived from the
   `opportunities` table.
2. When a strategy trigger fires for a live market, a `Trade` row is written
   with `dry_run=True`, `strategy_name` set, and `yes_price` = the live
   `yes_ask` from `market_prices` cache — no Kalshi API call regardless of
   the process-level `DRY_RUN` env var.
3. `trading_paused == "true"` prevents dry-run strategy trades from being
   written, same as live trades.
4. Settlement reconciliation processes
   `dry_run=True AND strategy_name IS NOT NULL` trades (WebSocket primary
   + REST fallback); P&L computed using contract math on the recorded
   `yes_ask` entry price.
5. `connect_args` in `db.py` includes `"timeout": 5` to prevent
   `SQLITE_BUSY` errors under concurrent analytics polling.

</spec_lock>

<decisions>
## Implementation Decisions

### Schema migration

- **D-01:** `Trade.strategy_name = Column(String, nullable=True, index=True)`.
  Indexed because Phase 4 analytics queries will filter/aggregate by this
  column and auto-refresh every 5 minutes. `nullable=True` so legacy real
  trades + legacy dry-run trades don't violate the column. Use the existing
  `_migrate_add_columns()` ALTER TABLE pattern in `db.py:152` (mirrors how
  `espn_clock_seconds` and `fee_cents` were added). Idempotent on existing
  DBs.

- **D-02:** `db.py:19` becomes
  `engine = create_engine(DATABASE_URL, connect_args={"check_same_thread":
  False, "timeout": 5})`. Single-line change. No env override — 5s is
  sufficient for the analytics polling cadence (5min auto-refresh) and small
  enough not to mask deadlocks during local dev. Per ROADMAP success
  criterion #5.

- **D-03:** `stretch_opportunities` → `stretch_opportunities_archived`
  rename happens inside `_migrate_add_columns()`. Logic:

  ```python
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

  Idempotent — runs once per fresh DB, no-op on subsequent boots. The
  `StretchOpportunity` SQLAlchemy model is **deleted** (not retargeted to
  the archived table); the table physically lives for audit/diagnostics
  only, not for app reads.

  **Pre-deploy gate** (per STATE.md decision STR-04): test the rename
  against a current S3 backup copy locally before pushing to prod. Document
  in PLAN.md.

### Strategy evaluation in the scan loop

- **D-04:** Add a new function `evaluate_strategies(session, client,
  espn_final_period, max_bet_cents)` in `scanner.py`. Called inside
  `kalshi_scan_loop` after `scan_kalshi_with_espn` returns, before
  `check_settlements`. Same iteration cadence (~5s) — does **not** spawn
  a 5th asyncio loop. Reuses the same `market_prices` cache, the same
  ESPN cache, and the same `session` lifetime. The existing
  `_evaluate_what_if_strategies` slot (called at scanner.py:575) is the
  insertion point — replace, don't append.

- **D-05:** Strategies are loaded **once per scan loop iteration** via
  `load_strategies()` (Phase 2's `src/predictions/strategies.py`). Cheap:
  YAML parse + Pydantic validate is small relative to ESPN/Kalshi I/O.
  Mirrors `get_config_int` re-read cadence — no caching, no hot-reload
  bookkeeping. Errors short-circuit: log + skip evaluation this tick (do
  NOT raise; preserves the scanner's permissive-logging error pattern).
  Phase 4 may revisit if profiling shows YAML parse cost matters.

- **D-06:** Strategy evaluation iterates **markets × strategies × triggers**
  with this short-circuit shape:

  ```
  for market in current_open_markets:
      espn_game = match_kalshi_to_espn(market, espn_cache)
      if not espn_game:  # no live ESPN match
          continue
      for strategy in strategies:
          if already_fired(strategy.name, market.ticker):  # see D-09
              continue
          for trigger in strategy.triggers:
              if trigger_matches(trigger, market, espn_game):
                  fire_strategy_trade(...)
                  break  # first-trigger-wins per (strategy, market) tick
  ```

  `trigger_matches` evaluates the AND-conditions on a single trigger:
  `sport`, `min_minute`, `min_lead`, `min_yes_price`, `max_yes_price`. A
  missing field on the trigger means "no constraint on that dimension"
  (per Phase 2 D-03). All five fields are evaluated against live data
  per DRY-01.

### Sport family ↔ sport_path + game-clock minute semantics

- **D-07:** **Phase 2 D-02 OVERRIDE governs.** `trigger.sport` is a
  **sport-family literal** (`football`, `baseball`, `basketball`,
  `tennis`, `american_football`, `hockey` — UK terminology, never
  `soccer`). NOT an ESPN sport_path. Phase 3 must add the
  family→sport_path mapping. Original Phase 2 D-02 (sport = ESPN
  sport_path) is **superseded** — see `02-CONTEXT.md` "Revision —
  2026-04-30 (D-02 OVERRIDE)" for full rationale.

- **D-08:** New module-level constant in `scanner.py`:

  ```python
  SPORT_FAMILY_TO_PATHS: dict[str, frozenset[str]] = {
      "football": frozenset({"soccer/eng.1", "soccer/esp.1",
                             "soccer/ger.1", "soccer/ita.1",
                             "soccer/fra.1", "soccer/usa.1",
                             "soccer/uefa.champions"}),
      "basketball": frozenset({"basketball/nba"}),
      "baseball": frozenset({"baseball/mlb"}),
      "american_football": frozenset({"football/nfl",
                                       "football/college-football"}),
      "hockey": frozenset({"hockey/nhl"}),
      "tennis": frozenset({"tennis/atp", "tennis/wta"}),
  }
  ```

  Lives in `scanner.py` next to `KALSHI_TO_ESPN` / `MIN_SCORE_LEAD`
  (the existing per-sport catalog). Authoritative values must be
  cross-checked against `KALSHI_TO_ESPN` keys and the `lead:<path>`
  config keys at planning time — the planner is responsible for
  enumerating actual sport_paths in use, not assuming this list is
  exhaustive. `frozenset` for O(1) lookup; the reverse `path → family`
  map is computed once at module import.

- **D-09:** Per-sport game-length constants for the `min_minute` derivation:

  ```python
  SPORT_GAME_LENGTH_SECS: dict[str, int] = {
      "soccer/eng.1": 90 * 60,   # count-up; min_minute = clock // 60
      "soccer/esp.1": 90 * 60,
      ...
      "basketball/nba": 48 * 60,  # count-down; elapsed = TOTAL - clock
      "football/nfl": 60 * 60,
      "hockey/nhl": 60 * 60,
      ...
  }
  ```

  And a helper `elapsed_minutes(sport_path, espn_clock_seconds, period)`
  that:
  - Soccer (count-up): returns `clock_seconds // 60` plus period offset
    (45 min for 2nd half).
  - Count-down sports: returns
    `(period_offset + (period_length_secs - clock_seconds)) // 60`.
  - Baseball/tennis (no clock): not supported in `min_minute` triggers
    today — log + skip the trigger, do not crash. Document as a known
    limitation; Phase 4+ revisits if YAML uses `min_minute` on
    clockless sports.

  This matches Phase 2 D-01's promise: "Phase 3 will need a per-sport
  `total_game_seconds` / period-length lookup". The planner owns the
  exact period structure (e.g., NBA 4×12min vs NCAA 2×20min) and must
  cross-check against `GameState` semantics in `espn.py`.

### Per-strategy dedupe + multi-strategy fire policy

- **D-10:** **Per-strategy dedupe by `(strategy_name, ticker)`.** Before
  firing, query
  `SELECT 1 FROM trades WHERE strategy_name = :s AND ticker = :t LIMIT 1`.
  Skip if a row exists (regardless of the row's status). A strategy fires
  at most once per market lifetime — once fired, future fires on the same
  ticker are skipped even after the market settles. Mirrors how a real
  position blocks re-entry (`scanner.py:469` already uses an open-positions
  filter for live trades).

- **D-11:** **Multiple distinct strategies CAN fire on the same ticker.**
  Each gets its own `Trade` row, settled independently. This is required
  for Phase 4's per-strategy P&L analytics. The `(strategy_name, ticker)`
  dedupe key is per-strategy, not global.

- **D-12:** **First-trigger-wins per (strategy, market) tick.** Within
  one strategy's `triggers: [...]` list, evaluate in YAML order; the
  first AND-set that matches fires the bet. No "best trigger" search,
  no fire-on-all-matches-and-take-max-count. Mirrors the backtest
  engine's first-fire-wins semantics (Phase 2 D-12).

### Strategy-driven dry-run path

- **D-13:** Add a new helper `place_strategy_trade(session, opp,
  strategy_name, max_cost_cents)` in `scanner.py` — does **not** call
  `client.create_order()`. Writes a `Trade` row with:
  - `dry_run=True` (hardcoded)
  - `status="dry_run"`
  - `strategy_name=<name>`
  - `yes_price = opp["yes_ask"]` (live cache value)
  - `count = max_cost_cents // yes_price`
  - `cost_cents`, `potential_profit_cents` computed same as `place_bet`
  - `order_id=None`, `fee_cents=None` (no real order, no real fee)

  Does NOT reuse `place_bet`'s `dry_run=True` branch — that branch is
  for the process-level `DRY_RUN` env (a debug toggle), and conflating
  the two paths makes settlement filtering and analytics ambiguous.
  Two distinct call sites, two distinct intents. `place_bet` keeps its
  existing semantics unchanged.

- **D-14:** **Bet sizing for strategy dry-runs uses the same balance
  source as live trades.** `max_bet_cents = bet_percent × current_balance`
  (computed once per scan iteration, reused). Identical to `place_bet`'s
  budgeting input. Per-strategy `bet_percent` overrides are deferred
  (REQUIREMENTS Future Requirements) — a single global `bet_percent`
  drives all dry-run strategies for v1.2.

- **D-15:** **`trading_paused` check happens inside `place_strategy_trade`,
  not at the loop level.** Read `get_config_str("trading_paused")` (or
  reuse the existing pattern in `place_bet`); if `"true"`, return
  immediately without writing any DB row, log a single line per
  strategy/market combo. Reasoning: matches existing live-trade kill-switch
  pattern; loop-level early-exit would also stop strategy evaluation
  bookkeeping (which we want to keep running so analytics show "would
  have fired but paused" later — handled via log lines, not a new
  Trade status).

  **Note for planner:** verify exact paused check location in current
  `place_bet` flow; if it's loop-level today, mirror that placement
  consistently. Goal is parity with live trades, not a new pattern.

### Settlement reconciliation (WS primary + REST fallback)

- **D-16:** **Single combined filter** in `check_settlements`:

  ```python
  open_trades = session.query(Trade).filter(
      Trade.status.in_(("placed", "filled", "dry_run")),
      or_(
          Trade.dry_run == False,
          and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),
      ),
  ).all()
  ```

  Rationale: a single query keeps both code paths in lockstep (no risk
  of one drifting). Excludes the OLD process-level dry-run trades
  (`dry_run=True AND strategy_name IS NULL`) — those continue to be
  diagnostic-only and are NOT settled. Strategy dry-runs
  (`dry_run=True AND strategy_name IS NOT NULL`) ARE settled.

- **D-17:** **WS `on_lifecycle` handler** (currently
  `scanner.py:883` registration) gains the same combined filter when
  it queries `Trade` rows by ticker on `market_lifecycle_v2` events.
  Both code paths (WS primary + REST fallback) MUST update the same
  set of trades — symmetry is a correctness requirement, not just a
  style preference.

- **D-18:** **P&L math for strategy dry-runs.** Win:
  `pnl_cents = count × (100 − yes_price)` (no fee — no real order).
  Loss: `pnl_cents = −count × yes_price`. Status flow:
  `dry_run` → (`settled_win` | `settled_loss` | `error`). Status
  remains `dry_run` for the placed/filled phase since no real
  `placed`/`filled` lifecycle exists. Final status semantics are the
  same as real trades — same enum values — so analytics can
  union/aggregate cleanly.

### `/api/sport-stats` migration

- **D-19:** **Re-source from `opportunities`.** Current code
  (`api.py:484–496`) does `SELECT series_ticker, COUNT(*) FROM
  stretch_opportunities GROUP BY series_ticker`. Replace with:

  ```sql
  SELECT series_ticker, COUNT(DISTINCT event_ticker) AS game_count
  FROM opportunities
  GROUP BY series_ticker
  ```

  `COUNT(DISTINCT event_ticker)` because one Kalshi event = one game,
  but a single game has many opportunities (every loop a candidate
  passes). Old behavior counted stretch_opp rows (closer to "near-miss
  events") — the migration changes the semantic from "near-misses per
  series" to "distinct games scanned per series", which is what the
  endpoint name actually implies. **This is a behavior change.** Flag
  in PLAN.md and verify the dashboard's consumer of this endpoint
  treats the new number as still meaningful (likely yes; today's
  number is mostly used as a "did anything happen?" indicator).

  **Alternative considered + rejected:** keep behavior identical by
  reading from `stretch_opportunities_archived`. Rejected because
  STR-04 explicitly says "derive from `opportunities` table"; the
  archive is meant to be inert.

### Removal scope (`WHAT_IF_STRATEGIES`)

- **D-20:** Remove from `scanner.py`:
  - `WHAT_IF_STRATEGIES` dict (line 262)
  - `_evaluate_what_if_strategies()` function (line 580)
  - `stretch_opps` accumulator inside `scan_kalshi_with_espn` (line 311)
  - All `stretch_lead` / `meets_stretch_lead` / `stretch_opps.append`
    branches inside the per-market evaluation loop
  - The `if stretch_opps: ...` flush block (line 535)
  - The `_evaluate_what_if_strategies(...)` call site (line 575)
  - `from .db import StretchOpportunity` import

  Remove from `db.py`:
  - `StretchOpportunity` ORM class (line 89)
  - `stretch_opportunities` migration column ALTERs (lines 166–180) —
    no longer needed (table is renamed and inert; ORM not mapped)

  Removals must be type-clean (`uv run ty check`) — flag any callers
  the planner finds that aren't on this list.

### Claude's Discretion

- **Module location for sport mapping helpers** — keep in `scanner.py`
  (next to `KALSHI_TO_ESPN`) vs. extract into `src/predictions/sports.py`.
  Planner judgment: extract if `evaluate_strategies` + helpers cross 100
  lines; otherwise inline keeps the call graph local.

- **`evaluate_strategies` test seam** — pure function with `session` +
  `strategies: list[Strategy]` injected, vs. a method on a class.
  Planner judgment; lean toward functional to match the rest of
  `scanner.py`.

- **Logging cadence** — log every fire (one line) but suppress repeated
  "skipped" / "already fired" entries (would flood scanner.log under
  the per-loop cadence). Log first skip per `(strategy, ticker)` if at
  all.

- **Ordering of new Trade columns** — Phase 4 may add `trigger_index`.
  Phase 3 leaves it out (per Phase 2 deferred ideas). If the planner
  judges it's cheaper to add now, that's allowed.

- **Concrete error handling** for malformed `strategies.yaml` at scan
  time — log + skip this tick (per D-05). Whether to also emit a
  one-line warning per loop or rate-limit to once per minute: planner's
  call.

- **Whether `evaluate_strategies` runs even if `trading_paused == true`** —
  D-15 says the gate is inside `place_strategy_trade`. But the planner
  may judge an early-exit at the loop level is cleaner; both are
  acceptable as long as success criterion #3 (no Trade row written
  while paused) holds.

</decisions>

<specifics>
## Specific Ideas

- The Phase 2 D-02 OVERRIDE addendum (`02-CONTEXT.md` lines 482–496) is
  the authoritative reference for `trigger.sport` semantics. Phase 3
  agents who read only the original Phase 2 D-02 will get the wrong
  answer. The override is loud and explicit — UK terminology
  (`football`, never `soccer`).

- D-11 RETRACTION (`02-CONTEXT.md` lines 498–520) clarifies an
  asymmetry that Phase 3 must preserve: the **backtest engine** ignores
  `min_yes_price` / `max_yes_price`, but the **live scanner** filters
  on them per DRY-01. Phase 3 implements the filter side; do not
  inherit the backtest's "ignore" semantics.

- The legacy `WHAT_IF_STRATEGIES` system has been the project's primary
  parameter-search mechanism since v1.0. Phase 3 deletes it. The
  rename-not-drop policy (D-03) is explicitly so the historical
  what-if data survives for retrospective analysis even after the
  code path is gone. Don't drop in a "cleanup" follow-up phase — the
  data is intended to be archival.

- The user has already flagged the settlement filter (`STATE.md`
  Blockers) as a Phase 3 must-fix. D-16 + D-17 satisfy this. Treat
  this as a smoke-test priority during UAT.

- `place_bet`'s existing `dry_run=True` branch (process-level DRY_RUN)
  must remain functional and untouched. Two dry-run modes coexist
  intentionally — one for ops debugging, one for strategy analytics.
  Don't unify them.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before acting.**

### Phase scope and acceptance

- `.planning/ROADMAP.md` § Phase 3 — phase goal, depends-on, **5 success
  criteria** that must all be TRUE. Settlement filter (#4) and
  `connect_args timeout` (#5) are non-obvious — verify both.

- `.planning/REQUIREMENTS.md` § STR-04, DRY-01, DRY-02 — canonical
  functional requirements. Note: REQUIREMENTS.md says "the
  `stretch_opportunities` DB table is **dropped**", but the **ROADMAP
  success criterion #1 supersedes this** with "renamed to
  `stretch_opportunities_archived` (not dropped)" — the rename is the
  authoritative policy (later, more conservative). Use ROADMAP.

- `.planning/PROJECT.md` § Active / Constraints / Key Decisions —
  no-new-deps rule, integer-cents invariant, oxfmt 4-space indent,
  `pnpm fmt:check && pnpm lint && pnpm build` gate, `uv run ruff…`
  Python gate, `trading_paused` kill switch invariant.

- `.planning/STATE.md` § Blockers/Concerns — Phase 3 settlement filter
  blocker (resolved by D-16/D-17), per-sport `total_game_seconds`
  lookup callout (resolved by D-09).

### Prior-phase context (must read)

- `.planning/phases/02-strategy-engine-core/02-CONTEXT.md` — Phase 2
  decisions. **Critical sections for Phase 3:**
  - **`Revision — 2026-04-30 (D-02 OVERRIDE)`** (lines 482–496) —
    `trigger.sport` is a sport-family literal (`football`, `baseball`,
    …), NOT an ESPN sport_path. Phase 3's scanner port reads THIS,
    not original D-02.
  - **`Revision — 2026-04-30 (D-11 UI retraction)`** (lines 498–520) —
    backtest UI does not surface `min_yes_price` / `max_yes_price`,
    but the **live scanner DOES filter on them** per DRY-01. Asymmetry
    is intentional.
  - **D-01** (lines 49–55) — `min_minute` semantics: "game-clock
    minutes elapsed since start". Phase 3 owes the per-sport
    `total_game_seconds` lookup (D-09 here).
  - **D-08** (lines 109–112) — `STRATEGIES_PATH` env var read in
    exactly one site (`load_strategies()`). Phase 3 scanner imports
    `load_strategies` directly — no parallel env reads, no second
    YAML parse.

- `.planning/phases/01-backtest-p-l-math/01-CONTEXT.md` § D-01..D-04 —
  contract-math formulas. Phase 3 P&L math (D-18 here) is the
  scanner-side mirror of these formulas; **integer cents throughout**.

### Code conventions

- `.planning/codebase/CONVENTIONS.md` — Python: `uv` + `ruff` + `ty`;
  Pydantic for boundaries; `_CONFIG_DEFAULTS` pattern for runtime
  tunables; **log-and-continue for scanner-loop failures** (no
  hard-fail on YAML errors per D-05).

- `.planning/codebase/ARCHITECTURE.md` § Settlement Duality — WS
  primary + REST fallback; both paths must update the same trades
  (D-17). § Anti-Patterns / "Configuration Hardcoding in Code" —
  use `get_config_int(key)` first; code defaults are fallbacks.

- `.planning/codebase/STRUCTURE.md` — `src/predictions/` module layout;
  scanner-related helpers stay close to `scanner.py` unless they grow
  past ~100 lines.

- `.planning/codebase/TESTING.md` — pytest conventions; `isolated_db` /
  `isolated_soccer_db` fixtures. Phase 3 likely adds tests with
  fixture YAML strategies + a fake `market_prices` cache + a fake
  ESPN game state.

### Code references (existing code Phase 3 modifies)

- `src/predictions/scanner.py:62` — `MIN_SCORE_LEAD` dict. Reuse for
  per-sport lead defaults; Phase 3 doesn't change this.

- `src/predictions/scanner.py:127–200` — `place_bet`. **Untouched**;
  Phase 3 adds a sibling `place_strategy_trade` (D-13).

- `src/predictions/scanner.py:203–250` — `check_settlements`. Modify
  the filter per D-16.

- `src/predictions/scanner.py:262` — `WHAT_IF_STRATEGIES` dict.
  **Removed** per D-20.

- `src/predictions/scanner.py:300+` — `scan_kalshi_with_espn`. Remove
  `stretch_opps` accumulator + `meets_stretch_lead` branches (D-20).

- `src/predictions/scanner.py:469–472` — open-positions filter. The
  pattern (`open_statuses = ("placed", "filled", "dry_run")`) is
  the model for D-16's settlement filter.

- `src/predictions/scanner.py:575` — `_evaluate_what_if_strategies`
  call site. Replace with `evaluate_strategies(...)` (D-04).

- `src/predictions/scanner.py:580` — `_evaluate_what_if_strategies`
  function. **Removed** per D-20.

- `src/predictions/scanner.py:883` — `ws.on("market_lifecycle_v2",
  on_lifecycle)` registration. Update `on_lifecycle` to apply the
  combined filter (D-17).

- `src/predictions/db.py:19` — `create_engine` `connect_args`. Add
  `"timeout": 5` (D-02).

- `src/predictions/db.py:62–87` — `Trade` model. Add `strategy_name`
  column (D-01).

- `src/predictions/db.py:89–125` — `StretchOpportunity` model.
  **Removed** per D-20.

- `src/predictions/db.py:152` — `_migrate_add_columns()`. Add the
  `Trade.strategy_name` ALTER (D-01) and the
  `stretch_opportunities → archived` RENAME (D-03). Remove the
  stretch_opportunities column ALTERs (D-20).

- `src/predictions/api.py:484–496` — `/api/sport-stats` endpoint.
  Re-source from `opportunities` per D-19.

- `src/predictions/strategies.py` (Phase 2 output) — `load_strategies()`
  is the single import for the scanner; do not re-parse YAML.

- `src/predictions/kalshi_client.py` — `extract_cents` / `extract_volume`
  remain the single drift point for Kalshi prices. `place_strategy_trade`
  reads `yes_ask` from `market_prices` cache (already extracted).

### Origin / dependencies

- `tests/test_strategies.py` (Phase 2) — extend with scanner-integration
  tests. Use the `isolated_db` fixture pattern.

- `.env.example` — `STRATEGIES_PATH` already documented from Phase 2;
  no new env vars in Phase 3.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- **`load_strategies()`** in `src/predictions/strategies.py` (Phase 2) —
  already returns Pydantic-validated `list[Strategy]`. Scanner imports
  directly. No re-parse, no re-validate.

- **`get_config_int(key)` / `get_config_str(key)`** in `db.py` — runtime
  config reads (`bet_percent`, `trading_paused`, etc.). Strategy eval
  uses these for the same per-loop config inputs as live trading.

- **`market_prices` module-level dict** in `scanner.py` — real-time WS
  price cache. `yes_ask = market_prices[ticker]["yes_ask"]`. DRY-01's
  "live yes_ask price" sources from here. Skip evaluation if a market
  has no price entry yet (no WS tick received).

- **`match_kalshi_to_espn(ticker, game)`** — already-pure mapper from
  Kalshi market → ESPN GameState. Reuse as-is.

- **`GameState`** in `espn.py` — `is_live`, `is_final_period`,
  `is_in_final_minutes`, `score_diff`, `leading_team`, `clock_seconds`,
  `period`. Sufficient for the `min_lead` and `min_minute` derivations.
  Per-sport clock semantics (count-up vs count-down) are already
  encapsulated — the planner should consult this instead of reinventing.

- **`_migrate_add_columns()`** pattern in `db.py:152` — idempotent
  ALTER TABLE migration scaffold. Phase 3 adds `Trade.strategy_name`
  and the stretch_opportunities RENAME via this same function.

- **`isolated_db` / `isolated_soccer_db` fixtures** in `tests/conftest.py`
  — mock SQLAlchemy session for unit tests. Extend with a fake
  `market_prices` and ESPN cache for `evaluate_strategies` tests.

### Established patterns

- **Single drift point per integration:** `load_strategies` is the only
  YAML reader; `extract_cents` / `extract_volume` are the only price
  extractors. Phase 3 must NOT add a second YAML parser or a parallel
  price extractor.

- **Permissive logging + log-and-continue** in scanner loops — YAML
  errors during eval, missing market_prices entries, missing
  game-length entries: log warning, skip the relevant unit, continue
  the loop. No raises out of the scan loop.

- **Idempotent migrations** via `_migrate_add_columns()` — column adds
  guarded by `inspector.get_columns()`; table renames guarded by
  `inspector.get_table_names()`. Same boot path on fresh DBs and
  upgraded DBs.

- **Bearer-auth on every endpoint** — `/api/sport-stats` already uses
  `Depends(_check_token)`. The query swap (D-19) keeps auth intact.

- **Settlement duality (WS primary + REST fallback)** — both paths
  must update the same trade set. Phase 3's combined filter (D-16)
  + on_lifecycle update (D-17) preserve symmetry.

### Integration points

- **API lifespan startup** (`api.py:215–241`) — no changes needed; the
  scanner picks up strategies on its first loop iteration after start.

- **`/api/strategies`** (Phase 2) — read by the dashboard for the
  backtest UI. Phase 3 adds no new endpoint; per-strategy analytics
  endpoints are Phase 4 (DASH-03).

- **Process-level `DRY_RUN` env var** — controls whether `place_bet`
  hits Kalshi REST. Phase 3's strategy dry-run is **independent** of
  this — it's hardcoded at `place_strategy_trade` and never calls
  Kalshi REST regardless of `DRY_RUN`. Two distinct dry-run modes;
  `place_bet`'s `dry_run` branch and `place_strategy_trade` produce
  Trade rows that look similar (`dry_run=True`, `status="dry_run"`)
  but are differentiated by `strategy_name IS NOT NULL` (D-16).

</code_context>

<deferred>
## Deferred Ideas

- **Per-strategy `bet_percent` override** — REQUIREMENTS Future
  Requirements. v1.2 uses the global `bet_percent` for all strategies.
  Pick up if Phase 4 analytics show single sizing is too coarse.

- **`lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields**
  — REQUIREMENTS Future Requirements. Phase 3 supports the 5 fields
  promised in STR-02 (`sport`, `min_minute`, `min_lead`, `min_yes_price`,
  `max_yes_price`). Future fields require a Pydantic schema bump in
  `strategies.py` first.

- **Hot-reload of `strategies.yaml` without container restart** —
  REQUIREMENTS Future Requirements. Open dry-run trades created under
  one strategy version would settle under another — design needed.
  Phase 3 reloads on each scan iteration (D-05) but assumes the file
  is hand-edited and stable. A SIGHUP reload pattern or a file-watch
  pattern is the natural follow-up.

- **`trigger_index` column on `Trade`** — Phase 4 may want
  per-trigger-within-strategy analytics. Phase 3 leaves it out unless
  the planner judges adding it now is cheaper than later.

- **`min_minute` for clockless sports (baseball, tennis)** — D-09
  notes these are unsupported today. If a future YAML uses
  `min_minute` on baseball, the scanner logs and skips that trigger.
  A "innings-elapsed" or "set count" mapping would be needed if
  user demand emerges.

- **Per-strategy `enabled: false` flag in YAML** — would let users
  silence a strategy without deleting it. Phase 3 keeps things simple:
  every strategy in `strategies.yaml` is evaluated. Deferred until
  signal that hand-managing the file is friction.

- **Cleanup follow-up to actually drop `stretch_opportunities_archived`**
  — explicitly NOT a Phase 3+1 task; the rename is intended to be
  permanent for archival access.

- **Removing the process-level `DRY_RUN` env var entirely** — once
  Phase 4 ships and analytics confirm strategy dry-run is the primary
  dry-run mode, the legacy `DRY_RUN`-driven `place_bet` branch may be
  removable. Out of Phase 3 scope; would require a migration plan for
  any ops scripts that depend on it.

</deferred>

---

*Phase: 03-scanner-integration*
*Context gathered: 2026-05-01*
*Mode: auto-selected recommended defaults (Auto Mode session, no flag)*
