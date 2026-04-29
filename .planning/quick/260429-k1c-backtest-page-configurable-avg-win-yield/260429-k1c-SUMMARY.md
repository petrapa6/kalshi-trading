---
id: 260429-k1c
type: quick
status: complete
description: Backtest page — configurable Avg win yield input replacing hard-coded WIN_YIELD constant
---

# Quick Task 260429-k1c — Summary

## Outcome

The backtest page's win yield is no longer a hard-coded `0.03` — it's a strategy parameter
the user can change in the sidebar. Default value (`DEFAULT_WIN_YIELD = 0.03`) reproduces the
previous behaviour exactly, so existing runs are regression-safe.

## Files changed

- `dashboard/app/backtest/backtest.ts` — added `avg_win_yield: number` to `BacktestParams`;
  renamed exported constant `WIN_YIELD` → `DEFAULT_WIN_YIELD` (same value, repurposed as the
  UI's default); `runBacktest` now reads `avg_win_yield` from params instead of the constant.
- `dashboard/app/backtest/page.tsx` — added `avgWinYield` state defaulting to
  `DEFAULT_WIN_YIELD`, a number input (min 0.001, max 1, step 0.001), passed it through to
  `runBacktest`, and updated the helper line to display the active rate live.

## Verification

- `pnpm exec oxfmt .` clean.
- `pnpm exec oxlint app/backtest/` → 0 warnings, 0 errors.
- `pnpm build` → ✓ compiled successfully, all pages generated.
- Sanity: with the default 0.03 yield, `1000 × 0.02 × 0.03 = 0.6 EUR` matches the previous
  worked example. Changing the input recomputes the simulation in real time via `useMemo`.

## Notes for follow-up

- `DEFAULT_WIN_YIELD` stays exported so any future caller (CLI, tests) keeps a sensible
  baseline without re-deriving the magic number.
- The input range (0.001..1) is a generous superset of realistic Kalshi YES-leg yields;
  tighten if the page ever picks up validation rules.
