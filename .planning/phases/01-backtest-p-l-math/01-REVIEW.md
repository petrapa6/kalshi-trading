---
phase: 01-backtest-p-l-math
reviewed: 2026-04-29T00:00:00Z
depth: standard
files_reviewed: 2
files_reviewed_list:
  - dashboard/app/backtest/backtest.ts
  - dashboard/app/backtest/page.tsx
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 01: Code Review Report

**Reviewed:** 2026-04-29
**Depth:** standard
**Files Reviewed:** 2
**Status:** issues_found

## Summary

The Phase 01 contract-based P&L migration is mathematically sound. Cents arithmetic is consistently integer; float64 has plenty of headroom (no overflow risk at realistic bankrolls); the canonical kernel matches the plan's verbatim spec; sign-stripping at render is preserved per RESEARCH Pitfall 2; `Math.floor` matches `scanner.py:134` semantics; and `capital_cents` cannot go negative because the floor remainder in `bet_amount_cents` is always ≤ `capital_cents` and loss = `−contracts × price ≤ bet_amount_cents`.

No BLOCKERs found. Two WARNINGs cover D-17 zero-contract rows leaking into win/loss tallies and creating a visual inconsistency on the row background. Five INFO items cover defensive-engineering gaps and minor cosmetic issues.

## Warnings

### WR-01: Zero-contract rows pollute summary stats

**File:** `dashboard/app/backtest/backtest.ts:163-179, 182-184, 203-204`
**Issue:** Per D-17, when `bet_amount_cents < contract_price_cents` the engine emits a row with `contracts=0, pnl_cents=0` while keeping the `result: "win" | "loss"` discriminator from `detectFire`. These rows then flow unconditionally into:
- `wins = trades.filter((t) => t.result === "win").length` (line 182)
- `losses = trades.filter((t) => t.result === "loss").length` (line 183)
- `matches_bet_on: trades.length` (line 204)
- `win_rate = wins / settled` (line 185)

A backtest configured with low capital and a high contract price will report inflated `wins`/`losses` counts, a `matches_bet_on` figure that includes matches where no money was actually staked, and a `win_rate` denominator that mixes real bets and zero-stake rows. The field name `matches_bet_on` is semantically wrong in this case — these rows record fires, not bets.

The plan's manual verification step #2 only checks capital invariance across zero-contract rows; it does not address summary distortion. The Python production `backtest.py:393` has the same semantic (`matches_bet_on` increments on any trigger), but the dashboard summary feeds the user-facing "Win rate" and "Final capital" cards, where misleading aggregates have higher impact.

**Fix:** Decide between two options and apply consistently:

Option A — exclude zero-contract rows from win/loss tallies (recommended; preserves field-name semantics):
```typescript
const settled_trades = trades.filter((t) => t.contracts > 0);
const wins = settled_trades.filter((t) => t.result === "win").length;
const losses = settled_trades.filter((t) => t.result === "loss").length;
// ...
matches_bet_on: settled_trades.length,
```

Option B — keep current behavior but rename to `matches_fired` for honesty.

Either fix needs a corresponding `<manual_verification>` update.

### WR-02: Zero-contract loss rows render with red background but green pnl text

**File:** `dashboard/app/backtest/page.tsx:44-47, 59-61`
**Issue:** The row background is driven by `won = trade.result === "win"` (line 41), but the pnl color is driven by `trade.pnl_cents >= 0` (line 45). For a zero-contract row whose underlying trigger was a "loss":
- Background: `bg-red-900/30` (red-tinted, because `won === false`)
- pnl text: `text-green-400` with `+€0.00` (because `pnl_cents === 0` satisfies `>= 0`)
- Emoji: ❌

This visual inconsistency was not addressed in the plan. The plan's manual verification step #2 only describes the "+€0.00" text and ignores the row background. A user looking at a row with `0 contracts @ 97¢ · €0.00 cost · +€0.00 · capital €1.00` and a red-tinted ❌ background will reasonably assume the row represents a loss.

**Fix:** Drive the visual state on `contracts === 0` first:
```typescript
const isZero = trade.contracts === 0;
const won = trade.result === "win";
const bgClass = isZero
  ? "bg-gray-900/30"
  : won
    ? "bg-green-900/30"
    : "bg-red-900/30";
const emoji = isZero ? "—" : won ? "✅" : "❌";
```
This is consistent with the WR-01 fix path (treating zero-contract rows as a third category at render).

## Info

### IN-01: `runBacktest` will throw if `contract_price_cents === 0`

**File:** `dashboard/app/backtest/backtest.ts:151`
**Issue:** `Math.floor(bet_amount_cents / contract_price_cents)` divides by `contract_price_cents`. If a future caller invokes `runBacktest` programmatically with `contract_price_cents = 0`, the result is `Infinity`, which then multiplies into `pnl_cents` as `Infinity` or `NaN`, corrupting capital and throwing `RangeError` deep in render. The UI slider's `min={50}` prevents this from the dashboard, but the engine's exported function makes no guarantee about its input range.

**Fix:** Either narrow the type at the boundary (a branded `ContractPriceCents` type) or add a single defensive check at function entry:
```typescript
if (contract_price_cents <= 0 || contract_price_cents >= 100) {
  throw new Error(`contract_price_cents must be in 1..99, got ${contract_price_cents}`);
}
```
Per CLAUDE.md, validate only at system boundaries — the engine is one. The slider's bounds (50-99) are UX, not contract-level guarantees.

### IN-02: `parseScore` / `parseGoalTime` throw on bad data, uncaught in render path

**File:** `dashboard/app/backtest/backtest.ts:54-58, 65-69`; consumed at `dashboard/app/backtest/page.tsx:89-99`
**Issue:** `parseScore` and `parseGoalTime` throw synchronously on malformed strings. They are called inside `detectFire` → `runBacktest`, which runs inside a `useMemo`. A malformed season JSON (e.g., a goal with `time: "90"` missing the `|stoppage` part) crashes the React render with no error boundary upstream. The dashboard shows a blank page or an unhandled error.

This is a pre-existing concern rather than a Phase 01 regression, but Phase 01 left it unaddressed while explicitly invoking these functions through the rewritten engine.

**Fix:** Wrap the `useMemo` body in a try/catch returning a `{ error: string }` discriminator, or add a small `<ErrorBoundary>` wrapper around the page body. Out of Phase 01 scope but worth a follow-up TODO.

### IN-03: Final-capital tone treats break-even as "positive"

**File:** `dashboard/app/backtest/page.tsx:272-277`
**Issue:** `final_capital_cents >= initial_capital_cents ? "positive" : "negative"` colors the "Final capital" card green when equal. An exact break-even outcome — distinct from a real gain — renders identically to a profitable run. The Gain card on the next block uses `gain_pct >= 0`, which has the same property. Minor; both follow the same convention so the cards stay in sync.

**Fix:** Strict comparison if you want break-even neutral:
```typescript
tone={
  result.summary.final_capital_cents > result.summary.initial_capital_cents
    ? "positive"
    : result.summary.final_capital_cents < result.summary.initial_capital_cents
      ? "negative"
      : "neutral"
}
```

### IN-04: `Math.floor(initial_capital * 100)` silently truncates fractional EUR

**File:** `dashboard/app/backtest/backtest.ts:142`
**Issue:** The number input on `initialCapital` (page.tsx:177-186) has `step={1}` and `min={1}`, but the browser does not enforce step on `<input type="number">` for arrow-key/keyboard input — only the `up`/`down` UI buttons step by 1. A user typing `1000.99` produces `initialCapital = 1000.99`, `Math.floor(100099) = 100099`. That's actually fine here. But typing `1000.005` produces `100000.5` → `Math.floor` → `100000`. The 0.5 cent silently disappears with no UI feedback. Acceptable per the integer-cents invariant; flagging because the truncation is invisible.

**Fix:** Either enforce `step={1}` validation on blur, or use `Math.round(initial_capital * 100)` if "round to nearest cent" is the intended semantic. Current `Math.floor` matches the conservative "never overstate capital" stance.

### IN-05: Negative-sign character is U+2212, not ASCII hyphen-minus

**File:** `dashboard/app/backtest/page.tsx:44`
**Issue:** `pnlSign = trade.pnl_cents >= 0 ? "+" : "−"` uses U+2212 MINUS SIGN. This matches the plan D-14 spec verbatim and renders cleanly in most fonts, but copy-paste of a row's text into a calculator or shell will fail to parse the leading `−`. Cosmetic and intentional per the plan, flagging for awareness.

**Fix:** None required — this is the documented spec. If the team later decides to support copy-to-calc, switch to ASCII `"-"`.

---

_Reviewed: 2026-04-29_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
