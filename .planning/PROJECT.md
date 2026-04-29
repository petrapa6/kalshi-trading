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
- ✓ **INFRA-01**: SST v3 deploys API to ECS Fargate + dashboard via OpenNext + Cloudflare DNS — existing
- ✓ **INFRA-02**: SQLite snapshot to S3 every 30 min; restored on container start — existing

### Active

<!-- Current milestone scope. -->

- [ ] **BT-03**: Backtest page reads pre-fetched season JSONs from `resources/` (one file per league+season) instead of calling `/api/backtest/soccer`
- [ ] **BT-04**: User selects league+season via dropdown sourced from `resources/*.json` filenames
- [ ] **BT-05**: Backtest page renders graphs and strategy config purely from local JSON; the `/api/backtest/soccer` integration and the Kalshi-price-based bankroll chart are removed from the page

### Out of Scope

- Live trading changes — this milestone only touches `dashboard/app/backtest/page.tsx`. Scanner/API are untouched.
- Backend deletion of `/api/backtest/soccer` — leave the endpoint and `soccer_cache` intact; only the dashboard wiring changes.
- New season fetchers — JSONs are produced out-of-band by the existing `fetch-football-season` skill.

## Context

- Brownfield project — production deployment exists. `.planning/codebase/` (mapped on commit `f2c2f78`) is the source of truth for architecture and stack.
- Current branch `feat/soccer-backtest` shipped the API-Football v3 provider swap and added a `fetch-football-season` skill that produces season JSONs into `resources/`. Today only `epl_2024_25_season.json` exists.
- The integer-cents invariant (Kalshi prices internal cents, dollar strings only at the `kalshi_client.py` boundary) holds across the codebase. Backtest JSONs do not contain Kalshi prices, so this milestone removes price-based charts rather than re-implementing them locally.

## Constraints

- **Tech stack**: Next.js 16 + React 19 + Tailwind 4 + recharts (existing dashboard deps). No new packages without a strong reason.
- **Code style**: oxfmt + oxlint, 4-space indent (`dashboard/oxfmt.json`). `pnpm fmt:check && pnpm lint && pnpm build` must pass.
- **Auth**: Backtest page must remain behind the `checkAuth` gate (just added on commit `34b8ab7`).
- **No backend changes**: `/api/backtest/soccer` and `soccer_cache.py` stay; this is a frontend-only milestone.

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Bootstrap minimal `.planning/` scaffolding inline (skip `/gsd-new-project` deep-questioning + 4 research agents) | Brownfield repo with a complete codebase map already exists; full project workflow would re-derive what's already in `.planning/codebase/`. | — Pending |
| Replace API+Kalshi-price wiring on the backtest page with local JSON loader | Pre-fetched season JSONs give deterministic backtests without depending on the soccer cache or Kalshi prices being available. | — Pending |
| Keep `/api/backtest/soccer` endpoint in place | Backend may still be useful from CLI/scripts; only dashboard wiring changes. | — Pending |

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
*Last updated: 2026-04-29 after inline bootstrap (brownfield)*
