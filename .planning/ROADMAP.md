# Roadmap: Kalshi Trading Scanner

## Overview

Brownfield project. v1.0 (pre-GSD) shipped the production scanner; v1.1 refactored the backtest dashboard onto local season JSONs; v1.2 replaced the hardcoded strategy system with a YAML-driven engine + per-strategy analytics dashboard. v1.3 is not yet defined.

## Milestones

- ✅ **v1.0 Production Scanner** — shipped pre-GSD, see PROJECT.md Validated section
- ✅ **v1.1 Local-JSON Backtest** — shipped 2026-04-29 ([archive](milestones/v1.1-ROADMAP.md))
- ✅ **v1.2 Strategy Engine** — shipped 2026-05-08, 4 phases / 17 plans ([archive](milestones/v1.2-ROADMAP.md))
- 📋 **v1.3** — not yet defined; run `/gsd-new-milestone` to start

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

Full archive: [milestones/v1.1-ROADMAP.md](milestones/v1.1-ROADMAP.md)

</details>

<details>
<summary>✅ v1.2 Strategy Engine — SHIPPED 2026-05-08</summary>

4 phases / 17 plans on branch `master`. Replaced hardcoded `WHAT_IF_STRATEGIES` with file-driven `strategies.yaml`; multi-trigger OR-of-AND conditions; live scanner dry-run trading; stretch system decommissioned (RENAME-not-DROP per STR-04 deviation); per-strategy `/analytics` dashboard with auth gate + 5-min auto-refresh.

- [x] Phase 01: Backtest P&L Math — 2/2 plans, completed 2026-04-30
- [x] Phase 02: Strategy Engine Core — 7/7 plans (incl. 02-06 gap closure), completed 2026-04-30
- [x] Phase 03: Scanner Integration — 4/4 plans, completed 2026-05-05
- [x] Phase 04: Analytics Dashboard — 4/4 plans, completed 2026-05-08

Full archive: [milestones/v1.2-ROADMAP.md](milestones/v1.2-ROADMAP.md) · [audit](milestones/v1.2-MILESTONE-AUDIT.md)

</details>

### 📋 v1.3 (not yet defined)

Run `/gsd-new-milestone` to define requirements and phases for the next milestone.

## Backlog

### Phase 999.1: Analytics back/forward popstate sync (BACKLOG)

**Goal:** Make the browser back/forward buttons re-sync the selected strategy on `/analytics` (closes Phase 04 WR-04 advisory)
**Source phase:** 04-analytics-dashboard
**Deferred at:** 2026-05-08 during /gsd-verify-work — accepted as advisory for v1.2 close
**Severity:** minor
**Plans:**
- [ ] 999.1-01: Add `popstate` listener in `dashboard/app/analytics/page.tsx` that re-reads `?strategy=` and calls `setSelected` (or revisit the Next.js 16 Suspense workaround at page.tsx:139-141 and switch to `useSearchParams()`)

---
*Roadmap defined: 2026-04-29 (inline bootstrap, brownfield)*
*v1.2 archived: 2026-05-08*
*Phase 999.1 deferred: 2026-05-08 (Phase 04 WR-04)*
