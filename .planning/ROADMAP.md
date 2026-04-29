# Roadmap: Kalshi Trading Scanner

## Overview

The product is a working, deployed prediction-market scanner. v1.0 is shipped and described in `PROJECT.md` Validated requirements + `.planning/codebase/`. v1.1 (the current milestone) is a focused frontend refactor of the backtest dashboard page — moving it off the live API + Kalshi-price wiring and onto pre-fetched season JSONs in `resources/`.

This roadmap is bootstrapped retroactively for an existing brownfield project. No deep-questioning research agents were run; v1.0 phases are not enumerated phase-by-phase.

## Milestones

- ✅ **v1.0 Production Scanner** — shipped, see PROJECT.md Validated section
- 🚧 **v1.1 Local-JSON Backtest** — in progress (this milestone)

## Phases

<details>
<summary>✅ v1.0 Production Scanner — SHIPPED</summary>

v1.0 was built before GSD scaffolding existed. There are no per-phase artifacts. Full inventory of what shipped lives in:

- `PROJECT.md` Validated requirements (SCAN-*, CFG-*, DASH-*, CLI-*, BT-*, INFRA-*)
- `.planning/codebase/ARCHITECTURE.md` — system architecture
- `.planning/codebase/STACK.md` — technology choices
- Git history on `master` and `feat/soccer-backtest`

</details>

### 🚧 v1.1 Local-JSON Backtest (In Progress)

**Milestone Goal:** Replace the dashboard backtest page's dependency on `/api/backtest/soccer` and Kalshi prices with a self-contained, deterministic experience driven by pre-fetched season JSONs in `resources/`.

This milestone is being executed as a single quick task (rather than a multi-phase plan) because the scope is contained to `dashboard/app/backtest/page.tsx`.

#### Quick Task: Local-JSON Backtest Page

**Goal**: Refactor the backtest page to load and render data from `resources/*.json`.
**Depends on**: v1.0 (existing backtest page + auth gate)
**Requirements**: BT-03, BT-04, BT-05
**Success Criteria** (what must be TRUE):
  1. Visiting `/backtest` shows a dropdown listing every `(league, season)` parsed from `resources/*.json` filenames.
  2. Selecting a `(league, season)` renders the strategy form, summary stats, trade list, and any retained graphs from that JSON file alone — no network calls to `/api/backtest/soccer`.
  3. The Kalshi-price-based bankroll chart and the `result.partial` retry banner are removed from the page; nothing on the page depends on Kalshi market prices.
  4. `pnpm fmt:check && pnpm lint && pnpm build` pass cleanly in `dashboard/`.
  5. Unauthenticated users continue to be redirected to `/` (auth gate from commit `34b8ab7` still works).

**Plan**: Will be tracked in `.planning/quick/<id>-update-the-soccer-backtest-page-to-check/` (created by `/gsd-quick`).

## Progress

| Phase | Milestone | Status | Completed |
|-------|-----------|--------|-----------|
| v1.0 Production Scanner (aggregate) | v1.0 | Complete | pre-GSD |
| Local-JSON Backtest | v1.1 | In progress | - |

---
*Roadmap defined: 2026-04-29 (inline bootstrap, brownfield)*
