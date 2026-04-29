---
id: 260429-k6u
type: quick
status: complete
description: Wire in LaLiga 2024/25 season JSON into the backtest seasons catalog
---

# Quick Task 260429-k6u — Summary

## Outcome

LaLiga 2024/25 is now selectable from the backtest dropdown alongside EPL 2024/25.

## Files changed

- `dashboard/app/backtest/seasons.ts`
  - Added `import laliga_2024_25 from "../../../resources/laliga_2024_25_season.json"`.
  - Replaced the unused `pd` entry in `LEAGUE_NAMES` with `laliga: "La Liga"` so the entry
    matches the actual filename produced by the `fetch-football-season` skill.
  - Appended the LaLiga JSON to the hand-maintained `IMPORTS` array.
- `resources/laliga_2024_25_season.json` — committed (was untracked).

## Verification

- `pnpm exec oxfmt .` clean.
- `pnpm exec oxlint app/backtest/` → 0 warnings, 0 errors.
- `pnpm build` → ✓ compiled successfully, all pages generated.

## Notes for follow-up

- The catalog is still hand-maintained (per the existing TODO in `seasons.ts`). When the
  next season lands, follow the same three-step pattern: import, append to `IMPORTS`,
  ensure `LEAGUE_NAMES` has the league key.
- Trade list sort by league name now puts La Liga between EPL and Bundesliga (when those
  are added later) — matches user expectation.
