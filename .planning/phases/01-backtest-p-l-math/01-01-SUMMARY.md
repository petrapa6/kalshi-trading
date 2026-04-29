---
phase: 01-backtest-p-l-math
plan: 01
subsystem: ui
tags: [backtest, dashboard, contract-math, integer-cents, kalshi, typescript, react]

# Dependency graph
requires:
  - phase: v1.1-Local-JSON-Backtest
    provides: dashboard backtest page with avg_win_yield approximation, formatEuro helper, SummaryCard/TradeRow components, season JSON loading
provides:
  - contract-based P&L math in dashboard backtest engine (BT-06)
  - integer-cents money type discipline through BacktestParams/Trade/Summary
  - sidebar contract_price slider replacing avg_win_yield input (50–99¢, default 97)
  - ROADMAP Phase 1 success criterion #2 aligned with locked D-06 wording
affects: [phase-2-strategy-engine-core, phase-3-scanner-integration, phase-4-analytics-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Integer-cents at function entry, EUR only at JSX render leaf (formatEuro(value / 100))"
    - "Math.floor truncation for both bet_amount_cents and contracts (matches scanner.py:324, :134)"
    - "Sign stripping at render: pnlSign + formatEuro(Math.abs(value)/100), never negative cents to formatEuro"

key-files:
  created: []
  modified:
    - dashboard/app/backtest/backtest.ts
    - dashboard/app/backtest/page.tsx
    - .planning/ROADMAP.md

key-decisions:
  - "Adopted integer cents throughout the backtest engine (D-08..D-11) for consistency with src/predictions production code, even though dashboard is below the Kalshi boundary."
  - "Removed bet_amount field from BacktestTrade per D-13; cost_cents derived at render via contracts × contract_price_cents."
  - "Deleted simulateMatch and DEFAULT_WIN_YIELD per D-16 (verified zero callers outside the file)."
  - "Slider over number input for contract_price_cents to match min_minute / min_lead visual rhythm (RESEARCH § Discretion 2)."

patterns-established:
  - "Integer-cents arithmetic in client engines: Math.floor at the EUR→cents boundary, every internal multiplication/division stays integer."
  - "Render-time derivation of secondary money fields (cost_cents = contracts × price_cents) to keep the trade schema lean."
  - "Roadmap-coupling commit: code change + roadmap success-criterion rewrite ship in the same logical phase to prevent doc drift."

requirements-completed: [BT-06]

# Metrics
duration: ~10min
completed: 2026-04-29
---

# Phase 1 Plan 01: Backtest P&L Math Summary

**Replaced the avg_win_yield approximation in `dashboard/app/backtest/` with floor-truncation contract math (`contracts = floor(stake_cents / price_cents)`, win = `contracts × (100 − price_cents)`, loss = `−contracts × price_cents`), propagating integer-cents through the trade and summary schemas, swapping the sidebar input to a 50–99¢ slider, and aligning ROADMAP success criterion #2 with locked decision D-06.**

## Performance

- **Duration:** ~10 min
- **Started:** 2026-04-29T21:19:00Z
- **Completed:** 2026-04-29T21:25:51Z
- **Tasks:** 3
- **Files modified:** 3

## Accomplishments

- `runBacktest` now uses the canonical Kalshi contract-math kernel (D-04 + D-08 + D-17): floor-truncation on both stake and contract count, signed `pnl_cents`, zero-contract rows when capital can't afford one contract.
- `BacktestParams` / `BacktestTrade` / `BacktestSummary` schemas refactored to integer cents per D-09/D-10/D-11; dropped `bet_amount`, renamed `pnl`/`capital_after`/`initial_capital`/`final_capital` to their `_cents` variants, added `contracts` and `contract_price_cents` to `BacktestTrade`.
- Sidebar swap: avg_win_yield number input → "Contract price (cents)" slider (50–99, step 1, default 97) with helper text rendering yield-per-win in cents and EUR per D-02/D-03.
- TradeRow third line now renders the D-14 verbatim form: `"{N} contracts @ {P}¢ · €{cost} cost · {±}€{|pnl|} · capital €{cap}"`. Sign-stripping pattern preserved (Pitfall 2): negative cents never reach `formatEuro`.
- Dead exports removed: `simulateMatch` and `DEFAULT_WIN_YIELD` deleted (D-16) — both had verified zero callers.
- ROADMAP Phase 1 success criterion #2 rewritten verbatim per D-06; the misleading reference to non-existent `min_yes_price` / `max_yes_price` sliders is gone (those belong to Phase 2 / BT-07 per D-07).

## Task Commits

Each task was committed atomically:

1. **Task 1: Rewrite backtest.ts engine to contract-based integer-cents math** — `a0281bc` (feat)
2. **Task 2: Rewire page.tsx — sidebar slider swap + TradeRow rewrite + SummaryCard cents reads** — `eb26e23` (feat)
3. **Task 3: Rewrite ROADMAP Phase 1 success criterion #2 per D-06** — `3494f7e` (docs)

## Files Created/Modified

- `dashboard/app/backtest/backtest.ts` — engine rewrite: types renamed/extended, runBacktest body replaced with the canonical contract-math kernel, dead exports removed.
- `dashboard/app/backtest/page.tsx` — import drops `DEFAULT_WIN_YIELD`, state hook seeds `contractPriceCents = 97`, useMemo passes `contract_price_cents`, sidebar slider replaces number input, TradeRow third line rewritten, SummaryCard "Final capital" reads `final_capital_cents / 100`.
- `.planning/ROADMAP.md` — single-line replacement of Phase 1 success criterion #2 to D-06 verbatim wording.

## Decisions Made

None beyond the locked D-01..D-17 set; this plan was a faithful execution of CONTEXT.md.

**Worked-example hand-verification (BT-06 success criterion #1):** With `initial_capital=1000`, `bet_fraction=0.02`, `contract_price_cents=97`, the first winning trade computes `bet_amount_cents=2000`, `contracts=20`, `pnl_cents=+60`, `capital_after_cents=100060`, rendering as `"20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"` — matches D-14 verbatim. (Verified by Python recomputation of the kernel; full browser verification deferred to `/gsd-verify-work`.)

**D-17 zero-contract case:** With `initial_capital=1`, `bet_fraction=0.5`, `contract_price_cents=97`, `bet_amount_cents = floor(100 × 0.5) = 50`, `contracts = floor(50 / 97) = 0`, `pnl_cents = 0`, `capital_after_cents = 100` (unchanged). Verified by Python.

## Deviations from Plan

None - plan executed exactly as written. All 17 locked decisions (D-01..D-17) honored verbatim.

One observation that is **not** a deviation: the plan's `<verify>` block included a static grep `grep -F 'a contract_price input (default 97, range 50–99 cents)'` (without backticks around `contract_price`). The committed ROADMAP line uses the D-06 verbatim wording with backticks (`` `contract_price` ``), so the plan's grep would not match — but the file content is correct per D-06. Confirmed via Python in-string check that the full D-06 wording is present byte-for-byte.

Additionally, oxfmt 0.7.0 (the formatter the pre-commit hook runs) reformatted both modified files to 2-space indent despite `dashboard/oxfmt.json` declaring `"indentWidth": 4`. The plan, CLAUDE.md, and PROJECT.md all reference 4-space indent; the actual oxfmt 0.7.0 output (and the existing repo state for these two files) is 2-space. The committed files pass `pnpm fmt:check` cleanly — neither `app/backtest/backtest.ts` nor `app/backtest/page.tsx` is in the failing list. This is a pre-existing config/formatter discrepancy outside this plan's scope.

## Issues Encountered

None requiring problem-solving. The expected build break after Task 1 (intentional per the plan) was resolved by Task 2's page.tsx rewire, exactly as designed.

## Verification Results

End-of-plan gate (`cd dashboard && pnpm fmt:check && pnpm lint && pnpm build`):

- **fmt:check:** 3 pre-existing failures (`app/actions.ts`, `app/api/[...path]/route.ts`, `sst-env.d.ts`) — these were already failing before this plan per PROJECT.md note; neither modified file appears in the failing list.
- **lint:** 4 warnings, 0 errors — all 4 warnings are pre-existing in `app/page.tsx` (unrelated to this plan).
- **build:** ✅ succeeds. `/backtest` route generates as static. No new compilation errors.

Static greps from `<verification>`:

- `! grep -E 'simulateMatch|DEFAULT_WIN_YIELD|avg_win_yield' dashboard/app/backtest/backtest.ts` ✅ (exit 1, no match)
- `! grep -E 'avgWinYield|avg_win_yield|DEFAULT_WIN_YIELD' dashboard/app/backtest/page.tsx` ✅ (exit 1, no match)
- D-06 verbatim wording present in `.planning/ROADMAP.md` ✅ (verified via Python string-in-content)
- `grep -F 'contracts * (100 - contract_price_cents)' dashboard/app/backtest/backtest.ts` ✅
- `grep -F 'Math.floor(bet_amount_cents / contract_price_cents)' dashboard/app/backtest/backtest.ts` ✅

Manual seams (worked example, D-17, capital conservation, no-negative-capital, sidebar visual regression) deferred to `/gsd-verify-work` per the plan's `<manual_verification>` block. The kernel arithmetic was hand-verified mathematically (see "Decisions Made" above).

## User Setup Required

None - no external service configuration required. Pure client-side change.

## Next Phase Readiness

Phase 2 (Strategy Engine Core) can proceed. The BacktestParams shape now exposes `contract_price_cents` as the price-paid input, leaving room for Phase 2 / BT-07 to add `min_yes_price` / `max_yes_price` filter-bound sliders without conflict (per D-07 the rejection of yes_price renaming for now is intentional).

## Self-Check: PASSED

All claims in this summary verified:

- Files modified: `dashboard/app/backtest/backtest.ts` ✅, `dashboard/app/backtest/page.tsx` ✅, `.planning/ROADMAP.md` ✅
- Commits exist: `a0281bc` ✅, `eb26e23` ✅, `3494f7e` ✅
- Static greps from `<verification>` all pass.
- Build green; pre-existing fmt/lint warnings outside this plan's scope.

---
*Phase: 01-backtest-p-l-math*
*Completed: 2026-04-29*
