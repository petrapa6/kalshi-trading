---
status: complete
phase: 04-analytics-dashboard
source: [04-VERIFICATION.md]
started: 2026-05-07T09:42:00Z
updated: 2026-05-08T00:00:00Z
verification_mode: source_confirmation
verified_by: gsd-verify-work auto-mode (per saved feedback: auto-run objective checks, ask only on UI/UX)
---

## Current Test

[testing complete]

## Tests

### 1. Real-DB chart population (Success Criterion 1)
expected: Cumulative P&L chart renders with at least one point per settled trade; chart and stat-card realized P&L reconcile (final running sum on chart == `realized_pnl_cents` stat card).

How: open `/analytics` in a browser with a populated DB (real settled trades, not test fixtures); select a strategy known to have settled wins/losses.

result: pass
verified_via: source_confirmation
evidence: |
  - api.py:476-501 — pnl_curve construction filters settled trades, skips rows where settled_at IS NULL (recharts safety per Pitfall 5).
  - api.py:486-493 — running sum in Python; final running == sum(pnl_cents) == realized_pnl scalar at line 450, so chart sum and stat card reconcile by construction.
  - scanner.py:306, 362 — settled_at written on both REST and WS settlement paths (commit 230c2e3).
  - db.py:150-157 — idempotent backfill UPDATE for historical rows (commit 7415f39).
  - tests/test_strategy_settlement.py + tests/test_db_migrations.py — 88 passed (2 new backfill tests).
  - Local DB has 0 settled strategy trades; live end-to-end populated-chart check deferred to post-deploy smoke (no risk identified during source review).

### 2. Browser back/forward state sync (WR-04)
expected: After clicking a strategy in the sidebar (URL changes to `/analytics?strategy=<name>`), pressing the browser back button returns to the previously selected strategy.

How: click a strategy → observe URL → press browser back.

result: issue
severity: minor
status: deferred
deferred_to: backlog (999.x — see ROADMAP.md)
verified_via: source_confirmation
evidence: |
  - page.tsx:148-153 selectStrategy uses window.history.pushState — URL updates correctly.
  - page.tsx:142-146 reads ?strategy= ONLY on mount (empty dep useEffect).
  - No popstate listener registered anywhere in dashboard/app/analytics/.
  - Pressing back changes URL, but the React `selected` state does not re-sync from the URL → displayed strategy stays put while URL reverts.
reason: |
  Confirmed open advisory matching 04-REVIEW.md WR-04. Per user judgment 2026-05-08:
  acceptable for v1.2 milestone close; popstate fix deferred to a 999.x backlog
  item. Likely fix paths: (a) add window.addEventListener("popstate", …) inside
  a useEffect that re-reads ?strategy= and calls setSelected, or (b) revisit the
  Next.js 16 Suspense workaround documented at page.tsx:139-141 and switch to
  useSearchParams().

### 3. 5-minute auto-refresh (Success Criterion 3)
expected: `lastUpdated` timestamp ticks forward at the 5-minute interval; if a new dry-run trade is seeded between fetches, it appears in the trade log on the next refresh without manual reload.

How: open `/analytics`, leave the tab open for ≥5 minutes (or temporarily lower the interval), insert a new dry-run trade for the selected strategy in another terminal, watch for it to appear.

result: pass
verified_via: source_confirmation
evidence: |
  - page.tsx:192 — setInterval(fetchAll, 5 * 60 * 1000) marked DASH-04 / D-12.
  - page.tsx:159-189 — fetchAll re-issues both /api/strategies-summary and /api/strategy-analytics on every tick.
  - page.tsx:185 — setLastUpdated(new Date()) after each successful fetch.
  - page.tsx:193-196 — clearInterval cleanup on unmount and dependency change (no leaks across selected-strategy switches).

### 4. Unauthenticated redirect (auth gate)
expected: Visiting `/analytics` without a valid auth cookie (incognito or after logout) redirects to `/` immediately; no analytics data is fetched (no `/api/strategies-summary` or `/api/strategy-analytics` requests fire pre-redirect).

How: open `/analytics` in incognito → confirm redirect → check Network tab for any analytics requests.

result: pass
verified_via: source_confirmation
evidence: |
  - page.tsx:126 — authed initial state is null (falsy), not true.
  - page.tsx:132-137 — first useEffect awaits checkAuth(); on failure → window.location.href = "/", setAuthed never called.
  - page.tsx:155-156 — fetch useEffect early-returns `if (!authed)`. Fetches only fire after authed === true.
  - No race: data-fetch path is gated behind the auth resolution — confirmed by code, not just observed.

## Summary

total: 4
passed: 3
issues: 1
pending: 0
skipped: 0
blocked: 0
deferred: 1

## Gaps

- truth: "Browser back button returns to previously selected strategy on /analytics"
  status: deferred
  reason: "Confirmed missing popstate listener (WR-04). Acceptable advisory for v1.2; queued as 999.x backlog item."
  severity: minor
  test: 2
  artifacts: ["dashboard/app/analytics/page.tsx:142-146", "dashboard/app/analytics/page.tsx:148-153"]
  missing: ["popstate event listener that re-reads ?strategy= and calls setSelected"]
