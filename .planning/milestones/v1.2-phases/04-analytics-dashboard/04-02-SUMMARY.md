---
phase: 04-analytics-dashboard
plan: 02
subsystem: dashboard/analytics
tags: [nextjs, react, recharts, dashboard, frontend]
requires: [04-01]
provides:
  - "/analytics route (client component with auth gate, sidebar, detail panel)"
  - "recharts integration (first use of recharts in the codebase)"
affects:
  - "dashboard/app/analytics/page.tsx (new file)"
tech-stack:
  added:
    - "recharts ^3.8.1 (already pinned in package.json — no install needed)"
  patterns:
    - "Client-component standalone route mirroring backtest/page.tsx structure (D-01)"
    - "URL-param state via window.location.search inside useEffect (Pitfall 4 — avoids Next.js 16 useSearchParams Suspense)"
    - "5-minute polling via setInterval registered after immediate fetch, cleared on dep change"
    - "Empty-data render: pnl_curve fallback to [], single &nbsp; row in trade log (D-11 clean zeros)"
key-files:
  created:
    - "dashboard/app/analytics/page.tsx (396 lines, 13196 bytes)"
  modified: []
decisions:
  - "StatCard re-declared locally (not extracted to shared component) — RESEARCH Open Question 1 resolved per 04-PATTERNS.md"
  - "URL param read via window.location.search inside useEffect — RESEARCH Pitfall 4, avoids the Next.js 16 useSearchParams Suspense build error"
  - "fmtCentsPlain function and _retainExport stub from plan's Task 1 omitted: trade log table uses fmtCents (signed) and shows yes_price as cents — no $-prefixed cost column needed. Plan explicitly allowed this cleaner approach (Change E)."
  - "ResponsiveContainer height fixed at 280px (Pitfall 6) — never percent height inside a flex/grid parent"
  - "recharts Tooltip uses custom JSX content (React-escaped) — no dangerouslySetInnerHTML"
metrics:
  duration_minutes: ~12
  completed: 2026-05-07
  task_count: 2
  file_count: 1
---

# Phase 04 Plan 02: Analytics Dashboard UI Summary

Built `/analytics` client route at `dashboard/app/analytics/page.tsx` —
auth-gated sidebar+detail layout consuming Wave 1's `/api/strategies-summary`
and `/api/strategy-analytics` endpoints, with recharts cumulative P&L chart,
trade log table, and 5-minute auto-refresh.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Scaffold analytics page — auth + sidebar + stat cards + URL param state | `62c5ea8` | dashboard/app/analytics/page.tsx (new) |
| 2 | Add recharts P&L chart, trade log table, and 5-minute polling | `29798c3` | dashboard/app/analytics/page.tsx |

## Key Decisions

### Open Question 1 (RESEARCH.md): StatCard re-declared locally
The plan's PATTERNS.md analog file declared `StatCard` and `fmtCents` locally
inside `dashboard/app/analytics/page.tsx` rather than importing the existing
`SummaryCard` from `dashboard/app/backtest/page.tsx`. This keeps both pages
independent — extracting later is cheap; coupling now is expensive. Choice
followed verbatim.

### Pitfall 4 (RESEARCH.md): window.location.search instead of useSearchParams
Next.js 16's `useSearchParams` requires a Suspense boundary; without one, the
production build fails with "useSearchParams() should be wrapped in a
Suspense boundary". The page reads `?strategy=<name>` once on mount inside a
`useEffect` via `new URLSearchParams(window.location.search)` — works the
same, no Suspense gymnastics. Verified against `next build` (clean).

### fmtCentsPlain not declared
Plan Task 1 included an `fmtCentsPlain` helper plus `_retainExport` stub to
silence lint between Task 1 and Task 2. Task 2 ultimately did not need it
(P&L column uses signed `fmtCents`, price column uses raw cents-with-c
suffix). Plan Change E explicitly allowed omitting both — taken. Lint is
clean without the stub.

### Pitfall 6 (RESEARCH.md): ResponsiveContainer height=280 (pixels, not %)
recharts' `ResponsiveContainer` collapses to 0 height when given `height="100%"`
inside a parent without an explicit pixel height. Used `height={280}` and a
fixed `top: 5, right: 20, left: 10, bottom: 5` margin per the plan.

## Recharts Components Used

- `ResponsiveContainer` (width="100%", height={280})
- `LineChart` (with `data={detail?.pnl_curve ?? []}` — never undefined)
- `CartesianGrid`, `XAxis`, `YAxis`
- `Tooltip` with custom React-children content (XSS-safe — JSX auto-escapes)
- `Line` (type="monotone", stroke="#d97706", dot={false})

## Stat Cards (5)

Total Trades · Wins · Losses · Win Rate · Realized P&L

## Verification

- `cd dashboard && ./node_modules/.bin/oxlint app/analytics/page.tsx` — 0 warnings, 0 errors
- `cd dashboard && ./node_modules/.bin/oxfmt --check app/analytics/page.tsx` — clean
- `cd dashboard && ./node_modules/.bin/next build` — exits 0; `/analytics` route prerendered as static
- `uv run pytest tests/ -q` — 86 passed, 1 skipped (backend untouched in this plan)
- `git diff --name-only` for the plan: only `dashboard/app/analytics/page.tsx` (no monolith touch)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Comment containing the literal string "useSearchParams" tripped acceptance grep**

- **Found during:** Task 1 verification
- **Issue:** The plan's literal Task 1 source included a comment `// window.location.search inside useEffect rather than useSearchParams to ...`. Acceptance criterion `grep -nE 'useSearchParams' returns 0 matches` flagged the comment as a match.
- **Fix:** Rephrased the comment to describe the rationale without naming the API ("avoids the Next.js 16 Suspense boundary build error associated with the dynamic search-params API"). Code semantics unchanged.
- **Files modified:** `dashboard/app/analytics/page.tsx` (comment only)
- **Commit:** included in `62c5ea8`

**2. [Rule 3 - Blocking] Worktree had no node_modules**

- **Found during:** Task 1 verification (lint step)
- **Issue:** Fresh worktree, `dashboard/node_modules` did not exist; oxlint/oxfmt/next binaries unavailable.
- **Fix:** Ran `pnpm install --prefer-offline` in `dashboard/`. Installed in 1.4s. Did NOT modify `dashboard/package.json` or `dashboard/pnpm-lock.yaml`.
- **Commit:** N/A (install only; nothing committed)

### Auth Gates

None. The `/analytics` route reuses the existing `checkAuth` cookie gate that's
already wired into `dashboard/app/actions.ts` and `dashboard/app/api/[...path]/route.ts`.

### Authentication / Authorization

The page redirects unauthenticated visitors to `/`, then renders a black
`min-h-screen` placeholder while auth resolves. No analytics fetches fire
until `authed === true`. All `/api/*` requests are routed through the Next.js
proxy which injects the Bearer token server-side — the client never touches
the token.

## Threat Flags

None. The page is a read-only authenticated client view; the `?strategy=`
URL param is read into React state and used only as a fetch query argument
(`encodeURIComponent`), never as raw HTML. The recharts `Tooltip` uses React
children (auto-escaped) for the dynamic ticker / time / P&L fields.

## Self-Check: PASSED

- `dashboard/app/analytics/page.tsx` exists (396 lines, 13196 bytes) — FOUND
- Commit `62c5ea8` (Task 1) — FOUND
- Commit `29798c3` (Task 2) — FOUND
- `cd dashboard && ./node_modules/.bin/next build` — clean (`/analytics` prerendered static)
- `uv run pytest tests/` — 86 passed, 1 skipped

## Known Stubs

None. The page is fully wired: sidebar → `/api/strategies-summary`, detail →
`/api/strategy-analytics?strategy=<name>`, both refetched every 5 minutes.
Empty-data states (zero-trade strategies) render clean zeros + empty axes +
empty table body per D-11, which is intentional (not a stub).
