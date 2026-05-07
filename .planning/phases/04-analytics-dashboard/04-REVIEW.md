---
phase: 04-analytics-dashboard
reviewed: 2026-05-07T00:00:00Z
depth: standard
files_reviewed: 5
files_reviewed_list:
  - src/predictions/api.py
  - tests/test_strategy_analytics.py
  - tests/conftest.py
  - dashboard/app/analytics/page.tsx
  - dashboard/app/page.tsx
findings:
  critical: 1
  warning: 4
  info: 5
  total: 10
status: issues_found
---

# Phase 04: Code Review Report

**Reviewed:** 2026-05-07
**Depth:** standard
**Files Reviewed:** 5
**Status:** issues_found

## Summary

The two new endpoints (`GET /api/strategy-analytics`, `GET /api/strategies-summary`) and the `/analytics` dashboard route are wired up correctly: auth dep is attached, the proxy route forwards the Bearer token, the SQLAlchemy queries are parameterized, and the `recharts` chart uses a fixed pixel height (Pitfall 6 avoided). Tests cover the core aggregation paths.

However the P&L chart — the marquee feature of this phase — is broken in production because the column it sorts on (`Trade.settled_at`) is **never written by the settlement path**. The endpoint correctly skips NULL `settled_at` rows (Pitfall 5), so production data will yield an empty chart while the stat cards show non-zero realized P&L. The bug is in pre-existing settlement code (`src/predictions/scanner.py`), but Phase 04 is the consumer that exposes it. Tests synthesize `settled_at` in the seed helper, masking the issue.

Other notable findings: the `or_(...)` "composite filter" in both new endpoints is dead logic (always evaluates True given the surrounding clauses), the `open_trades` field counts only `status="dry_run"` so totals will not reconcile once real-money strategy attribution lands, sidebar selection ignores browser back/forward, and there's a code-style/UX scattering of smaller issues.

## Critical Issues

### CR-01: P&L chart is empty in production — `settled_at` is never written

**Files:**
- `src/predictions/api.py:476-501` (consumer — Phase 04 scope)
- `src/predictions/scanner.py:303-319` and `350-369` (writer — pre-existing, but blocking Phase 04)

**Issue:**
`get_strategy_analytics` builds the `pnl_curve` by iterating settled trades ordered by `Trade.settled_at`, and explicitly skips rows where `settled_at is None`:

```python
.order_by(Trade.settled_at)
...
for t in settled_rows:
    if t.settled_at is None:
        continue
```

The two production paths that move a trade to `settled_win` / `settled_loss` (REST settlement poller and WebSocket lifecycle handler) set `trade.status` and `trade.pnl_cents` but **never assign `trade.settled_at`**. A grep confirms the only writes to `settled_at` are in test fixtures:

```
src/predictions/scanner.py:307:    trade.status = "settled_win"
src/predictions/scanner.py:308:    trade.pnl_cents = trade.potential_profit_cents - fee
src/predictions/scanner.py:314:    trade.status = "settled_loss"
src/predictions/scanner.py:362:    trade.status = "settled_win"
src/predictions/scanner.py:366:    trade.status = "settled_loss"
```

Production effect:
- All settled real-money trades have `settled_at = NULL`.
- `pnl_curve` is empty for every strategy regardless of how many trades have settled.
- `realized_pnl_cents` (computed via `func.sum(Trade.pnl_cents)`) is non-zero, but the chart is flat/empty — silent divergence between the stat card and the chart for the same strategy.

The unit tests pass because `tests/test_strategy_analytics.py:_make_row` synthesizes `settled_at` whenever `status != "dry_run"`. There is no integration test exercising the real settlement-write path against the new endpoint.

**Fix:** Set `settled_at` when transitioning a Trade to a settled status. In `src/predictions/scanner.py` (both settlement sites):

```python
from datetime import datetime, timezone
...
if status in ("finalized", "settled"):
    fee = trade.fee_cents or 0
    tag = "STRATEGY" if trade.strategy_name else "REAL"
    trade.settled_at = datetime.now(timezone.utc)  # add this
    if result == trade.side:
        trade.status = "settled_win"
        trade.pnl_cents = trade.potential_profit_cents - fee
    else:
        trade.status = "settled_loss"
        trade.pnl_cents = -trade.cost_cents - fee
```

Then add a backfill — for already-settled rows, set `settled_at = placed_at` (best available proxy) so historical strategies show a curve at all. Without backfill, the chart only starts populating from the deploy date.

Add an integration test that drives a Trade through settlement (or at least asserts `settled_at` is non-NULL after settlement) so this regression cannot recur.

## Warnings

### WR-01: "composite filter" `or_(...)` is dead logic in both new endpoints

**Files:**
- `src/predictions/api.py:438-441` (`get_strategy_analytics`)
- `src/predictions/api.py:537-540` (`get_strategies_summary`)

**Issue:** The filter expression in both endpoints is:

```python
or_(
    Trade.dry_run == False,
    and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),
)
```

In `get_strategy_analytics`, the outer clause is `Trade.strategy_name == strategy` — `strategy` is a non-NULL request string, so `strategy_name.isnot(None)` is always True for any matching row. The `or_` simplifies to `dry_run == False OR (dry_run == True AND True)`, i.e. always True. It does no filtering.

In `get_strategies_summary`, the outer clause is `Trade.strategy_name.isnot(None)`. The `and_(dry_run == True, strategy_name.isnot(None))` inner is again always True, so the `or_` simplifies the same way.

Effect: the comments claim "Phase 03 D-16 symmetry" and "excludes legacy process-level dry-run rows," but the code does no such thing — the legacy exclusion happens entirely because `strategy_name == strategy` (or `strategy_name IS NOT NULL`) excludes NULL-strategy rows. The dead clause is misleading and will rot if anyone refactors it.

**Fix:** Either remove the dead `or_` and update the comment to say "we exclude legacy dry-run via `strategy_name IS NOT NULL`", or replace the clause with what the comment says it does. The minimal correct form is:

```python
strategy_filter = Trade.strategy_name == strategy
```

If you genuinely need to keep real-money trades attributed to a strategy AND dry-run-with-strategy AND exclude something, write the clause that names the case being excluded. The current form just looks safe.

### WR-02: `open_trades` definition makes `total_trades` not reconcile with `wins + losses + open_trades`

**File:** `src/predictions/api.py:443-446`

**Issue:**

```python
total = session.query(Trade).filter(strategy_filter).count()
wins = ...status == "settled_win"...
losses = ...status == "settled_loss"...
open_trades = ...status == "dry_run"...
```

`total` counts every status (`dry_run`, `placed`, `filled`, `settled_*`, `error`, etc.). `open_trades` only counts `status == "dry_run"`. Today this works because strategy attribution only fires on dry-runs (Phase 03 D-13), so `placed` / `filled` / `error` rows for a strategy are zero.

The instant real-money strategy attribution lands (a roadmap item), or any `error`-status row gets a `strategy_name`, the dashboard will show e.g. `Total: 5, Wins: 1, Losses: 1, Open: 0` — a 3-trade discrepancy with no UI explanation. Users will reasonably treat the analytics page as broken.

**Fix:** Either widen `open_trades` to include the real "open" states (`Trade.status.in_(("placed", "filled", "dry_run"))`), or add an explicit `other`/`error` counter so totals reconcile. Pick one and document the invariant `total == wins + losses + open + other` in the response model.

### WR-03: orphan-strategy ordering in `/api/strategies-summary` is non-deterministic

**File:** `src/predictions/api.py:553, 583-586`

**Issue:** The GROUP BY query has no `ORDER BY`, so SQLite returns rows in undefined order. `db_by_name` iteration order then determines orphan order in the response. Across DB engines, restarts, or compaction, the orphan tail can reshuffle, causing test flakiness if anyone writes ordered assertions and visible row jitter for users on the analytics sidebar after a strategy is renamed.

**Fix:** Add a deterministic order. Either order the SQL:

```python
.group_by(Trade.strategy_name)
.order_by(Trade.strategy_name)
```

…or sort orphans by name when appending:

```python
for name in sorted(db_by_name.keys() - seen):
    result.append(StrategySummaryEntry(**db_by_name[name]))
```

### WR-04: analytics page does not sync to browser back/forward

**File:** `dashboard/app/analytics/page.tsx:142-153`

**Issue:** `?strategy=…` is read once on mount via the `[]`-deps `useEffect`. `selectStrategy` calls `window.history.pushState`, but no `popstate` listener is registered. Pressing the browser back button after switching strategies updates the URL but leaves the page showing the previously selected strategy — `selected` state is stale.

**Fix:** Add a `popstate` listener that re-reads the search param and calls `setSelected`:

```tsx
useEffect(() => {
  const onPop = () => {
    const params = new URLSearchParams(window.location.search);
    setSelected(params.get("strategy"));
  };
  window.addEventListener("popstate", onPop);
  return () => window.removeEventListener("popstate", onPop);
}, []);
```

Also reduces the "back button does nothing" complaint when a user lands on the page via the per-row cross-link in `dashboard/app/page.tsx`.

## Info

### IN-01: empty `catch {}` in 5-minute polling effect silences all transport errors

**File:** `dashboard/app/analytics/page.tsx:186-188`

**Issue:** The catch block is empty with a comment claiming "project pattern." Network errors, 401s, JSON parse errors, and bugs all disappear silently — the page just keeps showing stale data with no indication. The "Updated …" timestamp also isn't updated on failure (because the throw happens before `setLastUpdated`), but there's no negative signal either.

**Fix:** At minimum log the error and set a state flag so the header can show "Stale (last fetch failed)." Match the project pattern only if the project pattern is truly silent failure — otherwise log:

```tsx
} catch (e) {
  console.error("analytics fetch failed", e);
}
```

### IN-02: `payload[0].payload as PnlPoint` type assertion will rot silently if recharts changes payload shape

**File:** `dashboard/app/analytics/page.tsx:294`

**Issue:** Single-point assertion with no runtime guard. If recharts ever wraps the payload (it has between major versions), `d.x` becomes `undefined` and the tooltip silently renders empty fields rather than throwing.

**Fix:** Add a minimal shape guard:

```tsx
const d = payload[0]?.payload as PnlPoint | undefined;
if (!d) return null;
```

### IN-03: empty-trades placeholder renders `&nbsp;` instead of an empty-state message

**File:** `dashboard/app/analytics/page.tsx:335-343`

**Issue:** When the selected strategy has zero trades, the table shows a single blank cell. Users see "Trades" header + empty box and assume the page is broken.

**Fix:** Render a real message (`No trades yet for this strategy.`) — matches the sidebar empty state pattern at line 222.

### IN-04: SQLAlchemy `Trade.dry_run == False` triggers ruff E712 in most projects; relying on the `==` is correct here but worth a comment

**Files:**
- `src/predictions/api.py:323, 325, 329, 335, 358, 371, 439, 538, 652, 705`

**Issue:** SQLAlchemy ORM does require `== False` / `== True` (operator overloading) instead of the Pythonic `is False`. Project code is correct, but if anyone runs `ruff --select E712` they will get a flood of false positives and may "fix" them, breaking the queries silently.

**Fix:** If not already, add `E712` to `ignore` in `pyproject.toml` ruff config, or `# noqa: E712` on the lines. Pure code-quality nit.

### IN-05: `seed_trades` helper builds its own sessionmaker rather than going through the patched `predictions.db.SessionLocal`

**File:** `tests/conftest.py:79-81`

**Issue:** The fixture monkeypatches `db_module.SessionLocal`, but `seed_trades` constructs `Session = sessionmaker(bind=engine)` from the engine arg directly. Today this works because both sessionmakers point at the same engine. If `predictions.db` ever adds session-level config (events, expire_on_commit overrides, etc.) the seed path will diverge from the production path and tests will pass on data that the production code can't read.

**Fix:** Import `SessionLocal` from `predictions.db` after the monkeypatch and use it:

```python
from predictions.db import SessionLocal
session = SessionLocal()
```

---

_Reviewed: 2026-05-07_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
