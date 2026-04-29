# Milestones

## v1.1 — Local-JSON Backtest

**Shipped:** 2026-04-29
**Quick Tasks:** 4 | **Plans:** 4

### Delivered

Replaced the backtest dashboard's dependency on `/api/backtest/soccer` and Kalshi market prices with a fully self-contained, deterministic experience driven by pre-fetched season JSONs in `resources/`. Six leagues now selectable (EPL, LaLiga, Bundesliga, Ligue 1, Serie A, MLS). Capital simulation with compound bet sizing and configurable win yield gives realistic P&L projections with no network calls.

### Key Accomplishments

1. Created `seasons.ts` + `backtest.ts` — clean separation of data catalog from strategy engine; page.tsx reduced to pure UI wiring
2. Replaced API fetch + Kalshi-price bankroll chart with local JSON loader — backtest is now deterministic and works offline
3. Added capital simulation: initial capital, compound bet sizing, final capital + gain analytics
4. Promoted `WIN_YIELD` to configurable `avgWinYield` parameter — enables scenario analysis
5. Extended `FILENAME_RE` for calendar-year league filenames; corrected `LEAGUE_NAMES` keys; wired all 6 season JSONs

### Git Range

`9ac8bb9` (GSD bootstrap) → `a6cb9df` (last commit before milestone close)

### Tech Debt at Close

- Hand-maintained `IMPORTS` array in `seasons.ts` — editing required for each new season
- `simulateMatch` kept as back-compat shim wrapping `detectFire`
- No fee or partial-fill modeling in backtest engine
- Pre-existing `pnpm fmt:check` failures in `app/page.tsx`, `app/actions.ts`, `app/api/[...path]/route.ts`, `sst-env.d.ts` (predates milestone)

### Archive

- `.planning/milestones/v1.1-ROADMAP.md`
- `.planning/milestones/v1.1-REQUIREMENTS.md`
- `.planning/milestones/v1.1-MILESTONE-AUDIT.md`

---

## v1.0 — Production Scanner

**Shipped:** pre-GSD (before scaffolding existed)

See `PROJECT.md` Validated section for the full requirement list (SCAN-*, CFG-*, DASH-*, CLI-*, BT-*, INFRA-*).

No per-phase GSD artifacts exist for v1.0. Architecture and stack are documented in `.planning/codebase/`.
