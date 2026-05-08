# Phase 1: Backtest P&L Math — Discussion Log

**Gathered:** 2026-04-29
**Mode:** default (interactive, single-question turns)
**Areas selected:** all 4 + 2 follow-ups

> Human-readable record of every question asked, options presented, and what
> was selected. Not consumed by downstream agents — see `01-CONTEXT.md` for
> the canonical decisions.

---

## Area 1: Contract-price input model

**Q1.1: How is `contract_price` provided to the backtest?**
- Single value, slider+number (Recommended) ← **selected**
- Min/max range, sampled per trade
- Hardcoded constant in code, no UI

**Q1.2: Default value and range for the price input?**
- Default 0.97, range 0.50–0.99, step 0.01 (Recommended) ← **selected**
- Default 0.95, range 0.85–0.99, step 0.01
- Default 0.97, range 0.01–0.99, step 0.01

**Q1.3: Input field label?**
- Contract price (€ per contract) (Recommended) ← **selected**
- Yes price (€)
- Entry price (€)

**Q1.4: UI placement?**
- Replace `avg_win_yield` in-place (Recommended) ← **selected**
- Add as a separate slider above
- You decide

**Q1.5 (follow-up): Floor-remainder behaviour?**
- Returned to capital, not at risk (Recommended) ← **selected**
- Forfeited — unspent stake is lost
- Round contracts up

**Q1.6 (follow-up): Helper text?**
- Yield per win line (Recommended) ← **selected**
- Win/loss in € for current bet size
- No helper

> **Note:** Q1.2 / Q1.3 / Q1.6 values were later overridden by area-3
> decisions (cents-everywhere). The label became "Contract price (cents)";
> default 97 / range 50–99 / step 1; helper text shifted to cents wording.
> See CONTEXT.md D-02 / D-03 for the final values.

## Area 2: yes_price slider scope (roadmap fix)

**Q2.1: Reconciliation of roadmap inconsistency?**
- Phase 1 ignores yes_price sliders — fix roadmap text (Recommended) ← **selected**
- Phase 1 adds them, AND they ARE the contract_price
- Phase 1 adds yes_price sliders but they don't drive math yet

**Q2.2: Roadmap fix scope?**
- Yes — update ROADMAP.md in the same phase commit (Recommended)
- No — leave roadmap as-is, just note the deviation in CONTEXT.md
- Replace with the new contract_price criterion explicitly ← **selected**

## Area 3: Cents vs EUR units

**Q3.1: Move backtest internals to integer cents?**
- Stay in EUR floats (Recommended)
- Convert internals to integer cents ← **selected**
- Hybrid (cents only inside `floor()`)

**Q3.2: Boundary between EUR (inputs/display) and integer cents (internals)?**
- Convert at runBacktest entry; types stay EUR-shaped externally (Recommended) ← **selected**
- Move public types to cents too
- Cents only inside the floor() step

**Q3.3: How is `contract_price` represented in `BacktestParams`?**
- Float EUR, e.g. 0.97 (Recommended)
- Integer cents, e.g. 97 ← **selected**
- Both (float param + helper)

**Q3.4: Price-input UI display (now that price is integer cents)?**
- Default 97, range 50–99, step 1, label 'Contract price (cents)' (Recommended) ← **selected**
- Default 97, range 50–99, step 1, label 'Contract price (¢)'
- Default 97, range 88–99, step 1 (tighter)

**Q3.5: BacktestTrade `bet_amount` / `pnl` / `capital_after` types?**
- BacktestTrade fields stay EUR floats (Recommended)
- Add integer-cents fields too
- Replace EUR with integer-cents on BacktestTrade entirely ← **selected**

**Q3.6: BacktestSummary money fields?**
- Yes — also integer cents (Recommended) ← **selected**
- No — keep summary in EUR floats

## Area 4: Trade row & schema fields

**Q4.1: Which new fields land on `BacktestTrade`?**
- Add `contracts` and `contract_price_cents` only; derive the rest in render (Recommended) ← **selected**
- Add `contracts`, `contract_price_cents`, `actual_cost_cents`
- Add all of them (`actual_cost`, `win_profit`, `loss_amount` too)

**Q4.2: What's removed from `BacktestTrade`?**
- Remove `bet_amount`; keep `pnl`, `capital_after` as cents (Recommended) ← **selected**
- Keep `bet_amount_cents` AND add `actual_cost_cents`
- Replace `bet_amount` with `bet_amount_cents` (intended stake), drop actual cost

**Q4.3: Trade row third-line format?**
- '20×97¢ = €19.40 · +€0.60 · capital €1000.60' (Recommended)
- '20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60' ← **selected**
- Two lines (cost / P&L on separate lines)

**Q4.4: New summary cards?**
- No new cards — keep the 7 current (Recommended) ← **selected**
- Add 'Total contracts'
- Add 'Avg cost per trade'

**Q4.5: Legacy `simulateMatch` and `DEFAULT_WIN_YIELD`?**
- Drop both (Recommended) ← **selected**
- Keep `simulateMatch`, drop `DEFAULT_WIN_YIELD`
- Keep both

## Follow-up: Additional gray areas

**Q5.0: Which additional gray areas?**
- Python backtest scope (NOT selected)
- Test coverage (NOT selected)
- Zero-contracts edge case ← **selected**
- Naming: contract_price_cents vs yes_price_cents ← **selected**

**Q5.1: When `floor(stake_cents / price_cents) === 0`?**
- Skip the trade entirely (Recommended)
- Write a 0-contracts BacktestTrade with pnl=0 ← **selected**
- Halt the simulation early (bankrupt)

**Q5.2: Field naming?**
- contract_price_cents (Recommended) ← **selected**
- yes_price_cents
- entry_price_cents

---

## Deferred items captured during discussion

- Python `src/predictions/backtest.py` contract-math update (raised, not selected)
- Unit test for `runBacktest` against hand-calculated example (raised, not selected)
- Field rename to `yes_price_cents` (considered, rejected — different semantic role)
- Min/max contract-price range with per-trade sampling (considered, rejected — non-determinism)
- Per-trade `actual_cost` / `win_profit` / `loss_amount` schema fields (considered, rejected — derivable in render)

## Claude-discretion items (planner decides)

- Input element type for `contract_price_cents`: number input vs slider
- Rounding mode for stake step (`Math.round` recommended)
- Whether to rename local variables in `runBacktest` for clarity
- Whether to add a unit test for the new math (recommendation: yes, but
  Phase 1 success criterion #1 only requires manual verification)

---

*Phase: 01-backtest-p-l-math*
*Discussion log: 2026-04-29*
