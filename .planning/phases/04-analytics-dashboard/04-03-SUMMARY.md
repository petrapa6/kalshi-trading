---
phase: 04-analytics-dashboard
plan: 03
subsystem: dashboard/main-page
tags: [dashboard, cross-links, header-nav, frontend]
requires: [04-01, 04-02]
provides:
  - "Header link to /analytics on the main dashboard (D-03)"
  - "Per-row cross-link from trades-table strategy_name to /analytics?strategy=<name> (D-02)"
  - "Trade TS interface in sync with Wave 1 TradeResponse Pydantic model"
affects:
  - "dashboard/app/page.tsx (15 lines added; 0 removed; 0 refactor)"
tech-stack:
  added: []
  patterns:
    - "<a href> for cross-page nav (consistent with existing /backtest link; no next/link import in page.tsx)"
    - "Conditional JSX render `{t.strategy_name && (...)}` for legacy NULL safety"
    - "encodeURIComponent on URL param + JSX child auto-escape on visible text (XSS defense-in-depth)"
key-files:
  created: []
  modified:
    - "dashboard/app/page.tsx (+15 lines: 1 TS field, 1 header link, 1 conditional cross-link block)"
decisions:
  - "Used <a> not next/link — page.tsx does not import next/link anywhere; introducing it for two links would add a dependency the file otherwise avoids"
  - "Added margin-left (ml-2) on the new Analytics link only — preserves the existing /backtest link untouched and inherits the header's rounded amber-hover style verbatim"
  - "Conditional render `t.strategy_name && (...)` is the entire legacy-row defense — no `else` branch, no fallback element"
metrics:
  duration_minutes: ~7
  completed: 2026-05-07
  task_count: 2
  file_count: 1
---

# Phase 04 Plan 03: Wire Analytics Cross-Links Into Main Dashboard Summary

Three small additions to `dashboard/app/page.tsx` (the 98 KB monolith) wire
the Wave-2 `/analytics` page into the main dashboard: an Analytics header link
next to Strategy Backtest (D-03), a `strategy_name?: string | null` field on
the `Trade` TS interface (mirrors Wave 1 `TradeResponse` Pydantic model), and
a conditional per-row cross-link from any `Trade.strategy_name` in the trades
table to `/analytics?strategy=<name>` (D-02). Net +15 lines, zero new imports,
zero refactor — well below the CONCERNS.md "do not grow" soft cap.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Add Analytics header link + extend Trade TS interface | `1740e46` | dashboard/app/page.tsx |
| 2 | Wrap strategy_name in trades-table cell as cross-link to /analytics | `703f917` | dashboard/app/page.tsx |

## Strategy-name surfacing enumeration (D-02 planner action)

Before Task 2, ran:

```bash
grep -n 'strategy_name\|strategy:\|t\.strategy' dashboard/app/page.tsx
```

Result BEFORE Task 1: 0 matches. The trades table is the SOLE call site for
strategy data on the main dashboard. The "What If? Strategy Comparison" tab
referenced in 04-RESEARCH.md was already deleted in Phase 03 D-21 — no
orphaned references remain. No additional cross-link locations were
discovered; the plan's enumeration assumption holds verbatim.

After Task 1, the only match is the new TS field declaration. After Task 2,
matches are exactly:

- line 46: `  strategy_name?: string | null;`
- the conditional `{t.strategy_name && (...)}` block in the trades table
- the `encodeURIComponent(t.strategy_name)` URL param interpolation
- the `{t.strategy_name}` JSX child rendering the link text

## Line-count delta

`dashboard/app/page.tsx`: **+15 lines**, 0 removed.

- Task 1: +7 (1 TS field + 6 lines for the Analytics `<a>` block including the surrounding whitespace).
- Task 2: +8 (1 conditional guard + 5-line `<a>` block + closing parens).

Pre-task baseline: 2861 lines. Post-plan: 2876 lines.

## Verification

- `cd dashboard && ./node_modules/.bin/oxlint app/page.tsx` — 0 errors, 4 warnings (all PRE-EXISTING; not introduced by this plan: `zeroX`/`zeroY` declared-but-unused in the Bell Curve helper, `balanceHistory` declared-but-unused since Phase 03)
- `cd dashboard && ./node_modules/.bin/oxfmt --check app/page.tsx` — clean
- `cd dashboard && pnpm build` — exits 0; `/analytics` route still prerendered as static; no SSR errors, no TS errors
- `uv run pytest tests/ -q` — 86 passed, 1 skipped (backend untouched in this plan)
- `git diff --name-only` for the plan: only `dashboard/app/page.tsx` (the
  task scope is honored verbatim — no analytics-page touch, no api.py touch,
  no test touch)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Worktree had no node_modules**

- **Found during:** Task 1 verification (oxlint/oxfmt/next binaries unavailable)
- **Issue:** Fresh worktree, `dashboard/node_modules` did not exist.
- **Fix:** Ran `pnpm install --prefer-offline` in `dashboard/`. Installed in 1.3s. Did NOT modify `dashboard/package.json` or `dashboard/pnpm-lock.yaml`.
- **Files modified:** None committed.
- **Commit:** N/A (install only).

### Acceptance Criterion Note (NOT a deviation)

The plan's acceptance criterion `pnpm lint exits 0` did not return 0 in this
environment. Investigation: `pnpm lint` invokes `oxlint` (which exits 0 with
4 pre-existing warnings, 0 errors), but a post-process wrapper in the rtk
shell tee infrastructure subsequently runs `eslint`, which fails because the
project does not use ESLint (no `.eslintrc.*`). This is an environmental
artifact — the project's actual lint tool (`oxlint`) passes cleanly. Phase
04 Plan 02's SUMMARY.md hit the same artifact and used `./node_modules/.bin/oxlint`
directly (same approach taken here). Acceptance is met against the project's
configured lint tool.

### Auth Gates

None. The header link and trades-table cross-link both target `/analytics`,
which already enforces `checkAuth` (Wave 2). Unauthenticated users on the
main dashboard cannot reach this code path because `page.tsx` itself is
auth-gated.

### Authentication / Authorization

No new auth surface introduced. The `Trade.strategy_name` field reaches the
client through the existing authenticated `/api/trades` proxy; rendering it
in the table and wrapping it in an `<a href>` does not change auth posture.

## Threat Flags

None. Threats T-04-W3-01..T-04-W3-03 from the plan's threat model are
mitigated as specified:

| Threat ID | Mitigation Verified |
|-----------|---------------------|
| T-04-W3-01 (XSS via URL) | `encodeURIComponent(t.strategy_name)` confirmed at the `${}` interpolation site |
| T-04-W3-02 (XSS via JSX child) | `{t.strategy_name}` is a JSX child — React auto-escapes; no `dangerouslySetInnerHTML` introduced (`grep -c dangerouslySetInnerHTML dashboard/app/page.tsx` = 0, unchanged) |
| T-04-W3-03 (info disclosure via header link) | `/analytics` route enforces `checkAuth` (Wave 2); the link text alone leaks no data |

## Self-Check: PASSED

- `dashboard/app/page.tsx` exists; +15 lines vs base — FOUND
- Commit `1740e46` (Task 1) — FOUND
- Commit `703f917` (Task 2) — FOUND
- `cd dashboard && pnpm build` — clean (`/analytics` prerendered static)
- `uv run pytest tests/ -q` — 86 passed, 1 skipped
- `git diff --name-only 28947dc771cd16bfea60b344fedeb2522c1d5160 HEAD` — single file: `dashboard/app/page.tsx`

## Known Stubs

None. The cross-link is fully wired; conditional render handles the only
empty-data case (legacy NULL `strategy_name`). The Analytics header link
hardcodes `/analytics` as intended (single static destination, not a stub).
