---
phase: 04-analytics-dashboard
verified: 2026-05-07T08:27:50Z
status: gaps_found
score: 6/8 must-haves verified
overrides_applied: 0
gaps:
  - truth: "Cumulative P&L line chart populates for the selected strategy in production (Success Criterion 1)"
    status: failed
    reason: "Backend pnl_curve filter requires non-NULL Trade.settled_at, but production settlement code in src/predictions/scanner.py never writes settled_at. Tests pass only because the seed helper synthesizes settled_at. Real settled trades will yield an empty pnl_curve while realized_pnl_cents stat card shows a non-zero value — silent divergence between chart and stat card."
    artifacts:
      - path: "src/predictions/scanner.py"
        issue: "check_settlements (lines 297-323) and on_lifecycle (lines 327-372) set trade.status to settled_win/settled_loss and trade.pnl_cents, but never assign trade.settled_at. Confirmed by grep -rn 'settled_at\\s*=' src/ — only the model column declaration appears; no writes anywhere in production code."
      - path: "src/predictions/api.py"
        issue: "Lines 482-501: pnl_curve query orders by Trade.settled_at and explicit guard at line 490 'if t.settled_at is None: continue' silently drops every production-settled row from the chart."
      - path: "tests/test_strategy_analytics.py"
        issue: "Lines 33-51: _make_row helper synthesizes settled_at = datetime(2026,5,1,13,0, tzinfo=utc) when status != 'dry_run'. This masks the bug — there is no integration test that drives a Trade through the real settlement path and asserts settled_at is populated."
    missing:
      - "Set trade.settled_at = datetime.now(timezone.utc) in BOTH src/predictions/scanner.py:check_settlements (after line 303) and src/predictions/scanner.py:on_lifecycle (after line 358)"
      - "Backfill: UPDATE trades SET settled_at = placed_at WHERE settled_at IS NULL AND status IN ('settled_win', 'settled_loss') so historical strategies render a curve at all"
      - "Integration test that drives a Trade through settlement (or asserts settled_at is non-NULL after a settled status transition) so this regression cannot recur"
      - "Decision required from operator: align with REQUIREMENTS.md DASH-03 spec (x = placed_at, no Pitfall 5 needed) OR keep planning decision D-09 (x = settled_at, requires the writer fix above). The current code is the latter without the writer."

  - truth: "Strategies with zero trades show empty charts and zeroed stat cards rather than 404 or blank page (Success Criterion 4) — verified for explicit zero-trade YAML strategies, but ALSO holds for any selected strategy with at least one trade until the chart-writer bug is fixed"
    status: partial
    reason: "Test_analytics_zero_trade_strategy passes — a never-seeded strategy correctly returns 200 with all-zero stats and empty pnl_curve, and the analytics page renders empty axes + empty table body without copy. However, in production this 'zero state' will be visually indistinguishable from a fully-populated strategy whose chart silently drops every row due to the settled_at writer bug (CR-01 / gap above). Users cannot tell whether the strategy has zero trades or has settled trades that the system is silently hiding."
    artifacts:
      - path: "src/predictions/api.py"
        issue: "get_strategy_analytics correctly returns empty pnl_curve for zero-trade strategies, but the same empty pnl_curve is also produced for strategies with settled trades whose settled_at was never written (production path). The two states are indistinguishable in the API response."
    missing:
      - "Resolution depends on the CR-01 fix: once settled_at is populated by production, this distinction becomes meaningful again"

deferred: []

human_verification:
  - test: "Open /analytics in a browser with a populated DB (real settled trades, not test fixtures); select a strategy known to have settled wins/losses"
    expected: "Cumulative P&L chart renders with at least one point per settled trade; chart and stat-card realized P&L should reconcile (final running sum on chart == realized_pnl_cents stat card)"
    why_human: "The unit tests synthesize settled_at; only a real DB or live scanner run can confirm whether the chart populates with production data. Until CR-01 is fixed the answer will be 'empty chart even with settled trades' — but human verification is needed to confirm the failure mode end-to-end."

  - test: "Click a strategy in the sidebar; observe the URL change; press the browser back button"
    expected: "Page returns to the previously selected strategy"
    why_human: "WR-04 in 04-REVIEW.md flagged that the page does not register a popstate listener. Behavior is observable only in a real browser — automated checks cannot exercise the back/forward stack."

  - test: "Wait 5 minutes (or override interval) on /analytics with a populated DB; confirm new dry-run trades appear without manual reload (Success Criterion 3)"
    expected: "lastUpdated timestamp updates; if a new trade is seeded between fetches, it appears in the trade log on the next refresh"
    why_human: "setInterval(fetchAll, 5 * 60 * 1000) is wired in code, but actual refetch behavior over time + DOM update on new data is a runtime/UI concern — not provable from the source alone."

  - test: "Visit /analytics without a valid auth cookie (incognito or after logout)"
    expected: "Page redirects to / immediately; no analytics data fetched"
    why_human: "checkAuth() is called inside useEffect and triggers window.location.href = '/' on failure. The redirect-vs-data-leak race condition is a runtime concern; only a browser session can confirm no API calls fire pre-redirect."
---

# Phase 04: Analytics Dashboard — Verification Report

**Phase Goal:** Users can inspect per-strategy dry-run performance in the dashboard with live-updating data
**Verified:** 2026-05-07T08:27:50Z
**Status:** gaps_found
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths (derived from ROADMAP Success Criteria + REQUIREMENTS DASH-03/DASH-04)

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | A new dashboard page (behind `checkAuth` gate) shows a strategy selector | VERIFIED | `dashboard/app/analytics/page.tsx:132-137` — `checkAuth()` called in useEffect, redirects to `/` on failure. Sidebar listing rendered from `/api/strategies-summary` (lines 217-233). |
| 2 | The page shows summary stat cards (total trades, wins, losses, win rate, realized P&L) for the selected strategy | VERIFIED | `dashboard/app/analytics/page.tsx:242-267` — five `<StatCard>` components rendered: Total Trades, Wins, Losses, Win Rate, Realized P&L. Values bound to `detail.stats`. Backend supplies all five fields via `StrategyAnalyticsStats` (`api.py:146-152`). |
| 3 | The page shows a cumulative P&L line chart for the selected strategy | FAILED (production) | Chart component is wired (`page.tsx:269-316` — `<LineChart data={detail?.pnl_curve ?? []}>`), and tests prove it renders correctly with synthesized `settled_at`. **However**, `src/predictions/api.py:482-490` orders pnl_curve by `Trade.settled_at` and explicitly skips rows with `settled_at IS NULL`. `src/predictions/scanner.py:297-323` (REST poller) and `:327-372` (WS handler) NEVER write `trade.settled_at`. Production-settled trades have `settled_at = NULL` and are silently dropped. **The marquee chart is empty for any strategy with real settled trades.** See gap #1. |
| 4 | A trade log table shows per-trade detail (date, ticker, entry price, contracts, P&L, status) for the selected strategy | VERIFIED | `dashboard/app/analytics/page.tsx:318-385` — `<table>` with columns Date, Ticker, Price, Contracts, P&L, Status. Backend supplies these via `StrategyAnalyticsTrade` (`api.py:155-164`) — note: per-trade entry price is `yes_price` rendered as `{t.yes_price}c`; "contracts" is `t.count`. Trade rows render. Trade log table is independent of `settled_at` (uses `placed_at` for ordering and date display). |
| 5 | The page auto-refreshes every 5 minutes; new dry-run trades appear without a manual reload | VERIFIED (code path) | `dashboard/app/analytics/page.tsx:192` — `setInterval(fetchAll, 5 * 60 * 1000)`. Cleanup at line 195. fetchAll re-fetches both `/api/strategies-summary` and `/api/strategy-analytics`. Runtime behavior (does new data actually appear after 5 min) requires human verification — see human_verification list. |
| 6 | Strategies with zero trades appear in the selector but show empty charts and zeroed stat cards rather than 404 or blank page | VERIFIED (test) / PARTIAL (production) | Backend: `api.py:566-586` — YAML+DB merge inserts zero-trade YAML strategies with all-zero aggregates. Test `test_summary_includes_zero_trade_strategies` and `test_analytics_zero_trade_strategy` both pass. Frontend renders empty `pnl_curve` as axes-only chart (D-11) and trade log as `&nbsp;` cell. **However**, due to gap #1, this "zero state" is visually identical to a strategy with real settled trades whose `settled_at` was never written — users cannot distinguish the two cases. See gap #2. |
| 7 | The page is behind `checkAuth` gate (Success Criterion 1, REQUIREMENTS DASH-03) | VERIFIED | `dashboard/app/analytics/page.tsx:132-137` — auth useEffect redirects to `/` on `checkAuth() === false`. Page renders only when `authed === true` (line 199). Both new API endpoints attach `dependencies=[Depends(_check_token)]` (api.py:424, :521). curl smoke confirmed: 401 without Bearer, 200 with Bearer. |
| 8 | URL `?strategy=<name>` is refresh-stable and deep-linkable (4-02 PLAN must_have, supports SC 1) | VERIFIED | `page.tsx:142-146` reads `URLSearchParams(window.location.search)` on mount; `selectStrategy()` (lines 148-153) calls `window.history.pushState`. Note WR-04 from 04-REVIEW.md: no `popstate` listener — back/forward navigation does not sync state. Flagged as warning, not blocking. |

**Score:** 6/8 truths verified (Truth 3 FAILED, Truth 6 PARTIAL).

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|---------|--------|---------|
| `src/predictions/api.py` | TradeResponse.strategy_name; StrategyAnalyticsResponse + 3 sub-models; StrategiesSummaryResponse + entry; GET /api/strategy-analytics; GET /api/strategies-summary | VERIFIED | All 7 Pydantic classes present (api.py:60-189). TradeResponse.strategy_name at line 76. Both endpoint handlers present (api.py:421-515, :518-588) with `Depends(_check_token)`. SQL queries are ORM-parameterized — no raw SQL. |
| `tests/test_strategy_analytics.py` | 7 passing tests, 0 xfail | VERIFIED | `uv run pytest tests/test_strategy_analytics.py -v` reports `7 passed in 0.45s`. All xfail markers removed. |
| `tests/conftest.py` | seed_trades(engine, rows) helper; isolated_db fixture upgraded to StaticPool | VERIFIED | `seed_trades` defined as plain (non-fixture) helper. StaticPool added to both `isolated_db` and `isolated_soccer_db` fixtures (per 04-01-SUMMARY deviation #1). Fixture count remains 2. |
| `dashboard/app/analytics/page.tsx` | "use client"; checkAuth import; recharts named imports; AnalyticsPage default export; setInterval 5 min; pushState; URLSearchParams | VERIFIED | 396 lines. All required patterns present. Build clean (`pnpm build` exits 0; `/analytics` prerendered as static). |
| `dashboard/app/page.tsx` | Trade interface adds strategy_name?; header `<a href="/analytics">`; trades-table conditional cross-link | VERIFIED | strategy_name field at line 46. Header link at lines 2315-2320. Cross-link with `encodeURIComponent` at lines 2668-2675. |
| `pyproject.toml` | ty.environment.root extended to include "tests" | VERIFIED | Required for `uv run ty check` to resolve `from conftest import seed_trades`. Confirmed by 04-01-SUMMARY deviation #2. |

### Key Link Verification

| From | To | Via | Status | Details |
|------|----|-----|--------|---------|
| GET /api/strategy-analytics | Trade.strategy_name (Phase 03 D-01) | `Trade.strategy_name == strategy` filter | WIRED | api.py:438. Index exists per Phase 03. |
| GET /api/strategy-analytics | Phase 03 D-16 composite filter | `or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))` | WIRED (but dead logic) | Filter present at api.py:438-441. **WR-01 in 04-REVIEW**: simplifies to always-True given the outer `strategy_name == strategy` clause. Real legacy exclusion happens via the `strategy_name == strategy` filter alone. Not blocking, but misleading dead code. |
| GET /api/strategies-summary | load_strategies() YAML loader | `for s in yaml_strategies` merge loop | WIRED | api.py:567-582. YAML strategies inserted first (in YAML order), DB-only orphans appended. |
| TradeResponse | Trade.strategy_name | `strategy_name=t.strategy_name` constructor | WIRED | api.py:625. |
| analytics/page.tsx | GET /api/strategies-summary | `fetch("/api/strategies-summary")` | WIRED | page.tsx:162. |
| analytics/page.tsx | GET /api/strategy-analytics?strategy=<name> | `fetch(...?strategy=${encodeURIComponent(selected)})` | WIRED | page.tsx:164-166. |
| analytics/page.tsx | checkAuth() | `import { checkAuth } from "../actions"` + `checkAuth().then(...)` | WIRED | page.tsx:13, :132-137. |
| dashboard/app/page.tsx header | /analytics route | `<a href="/analytics">` | WIRED | page.tsx:2315-2320. |
| dashboard/app/page.tsx trades table | /analytics?strategy=<name> | conditional `<a href={\`/analytics?strategy=${encodeURIComponent(t.strategy_name)}\`}>` | WIRED | page.tsx:2668-2675. |

### Data-Flow Trace (Level 4) — `pnl_curve` chart

This is the failure surface that produces gap #1. Tracing upstream from the chart:

| Layer | Component | Data Source | Real Data? | Status |
|-------|-----------|-------------|------------|--------|
| 1. Chart render | `<LineChart data={detail?.pnl_curve ?? []}>` (page.tsx:275) | `detail.pnl_curve` from API response | Depends on layer 2 | wired correctly |
| 2. API serialize | `pnl_curve` field of `StrategyAnalyticsResponse` (api.py:514) | List built from `settled_rows` filtered by `Trade.status IN settled_win/loss` AND ordered by `Trade.settled_at`, with explicit `if t.settled_at is None: continue` (api.py:476-501) | Only rows with non-NULL `settled_at` flow through | Filter is correct given the data assumption |
| 3. DB query | SQLAlchemy ORM read on `Trade` table | `Trade.settled_at` column populated by writer | **NO** | DISCONNECTED |
| 4. DB writer | `src/predictions/scanner.py:check_settlements` (lines 297-323) and `:on_lifecycle` (lines 327-372) | Should set `trade.settled_at = datetime.now(timezone.utc)` on settlement | **NO writer found** — `grep -rn 'settled_at\s*=' src/` returns only model column declaration | DISCONNECTED |

**Conclusion:** The chart pipeline is fully wired in code but the upstream data is never produced. `pnl_curve` will be empty in production for every strategy. Tests pass because `tests/test_strategy_analytics.py:_make_row` synthesizes `settled_at` (lines 33-51), masking the gap.

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Backend test suite passes | `uv run pytest tests/` | `86 passed, 1 skipped` | PASS |
| New analytics tests pass | `uv run pytest tests/test_strategy_analytics.py -v` | `7 passed in 0.45s` | PASS |
| Dashboard build clean | `cd dashboard && pnpm build` | exits 0; `/analytics` prerendered as static | PASS |
| `/api/strategy-analytics` requires auth | `client.get('/api/strategy-analytics?strategy=foo')` | 401 | PASS |
| `/api/strategy-analytics` returns 200 with Bearer | `client.get(..., Authorization: Bearer test-token)` | 200 | PASS |
| `/api/strategies-summary` requires auth | `client.get('/api/strategies-summary')` | 401 | PASS |
| `/api/strategies-summary` returns 200 with Bearer | `client.get(..., Authorization: Bearer test-token)` | 200; loads strategies.yaml | PASS |

### Requirements Coverage

| Requirement | Source Plan | Description | Status | Evidence |
|-------------|------------|-------------|--------|----------|
| DASH-03 | 04-00, 04-01, 04-02, 04-03 | Per-strategy dashboard page: selector + 5 stat cards + cumulative P&L line chart + trade log; behind checkAuth | **PARTIALLY SATISFIED** | Selector + stat cards + trade log + auth gate VERIFIED. Cumulative P&L chart code wired but **non-functional in production** due to scanner not writing `settled_at`. Note also: REQUIREMENTS.md spec says `x = placed_at`; phase planning chose `x = settled_at` (D-09); the deviation compounds with the writer gap. |
| DASH-04 | 04-02 | Page auto-refreshes every 5 minutes | SATISFIED (code) / NEEDS HUMAN (runtime) | `setInterval(fetchAll, 5 * 60 * 1000)` at page.tsx:192. Runtime "new data appears" verification requires browser session. |

No orphaned requirement IDs detected — REQUIREMENTS.md maps DASH-03 and DASH-04 to Phase 4 only, and both are claimed in PLAN frontmatter.

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| src/predictions/api.py | 488-491 | Comment "Pitfall 5: skip rows where settled_at is NULL" combined with silent `continue` | Blocker (root cause of gap #1) | The guard is correct given the contract, but no log/metric/error fires when production data is silently dropped. The chart goes empty without any signal in scanner.log or API response. |
| src/predictions/api.py | 438-441, 537-540 | "Composite filter" `or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))` is dead logic given the outer clauses | Warning (WR-01 in 04-REVIEW.md) | Misleading code that will rot under refactor. Comments claim filtering legacy rows; real filtering happens via outer `strategy_name == strategy` / `strategy_name.isnot(None)` clauses. Recommendation: delete the dead clause and update comment. |
| src/predictions/api.py | 446 | `open_trades` only counts `status == "dry_run"` while `total_trades` counts every row | Warning (WR-02 in 04-REVIEW.md) | `total != wins + losses + open + other` once any non-dry-run strategy attribution lands. Currently works because Phase 03 D-13 hardcodes dry_run, but a brittle invariant. |
| src/predictions/api.py | 542-553 | `/api/strategies-summary` GROUP BY has no ORDER BY for orphan strategies | Warning (WR-03) | Non-deterministic orphan ordering across SQLite restarts. Test flake risk + UI jitter. |
| dashboard/app/analytics/page.tsx | 142-146 | URL `?strategy=` read once on mount, no `popstate` listener | Warning (WR-04) | Browser back/forward updates URL but not state — page becomes stale. |
| dashboard/app/analytics/page.tsx | 186-188 | Empty `catch { }` on 5-min polling fetch | Info (IN-01) | All transport / parse errors swallowed silently; no signal of staleness in the header. |
| dashboard/app/analytics/page.tsx | 294 | `payload[0].payload as PnlPoint` type assertion without runtime guard | Info (IN-02) | recharts payload-shape rot would silently render empty fields. |
| dashboard/app/analytics/page.tsx | 335-343 | Empty trades table renders `&nbsp;` cell, not "No trades yet" | Info (IN-03) | Per D-11, intentional "clean zeros" — but indistinguishable from a broken page UX-wise. |
| tests/conftest.py | 79-81 | `seed_trades` builds its own sessionmaker rather than using monkeypatched `predictions.db.SessionLocal` | Info (IN-05) | Today both point at the same engine; future config drift could diverge seed path from production path. |

### Human Verification Required

See `human_verification:` block in frontmatter. Four runtime checks needed:
1. Real-DB chart population (will fail until CR-01 is fixed)
2. Browser back/forward state sync (WR-04)
3. 5-minute auto-refresh runtime behavior
4. Unauthenticated `/analytics` redirect timing

### Gaps Summary

**Two gaps block goal achievement:**

1. **CR-01 / Gap #1 — Cumulative P&L chart is empty in production.** The marquee feature of Success Criterion 1 fails the moment real settled trades hit the dashboard. Root cause is in `src/predictions/scanner.py` (pre-existing settlement code that never writes `settled_at`), but Phase 04 is the consumer that exposes it. The endpoint code is correct given the data assumption; the writer is missing. Tests synthesize `settled_at` and mask the bug — there is no integration test that drives a Trade through the real settlement path.

   **The fix is small** (4 lines: 2 writers + 1 import + 1 backfill SQL) but requires touching scanner.py and adding an integration test. An alternative is to switch the chart's x-axis to `placed_at`, which matches REQUIREMENTS.md DASH-03 verbatim and avoids the writer gap entirely. **The operator should pick the path** before the next plan closure.

2. **Gap #2 — Zero-trade and "settled-but-empty" states are indistinguishable.** A consequence of gap #1: the page cannot communicate to users whether a strategy has truly zero trades or has settled trades that the system silently dropped. Closing gap #1 closes this gap automatically.

**Other notable findings (4 warnings + 5 info, all from 04-REVIEW.md, all non-blocking):**
- WR-01 dead `or_` filter logic in both endpoints
- WR-02 `open_trades` definition will not reconcile with `total_trades` once non-dry-run strategy attribution lands
- WR-03 non-deterministic orphan ordering in `/api/strategies-summary`
- WR-04 no `popstate` listener on analytics page
- IN-01..IN-05 minor code-quality / UX scattering

These can be addressed in a closure plan or scheduled as follow-ups; they do not block phase exit on their own.

---

_Verified: 2026-05-07T08:27:50Z_
_Verifier: Claude (gsd-verifier)_
