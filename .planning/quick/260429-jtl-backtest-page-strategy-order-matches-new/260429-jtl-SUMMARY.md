---
id: 260429-jtl
type: quick
status: complete
description: Backtest page — capital simulation strategy with newest-first trade ordering
---

# Quick Task 260429-jtl — Summary

## Outcome

Dashboard backtest page now simulates capital accumulation over a season:

- Trade list is rendered newest-first (simulation still walks oldest→newest so capital compounds correctly).
- Two new strategy inputs: **Initial capital** (default `1000` EUR), **Bet size** (default `2%` of current capital).
- Two new analytics cards: **Final capital**, **Gain (%)**, color-coded (green ≥ initial, red below).
- Per-trade row shows `Bet €X · ±€Y · capital €Z`.
- Helper text near the financial inputs documents the asymmetric payoff: `WIN_YIELD = 0.03 EUR per 1 EUR staked; loss = full stake`.

Spec example sanity check: `1000 EUR × 0.02 = 20` stake → win yields `20 × 0.03 = 0.6` → new capital `1000.6`. Matches exactly.

## Files changed

- `dashboard/app/backtest/backtest.ts` — extended `BacktestParams`/`BacktestTrade`/`BacktestSummary`; introduced `detectFire` helper + exported `WIN_YIELD = 0.03`; `runBacktest` now sorts a local copy chronologically (`a.date.localeCompare(b.date)`), accumulates capital, and returns trades newest-first.
- `dashboard/app/backtest/page.tsx` — added `initialCapital`/`betFractionPct` state, two number inputs, `formatEuro` helper, two new SummaryCards with `tone` prop, per-row bet/pnl/capital line, and updated trigger description.

## Verification

- `pnpm exec oxfmt .` → all files formatted.
- `pnpm exec oxlint` → 0 errors (4 pre-existing warnings in `app/page.tsx`, unrelated).
- `pnpm build` → ✓ compiled successfully, all pages generated.
- Manual sanity: with 1000/2% defaults, the first chronological fire compounds to 1000.6 on win, matching the user's worked example.

## Notes for follow-up

- `simulateMatch` is kept as a back-compat shim for any external script that imported the old signature; it wraps `detectFire` and returns the legacy non-monetary trade shape.
- `WIN_YIELD` is hard-coded at 0.03 to match the spec — promoting it to a UI input is trivial if needed.
- The backtest still does not model fees or partial fills; it's a pure goal-trigger simulation against final scores.
