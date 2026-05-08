---
phase: 01-backtest-p-l-math
plan: 02
subsystem: ui
gap_closure: true
closes_uat_tests: [3, 6]
tags: [backtest, dashboard, ordering, tallies, ui-tri-state, integer-cents]

# Dependency graph
requires:
  - plan: 01
    provides: contract-based P&L kernel + integer-cents schema + sidebar slider
provides:
  - strict reverse-chronological trade-list display (newest-first across both day boundaries AND within-day)
  - zero-contract row exclusion from wins/losses/matches_bet_on tallies (Option A extended)
  - tri-state TradeRow rendering: green/red bet rows + muted #F28C28/30 zero-contract rows with neutral pnl text
affects: [phase-2-strategy-engine-core, phase-4-analytics-dashboard]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Display ordering by reversing chronological-walk insertion order (Array.prototype.reverse) — stable wrt within-day ordering; no separate sort key needed when source data is already chronological."
    - "Zero-contract gate: filter trades by `contracts > 0` for tally aggregation; preserve binary `result: \"win\" | \"loss\"` discriminator for future analytics."
    - "Tailwind v4 arbitrary-value with opacity modifier for one-off brand colors: `bg-[#F28C28]/30` keeps the same /30 alpha rhythm as `bg-{green,red}-900/30`."

key-files:
  created:
    - .planning/phases/01-backtest-p-l-math/01-02-SUMMARY.md
  modified:
    - dashboard/app/backtest/backtest.ts
    - dashboard/app/backtest/page.tsx
    - .planning/ROADMAP.md
    - .planning/STATE.md

key-decisions:
  - "Kept `BacktestTrade.result` binary `\"win\" | \"loss\"`; gated tally + render on `contracts === 0` instead of introducing a `\"noop\"` discriminator. Smaller diff; preserves match-outcome data for future capital-starvation analytics."
  - "Replaced `[...trades].sort(b.date.localeCompare(a.date))` with `[...trades].reverse()` — provably correct against EPL/LaLiga JSON where ESPN event-IDs map to ascending kickoff order within a date."
  - "User-specified zero-contract background `#F28C28` at /30 alpha to match the visual rhythm of `bg-green-900/30` and `bg-red-900/30`."
  - "Zero-contract pnl span uses `text-gray-300` (inherits surrounding third-line gray) instead of `text-green-400`. The previous green `+€0.00` visually overclaimed a profit on rows where no bet was placed."

patterns-established:
  - "Display reversal pattern: when the engine walks data in canonical chronological order and the UI wants the inverse, prefer `[...arr].reverse()` over `[...arr].sort(desc)` — stable wrt within-key tiebreakers without needing a secondary sort field."
  - "Tally gate pattern: when a row schema mixes 'evaluated' and 'acted on' states, gate aggregation on the act-discriminator (here, `contracts > 0`), not on the outcome discriminator (here, `result`)."
  - "Tri-state UI pattern: dispatch on the act-discriminator first (`isZero`), then on the outcome (`won`); inherit text color from parent for the noop branch to avoid visual overclaim."

requirements-completed: [BT-06]

# Metrics
duration: ~25min
completed: 2026-04-30
---

# Phase 1 Plan 02: Gap Closure Summary

**Closed two major gaps from `01-HUMAN-UAT.md` surfaced during human verification of Plan 01: a display-sort bug breaking within-day ordering (Test 3) and a design decision making zero-contract rows tri-state at both the tally and UI layers (Test 6).**

## Performance

- **Duration:** ~25 min (planner ~10 min, executor ~4 min, two human-verify rounds + refinement ~10 min)
- **Started:** 2026-04-30T07:03:20Z
- **Completed:** 2026-04-30T07:28:00Z
- **Tasks:** 3 (2 auto + 1 human-verify checkpoint)
- **Files modified:** 2 source + 2 doc

## Accomplishments

### Gap 1 closed (UAT Test 3) — Display ordering

**Root cause:** `dashboard/app/backtest/backtest.ts:198-199` sorted by `date` alone with no within-day tiebreaker. V8's stable sort preserved source-JSON order within a day, while across days flipped to descending. Result: top of an N-match-same-day group was the chronologically *first* match of that day, breaking the "topmost row = final trade" invariant.

**Fix (commit `20653ec`):** Replaced `[...trades].sort((a, b) => b.date.localeCompare(a.date))` with `[...trades].reverse()`. Since `runBacktest` walks `chronological` (ascending date, line 138) and pushes each trade in walk order, reversing yields strict newest-first INCLUDING within-day. The plan-checker verified against the actual EPL season JSON: ESPN event-IDs map to ascending kickoff order within a date (Aug 24 EPL: 704289 = 12:30, 704295 = 15:00, 704297 = 17:30 BST), confirming the reversal produces correct kickoff-order display.

**Verification evidence:** With `initial_capital=1000`, `bet_size=2%`, `contract_price=97` on EPL 24/25, the user confirmed the trade list now reads top→bottom: Aug 25 Wolves–Chelsea (€1003.60 = Final) → Aug 24 Tottenham → Aug 24 Man City → Aug 24 Aston Villa → Aug 18 Chelsea → Aug 17 Everton (€1000.60). Strictly monotone descending capital. Topmost row's `capital_after_cents` equals `final_capital_cents`.

### Gap 2 closed (UAT Test 6) — Zero-contract tri-state

**Decision (locked in `01-HUMAN-UAT.md` Test 6, Option A extended):**
- Tally side: exclude zero-contract rows from `wins`/`losses`/`matches_bet_on` so summary cards reflect actual edge captured.
- UI side: keep zero-contract rows visible; render in muted orange with no checkmark/cross icon to surface "would have bet if capital permitted" as a categorically distinct state.

**Implementation choice (justified inline):** kept `result` binary (`"win" | "loss"`); used `contracts === 0` as the single source of truth for "did we bet?" Smaller diff than introducing a `"noop"` discriminator and preserves match-outcome data for future "would-have-won rate when capital-starved" analytics.

**Tally fix (commit `20653ec`):** Introduced `placed = trades.filter((t) => t.contracts > 0)` and rebuilt `wins`/`losses`/`matches_bet_on` from `placed` instead of `trades`. `win_rate` denominator (`settled = wins + losses`) now excludes zero-contract rows. `gain_pct` unchanged (uses `final_capital_cents − initial_capital_cents`, independent of count semantics).

**UI rewrite (commit `0277022`):** Rewrote `TradeRow` in `page.tsx`. Dispatches on `isZero = trade.contracts === 0` first, then on `won = trade.result === "win"`. Initial color: `bg-orange-900/30`. No emoji on line 1 for zero rows. D-14 third-line format byte-for-byte preserved across all three row kinds.

**Refinement after human-verify (commit `e7948e3`):**
- `bg-orange-900/30` → `bg-[#F28C28]/30`: user requested specific brand hex with the same /30 alpha treatment as green/red rows.
- `pnlClass` now branches on `isZero` first, returning `text-gray-300` (inherits surrounding gray) for zero rows. The previous `text-green-400` on `+€0.00` visually overclaimed a profit; neutral gray makes the noop semantics unambiguous.

**Verification evidence:** With `initial_capital=1`, `bet_size=50%`, `contract_price=97` on EPL 24/25, every row renders muted `#F28C28/30`, no icon, third line `0 contracts @ 97¢ · €0.00 cost · +€0.00 · capital €1.00` with `+€0.00` in gray. Summary: `Bet on=0`, `Wins=0`, `Losses=0`, `Win rate=0.0%`, `Final capital=€1.00`, `Gain=+0.00%`. Mixed scenario at `100/50%/99` shows real-bet rows (green/red, ±€X.XX colored) above zero-contract rows (muted orange, gray ±€0.00) — visually unambiguous.

### D-14 regression check (UAT Test 1 re-run)

With `1000/2%/97`, the first winning row's third line still reads `20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60` byte-for-byte. Pitfall 2 sign-stripping preserved (`Math.abs(trade.pnl_cents) / 100` is the only path into `formatEuro` for pnl).

## Verification of must_have truths

| # | Truth | Evidence |
|---|-------|----------|
| 1 | Reverse-chronological display top→bottom across day boundaries AND within-day | User-confirmed EPL 24/25 walkthrough: Aug 25 → Aug 24 (Tottenham → ManCity → Aston Villa) → Aug 18 → Aug 17, capital strictly descending |
| 2 | Topmost row's `capital_after_cents == final_capital_cents` | User-confirmed €1003.60 top row matches Final capital card |
| 3 | Zero-contract rows excluded from `wins`/`losses`/`matches_bet_on`; `wins + losses === matches_bet_on` | All-zero stress case: `Bet on=0, Wins=0, Losses=0` (pre-fix: would have shown the full 98+ wins) |
| 4 | Zero-contract rows render `bg-[#F28C28]/30`, no emoji, gray pnl text | User-confirmed muted orange + neutral gray `+€0.00` |
| 5 | D-14 third-line format byte-for-byte for all three row kinds | UAT Test 1 re-run match exact; zero-contract rows show `0 contracts @ 97¢ · €0.00 cost · +€0.00 · capital €1.00` |
| 6 | Pitfall 2 sign-stripping holds | `formatEuro(Math.abs(trade.pnl_cents) / 100)` retained; no `formatEuro(trade.pnl_cents / 100)` path introduced |
| 7 | `pnpm fmt:check && pnpm lint && pnpm build` no new failures vs Plan 01 baseline | fmt:check: 3 pre-existing files (`actions.ts`, `api/[...path]/route.ts`, `sst-env.d.ts`) — none in `app/backtest/*`; lint: 4 warnings (all in `app/page.tsx`); build: clean, `/backtest` static |

## Task Commits

1. **Task 1: backtest.ts edits** — `20653ec` (fix)
2. **Task 2: TradeRow tri-state** — `0277022` (feat)
3. **Task 3 refinement: muted #F28C28/30 + neutral pnl** — `e7948e3` (style)

## Files Modified

- `dashboard/app/backtest/backtest.ts` — replaced date-only sort with `[...trades].reverse()`; introduced `placed = trades.filter((t) => t.contracts > 0)` and rebuilt `wins`/`losses`/`matches_bet_on` from `placed`. Engine kernel (lines 142-180) untouched. `BacktestTrade` and `BacktestSummary` shapes unchanged.
- `dashboard/app/backtest/page.tsx` — rewrote `TradeRow` for tri-state rendering: `isZero` dispatch first, `bg-[#F28C28]/30` + no emoji + gray pnl text for zero-contract rows. D-14 third-line format byte-for-byte preserved across all three row kinds.

## Decisions Made

Two design decisions surfaced during planning, both presented to the user with options before committing:

- **Keep `result` binary, gate on `contracts > 0`** (not introduce `result: "noop"`). Rationale: smaller diff; `contracts === 0` is a single source of truth for "did we bet"; `result` keeps carrying match-outcome information for future analytics (e.g., "would-have-won rate when capital-starved"). User approved Option Y.
- **Use `[...trades].reverse()` over `[...trades].sort(...)` with a secondary key.** Verified against the actual EPL/LaLiga JSON during plan-checker review: source-JSON within-day order matches kickoff order, so reverse is provably correct.

Two refinements surfaced during human-verify (Task 3):

- **Background color:** `bg-orange-900/30` → `bg-[#F28C28]/30` per user-specified brand hex; preserved `/30` alpha to keep the same visual rhythm as green/red rows.
- **PnL text on zero-contract rows:** `text-green-400` → `text-gray-300` to avoid visually overclaiming `+€0.00` as a profit; gray inherits the surrounding third-line text color.

## Deviations from Plan

The plan specified `bg-orange-900/30` and a binary `pnlClass`. Both were superseded by user feedback during the Task 3 human-verify checkpoint, applied as a single style commit (`e7948e3`) with no plan-level rework. The plan's verification protocol caught the visual issues exactly as designed.

The plan referenced "line 204" for `matches_bet_on` but the actual line was 205 — non-issue since the plan provides the exact code string to replace, not a line-keyed edit. Plan-checker flagged this as INFO; executor found the right line by content match.

## Issues Encountered

`pnpm fmt` failed (script in `package.json` uses `--write` which oxfmt 0.7.0 does not accept). Pre-existing project issue; `pnpm fmt:check` works correctly. Documented as a known-quirk separate from this plan's scope.

## Verification Results

End-of-plan gate (`cd dashboard && pnpm fmt:check && pnpm lint && pnpm build`):

- **fmt:check:** 3 pre-existing failures matching the 01-01-SUMMARY.md baseline. `app/backtest/*` clean.
- **lint:** 4 warnings, 0 errors — all in `app/page.tsx`, unchanged from baseline.
- **build:** ✅ clean. `/backtest` static.

User-confirmed visual gates: all three verification scenarios from the plan's `<how-to-verify>` block + the post-refinement re-check.

## User Setup Required

None — pure client-side change.

## Next Phase Readiness

**Phase 1 is now ready to close.** Both UAT gaps (Test 3, Test 6) are resolved; D-14 verbatim format preserved; engine kernel and schema invariants from Plan 01 untouched. The phase has shipped its single requirement (BT-06) with both the kernel rewrite (Plan 01) and the post-UAT refinements (Plan 02).

Suggested next steps:
1. Re-run `/gsd-verify-work 01` to flip Test 3 and Test 6 in `01-HUMAN-UAT.md` from `issue` / decision-recorded to `pass`. (Optional — `01-HUMAN-UAT.md` can also stand as a historical record of the diagnosis + design decision.)
2. Mark Phase 1 complete in ROADMAP.md and STATE.md (this summary commit handles those updates).
3. `/gsd-plan-phase 02` to begin Strategy Engine Core.

## Self-Check: PASSED

- All 3 commits exist: `20653ec`, `0277022`, `e7948e3`
- Static-grep invariants from plan-level `<verification>` block: all 9 patterns match
- Build gate green; no new failures vs Plan 01 baseline
- D-01..D-17 (Phase 1 locked decisions) preserved verbatim
- Engine kernel (backtest.ts:142-180) bytewise unchanged from Plan 01
- `BacktestTrade` / `BacktestSummary` shapes unchanged; `result` stays `"win" | "loss"`

---
*Phase: 01-backtest-p-l-math · Plan: 02 (gap closure)*
*Completed: 2026-04-30*
