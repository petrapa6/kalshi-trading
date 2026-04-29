# Roadmap: Kalshi Trading Scanner

## Overview

This roadmap is bootstrapped retroactively for an existing brownfield project. v1.0 is the pre-GSD production scanner; v1.1 refactored the backtest dashboard page onto local season JSONs.

## Milestones

- ✅ **v1.0 Production Scanner** — shipped pre-GSD, see PROJECT.md Validated section
- ✅ **v1.1 Local-JSON Backtest** — shipped 2026-04-29
- 📋 **v1.2 (TBD)** — not yet planned

## Phases

<details>
<summary>✅ v1.0 Production Scanner — SHIPPED (pre-GSD)</summary>

v1.0 was built before GSD scaffolding existed. There are no per-phase artifacts. Full inventory of what shipped lives in:

- `PROJECT.md` Validated requirements (SCAN-*, CFG-*, DASH-*, CLI-*, BT-*, INFRA-*)
- `.planning/codebase/ARCHITECTURE.md` — system architecture
- `.planning/codebase/STACK.md` — technology choices
- Git history on `master` and `feat/soccer-backtest`

</details>

<details>
<summary>✅ v1.1 Local-JSON Backtest — SHIPPED 2026-04-29</summary>

4 quick tasks executed on branch `feat/soccer-backtest`.

- [x] 260429-h5z: Local-JSON backtest page (BT-03..05) — completed 2026-04-29
- [x] 260429-jtl: Capital simulation + newest-first trade list — completed 2026-04-29
- [x] 260429-k1c: Configurable avg win yield input — completed 2026-04-29
- [x] 260429-k6u: Wire in LaLiga 2024/25 season — completed 2026-04-29

Full archive: `.planning/milestones/v1.1-ROADMAP.md`

</details>

## Progress

| Phase | Milestone | Status | Completed |
|-------|-----------|--------|-----------|
| v1.0 Production Scanner (aggregate) | v1.0 | ✅ Complete | pre-GSD |
| v1.1 Local-JSON Backtest (4 quick tasks) | v1.1 | ✅ Complete | 2026-04-29 |

---
*Roadmap defined: 2026-04-29 (inline bootstrap, brownfield)*
*Last updated: 2026-04-29 after v1.1 milestone completion*
