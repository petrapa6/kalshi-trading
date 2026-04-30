---
phase: 02-strategy-engine-core
plan: 04
subsystem: ui
tags: [typescript, react, dashboard, backtest, multi-trigger, strategy, sport-family, hierarchy, d-02-override]

# Dependency graph
requires:
  - phase: 02-strategy-engine-core
    provides: "Trigger / Strategy Pydantic shapes + GET /api/strategies endpoint (02-01, 02-02); multi-trigger backtest engine + LeagueOption.sport_path (02-03)"
provides:
  - "Sport→League→Strategy hierarchical sidebar in dashboard/app/backtest/page.tsx"
  - "Page-level Sport dropdown (currently single-option: Football)"
  - "League dropdown filtered by sport (renamed from Season; 6 football leagues)"
  - "Strategy dropdown filtered by sport — only strategies whose ALL triggers match the selected sport are listed"
  - "Per-trigger cards (no per-trigger Sport row): min_minute / min_lead sliders + read-only Live trading info text + remove-with-confirm button"
  - "Sport-family literal (football) replacing ESPN sport_path across strategies.yaml, fixtures, tests, and dashboard TS layer (D-02 override)"
  - "Season→League rename in seasons.ts (SeasonOption→LeagueOption, SEASONS→LEAGUES, sport_path→sport)"
affects:
  - 02-05 (verification plan reads the final state of the sidebar + strategies.yaml)
  - phase 03 scanner integration (must read the D-02 override in 02-CONTEXT.md addendum, NOT the original D-02; trigger.sport is a sport-family literal, mapped to the scanner's per-league taxonomy at evaluation time)
  - phase 04 analytics dashboard (per-strategy filtering UI can mirror the Sport→League→Strategy hierarchy)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Sport→League→Strategy hierarchy: page-level Sport drives both the League list (filter by family) and the Strategy list (filter by ALL-triggers-match-sport). All triggers in a backtest run inherit the page-level Sport implicitly — per-trigger Sport dropdown is structurally absent."
    - "Sport-family literal (football, baseball, …) instead of ESPN sport_path — UK terminology (football, never soccer). Loader Pydantic schema unchanged (sport: str validates any string); only the values changed."
    - "Auto-snap-to-Custom on any field edit — selecting a named strategy populates triggers; editing any trigger field flips selectedStrategy back to __custom__ to signal the trigger set no longer matches the preset."
    - "Filter-not-gray for sport mismatch: strategies whose triggers don't match selectedSport are hidden from the dropdown entirely (not grayed). The original D-15/D-18 graying + skipped-triggers UI is structurally impossible under the new model and was deleted."
    - "Defensive engine-side sport equality preserved: detectFireMulti still does a per-trigger `trigger.sport !== league.sport` check even though the UI guarantees alignment — cheap, future-proof if a non-UI caller bypasses the page."

key-files:
  created: []
  modified:
    - dashboard/app/backtest/page.tsx
    - dashboard/app/backtest/seasons.ts
    - dashboard/app/backtest/backtest.ts
    - strategies.yaml
    - tests/fixtures/strategies-good.yaml
    - tests/fixtures/strategies-unknown-field.yaml
    - tests/test_strategies.py
    - tests/test_strategies_api.py
    - .planning/phases/02-strategy-engine-core/02-CONTEXT.md

key-decisions:
  - "D-02 OVERRIDE: trigger.sport is a sport-family literal (football, baseball, …) NOT the ESPN sport_path (soccer/eng.1, …). Triggered by user pushback during the human-verify checkpoint after the original 72683e5 implementation. Recorded in 02-CONTEXT.md addendum (preserves original D-02 verbatim above for audit trail)."
  - "UK terminology: football (never soccer) across YAML, code, tests, and UI."
  - "Per-trigger Sport dropdown removed from the UI. Sport is a page-level concern; all triggers in a run share it. This simplifies the mental model (no sport mismatch graying, no skipped-triggers count line) and rules out an entire class of UX bugs."
  - "Strategy dropdown uses filter-not-gray: strategies with any non-matching trigger are hidden, not grayed. The user explicitly preferred hiding over visual-cleanliness-via-graying (reversal of the earlier transparency-over-cleanliness preference once the per-trigger Sport row was deleted — without per-trigger sport, there's nothing to gray)."
  - "League dropdown renamed from Season at the user's request — Season was domain-specific to soccer; League scales across sport families."
  - "LEAGUE_SPORT_PATH constant (introduced in 02-03) was DELETED in this plan; replaced with a tiny LEAGUE_SPORT (family) map. The sport_path-keyed lookup was redundant under the family-only model."
  - "detectFireMulti's defensive sport equality check kept (single comparison per trigger, no allocations) even though the UI prevents mismatches — cheap insurance against non-UI callers (Phase 3 scanner port, tests)."

patterns-established:
  - "Hierarchy of selectors: top-level page state filters everything below it (Sport → League list → Strategy list → trigger defaults). Sport change cascades: setSelectedStrategy(CUSTOM_KEY) + setTriggers([defaultTriggerForSport(sport)]) + setSelectedKey(firstMatchingLeague.key)."
  - "Cross-plan revision protocol: when a checkpoint pushback invalidates an upstream plan's deliverables, capture it as (a) refactor commits scoped per-deliverable, (b) a docs commit appending to the upstream CONTEXT.md (never edit the original decision text), (c) explicit acknowledgement in the originating plan's SUMMARY (this section). Avoids ghost decisions and keeps Phase 3 readers honest about which D-02 to follow."

requirements-completed: [BT-07]

# Metrics
duration: ~30min (initial impl + checkpoint pushback + revision)
completed: 2026-04-30
---

# Phase 2 Plan 04: Backtest Sidebar (Sport→League→Strategy Hierarchy) Summary

**Sport→League→Strategy hierarchical sidebar replacing Phase 1's flat min_minute/min_lead sliders; sport semantics revised mid-plan from ESPN sport_path to sport-family literal (football) per user pushback at the human-verify checkpoint; all 9 acceptance checks passed on the final design.**

## Performance

- **Duration:** ~30 min (single executor session, includes checkpoint pushback + revision round)
- **Started:** 2026-04-30T13:48:45+02:00 (first commit `72683e5`)
- **Completed:** 2026-04-30T14:17:49+02:00 (last commit `d444a4e`)
- **Tasks:** 2 (Task 1 implementation, Task 2 manual checkpoint)
- **Commits:** 4 (1 initial + 3 revision: `72683e5`, `39cf819`, `8f08fa5`, `d444a4e`)
- **Files modified:** 9 (1 sidebar + 1 backtest engine + 1 seasons catalog + 1 strategies.yaml + 2 fixture YAMLs + 2 test files + 1 CONTEXT.md addendum)

## Accomplishments

- **Sport→League→Strategy hierarchical sidebar landed.** Top of sidebar: Sport dropdown (single option: Football). Below: League dropdown filtered to leagues whose `sport === selectedSport` (6 football leagues: EPL, Bundesliga, La Liga, Ligue 1, MLS, Serie A). Below that: Strategy dropdown listing `— Custom —` (default) plus only strategies whose ALL triggers match the selected sport (currently `conservative_late_lead` and `early_value`).
- **Per-trigger cards simplified.** No per-trigger Sport row (sport is a page-level concern). Each card has Min minute slider, Min lead slider, Live trading info text for `min_yes_price`/`max_yes_price` (D-11), `+ Add trigger` button below the last card, `Remove trigger` button on each card hidden when only one trigger exists. Editing any field auto-snaps Strategy back to `— Custom —`.
- **D-02 OVERRIDE applied across the codebase.** `trigger.sport` is now a sport-family literal — `football`, `baseball`, `tennis`, … — instead of the ESPN sport_path (`soccer/eng.1`, `basketball/nba`, …). UK terminology: `football` everywhere, never `soccer`. Loader Pydantic schema unchanged (`sport: str` still accepts any string); only the values changed. Affected: `strategies.yaml` (active + commented WHAT_IF strategies), `tests/fixtures/strategies-good.yaml`, `tests/fixtures/strategies-unknown-field.yaml`, `tests/test_strategies.py` (sport assertion), `tests/test_strategies_api.py` (sport assertion).
- **Season→League rename in dashboard TS.** `SeasonOption`→`LeagueOption`, `SEASONS`→`LEAGUES`, `sport_path`→`sport`. The redundant `LEAGUE_SPORT_PATH` map (introduced in 02-03) was removed and replaced with a small `LEAGUE_SPORT` family map. The dropdown UI label changed from "Season" to "League".
- **Sport-mismatch graying + skipped-triggers UI deleted.** D-15 (opacity-40 + tooltip on mismatched cards) and D-18 (`N of M triggers skipped` muted line) were removed entirely — under the new Sport→League→Strategy hierarchy, sport mismatches are structurally impossible (every trigger inherits the page-level Sport).
- **Phase 1 capital math + summary cards intact.** All 7 summary cards (Scanned, Bet on, Wins, Losses, Win rate, Final capital, Gain) preserved verbatim. `contract_price_cents` slider stays single-instance at the top of the financial section (D-14). `min_yes_price`/`max_yes_price` never appear as sliders anywhere (D-11). Trigger edits remain ephemeral (D-16 — no save-back to YAML).
- **All 9 manual acceptance checks passed.** User typed "approved" after browser-verifying the final revised design.

## Cross-Plan Revision Impact

This plan's D-02 override required amending deliverables of three earlier plans. The amendments are owned by THIS plan (02-04) and are recorded as cross-plan revision commits:

| Plan | Original Deliverable | Revised By 02-04 |
| ---- | -------------------- | ---------------- |
| 02-00 (bootstrap) | `strategies.yaml` shipping with `sport: soccer/eng.1` (ESPN sport_path), per-league `early_value` triggers | All `sport:` values switched to `football`; `early_value` two triggers collapsed to differentiated min_minute/min_lead under one sport family. Five commented WHAT_IF translations updated likewise. |
| 02-00 (bootstrap) | Fixture YAMLs `tests/fixtures/strategies-good.yaml` and `…-unknown-field.yaml` using `sport: soccer/eng.1` | Updated to `sport: football`. |
| 02-01 (loader) | `tests/test_strategies.py` asserting `sport == "soccer/eng.1"` on a happy-path load | Asserts `sport == "football"`. |
| 02-02 (API) | `tests/test_strategies_api.py` asserting `triggers[0]["sport"] == "soccer/eng.1"` on the JSON response | Asserts `triggers[0]["sport"] == "football"`. |
| 02-03 (engine + catalog) | `LEAGUE_SPORT_PATH` exported from seasons.ts; `SeasonOption.sport_path` field; `runBacktest`'s `season_sport_path` arg name | `LEAGUE_SPORT_PATH` deleted (redundant under family-only); `SeasonOption`→`LeagueOption`, `sport_path`→`sport`; `runBacktest` arg renamed to `league_sport`; `detectFireMulti`'s defensive per-trigger sport check is now a single equality against the league family. |

**D-02 override location:** `.planning/phases/02-strategy-engine-core/02-CONTEXT.md`, "Revision — 2026-04-30" section appended after the original `<decisions>` block. The original D-02 wording is preserved verbatim above the addendum for audit trail; the addendum is the authoritative reference for Phase 3.

## Task Commits

Implementation landed across 4 commits (1 initial impl + 3 revision after checkpoint pushback):

1. **Initial implementation (superseded sidebar design)** — `72683e5` (feat) — original Strategy dropdown + per-trigger Sport row + sport-mismatch graying + "N of M skipped" line, per the literal 02-04-PLAN spec.
2. **Cross-plan rename (sport semantics + Season→League)** — `39cf819` (refactor) — D-02 override applied across `strategies.yaml`, fixture YAMLs, tests, and dashboard TS layer (`SeasonOption`→`LeagueOption`, `LEAGUE_SPORT_PATH` removed, `runBacktest`'s arg renamed, `detectFireMulti` per-trigger sport check simplified).
3. **Sidebar replacement (Sport→League→Strategy hierarchy)** — `8f08fa5` (refactor) — final sidebar UX: top-level Sport dropdown, filtered League dropdown, sport-filtered Strategy dropdown, simplified trigger cards (no per-trigger Sport row), removed graying + skipped-triggers UI.
4. **D-02 override documentation** — `d444a4e` (docs) — appended `Revision — 2026-04-30` section to 02-CONTEXT.md noting the override, preserving original D-02 verbatim above.

**Plan metadata commit:** appended at the end of execution.

## Acceptance Checks (all 9 passed)

| # | Check | Result |
| - | ----- | ------ |
| 1 | Strategy dropdown populated from `/api/strategies`, default `— Custom —`, only sport-matching strategies listed | passed |
| 2 | Default trigger card visible (Min minute = 75, Min lead = 2); no Remove button when only 1 trigger | passed |
| 3 | Auto-snap Strategy to Custom on any slider edit | passed |
| 4 | + Add trigger clones; - Remove trigger uses native `window.confirm("Delete this trigger?")` | passed |
| 5 | (replaced under new model) Sport mismatch graying — N/A: hierarchy makes mismatch impossible | n/a — by design |
| 6 | Read-only price info text (e.g. "Live trading: 92¢–99¢"); no slider for min/max_yes_price anywhere | passed |
| 7 | Single contract-price slider at financial section top, not per-trigger | passed |
| 8 | Trigger edits ephemeral — page reload returns to default 1-trigger state | passed |
| 9 | Backtest runs and produces all 7 summary cards (Scanned / Bet on / Wins / Losses / Win rate / Final capital / Gain) | passed |

User approval: typed "approved" after final browser verification of `8f08fa5`.

## Files Created/Modified

### Modified

- `dashboard/app/backtest/page.tsx` — Sidebar wholesale rewritten across 2 commits (`72683e5` then `8f08fa5`). Final state: Sport dropdown + League dropdown + Strategy dropdown hierarchy, per-trigger cards without Sport row, financial section unchanged, summary cards section unchanged. The `8f08fa5` diff alone is +153/-138 lines.
- `dashboard/app/backtest/seasons.ts` — Renamed `SeasonOption`→`LeagueOption`, `SEASONS`→`LEAGUES`. Replaced `LEAGUE_SPORT_PATH` (ESPN sport_path map) with `LEAGUE_SPORT` (family map). Field `sport_path` renamed to `sport`. All 6 leagues map to family `"football"`.
- `dashboard/app/backtest/backtest.ts` — `runBacktest`'s third positional arg renamed `season_sport_path`→`league_sport`. `detectFireMulti`'s defensive per-trigger sport check simplified to a single equality against the league family. `Trigger.sport` JSDoc updated to document family-literal semantics.
- `strategies.yaml` — All `sport:` values switched from ESPN sport_path (`soccer/eng.1`, etc.) to family literal (`football`). `early_value`'s two triggers collapsed to differentiated min_minute/min_lead under one sport family (still demonstrates OR-of-AND semantics). Five commented WHAT_IF translations updated.
- `tests/fixtures/strategies-good.yaml` — `sport: soccer/eng.1` → `sport: football`.
- `tests/fixtures/strategies-unknown-field.yaml` — `sport: soccer/eng.1` → `sport: football`.
- `tests/test_strategies.py` — Updated sport string-literal assertion to `"football"`.
- `tests/test_strategies_api.py` — Updated sport string-literal assertion to `"football"`.
- `.planning/phases/02-strategy-engine-core/02-CONTEXT.md` — Appended `Revision — 2026-04-30` section recording the D-02 override; preserves original D-02 verbatim above for audit trail.

## Decisions Made

- **D-02 override** (the largest decision; triggered by user pushback at the human-verify checkpoint): `trigger.sport` is a sport-family literal (`football`, …) NOT the ESPN sport_path (`soccer/eng.1`, …). Loader schema (`sport: str`) is unchanged; only values changed. Phase 3 scanner port must map family → its per-league taxonomy at evaluation time, NOT mirror the previous one-to-one ESPN mapping.
- **Per-trigger Sport dropdown removed from UI.** Sport is a page-level concern under the new hierarchy. Removes an entire class of UX bugs (sport-mismatch graying, skipped-triggers count line, "what does it mean to mix sports?" confusion).
- **Strategy dropdown filter-not-gray.** Strategies with any non-matching trigger are hidden from the dropdown, not grayed. Without per-trigger Sport, there is no per-trigger surface to gray.
- **Season→League rename** at the user's request. Season is soccer-specific; League scales across families.
- **LEAGUE_SPORT_PATH deleted, replaced with LEAGUE_SPORT.** The ESPN sport_path keyed map (introduced in 02-03) was redundant under family-only — collapsed to a 6-row league→family map. No external callers, so safe rename.
- **Engine-side defensive sport equality preserved.** `detectFireMulti` still checks `trigger.sport !== league.sport` and silently skips, even though the UI guarantees alignment. Single equality, no allocations, future-proof if a non-UI caller bypasses the page (Phase 3 port, tests).

## Deviations from Plan

### User-driven Revision (Checkpoint Pushback — largest deviation)

**1. [Rule 4-equivalent: human decision] D-02 override + Sport→League→Strategy hierarchy**
- **Found during:** Task 2 (manual UI dogfood checkpoint, run against initial implementation `72683e5`)
- **Issue:** The original 02-04-PLAN spec was implemented faithfully (per-trigger Sport dropdown using ESPN sport_path values, sport-mismatch graying, "N of M skipped" muted line). At the human-verify checkpoint the user rejected the design and proposed:
  1. `trigger.sport` should be a sport-family literal (`football`, …), not ESPN sport_path. UK terminology: football, never soccer.
  2. Sport selection should be a page-level concern, not per-trigger.
  3. Add a Sport dropdown above the existing Season dropdown; rename Season→League; have Sport filter both League and Strategy options.
  4. Strategy dropdown should hide non-matching strategies (filter-not-gray).
  5. The graying + skipped-triggers UI is deleted (structurally impossible under the new hierarchy).
- **Fix:** Three follow-up commits.
  - `39cf819` (refactor): cross-plan rename — sport semantics + Season→League across YAML, fixtures, tests, seasons.ts, backtest.ts.
  - `8f08fa5` (refactor): sidebar replaced wholesale with the new Sport→League→Strategy hierarchy.
  - `d444a4e` (docs): D-02 override recorded in 02-CONTEXT.md addendum, preserving original D-02 verbatim above.
- **Files modified:** all 9 listed in the Files Created/Modified section.
- **Verification:** All 9 manual acceptance checks passed on `8f08fa5`. Automated baseline: `uv run pytest tests/ -q` → 60 passed, 1 skipped (no regressions). Dashboard build clean (`pnpm build`), `pnpm exec oxfmt --check app/backtest/` and `pnpm exec oxlint app/backtest/` clean (0 warnings, 0 errors).
- **Committed in:** `39cf819`, `8f08fa5`, `d444a4e`.

### Auto-fixed Issues

None beyond the user-driven revision above. The initial `72683e5` implementation followed the literal plan spec; the revision was user-directed.

---

**Total deviations:** 1 large user-driven revision (D-02 override + sidebar redesign) spanning 3 follow-up commits, amending deliverables of plans 02-00, 02-01, 02-02, and 02-03.
**Impact on plan:** The originating plan's success criteria are met (BT-07 satisfied — the dashboard backtest is the user's window into the YAML strategy catalog). The revision strictly improves the UX clarity and rules out a class of UX bugs. No scope creep; the new design is structurally simpler than the original (fewer UI affordances, simpler mental model, no graying logic). Phase 3 readers must consult the 02-CONTEXT.md addendum, not the original D-02.

## Issues Encountered

- **Initial implementation triggered checkpoint rejection.** Resolved as documented above. The pushback was about UX shape, not correctness — the initial design met every literal acceptance criterion in 02-04-PLAN, but the user judged the per-trigger Sport row + graying UI to be more complicated than the problem warranted once they saw it in the browser. This is exactly what the human-verify checkpoint exists to catch.
- **No build / type / lint regressions across either round.** Dashboard build, oxfmt, oxlint, and pytest all green at every commit boundary.

## User Setup Required

None — no environment variables, no external services. Pure dashboard + YAML + test refactor.

## Next Phase Readiness

- **Plan 02-05 (verification + STATE.md update) ready.** All Phase 2 functional requirements (STR-01, STR-02, STR-03, BT-07) have been implemented. Plan 02-05 should run a goal-backward verification across the full Phase 2 scope (loader → API → engine → UI) and confirm the four roadmap success criteria. Note: 02-05's verification must read 02-CONTEXT.md's addendum for the current sport semantics.
- **Phase 3 (live scanner) — important caveat.** The live scanner port must use the addendum (D-02 override), NOT the original D-02. Specifically: `trigger.sport` is a family literal (`football`, …); the scanner needs a family→per-league taxonomy mapping (e.g., `football` → all `KXNBAGAME`-style soccer event tickers, `basketball` → NBA tickers). The original 02-CONTEXT.md `<decisions>` block's D-02 (ESPN sport_path) is INCORRECT for Phase 3.
- **Phase 4 (analytics dashboard) — the Sport→League→Strategy hierarchy is reusable.** Per-strategy analytics filtering can mirror this UX pattern.
- **No new blockers.** The deferred-items.md log from 02-03 still applies (pre-existing oxfmt issues in `app/actions.ts`, `app/api/[...path]/route.ts`, `sst-env.d.ts` — out of Phase 2 scope).

## Self-Check: PASSED

- Created files: none (this plan modifies existing files only).
- Modified files exist with expected post-revision changes:
  - FOUND: `dashboard/app/backtest/page.tsx` (Sport / League / Strategy dropdowns; SPORTS const; defaultTriggerForSport; strategyMatchesSport; handleSportChange; no per-trigger Sport row; no graying / skipped-triggers UI)
  - FOUND: `dashboard/app/backtest/seasons.ts` (`LeagueOption` interface; `LEAGUES` export; `LEAGUE_SPORT` family map; no `LEAGUE_SPORT_PATH`; `sport: "football"` for all 6 leagues)
  - FOUND: `dashboard/app/backtest/backtest.ts` (Trigger.sport JSDoc updated; `runBacktest` 3rd arg renamed `league_sport`)
  - FOUND: `strategies.yaml` (`sport: football` on both active strategies; commented WHAT_IFs all updated)
  - FOUND: `tests/fixtures/strategies-good.yaml`, `tests/fixtures/strategies-unknown-field.yaml` (sport: football)
  - FOUND: `tests/test_strategies.py`, `tests/test_strategies_api.py` (assertion: "football")
  - FOUND: `.planning/phases/02-strategy-engine-core/02-CONTEXT.md` (Revision — 2026-04-30 section appended; original D-02 preserved verbatim above)
- Commits exist on `master`:
  - FOUND: `72683e5` (feat — initial sidebar implementation, superseded by revision)
  - FOUND: `39cf819` (refactor — sport semantics rename + Season→League across YAML/fixtures/tests/TS layer)
  - FOUND: `8f08fa5` (refactor — sidebar replaced with Sport→League→Strategy hierarchy)
  - FOUND: `d444a4e` (docs — D-02 override recorded in 02-CONTEXT.md addendum)
- Verification commands run:
  - `uv run pytest tests/ -q` → 60 passed, 1 skipped (no regressions vs. pre-02-04 baseline) ✓
  - `(cd dashboard && pnpm exec oxlint app/backtest/)` → 0 warnings, 0 errors ✓
  - `(cd dashboard && pnpm exec oxfmt --check app/backtest/)` → clean ✓
  - `(cd dashboard && pnpm build)` → success ✓
- All 9 manual acceptance checks passed; user typed "approved".

---

*Phase: 02-strategy-engine-core*
*Plan: 04*
*Completed: 2026-04-30*
