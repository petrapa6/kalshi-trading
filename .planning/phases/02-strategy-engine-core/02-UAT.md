---
status: diagnosed
phase: 02-strategy-engine-core
source: [02-00-SUMMARY.md, 02-01-SUMMARY.md, 02-02-SUMMARY.md, 02-03-SUMMARY.md, 02-04-SUMMARY.md, 02-05-SUMMARY.md]
started: 2026-04-30T00:00:00Z
updated: 2026-04-30T00:00:03Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold Start Smoke Test
expected: |
  Kill any running API server / scanner. Clear ephemeral state if any
  (no DB drop required — strategies.yaml is the source of truth, no
  seed/migration shipped in Phase 2). Start fresh:

      pnpm dev:api

  Server boots without import errors, scanner loop initializes, and
  GET http://localhost:8000/ returns {"status":"ok"}. Phase 2 added a
  module-level `from predictions.strategies import load_strategies`
  in src/predictions/api.py — if that import fails or strategies.yaml
  parsing crashes at startup, this is where it shows up.
result: pass

### 2. GET /api/strategies endpoint
expected: |
  With API_TOKEN set in env:

      curl -i http://localhost:8000/api/strategies                                    # → 401 Unauthorized
      curl -s -H "Authorization: Bearer $API_TOKEN" http://localhost:8000/api/strategies | jq .

  Returns 200 with shape {"strategies":[…]}. Two strategies present:
  `conservative_late_lead` and `early_value`. Each has a `triggers`
  array. Triggers have `sport: "football"`. Optional fields not set
  in YAML (like `max_yes_price` on early_value's second trigger) are
  ABSENT from JSON, not null. YAML insertion order preserved.
result: pass

### 3. Sport→League→Strategy dropdowns visible
expected: |
  Open the dashboard backtest page (pnpm dev:dashboard, then load
  http://localhost:3777/backtest). Sidebar top shows three dropdowns
  in this order:

    Sport     → single option "Football"
    League    → 6 options (EPL, Bundesliga, La Liga, Ligue 1, MLS, Serie A)
    Strategy  → "— Custom —" plus conservative_late_lead and early_value

  No "Season" label anywhere — it was renamed to "League".
result: pass

### 4. Default trigger card
expected: |
  On first load (Strategy = "— Custom —") exactly ONE trigger card
  shows beneath the dropdowns. Card has Min minute slider (default
  75) and Min lead slider (default 2). No Remove button (only one
  trigger). "+ Add trigger" button appears below the card.
  No per-trigger Sport row inside the card.
result: pass

### 5. Preset fill + auto-snap to Custom
expected: |
  Select `conservative_late_lead` from Strategy dropdown — trigger
  card(s) populate with that strategy's values; sliders remain
  editable. Now drag any slider — Strategy dropdown immediately
  flips back to "— Custom —" (signals the trigger set no longer
  matches the preset).
result: pass

### 6. Add and Remove trigger with confirm
expected: |
  Click "+ Add trigger" → a second card appears. Both cards now show
  a Remove button (only hidden when exactly 1 trigger exists). Click
  Remove on a card → native browser confirm pops up: "Delete this
  trigger?". Clicking Cancel keeps the card; OK removes it.
result: pass

### 7. Live trading info text, no per-trigger price sliders
expected: |
  Each trigger card shows read-only text mentioning live trading
  bounds, e.g. "Live trading: 92¢–99¢", reflecting min_yes_price /
  max_yes_price from the YAML. There is NO min_yes_price slider
  inside the card and NO max_yes_price slider inside the card —
  these are info-only at the trigger level.
result: issue
reported: "pass, but this text should not be here, it's confusing - remove it and use `contract_price` for backtesting"
severity: minor

### 8. Single contract-price slider
expected: |
  Exactly ONE contract-price slider exists, at the top of the
  Financial section (single instance, page-level). It is NOT
  duplicated per trigger card. Adding more triggers does NOT add
  more contract-price sliders.
result: pass

### 9. Backtest runs and produces 7 summary cards
expected: |
  Click Run Backtest (or whatever the action button is labeled).
  Results appear with all 7 summary cards: Scanned, Bet on, Wins,
  Losses, Win rate, Final capital, Gain. No regressions in numbers
  versus Phase 1 single-trigger flow when using Min minute=75 /
  Min lead=2 against any of the 6 leagues.
result: pass

### 10. Trigger edits ephemeral on reload
expected: |
  Edit a trigger's Min minute slider to a non-default value. Add a
  second trigger. Hit browser Refresh (F5). Page returns to default
  state: 1 trigger card with default values. Trigger edits are
  ephemeral — never persisted to strategies.yaml.
result: pass

## Summary

total: 10
passed: 9
issues: 1
pending: 0
skipped: 0
blocked: 0

## Gaps

- truth: "Trigger card shows read-only Live trading info text reflecting YAML min_yes_price/max_yes_price"
  status: failed
  reason: "User reported: pass, but this text should not be here, it's confusing - remove it and use `contract_price` for backtesting"
  severity: minor
  test: 7
  root_cause: "Design intent (D-11) conflicts with user UX preference at UAT — not a defect. D-11 deliberately surfaced YAML min_yes_price/max_yes_price as read-only info text inside trigger cards; user finds it confusing clutter and wants it removed. User's 'use contract_price for backtesting' is ambiguous between (a) UI-only deletion since contract_price already drives capital math, or (b) engine-level price gating using contract_price as a stand-in for the missing Kalshi book."
  artifacts:
    - path: "dashboard/app/backtest/page.tsx"
      issue: "lines 404-417 render the conditional Live trading info text block; lines 8-14 ApiTrigger interface declares min_yes_price/max_yes_price"
    - path: "dashboard/app/backtest/backtest.ts"
      issue: "lines 14-15 JSDoc declares min_yes_price/max_yes_price NOT used by engine (D-11); detectFireMulti at lines 151-193 confirms zero engine consumption"
    - path: ".planning/phases/02-strategy-engine-core/02-CONTEXT.md"
      issue: "D-11 at lines 137-152 is the original design intent; needs Revision addendum if UAT outcome retracts it"
    - path: "strategies.yaml"
      issue: "lines 15-16 comment notes min_yes_price/max_yes_price are live-scanner config — keep, do not strip from YAML"
  missing:
    - "Disambiguation: confirm whether fix is (a) UI-only deletion or (b) engine-level price gating"
    - "Under (a): delete page.tsx:404-417, optionally clean ApiTrigger fields, add D-11 retraction to 02-CONTEXT.md Revision section"
    - "Under (b): extend detectFireMulti to filter on contract_price ∈ [min_yes_price, max_yes_price], thread contract_price into trigger evaluation, update Trigger JSDoc, add tests"
  debug_session: ".planning/debug/live-trading-info-text-ux.md"
