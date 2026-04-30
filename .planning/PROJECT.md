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
- ✓ **STR-03**: Strategy definitions drive both the backtest simulator and the live scanner — Validated in Phase 2 (backtest half; live-scanner half is DRY-01/DRY-02 in Phase 3)

### Active

<!-- v1.2 Strategy Engine — defined 2026-04-29; Phase 2 complete 2026-04-30 -->

- **BT-06**: Backtest engine uses contract-based P&L math (`contracts = floor(stake/price)`, win = `contracts × (1−price)`, loss = `contracts × price`)
- **STR-04**: `stretch_opportunities` table and `WHAT_IF_STRATEGIES` are replaced by the new strategy file system
- **DRY-01**: Live scanner evaluates strategies each loop; when triggered, records live Kalshi yes_ask price and writes a dry-run Trade row (no API call, hardcoded `dry_run=True`)
- **DRY-02**: Dry-run trades stored with `strategy_name`; P&L computed on settlement using contract math with the recorded yes_ask entry price
- **DASH-03**: New analytics dashboard page shows per-strategy trade log, P&L curve, and win rate
- **DASH-04**: Analytics page auto-refreshes to show live dry-run activity as new trades arrive

### Out of Scope

- Real-money trading — this milestone is dry-run only; `trading_paused` kill switch remains in place
- New season JSONs or backtest page UI redesign beyond the P&L math change
- CLI changes — no new CLI commands for strategy management in this milestone

## Current Milestone: v1.2 Strategy Engine

**Goal:** Replace the hardcoded strategy list with a file-driven engine that supports multi-trigger conditions, powers both backtest and live dry-run trading, and surfaces per-strategy analytics in the dashboard.

**Target features:**
- Contract-based P&L math in the backtest engine
- `strategies.yaml` replaces `WHAT_IF_STRATEGIES` + `stretch_opportunities`
- Multi-trigger (OR-of-AND) conditions in strategies
- Kalshi dry-run: live scanner places API orders per strategy with `dry_run=True`
- New analytics dashboard page with per-strategy trade log, P&L curves, win rate, auto-refresh

## Context

- Brownfield project — production deployment exists. `.planning/codebase/` (mapped on commit `f2c2f78`) is the source of truth for architecture and stack.
- v1.1 shipped 2026-04-29 on branch `feat/soccer-backtest`. The backtest page is now a fully self-contained client-side computation over 6 pre-fetched season JSONs (EPL, LaLiga, Bundesliga, Ligue 1, Serie A, MLS). No network calls after page load.
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
*Last updated: 2026-04-30 — Phase 2 (Strategy Engine Core) complete*
