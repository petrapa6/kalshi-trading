---
created: "2026-04-29"
title: "Backtest page: rework trading mechanism for contract-based P&L"
area: ui
resolves_phase: 1
files:
  - dashboard/app/backtest/backtest.ts
  - dashboard/app/backtest/page.tsx
---

## Problem

The current backtest engine uses a simplified yield multiplier:

```
win_profit = stake × avg_win_yield
loss       = stake
```

This is a proxy that doesn't match how Kalshi actually works. Kalshi sells contracts at a price P (e.g. 0.97 EUR per contract). The real mechanic:

1. Stake = `initial_capital × bet_fraction` (e.g. 1000 × 0.02 = 20 EUR)
2. Contracts bought = `floor(stake / P)` (e.g. floor(20 / 0.97) = 20 contracts)
3. Win: each contract pays 1 EUR → win = `contracts × (1 - P)` (e.g. 20 × 0.03 = 0.60 EUR)
4. Loss: you lose the amount paid → loss = `contracts × P` (e.g. 20 × 0.97 = 19.40 EUR, NOT 20 EUR — the unspent 0.60 EUR is returned)

Current `avg_win_yield` input approximates `(1 - P)` but skips the floor truncation and
uses full stake as loss rather than `contracts × P`. This becomes meaningful when P is not
close to 1 (lower-confidence bets) or when stake is large relative to P.

## Solution

Add a `contract_price` parameter to `BacktestParams` (e.g. default 0.97, range 0.50–0.99).
Derive `avg_win_yield` from it (`1 - contract_price`) or remove the separate yield input.

Update `runBacktest` / `detectFire` logic:

```ts
const contracts = Math.floor(betAmount / contractPrice);
const win  = contracts * (1 - contractPrice);   // profit on win
const loss = contracts * contractPrice;          // cost on loss (unspent remainder returned)
```

Update `BacktestTrade` to record: `contracts`, `contract_price`, `bet_amount`, `actual_cost`,
`win_profit` / `loss_amount`.

Update `BacktestSummary` to track capital correctly (loss is `actual_cost`, not full stake).

Update `page.tsx` UI: replace or rename `avgWinYield` input → `contractPrice` (or keep yield
as derived display). Show "Contracts bought" per trade row.
