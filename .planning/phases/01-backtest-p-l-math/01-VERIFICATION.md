---
phase: 01-backtest-p-l-math
verified: 2026-04-29T21:36:00Z
status: human_needed
score: 19/19 must-haves verified
overrides_applied: 0
roadmap_success_criteria:
  - id: SC-1
    text: "Backtest results use `contracts = floor(stake / price)`, `win = contracts × (1 − price)`, `loss = contracts × price` — verifiable by checking output against manual calculation for one match"
    status: passed
    evidence: "dashboard/app/backtest/backtest.ts:151,157,159 — canonical kernel matches; node-recomputed worked example (1000/0.02/97) gives contracts=20, win pnl=+60, loss pnl=−1940; zero-stake case (1/0.5/97) gives contracts=0"
  - id: SC-2
    text: "The `avg_win_yield` input is gone; a `contract_price` input (default 97, range 50–99 cents) drives the new math; existing sliders (`min_minute`, `min_lead`) remain and function."
    status: passed
    evidence: "ROADMAP.md:58 contains the locked D-06 wording verbatim; page.tsx:75 seeds contractPriceCents=97; page.tsx:208–217 renders slider min=50 max=99 step=1; page.tsx:147–170 retains min_minute/min_lead sliders unchanged"
  - id: SC-3
    text: "`pnpm fmt:check && pnpm lint && pnpm build` passes with no new failures"
    status: passed_with_caveat
    evidence: "fmt:check fails on 3 pre-existing files (app/actions.ts, app/api/[...path]/route.ts, sst-env.d.ts) — neither modified file is in the failing list; lint reports 4 warnings 0 errors, all 4 in app/page.tsx (pre-existing); build succeeds (Next.js 16.1.6, /backtest route generates static)"
must_haves:
  truths:
    - id: D-01
      text: "BacktestParams gains a new field contract_price_cents (integer cents)"
      status: verified
      evidence: "dashboard/app/backtest/backtest.ts:5–11"
    - id: D-02
      text: "Sidebar contract_price_cents input is a slider with default 97, range 50–99, step 1, label 'Contract price (cents)' — replaces the avg_win_yield input in-place"
      status: verified
      evidence: "dashboard/app/backtest/page.tsx:206–218 (slider type=range min={50} max={99} step={1} value={contractPriceCents}); state seed at :75 useState(97); positioned inside the same border-t pt-3 block where avg_win_yield used to be"
    - id: D-03
      text: "Helper text below the price input reads 'Yield per win: {100 − price_cents} cents per contract (€{(100 − price_cents) / 100})'"
      status: verified
      evidence: "dashboard/app/backtest/page.tsx:219–222"
    - id: D-04
      text: "Floor-truncation remainder stays in capital — there is no separate at-risk stake; bet_amount field is removed from BacktestTrade and derived at render"
      status: verified
      evidence: "backtest.ts BacktestTrade (lines 13–29) has no bet_amount field; cost_cents derived at render in page.tsx:43"
    - id: D-05
      text: "One fixed contract price per backtest run — deterministic, no per-trade randomisation, no min/max range"
      status: verified
      evidence: "backtest.ts:151 uses contract_price_cents from params throughout; no Math.random or per-trade variation"
    - id: D-06
      text: "ROADMAP Phase 1 success criterion #2 is rewritten verbatim in the same phase commit to the wording locked in CONTEXT.md"
      status: verified
      evidence: ".planning/ROADMAP.md:58 contains the verbatim D-06 wording; commit 3494f7e applies it"
    - id: D-07
      text: "Phase 1 does not add min_yes_price or max_yes_price sliders — those belong to Phase 2 (BT-07)"
      status: verified
      evidence: "page.tsx contains no min_yes_price/max_yes_price sliders; ROADMAP success criterion #2 no longer references them"
    - id: D-08
      text: "runBacktest converts EUR inputs to integer cents at function entry; all internal arithmetic is integer cents"
      status: verified
      evidence: "backtest.ts:142 const initial_capital_cents = Math.floor(initial_capital * 100); only EUR multiplication in the function — every subsequent multiplication uses integer cents"
    - id: D-09
      text: "BacktestParams external shape: initial_capital (EUR float), contract_price_cents (integer cents), bet_fraction (0..1), min_minute, min_lead"
      status: verified
      evidence: "backtest.ts:5–11 matches D-09 exactly"
    - id: D-10
      text: "BacktestTrade money fields are integer cents — adds contracts and contract_price_cents, renames pnl→pnl_cents and capital_after→capital_after_cents, removes bet_amount"
      status: verified
      evidence: "backtest.ts:13–29 — exact shape match (contracts, contract_price_cents, pnl_cents, capital_after_cents present; bet_amount/pnl/capital_after removed)"
    - id: D-11
      text: "BacktestSummary money fields become integer cents (initial_capital_cents, final_capital_cents); gain_pct stays a float percentage"
      status: verified
      evidence: "backtest.ts:31–40 — initial_capital_cents and final_capital_cents present; gain_pct still a number"
    - id: D-12
      text: "page.tsx formats every cents-typed field for display via formatEuro(value / 100); no new format helper introduced"
      status: verified
      evidence: "page.tsx:58 (cost_cents/100), :60 (Math.abs(pnl_cents)/100), :62 (capital_after_cents/100), :221 (yield/100), :271 (final_capital_cents/100); only one formatEuro definition at :8"
    - id: D-13
      text: "Schema additions are minimal — only contracts and contract_price_cents on BacktestTrade. Do NOT add actual_cost, win_profit, or loss_amount fields; derive at render"
      status: verified
      evidence: "backtest.ts BacktestTrade has no actual_cost/win_profit/loss_amount; cost_cents derived at render in page.tsx:43"
    - id: D-14
      text: "TradeRow third line reads exactly '{N} contracts @ {P}¢ · €{cost} cost · {±}€{|pnl|} · capital €{cap}'"
      status: verified
      evidence: "page.tsx:56–63 implements the exact verbatim form; sign-stripping at :60 with Math.abs preserves Pitfall 2 invariant"
    - id: D-15
      text: "Summary cards remain unchanged — keep the 7 current ones (Scanned, Bet on, Wins, Losses, Win rate, Final capital, Gain)"
      status: verified
      evidence: "page.tsx:248–286 — 7 SummaryCards in the original order"
    - id: D-16
      text: "simulateMatch export and DEFAULT_WIN_YIELD constant are deleted from backtest.ts (zero callers verified)"
      status: verified
      evidence: "grep -rE 'simulateMatch|DEFAULT_WIN_YIELD' under dashboard/app, dashboard/lib, cli/src, src/ → 0 source matches (matches in .next/ are stale build cache, regenerated on next build); production build succeeds"
    - id: D-17
      text: "When floor(stake_cents / contract_price_cents) === 0 the engine writes a BacktestTrade with contracts=0, pnl_cents=0, capital_after_cents unchanged"
      status: verified
      evidence: "backtest.ts:153–155 — explicit zero-contract branch; node recomputation (1/0.5/97) → contracts=0 confirmed"
    - id: KERNEL
      text: "Engine math kernel: contracts = floor(stake_cents / contract_price_cents); win adds contracts × (100 − contract_price_cents); loss subtracts contracts × contract_price_cents"
      status: verified
      evidence: "backtest.ts:151,157,159"
    - id: GATE
      text: "cd dashboard && pnpm fmt:check && pnpm lint && pnpm build passes with no new failures"
      status: verified_with_caveat
      evidence: "fmt:check 3 pre-existing failures (none in modified files), lint 4 warnings (all in app/page.tsx, pre-existing), build OK"
gaps: []
deferred: []
human_verification:
  - test: "Worked-example seam (BT-06 success criterion #1)"
    expected: "On /backtest with initial_capital=1000, bet_size=2, contract_price=97, the first winning row's third line reads exactly '20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60'"
    why_human: "Requires loading the dashboard in a browser and visually inspecting the rendered TradeRow string with a known-winning fixture; cannot be confirmed without running the page."
  - test: "Zero-contract seam (D-17)"
    expected: "With initial_capital=1, bet_size=50, contract_price=97, at least one trade row reads '0 contracts @ 97¢ · €0.00 cost · +€0.00 · capital €1.00' and capital does not drift across consecutive zero-contract rows"
    why_human: "Requires running the page; the engine math is verified statically but the user-visible row format and capital invariance across rows is a render-time property"
  - test: "Capital conservation seam"
    expected: "Walking 10 trade rows from newest to oldest, capital decreases by exactly the loss-row pnl, increases by exactly the win-row pnl, and is unchanged across zero-contract rows; topmost row's capital matches Final capital summary card"
    why_human: "Visual sanity check across DOM rows; not statically expressible"
  - test: "No-negative-capital seam"
    expected: "With initial_capital=100, bet_size=50, contract_price=99, no trade row shows a negative capital value (zero-contract rows should appear once capital can no longer afford one contract)"
    why_human: "End-to-end stress check across the full season's fires; requires running the engine on real data"
  - test: "Sidebar visual regression"
    expected: "The Contract price (cents) slider sits in the same visual slot the avg_win_yield input occupied (between Bet size and the trailing helper paragraph); label updates live with the slider value; helper text reads 'Yield per win: 3 cents per contract (€0.03)' at price=97"
    why_human: "Layout/visual position cannot be asserted from source; requires browser inspection"
  - test: "WR-01 follow-up (out of D-17 scope but flagged in REVIEW.md)"
    expected: "Decide whether zero-contract rows should be excluded from wins/losses/matches_bet_on tallies (Option A) or whether matches_bet_on should be renamed (Option B). Current behavior: zero-contract rows leak into win/loss counts via trade.result discriminator"
    why_human: "Design call — D-17 fixed engine semantics but did not specify summary semantics; raised as INFO-class follow-up by code review (WR-01). Out of Phase 1 scope per D-17 wording but worth a deliberate decision."
requirements_traceability:
  - id: BT-06
    description: "User backtests use contract-based P&L math: contracts = floor(stake_cents / price_cents), win profit = contracts × (100 − price_cents), loss = contracts × price_cents; the avg_win_yield input is removed from the backtest UI"
    plan: "01-01-PLAN.md"
    status: closed
    evidence: "Engine kernel verified at backtest.ts:151,157,159; avg_win_yield removed from page.tsx and BacktestParams; static greps confirm zero references in source; production build passes"
notes:
  - "REVIEW.md WR-01 (zero-contract rows leak into wins/losses/matches_bet_on tallies) is real but not a phase gap — D-17 scopes engine behavior only, not summary semantics. Surfaced as human_verification item for design decision."
  - "REVIEW.md WR-02 (zero-contract loss rows render with red bg + green pnl text) is also out of D-17 scope but a real visual inconsistency — surfaced under WR-01 follow-up."
  - "Plan SUMMARY.md noted oxfmt 0.7.0 reformatted modified files to 2-space indent despite oxfmt.json declaring indentWidth=4. The committed files pass fmt:check; this is a config/formatter discrepancy outside Phase 1 scope."
  - "ROADMAP grep with the bare wording 'a contract_price input (default 97, range 50–99 cents)' (no backticks around contract_price) returns no match because the file uses backtick-fenced `contract_price`. The D-06 wording in CONTEXT.md does include the backticks; the file content matches D-06 verbatim."
  - "Stale references to DEFAULT_WIN_YIELD/simulateMatch/avgWinYield exist in dashboard/.next/ build cache and in .planning/ docs (intentional — describing what was removed). All source files (.ts/.tsx in dashboard/app, dashboard/lib, cli/src, src/) are clean."
---

# Phase 01: Backtest P&L Math — Verification Report

**Phase Goal:** The backtest engine computes P&L using contract-based math, removing the avg_win_yield approximation.
**Verified:** 2026-04-29T21:36:00Z
**Status:** human_needed
**Re-verification:** No — initial verification.

## Goal Achievement

### Roadmap Success Criteria

| # | Criterion | Status | Evidence |
|---|-----------|--------|----------|
| 1 | Backtest uses contracts = floor(stake/price), win = contracts × (1−price), loss = contracts × price | passed | backtest.ts:151,157,159 + node-recomputed worked example |
| 2 | avg_win_yield gone; contract_price (97, 50–99 cents) drives math; min_minute/min_lead remain | passed | ROADMAP:58 + page.tsx:75,206–222 + retained sliders at page.tsx:147–170 |
| 3 | pnpm fmt:check && pnpm lint && pnpm build passes with no new failures | passed (caveat) | fmt:check 3 pre-existing failures (modified files NOT in list); lint 4 pre-existing warnings; build OK |

### Observable Truths (D-01..D-17 + KERNEL + GATE)

All 19 must-have truths verified. Score: 19/19. See frontmatter for per-truth evidence.

### Required Artifacts

| Artifact | Expected | Exists | Substantive | Wired | Status |
|----------|----------|--------|-------------|-------|--------|
| dashboard/app/backtest/backtest.ts | Engine with contract-based kernel + cents schemas; simulateMatch & DEFAULT_WIN_YIELD removed | yes | yes | yes (imported by page.tsx) | VERIFIED |
| dashboard/app/backtest/page.tsx | Sidebar slider, TradeRow third line per D-14, SummaryCard cents reads | yes | yes | yes (rendered at /backtest route) | VERIFIED |
| .planning/ROADMAP.md (Phase 1 SC #2) | D-06 verbatim wording | yes | yes | n/a (doc) | VERIFIED |

### Key Link Verification

| From | To | Via | Status |
|------|----|----|--------|
| page.tsx | backtest.ts | `import { runBacktest, type BacktestTrade } from "./backtest"` (line 6) | WIRED |
| useMemo params | runBacktest | `contract_price_cents: contractPriceCents` (line 97) | WIRED |
| TradeRow | BacktestTrade | `trade.contracts × trade.contract_price_cents` derives cost_cents at line 43 | WIRED |

### Data-Flow Trace (Level 4)

| Artifact | Data Variable | Source | Produces Real Data | Status |
|----------|---------------|--------|--------------------|--------|
| TradeRow rows | result.trades | runBacktest(selected.data, params) at page.tsx:89–98 | yes — pure function over loaded SeasonFile | FLOWING |
| SummaryCards | result.summary | same as above | yes | FLOWING |
| Slider state | contractPriceCents | useState(97) at page.tsx:75; onChange at :216 | yes — feeds back into useMemo deps array at :100–107 | FLOWING |

### Behavioral Spot-Checks

| Behavior | Command | Result | Status |
|----------|---------|--------|--------|
| Build succeeds | `cd dashboard && pnpm build` | Compiled successfully in 6.0s; /backtest static; 0 type errors | PASS |
| fmt:check no new failures | `cd dashboard && pnpm fmt:check` | 3 pre-existing failures, modified files NOT in list | PASS |
| Lint no new errors | `cd dashboard && pnpm exec oxlint .` | 4 warnings 0 errors, all 4 in app/page.tsx (pre-existing) | PASS |
| Engine kernel correctness | `node -e` reproduction with (1000, 0.02, 97) | contracts=20, win pnl=+60, loss pnl=−1940 — matches D-14 worked example | PASS |
| D-17 zero-contract case | `node -e` reproduction with (1, 0.5, 97) | bet=50, contracts=0 | PASS |
| No source-level dangling refs | `grep -rE 'simulateMatch|DEFAULT_WIN_YIELD|avg_win_yield|avgWinYield' dashboard/app dashboard/lib cli/src src/ --include='*.ts' --include='*.tsx'` | exit 1 (no matches) | PASS |

### Requirements Coverage

| Requirement | Description | Plan | Status | Evidence |
|-------------|-------------|------|--------|----------|
| BT-06 | Contract-based P&L math; avg_win_yield input removed | 01-01-PLAN.md | closed | Engine kernel + UI swap + roadmap rewrite all shipped in 3 commits (a0281bc, eb26e23, 3494f7e); 19/19 must-haves verified |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| backtest.ts | 151 | Implicit /0 risk if contract_price_cents=0 (REVIEW.md IN-01) | INFO | Slider min=50 prevents from UI; programmatic callers unprotected. Not a Phase 1 gap — engine boundary check is a follow-up. |
| backtest.ts | 54–69 | parseScore/parseGoalTime throw uncaught (REVIEW.md IN-02) | INFO | Pre-existing; Phase 1 did not introduce or address. |
| page.tsx | 272–277 | break-even renders as "positive" (REVIEW.md IN-03) | INFO | Same convention as Gain card; cosmetic. |
| backtest.ts | 142 | Math.floor on EUR×100 silently truncates fractional cents (REVIEW.md IN-04) | INFO | Conservative ("never overstate capital"); intentional. |
| page.tsx:182–184 | trade.result tally | Zero-contract rows leak into wins/losses/matches_bet_on (REVIEW.md WR-01) | WARNING | Real semantic concern but D-17 scopes only engine, not summary. Surfaced as human_verification follow-up. |
| page.tsx:47 | bg-red-900/30 vs text-green-400 mismatch on zero-contract loss rows (REVIEW.md WR-02) | WARNING | Visual inconsistency; same root cause as WR-01. |

None of these constitute a missed must_have for Phase 1 as scoped — every locked decision (D-01..D-17) is honored. The two warnings are correctly classified as advisory by the code reviewer (status: issues_found, 0 critical) and are flagged for the developer's design decision.

### Human Verification Required

See frontmatter `human_verification`. Six items:
1. Worked-example seam (the BT-06 SC #1 manual hand-verification of the 20-contracts-@-97¢ trade row) — REQUIRED to formally close BT-06 SC #1.
2. Zero-contract render seam (D-17 visible in the row list).
3. Capital conservation seam (across many rows).
4. No-negative-capital seam (extreme-settings stress).
5. Sidebar visual regression (slot position + label rhythm + helper text wording).
6. WR-01 follow-up design decision (whether to exclude zero-contract rows from summary tallies — out of D-17 scope but a real concern raised by review).

### Gaps Summary

No gaps. All 19 must-haves verified, BT-06 closeable upon completion of human verification items 1–5 (item 6 is an explicit follow-up design decision raised by code review, not a Phase 1 gap). The phase is mathematically and structurally correct; manual visual verification is the only remaining gate before declaring BT-06 closed.

---

_Verified: 2026-04-29T21:36:00Z_
_Verifier: Claude (gsd-verifier)_
