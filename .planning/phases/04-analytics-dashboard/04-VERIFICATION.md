---
phase: 04-analytics-dashboard
verified: 2026-05-07T09:42:00Z
status: human_needed
score: 8/8 must-haves verified
overrides_applied: 0
re_verification:
  previous_status: gaps_found
  previous_score: 6/8
  gaps_closed:
    - "Cumulative P&L line chart populates for the selected strategy in production (Success Criterion 1) — CR-01 fixed in commits 230c2e3 + 7415f39 + b6194c8"
    - "Strategies with zero trades show empty charts and zeroed stat cards rather than 404 or blank page — automatically resolved when CR-01 closed (zero-trade and settled-but-empty states are now distinguishable in production)"
  gaps_remaining: []
  regressions: []
gaps:
  - truth: "Cumulative P&L line chart populates for the selected strategy in production (Success Criterion 1)"
    status: resolved
    resolution: "Commit 230c2e3 added `trade.settled_at = datetime.now(timezone.utc)` to BOTH settlement paths in src/predictions/scanner.py: line 306 in check_settlements (REST poller) and line 362 in on_lifecycle (WS handler). Commit 7415f39 added an idempotent backfill in src/predictions/db.py:_migrate_add_columns (lines 143-157) that UPDATEs settled_at = placed_at WHERE settled_at IS NULL AND status IN ('settled_win', 'settled_loss'), so historical strategies render a curve immediately after deploy. Commit b6194c8 added tests/test_strategy_settlement.py with assertions that trade.settled_at is not None after both settlement paths (lines 65, 104), and tests/test_db_migrations.py with test_backfill_settled_at + test_backfill_settled_at_idempotent (lines 104-192). Test suite went from 86 -> 88 passed (the 2 new backfill tests). The chart pipeline is now data-flowing end-to-end for fresh settlements AND historical rows; the operator decision between D-09 (settled_at) and REQUIREMENTS DASH-03 (placed_at) is no longer forced by the missing writer."

  - truth: "Strategies with zero trades show empty charts and zeroed stat cards rather than 404 or blank page (Success Criterion 4)"
    status: resolved
    resolution: "Automatically resolved by CR-01 closure. Now that production-settled trades populate settled_at, the zero-trade pnl_curve (empty list, no rows match the filter) is no longer indistinguishable from a settled-but-disconnected pnl_curve. Test_analytics_zero_trade_strategy continues to pass for explicit zero-trade YAML strategies. No code change needed beyond CR-01."

deferred: []

human_verification:
  - test: "Open /analytics in a browser with a populated DB (real settled trades, not test fixtures); select a strategy known to have settled wins/losses"
    expected: "Cumulative P&L chart renders with at least one point per settled trade; chart and stat-card realized P&L should reconcile (final running sum on chart == realized_pnl_cents stat card)"
    why_human: "Unit + migration tests now cover the writer and backfill paths, but only a real DB or live scanner run can confirm the chart populates end-to-end. After CR-01 the expected outcome flips from 'empty chart' to 'populated chart' — human verification still required to confirm runtime success."

  - test: "Click a strategy in the sidebar; observe the URL change; press the browser back button"
    expected: "Page returns to the previously selected strategy"
    why_human: "WR-04 in 04-REVIEW.md flagged that the page does not register a popstate listener. Behavior is observable only in a real browser — automated checks cannot exercise the back/forward stack. NOT addressed by the CR-01 commits (still open advisory)."

  - test: "Wait 5 minutes (or override interval) on /analytics with a populated DB; confirm new dry-run trades appear without manual reload (Success Criterion 3)"
    expected: "lastUpdated timestamp updates; if a new trade is seeded between fetches, it appears in the trade log on the next refresh"
    why_human: "setInterval(fetchAll, 5 * 60 * 1000) is wired in code, but actual refetch behavior over time + DOM update on new data is a runtime/UI concern — not provable from the source alone."

  - test: "Visit /analytics without a valid auth cookie (incognito or after logout)"
    expected: "Page redirects to / immediately; no analytics data fetched"
    why_human: "checkAuth() is called inside useEffect and triggers window.location.href = '/' on failure. The redirect-vs-data-leak race condition is a runtime concern; only a browser session can confirm no API calls fire pre-redirect."
---

# Phase 04: Analytics Dashboard — Verification Report

**Phase Goal:** Users can inspect per-strategy dry-run performance in the dashboard with live-updating data
**Verified:** 2026-05-07T09:42:00Z (re-verification)
**Status:** human_needed
**Re-verification:** Yes — after CR-01 gap closure (commits 230c2e3, 7415f39, b6194c8)

## Re-Verification Summary

Previous verification (2026-05-07T08:27:50Z) reported `gaps_found` with score 6/8: two gaps both rooted in CR-01 (the `Trade.settled_at` writer bug). Three atomic fix commits landed:

- **230c2e3** — `fix(scanner): write Trade.settled_at on settlement (Phase 04 gap CR-01)` — adds writes at scanner.py:306 (check_settlements / REST poller) and scanner.py:362 (on_lifecycle / WS handler).
- **7415f39** — `fix(db): backfill settled_at from placed_at for historical settled rows` — adds idempotent backfill UPDATE in db.py:_migrate_add_columns:150-157.
- **b6194c8** — `test(04): assert settled_at is written by both settlement paths and backfilled` — adds tests/test_strategy_settlement.py assertions and tests/test_db_migrations.py:test_backfill_settled_at + test_backfill_settled_at_idempotent.

All four mechanical claims independently verified against the codebase:

| Claim | Verified Against | Result |
|-------|------------------|--------|
| Both settlement paths assign `settled_at` | `grep -rn 'settled_at\s*=' src/` shows writes at scanner.py:306 and scanner.py:362 (plus the column declaration at db.py:80 and the response serialization at api.py:463) | CONFIRMED |
| `_migrate_add_columns` backfills NULL settled_at for settled rows | `src/predictions/db.py:150-157` — `UPDATE trades SET settled_at = placed_at WHERE settled_at IS NULL AND status IN ('settled_win', 'settled_loss')` | CONFIRMED |
| `tests/test_strategy_settlement.py` asserts `trade.settled_at is not None` after both paths | Lines 65 (REST path), 104 (WS path) | CONFIRMED |
| `tests/test_db_migrations.py` adds `test_backfill_settled_at` + `test_backfill_settled_at_idempotent` | Lines 104-157 (backfill correctness), 160-192 (idempotency) | CONFIRMED |
| `uv run pytest tests/ -q` reports 88 passed (was 86) | Output: `88 passed, 1 skipped in 1.11s` (+2 = new backfill tests) | CONFIRMED |

Both gaps are now `resolved`. Score raised to **8/8 must-haves verified**.

The four `human_verification` items from the previous run still apply — the real-DB chart-population test (item 1) flips its expected outcome from "empty chart" to "populated chart" after CR-01, but still requires browser/runtime confirmation. WR-01..WR-04 advisories from 04-REVIEW.md were NOT addressed by these commits and remain open.

## Goal Achievement

### Observable Truths (derived from ROADMAP Success Criteria + REQUIREMENTS DASH-03/DASH-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A new dashboard page (behind `checkAuth` gate) shows a strategy selector | VERIFIED | `dashboard/app/analytics/page.tsx:132-137` — `checkAuth()` called in useEffect, redirects to `/` on failure. Sidebar listing rendered from `/api/strategies-summary` (lines 217-233). |
| 2 | The page shows summary stat cards (total trades, wins, losses, win rate, realized P&L) for the selected strategy | VERIFIED | `dashboard/app/analytics/page.tsx:242-267` — five `<StatCard>` components rendered: Total Trades, Wins, Losses, Win Rate, Realized P&L. Values bound to `detail.stats`. Backend supplies all five fields via `StrategyAnalyticsStats` (`api.py:146-152`). |
| 3 | The page shows a cumulative P&L line chart for the selected strategy | VERIFIED (re-verification) | Chart wired (`page.tsx:269-316` — `<LineChart data={detail?.pnl_curve ?? []}>`). API filter at `api.py:482-501` orders by `Trade.settled_at` and skips NULL rows; the writer that populates `settled_at` is now present at `scanner.py:306` (check_settlements) and `scanner.py:362` (on_lifecycle). Historical NULL rows are backfilled by `db.py:_migrate_add_columns:150-157`. Tests at `test_strategy_settlement.py:65,104` assert `trade.settled_at is not None` after both settlement paths. Production data flow is now end-to-end intact. |
| 4 | A trade log table shows per-trade detail (date, ticker, entry price, contracts, P&L, status) for the selected strategy | VERIFIED | `dashboard/app/analytics/page.tsx:318-385` — `<table>` with columns Date, Ticker, Price, Contracts, P&L, Status. Backend supplies these via `StrategyAnalyticsTrade` (`api.py:155-164`). Trade log table is independent of `settled_at` (uses `placed_at` for ordering and date display). |
| 5 | The page auto-refreshes every 5 minutes; new dry-run trades appear without a manual reload | VERIFIED (code path) | `dashboard/app/analytics/page.tsx:192` — `setInterval(fetchAll, 5 * 60 * 1000)`. Cleanup at line 195. fetchAll re-fetches both `/api/strategies-summary` and `/api/strategy-analytics`. Runtime behavior requires human verification — see human_verification list. |
| 6 | Strategies with zero trades appear in the selector but show empty charts and zeroed stat cards rather than 404 or blank page | VERIFIED (re-verification) | Backend: `api.py:566-586` — YAML+DB merge inserts zero-trade YAML strategies with all-zero aggregates. Test `test_summary_includes_zero_trade_strategies` and `test_analytics_zero_trade_strategy` both pass. Frontend renders empty `pnl_curve` as axes-only chart (D-11) and trade log as `&nbsp;` cell. After CR-01, zero-trade and settled-state pages are distinguishable in production again. |
| 7 | The page is behind `checkAuth` gate (Success Criterion 1, REQUIREMENTS DASH-03) | VERIFIED | `dashboard/app/analytics/page.tsx:132-137` — auth useEffect redirects to `/` on `checkAuth() === false`. Page renders only when `authed === true` (line 199). Both new API endpoints attach `dependencies=[Depends(_check_token)]` (api.py:424, :521). curl smoke confirmed: 401 without Bearer, 200 with Bearer. |
| 8 | URL `?strategy=<name>` is refresh-stable and deep-linkable (4-02 PLAN must_have, supports SC 1) | VERIFIED | `page.tsx:142-146` reads `URLSearchParams(window.location.search)` on mount; `selectStrategy()` (lines 148-153) calls `window.history.pushState`. WR-04 from 04-REVIEW.md (no `popstate` listener) remains open as an advisory; back/forward navigation does not sync state. |

**Score:** 8/8 truths verified.

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|---------|--------|---------|
| `src/predictions/api.py` | TradeResponse.strategy_name; StrategyAnalyticsResponse + 3 sub-models; StrategiesSummaryResponse + entry; GET /api/strategy-analytics; GET /api/strategies-summary | VERIFIED | All 7 Pydantic classes present (api.py:60-189). TradeResponse.strategy_name at line 76. Both endpoint handlers present (api.py:421-515, :518-588) with `Depends(_check_token)`. SQL queries are ORM-parameterized — no raw SQL. |
| `src/predictions/scanner.py` | check_settlements + on_lifecycle write `trade.settled_at` on settlement | VERIFIED (re-verification) | Writes at lines 306 (REST poller) and 362 (WS handler). |
| `src/predictions/db.py` | `_migrate_add_columns` backfills `settled_at` from `placed_at` for historical settled rows | VERIFIED (re-verification) | Lines 143-157. Idempotent (only touches NULL rows). |
| `tests/test_strategy_analytics.py` | 7 passing tests, 0 xfail | VERIFIED | `uv run pytest tests/test_strategy_analytics.py -v` reports `7 passed`. All xfail markers removed. |
| `tests/test_strategy_settlement.py` | Asserts `trade.settled_at is not None` after both settlement paths | VERIFIED (re-verification) | Lines 65 (REST) and 104 (WS). |
| `tests/test_db_migrations.py` | `test_backfill_settled_at` + `test_backfill_settled_at_idempotent` | VERIFIED (re-verification) | Lines 104-157 and 160-192. |
| `tests/conftest.py` | seed_trades(engine, rows) helper; isolated_db fixture upgraded to StaticPool | VERIFIED | `seed_trades` defined as plain (non-fixture) helper. StaticPool added to both `isolated_db` and `isolated_soccer_db` fixtures. |
| `dashboard/app/analytics/page.tsx` | "use client"; checkAuth import; recharts named imports; AnalyticsPage default export; setInterval 5 min; pushState; URLSearchParams | VERIFIED | 396 lines. All required patterns present. Build clean (`pnpm build` exits 0; `/analytics` prerendered as static). |
| `dashboard/app/page.tsx` | Trade interface adds strategy_name?; header `<a href="/analytics">`; trades-table conditional cross-link | VERIFIED | strategy_name field at line 46. Header link at lines 2315-2320. Cross-link with `encodeURIComponent` at lines 2668-2675. |
| `pyproject.toml` | ty.environment.root extended to include "tests" | VERIFIED | Required for `uv run ty check` to resolve `from conftest import seed_trades`. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| GET /api/strategy-analytics | Trade.strategy_name (Phase 03 D-01) | `Trade.strategy_name == strategy` filter | WIRED | api.py:438. Index exists per Phase 03. |
| GET /api/strategy-analytics | Phase 03 D-16 composite filter | `or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))` | WIRED (but dead logic) | Filter present at api.py:438-441. WR-01 in 04-REVIEW: simplifies to always-True given the outer `strategy_name == strategy` clause. Not blocking; remains open advisory. |
| GET /api/strategies-summary | load_strategies() YAML loader | `for s in yaml_strategies` merge loop | WIRED | api.py:567-582. |
| TradeResponse | Trade.strategy_name | `strategy_name=t.strategy_name` constructor | WIRED | api.py:625. |
| analytics/page.tsx | GET /api/strategies-summary | `fetch("/api/strategies-summary")` | WIRED | page.tsx:162. |
| analytics/page.tsx | GET /api/strategy-analytics?strategy=<name> | `fetch(...?strategy=${encodeURIComponent(selected)})` | WIRED | page.tsx:164-166. |
| analytics/page.tsx | checkAuth() | `import { checkAuth } from "../actions"` + `checkAuth().then(...)` | WIRED | page.tsx:13, :132-137. |
| dashboard/app/page.tsx header | /analytics route | `<a href="/analytics">` | WIRED | page.tsx:2315-2320. |
| dashboard/app/page.tsx trades table | /analytics?strategy=<name> | conditional `<a href={\`/analytics?strategy=${encodeURIComponent(t.strategy_name)}\`}>` | WIRED | page.tsx:2668-2675. |
| Trade.settled_at writer | scanner.py settlement paths | `trade.settled_at = datetime.now(timezone.utc)` | WIRED (new) | scanner.py:306 (check_settlements), scanner.py:362 (on_lifecycle). |
| Historical NULL rows | _migrate_add_columns backfill | `UPDATE trades SET settled_at = placed_at WHERE settled_at IS NULL AND status IN ('settled_win', 'settled_loss')` | WIRED (new) | db.py:150-157. Idempotent. |

### Data-Flow Trace (Level 4) — `pnl_curve` chart

After CR-01 closure, the previously-broken trace is now intact:

| Layer | Component | Data Source | Real Data? | Status |
|-------|-----------|-------------|------------|--------|
| 1. Chart render | `<LineChart data={detail?.pnl_curve ?? []}>` (page.tsx:275) | `detail.pnl_curve` from API response | Yes | FLOWING |
| 2. API serialize | `pnl_curve` field of `StrategyAnalyticsResponse` (api.py:514) | List built from `settled_rows` filtered by `Trade.status IN settled_win/loss` AND ordered by `Trade.settled_at`, with `if t.settled_at is None: continue` (api.py:476-501) | Yes — populated rows now have settled_at set | FLOWING |
| 3. DB query | SQLAlchemy ORM read on `Trade` table | `Trade.settled_at` column populated by writer + backfilled for historical rows | Yes | FLOWING |
| 4. DB writer | `src/predictions/scanner.py:306` (check_settlements) and `:362` (on_lifecycle) | `trade.settled_at = datetime.now(timezone.utc)` on settlement transitions | Yes | FLOWING |
| 5. Historical rows | `src/predictions/db.py:150-157` migration backfill | `UPDATE trades SET settled_at = placed_at WHERE settled_at IS NULL AND status IN ('settled_win', 'settled_loss')` | Yes | FLOWING |

**Conclusion:** The chart pipeline is now end-to-end intact for both fresh settlements (writer) and historical rows (backfill). The previous DISCONNECTED state at layers 3-4 is closed.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend test suite passes | `uv run pytest tests/ -q` | `88 passed, 1 skipped in 1.11s` (+2 from previous run) | PASS |
| New analytics tests pass | `uv run pytest tests/test_strategy_analytics.py -v` | `7 passed` | PASS |
| New settlement tests pass | `uv run pytest tests/test_strategy_settlement.py -v` | included in 88-pass run; asserts settled_at on both paths | PASS |
| Backfill tests pass | `uv run pytest tests/test_db_migrations.py -k backfill -v` | included in 88-pass run; covers correctness + idempotency | PASS |
| `grep -rn 'settled_at\s*=' src/` shows production writers | scanner.py:306, scanner.py:362, db.py:153 (backfill SQL), db.py:80 (column), api.py:463 (response) | 5 hits, including the 2 new writers | PASS |
| Dashboard build clean | `cd dashboard && pnpm build` | exits 0; `/analytics` prerendered as static | PASS (re-checked indirectly via no dashboard changes in fix commits) |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DASH-03 | 04-00, 04-01, 04-02, 04-03 | Per-strategy dashboard page: selector + 5 stat cards + cumulative P&L line chart + trade log; behind checkAuth | SATISFIED (re-verification) | All four sub-elements verified end-to-end. Cumulative P&L chart is now data-flowing (CR-01 closed). REQUIREMENTS.md spec says `x = placed_at`; phase planning chose `x = settled_at` (D-09); the deviation is now functionally equivalent for fresh settlements (settled_at is written) and benign for historical rows (settled_at backfilled to placed_at). |
| DASH-04 | 04-02 | Page auto-refreshes every 5 minutes | SATISFIED (code) / NEEDS HUMAN (runtime) | `setInterval(fetchAll, 5 * 60 * 1000)` at page.tsx:192. Runtime "new data appears" verification requires browser session. |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/predictions/api.py | 488-491 | Comment "Pitfall 5: skip rows where settled_at is NULL" combined with silent `continue` | Info (no longer a blocker after CR-01) | The guard remains correct given the contract; production data is now populated, so the silent-drop failure mode is closed. Could still benefit from a counter/log if a row with NULL ever appears, but this is a minor signal-quality concern, not a goal blocker. |
| src/predictions/api.py | 438-441, 537-540 | "Composite filter" `or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))` is dead logic given the outer clauses | Warning (WR-01 in 04-REVIEW.md) | Misleading code that will rot under refactor. NOT addressed by CR-01 commits — remains open. |
| src/predictions/api.py | 446 | `open_trades` only counts `status == "dry_run"` while `total_trades` counts every row | Warning (WR-02 in 04-REVIEW.md) | Brittle invariant if non-dry-run strategy attribution lands. NOT addressed — remains open. |
| src/predictions/api.py | 542-553 | `/api/strategies-summary` GROUP BY has no ORDER BY for orphan strategies | Warning (WR-03) | Non-deterministic orphan ordering. NOT addressed — remains open. |
| dashboard/app/analytics/page.tsx | 142-146 | URL `?strategy=` read once on mount, no `popstate` listener | Warning (WR-04) | Browser back/forward updates URL but not state. NOT addressed — remains open. |
| dashboard/app/analytics/page.tsx | 186-188 | Empty `catch { }` on 5-min polling fetch | Info (IN-01) | All transport / parse errors swallowed silently. |
| dashboard/app/analytics/page.tsx | 294 | `payload[0].payload as PnlPoint` type assertion without runtime guard | Info (IN-02) | recharts payload-shape rot would silently render empty fields. |
| dashboard/app/analytics/page.tsx | 335-343 | Empty trades table renders `&nbsp;` cell, not "No trades yet" | Info (IN-03) | Per D-11, intentional "clean zeros." |
| tests/conftest.py | 79-81 | `seed_trades` builds its own sessionmaker rather than using monkeypatched `predictions.db.SessionLocal` | Info (IN-05) | Today both point at the same engine; future config drift risk. |

**Open advisories (NOT addressed by CR-01 commits):** WR-01, WR-02, WR-03, WR-04, IN-01..IN-05. These remain as scheduled follow-ups; none block phase exit.

### Human Verification Required

See `human_verification:` block in frontmatter. Four runtime checks remain:

1. **Real-DB chart population** — expected outcome flips from "empty chart" (pre-fix) to "populated chart" (post-fix). Still requires browser confirmation against a real DB or live scanner run.
2. **Browser back/forward state sync (WR-04)** — unchanged; still open advisory.
3. **5-minute auto-refresh runtime behavior** — unchanged; still requires browser observation.
4. **Unauthenticated `/analytics` redirect timing** — unchanged; still requires browser session.

### Gaps Summary

**Both gaps from the previous run are resolved:**

1. **CR-01 / Gap #1 — Cumulative P&L chart empty in production.** RESOLVED by commits 230c2e3 (writer at scanner.py:306 + 362), 7415f39 (idempotent backfill at db.py:150-157), and b6194c8 (regression tests asserting settled_at on both paths + backfill correctness/idempotency). Test count went from 86 -> 88 passed.

2. **Gap #2 — Zero-trade and settled-but-empty states indistinguishable.** RESOLVED automatically by CR-01 closure. Production-settled rows now populate settled_at, so the zero-trade pnl_curve (no rows) is no longer indistinguishable from a settled-but-disconnected one (which can no longer occur).

**Open advisories not addressed by CR-01 commits:**
- WR-01 dead `or_` filter logic in both endpoints
- WR-02 `open_trades` definition will not reconcile with `total_trades` once non-dry-run strategy attribution lands
- WR-03 non-deterministic orphan ordering in `/api/strategies-summary`
- WR-04 no `popstate` listener on analytics page
- IN-01..IN-05 minor code-quality / UX scattering

These can be scheduled as follow-ups; they do not block phase exit on their own. Phase status moves from `gaps_found` to `human_needed` — the four runtime/UI checks in `human_verification:` are the only remaining items before phase closure.

---

_Verified: 2026-05-07T09:42:00Z (re-verification after CR-01 gap closure)_
_Verifier: Claude (gsd-verifier)_
