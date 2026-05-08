# Phase 1: Backtest P&L Math - Pattern Map

**Mapped:** 2026-04-29
**Files analyzed:** 3 (all in-place modifications)
**Analogs found:** 3 / 3 (every analog is in-file)

## Phase shape

This phase modifies three existing files in-place. There are no genuinely new
files. Every "analog" is a span of code in the same file the planner is going
to edit. The planner should reference these line ranges as the patterns to
extend, not as patterns to copy from elsewhere.

## File Classification

| Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---------------|------|-----------|----------------|---------------|
| `dashboard/app/backtest/backtest.ts` | engine (pure module: types + transform) | request-response (params → result, sync) | the file itself, `runBacktest` block | exact (in-place rewrite of same function) |
| `dashboard/app/backtest/page.tsx` | component (client React page) | request-response (UI state → useMemo → JSX) | same file, `min_minute` / `min_lead` slider blocks | exact (extend established slider rhythm) |
| `.planning/ROADMAP.md` | doc | text | the file itself, success-criterion line | exact (one-line rewrite) |

## Pattern Assignments

### `dashboard/app/backtest/backtest.ts` (engine, transform)

**Analog:** the file itself. Everything the planner needs is already in this
file. The phase rewrites internal arithmetic and renames type fields.

#### Imports pattern (line 1)

```typescript
import type { Match, SeasonFile } from "./seasons";
```

Single type-only import from the local `seasons` module. No new imports
needed for the phase — `Math.floor` is global. Keep the import block as-is.

#### Existing `BacktestParams` shape (lines 5–11) — to be modified

```typescript
export interface BacktestParams {
  min_minute: number;
  min_lead: number;
  initial_capital: number;
  bet_fraction: number; // 0..1, fraction of current capital staked per bet
  avg_win_yield: number; // EUR returned per 1 EUR staked on a winning bet (e.g. 0.03)
}
```

**Mutation per D-01, D-09:** drop `avg_win_yield`, add
`contract_price_cents: number`. Keep `initial_capital` as EUR float (UI is
unchanged), keep `bet_fraction` as `0..1` float, keep `min_minute` /
`min_lead` as integers.

#### Existing `BacktestTrade` shape (lines 13–28) — to be modified

```typescript
export interface BacktestTrade {
  match_id: string;
  date: string;
  home_team: string;
  away_team: string;
  final_home: number;
  final_away: number;
  fired_at_minute: number;
  score_at_fire_home: number;
  score_at_fire_away: number;
  leading_side: "home" | "away";
  result: "win" | "loss";
  bet_amount: number;
  pnl: number;
  capital_after: number;
}
```

**Mutation per D-10:** remove `bet_amount` (line 25). Rename `pnl` → `pnl_cents`,
`capital_after` → `capital_after_cents`. Add `contracts: number` and
`contract_price_cents: number`. Keep all non-money fields untouched.

#### Existing `BacktestSummary` shape (lines 30–39) — to be modified

```typescript
export interface BacktestSummary {
  matches_scanned: number;
  matches_bet_on: number;
  wins: number;
  losses: number;
  win_rate: number; // 0..1, 4 decimal places
  initial_capital: number;
  final_capital: number;
  gain_pct: number; // (final − initial) / initial * 100
}
```

**Mutation per D-11:** rename `initial_capital` → `initial_capital_cents`,
`final_capital` → `final_capital_cents`. Keep `gain_pct` as float (it's a
percentage, not money). `wins` / `losses` / `win_rate` / `matches_*` are
untouched.

#### Constant to delete (line 48)

```typescript
export const DEFAULT_WIN_YIELD = 0.03;
```

**Mutation per D-16:** delete. Verified zero callers outside `page.tsx` (which
also stops importing it in this phase).

#### Helpers to keep as-is (lines 52–74)

```typescript
export function parseGoalTime(time: string): { minute: number; stoppage: number; } { ... }
export function parseScore(score: string): { home: number; away: number } { ... }
```

Untouched. Pure parsers, no money types.

#### `detectFire` to keep as-is (lines 78–125)

The `FireOutcome` interface (lines 78–87) and the `detectFire` function
(lines 90–125) are pure, capital-independent, and already correct. Per the
research file's anti-patterns list and CONTEXT.md "Reusable assets" callout,
**do not modify `detectFire`**. The contract math wraps around it in
`runBacktest`.

#### `simulateMatch` to delete (lines 127–148)

```typescript
// Back-compat alias: legacy callers used `simulateMatch` and expected a trade-shaped
// object without monetary fields. Tests/scripts may still depend on the name.
export function simulateMatch(
  match: Match,
  params: { min_minute: number; min_lead: number },
): Omit<BacktestTrade, "bet_amount" | "pnl" | "capital_after"> | null {
  ...
}
```

**Mutation per D-16:** delete entire export (lines 127–148 inclusive).
Verified zero callers via repo-wide grep.

#### `runBacktest` core pattern (lines 150–223) — to be rewritten

**Existing structure** (the shape to preserve):

```typescript
export function runBacktest(
  file: SeasonFile,
  params: BacktestParams,
): BacktestResult {
  const { min_minute, min_lead, initial_capital, bet_fraction, avg_win_yield } =
    params;

  // Walk matches chronologically (oldest first) so capital accumulates in time order.
  // YYYY-MM-DD strings are lexicographically sortable.
  const chronological = [...file.matches].sort((a, b) =>
    a.date.localeCompare(b.date),
  );

  const trades: BacktestTrade[] = [];
  let capital = initial_capital;

  for (const match of chronological) {
    const fire = detectFire(match, min_minute, min_lead);
    if (fire === null) continue;

    const bet_amount = capital * bet_fraction;
    const pnl =
      fire.result === "win" ? bet_amount * avg_win_yield : -bet_amount;
    capital += pnl;

    trades.push({ ... bet_amount, pnl, capital_after: capital });
  }

  // ... win_rate, final_capital, gain_pct computation ...

  // Display newest-first.
  const display_trades = [...trades].sort((a, b) =>
    b.date.localeCompare(a.date),
  );

  return {
    summary: {
      matches_scanned: file.matches.length,
      matches_bet_on: trades.length,
      wins,
      losses,
      win_rate,
      initial_capital,
      final_capital,
      gain_pct,
    },
    trades: display_trades,
  };
}
```

**Mutations:**

1. Destructure `contract_price_cents` instead of `avg_win_yield` (line 154).
2. Insert at function entry (per D-08 + Pattern 1 from RESEARCH.md):
   ```typescript
   const initial_capital_cents = Math.floor(initial_capital * 100);
   let capital_cents = initial_capital_cents;
   ```
   replacing `let capital = initial_capital` (line 164).
3. Rewrite the inner loop body (lines 170–172) per the canonical contract-math
   kernel (RESEARCH.md "Code Examples" + D-04 + D-17):
   ```typescript
   const bet_amount_cents = Math.floor(capital_cents * bet_fraction);
   const contracts = Math.floor(bet_amount_cents / contract_price_cents);

   let pnl_cents: number;
   if (contracts === 0) {
       pnl_cents = 0;
   } else if (fire.result === "win") {
       pnl_cents = contracts * (100 - contract_price_cents);
   } else {
       pnl_cents = -contracts * contract_price_cents;
   }
   capital_cents += pnl_cents;
   ```
4. Replace the `trades.push({...})` payload (lines 175–190) — drop
   `bet_amount`, add `contracts` and `contract_price_cents`, rename `pnl` →
   `pnl_cents` and `capital_after` → `capital_after_cents`.
5. Compute `final_capital_cents` (was `final_capital`) and rewrite the
   `gain_pct` formula to use `_cents` operands (line 198–203):
   ```typescript
   const gain_pct =
       initial_capital_cents === 0
           ? 0
           : Math.round(
                 ((capital_cents - initial_capital_cents) / initial_capital_cents) * 100 * 1e4,
             ) / 1e4;
   ```
6. Update the returned `summary` (lines 211–220) to emit `initial_capital_cents`
   / `final_capital_cents` per D-11.

**Preserve** (do not touch):
- The chronological sort (lines 159–161).
- `detectFire` invocation (line 167).
- The `wins` / `losses` / `settled` / `win_rate` aggregation block (lines 193–196).
- The newest-first `display_trades` sort (lines 206–208).
- Final return shape `{ summary, trades }` (lines 210–222).

#### Internal-rename pattern (Discretion item 3)

Local variables inside `runBacktest` rename in lockstep with the type fields:
`capital` → `capital_cents`, `bet_amount` → `bet_amount_cents`, `pnl` →
`pnl_cents`, `final_capital` → `final_capital_cents`. RESEARCH.md
recommendation is "yes, rename for clarity" — variable names should match the
unit semantics they carry.

---

### `dashboard/app/backtest/page.tsx` (component, request-response)

**Analog:** the file itself. The two existing slider blocks for `min_minute`
and `min_lead` are the in-place pattern for the new `contract_price_cents`
input. The `TradeRow` component is the in-place pattern for the trade-row
text update.

#### Imports pattern (line 6) — to be modified

```typescript
import { runBacktest, DEFAULT_WIN_YIELD, type BacktestTrade } from "./backtest";
```

**Mutation per D-16:** remove `DEFAULT_WIN_YIELD` from the import list. Final
form:

```typescript
import { runBacktest, type BacktestTrade } from "./backtest";
```

#### `formatEuro` helper (lines 8–13) — keep as-is

```typescript
function formatEuro(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}
```

**Reuse pattern per D-12:** every cents-typed field renders via
`formatEuro(value / 100)`. No new helper needed.

#### `SummaryCard` component (lines 15–38) — keep as-is, change call sites only

The component itself is untouched. Only the `value` strings passed in change
(see Summary card call sites below).

#### `TradeRow` component (lines 40–64) — partial rewrite

**Existing third-line block (lines 55–61):**

```typescript
<div className="text-xs text-gray-300 mt-1">
    Bet €{formatEuro(trade.bet_amount)} ·{" "}
    <span className={pnlClass}>
        {pnlSign}€{formatEuro(Math.abs(trade.pnl))}
    </span>{" "}
    · capital €{formatEuro(trade.capital_after)}
</div>
```

**Sign-stripping pattern to preserve (lines 43–44):**

```typescript
const pnlSign = trade.pnl >= 0 ? "+" : "−";
const pnlClass = trade.pnl >= 0 ? "text-green-400" : "text-red-400";
```

**Mutation per D-14, D-12, RESEARCH.md "TradeRow third line" example:**

```typescript
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

Key points:
- `cost_cents` derived at render per D-13 (not stored on `BacktestTrade`).
- Sign stripping pattern preserved (per RESEARCH.md Pitfall 2): negative
  cents never reach `formatEuro`.
- All three EUR renders use `value / 100`.

#### Sidebar input — analog pattern (lines 137–162)

The two existing slider blocks are the canonical pattern for the new input.
Match this rhythm exactly.

**`min_minute` slider (lines 137–149):**

```typescript
<div>
    <label className="block text-sm text-gray-300 mb-1">
        Min minute: {minMinute}
    </label>
    <input
        type="range"
        min={1}
        max={90}
        value={minMinute}
        onChange={(e) => setMinMinute(Number(e.target.value))}
        className="w-full"
    />
</div>
```

**`min_lead` slider (lines 150–162):**

```typescript
<div>
    <label className="block text-sm text-gray-300 mb-1">
        Min lead: {minLead}
    </label>
    <input
        type="range"
        min={1}
        max={5}
        value={minLead}
        onChange={(e) => setMinLead(Number(e.target.value))}
        className="w-full"
    />
</div>
```

#### `avgWinYield` block to replace (lines 197–222)

**Existing block to delete:**

```typescript
<div>
    <label className="block text-sm text-gray-300 mb-1">
        Avg win yield (EUR per 1 EUR staked)
    </label>
    <input
        type="number"
        min={0.001}
        max={1}
        step={0.001}
        value={avgWinYield}
        onChange={(e) =>
            setAvgWinYield(
                Math.min(
                    1,
                    Math.max(0.001, Number(e.target.value) || 0.001),
                ),
            )
        }
        className="w-full bg-black border border-gray-700 rounded px-2 py-1"
    />
</div>
<p className="text-xs text-gray-500">
    Win yield: {avgWinYield} EUR per 1 EUR staked. A losing bet loses
    the full stake.
</p>
```

**Replacement per D-02, D-03, RESEARCH.md "Sidebar input replacement"
example, modeled on the `min_minute` / `min_lead` slider rhythm above:**

```typescript
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

Note: this slider lives inside the `border-t border-gray-800 pt-3 space-y-3`
section (line 163) alongside `Initial capital` and `Bet size`. Keep that
position — it's the same visual slot the deleted `avgWinYield` block
occupied.

#### State hook (line 73) — to be modified

**Existing:**

```typescript
const [avgWinYield, setAvgWinYield] = useState(DEFAULT_WIN_YIELD);
```

**Replacement per D-02:**

```typescript
const [contractPriceCents, setContractPriceCents] = useState(97);
```

#### `useMemo` params object (lines 87–99) — to be modified

**Existing:**

```typescript
const result = useMemo(
    () =>
        selected
            ? runBacktest(selected.data, {
                  min_minute: minMinute,
                  min_lead: minLead,
                  initial_capital: initialCapital,
                  bet_fraction: betFractionPct / 100,
                  avg_win_yield: avgWinYield,
              })
            : null,
    [selected, minMinute, minLead, initialCapital, betFractionPct, avgWinYield],
);
```

**Mutation:** swap `avg_win_yield: avgWinYield` for
`contract_price_cents: contractPriceCents` in the params object, and update
the dependency array (`avgWinYield` → `contractPriceCents`).

#### Summary card call sites (lines 267–283) — partial rewrite

**Existing:**

```typescript
<SummaryCard
    label="Final capital"
    value={`€${formatEuro(result.summary.final_capital)}`}
    tone={
        result.summary.final_capital >=
        result.summary.initial_capital
            ? "positive"
            : "negative"
    }
/>
```

**Mutation per D-11, D-12:** read `final_capital_cents` /
`initial_capital_cents`, divide by 100 for `formatEuro`:

```typescript
<SummaryCard
    label="Final capital"
    value={`€${formatEuro(result.summary.final_capital_cents / 100)}`}
    tone={
        result.summary.final_capital_cents >=
        result.summary.initial_capital_cents
            ? "positive"
            : "negative"
    }
/>
```

The other six summary cards (Scanned, Bet on, Wins, Losses, Win rate, Gain)
are untouched per D-15 — they don't reference the renamed fields.

---

### `.planning/ROADMAP.md` (doc, text)

**Analog:** the file itself. One-line rewrite.

#### Existing line (line 58)

```
  2. The `avg_win_yield` slider is gone from the backtest UI; existing sliders (min_minute, min_lead, min_yes_price, max_yes_price) remain and function
```

#### Replacement per D-06

```
  2. The `avg_win_yield` input is gone; a `contract_price` input (default 97, range 50–99 cents) drives the new math; existing sliders (`min_minute`, `min_lead`) remain and function.
```

The replacement removes the `min_yes_price` / `max_yes_price` reference (those
sliders don't exist yet — they're Phase 2 / BT-07 per D-07). Other lines in
`Phase 1` block (lines 52–60) stay as-is.

---

## Shared Patterns

### Integer-cents at function entry, EUR at boundary
**Source:** new pattern introduced by this phase, anchored to
`src/predictions/scanner.py:324` (`int(available_cash * (bet_percent / 100.0))`)
and `src/predictions/scanner.py:134` (`count = max_cost_cents // yes_price`)
for the floor convention, and to the existing `formatEuro(value)` helper
(`page.tsx:8–13`) for the EUR formatting boundary.
**Apply to:** `backtest.ts` `runBacktest` body and every cents-typed render
site in `page.tsx`.

```typescript
// At runBacktest entry (the only EUR → cents conversion point):
const initial_capital_cents = Math.floor(initial_capital * 100);

// At every JSX leaf rendering money (the only cents → EUR conversion point):
formatEuro(value_cents / 100)
```

### Floor truncation for stake and contract counts
**Source:** `src/predictions/scanner.py:324` and `:134` (Python's `int()`
truncates toward zero; for non-negative values, `Math.floor` matches).
**Apply to:** both `bet_amount_cents` and `contracts` computation in
`runBacktest`.

```typescript
const bet_amount_cents = Math.floor(capital_cents * bet_fraction);
const contracts = Math.floor(bet_amount_cents / contract_price_cents);
```

### Sign stripping at render
**Source:** `dashboard/app/backtest/page.tsx:43–44` (existing `pnlSign` /
`pnlClass` ternary in `TradeRow`).
**Apply to:** `TradeRow` post-rename. Negative `pnl_cents` must never reach
`formatEuro` directly; pass `Math.abs(...)`.

```typescript
const pnlSign = trade.pnl_cents >= 0 ? "+" : "−";
const pnlClass = trade.pnl_cents >= 0 ? "text-green-400" : "text-red-400";
// ...
{pnlSign}€{formatEuro(Math.abs(trade.pnl_cents) / 100)}
```

### Slider input rhythm
**Source:** `dashboard/app/backtest/page.tsx:137–149` (`min_minute`),
`page.tsx:150–162` (`min_lead`).
**Apply to:** new `contract_price_cents` slider. Matches RESEARCH.md
Discretion item 2 recommendation (slider over number input).

---

## No Analog Found

None. Every required pattern exists in-file or in `src/predictions/scanner.py`
(referenced for the floor-truncation convention).

## Metadata

**Analog search scope:** the three target files plus `src/predictions/scanner.py`
(referenced for the floor-truncation convention only — no edits). Confirmed
by RESEARCH.md repo-wide greps that `simulateMatch`, `DEFAULT_WIN_YIELD`,
`avg_win_yield`, and `avgWinYield` appear nowhere else in `*.ts`/`*.tsx`.

**Files scanned:** 3 in-scope, 1 reference (`scanner.py`).

**Pattern extraction date:** 2026-04-29
