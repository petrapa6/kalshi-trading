---
id: 260429-jtl
type: quick
status: planned
description: Backtest page — capital simulation strategy with newest-first trade ordering
---

# Quick Task 260429-jtl

**Goal:** Add capital-accumulation strategy mechanics to the dashboard backtest page:
1. Display trades newest-first (sim still iterates chronologically).
2. Add strategy options: `initial_capital` (default 1000 EUR) and `bet_fraction` (default 2% of current capital).
3. Add two analytics cards: **Final capital** and **Gain (%)**.
4. Apply the asymmetric payoff: win adds `bet * 0.03`, loss subtracts the full bet.
5. Surface the `0.03 EUR / EUR invested` win-yield assumption next to the inputs.

## Files to change

- `dashboard/app/backtest/backtest.ts` — extend `BacktestParams`, `BacktestTrade`, `BacktestSummary`; rewrite `runBacktest` to walk matches chronologically, track running capital, then return trades newest-first.
- `dashboard/app/backtest/page.tsx` — add capital + bet-fraction inputs, two new SummaryCards (Final capital, Gain %), per-trade bet/capital display, win-yield helper text.

## Tasks

### Task 1 — Extend strategy engine (`backtest.ts`)

- Add to `BacktestParams`: `initial_capital: number`, `bet_fraction: number` (0..1).
- Add to `BacktestTrade`: `bet_amount: number`, `pnl: number`, `capital_after: number`.
- Add to `BacktestSummary`: `initial_capital: number`, `final_capital: number`, `gain_pct: number`.
- Export constant `WIN_YIELD = 0.03` (used both in engine and page UI).
- `simulateMatch` no longer computes capital — it returns the trade *without* monetary fields (or expose a separate `detectFire` helper). Cleanest: rename current `simulateMatch` → `detectFire` returning a leaner "fire" struct (no monetary fields), then `runBacktest` enriches each fired trade with `bet_amount`/`pnl`/`capital_after` as it walks chronologically.
- `runBacktest`:
  - Sort `file.matches` chronologically (asc by `date`) into a local copy — do NOT mutate input.
  - Walk that chronological copy, accumulating `capital`. For each fire: `bet = capital * bet_fraction`; `pnl = result === 'win' ? bet * WIN_YIELD : -bet`; `capital += pnl`.
  - Build `trades` newest-first by sorting the collected fires by `date` desc before returning.
  - `gain_pct = (final_capital - initial_capital) / initial_capital * 100`. Round summary numbers to 4 decimals; preserve precision in trade rows.

### Task 2 — Surface controls + analytics (`page.tsx`)

- Add two state hooks: `initialCapital` (default 1000), `betFractionPct` (default 2; convert to 0.02 when calling `runBacktest`).
- Number input for initial capital (min 1, step 1).
- Number input for bet fraction (% — min 0.1, step 0.1, max 100).
- Pass new params through `runBacktest`.
- Two new SummaryCards: **Final capital** (`€` + value to 2 dp), **Gain** (`%` to 2 dp, color green if positive, red if negative).
- Update each `TradeRow` to show `bet €X.XX → +€Y.YY (cap €Z.ZZ)` style line.
- Add helper line near financial inputs: "Win yield: 0.03 EUR per 1 EUR staked. A losing bet loses the full stake."

### Task 3 — Verification

- `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build` must pass.
- Sanity check: with default params (1000 EUR, 2%, EPL 24/25), the trade list renders newest match first, Final capital card matches the last trade's `capital_after`, Gain % equals `(final − 1000) / 10`.

## Done when

- All three tasks complete, lint/format/build green, manual sanity check passes.
- Two atomic commits (engine, then page) — UI changes don't precede engine API changes.
