# Phase 3: Scanner Integration - Pattern Map

**Mapped:** 2026-05-01
**Files analyzed:** 8 (4 modified, 3 new tests, 1 modified test)
**Analogs found:** 8 / 8 (3 exact, 4 role-match, 1 partial-match novelty)

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/predictions/scanner.py` (MOD) | service / async-loop / event-driven | request-response + pub-sub (WS) | (self — sibling functions) | exact (sibling) |
| `src/predictions/db.py` (MOD) | model / migration | schema + transform | (self — existing migrations) | exact (sibling) |
| `src/predictions/api.py` (MOD) | controller (FastAPI) | request-response | self (`get_total_sport_stats`, `clear_stretch_opportunities`) | exact (sibling) |
| `dashboard/app/page.tsx` (MOD) | component (React) | fetch / state-driven | self (other tab blocks) | role-match (delete-only) |
| `tests/test_scanner_strategies.py` (NEW) | test (unit) | pure + DB-via-fixture | `tests/test_strategies.py` + `tests/test_sport_stats.py` | role-match |
| `tests/test_strategy_settlement.py` (NEW) | test (unit) | DB-via-fixture | `tests/test_sport_stats.py` (no current settlement test) | partial-match (novel) |
| `tests/test_db_migrations.py` (NEW) | test (unit) | DDL-via-fixture | (no existing migration test) | partial-match (novel) |
| `tests/test_sport_stats.py` (MOD) | test (unit) | DB-via-fixture | (self — small re-seed) | exact (sibling) |

**Note on locations:** The dashboard page is at `dashboard/app/page.tsx`, not `dashboard/src/app/page.tsx` as the prompt suggested. Verified via filesystem.

## Pattern Assignments

### `src/predictions/scanner.py` — `evaluate_strategies` (NEW), `place_strategy_trade` (NEW), helpers (NEW)

**Analog 1 (loop step replacement):** `_evaluate_what_if_strategies` at `scanner.py:580-707` — the slot we are physically replacing.

**Analog 2 (sibling — trade write path):** `place_bet` at `scanner.py:127-200` — copy session lifecycle, log line shape, error handling. **Do NOT refactor `place_bet`**; copy.

**Analog 3 (loop integration site):** `scan_kalshi_with_espn` at `scanner.py:469-577` — copy the `trading_paused` check pattern (line 523), the open-trades dedupe pattern (lines 469-475), and the session lifecycle.

#### Imports pattern (scanner.py:17-43)

```python
import asyncio
import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from predictions.db import (
    BalanceSnapshot,
    Opportunity,
    Scan,
    StretchOpportunity,   # REMOVE per D-20
    Trade,
    get_config,
    get_config_int,
    get_session,
    init_db,
)
from predictions.espn import (
    game_meets_timing,
    get_categorized_games,
    match_kalshi_to_espn,
)
from predictions.kalshi_client import KalshiClient, KalshiWebSocket, extract_cents, extract_volume
```

**For Phase 3:** Add `from predictions.strategies import Strategy, load_strategies`. Add `from sqlalchemy import or_, and_` (used by D-16/D-17). Drop `StretchOpportunity` from the predictions.db import (D-20). Drop `from predictions.espn import _espn_to_kalshi_codes` (was used inside `_evaluate_what_if_strategies`).

#### Place_bet sibling — session lifecycle to mirror in `place_strategy_trade` (scanner.py:149-170)

```python
session = get_session()
trade = Trade(
    ticker=opp["ticker"],
    event_ticker=opp["event_ticker"],
    title=opp["title"],
    side="yes",
    action="buy",
    count=count,
    yes_price=yes_price,
    cost_cents=total_cost,
    potential_profit_cents=total_profit_if_win,
    dry_run=dry_run,
    espn_clock_seconds=opp.get("espn_clock_seconds"),
)

if dry_run:
    log.info("  [DRY RUN] Order not placed")
    trade.status = "dry_run"
    session.add(trade)
    session.commit()
    session.close()
    return {"dry_run": True, "count": count, "yes_price": yes_price}
```

**For Phase 3 `place_strategy_trade`:** Copy this Trade(...) constructor, hardcode `dry_run=True` and `status="dry_run"`, add `strategy_name=strategy_name`, omit the Kalshi REST branch entirely. Per D-13: "does NOT reuse `place_bet`'s `dry_run=True` branch — that branch is for the process-level `DRY_RUN` env."

#### Place_bet sibling — log line shape (scanner.py:143-147)

```python
log.info(
    f"  Order: BUY {count}x YES @ {yes_price}c = ${total_cost / 100:.2f} cost, "
    f"${total_profit_if_win / 100:.2f} potential profit | "
    f"ESPN: P{opp.get('espn_period', '')} {opp.get('espn_clock', '')}"
)
```

**For Phase 3:** Mirror the format; replace `"Order:"` with `f"STRATEGY FIRE {strategy_name}:"` (per RESEARCH.md Example 2). Same arithmetic on cost/profit.

#### Loop-level `trading_paused` check (scanner.py:523-525) — pattern to mirror per D-23

```python
if get_config("trading_paused") == "true":
    log.info("  SKIP: trading is paused via config")
    continue
```

**For Phase 3 `evaluate_strategies`:** Mirror this. D-23 (revision 2026-05-01) overrides D-15: gate at the loop level (top of `evaluate_strategies`), not inside `place_strategy_trade`. Return early — do NOT iterate strategies × markets when paused.

```python
# Pattern to copy at the top of evaluate_strategies():
if get_config("trading_paused") == "true":
    log.info("evaluate_strategies: trading paused via config — skipping tick")
    return
```

#### Open-positions dedupe pre-load (scanner.py:469-475) — pattern for D-10

```python
open_statuses = ("placed", "filled", "dry_run")
open_trades = (
    session.query(Trade)
    .filter(Trade.status.in_(open_statuses), Trade.dry_run == dry_run)
    .all()
)
open_event_tickers = {t.event_ticker for t in open_trades}
open_count = len(open_trades)
```

**For Phase 3 D-10 (per-strategy dedupe):** Replace the filter shape with `Trade.strategy_name.isnot(None)` and pre-build a `set[(strategy_name, ticker)]`. Note: dedupe key is `(strategy_name, ticker)` per D-10, **regardless of status** — explicitly different from the open-positions filter, which only blocks open trades. Strategy fires are once-per-market-lifetime.

```python
# Adapted pattern for D-10:
existing_strategy_trades: set[tuple[str, str]] = {
    (sn, t)
    for (sn, t) in session.query(Trade.strategy_name, Trade.ticker)
    .filter(Trade.strategy_name.isnot(None))
    .all()
}
```

#### Loop integration call site (scanner.py:986-999)

```python
# Now evaluate using real-time prices from WS
await scan_kalshi_with_espn(
    client,
    current_espn,
    cur_price,
    cur_bet_percent,
    dry_run,
    espn_final_period=current_espn_fp,
)

# Settlement checks as fallback (WS lifecycle handles most)
await check_settlements(client)
await check_stretch_settlements(client)   # REMOVE per D-22
await record_balance(client)
```

**For Phase 3:** Insert `await evaluate_strategies(session=..., espn_final_period=current_espn_fp, max_bet_cents=..., client=client)` between `scan_kalshi_with_espn` and `check_settlements` (per D-04). Delete the `check_stretch_settlements` call (per D-22).

#### Sport-family + game-clock constants (D-08, D-09) — placement next to `MIN_SCORE_LEAD` (scanner.py:62-73)

```python
MIN_SCORE_LEAD = {
    "basketball/nba": 8,
    "basketball/mens-college-basketball": 8,
    "hockey/nhl": 2,
    ...
}
```

**For Phase 3:** Add `SPORT_FAMILY_TO_PATHS`, `SPORT_PATH_TO_FAMILY`, `SPORT_PERIOD_LENGTH_SECS`, `CLOCKLESS_SPORT_PATHS`, `COUNT_UP_SPORT_PATHS` immediately after `MIN_SCORE_LEAD`. Use the same dict-literal style. Per D-08: only enumerate paths actually present in `KALSHI_TO_ESPN`. Per RESEARCH.md verification: `basketball/nba`, `basketball/mens-college-basketball`, `hockey/nhl`, `football/nfl`, `football/college-football`, `baseball/mlb`, `soccer/eng.1`, `soccer/esp.1`, `soccer/usa.1`.

**Game-clock helper (D-09):** Place `elapsed_minutes(sport_path, clock_seconds, period) -> int | None` adjacent to constants. Returns `None` for clockless sports — caller logs and skips trigger. Verified `GameState` exposes `clock_seconds: float`, `period: int`, `sport_path: str` at `espn.py:54-59`.

⚠️ **Soccer cumulative-clock assumption (RESEARCH A1):** Helper assumes ESPN soccer clock is cumulative (45:00 at half, 90:00 at full). Corroborated by `espn.py:88` threshold check `clock_seconds >= 4500`. Empirical verification recommended before lock — flag in PLAN.md.

---

### `src/predictions/scanner.py` — `check_settlements` (MOD per D-16)

**Analog (self):** Existing `check_settlements` at `scanner.py:203-239`.

#### Current filter (scanner.py:206-210) — to be modified

```python
open_trades = (
    session.query(Trade)
    .filter(Trade.status.in_(("placed", "filled")), Trade.dry_run == False)
    .all()
)
```

**For Phase 3 D-16:** Replace with the combined filter (RESEARCH.md Example 3):

```python
from sqlalchemy import or_, and_

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
```

**E712 note:** `pyproject.toml:32` already globally ignores E712, so `== False` / `== True` are correct. Do NOT switch to `is_(False)` — emits non-portable `IS FALSE` SQL on SQLite (RESEARCH Pitfall 1).

**Settlement math reuse (scanner.py:218-234):** Existing if/else win/loss block with `fee = trade.fee_cents or 0`. For strategy dry-runs, `fee_cents` is NULL → `or 0` returns 0 — no fee per D-18. **Block can be reused as-is** with a small log-tag refinement (`"STRATEGY"` vs `"REAL"`).

---

### `src/predictions/scanner.py` — `on_lifecycle` (MOD per D-17)

**Analog (self):** Existing `on_lifecycle` at `scanner.py:828-880` — the WS handler. Symmetry with `check_settlements` filter is a correctness requirement.

#### Current trade query (scanner.py:838-847)

```python
session = get_session()
open_trades = (
    session.query(Trade)
    .filter(
        Trade.ticker == ticker,
        Trade.status.in_(("placed", "filled")),
        Trade.dry_run == False,
    )
    .all()
)
```

**For Phase 3 D-17:** Apply the same combined filter as D-16, AND-ed with `Trade.ticker == ticker`. RESEARCH.md Example 4:

```python
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
```

**Also delete (D-20):** The "Update stretch opportunities" block at `scanner.py:859-876` (entire `open_stretches` query + loop). After D-20 deletes `StretchOpportunity` ORM, this block won't import.

---

### `src/predictions/scanner.py` — Removals per D-20, D-22

| Lines | What to delete |
|------:|----------------|
| 31 | `StretchOpportunity` from the `predictions.db` import block |
| 262-310 | `WHAT_IF_STRATEGIES = {...}` dict |
| 311-371 | `stretch_opps` accumulator + `meets_stretch_lead` branches inside `scan_kalshi_with_espn` (planner verifies exact line range) |
| 535-570 | `if stretch_opps:` flush block |
| 575 | `_evaluate_what_if_strategies(...)` call site |
| 580-707 | `_evaluate_what_if_strategies(...)` function definition |
| 710-747 | `check_stretch_settlements` function (per D-22 — currently has one caller at 998 which D-20 also deletes) |
| 859-876 | "Update stretch opportunities" block inside `on_lifecycle` |
| 998 | `await check_stretch_settlements(client)` call site |

**Type-clean check:** `uv run ty check` after deletions; planner greps for any remaining `StretchOpportunity` / `WHAT_IF_STRATEGIES` / `stretch_opps` / `meets_stretch_lead` references.

---

### `src/predictions/db.py` — `Trade.strategy_name` column (NEW per D-01)

**Analog (self — schema):** Existing `Trade` model at `db.py:62-87`.

#### Current Trade columns (db.py:62-87)

```python
class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    placed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ticker = Column(String, index=True)
    event_ticker = Column(String)
    title = Column(Text)
    side = Column(String)
    action = Column(String)
    count = Column(Integer)
    yes_price = Column(Integer)
    cost_cents = Column(Integer)
    potential_profit_cents = Column(Integer)
    status = Column(String, default="placed")
    settled_at = Column(DateTime, nullable=True)
    pnl_cents = Column(Integer, nullable=True)
    dry_run = Column(Boolean, default=True)
    order_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    espn_clock_seconds = Column(Integer, nullable=True)
    fee_cents = Column(Integer, nullable=True)
```

**For Phase 3 D-01:** Append:

```python
strategy_name = Column(String, nullable=True, index=True)
```

`nullable=True` keeps legacy rows valid; `index=True` for Phase 4 analytics filtering and for D-10 dedupe lookup.

---

### `src/predictions/db.py` — `_migrate_add_columns` (MOD per D-01, D-03, D-20)

**Analog (self):** Existing `_migrate_add_columns` at `db.py:152-207`.

#### Existing migration shape (db.py:152-180)

```python
def _migrate_add_columns():
    """Add columns to existing tables if they don't exist."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "trades" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("trades")}
        if "espn_clock_seconds" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN espn_clock_seconds INTEGER"))
        if "fee_cents" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN fee_cents INTEGER"))

    if "stretch_opportunities" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("stretch_opportunities")}
        if "strategy_set" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text(
                        "ALTER TABLE stretch_opportunities "
                        "ADD COLUMN strategy_set VARCHAR DEFAULT 'default'"
                    )
                )
        if "side" not in cols:
            with engine.begin() as conn:
                conn.execute(
                    text("ALTER TABLE stretch_opportunities ADD COLUMN side VARCHAR DEFAULT 'yes'")
                )
```

**For Phase 3 D-01 (column add — copy idempotent shape):**

```python
if "trades" in inspector.get_table_names():
    cols = {c["name"] for c in inspector.get_columns("trades")}
    if "strategy_name" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE trades ADD COLUMN strategy_name VARCHAR"))
            conn.execute(text(
                "CREATE INDEX IF NOT EXISTS ix_trades_strategy_name "
                "ON trades (strategy_name)"
            ))
```

**For Phase 3 D-03 (table rename — NOVEL pattern, no existing analog):**

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

⚠️ **No prior rename precedent in the codebase.** This is the first table-rename migration. Idempotency strategy mirrors the column-add guard: precondition guard via `inspector.get_table_names()`. Verified by RESEARCH:
- `ALTER TABLE ... RENAME TO` is supported in SQLite 3.25+ inside `engine.begin()`.
- SQLAlchemy `inspector.get_table_names()` is the same primitive used by existing column guards.
- `init_db()` runs once at API lifespan startup before scanner spawns (`api.py:234-256`) — no concurrent connections to invalidate prepared statements (RESEARCH Pitfall 4).

**For Phase 3 D-20 (remove stretch column ALTERs):** Delete `db.py:166-180` block (`strategy_set` and `side` ALTERs). Once the table is renamed and the ORM model is gone, those columns are no longer maintained.

---

### `src/predictions/db.py` — `engine = create_engine(...)` connect_args (MOD per D-02)

**Analog (self):** `db.py:19`.

#### Current engine line

```python
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
```

**For Phase 3 D-02:**

```python
engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 5},
)
```

Single-line additive change. No env override per D-02.

---

### `src/predictions/db.py` — `StretchOpportunity` ORM (DELETE per D-20)

**Lines:** 89-126 — entire class. After deletion, the `stretch_opportunities` table will only exist on upgraded DBs (renamed to `_archived`); fresh DBs won't recreate it because no model is mapped (RESEARCH Pitfall 3).

---

### `src/predictions/api.py` — `/api/sport-stats` (MOD per D-19)

**Analog (self):** `get_total_sport_stats` at `api.py:484-554`.

#### Current SQL query (api.py:491-498)

```python
from sqlalchemy import text

seen_matches = session.execute(
    text(
        "SELECT series_ticker, COUNT(DISTINCT event_ticker) "
        "FROM stretch_opportunities GROUP BY series_ticker"
    )
).fetchall()
```

**For Phase 3 D-19 (table swap; semantic shift):**

```python
seen_matches = session.execute(
    text(
        "SELECT series_ticker, COUNT(DISTINCT event_ticker) "
        "FROM opportunities "
        "WHERE series_ticker IS NOT NULL "
        "GROUP BY series_ticker"
    )
).fetchall()
```

**Behavior change to flag in PLAN.md:** Old count was rows in `stretch_opportunities` (near-miss events); new count is distinct games scanned per series. The number is consumed by the dashboard "Sports" tab as a "did anything happen?" indicator (RESEARCH §Architectural Responsibility Map).

**Auth pattern preserved:** `dependencies=[Depends(_check_token)]` on the route decorator (line 484). Unchanged.

**Aggregation logic unchanged:** Lines 511-552 (ticker-prefix → label mapping, per-sport stats accumulation) operate on whatever `seen_matches` returns. Only the source query changes.

---

### `src/predictions/api.py` — `/api/stretch-stats` and `DELETE /api/stretch` (DELETE per D-21)

**Analogs (self):** `get_stretch_stats` at `api.py:826-878`; `clear_stretch_opportunities` at `api.py:881-895`.

**For Phase 3 D-21:**
- Delete the entire `get_stretch_stats` route (decorator + body, ~53 lines).
- Delete the entire `clear_stretch_opportunities` route (decorator + body, ~14 lines).
- Delete `from predictions.scanner import WHAT_IF_STRATEGIES` (api.py:830) — orphaned after D-20 removes the dict.
- Grep for any remaining `StretchOpportunity` / `WHAT_IF_STRATEGIES` / `StretchStatsResponse` / `_compute_stretch_stats` references in `api.py`. If `_compute_stretch_stats` and `StretchStatsResponse` become orphaned, delete them too. Same for `StrategySetStats`.

**Type-clean check:** `uv run ty check` after deletions.

---

### `dashboard/app/page.tsx` — "What If? Strategy Comparison" tab + `/api/stretch-stats` consumer (DELETE per D-21)

**Analog (self):** Existing tab structure at `page.tsx:2392-2415` and tab bodies at `2618-2691`.

**Important correction:** File location is `dashboard/app/page.tsx` (Next.js App Router at root), not `dashboard/src/app/page.tsx` as the prompt suggested.

#### Existing tab list (page.tsx:2392-2415)

```typescript
{/* Main Tabs */}
<div className="flex flex-wrap gap-2 animate-fade-in">
  {[
    { id: "overview", label: "Overview" },
    { id: "charts", label: "Charts" },
    { id: "sports", label: "Sports" },
    { id: "live_games", label: "Live Games" },
    { id: "strategy", label: "Strategy" },        // REMOVE
    { id: "config", label: "Config" },
    { id: "trades", label: "Recent Trades" },
  ].map((t) => (
    <button
      key={t.id}
      onClick={() => setMainTab(t.id as any)}
      ...
```

**For Phase 3 D-21:** Remove `{ id: "strategy", label: "Strategy" }` from the array.

#### Existing `mainTab` union type (page.tsx:2202-2210)

```typescript
const [mainTab, setMainTab] = useState<
  | "overview"
  | "charts"
  | "sports"
  | "live_games"
  | "strategy"      // REMOVE
  | "config"
  | "trades"
>("overview");
```

**For Phase 3:** Remove `"strategy"` from the union type.

#### Existing fetch + state (page.tsx:2192, 2259-2266)

```typescript
const [stretchStats, setStretchStats] = useState<StretchStats | null>(null);
...
const [tradesRes, stretchRes, configRes, ssRes] = await Promise.all([
  fetch(`${API}/api/histogram-trades?limit=10000`),
  fetch(`${API}/api/stretch-stats`),
  fetch(`${API}/api/config`),
  fetch(`${API}/api/sport-stats`),
]);
if (tradesRes.ok) setAllTrades((await tradesRes.json()).trades ?? []);
if (stretchRes.ok) setStretchStats(await stretchRes.json());
```

**For Phase 3 D-21:**
- Remove the `stretchStats` `useState` declaration (line 2192).
- Remove `fetch(\`${API}/api/stretch-stats\`)` from the `Promise.all` and the destructured `stretchRes` slot.
- Remove `if (stretchRes.ok) setStretchStats(...)`.
- Remove `interface StretchStats { ... }` (lines 145-157).
- Remove the entire `{mainTab === "strategy" && (...)}` block (lines 2618-2691).
- Grep for `stretchStats`, `StretchStats`, `setStretchStats` — should be zero remaining.

**Build verification:** `pnpm lint && pnpm fmt:check && pnpm build` per CLAUDE.md verification gate.

---

### `tests/test_scanner_strategies.py` (NEW — Wave 0)

**Analog 1 (closest):** `tests/test_strategies.py` (Phase 2) — Pydantic-validated strategy fixtures via `tmp_path`, `monkeypatch.setenv("STRATEGIES_PATH", ...)`.

**Analog 2 (DB seeding):** `tests/test_sport_stats.py` — `Trade(...)` constructor + `session.add` + `session.commit()` against the `isolated_db` fixture.

**Analog 3 (fixture):** `tests/conftest.py::isolated_db` — autouse, in-memory SQLite, monkeypatches `predictions.db.engine` and `SessionLocal`.

#### Fixture pattern (conftest.py:10-24) — auto-applies to every test

```python
@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    db_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
```

#### Test seam pattern from test_strategies.py:22-37

```python
def test_valid_file_loads(tmp_path):
    from predictions.strategies import load_strategies

    f = tmp_path / "valid.yaml"
    f.write_text(
        "strategies:\n"
        "  s:\n"
        "    triggers:\n"
        "      - sport: football\n"
        "        min_minute: 80\n"
        "        min_lead: 2\n"
    )
    result = load_strategies(str(f))
    assert len(result) == 1
    assert result[0].name == "s"
```

**For Phase 3 test_scanner_strategies.py:**
- Build YAML strategy fixtures via `tmp_path` + `monkeypatch.setenv("STRATEGIES_PATH", ...)`.
- Build a fake `market_prices` dict (module-level scanner state) by `monkeypatch.setattr(scanner, "market_prices", {...})`.
- Construct `GameState(...)` instances directly (dataclass at `espn.py:45-59`) — pass `clock_seconds`, `period`, `sport_path`, scores, teams, `state="in"`.
- Build a fake `espn_final_period: dict[str, list[GameState]]` and call `await evaluate_strategies(session, espn_final_period, max_bet_cents=...)`.
- Assert via `session.query(Trade).filter(Trade.strategy_name == "...").all()`.

**Test list (from RESEARCH §Phase Requirements → Test Map, Wave 0):**
- `test_evaluate_strategies_fires_dry_run_trade`
- `test_strategy_fire_independent_of_dry_run_env`
- `test_first_trigger_wins`
- `test_per_strategy_dedupe`
- `test_multi_strategy_fire_same_ticker`
- `test_trading_paused_blocks_strategy_fire`
- `test_elapsed_minutes_per_sport`
- `test_sport_path_to_family`
- `test_what_if_strategies_removed` (import-error assertion)

**Async test note:** `pyproject.toml` already sets `asyncio_mode = "auto"` — no `@pytest.mark.asyncio` needed.

---

### `tests/test_strategy_settlement.py` (NEW — Wave 0)

**Analog (closest in current codebase):** `tests/test_sport_stats.py` — only existing test that seeds `Trade` rows against `isolated_db`.

**Novelty flag:** No existing test exercises `check_settlements` or `on_lifecycle`. This is the first settlement test family. Pattern is composed from:
1. `Trade(...)` constructor pattern (test_sport_stats.py:11-25).
2. `check_settlements` signature accepts a `KalshiClient` — tests must mock the client. Pattern: define a minimal `class FakeClient` with `async def get_market(self, ticker) -> dict: return {"status": "finalized", "result": "yes"}` (or "no"), pass to `await check_settlements(fake_client)`.
3. `on_lifecycle` is a closure inside `run_scanner` — to test it, **extract** `on_lifecycle` to a module-level function (planner judgment) OR test the same logic by directly constructing a `msg` dict and exercising the trade-update branch through a refactored helper. Flag for planner: extracting `on_lifecycle` to module-level is a small refactor that improves testability — recommended.

#### Trade seeding pattern (from test_sport_stats.py:10-25)

```python
session.add(
    Trade(
        ticker="KXMLBSTGAME-TEST-BOS-NYY",
        status="settled_win",
        pnl_cents=100,
        dry_run=False,
    )
)
```

**For Phase 3:** Seed mixed-state Trade rows (real placed, real filled, real settled, strategy dry_run, legacy process-level dry_run with `strategy_name=None`), invoke `check_settlements` / `on_lifecycle`, assert which rows transitioned and which did not (D-16 negation: legacy process-level dry-runs stay untouched).

**Test list:**
- `test_check_settlements_updates_strategy_trades`
- `test_on_lifecycle_updates_strategy_trades`
- `test_strategy_pnl_math`
- `test_legacy_dry_runs_not_settled`
- `test_settlement_filter_symmetry` (the same trade set on both code paths — D-17 invariant)

---

### `tests/test_db_migrations.py` (NEW — Wave 0)

**Novelty flag:** No existing migration tests in the codebase. This is the first migration test file.

**Pattern composition strategy:** Cannot reuse `isolated_db` autouse directly because that fixture calls `Base.metadata.create_all(engine)` (post-D-20 schema). To test the rename migration, the test needs to:
1. Build an in-memory engine.
2. Manually `CREATE TABLE stretch_opportunities (...)` via `text()` (mimicking pre-Phase-3 schema).
3. Monkeypatch `predictions.db.engine` to that engine.
4. Call `_migrate_add_columns()`.
5. Assert via `inspector.get_table_names()` that `stretch_opportunities_archived` exists and `stretch_opportunities` does not.

**Engine construction pattern (from conftest.py:18):**

```python
engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
```

**Inspector pattern (from db.py:154-156):**

```python
from sqlalchemy import inspect, text
inspector = inspect(engine)
table_names = inspector.get_table_names()
```

**Recommendation:** Override `isolated_db` per-test (or write a non-autouse fixture for the migration tests; `autouse` of `isolated_db` will still run, but `db_module.Base.metadata.create_all(engine)` won't create `stretch_opportunities` since the model is gone post-D-20 — so the test can `text("CREATE TABLE stretch_opportunities (id INTEGER PRIMARY KEY)")` manually after the autouse fixture has prepared the engine).

**Test list:**
- `test_rename_stretch_opportunities`
- `test_rename_idempotent`
- `test_strategy_name_column`
- `test_strategy_name_index_exists` (verify `ix_trades_strategy_name`)
- `test_engine_timeout` (assert `engine.url.query` or `connect_args["timeout"] == 5`)

---

### `tests/test_sport_stats.py` (MOD per D-22)

**Analog (self):** Existing test at `tests/test_sport_stats.py:1-55`.

#### Existing test seeds StretchOpportunity rows (test_sport_stats.py:4, 27-41)

```python
from predictions.db import StretchOpportunity, Trade, get_session
...
session.add(
    StretchOpportunity(
        ticker="KXMLBSTGAME-TEST-BOS-NYY",
        event_ticker="KXMLBSTGAME-TEST-BOS-NYY",
        series_ticker="KXMLBSTGAME",
        sport_path="baseball/mlb",
    )
)
session.add(
    StretchOpportunity(
        ticker="KXMLBGAME-MATCH-2-BOS-NYY",
        event_ticker="KXMLBGAME-MATCH-2-BOS-NYY",
        series_ticker="KXMLBGAME",
        sport_path="baseball/mlb",
    )
)
```

**For Phase 3 D-22:** Replace `StretchOpportunity` with `Opportunity` (already exported from `predictions.db`). Set required fields. The new D-19 query is `COUNT(DISTINCT event_ticker)` from `opportunities WHERE series_ticker IS NOT NULL`, so seeded rows must have `series_ticker` and `event_ticker` populated. Assertions on `played` count remain `1` per series (one distinct event_ticker each).

```python
from predictions.db import Opportunity, Trade, get_session
...
session.add(
    Opportunity(
        ticker="KXMLBSTGAME-TEST-BOS-NYY",
        event_ticker="KXMLBSTGAME-TEST-BOS-NYY",
        series_ticker="KXMLBSTGAME",
        sport_path="baseball/mlb",
    )
)
```

`Opportunity` schema at `db.py:32-59` — most columns are nullable so a minimal seed is fine.

---

## Shared Patterns

### Pattern S1: Idempotent migration via inspector guards (D-01, D-03)

**Source:** `src/predictions/db.py:152-207` (existing `_migrate_add_columns`).
**Apply to:** All schema changes in Phase 3 (column add, table rename).

```python
from sqlalchemy import inspect, text
inspector = inspect(engine)

# Column-add guard
if "<table>" in inspector.get_table_names():
    cols = {c["name"] for c in inspector.get_columns("<table>")}
    if "<col>" not in cols:
        with engine.begin() as conn:
            conn.execute(text("ALTER TABLE <table> ADD COLUMN <col> <type>"))
```

```python
# Table-rename guard (NOVEL but composable)
table_names = inspector.get_table_names()
if "<old>" in table_names and "<new>" not in table_names:
    with engine.begin() as conn:
        conn.execute(text("ALTER TABLE <old> RENAME TO <new>"))
```

### Pattern S2: SQLAlchemy combined filter (`or_` + `and_`) (D-16, D-17)

**Source:** RESEARCH.md Standard Stack — `from sqlalchemy import or_, and_`.
**Apply to:** `check_settlements` (scanner.py:206-210), `on_lifecycle` (scanner.py:838-847).

```python
from sqlalchemy import or_, and_

session.query(Trade).filter(
    Trade.status.in_(("placed", "filled", "dry_run")),
    or_(
        Trade.dry_run == False,
        and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),
    ),
)
```

E712 (`== False` / `== True`) is globally ignored in `pyproject.toml:32` — no `# noqa` needed.

### Pattern S3: Loop-level `trading_paused` kill switch (D-23)

**Source:** `src/predictions/scanner.py:523-525`.
**Apply to:** `evaluate_strategies` (top of function — early return).

```python
if get_config("trading_paused") == "true":
    log.info("...trading paused via config — skipping...")
    return  # or `continue` inside a loop
```

D-23 supersedes D-15's "inside `place_strategy_trade`" prose. RESEARCH Pitfall 2 confirms the existing live-trade pattern is loop-level.

### Pattern S4: Permissive log-and-continue inside scanner loops

**Source:** Established convention; examples at `scanner.py:236, 257, 454, 909, 962, 984, 1001`.
**Apply to:** `evaluate_strategies` outer try/except, missing `market_prices` entry, missing game-length lookup, malformed `strategies.yaml`.

```python
try:
    ...
except Exception as e:
    log.warning("...: %s", e)
    continue  # or return, depending on scope
```

CLAUDE.md `.planning/codebase/CONVENTIONS.md`: "log-and-continue for scanner-loop failures — no hard-fail." Per D-05 and DRY-01 RESEARCH support.

### Pattern S5: Bearer-auth on FastAPI endpoints

**Source:** `src/predictions/api.py:484` (`Depends(_check_token)`).
**Apply to:** `/api/sport-stats` (preserved during D-19 swap). No new endpoints in Phase 3.

```python
@app.get("/api/sport-stats", dependencies=[Depends(_check_token)])
def get_total_sport_stats():
    ...
```

### Pattern S6: Test fixture isolation via `isolated_db` autouse

**Source:** `tests/conftest.py:10-24`.
**Apply to:** All Phase 3 test files (autouse — implicit).

The fixture calls `db_module.Base.metadata.create_all(engine)` against the **current** model definitions. After D-20 deletes `StretchOpportunity`, fresh tests see no `stretch_opportunities` table. Migration tests must `text("CREATE TABLE stretch_opportunities (...)")` manually to exercise the rename.

---

## No Analog Found

| File / Construct | Reason | Mitigation |
|------------------|--------|-----------|
| Table rename (`stretch_opportunities` → `_archived`) | First rename migration in the codebase | Compose with existing column-add guard pattern; see Pattern S1. RESEARCH-verified safe. |
| `tests/test_strategy_settlement.py` | No existing test exercises `check_settlements` / `on_lifecycle` | Compose Trade-seeding pattern + minimal `FakeClient`; consider extracting `on_lifecycle` to module-level for testability (planner judgment). |
| `tests/test_db_migrations.py` | No existing migration test | Compose engine/inspector primitives directly; document the test recipe in PLAN.md. |
| `place_strategy_trade` "no-Kalshi-REST" branch | `place_bet`'s `dry_run=True` branch is intentionally not reused per D-13 | Copy the Trade(...) constructor + log line + session lifecycle from `place_bet`; omit the REST call entirely. |

---

## Metadata

**Analog search scope:**
- `src/predictions/scanner.py` (1043 lines)
- `src/predictions/db.py` (290 lines)
- `src/predictions/api.py` (lines 480-555, 820-905)
- `src/predictions/strategies.py` (104 lines)
- `src/predictions/espn.py` (lines 30-120)
- `tests/conftest.py`, `tests/test_strategies.py`, `tests/test_sport_stats.py`
- `dashboard/app/page.tsx` (lines 140-160, 2185-2280, 2380-2420, 2615-2691)

**Files scanned:** 9
**Pattern extraction date:** 2026-05-01

**Phase 2 D-02 OVERRIDE confirmed:** `02-CONTEXT.md:482-496` — `trigger.sport` is sport-family literal (`football`, never `soccer`); UK terminology. All Phase 3 patterns honor this.

**Dashboard path correction:** `dashboard/app/page.tsx` (not `dashboard/src/app/page.tsx`).
