# Phase 1: Backtest P&L Math - Research

**Researched:** 2026-04-29
**Domain:** TypeScript / dashboard backtest engine (client-side, deterministic)
**Confidence:** HIGH

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Contract-price input**

- **D-01:** New field `contract_price_cents` on `BacktestParams`, type `number` (integer cents).
- **D-02:** UI input shows integer cents directly: default `97`, range `50–99`, step `1`, label **"Contract price (cents)"**. Replaces the `avgWinYield` input in-place in the sidebar (same visual slot).
- **D-03:** Helper text below the price input reads:
  `"Yield per win: {100 − price_cents} cents per contract (€{(100 − price_cents) / 100})"`.
- **D-04:** Floor-truncation remainder is **returned to capital, not at risk**. Per fire: capital change = `+contracts × (100 − price_cents)` on win, `−contracts × price_cents` on loss. The unspent stake never leaves capital in the first place.
- **D-05:** Single fixed price per backtest run (deterministic). No per-trade randomisation, no min/max range. Same params produce the same P&L.

**Roadmap reconciliation (must be in the same phase commit)**

- **D-06:** Phase 1 success criterion #2 in `.planning/ROADMAP.md` is rewritten explicitly to:
  > "The `avg_win_yield` input is gone; a `contract_price` input (default 97, range 50–99 cents) drives the new math; existing sliders (`min_minute`, `min_lead`) remain and function."
- **D-07:** Phase 1 does **not** add `min_yes_price` / `max_yes_price` sliders. Those are Phase 2 (BT-07).

**Cents-vs-EUR units (the bigger refactor)**

- **D-08:** `runBacktest` converts EUR inputs to integer cents at function entry. All internal arithmetic is integer cents.
- **D-09:** `BacktestParams` external shape:
  - `initial_capital`: EUR float (e.g. `1000`) — UI unchanged
  - `contract_price_cents`: integer cents (e.g. `97`)
  - `bet_fraction`: float `0..1` — unchanged
  - `min_minute`, `min_lead`: integers — unchanged
- **D-10:** `BacktestTrade` money fields are **integer cents throughout**:
  - Add: `contracts: number`, `contract_price_cents: number`
  - Re-type (rename for clarity): `pnl_cents: number`, `capital_after_cents: number`
  - **Remove:** `bet_amount` — derive at render from `bet_fraction × capital_at_fire`; actual cost is `contracts × contract_price_cents`, also derived at render.
- **D-11:** `BacktestSummary` money fields become integer cents: `initial_capital_cents`, `final_capital_cents`. `gain_pct` stays float (no money unit).
- **D-12:** `page.tsx` formats every cents-typed field for display via `formatEuro(value / 100)`. No new format helper needed.

**Trade row & summary UI**

- **D-13:** Schema additions are minimal: `contracts` and `contract_price_cents` only on `BacktestTrade`. `actual_cost` / `win_profit` / `loss_amount` are NOT added — derive at render.
- **D-14:** Trade row third line reads:
  `"20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"` (verbose / labelled form).
- **D-15:** Summary cards unchanged. Keep the 7 current ones.

**Legacy cleanup**

- **D-16:** Drop the `simulateMatch` export and `DEFAULT_WIN_YIELD` constant from `backtest.ts`. Verified zero callers outside the file.

**Edge cases**

- **D-17:** When `floor(stake_cents / contract_price_cents) === 0`: write a `BacktestTrade` with `contracts = 0`, `pnl_cents = 0`, `capital_after_cents = capital_at_fire_cents` (unchanged). Visible in the trade list as a no-money row.

### Claude's Discretion

- Exact input element type (number vs slider) for `contract_price_cents`.
- Rounding mode for `bet_amount_cents = capital_at_fire_cents × bet_fraction` — pick `Math.round` unless there's a reason for `floor`.
- Whether to also rename internal local variables in `runBacktest` for clarity (`capital` → `capital_cents`, etc.).

### Deferred Ideas (OUT OF SCOPE)

- Python `src/predictions/backtest.py` contract-math update — not Phase 1.
- Unit test for `runBacktest` against a hand-calculated example — planner judgment call.
- Field rename to `yes_price_cents` — Phase 2 may revisit.
- Min/max contract-price range with per-trade sampling — rejected (loses determinism).
- Per-trade `actual_cost` / `win_profit` / `loss_amount` fields — derive at render.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| BT-06 | User backtests use contract-based P&L math: `contracts = floor(stake_cents / price_cents)`, win profit = `contracts × (100 − price_cents)`, loss = `contracts × price_cents`; the `avg_win_yield` input is removed from the backtest UI | All sections — math is the entire phase. Standard Stack confirms no new deps. Architecture Patterns section pins the `runBacktest` shape. Code Examples gives the canonical integer-cents formula. Validation Architecture proves correctness end-to-end. |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

These are binding directives extracted from `./CLAUDE.md` and `./docs/project.md`. The planner must NOT recommend approaches that contradict them.

- **Integer-cents invariant** at the Kalshi boundary (`extract_cents` in `kalshi_client.py`) — the dashboard backtest is *below* that boundary, so adoption of cents here is a **consistency** choice, not a correctness one. Worth maintaining anyway. [VERIFIED: docs/project.md, CLAUDE.md]
- **No new deps without strong reason.** This phase requires zero new packages. [VERIFIED: PROJECT.md § Constraints]
- **oxfmt 4-space indent, line width 100** (`dashboard/oxfmt.json`). [VERIFIED: dashboard/oxfmt.json]
- **`pnpm fmt:check && pnpm lint && pnpm build`** must pass before claiming done. [VERIFIED: PROJECT.md, ROADMAP.md success criterion #3]
- **No comments restating what the code says.** Only WHY-comments where non-obvious. [VERIFIED: CLAUDE.md]
- **Don't add error handling, fallbacks, or validation for cases that can't happen.** Trust types; validate at boundaries only. [VERIFIED: CLAUDE.md]
- **Functional React components, no class components.** [VERIFIED: codebase/CONVENTIONS.md]
- **No new abstractions beyond what the task requires.** Don't design for hypothetical future requirements. [VERIFIED: CLAUDE.md]

## Summary

Phase 1 replaces a single-formula proxy (`pnl = stake × yield`) with the actual Kalshi contract math (`contracts = floor(stake_cents / price_cents)`, win = `contracts × (100 − price_cents)` cents, loss = `contracts × price_cents` cents) inside `dashboard/app/backtest/backtest.ts`, swaps one sidebar input in `page.tsx`, and rewrites a roadmap success-criterion line. The schema gets two new fields (`contracts`, `contract_price_cents`); two existing money fields are renamed/retyped to cents (`pnl_cents`, `capital_after_cents`); one field (`bet_amount`) is removed and derived at render. Two dead exports (`simulateMatch`, `DEFAULT_WIN_YIELD`) are dropped — both have verified zero callers outside the file.

The phase is small (two files, ~50 lines net change) but touches every site that reads `BacktestTrade` money fields. The blast radius is limited to `dashboard/app/backtest/` (verified by repo-wide grep: `simulateMatch`, `DEFAULT_WIN_YIELD`, `avg_win_yield`, `avgWinYield` appear only in `backtest.ts` and `page.tsx`).

**Primary recommendation:** Make all internal arithmetic integer cents inside `runBacktest`. Use `Math.floor` for both the `bet_amount_cents` and `contracts` truncations (matches production scanner's `int(available_cash * (bet_percent / 100.0))` and `count = max_cost_cents // yes_price` — both are floor for non-negative values). Keep the `contract_price_cents` UI input as a `<input type="range">` slider to match `min_minute` / `min_lead`. Hand-verify success criterion #1 against the worked example in the origin todo (no Vitest install — there is no JS test infrastructure in the repo and adding it for a 50-line change is overkill).

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Contract math (`floor`, win/loss formulas) | Browser / Client (`backtest.ts`) | — | Pure function, no I/O; deterministic per D-05; runs at every input change via `useMemo` |
| Param input (sidebar UI) | Browser / Client (`page.tsx`) | — | React state hooks already own this; no server involvement |
| Trade-row rendering | Browser / Client (`page.tsx`) | — | Pure projection of `BacktestTrade` (cents) → display (€) via `formatEuro(v / 100)` |
| Season-data fetch | Browser / Client (Webpack-bundled JSON via `seasons.ts`) | — | Pre-existing; v1.1 made the page fully local; not touched by Phase 1 |
| Auth gate | Frontend Server (`actions.ts::checkAuth`) | — | Pre-existing; not touched by Phase 1 |

**Why this matters:** Every Phase 1 change lives in the browser tier. There is no API call, no server action, no DB write. The single quality gate is `pnpm fmt:check && pnpm lint && pnpm build`. [VERIFIED: dashboard/app/backtest/page.tsx contains no fetch/server-action calls; runBacktest is pure.]

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| TypeScript | 5.x (strict) | Type safety for params/trade/summary | Already in repo; strict mode catches the cents-vs-EUR confusion this phase introduces [VERIFIED: dashboard/package.json] |
| React | 19.2.3 | Hooks (useState, useMemo) for sidebar state | Already in repo; functional components only [VERIFIED: dashboard/package.json] |
| Next.js | 16.1.6 | App-router page; client component | Already in repo; backtest page is `"use client"` [VERIFIED: dashboard/app/backtest/page.tsx:1] |

### Supporting (already in use, no changes)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| Tailwind CSS | 4.x | Sidebar/trade-row styling | Existing classes — no new utilities needed |
| oxfmt | ^0.7 | Format on commit (4-space) | `pnpm fmt` before commit [VERIFIED: dashboard/oxfmt.json] |
| oxlint | ^0.16 | `no-unused-vars: warn`, `no-console: off` | `pnpm lint` before commit [VERIFIED: dashboard/oxlint.json] |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| Hand-verification of math | Vitest unit test | Cleaner regression net, but adds a dev dep (`vitest`), config (`vitest.config.ts`), and a precedent for adding TS tests piecemeal. **Rejected** for this phase — see Validation Architecture and the "Dashboard tests" Open Question. |
| `<input type="range">` slider for `contract_price_cents` | `<input type="number">` | Slider matches `min_minute` / `min_lead` UX (consistency), step=1 over 50 values is fine. Number input is finger-friendly on mobile but breaks the visual rhythm. **Recommend slider.** |

**Installation:** None. Zero new packages. [VERIFIED: dashboard/package.json — all required deps present.]

**Version verification:** Skipped. No version-sensitive APIs are introduced. The phase uses only `Number`, `Math.floor`, `Math.round`, `Array.prototype` methods — all stable across TS 4.x+.

## Architecture Patterns

### System Architecture Diagram

```
[User input in sidebar]
        │ (React state via useState)
        ↓
[BacktestParams object]   ── { initial_capital: 1000 (EUR), contract_price_cents: 97 (int), bet_fraction: 0.02, min_minute: 75, min_lead: 2 }
        │ (useMemo dependency change)
        ↓
[runBacktest()]                      ←── pure function, in backtest.ts
   ├─ initial_capital_cents = floor(initial_capital × 100)
   ├─ for each chronological match:
   │      ├─ detectFire(match, min_minute, min_lead)  ──→ FireOutcome | null
   │      └─ if fire:
   │              ├─ bet_amount_cents = floor(capital_cents × bet_fraction)
   │              ├─ contracts = floor(bet_amount_cents / contract_price_cents)
   │              ├─ if contracts === 0:  emit zero-contract row, capital unchanged
   │              ├─ else if win:         pnl_cents = +contracts × (100 − price_cents)
   │              └─ else loss:           pnl_cents = −contracts × price_cents
   │              capital_cents += pnl_cents
   │              push BacktestTrade{ contracts, contract_price_cents, pnl_cents, capital_after_cents, ... }
   ↓
[BacktestResult]   ──→  summary (cents-typed where money) + display_trades (newest-first)
        │
        ↓
[page.tsx render]
   ├─ SummaryCard:  formatEuro(initial_capital_cents / 100)  etc.
   └─ TradeRow:     "{contracts} contracts @ {price_cents}¢ · €{cost} cost · {±}€{|pnl|} · capital €{capital}"
                    where cost = contracts × contract_price_cents (derived per D-13)
```

### Recommended Project Structure

No structural change. Two files only:

```
dashboard/app/backtest/
├── backtest.ts        # ENGINE: types, detectFire (unchanged), runBacktest (rewritten)
└── page.tsx           # UI: sidebar input swap, TradeRow line 3 rewrite, SummaryCard /100
```

`seasons.ts` — untouched.

### Pattern 1: Integer-cents at function entry, EUR at boundary
**What:** Convert EUR inputs to cents on the first line of `runBacktest`. Convert cents back to EUR only in `formatEuro(value / 100)` at the JSX leaf.
**When to use:** Whenever the engine does multiplication/division on currency values that must round predictably.
**Why:** Eliminates floating-point drift across `n` trades. With float EUR, `1000.0 × 0.02 = 20.000000000000004` is possible. With ints, `100000 × 0.02 = 2000` always (the multiplication still produces a float, but `Math.floor(...)` collapses it deterministically).

```typescript
// Source: pattern derived from src/predictions/scanner.py:324
//   max_bet_cents = int(available_cash * (bet_percent / 100.0))
export function runBacktest(file: SeasonFile, params: BacktestParams): BacktestResult {
    const { min_minute, min_lead, initial_capital, bet_fraction, contract_price_cents } = params;

    const initial_capital_cents = Math.floor(initial_capital * 100);
    let capital_cents = initial_capital_cents;

    // ... main loop in cents ...

    return {
        summary: {
            // ...
            initial_capital_cents,
            final_capital_cents: capital_cents,
            gain_pct: initial_capital_cents === 0
                ? 0
                : Math.round(((capital_cents - initial_capital_cents) / initial_capital_cents) * 100 * 1e4) / 1e4,
        },
        trades: display_trades,
    };
}
```

### Pattern 2: Floor at every stake/contract truncation step
**What:** Use `Math.floor` for `bet_amount_cents` and `contracts`. Both quantities are non-negative, so `Math.floor` and `Math.trunc` are equivalent.
**Why:** Matches production scanner conventions (`int(available_cash * (bet_percent / 100.0))` at scanner.py:324; `count = max_cost_cents // yes_price` at scanner.py:134). Future maintainers reading both files will see the same shape on both sides of the Kalshi boundary.

```typescript
// Source: scanner.py:324 (Python's int() truncates toward zero; Math.floor matches for non-negative)
const bet_amount_cents = Math.floor(capital_cents * bet_fraction);
const contracts = Math.floor(bet_amount_cents / contract_price_cents);
```

### Pattern 3: Capital change is signed, not split
**What:** A single `pnl_cents` field per trade carries sign. Don't introduce parallel `win_profit` / `loss_amount` fields (D-13).
**Why:** Render-time logic already handles sign via `pnl >= 0 ? "+" : "−"` (page.tsx:43-44). Keeping it as one field reduces the number of places that have to agree on the sign convention.

### Anti-Patterns to Avoid

- **Mixing units mid-loop.** Don't store some money fields as float EUR and others as int cents. `runBacktest` should not pass EUR floats to anything except the very first line (entry conversion) and the `formatEuro(v / 100)` rendering helper at the very last leaf.
- **Adding `actual_cost` / `win_profit` / `loss_amount` to the trade schema.** Rejected in D-13. They are trivially derivable at render: `cost = contracts × contract_price_cents`, `win_profit = contracts × (100 − contract_price_cents)`, `loss_amount = contracts × contract_price_cents`. Storing them duplicates information already in `pnl_cents`.
- **Special-casing zero contracts in the schema.** D-17 says: write the row with `contracts = 0`, `pnl_cents = 0`, `capital_after_cents = capital_at_fire_cents`. Don't introduce a `result: "skip"` enum variant — keep `result: "win" | "loss"` and let the win/loss branch produce zeros naturally when contracts is zero.
- **Converting `gain_pct` to cents.** D-11 explicitly keeps it as a float — it's a percentage, not a money unit.
- **Reordering or refactoring `detectFire`.** It's pure, capital-independent, and already correct. Phase 1 wraps around it; do not modify it.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Cents → EUR display | New formatter | `formatEuro(value / 100)` (page.tsx:8) | Already handles 2-decimal locale formatting; D-12 explicitly mandates this approach |
| Sign rendering ("+" / "−") | New helper | Existing `pnlSign` / `pnlClass` ternary at page.tsx:43-44 | Already correct |
| Currency parsing of UI input | Custom parser | `Number(e.target.value)` in onChange handlers | Pattern already established at page.tsx:174 etc. |
| Test runner | Add Vitest | Hand-verify against worked example in todo | Phase is 50 lines; adding a test framework is more work than the phase itself |

**Key insight:** This phase is intentionally small. The temptation to "while we're here, add Vitest" or "rename more variables for consistency" should be resisted. The smallest diff that makes the math correct + passes the gate is the right diff.

## Runtime State Inventory

> Skipped. This is not a rename/refactor/migration phase. There is no stored state, no service config, no OS-registered task tied to the schema field names being renamed. The renames (`bet_amount` removed; `pnl` → `pnl_cents`; `capital_after` → `capital_after_cents`; `initial_capital` / `final_capital` → `_cents` variants) are confined to in-memory TypeScript types. No DB columns, no JSON serialization, no localStorage, no URL params reference these names. [VERIFIED via grep on the repo for each renamed field.]

## Common Pitfalls

### Pitfall 1: Float multiplication of `capital_cents × bet_fraction`
**What goes wrong:** `Math.floor(2000 * 0.001)` is `1`, but `Math.floor(2000 * 0.1 * 0.01)` could be `1` or `2` depending on float rounding before the floor.
**Why it happens:** `bet_fraction` is `betFractionPct / 100` in page.tsx:94 — already one division step away from int. Compounding multiplications can drift.
**How to avoid:** Compute `bet_amount_cents` in one step: `Math.floor(capital_cents * bet_fraction)`. Don't break it into intermediate floats.
**Warning signs:** Slight discrepancies between hand calculation and engine output that disappear when the bet_fraction is a "clean" decimal like 0.5 or 0.25.

### Pitfall 2: `formatEuro(value / 100)` on negative cents
**What goes wrong:** `formatEuro(-60 / 100)` = `formatEuro(-0.6)` = `"-0.60"` (locale-dependent: could be `"-0,60"` or with parentheses, depending on locale).
**Why it happens:** `toLocaleString` with `undefined` locale honors browser/OS locale. The existing TradeRow code at page.tsx:43-44 already separates the sign from the magnitude with `pnlSign` and `Math.abs(trade.pnl)`. **The same pattern must be preserved post-rename**: render `pnlSign` separately, then `formatEuro(Math.abs(pnl_cents) / 100)`.
**How to avoid:** Keep the existing sign-stripping pattern. Do not pass negative values to `formatEuro`.
**Warning signs:** UI shows `"-€-0.60"` or `"+€-0.60"` for losses.

### Pitfall 3: Trailing-zero formatting of integer cents
**What goes wrong:** `formatEuro(60 / 100)` = `formatEuro(0.6)` = `"0.60"`. Looks fine. But `formatEuro(1940 / 100)` = `"19.40"` — also fine. `formatEuro(100060 / 100)` = `formatEuro(1000.6)` = `"1,000.60"`. Also fine.
**Why it's a non-issue:** `toLocaleString` with `minimumFractionDigits: 2, maximumFractionDigits: 2` always produces exactly 2 decimal places. There is no "trailing zero is dropped" failure mode.
**Warning signs:** None — this is here only because the upstream brief flagged it as a concern. Verified safe.

### Pitfall 4: Negative or zero `capital_at_fire_cents` mid-run
**What goes wrong:** A long losing streak drains capital below the cost of one contract, then below zero.
**Why it happens:** D-04 keeps unspent stake remainder in capital, so capital can only shrink by `contracts × price_cents` per loss. But if `capital_cents` goes below `contract_price_cents`, then `bet_amount_cents = floor(capital_cents × bet_fraction)` shrinks too, and `contracts = floor(bet_amount_cents / price_cents)` becomes 0 — which D-17 already handles. **Capital can drop to a small positive value but cannot easily go negative** unless `bet_fraction = 1.0` and one full loss takes all capital, after which the next fire produces `bet_amount_cents = 0` → `contracts = 0` → no further loss.
**How to avoid:** Trust the D-17 zero-contract case. No additional guard is needed. **Verify with a Validation Architecture seam (see below): no `BacktestTrade` should have `capital_after_cents < 0` for any reasonable input combo.**
**Warning signs:** A trade row with negative `capital_after_cents`. Should not occur with the D-04 + D-17 contract.

### Pitfall 5: `simulateMatch` removal breaking an external import
**What goes wrong:** Some script outside the repo imports `simulateMatch`.
**Why it's a non-issue:** Verified via repo-wide grep on `*.ts`/`*.tsx`: zero callers outside `backtest.ts` itself. The function was added as a "back-compat alias" (per its own comment at backtest.ts:127) but no caller materialized.
**Warning signs:** If `pnpm build` fails on `simulateMatch is not exported`, search for the importer and either delete the importer or restore the export. Per the verified grep, this is not expected.

## Code Examples

### Canonical contract-math kernel (the entire BT-06 formula)

```typescript
// Source: REQUIREMENTS.md § BT-06; CONTEXT.md D-04, D-08, D-10, D-17
// Style: integer cents throughout; floor truncation matches scanner.py:324, scanner.py:134
const bet_amount_cents = Math.floor(capital_cents * bet_fraction);
const contracts = Math.floor(bet_amount_cents / contract_price_cents);

let pnl_cents: number;
if (contracts === 0) {
    // D-17: emit zero-contract row, no capital change
    pnl_cents = 0;
} else if (fire.result === "win") {
    pnl_cents = contracts * (100 - contract_price_cents);
} else {
    pnl_cents = -contracts * contract_price_cents;
}
capital_cents += pnl_cents;
```

### TradeRow third line (per D-14)

```typescript
// Source: CONTEXT.md D-14, D-12
// "20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"
const cost_cents = trade.contracts * trade.contract_price_cents;
const pnlSign = trade.pnl_cents >= 0 ? "+" : "−";
const pnlClass = trade.pnl_cents >= 0 ? "text-green-400" : "text-red-400";

<div className="text-xs text-gray-300 mt-1">
    {trade.contracts} contracts @ {trade.contract_price_cents}¢ ·
    €{formatEuro(cost_cents / 100)} cost ·{" "}
    <span className={pnlClass}>
        {pnlSign}€{formatEuro(Math.abs(trade.pnl_cents) / 100)}
    </span>{" "}
    · capital €{formatEuro(trade.capital_after_cents / 100)}
</div>
```

### Sidebar input replacement (per D-02, D-03)

```typescript
// Source: CONTEXT.md D-02, D-03; matches the visual rhythm of min_minute/min_lead sliders above it
const [contractPriceCents, setContractPriceCents] = useState(97);

<div>
    <label className="block text-sm text-gray-300 mb-1">
        Contract price (cents): {contractPriceCents}
    </label>
    <input
        type="range"
        min={50}
        max={99}
        step={1}
        value={contractPriceCents}
        onChange={(e) => setContractPriceCents(Number(e.target.value))}
        className="w-full"
    />
    <p className="text-xs text-gray-500 mt-1">
        Yield per win: {100 - contractPriceCents} cents per contract
        (€{formatEuro((100 - contractPriceCents) / 100)})
    </p>
</div>
```

## State of the Art

This is a self-contained math change. There is no "ecosystem state of the art" to track. The relevant convention check:

| Old Approach (in-repo) | Current Approach (in-repo, post-Phase-1) | Why |
|------------------------|-------------------------------------------|-----|
| `pnl = stake × yield` (float EUR) | `pnl_cents = ±contracts × (100 − price_cents)` or `±contracts × price_cents` (int cents) | Matches actual Kalshi market mechanic; matches `src/predictions/scanner.py` and BT-06 |
| `simulateMatch` back-compat alias | Removed | Zero callers, not load-bearing |
| `DEFAULT_WIN_YIELD` constant | Removed | Only consumer was `avgWinYield` state, also removed |

**Deprecated/outdated:** None upstream. Within the repo, `avg_win_yield` is the only deprecated concept and Phase 1 removes it.

## Discretion Recommendations

The CONTEXT.md "Claude's Discretion" items, with my recommendations and reasoning:

### 1. Rounding mode for `bet_amount_cents`

**Recommendation: `Math.floor`.**

**Reasoning:** Production scanner uses `int(available_cash * (bet_percent / 100.0))` at `src/predictions/scanner.py:324` [VERIFIED]. Python's `int()` truncates toward zero; for non-negative `available_cash` this is equivalent to `Math.floor`. Matching this convention means a future reviewer reading both the backtest engine and the scanner will see the same arithmetic shape across the boundary. The CONTEXT brief defaults to `Math.round` "unless there's a reason for floor" — the reason is the parallel with production. Using floor here also prevents the edge case where `Math.round(capital_cents × bet_fraction)` rounds up to a value greater than the floor of the same expression, then `floor(bet_amount_cents / price_cents)` floors back down — same contract count either way for typical inputs, but the consistent flooring removes one edge-case mental hop.

### 2. Input element type for `contract_price_cents`

**Recommendation: `<input type="range">` slider, step=1, range 50–99.**

**Reasoning:** The sidebar already uses sliders for `min_minute` (range 1–90) and `min_lead` (range 1–5). Visual consistency wins. The range 50–99 is 50 discrete steps; a slider with `step=1` over 50 values is comfortable on desktop (the only target — no mobile dashboard) and matches the existing `min_minute` slider's 90-step range. The label-with-current-value pattern (`"Min minute: {minMinute}"`) is already established and works for cents the same way: `"Contract price (cents): {contractPriceCents}"`.

The number-input alternative is acceptable per D-02 but breaks the visual rhythm of the sidebar. Number inputs are also more error-prone (users can type values outside the validated range, requiring more `onChange` clamping logic — see existing `setBetFractionPct` clamp at page.tsx:189-193).

### 3. Internal variable renames in `runBacktest`

**Recommendation: Yes, rename for clarity.**

`capital` → `capital_cents`, `bet_amount` → `bet_amount_cents`, `pnl` → `pnl_cents`, `final_capital` → `final_capital_cents`.

**Reasoning:** The function is small enough that doing both the type rename (locked by D-10/D-11) and the local-variable rename in one commit is cleaner than two passes. With external types renamed and internal variables un-renamed, a reader of the function body would see `capital` and have to remember "this is cents because of the function-entry conversion" rather than reading it in the variable name. Cost is ~10 lines of mechanical rename within a function the phase is already rewriting end-to-end.

### 4. Verification approach for ROADMAP success criterion #1

**Recommendation: Hand-verification, not Vitest.**

**Reasoning:** There is no JavaScript test infrastructure in the repo today (`tests/` is pytest only; `dashboard/package.json` has no `test` script and no Vitest/Jest dep) [VERIFIED]. Adding Vitest for a 50-line phase introduces:
- A new dev dependency (Vitest)
- A config file (`vitest.config.ts` or extension to `next.config.ts`)
- A precedent: now every future TS change can be asked "where's the test?", which is fine eventually but should be a dedicated decision, not a side-effect of Phase 1.

The ROADMAP success criterion already says **"verifiable by checking output against manual calculation for one match"** — i.e., the criterion was written assuming hand-verification. The origin todo file (`.planning/todos/pending/2026-04-29-backtest-contract-based-pnl.md`) provides the worked example: `floor(20 / 0.97) = 20 contracts`, win = 0.60 EUR, loss = 19.40 EUR, remainder = 0.60 EUR returned to capital. The Validation Architecture below pins this as a checklist item the executor performs once at the end of the phase.

If a future phase decides to add Vitest, this manual-verification step transcribes trivially into a unit test. **Defer the framework decision; do the math correctly now.**

## Validation Architecture

> Required because workflow.nyquist_validation defaults to enabled (no `.planning/config.json` present).

### Test Framework
| Property | Value |
|----------|-------|
| Framework | None (no JS test infra in repo) |
| Config file | none — see Wave 0 |
| Quick run command | `cd dashboard && pnpm fmt:check && pnpm lint && pnpm build` |
| Full suite command | `cd dashboard && pnpm fmt:check && pnpm lint && pnpm build` (same — there is no separate test step) |

### Phase Requirements → Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| BT-06 | The build compiles after the schema rename (proves no stale references to `bet_amount`, `pnl`, `capital_after`, `avg_win_yield`, `DEFAULT_WIN_YIELD`, `simulateMatch`) | smoke (typecheck via `next build`) | `cd dashboard && pnpm build` | ✅ |
| BT-06 | The lint passes (no unused-var warnings on removed identifiers) | static | `cd dashboard && pnpm lint` | ✅ |
| BT-06 | Format check passes (4-space, line width 100) | static | `cd dashboard && pnpm fmt:check` | ✅ |
| BT-06 | Worked example matches output: with `initial_capital=1000`, `bet_fraction=0.02`, `contract_price_cents=97`, a winning fire produces `contracts=20`, `pnl_cents=+60`, `capital_after_cents=100060` | manual | open page in browser, configure params, find any winning trade, verify the row reads `"20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"` | manual |
| BT-06 | Zero-contract case (D-17): with `initial_capital=1`, `bet_fraction=0.5`, `contract_price_cents=97`, a fire produces `contracts=0`, `pnl_cents=0`, `capital_after_cents=100` (1 EUR = 100 cents, unchanged) | manual | open page, set those params, verify a zero-contract row appears with capital unchanged | manual |
| BT-06 | Sum-of-pnls equals final − initial: across all trades in the result, `Σ pnl_cents === final_capital_cents − initial_capital_cents` | manual | open browser DevTools, run on the in-memory `result.trades`: `result.trades.reduce((s, t) => s + t.pnl_cents, 0) === result.summary.final_capital_cents - result.summary.initial_capital_cents` | manual |
| BT-06 (D-06) | Roadmap criterion #2 rewritten | static (grep) | `grep -F 'a contract_price input (default 97, range 50–99 cents)' .planning/ROADMAP.md` | ✅ (existing roadmap file) |
| BT-06 (D-16) | Dead exports removed | static (grep) | `! grep -E 'simulateMatch\|DEFAULT_WIN_YIELD' dashboard/app/backtest/backtest.ts` | ✅ |
| BT-06 (D-16) | UI input gone | static (grep) | `! grep -E 'avgWinYield\|avg_win_yield' dashboard/app/backtest/page.tsx` | ✅ |

### Validation Seams (observable behaviors that prove correctness)

These are the seams the planner should reflect in `VALIDATION.md` as the executor's verification checklist:

1. **Build seam:** `pnpm build` succeeds. Type errors at the schema rename catch any missed call site automatically.
2. **Worked-example seam:** One winning trade in the trade list reads exactly the D-14 string for the canonical params (1000 EUR / 2% / 97¢).
3. **Zero-contract seam:** With params that floor to 0 contracts, a row appears with `0 contracts`, `+€0.00` (or `−€0.00` — sign doesn't matter for zero), and capital unchanged from the previous row.
4. **Capital conservation seam:** Σ `pnl_cents` over all displayed trades equals `final_capital_cents − initial_capital_cents`. (The display order is newest-first; the order doesn't affect the sum.) This is the strongest end-to-end check that the cents arithmetic is consistent.
5. **No-negative-capital seam:** No `BacktestTrade` has `capital_after_cents < 0` for any reasonable input. The D-04 floor-remainder behavior plus D-17 zero-contract handling should make this naturally true.
6. **Roadmap-coupling seam:** The ROADMAP success criterion #2 rewrite (D-06) lands in the same commit as the code change. Without this, the roadmap and the code drift.
7. **Dead-code seam:** `simulateMatch` and `DEFAULT_WIN_YIELD` are gone from `backtest.ts`. `avgWinYield` state is gone from `page.tsx`. `oxlint` `no-unused-vars: warn` would have flagged these but is `warn` not `error`, so an explicit grep catches them.

### Sampling Rate
- **Per task commit:** `cd dashboard && pnpm fmt:check && pnpm lint && pnpm build`
- **Per wave merge:** Same command (no separate full suite — phase has no unit tests).
- **Phase gate:** Same command + the manual seams (1, 2, 3, 4, 5) verified once in the browser.

### Wave 0 Gaps
- None — there is no test infrastructure to add. The "Wave 0" for this phase is the build/lint/fmt gate that already exists. **No Vitest install is recommended** (see Discretion Recommendations § 4).

## Environment Availability

> Skipped. This phase depends only on tools already present in the dev environment (`pnpm`, `oxfmt`, `oxlint`, `next build`). No external service, no new CLI tool, no runtime dependency outside what `dashboard/package.json` already declares. The `pnpm` workspace command is exercised on every dev session per `pnpm dev:dashboard`. No availability audit needed.

## Security Domain

> Required because `security_enforcement` defaults to enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Phase touches no auth surface; existing `checkAuth` gate at `dashboard/app/backtest/page.tsx:75-79` is unchanged |
| V3 Session Management | no | No session changes |
| V4 Access Control | no | Page-level access already enforced upstream by `checkAuth` |
| V5 Input Validation | yes (light) | Sidebar inputs are clamped (existing pattern at page.tsx:174, 189-193); the new `contract_price_cents` slider has range/step in the input element itself, so out-of-range values cannot be entered via the slider UI. No string parsing, no SQL, no shell. |
| V6 Cryptography | no | No crypto in this phase |

### Known Threat Patterns for {Next.js client-side computation}

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Untrusted user input feeding `Math.floor` etc. | Tampering | The inputs are local-only React state; an attacker who controls these inputs is the user themselves on their own browser. No server trust boundary is crossed. **No mitigation needed beyond the slider's `min`/`max`/`step` attributes.** |
| `dangerouslySetInnerHTML` on trade row | XSS | Not used. `TradeRow` renders only number/string interpolations through React's auto-escaped JSX. **No risk.** |
| Auth bypass | Spoofing | `checkAuth` server action is unchanged. Phase does not touch the auth gate. |

**Net:** Phase 1 has no meaningful security surface. The math runs in the user's browser on data the user already has access to.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| (none) | All claims in this research were either verified by direct file reads, repo-wide greps, or cited from CONTEXT.md/REQUIREMENTS.md/ROADMAP.md/PROJECT.md/CLAUDE.md/scanner.py. | — | — |

**No user confirmation needed.** Every recommendation is grounded in either the locked CONTEXT.md decisions or in verified repo conventions.

## Open Questions

1. **Whether to add Vitest in a future phase**
   - What we know: No JS test infra exists today. ROADMAP success criterion #1 explicitly says "manual calculation" — designed for hand-verification.
   - What's unclear: Whether the team wants to install Vitest at some point (e.g. before Phase 2 introduces YAML-driven strategies that warrant unit tests).
   - Recommendation: Defer. Don't bundle a test-framework decision into a 50-line math phase. Revisit in Phase 2 retrospective if useful.

2. **Whether `Math.floor(initial_capital * 100)` ever matters in practice**
   - What we know: The UI input forces `initial_capital` to integer EUR values (`min={1} step={1}` at page.tsx:170-171). So `initial_capital * 100` is always already integer.
   - What's unclear: Nothing — `Math.floor` is a no-op here for the UI-driven case but defensive against a future programmatic caller passing a float.
   - Recommendation: Keep the `Math.floor` on entry. Cost is zero; it documents intent.

## Sources

### Primary (HIGH confidence)
- `.planning/phases/01-backtest-p-l-math/01-CONTEXT.md` — locked decisions D-01..D-17
- `.planning/REQUIREMENTS.md` — BT-06 canonical formula
- `.planning/ROADMAP.md` — Phase 1 success criteria (criterion #2 to be rewritten per D-06)
- `.planning/PROJECT.md` — milestone constraints, no-new-deps, oxfmt 4-space
- `dashboard/app/backtest/backtest.ts` — current 224-line engine (read end-to-end)
- `dashboard/app/backtest/page.tsx` — current 303-line UI (read end-to-end)
- `dashboard/oxfmt.json`, `dashboard/oxlint.json` — formatter & linter
- `dashboard/package.json` — verified deps; no Vitest/Jest, no `test` script
- `src/predictions/scanner.py` — verified `int(available_cash * (bet_percent / 100.0))` at line 324 and `count = max_cost_cents // yes_price` at line 134, establishing the "floor for stake and contract counts" repo convention
- `CLAUDE.md`, `docs/project.md` — integer-cents invariant at the Kalshi boundary, no-comments-restating-code, functional-components-only
- Repo-wide grep `simulateMatch | DEFAULT_WIN_YIELD | avg_win_yield | avgWinYield` over `*.ts`/`*.tsx` — confirms zero callers outside `dashboard/app/backtest/`

### Secondary (MEDIUM confidence)
- None — every claim has a primary source.

### Tertiary (LOW confidence)
- None.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — read directly from `dashboard/package.json`
- Architecture: HIGH — derived from D-01..D-17 (locked) and the existing engine code
- Pitfalls: HIGH — derived from `Math.floor` semantics, D-04/D-17 contract behavior, and the existing TradeRow sign-stripping pattern
- Discretion recommendations: HIGH — grounded in production scanner conventions (`src/predictions/scanner.py`) for rounding; grounded in existing UI patterns for slider vs number; grounded in repo state for Vitest decision
- Validation architecture: HIGH — every seam corresponds to either a runnable command or a hand-verifiable observation against the worked example

**Research date:** 2026-04-29
**Valid until:** 2026-05-29 (30 days; the phase is small and the surrounding stack is stable)
