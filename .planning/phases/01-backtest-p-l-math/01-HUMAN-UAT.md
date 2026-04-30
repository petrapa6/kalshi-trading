---
status: complete
phase: 01-backtest-p-l-math
source: [01-VERIFICATION.md]
started: 2026-04-29T21:36:00Z
updated: 2026-04-30T07:35:00Z
closed_by_plan: 01-02
---

## Current Test

[testing complete]

## Tests

### 1. Worked-example seam (BT-06 success criterion #1)
expected: On `/backtest` with `initial_capital=1000`, `bet_size=2`, `contract_price=97`, the first winning row's third line reads exactly `20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60`
result: pass

### 2. Zero-contract seam (D-17)
expected: With `initial_capital=1`, `bet_size=50`, `contract_price=97`, at least one trade row reads `0 contracts @ 97¢ · €0.00 cost · +€0.00 · capital €1.00`; capital does not drift across consecutive zero-contract rows
result: pass

### 3. Capital conservation seam
expected: Walking 10 trade rows from newest to oldest, capital decreases by exactly the loss-row pnl, increases by exactly the win-row pnl, and is unchanged across zero-contract rows; topmost row's `capital €X.XX` matches Final capital summary card
result: pass
closed_by:
  commit: 20653ec
  plan: 01-02 Task 1
  evidence: |
    Plan 01-02 replaced `[...trades].sort((a, b) => b.date.localeCompare(a.date))`
    with `[...trades].reverse()` in dashboard/app/backtest/backtest.ts. Since trades
    are pushed in chronological-walk order, reversing yields strict newest-first
    INCLUDING within-day. User confirmed during /gsd-execute-phase Task 3
    human-verify: top row Aug 25 Wolves-Chelsea (€1,003.60 = Final capital);
    Aug 24 group descends 1003.00 → 1002.40 → 1001.80; Aug 18 1001.20; Aug 17
    1000.60. Strictly monotone. Plan-checker independently verified ESPN event-IDs
    map to ascending kickoff order within a date.
historical_report: |
  The ordering of matches is not matching the trade order. Matches on the same day are mixed, this is the order in the app:
  2024-08-24 · Aston Villa 0 – 2 Arsenal — 51 contracts @ 97¢ · +€1.53 · capital €1,004.59
  2024-08-24 · Manchester City 4 – 1 Ipswich Town — capital €1,006.12
  2024-08-24 · Tottenham Hotspur 4 – 0 Everton — capital €1,007.65
  2024-08-18 · Chelsea 0 – 2 Manchester City — capital €1,003.06
  2024-08-17 · Everton 0 – 3 Brighton & Hove Albion — capital €1,001.53

### 4. No-negative-capital seam
expected: With `initial_capital=100`, `bet_size=50`, `contract_price=99`, no trade row shows a negative `capital €` value (zero-contract rows should appear once capital can no longer afford one contract)
result: pass
caveat: |
  Invariant held (no negative capital observed). However, in this dataset
  the strategy's near-1.0 hit rate at price=99 means capital climbs rather
  than depletes, so the in-flight zero-contract transition path (capital
  drops below price → engine clamps to 0 contracts mid-run) was not
  actually exercised. That transition path is already covered by Test 2
  (`initial_capital=1` → immediate clamp from first bet), so the engine
  logic itself is verified.

### 5. Sidebar visual regression
expected: The "Contract price (cents)" slider sits in the same visual slot the avg_win_yield input occupied (between Bet size and the trailing helper paragraph); label updates live with slider value; helper text reads `Yield per win: 3 cents per contract (€0.03)` at price=97
result: pass

### 6. WR-01 follow-up — design decision
expected: Decide whether zero-contract rows should be excluded from `wins`/`losses`/`matches_bet_on` tallies (Option A) or whether `matches_bet_on` should be renamed (Option B). Current behavior: zero-contract rows leak into win/loss counts via `trade.result` discriminator. Out of D-17 scope but raised by code review WR-01.
result: pass
decision: |
  Option A (extended): exclude zero-contract rows from `wins`, `losses`, and
  `matches_bet_on` tallies. UI keeps the row visible but renders it in
  orange with no checkmark/cross icon, signaling "would have bet if
  capital permitted" — distinct from green ✓ (won bet) and red ✗ (lost bet).
  Rationale: tallies should reflect actual edge captured, not
  hypothetical edge, while the UI still surfaces capital-starvation
  events so the user can see how often they cost the strategy.
closed_by:
  commits: [20653ec, 0277022, e7948e3]
  plan: 01-02 Task 1 + Task 2 + post-checkpoint refinement
  evidence: |
    Tally side (commit 20653ec): introduced `placed = trades.filter(t => t.contracts > 0)`
    in dashboard/app/backtest/backtest.ts; rebuilt wins/losses/matches_bet_on from
    placed instead of trades. result discriminator stays binary "win" | "loss"
    (chosen over a "noop" enum value — smaller diff, contracts === 0 is the single
    source of truth for "did we bet").
    UI side (commit 0277022): TradeRow rewritten to dispatch on isZero first,
    then on won. Zero-contract rows render with bg-orange-900/30 (initial choice)
    and no emoji. D-14 third-line format byte-for-byte preserved.
    Refinement (commit e7948e3): bg-orange-900/30 → bg-[#F28C28]/30 per user-
    specified brand hex with /30 alpha to match green/red rhythm; pnlClass on
    zero rows now text-gray-300 (inherits surrounding gray) instead of
    text-green-400 — eliminates visual overclaim of profit on +€0.00.
    User confirmed via /gsd-execute-phase Task 3 human-verify: all-zero stress
    case (initial=1, bet=50%, price=97) shows Bet on=0, Wins=0, Losses=0,
    Win rate=0.0%, Final capital=€1.00; mixed scenario at 100/50%/99 shows
    real-bet rows (green/red) above zero-contract rows (muted orange, gray
    +€0.00) unambiguously.

## Summary

total: 6
passed: 6
issues: 0
pending: 0
skipped: 0
blocked: 0
closed_via: 01-02-PLAN.md

## Gaps

<!-- Both gaps closed by Plan 01-02. Retained as historical record of the diagnosis and design-decision artifact that drove the fix plan. -->

- truth: "Trade rows are displayed in true reverse-chronological order such that the topmost row reflects the final trade, and capital values change monotonically (or stay flat for zero-contract rows) walking top→bottom."
  status: closed
  closed_by_commit: 20653ec
  reason: |
    User reported: matches on the same day appear in ascending kickoff order rather than descending, so within a day capital values *increase* top→bottom while across days they decrease. Concrete example: Aug 24 group reads 1004.59 → 1006.12 → 1007.65 top→bottom, then drops to 1003.06 (Aug 18) and 1001.53 (Aug 17). Capital conservation per se holds (1001.53 + 4 × 1.53 = 1007.65), but the topmost displayed row is *not* the final trade.
  severity: major
  test: 3
  root_cause: |
    `dashboard/app/backtest/backtest.ts:198-199` sorts the display list by
    `date` descending only. Within-day order is whatever order the source
    JSON stores matches in, preserved through V8's stable sort.
    `runBacktest` walks `chronological` (line 138, sorted ascending by
    date alone) so trades are built in ascending walk order. After the
    descending date sort on line 198-199, day groups flip but within-day
    order stays in source-JSON order, breaking the "topmost row = final
    trade" invariant.
  artifacts:
    - path: "dashboard/app/backtest/backtest.ts"
      issue: "Lines 198-199: `[...trades].sort((a, b) => b.date.localeCompare(a.date))` sorts by date alone with no within-day tiebreaker."
  missing:
    - "Replace the date-only sort with a sort that preserves within-day chronological order in reverse, so the topmost displayed row is the final trade."
    - "Simplest fix: `[...trades].reverse()` (works because `trades` is built in chronological walk order, so reversing yields strict newest-first including within-day)."
    - "Verify topmost row's `capital_after_cents` equals `final_capital_cents` after fix."
  debug_session: "(diagnosed inline by orchestrator; no separate debug session)"

- truth: "Zero-contract rows (capital insufficient to buy even one contract) are excluded from wins/losses/matches_bet_on tallies, and rendered in the UI as a third visual state — orange, no checkmark/cross icon — distinct from won-bet (green ✓) and lost-bet (red ✗) rows."
  status: closed
  closed_by_commits: [20653ec, 0277022, e7948e3]
  reason: |
    Decision A (extended) from Test 6. Current code lets zero-contract rows
    leak into win/loss tallies via the `trade.result` discriminator
    (REVIEW.md WR-01). UI currently renders zero-contract rows with the
    same green/red treatment as bet-won / bet-lost rows, conflating
    "would have bet" with "did bet."
  severity: major
  test: 6
  artifacts:
    - path: "dashboard/app/backtest/backtest.ts"
      issue: "Tally aggregation in runBacktest uses trade.result regardless of contracts > 0; zero-contract rows are summed into wins/losses/matches_bet_on."
    - path: "dashboard/app/backtest/page.tsx"
      issue: "TradeRow rendering uses binary win/loss styling; needs a third orange state for zero-contract rows."
  missing:
    - "Update runBacktest to skip zero-contract rows when incrementing wins/losses/matches_bet_on counters."
    - "Add a `result: 'noop'` (or equivalent) discriminator branch in BacktestTrade for zero-contract rows."
    - "Add orange-themed TradeRow variant with no icon for the noop state; preserve the existing third-line format (`0 contracts @ ... · €0.00 cost · +€0.00 · capital €X.XX`)."
    - "Verify summary card values (win rate, ROI%) recompute correctly with the new tally semantics."
