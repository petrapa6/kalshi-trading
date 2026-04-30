---
status: diagnosed
trigger: "UAT Test 7 (phase 02): user reports 'pass, but this text should not be here, it's confusing - remove it and use `contract_price` for backtesting'. Read-only 'Live trading: X¢–Y¢' info text inside each trigger card reflecting YAML min_yes_price/max_yes_price."
created: 2026-04-30T19:14:02Z
updated: 2026-04-30T19:14:02Z
---

## Current Focus

hypothesis: This is a UX-feedback gap (not a defect). The "Live trading: X¢–Y¢" text was deliberately added per D-11 as info-only surfacing of YAML `min_yes_price`/`max_yes_price`. User now rejects the design choice. Two interpretations of "use `contract_price` for backtesting" — see Resolution.
test: Read page.tsx and backtest.ts, confirm rendering location and engine non-consumption of min/max_yes_price.
expecting: Confirmation that engine ignores those fields entirely (D-11) and rendering is a single self-contained block.
next_action: Return ROOT CAUSE FOUND with both interpretations surfaced for planner to decide.

## Symptoms

expected: |
  No "Live trading: X¢–Y¢" text inside trigger cards. The page-level
  contract_price slider should be the only price-related UI affordance;
  YAML min_yes_price/max_yes_price should not bleed into the backtest UI
  in any user-visible form.

actual: |
  Each trigger card renders a read-only "Live trading: 92¢–99¢ (info only —
  backtest uses contract price slider)" text block whenever YAML triggers
  carry min_yes_price/max_yes_price. The text reflects D-11's design intent
  but the user judges it confusing clutter.

errors: None — feature works as specified per 02-04-SUMMARY check #6 ("passed").

reproduction: |
  1. pnpm dev:api (terminal 1)
  2. pnpm dev:dashboard (terminal 2)
  3. Open http://localhost:3777/backtest
  4. Strategy dropdown → select `conservative_late_lead`
  5. Observe trigger card — "Live trading: 92¢–99¢ (info only — backtest uses contract price slider)" text is visible inside the card

started: |
  Introduced in commit 72683e5 (Phase 02-04 initial implementation,
  2026-04-30) and preserved through revision commits 39cf819 / 8f08fa5 /
  d444a4e. Discovered during /gsd-verify-work UAT Test 7 on 2026-04-30 —
  the user passed Test 7 on its literal acceptance criteria, then rejected
  the design choice in the same line.

## Eliminated

- hypothesis: "Engine reads min_yes_price/max_yes_price and price math is wrong"
  evidence: |
    backtest.ts:151–193 (detectFireMulti): only consumes trigger.sport,
    trigger.min_minute, trigger.min_lead. The Trigger type at backtest.ts:16–22
    accepts min_yes_price/max_yes_price but the JSDoc at backtest.ts:14–15
    explicitly says "NOT used by the backtest engine (D-11)". detectFireMulti's
    body has zero references to min_yes_price or max_yes_price. Confirmed.
  timestamp: 2026-04-30T19:14:02Z

- hypothesis: "Bug — text was supposed to be removed but renderer kept it"
  evidence: |
    02-04-SUMMARY.md lines 83 and 124 both explicitly call out the
    "Live trading info text for min_yes_price/max_yes_price (D-11)" as
    a delivered feature. 02-CONTEXT.md D-11 (lines 137–152) and the
    `<specifics>` block (line 259–263) both call for this exact info-text
    rendering. The feature was deliberately specified, implemented, and
    accepted. This is a design-choice retraction, not a bug.
  timestamp: 2026-04-30T19:14:02Z

## Evidence

- timestamp: 2026-04-30T19:14:02Z
  checked: dashboard/app/backtest/page.tsx — the rendering location of "Live trading"
  found: |
    Lines 404–417 inside the trigger-card map (lines 365–428). The block:

      {(trigger.min_yes_price !== undefined ||
        trigger.max_yes_price !== undefined) && (
        <p className="text-xs text-gray-400">
          Live trading:{" "}
          {trigger.min_yes_price !== undefined
            ? `${trigger.min_yes_price}¢`
            : "—"}
          –
          {trigger.max_yes_price !== undefined
            ? `${trigger.max_yes_price}¢`
            : "—"}{" "}
          (info only — backtest uses contract price slider)
        </p>
      )}

    Self-contained conditional. No state, no effects, no consumers. Pure
    deletion would not break anything else in this file.
  implication: |
    Removing this block is a 14-line surgical delete. No fan-out.

- timestamp: 2026-04-30T19:14:02Z
  checked: dashboard/app/backtest/backtest.ts — engine consumption of min_yes_price/max_yes_price
  found: |
    - Trigger interface declares optional min_yes_price/max_yes_price at
      lines 16–22, with JSDoc lines 14–15 stating "min_yes_price /
      max_yes_price are accepted in the type but NOT used by the backtest
      engine (D-11 — backtest has no Kalshi prices; these are info only)."
    - detectFireMulti (lines 151–193) reads ONLY trigger.sport (line 164),
      trigger.min_minute (line 168), trigger.min_lead (line 169). Zero
      references to min_yes_price/max_yes_price in this function or
      anywhere else in backtest.ts.
    - runBacktest (lines 195–289) also makes zero use of these fields —
      only contract_price_cents from BacktestParams drives capital math
      (lines 218, 224, 226, 244).
  implication: |
    The 02-03 SUMMARY claim "info-only — never read by the engine" is true.
    Interpretation (a) deletion of the UI block is genuinely dead code at
    runtime — the engine will not change behavior whatsoever.

- timestamp: 2026-04-30T19:14:02Z
  checked: dashboard/app/backtest/page.tsx — page-level contract_price slider
  found: |
    Single-instance contract_price slider at lines 344–361 inside the
    Financial section. Drives capital math via BacktestParams.contract_price_cents
    (line 227). Slider range 50–99¢, step 1, default 97. Visible regardless
    of strategy selection.
  implication: |
    The user's "use `contract_price` for backtesting" is already true
    operationally — the slider already drives 100% of price-related capital
    math. So interpretation (a) maps to "no engine change needed; the user
    is saying stop surfacing dead YAML fields in UI."

- timestamp: 2026-04-30T19:14:02Z
  checked: 02-CONTEXT.md D-11 verbatim
  found: |
    Lines 137–152: "**BT-07 is intentionally narrowed.** … `min_yes_price`
    and `max_yes_price` are surfaced as **read-only info text** under each
    trigger group (e.g., 'Live trading: 92¢–99¢'). Not sliders. Not used
    by the backtest engine. … Planner: this narrowing is **intentional**
    and supersedes the literal REQUIREMENTS wording."

    The 2026-04-30 Revision addendum (lines 482–496) covers the D-02
    sport-family override but does NOT touch D-11. D-11 stands.
  implication: |
    Original intent: surface YAML data so users see it without making it
    clickable in backtest (because backtest has no Kalshi book). User UAT
    feedback now overrides this design choice. The two are in direct
    conflict on the surfacing question (not on the engine question — D-11
    and the user agree the engine doesn't use these fields).

- timestamp: 2026-04-30T19:14:02Z
  checked: strategies.yaml — current min_yes_price/max_yes_price usage
  found: |
    Both active strategies use these fields:
    - conservative_late_lead trigger 0: min_yes_price=92, max_yes_price=99
    - early_value trigger 0: min_yes_price=88 (no max)
    - early_value trigger 1: min_yes_price=88 (no max)
    Five commented-out WHAT_IF strategies also use min_yes_price.
    Comment at lines 15–16: "min_yes_price / max_yes_price (live scanner
    only — info text in backtest)" — explicitly documents the dual-use:
    these are LIVE-TRADING fields, surfaced as info in backtest.
  implication: |
    These fields have a real future home — Phase 3 live scanner will FILTER
    on them. They are not dead in the YAML; they are just dead in the
    backtest engine. So removing them from YAML would be wrong (it would
    discard live-trading config). Removing them only from the UI is correct
    under interpretation (a).

- timestamp: 2026-04-30T19:14:02Z
  checked: tests/test_strategies.py and tests/test_strategies_api.py — Python-side schema/test references
  found: |
    Both test files exist. Strategy/Trigger Pydantic schema at
    src/predictions/strategies.py defines min_yes_price/max_yes_price as
    optional fields (per phase 02-01 plan). Tests assert presence/absence
    of these fields on JSON shape. Removing the fields from the schema or
    from active strategies in YAML would break these tests AND remove
    config that Phase 3 needs. So interpretation (a) explicitly leaves
    Python schema and YAML alone — the deletion is purely TS/UI.
  implication: |
    Blast radius for interpretation (a): exactly one file
    (dashboard/app/backtest/page.tsx). Optionally a JSDoc cleanup in
    backtest.ts but no behavioral change there. Zero Python files touched.

## Resolution

root_cause: |
  Design intent (D-11) conflicts with user UX preference at UAT.

  D-11 deliberately specified read-only "Live trading: X¢–Y¢" info text
  inside each trigger card to surface YAML min_yes_price/max_yes_price
  values that the backtest engine intentionally ignores (because backtest
  data has no Kalshi book). The feature was implemented faithfully and
  passed Test 7 on its literal criteria. The user immediately rejected the
  design choice as confusing — calling it noise rather than helpful info.

  The user's directive "use `contract_price` for backtesting" is ambiguous:

  - Interpretation (a) — UI-only deletion: The page-level contract_price
    slider already drives 100% of capital math. The user is observing this
    and saying "the slider is sufficient; stop surfacing the YAML fields
    in the trigger cards." The fix is a 14-line conditional-block deletion
    in page.tsx (lines 404–417). The engine is not changed because the
    engine already does not read these fields. YAML is not changed because
    Phase 3 live scanner will use these fields. Smallest blast radius.

  - Interpretation (b) — engine-level price gating: The user wants
    detectFireMulti to consume min_yes_price/max_yes_price as a filter,
    using the page-level contract_price as the stand-in for the missing
    Kalshi book. Concretely: a goal fires only if
    `min_yes_price <= contract_price_cents <= max_yes_price` (with
    sensible defaults for missing fields). This would make the YAML
    fields *active* in backtest, possibly justifying their continued
    UI presence (just in a different form). Larger blast radius:
    detectFireMulti signature changes, runBacktest needs to forward
    contract_price_cents into the trigger evaluation, tests in
    tests/test_strategies.py potentially gain new assertions.

  The codebase MOST NATURALLY supports interpretation (a) — the
  smaller-blast-radius fix — because:
    1. D-11's narrowing was deliberate and recently documented.
    2. The Trigger interface JSDoc explicitly labels these as info-only.
    3. The contract_price slider already exists and already drives capital
       math; the user's wording ("use `contract_price` for backtesting")
       can be read as confirmation of the status quo, not a request to
       change it.
    4. Interpretation (b) introduces a semantic drift: the YAML's
       min_yes_price/max_yes_price are documented (strategies.yaml lines
       15–16) as live-scanner price bounds against the live YES ask. Using
       them as a static gate against the user-set contract_price slider
       is a conceptual mismatch — contract_price is what the user PAYS,
       not what the market is offering.

  HOWEVER, interpretation (b) cannot be ruled out without user input. The
  planner must surface both options.

fix: ""  # Not applied — diagnose-only mode
verification: ""  # Not applicable — diagnose-only mode
files_changed: []
