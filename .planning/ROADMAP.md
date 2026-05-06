# Roadmap: Kalshi Trading Scanner

## Overview

This roadmap is bootstrapped retroactively for an existing brownfield project. v1.0 is the pre-GSD production scanner; v1.1 refactored the backtest dashboard page onto local season JSONs. v1.2 replaces the hardcoded strategy system with a YAML-driven strategy engine and analytics dashboard.

## Milestones

- ✅ **v1.0 Production Scanner** — shipped pre-GSD, see PROJECT.md Validated section
- ✅ **v1.1 Local-JSON Backtest** — shipped 2026-04-29
- 🚧 **v1.2 Strategy Engine** — Phases 1–4 (in progress)

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

### 🚧 v1.2 Strategy Engine (In Progress)

**Milestone Goal:** Replace the hardcoded strategy list with a file-driven engine supporting multi-trigger conditions, power both backtest and live dry-run trading, and surface per-strategy analytics in the dashboard.

- [x] **Phase 1: Backtest P&L Math** - Replace yield-based math with contract-based P&L in the backtest engine — completed 2026-04-30
- [x] **Phase 2: Strategy Engine Core** - Build `strategies.py` + `strategies.yaml`, wire into backtest — completed 2026-04-30 (gap-closure 02-06 closed UAT Test 7)
- [ ] **Phase 3: Scanner Integration** - DB migration, strategy evaluation in live scanner, stretch system removal
- [ ] **Phase 4: Analytics Dashboard** - Per-strategy analytics API endpoints and dashboard page

## Phase Details

### Phase 1: Backtest P&L Math
**Goal**: The backtest engine computes P&L using contract-based math, removing the avg_win_yield approximation
**Depends on**: Nothing (first phase)
**Requirements**: BT-06
**Success Criteria** (what must be TRUE):
  1. Backtest results use `contracts = floor(stake / price)`, `win = contracts × (1 − price)`, `loss = contracts × price` — verifiable by checking output against manual calculation for one match
  2. The `avg_win_yield` input is gone; a `contract_price` input (default 97, range 50–99 cents) drives the new math; existing sliders (`min_minute`, `min_lead`) remain and function.
  3. `pnpm fmt:check && pnpm lint && pnpm build` passes with no new failures
**Plans**: 2 plans
- [x] 01-01-PLAN.md — Contract-based P&L math in backtest engine + roadmap criterion #2 rewrite
- [x] 01-02-PLAN.md — Gap closure: reverse-chronological display + zero-contract tally exclusion + tri-state TradeRow (closes UAT Test 3 & Test 6)

### Phase 2: Strategy Engine Core
**Goal**: Named strategies defined in `strategies.yaml` drive both the backtest simulator and can be validated against historical data before touching the live scanner
**Depends on**: Phase 1
**Requirements**: STR-01, STR-02, STR-03, BT-07
**Success Criteria** (what must be TRUE):
  1. A `strategies.yaml` file exists at the repo root with at least one named strategy using OR-of-AND triggers; the scanner logs a warning and runs with no strategies if the file is missing
  2. Backtest page strategy dropdown is populated from `strategies.yaml`; selecting a strategy pre-fills parameter sliders with the strategy's first trigger values; sliders remain editable (per CONTEXT.md D-11: sliders = sport, min_minute, min_lead; min_yes_price/max_yes_price = read-only info text)
  3. Empty trigger block (`triggers: []` or a trigger with no fields) is rejected at load time — Pydantic validation enforces `min_length=1` on trigger lists and individual trigger dicts
  4. `uv run ruff check . && uv run ruff format --check . && uv run ty check` passes clean
**Plans**: 7 plans
- [x] 02-00-PLAN.md — Bootstrap: pyyaml dep, .env.example, starter strategies.yaml, test fixtures + xfail stubs (Wave 0)
- [x] 02-01-PLAN.md — Pydantic loader (`src/predictions/strategies.py`) + STR-01/STR-02 tests (Wave 1)
- [x] 02-02-PLAN.md — `GET /api/strategies` Bearer-auth endpoint + STR-03 tests (Wave 2)
- [x] 02-03-PLAN.md — Multi-trigger backtest engine + season sport_path mapping (Wave 2)
- [x] 02-04-PLAN.md — Backtest UI: strategy dropdown, per-trigger cards, +/-, sport-mismatch graying (Wave 3, has manual checkpoint)
- [x] 02-05-PLAN.md — Goal-backward verification + STATE.md update (Wave 4, has manual checkpoint)
- [x] 02-06-PLAN.md — Gap closure (UAT Test 7): drop Live-trading info text from backtest trigger cards + record D-11 UI-retraction in CONTEXT.md
**UI hint**: yes

### Phase 3: Scanner Integration
**Goal**: The live scanner evaluates strategies each loop and records dry-run trades; the stretch system is decommissioned
**Depends on**: Phase 2
**Requirements**: STR-04, DRY-01, DRY-02
**Success Criteria** (what must be TRUE):
  1. `stretch_opportunities` table is renamed to `stretch_opportunities_archived` (not dropped); `WHAT_IF_STRATEGIES` is removed from `scanner.py`; `GET /api/sport-stats` returns correct game counts derived from the `opportunities` table
  2. When a strategy trigger fires for a live market, a `Trade` row is written with `dry_run=True`, `strategy_name` set, and `yes_price` = the live `yes_ask` from `market_prices` cache — no Kalshi API call is made regardless of the process-level `DRY_RUN` env var
  3. `trading_paused == "true"` prevents dry-run strategy trades from being written, same as live trades
  4. Settlement reconciliation processes `dry_run=True AND strategy_name IS NOT NULL` trades (WebSocket primary + REST fallback); P&L is computed using contract math on the recorded `yes_ask` entry price
  5. `connect_args` in `db.py` includes `"timeout": 5` to prevent `SQLITE_BUSY` errors under concurrent analytics polling
**Plans**: 4 plans
- [x] 03-01-PLAN.md — Wave 0 test scaffolding (3 new test files + tests/test_sport_stats.py D-22 migration; xfail stubs)
- [x] 03-02-PLAN.md — Wave 1 schema migration (db.py: D-01 strategy_name + D-02 timeout=5 + D-03 rename + D-20 ORM removal)
- [x] 03-03-PLAN.md — Wave 2 scanner integration (sport mapping + evaluate_strategies + place_strategy_trade + paused gate D-23 + settlement filters D-16/D-17 + WHAT_IF removal)
- [x] 03-04-PLAN.md — Wave 3 api + dashboard cleanup (D-19 sport-stats from opportunities + D-21 endpoint + dashboard Strategy-tab deletion)

### Phase 4: Analytics Dashboard
**Goal**: Users can inspect per-strategy dry-run performance in the dashboard with live-updating data
**Depends on**: Phase 3
**Requirements**: DASH-03, DASH-04
**Success Criteria** (what must be TRUE):
  1. A new dashboard page (behind `checkAuth` gate) shows a strategy selector, summary stat cards (total trades, wins, losses, win rate, realized P&L), and a cumulative P&L line chart for the selected strategy
  2. A trade log table on the analytics page shows per-trade detail (date, ticker, entry price, contracts, P&L, status) for the selected strategy
  3. The page auto-refreshes every 5 minutes; new dry-run trades appear without a manual reload
  4. Strategies with zero trades appear in the selector but show empty charts and zeroed stat cards rather than 404 or blank page
**Plans**: 4 plans
- [ ] 04-00-PLAN.md — Wave 0 test scaffolding (xfail stubs in tests/test_strategy_analytics.py + seed_trades helper in tests/conftest.py)
- [ ] 04-01-PLAN.md — Wave 1 backend endpoints (TradeResponse.strategy_name + GET /api/strategy-analytics + GET /api/strategies-summary with YAML+DB merge for zero-trade strategies)
- [ ] 04-02-PLAN.md — Wave 2 analytics page (dashboard/app/analytics/page.tsx — auth gate + sidebar mini-stats + stat cards + recharts P&L chart + trade log + 5-min auto-refresh)
- [ ] 04-03-PLAN.md — Wave 3 dashboard integration (Trade TS interface + header Analytics link + trades-table strategy-name cross-links)
**UI hint**: yes

## Progress

**Execution Order:** 1 → 2 → 3 → 4

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| v1.0 Production Scanner (aggregate) | v1.0 | — | ✅ Complete | pre-GSD |
| v1.1 Local-JSON Backtest (4 quick tasks) | v1.1 | 4/4 | ✅ Complete | 2026-04-29 |
| 1. Backtest P&L Math | v1.2 | 2/2 | ✅ Complete | 2026-04-30 |
| 2. Strategy Engine Core | v1.2 | 6/7 | Gap closure (02-06) in flight | 2026-04-30 |
| 3. Scanner Integration | v1.2 | 0/4 | Planned (waves 0-3) | - |
| 4. Analytics Dashboard | v1.2 | 0/4 | Planned (waves 0-3) | - |

---
*Roadmap defined: 2026-04-29 (inline bootstrap, brownfield)*
*v1.2 phases added: 2026-04-29*
