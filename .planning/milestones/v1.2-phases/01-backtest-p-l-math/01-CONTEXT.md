# Phase 1: Backtest P&L Math - Context

**Gathered:** 2026-04-29
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace the `avg_win_yield` proxy in the dashboard backtest engine with real
contract-based P&L math: `contracts = floor(stake / price)`, win profit =
`contracts × (100 − price_cents)`, loss = `contracts × price_cents`.

**In scope (Phase 1):**

- `dashboard/app/backtest/backtest.ts` — math, types, helpers
- `dashboard/app/backtest/page.tsx` — sidebar input swap, trade row format
- `.planning/ROADMAP.md` — rewrite Phase 1 success criterion #2 (it currently
  references `min_yes_price` / `max_yes_price` sliders that don't exist yet)

**Out of scope (deferred to later phases):**

- `src/predictions/backtest.py` (Python REST endpoint) — not a Phase 1 target
- `min_yes_price` / `max_yes_price` sliders — Phase 2 (BT-07)
- Strategy YAML, scanner, analytics dashboard — Phases 2–4
- Real-money trading (milestone is dry-run only)

</domain>

<decisions>
## Implementation Decisions

### Contract-price input

- **D-01:** New field `contract_price_cents` on `BacktestParams`, type `number`
  (integer cents).
- **D-02:** UI input shows integer cents directly: default `97`, range `50–99`,
  step `1`, label **"Contract price (cents)"**. Replaces the `avgWinYield`
  input in-place in the sidebar (same visual slot).
- **D-03:** Helper text below the price input reads:
  `"Yield per win: {100 − price_cents} cents per contract (€{(100 − price_cents) / 100})"`.
- **D-04:** Floor-truncation remainder is **returned to capital, not at
  risk**. Per fire: capital change = `+contracts × (100 − price_cents)` on
  win, `−contracts × price_cents` on loss. The unspent stake never leaves
  capital in the first place.
- **D-05:** Single fixed price per backtest run (deterministic). No per-trade
  randomisation, no min/max range. Same params produce the same P&L.

### Roadmap reconciliation (must be in the same phase commit)

- **D-06:** Phase 1 success criterion #2 in `.planning/ROADMAP.md` is
  rewritten explicitly to:
  > "The `avg_win_yield` input is gone; a `contract_price` input (default
  > 97, range 50–99 cents) drives the new math; existing sliders
  > (`min_minute`, `min_lead`) remain and function."
- **D-07:** Phase 1 does **not** add `min_yes_price` / `max_yes_price`
  sliders. Those are Phase 2 (BT-07) and arrive with the strategy engine.

### Cents-vs-EUR units (the bigger refactor)

- **D-08:** `runBacktest` converts EUR inputs to integer cents at function
  entry. All internal arithmetic is integer cents.
- **D-09:** `BacktestParams` external shape:
  - `initial_capital`: EUR float (e.g. `1000`) — UI unchanged
  - `contract_price_cents`: integer cents (e.g. `97`)
  - `bet_fraction`: float `0..1` — unchanged
  - `min_minute`, `min_lead`: integers — unchanged
- **D-10:** `BacktestTrade` money fields are **integer cents throughout**:
  - Add: `contracts: number`, `contract_price_cents: number`
  - Re-type (rename for clarity): `pnl_cents: number`,
    `capital_after_cents: number`
  - **Remove:** `bet_amount` (intended-stake field) — derive at render time
    from `bet_fraction × capital_at_fire`; actual cost is
    `contracts × contract_price_cents`, also derived at render
- **D-11:** `BacktestSummary` money fields become integer cents:
  `initial_capital_cents`, `final_capital_cents`. `gain_pct` stays float
  (no money unit).
- **D-12:** `page.tsx` formats every cents-typed field for display via
  `formatEuro(value / 100)`. No new format helper needed.

### Trade row & summary UI

- **D-13:** Schema additions are minimal: `contracts` and
  `contract_price_cents` only on `BacktestTrade`. `actual_cost`,
  `win_profit`, `loss_amount` from the original todo are NOT added — they
  are trivially derivable in render and would just duplicate `pnl_cents`.
- **D-14:** Trade row third line reads:
  `"20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"`
  (verbose / labelled form, not the compact `20×97¢` form).
- **D-15:** Summary cards unchanged. Keep the 7 current ones (Scanned, Bet
  on, Wins, Losses, Win rate, Final capital, Gain).

### Legacy cleanup

- **D-16:** Drop the `simulateMatch` export and `DEFAULT_WIN_YIELD` constant
  from `backtest.ts`. `simulateMatch` has zero callers in the workspace
  (verified via grep on `*.ts`/`*.tsx`); `DEFAULT_WIN_YIELD` is only used by
  the `avgWinYield` state in `page.tsx`, which is being deleted with this
  phase.

### Edge cases

- **D-17:** When `floor(stake_cents / contract_price_cents) === 0` (capital
  too low or bet_fraction too small for even one contract): write a
  `BacktestTrade` with `contracts = 0`, `pnl_cents = 0`,
  `capital_after_cents = capital_at_fire_cents` (unchanged). Visible in the
  trade list as a no-money row. Helps debug strategy fire counts vs actual
  bets placed.

### Claude's Discretion

- Exact input element type (number vs slider) for `contract_price_cents` —
  match the existing `min_minute` / `min_lead` slider feel where reasonable;
  number input is acceptable if the slider UX is awkward at step=1 over
  50 values.
- Rounding mode for `bet_amount_cents = capital_at_fire_cents × bet_fraction`
  — pick `Math.round` unless there's a reason for `floor` (the floor is
  applied at the contract calculation, not at the stake step).
- Whether to also rename internal local variables in `runBacktest` for
  clarity (`capital` → `capital_cents`, etc.).

</decisions>

<specifics>
## Specific Ideas

- The contract-math intent is described in the original todo file with a
  concrete worked example (`floor(20 / 0.97) = 20 contracts`, win 0.60 EUR,
  loss 19.40 EUR, remainder 0.60 EUR returned). Honour that example as the
  hand-verifiable test for success criterion #1.
- The integer-cents invariant from CLAUDE.md applies to the production-code
  Kalshi boundary; the dashboard backtest does not cross that boundary, so
  this phase's adoption of cents is a *consistency* choice, not a
  correctness one. Worth maintaining anyway: future code review of this
  module is faster when the convention is the same as the rest of the repo.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before acting.**

### Phase scope and acceptance

- `.planning/ROADMAP.md` § Phase 1 — phase goal, depends-on, success
  criteria. Note: success criterion #2 will be rewritten in this phase per
  D-06.
- `.planning/REQUIREMENTS.md` § BT-06 — canonical formula in integer cents
  (`contracts = floor(stake_cents / price_cents)`, win =
  `contracts × (100 − price_cents)`, loss = `contracts × price_cents`)
- `.planning/PROJECT.md` § Active / Constraints / Key Decisions — milestone
  context, integer-cents invariant, no-new-deps rule, oxfmt 4-space indent,
  `pnpm fmt:check && pnpm lint && pnpm build` gate

### Code conventions

- `.planning/codebase/CONVENTIONS.md` § TypeScript — oxfmt/oxlint config,
  server-side proxy pattern, functional components, Recharts. Style is
  enforced; defer to the linters.
- `.planning/codebase/STRUCTURE.md` — repo layout (relevant: `dashboard/`)
- `dashboard/oxfmt.json`, `dashboard/oxlint.json` — formatter & linter
  config files (4-space indent, line width 100)

### Origin of the rework

- `.planning/todos/pending/2026-04-29-backtest-contract-based-pnl.md` —
  original problem statement and worked example. Note: the original todo
  proposes additional `BacktestTrade` fields (`actual_cost`, `win_profit`,
  `loss_amount`) that this CONTEXT supersedes — see D-13. The math intent
  is honoured; the schema shape is leaner.

### Edit targets

- `dashboard/app/backtest/backtest.ts` — engine: types, helpers,
  `runBacktest`, `detectFire`, `simulateMatch` (to be removed)
- `dashboard/app/backtest/page.tsx` — sidebar input swap, trade row
  format, summary card formatting

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- **`detectFire(match, min_minute, min_lead)`** in `backtest.ts:90` — pure
  function, capital-independent. Phase 1 does **not** change it; the
  contract math wraps around it in `runBacktest`. Reuse as-is.
- **`formatEuro(value)`** in `page.tsx:8` — existing 2-decimal EUR
  formatter. Combine with `value / 100` to render cents-typed fields.
- **`SummaryCard`** and **`TradeRow`** components in `page.tsx` — keep the
  same component shape; only the internal text content changes.

### Established patterns

- **Two stacks, one repo:** dashboard backtest is fully client-side TS
  (Phase 1 scope). Backend Python `src/predictions/backtest.py` exists but
  is unused by the dashboard since v1.1 made the page local-JSON only —
  out of Phase 1 scope.
- **Integer cents at the Kalshi boundary** (`src/predictions/kalshi_client.py`
  `extract_cents`/`extract_volume`). The dashboard backtest is below that
  boundary; integer cents here is for *consistency*, not invariant
  enforcement.
- **No tests for the dashboard backtest module today** — `tests/` has only
  Python scripts. Adding a TS unit test for `runBacktest`'s new math is
  optional and a planner judgment call (raised but not selected during
  discussion).

### Integration points

- **`dashboard/app/backtest/page.tsx:73`** — `useState(DEFAULT_WIN_YIELD)`
  must become `useState(97)`; the param key sent to `runBacktest` changes
  from `avg_win_yield` to `contract_price_cents`.
- **`dashboard/app/backtest/page.tsx:218–221`** — helper text block updates
  per D-03.
- **`dashboard/app/backtest/page.tsx:55–60`** — `TradeRow` line 3 layout
  updates per D-14; uses `value / 100` formatting per D-12.

</code_context>

<deferred>
## Deferred Ideas

- **Python `src/predictions/backtest.py` contract-math update** — raised but
  not selected. The Python REST endpoint (`/api/backtest/soccer`) was
  preserved in v1.1 "for future CLI/scripts use" but isn't called from the
  dashboard. If/when it gets reused, it should adopt the same math.
- **Unit test for `runBacktest` against a hand-calculated example** —
  raised but not selected. Success criterion #1 specifies "verifiable by
  checking output against manual calculation for one match"; planner can
  decide whether to formalise this as a Vitest/Jest test or leave it as a
  manual verification step.
- **Field rename to `yes_price_cents`** — considered for Kalshi-vocabulary
  alignment with Phase 2 (BT-07's `min_yes_price` / `max_yes_price`).
  Rejected for Phase 1 because `contract_price` and `yes_price` play
  different semantic roles (price-paid vs. filter-bound). Phase 2 may
  revisit when wiring strategy presets.
- **Min/max contract-price range with per-trade sampling** — considered
  and rejected for Phase 1 (loses determinism). Could be revisited if
  Phase 4 analytics show the assumption "price is constant across trades"
  produces misleading results.
- **Per-trade actual_cost / win_profit / loss_amount fields on
  `BacktestTrade`** — considered (matches the original todo) and rejected
  in D-13. Derive at render instead of bloating the schema.

</deferred>

---

*Phase: 01-backtest-p-l-math*
*Context gathered: 2026-04-29*
