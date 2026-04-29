---
status: partial
phase: 01-backtest-p-l-math
source: [01-VERIFICATION.md]
started: 2026-04-29T21:36:00Z
updated: 2026-04-29T21:36:00Z
---

## Current Test

[awaiting human testing]

## Tests

### 1. Worked-example seam (BT-06 success criterion #1)
expected: On `/backtest` with `initial_capital=1000`, `bet_size=2`, `contract_price=97`, the first winning row's third line reads exactly `20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60`
result: [pending]

### 2. Zero-contract seam (D-17)
expected: With `initial_capital=1`, `bet_size=50`, `contract_price=97`, at least one trade row reads `0 contracts @ 97¢ · €0.00 cost · +€0.00 · capital €1.00`; capital does not drift across consecutive zero-contract rows
result: [pending]

### 3. Capital conservation seam
expected: Walking 10 trade rows from newest to oldest, capital decreases by exactly the loss-row pnl, increases by exactly the win-row pnl, and is unchanged across zero-contract rows; topmost row's `capital €X.XX` matches Final capital summary card
result: [pending]

### 4. No-negative-capital seam
expected: With `initial_capital=100`, `bet_size=50`, `contract_price=99`, no trade row shows a negative `capital €` value (zero-contract rows should appear once capital can no longer afford one contract)
result: [pending]

### 5. Sidebar visual regression
expected: The "Contract price (cents)" slider sits in the same visual slot the avg_win_yield input occupied (between Bet size and the trailing helper paragraph); label updates live with slider value; helper text reads `Yield per win: 3 cents per contract (€0.03)` at price=97
result: [pending]

### 6. WR-01 follow-up — design decision
expected: Decide whether zero-contract rows should be excluded from `wins`/`losses`/`matches_bet_on` tallies (Option A) or whether `matches_bet_on` should be renamed (Option B). Current behavior: zero-contract rows leak into win/loss counts via `trade.result` discriminator. Out of D-17 scope but raised by code review WR-01.
result: [pending]

## Summary

total: 6
passed: 0
issues: 0
pending: 6
skipped: 0
blocked: 0

## Gaps
