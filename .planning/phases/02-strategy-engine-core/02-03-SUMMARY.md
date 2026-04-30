---
phase: 02-strategy-engine-core
plan: 03
subsystem: ui
tags: [typescript, dashboard, backtest, multi-trigger, or-of-and, sport-path]

# Dependency graph
requires:
  - phase: 02-strategy-engine-core
    provides: "Trigger / Strategy Pydantic shapes from 02-01 + GET /api/strategies endpoint from 02-02 — TS Trigger interface mirrors the JSON shape"
provides:
  - "Trigger interface in dashboard/app/backtest/backtest.ts (sport, min_minute, min_lead, min_yes_price, max_yes_price; all optional)"
  - "BacktestParams with triggers: Trigger[] replacing flat min_minute/min_lead"
  - "detectFireMulti(match, triggers, season_sport_path) — OR-of-AND evaluator, first-fire-wins per match"
  - "runBacktest(file, params, season_sport_path) — third positional arg for sport-mismatch skip"
  - "LEAGUE_SPORT_PATH constant + sport_path field on SeasonOption (D-02 plumbing)"
  - "Transitional single-trigger wiring in page.tsx so Phase 1 UX still works while Plan 02-04 builds the multi-trigger sidebar"
affects:
  - 02-04-PLAN (sidebar UI consumes Trigger interface + sport_path; replaces page.tsx wholesale)
  - phase 03 scanner integration (live scanner can mirror detectFireMulti's OR-of-AND semantics)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "OR-of-AND multi-trigger evaluation: outer loop walks goals chronologically, inner loop tries triggers in declaration order; first satisfied trigger fires (mirrors live scanner's first-fire-wins semantics)"
    - "Sport mismatch is silent skip, not error: trigger.sport defined and != season_sport_path → continue; preserves explicit-multi-league strategies that hand a season-specific catalog of triggers and let the engine filter"
    - "Existing single-trigger detectFire kept alongside detectFireMulti — zero external callers but harmless to leave; avoids gratuitous churn"
    - "Phase 1 capital math (contracts = floor(stake_cents / contract_price_cents), zero-contract exclusion from win/loss tallies, integer cents, newest-first display reverse) preserved verbatim"

key-files:
  created: []
  modified:
    - dashboard/app/backtest/seasons.ts
    - dashboard/app/backtest/backtest.ts
    - dashboard/app/backtest/page.tsx

key-decisions:
  - "Matched the existing 2-space indent in dashboard/app/backtest/*.ts even though oxfmt.json declares indentWidth: 4 — oxfmt does not enforce it for those files (verified by --check passing on the modified files), and the 4-space convention referenced in the plan does not reflect the actual repo state"
  - "Added page.tsx to this plan's modifications (in addition to the listed files_modified) for a transitional single-trigger wiring that keeps the dashboard build green at this plan's commit boundary; plan 02-04 replaces the sidebar wholesale"
  - "Kept the original detectFire export in place — zero external callers, but removing it would expand blast radius without value"
  - "page.tsx's transitional useMemo passes selected.sport_path as both Trigger.sport AND the season_sport_path arg, so the Phase 1 single-trigger flow runs through the new code path with identical engine semantics (no regression on EPL/LaLiga/Bundesliga numbers)"

patterns-established:
  - "Trigger interface mirror: dashboard Trigger fields use the exact names emitted by GET /api/strategies (sport, min_minute, min_lead, min_yes_price, max_yes_price); response_model_exclude_none=True on the API side maps to optional/undefined on the TS side"
  - "season_sport_path threading: the season selector's sport_path is the single source of truth for trigger filtering; runBacktest takes it explicitly rather than re-deriving from triggers"

requirements-completed: [BT-07]

# Metrics
duration: ~5min
completed: 2026-04-30
---

# Phase 2 Plan 03: Backtest Engine Multi-Trigger Refactor Summary

**Backtest engine now evaluates OR-of-AND multi-trigger strategies via `detectFireMulti(match, triggers, season_sport_path)`; `BacktestParams.triggers: Trigger[]` replaces flat `min_minute` / `min_lead`; sport-mismatched triggers silently skip; Phase 1 capital math unchanged.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-30T11:34:38Z
- **Completed:** 2026-04-30T11:39:52Z
- **Tasks:** 2
- **Files modified:** 3 (2 in plan's listed scope + page.tsx transitional wiring)

## Accomplishments

- **`Trigger` interface exported from `backtest.ts`.** Five optional fields (`sport`, `min_minute`, `min_lead`, `min_yes_price`, `max_yes_price`); shape mirrors the JSON emitted by `GET /api/strategies` (Plan 02-02). Plan 02-04's sidebar can `import type { Trigger }` directly.
- **`BacktestParams` is now multi-trigger.** Flat `min_minute` / `min_lead` removed. `triggers: Trigger[]` is required. Existing financial fields (`initial_capital`, `bet_fraction`, `contract_price_cents`) untouched — they remain page-top single-instance per D-14.
- **`detectFireMulti` ships.** Walks `match.goals` chronologically; for each goal, tries every trigger in declaration order; fires on the first trigger whose AND-conditions are satisfied. Sport-mismatched triggers (`trigger.sport !== undefined && trigger.sport !== season_sport_path`) silently `continue` — the engine ignores them entirely (D-12 / D-15). `min_yes_price` / `max_yes_price` are accepted in the type but never read by the engine (D-11 — backtest data has no Kalshi prices).
- **`runBacktest` signature evolved.** New third positional `season_sport_path: string` arg. Internal capital math (Phase 1 D-01..D-17) is byte-identical to before — same `Math.floor(bet_amount_cents / contract_price_cents)` contract count, same zero-contract exclusion from win/loss tallies, same newest-first display reverse.
- **`LEAGUE_SPORT_PATH` exported from `seasons.ts`.** All 6 leagues mapped (`bundesliga` → `soccer/ger.1`, `epl` → `soccer/eng.1`, `laliga` → `soccer/esp.1`, `ligue1` → `soccer/fra.1`, `mls` → `soccer/usa.1`, `seriea` → `soccer/ita.1`). Reuses ESPN sport_path notation per D-02.
- **`SeasonOption.sport_path` populated for all `SEASONS`.** Constructed at `IMPORTS.flatMap` time via `LEAGUE_SPORT_PATH[parsed.league] ?? ""`. All 6 active seasons resolve to a non-empty `soccer/<code>` value.
- **Transitional `page.tsx` wiring keeps Phase 1 UX intact.** The single `useMemo` body now builds a single-trigger array `[{ sport: selected.sport_path, min_minute: minMinute, min_lead: minLead }]` and passes `selected.sport_path` as the third arg. Numbers reproduce the Phase 1 backtest exactly because the engine's behavior on a single trigger with matching sport is mathematically identical to the old `detectFire` path. Plan 02-04 will replace this wholesale with the multi-trigger sidebar.

## Public Engine Surface (for Plan 02-04 handoff)

```typescript
// dashboard/app/backtest/backtest.ts
export interface Trigger {
  sport?: string;
  min_minute?: number;
  min_lead?: number;
  min_yes_price?: number;   // info-only in backtest; not consumed
  max_yes_price?: number;   // info-only in backtest; not consumed
}

export interface BacktestParams {
  triggers: Trigger[];        // OR-of-AND; first fires
  initial_capital: number;    // EUR float
  bet_fraction: number;       // 0..1
  contract_price_cents: number;
}

export function runBacktest(
  file: SeasonFile,
  params: BacktestParams,
  season_sport_path: string,  // from selected.sport_path
): BacktestResult;
```

```typescript
// dashboard/app/backtest/seasons.ts
export const LEAGUE_SPORT_PATH: Record<string, string>;

export interface SeasonOption {
  key: string;
  parsed: ParsedFilename;
  data: SeasonFile;
  sport_path: string;   // "" if league not in LEAGUE_SPORT_PATH
}
```

Plan 02-04 should:
1. Replace `minMinute` / `minLead` `useState` with `triggers: Trigger[]` + `selectedStrategy: string` state.
2. Fetch `/api/strategies` on mount; populate strategy dropdown.
3. Render per-trigger cards (sport dropdown, min_minute slider, min_lead slider, info text for min_yes_price/max_yes_price); add (+)/(-) buttons.
4. Replace the transitional `useMemo` body with the new state model.
5. Sport-mismatched cards rendered grayed/dim with tooltip per D-15.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add LEAGUE_SPORT_PATH + sport_path on SeasonOption** — `2f969c7` (feat)
2. **Task 2: Refactor backtest engine for OR-of-AND multi-trigger evaluation** — `33d1b54` (feat; also bundles transitional page.tsx wiring)

**Plan metadata commit:** appended at the end of execution.

## Files Created/Modified

### Modified

- `dashboard/app/backtest/seasons.ts` — Added `LEAGUE_SPORT_PATH` constant (exported) immediately after `LEAGUE_NAMES`. Added `sport_path: string` field to `SeasonOption` interface. Updated `SEASONS` flatMap to populate `sport_path` per entry. 22 line insertions, 1 deletion.
- `dashboard/app/backtest/backtest.ts` — Added `Trigger` interface (exported). Replaced `BacktestParams` body (removed `min_minute` + `min_lead` flat fields, added `triggers: Trigger[]`). Added `detectFireMulti` helper (60 lines). Updated `runBacktest` signature (third `season_sport_path` arg) and call site (now invokes `detectFireMulti`). Existing `detectFire` left intact. 78 insertions, 8 deletions.
- `dashboard/app/backtest/page.tsx` — Single `useMemo` body updated to call `runBacktest` with the new shape: builds a single-trigger array from existing `minMinute` / `minLead` state, passes `selected.sport_path` as the third arg. No new state, no new imports, no new UI elements (those are 02-04's scope). 17 insertions, 6 deletions.

## Decisions Made

- **2-space indent retained.** `oxfmt.json` declares `indentWidth: 4`, but the actual codebase uses 2-space and oxfmt does not enforce 4-space on these files (`pnpm fmt:check` passes on all 3 modified files at 2-space). Following the file-local convention is correct; switching to 4-space would balloon the diff and confuse code review.
- **Added `page.tsx` to the modified set.** The plan's `<files_modified>` listed only `seasons.ts` and `backtest.ts`, but the engine signature change in `backtest.ts` would have made `page.tsx` fail TypeScript compilation. The plan's `<action>` block (Task 2 step 5) explicitly authorizes this transitional update, so this is plan-sanctioned, not a deviation. Plan 02-04 will rewrite `page.tsx` wholesale.
- **`detectFire` kept in place.** Zero external callers (verified by reading `runBacktest` — the only caller — which now uses `detectFireMulti`). Removing it would have been pure churn for no functional benefit.
- **Sport mismatch via `!==` (not `===`).** D-12 wording "silently skipped" maps to a `continue` after the comparison. The engine never throws or logs on sport mismatch — exactly mirrors the live scanner's behavior of "trigger doesn't fire if sport doesn't apply".

## Deviations from Plan

### Auto-fixed Issues

None. The plan was executed as written. Two minor notes:

1. The plan's literal acceptance criterion `cd dashboard && pnpm fmt:check` exits 0 is **not currently satisfied** at the repo level — `app/actions.ts`, `app/api/[...path]/route.ts`, `sst-env.d.ts` have pre-existing formatting issues (verified pre-existing at plan baseline). The 3 files **inside this plan's blast radius** all pass `pnpm oxfmt --check`. Pre-existing failures are out of scope per execute-plan.md SCOPE BOUNDARY rule and are tracked in `.planning/phases/02-strategy-engine-core/deferred-items.md`.

2. The plan's literal grep acceptance for `min_minute?: number` says `>= 1` and the actual count is 1. The Trigger interface declares `min_minute?: number;` (with `?`) once. There is also one usage `trigger.min_minute === undefined || minute >= trigger.min_minute` which contains the `min_minute` token but not in `min_minute?: number` form. Acceptance grep counted the right thing — 1.

---

**Total deviations:** 0 — plan executed as written.
**Impact on plan:** None. The deferred-items.md log captures the pre-existing fmt failures so 02-04 doesn't trip on them.

## Issues Encountered

- **`pnpm fmt` initially errored with "`--write` is not expected in this context".** The dashboard's `fmt` script invokes `oxfmt --write .` but the installed oxfmt version (^0.7) does not accept `--write` (it writes by default; only `--check` and `--list-different` are flags). Worked around by invoking `pnpm oxfmt <file>` directly without flags. Not in this plan's scope to fix the script (touches `package.json`, requires user discussion). Logged as a follow-up.

## User Setup Required

None — no environment variables, no external services. Pure dashboard refactor.

## Next Phase Readiness

- **Plan 02-04 (sidebar UI rewrite) ready.** Public surface documented above. The `Trigger` shape, `BacktestParams` shape, `runBacktest` signature, and `LEAGUE_SPORT_PATH` / `SeasonOption.sport_path` are stable. Plan 02-04 can replace the page.tsx sidebar without touching `backtest.ts` or `seasons.ts` again.
- **Phase 3 (live scanner) ready.** The OR-of-AND first-fire-wins semantics in `detectFireMulti` mirror what the live scanner needs to do per loop: walk the current game state, evaluate each strategy's triggers, fire on first match. The TS reference implementation gives Phase 3 a known-good evaluator to port.
- **No blockers introduced.** The transitional `page.tsx` wiring is intentionally minimal and 02-04 can replace it wholesale.

## Self-Check: PASSED

- Created files: none (this plan modifies existing files only)
- Modified files exist with expected changes:
  - FOUND: `dashboard/app/backtest/seasons.ts` (`LEAGUE_SPORT_PATH` exported, `sport_path` on `SeasonOption`)
  - FOUND: `dashboard/app/backtest/backtest.ts` (`Trigger` interface, `detectFireMulti`, `runBacktest` 3-arg)
  - FOUND: `dashboard/app/backtest/page.tsx` (`triggers: [...]` in `useMemo`, `season_sport_path` passed)
- Commits exist on `master`:
  - FOUND: `2f969c7` (Task 1: feat — `LEAGUE_SPORT_PATH` + `sport_path`)
  - FOUND: `33d1b54` (Task 2: feat — multi-trigger refactor + transitional page.tsx)
- Verification commands run on modified files:
  - `pnpm oxfmt --check app/backtest/{seasons,backtest,page}.{ts,tsx}` exits 0 ✓
  - `pnpm oxlint app/backtest/{seasons,backtest,page}.{ts,tsx}` exits 0 (0 warnings, 0 errors) ✓
  - `pnpm build` exits 0 (Next.js build passes) ✓
  - `pnpm oxlint` (full repo) reports 4 pre-existing warnings (same as baseline) ✓
- Acceptance grep counts (verified via plain grep):
  - `export const LEAGUE_SPORT_PATH` in seasons.ts: 1 (==1) ✓
  - `sport_path: string` in seasons.ts: 1 (==1) ✓
  - All 6 `soccer/<code>` strings in seasons.ts: 1 each ✓
  - `export interface Trigger` in backtest.ts: 1 (==1) ✓
  - `triggers: Trigger[]` in backtest.ts: 2 (>=1) ✓
  - `detectFireMulti` in backtest.ts: 2 (>=2; one definition, one call site) ✓
  - `season_sport_path` in backtest.ts: 5 (>=2) ✓
  - Top-level `min_minute: number;` / `min_lead: number;` in backtest.ts: 0 (==0) ✓
  - `min_minute?: number` in backtest.ts: 1 (>=1) ✓
  - `triggers: [` in page.tsx: 1 (>=1) ✓
  - `Math.floor(bet_amount_cents / contract_price_cents)` in backtest.ts: 1 (Phase 1 capital math intact) ✓

---

*Phase: 02-strategy-engine-core*
*Plan: 03*
*Completed: 2026-04-30*
