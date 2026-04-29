# Requirements: v1.2 Strategy Engine

**Milestone:** v1.2 — Strategy Engine
**Status:** Active
**Defined:** 2026-04-29

---

## Requirements

### Backtest Engine

- [ ] **BT-06**: User backtests use contract-based P&L math: `contracts = floor(stake_cents / price_cents)`, win profit = `contracts × (100 − price_cents)`, loss = `contracts × price_cents`; the `avg_win_yield` input is removed from the backtest UI

- [ ] **BT-07**: The backtest page has a strategy selector dropdown populated from `strategies.yaml`; selecting a strategy pre-populates the parameter sliders (sport, min_lead, min_minute, min_yes_price, max_yes_price) with that strategy's first trigger values; sliders remain fully editable so users can explore custom variations after loading a preset

### Strategy Definition

- [ ] **STR-01**: Named strategies are defined in a `strategies.yaml` file at the repo root (path overridable via `STRATEGIES_PATH` env var), replacing the hardcoded `WHAT_IF_STRATEGIES` list in `scanner.py`; missing file → scanner logs a warning and proceeds with no strategies

- [ ] **STR-02**: Each strategy in `strategies.yaml` supports multi-trigger (OR-of-AND) conditions: a `triggers` list where each entry is a flat dict of AND conditions, and any one entry matching fires the strategy; supported trigger fields: `sport`, `min_lead`, `min_minute`, `min_yes_price`, `max_yes_price`; missing field in a trigger = no constraint on that dimension

- [ ] **STR-03**: Strategy definitions in `strategies.yaml` drive both the backtest simulator and the live scanner (single source of truth for strategy logic)

- [ ] **STR-04**: The `stretch_opportunities` DB table is dropped and `WHAT_IF_STRATEGIES` is removed from `scanner.py`; the existing `GET /api/sport-stats` endpoint is updated to derive game counts from the `opportunities` table instead

### Dry-Run Trading

- [ ] **DRY-01**: The live scanner evaluates all enabled strategies from `strategies.yaml` each scan loop; when a strategy's trigger conditions are met for a market, the scanner fires a dry-run trade: no Kalshi API call is made, but the live `yes_ask` price from the market_prices cache (fetched via WebSocket/REST) is recorded as the entry price, hardcoded `dry_run=True` regardless of the process-level `DRY_RUN` env var

- [ ] **DRY-02**: Dry-run strategy trades are stored in the `trades` table with a new `strategy_name` column; the recorded `yes_price` (live Kalshi yes_ask at signal time) is used to compute contract-based P&L on settlement: `contracts = floor(bet_amount / yes_price)`, win = `contracts × (100 − yes_price)`, loss = `−contracts × yes_price`; settlement reconciliation runs for these trades (via WebSocket primary + REST fallback)

### Analytics Dashboard

- [ ] **DASH-03**: A new dashboard page shows per-strategy dry-run performance: strategy selector, summary stat cards (total trades, wins, losses, win rate, realized P&L), cumulative P&L line chart (x = `placed_at`, y = running P&L sum), and a trade log table (date, ticker, price, contracts, P&L, status); page is behind the `checkAuth` gate

- [ ] **DASH-04**: The analytics page auto-refreshes every 5 minutes to show new dry-run activity without a manual reload

---

## Future Requirements

- `lead_pct` trigger field (% of runtime config `min_lead`, e.g. `lead_pct: 75`) — deferred; flat values sufficient for v1.2
- `max_countdown_secs` and `series_ticker` trigger fields — deferred; core fields sufficient for v1.2
- Per-strategy `bet_percent` override — keep sizing in SQLite config for now
- Hot-reload of `strategies.yaml` without container restart — open dry-run trades under changed strategies create mismatched state; design needed
- Strategy editor in the dashboard UI — file-driven config is the v1.2 design

---

## Out of Scope

- Real-money trading — this milestone is dry-run only; `trading_paused` kill switch remains in place
- Kalshi demo/sandbox environment integration — local simulation is sufficient for the 2-week observation goal
- CLI commands for strategy management — out of scope for v1.2
- New season JSONs or backtest page UI redesign beyond BT-06

---

## Traceability

| REQ-ID | Phase | Notes |
|--------|-------|-------|
| BT-06 | — | |
| BT-07 | — | |
| STR-01 | — | |
| STR-02 | — | |
| STR-03 | — | |
| STR-04 | — | |
| DRY-01 | — | |
| DRY-02 | — | |
| DASH-03 | — | |
| DASH-04 | — | |
