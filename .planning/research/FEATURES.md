# Feature Research: v1.2 Strategy Engine

## Strategy YAML Schema

### Table Stakes

- `name` (machine key), `label` (display), `enabled` flag
- `triggers` list (OR semantics); each trigger item is a flat dict (AND semantics)
- Per-trigger fields: `sport`, `min_yes_price`, `min_lead`, `lead_pct`, `min_minute`, `max_countdown_secs`, `series_ticker`
- Missing field in a trigger = no constraint on that dimension (pass-through)

### OR-of-AND Pattern

```yaml
strategies:
  - name: early_soccer_blowout
    label: "Early Soccer Blowout"
    enabled: true
    triggers:
      - sport: soccer
        min_lead: 3
        min_minute: 65
        min_yes_price: 90
      - sport: soccer          # OR: any trigger block can fire
        min_lead: 2
        min_minute: 80
        min_yes_price: 92
```

### Differentiators (Low complexity)

- `max_yes_price` ceiling (avoid 99¢ trades with tiny upside)
- `comment` / `description` (ignored by loader, helps ops)

### Anti-Features

- Expression/formula fields in YAML (`"config.nba_lead * 0.5"`) — use `lead_pct: 50` instead
- `extends` / inheritance between strategies — flat list is enough
- Hot-reload file watching — container restart is sufficient
- Per-strategy `bet_percent` override — keep sizing in SQLite config

## Backtest P&L Math (BT-06)

### Table Stakes

- `contracts = floor(stake_cents / price_cents)` — correct discrete contract model
- Win: `contracts * (100 - price_cents)`
- Loss: `-contracts * price_cents`
- Remove `avg_win_yield` slider from backtest UI — derived from price_cents once contract math is in

## Analytics Page

### Table Stakes (all Low complexity)

- Strategy selector (tabs or dropdown pulling from `/api/strategies`)
- Cumulative P&L line chart (recharts `LineChart`, x = `placed_at`, y = running sum of `pnl_cents`)
- Summary stat cards: total trades, wins, losses, win rate, realized P&L, open positions
- Trade log table: date, ticker, price, contracts, P&L, status (filter `Trade` by `strategy_name + dry_run=True`)
- Auto-refresh every 10–15s (`setInterval` + `useEffect` cleanup)
- Auth gate via `checkAuth()` — required

### Differentiators (Low-Medium complexity)

- Per-strategy win rate vs "default" baseline comparison
- Trade frequency histogram by date (bar chart)

### Anti-Features

- Sharpe ratio, max drawdown, rolling volatility — overkill for O(100) dry-run trades
- Multi-strategy overlay charts — tab switching is sufficient
- Real-time WebSocket push — 10s polling is adequate
- Editable strategy config in UI — file-driven; YAML + restart is the workflow
- Export to CSV/PDF — out of scope

## DB + API Prerequisites

| New Thing | Complexity | Blocks |
|-----------|------------|--------|
| `strategy_name` column on `Trade` (nullable) | Low — one `ALTER TABLE` | Everything analytics |
| `GET /api/strategies` — returns loaded strategy names/labels | Low | UI strategy selector |
| `GET /api/analytics/strategies/{name}` — trade log + aggregate stats | Low | Analytics page |

## Feature Dependencies

```
strategies.yaml loader
  → scanner strategy evaluation
    → Trade.strategy_name column (one migration)
      → /api/analytics/strategies/{name}
        → analytics dashboard page (DASH-03/04)

BT-06 contract math (self-contained, no schema changes)
  → remove avg_win_yield slider

STR-04 (drop stretch_opportunities + WHAT_IF_STRATEGIES)
  → must be LAST — after analytics page is verified
```

## Open Questions

- Where does `strategies.yaml` live? Repo root (beside `pyproject.toml`) is cleanest; path configurable via `STRATEGIES_FILE` env var for ECS container.
- Does ECS bundle `strategies.yaml` in the Docker image or fetch from S3 at start?
- When STR-04 drops `stretch_opportunities`, should historical data be migrated or archived? Clarify before STR-04 to avoid a data migration surprise.
