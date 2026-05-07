---
status: partial
phase: 04-analytics-dashboard
source: [04-VERIFICATION.md]
started: 2026-05-07T09:42:00Z
updated: 2026-05-07T09:42:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Real-DB chart population (Success Criterion 1)
expected: Cumulative P&L chart renders with at least one point per settled trade; chart and stat-card realized P&L reconcile (final running sum on chart == `realized_pnl_cents` stat card).

How: open `/analytics` in a browser with a populated DB (real settled trades, not test fixtures); select a strategy known to have settled wins/losses.

result: [pending]

### 2. Browser back/forward state sync (WR-04)
expected: After clicking a strategy in the sidebar (URL changes to `/analytics?strategy=<name>`), pressing the browser back button returns to the previously selected strategy.

How: click a strategy → observe URL → press browser back.

result: [pending]

Note: this is a known open advisory (WR-04). The analytics page does not register a `popstate` listener — back/forward may not sync the displayed strategy with the URL. Confirm whether the current behavior is acceptable or whether a follow-up fix is needed.

### 3. 5-minute auto-refresh (Success Criterion 3)
expected: `lastUpdated` timestamp ticks forward at the 5-minute interval; if a new dry-run trade is seeded between fetches, it appears in the trade log on the next refresh without manual reload.

How: open `/analytics`, leave the tab open for ≥5 minutes (or temporarily lower the interval), insert a new dry-run trade for the selected strategy in another terminal, watch for it to appear.

result: [pending]

### 4. Unauthenticated redirect (auth gate)
expected: Visiting `/analytics` without a valid auth cookie (incognito or after logout) redirects to `/` immediately; no analytics data is fetched (no `/api/strategies-summary` or `/api/strategy-analytics` requests fire pre-redirect).

How: open `/analytics` in incognito → confirm redirect → check Network tab for any analytics requests.

result: [pending]

## Summary

total: 4
passed: 0
issues: 0
pending: 4
skipped: 0
blocked: 0

## Gaps
