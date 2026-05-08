# Kalshi Trading Scanner

## What This Is

A Python + TypeScript system that scans Kalshi sports prediction markets, cross-references live game state from ESPN (and historical match data from API-Football for soccer backtesting), and buys YES contracts at 88–99¢ on games that are already effectively decided. Single FastAPI process embeds the scanner as an asyncio task; a read-only Next.js dashboard and a React-ink CLI consume the API over Bearer-auth HTTPS. Production runs on AWS ECS Fargate via SST.

## Core Value

Capture the lag between actual game state and Kalshi's market re-pricing — every settled YES contract pays $1, so buying late, near-certain YES at 88–99¢ has a structural edge.

## Requirements

### Validated

<!-- Existing, shipped capabilities — confirmed by codebase map. -->

- ✓ **SCAN-01**: Scanner cross-references Kalshi markets with ESPN scoreboards each loop — existing
- ✓ **SCAN-02**: Scanner places (or dry-runs) YES orders when min_yes_price + min_lead + min_minute filters all pass — existing
- ✓ **SCAN-03**: Settlements reconcile via Kalshi WebSocket primary + REST fallback every loop — existing
- ✓ **SCAN-04**: WHAT_IF_STRATEGIES continuously shadow-backtest parameter relaxations on live data — existing
- ✓ **CFG-01**: Runtime config (`min_yes_price`, `bet_percent`, `trading_paused`, etc.) re-read from SQLite every scan loop — existing
- ✓ **CFG-02**: `trading_paused == "true"` is the kill switch — checked before any order placement — existing
- ✓ **DASH-01**: Read-only dashboard renders stats, trades, opportunities, and balance curves — existing
- ✓ **DASH-02**: Dashboard authenticates via password cookie; API_TOKEN never reaches the browser — existing
- ✓ **CLI-01**: React-ink CLI views/edits runtime config, stats, and trades over Bearer auth — existing
- ✓ **BT-01**: `/api/backtest/soccer` simulates the strategy over historical API-Football matches with cached match + goal data — existing
- ✓ **BT-02**: Backtest dashboard page lets user tune league, dates, min_minute, min_lead, min_yes_price, initial_balance, bet_percent — existing
- ✓ **BT-03**: Backtest page reads pre-fetched season JSONs from `resources/` (one file per league+season) instead of calling `/api/backtest/soccer` — v1.1
- ✓ **BT-04**: User selects league+season via dropdown sourced from `resources/*.json` filenames — v1.1
- ✓ **BT-05**: Backtest page renders graphs and strategy config purely from local JSON; the `/api/backtest/soccer` integration and the Kalshi-price-based bankroll chart are removed from the page — v1.1
- ✓ **INFRA-01**: SST v3 deploys API to ECS Fargate + dashboard via OpenNext + Cloudflare DNS — existing
- ✓ **INFRA-02**: SQLite snapshot to S3 every 30 min; restored on container start — existing
- ✓ **BT-07**: Backtest page strategy dropdown populated from `strategies.yaml` pre-populates parameter sliders (sliders stay editable) — Validated in Phase 2
- ✓ **STR-01**: Named strategies are defined in a `strategies.yaml` file (replaces `WHAT_IF_STRATEGIES` hardcoded list in `scanner.py`) — Validated in Phase 2 (loader half; scanner replacement is STR-04 in Phase 3)
- ✓ **STR-02**: Each strategy supports multi-trigger conditions: OR-of-AND sets (e.g. "goal_diff ≥ 3 at minute ≥ 20 OR goal_diff ≥ 2 at minute ≥ 75") — Validated in Phase 2
- ✓ **STR-03**: Strategy definitions drive both the backtest simulator and the live scanner — Validated in Phase 2 (backtest half) + Phase 3 (live-scanner half via `evaluate_strategies` + `place_strategy_trade`)
- ✓ **BT-06**: Backtest engine uses contract-based P&L math (`contracts = floor(stake/price)`, win = `contracts × (1−price)`, loss = `contracts × price`) — Validated in Phase 1
- ✓ **STR-04**: `stretch_opportunities` table renamed to `stretch_opportunities_archived` (NOT dropped, per S3-backup safety); `WHAT_IF_STRATEGIES` + `_evaluate_what_if_strategies` removed; `/api/sport-stats` re-sourced from `opportunities` (D-19) — Validated in Phase 3
- ✓ **DRY-01**: `place_strategy_trade` hardcodes `dry_run=True`/`status="dry_run"`/`yes_price=opp["yes_ask"]` — never calls Kalshi REST regardless of process-level `DRY_RUN`; `trading_paused == "true"` early-exits `evaluate_strategies` (D-23) — Validated in Phase 3
- ✓ **DRY-02**: Settlement filter widened to `Trade.dry_run==False OR (dry_run==True AND strategy_name IS NOT NULL)` (D-16); P&L on dry-run strategy trades computed via contract math on recorded `yes_ask` — Validated in Phase 3
- ✓ **DASH-03**: New `/analytics` dashboard page (auth-gated) renders per-strategy stat cards, cumulative P&L curve (settled_at axis per D-09 — semantically correct for realized P&L), and trade log; backed by `GET /api/strategy-analytics` + `GET /api/strategies-summary` (Bearer auth) — Validated in Phase 4
- ✓ **DASH-04**: Analytics page auto-refreshes every 5 minutes via `setInterval(fetchAll, 5*60*1000)`; `lastUpdated` state ticks per fetch — Validated in Phase 4

### Active

<!-- v1.3 — TBD; defined via /gsd-new-milestone -->

(none — v1.2 shipped 2026-05-08; v1.3 not yet defined)

### Out of Scope

- Real-money trading — this milestone is dry-run only; `trading_paused` kill switch remains in place
- New season JSONs or backtest page UI redesign beyond the P&L math change
- CLI changes — no new CLI commands for strategy management in this milestone

## Current State

**Shipped:** v1.2 Strategy Engine (2026-05-08). 4 phases, 17 plans. All 10 v1.2 REQ-IDs validated; STR-04 satisfied via documented RENAME-not-DROP deviation. See `.planning/MILESTONES.md` and `.planning/milestones/v1.2-*.md` for archive.

## Next Milestone Goals

v1.3 not yet defined. Likely candidates (operator judgement):
- Phase 999.1 backlog: analytics back/forward popstate sync (WR-04)
- WAL mode or read replica for SQLite if analytics polling pressure increases under multi-tab use
- Strategy editor in dashboard UI (deferred from v1.2 Future Requirements; requires max-file-size check before `safe_load`)
- Hot-reload of `strategies.yaml` (deferred — open dry-run trades under changed strategies create mismatched state)

## Context

- Brownfield project — production deployment exists. `.planning/codebase/` (mapped on commit `f2c2f78`) is the source of truth for architecture and stack.
- v1.1 shipped 2026-04-29 on branch `feat/soccer-backtest`. The backtest page is now a fully self-contained client-side computation over 6 pre-fetched season JSONs (EPL, LaLiga, Bundesliga, Ligue 1, Serie A, MLS). No network calls after page load.
- v1.2 shipped 2026-05-08 on `master`. Strategy engine + analytics dashboard. 88/88 unit tests + 1 skipped; Phase 04 security audit clean (`threats_open: 0`).
- The integer-cents invariant (Kalshi prices internal cents, dollar strings only at the `kalshi_client.py` boundary) holds across the codebase. Backtest JSONs do not contain Kalshi prices; the v1.1 milestone removed price-based charts entirely.
- Known tech debt: hand-maintained static import catalog in `seasons.ts` requires editing for each new season JSON; pre-existing `pnpm fmt:check` failures in `app/page.tsx` and surrounding files.
- The pending contract-based P&L todo (`.planning/todos/pending/2026-04-29-backtest-contract-based-pnl.md`) is a v1.2 target.

## Constraints

- **Tech stack**: Next.js 16 + React 19 + Tailwind 4 + recharts (existing dashboard deps). No new packages without a strong reason.
- **Code style**: oxfmt + oxlint, 4-space indent (`dashboard/oxfmt.json`). `pnpm fmt:check && pnpm lint && pnpm build` must pass.
- **Auth**: All new dashboard pages must be behind the `checkAuth` gate.
- **Kill switch**: `trading_paused == "true"` must be checked before any dry-run order placement, same as live trades.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Bootstrap minimal `.planning/` scaffolding inline (skip `/gsd-new-project` deep-questioning + 4 research agents) | Brownfield repo with a complete codebase map already exists; full project workflow would re-derive what's already in `.planning/codebase/`. | ✓ Good — saved significant time with no loss of planning quality |
| Replace API+Kalshi-price wiring on the backtest page with local JSON loader | Pre-fetched season JSONs give deterministic backtests without depending on the soccer cache or Kalshi prices being available. | ✓ Good — removes a runtime dependency; backtest now works offline and deterministically |
| Keep `/api/backtest/soccer` endpoint in place | Backend may still be useful from CLI/scripts; only dashboard wiring changes. | ✓ Good — minimal blast radius; endpoint preserved for future use |
| Use static imports over `import.meta.glob` for season catalog | Next.js 16 Webpack doesn't support `import.meta.glob` without a custom loader; static imports bundle JSON at build time and satisfy `output: standalone`. | ✓ Good — clean build, correct standalone trace; trade-off (hand-maintained catalog) documented |
| Execute v1.1 as quick tasks rather than formal GSD phases | Scope was tightly contained to `dashboard/app/backtest/`; quick tasks move faster with less planning overhead for sub-day work. | ✓ Good — 4 tasks executed in a single session; overhead appropriate to scope |
| [Phase 03] Rename `stretch_opportunities` → `stretch_opportunities_archived` instead of dropping (D-03) | Production has 6+ months of stretch data; tested rename against S3 backup. Drop = data loss, rename = idempotent + reversible. | ✓ Good — table preserved; ORM class deleted (D-20) so fresh DBs don't recreate it |
| [Phase 03] Hardcode `dry_run=True` + `yes_price=opp["yes_ask"]` in `place_strategy_trade` (D-13) | Strategies are local-simulation-only by design; honoring process-level `DRY_RUN` would let real trades fire by accident if the env var is ever flipped. Single boundary mirrors the `extract_cents` invariant. | ✓ Good — DRY-01 invariant enforced at the call site; structurally impossible to violate |
| [Phase 03] Settlement filter `dry_run==False OR (dry_run==True AND strategy_name IS NOT NULL)` (D-16) | Real trades always have `strategy_name=NULL`; strategy fires always have it set. The composite filter lets one settlement loop reconcile both populations without branching. | ✓ Good — closes DRY-02; Phase 04 analytics queries depend on this composite |
| [Phase 03] `connect_args timeout=5` on the SQLAlchemy engine (D-02) | Phase 4 analytics polling will compete with the scanner's per-loop writes. SQLite's default lock timeout is 0; 5s is a generous buffer without masking real deadlocks. | ✓ Good — pre-emptive; revisit if WAL or read replica is needed under load |
| [Phase 03] UK terminology: `football` not `soccer` for sport-family literals (D-08) | Operator preference + ESPN's `sport_path` already uses `soccer/`, so the family literal is the natural place to draw the terminology boundary. | ✓ Good — `SPORT_FAMILY_TO_PATHS` is the only translation surface; YAML strategies stay UK-style |
| [Phase 04] `/analytics` page chart x-axis uses `settled_at` not `placed_at` (D-09 vs DASH-03) | DASH-03 specified `placed_at`; D-09 implemented `settled_at` because the chart shows realized P&L, which only settled trades contribute to. User approved at Phase 04 verification. | ✓ Good — semantically correct for a realized-P&L curve; documented as adjustment in v1.2-REQUIREMENTS archive |
| [Phase 04] CR-01 `Trade.settled_at` writer fix (post-execution gap closure) | Phase 03 added the `settled_at` column but never wrote it from either settlement path; Phase 04 verification surfaced the empty-chart symptom. Atomic 3-commit fix (writer + idempotent backfill + tests) closed the gap; verification re-run flipped 6/8 → 8/8. | ✓ Good — caught at the right phase boundary; idempotent backfill handles historical rows; cross-phase contracts now durable |
| [Phase 04] Composite filter for `/api/strategy-analytics` mirrors D-16 settlement filter | Symmetry between read path (analytics) and write path (settlement) — if the schema ever evolves to allow `dry_run=False` strategy attribution, both paths shift together. | ✓ Good — WR-01 advisory notes the outer `strategy_name == :name` makes part of the filter redundant today, but the symmetry is intentional defense-in-depth |
| [Phase 04] Skip git tag at v1.2 close | Operator judgement (2026-05-08) — milestone artifacts (audit + archive + MILESTONES.md entry) capture the cut without a tag. | — Pending — revisit if release tags become useful for deployment correlation |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-05-08 — v1.2 Strategy Engine milestone shipped*
