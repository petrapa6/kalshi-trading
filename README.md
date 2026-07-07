# Kalshi Trading Scanner

Automated scanner that watches live sports games across multiple leagues, cross-references ESPN scores with Kalshi YES contract prices, and buys YES at 88–99¢ on games that are already effectively decided. Settled contracts pay $1; the edge comes from Kalshi's market lag behind live game state.

**Disclaimer.** This software is provided as-is. Prediction markets involve real financial risk and regulatory constraints that vary by jurisdiction. Run with `DRY_RUN=true` first (see [How to dry-run](#how-to-dry-run)), review every trade placed, and do not deploy with real funds unless you understand the strategy, the risks, and your local regulations.

---

## Architecture

```mermaid
graph TD
    ESPN["ESPN API<br/>scores, periods, clocks · 10s poll"]
    KWS["Kalshi WebSocket<br/>real-time prices + settlements"]
    KREST["Kalshi REST API<br/>discover markets, place orders · 5s"]
    SCANNER["Scanner<br/>Python / asyncio"]
    DB["SQLite on /tmp (prod)<br/>S3 snapshots every 30 min<br/>trades, balance, opportunities"]
    API["FastAPI<br/>/api/*"]
    DASH["Next.js dashboard"]

    ESPN --> SCANNER
    KWS --> SCANNER
    SCANNER --> DB
    SCANNER --> KREST
    DB --> API
    API --> DASH
```

The scanner runs four concurrent async loops inside a single FastAPI process:

| Loop               | Source      | Cadence   | Purpose                                          |
|--------------------|-------------|-----------|--------------------------------------------------|
| ESPN poll          | ESPN REST   | 10 s      | Live game state (score, period, clock)           |
| Kalshi API scan    | Kalshi REST | 5 s       | Discover markets, evaluate filters, place orders |
| WebSocket listener | Kalshi WS   | real-time | Streaming price ticks + settlement events        |
| DB backup          | S3          | 30 min    | SQLite snapshot upload                           |

For deeper architecture detail (scanner loops, settlement duality, integration surfaces), see [`.planning/codebase/ARCHITECTURE.md`](.planning/codebase/ARCHITECTURE.md) and the rest of [`.planning/codebase/`](.planning/codebase/).

---

## Tech Stack

| Layer     | Tools                                                               |
|-----------|---------------------------------------------------------------------|
| Backend   | Python 3.13, FastAPI, SQLAlchemy 2, SQLite, `asyncio`, `websockets` |
| Dashboard | Next.js 16, React 19, Tailwind CSS 4                                |
| CLI       | React-ink TUI (`cli/`)                                              |
| Tooling   | `uv`, `ruff`, `ty`, `pnpm`, `oxfmt`, `oxlint`                       |
| Infra     | SST v3, AWS ECS, S3, OpenNext, Cloudflare DNS                       |

---

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/) (Python package manager — replaces pip)
- [`pnpm`](https://pnpm.io) ≥ 10 (JS package manager)
- Node.js ≥ 20 (required by Next.js 16)
- Docker (optional — for local container builds)
- A [Kalshi API key + RSA private key](https://kalshi.com/sign-up/api)
- For deployment only: AWS account in `us-east-2` and a Cloudflare account with API token

---

## Install

### Automatic

```bash
./install.sh
```

The script:

1. Checks for `uv`, `pnpm`, Node ≥ 20 (warns if `docker` is missing).
2. Runs `uv sync` to create `.venv` and install Python deps + the `predictions` package.
3. Runs `pnpm install` at the root, in `dashboard/`, and in `cli/`.
4. Copies `.env.example` → `.env` if `.env` does not already exist.
5. Installs `scripts/pre-commit-check.sh` as the git pre-commit hook (skipped if no `.git`).
6. Prints a "next steps" block.

Safe to re-run: each step is idempotent.

### Manual

If you prefer to run the steps yourself:

```bash
uv sync
pnpm install
(cd dashboard && pnpm install)
(cd cli && pnpm install)
cp .env.example .env  # then edit .env
ln -sf ../../scripts/pre-commit-check.sh .git/hooks/pre-commit  # if git repo
```

---

## Configuration

All runtime configuration is read from environment variables. See [`.env.example`](.env.example) for the canonical list; copy it to `.env` and fill in the values.

Scanner tuning (min YES price, bet percentage, per-sport score leads, etc.) lives in the SQLite `config` table and is re-read by the scanner every loop (≈ 5 s). Initial values come from `src/predictions/db.py::_CONFIG_DEFAULTS`.

### Runtime config keys

**Trading parameters**

| Key                 | Default | Description                                      |
|---------------------|---------|--------------------------------------------------|
| `min_yes_price`     | 91      | Minimum YES ask price in cents to place a bet    |
| `bet_percent`       | 10      | Percentage of available cash to bet per match    |
| `max_positions`     | 20      | Maximum concurrent open positions                |
| `min_volume`        | 50      | Minimum market volume for liquidity              |
| `stretch_price_min` | 85      | Minimum YES price for stretch (shadow) tracking  |
| `trading_paused`    | false   | If `"true"`, the scanner stops placing real bets |

**Per-sport minimum score lead** — keys like `lead:basketball/nba`, `lead:hockey/nhl`. Current defaults live in `db.py`; the NBA/NCAAMB defaults are `12`, NFL/NCAAFB `10`, MLB `3`, NHL/soccer `2`, UFC `0`.

**Per-sport end-of-game timing** — keys like `final_seconds:basketball/nba` (countdown sports: clock ≤ value) or `final_seconds:soccer/eng.1` (count-up sports: clock ≥ value). See `db.py` for defaults.

---

## How to dry-run

Dry-run mode runs the **full live pipeline** — ESPN polling, Kalshi market
discovery, WebSocket price ticks, balance reads, and the complete bet-decision
logic — but skips the final order placement. Instead of sending an order to
Kalshi, the scanner writes the would-be trade to SQLite with status
`dry_run` and logs `[DRY RUN] Order not placed`.

Dry-run is controlled by the `DRY_RUN` environment variable. It defaults to
`true` everywhere except production (`sst.config.ts` sets `DRY_RUN=false` on
the deployed ECS service; `sst dev` keeps it `true`).

> **Note:** dry-run still requires real Kalshi API credentials. Market
> discovery, prices, and the balance snapshot are all live reads — only
> order placement is suppressed. There is no fully-offline mode.

### 1. Configure

```bash
cp .env.example .env   # if you haven't already (install.sh does this)
```

Edit `.env` and set at minimum:

```bash
KALSHI_API_KEY=your-key-id
KALSHI_PRIVATE_KEY_PATH=./secrets/kalshi.pem   # or inline KALSHI_PRIVATE_KEY
DRY_RUN=true                                    # already the default
```

### 2. Run

```bash
pnpm dev:api
```

Startup logs confirm the mode: `Starting scanner: … dry_run=True`.

Dry-run only produces trades while games are live **and** near their end
(high YES price + big score lead). Run it during an active game window for
NBA/NFL/etc., otherwise expect the scanner to idle — that's normal.

### 3. Inspect results

Any of:

```bash
pnpm cli trades                 # recent trades — dry-run rows show status "dry_run"
pnpm cli stats                  # includes a dry_run_trades count
sqlite3 predictions.db "SELECT ticker, count, yes_price, cost_cents, placed_at
                        FROM trades WHERE status='dry_run' ORDER BY id DESC LIMIT 20;"
```

Or open the dashboard at http://localhost:3777 (`pnpm dev:dashboard` in a
second terminal).

Dry-run trades are excluded from real P&L stats (`dry_run=1` in the DB), so
they never pollute live accounting.

### Going live

Set `DRY_RUN=false` in `.env` and restart. Two further locks apply on top of
`DRY_RUN`:

- the `trading_paused` runtime config key (set via `pnpm cli config set
  trading_paused true`) stops real order placement without a restart;
- `max_positions` caps concurrent exposure.

The [Home Assistant add-on](#run-as-a-home-assistant-add-on-dry-run-only)
hardcodes `DRY_RUN=true` in `run.sh` and cannot go live.

---

## Usage

### Local development

Start the API + scanner (runs four async loops inside uvicorn):

```bash
pnpm dev:api     # equivalent to `uv run uvicorn predictions.api:app --host 0.0.0.0 --port 8000 --reload`
```

Start the dashboard (separate terminal):

```bash
pnpm dev:dashboard   # Next.js on http://localhost:3777
```

### CLI

A React-ink TUI that talks to the API over HTTPS with a Bearer token:

```bash
pnpm cli config                      # show current config (TUI)
pnpm cli config set min_yes_price 90 # update a config key
pnpm cli stats                       # summary stats
pnpm cli trades                      # recent trades

# JSON output for scripting
pnpm cli stats --json
pnpm cli trades --json | jq '.trades[0]'
```

The CLI reads `API_TOKEN` and `GETRICH_API_URL` from the environment (or `--token` / `--api-url` flags).

### Direct Python invocation

Local DB access (no API round-trip):

```bash
uv run python -m predictions.config_cli                    # show all config
uv run python -m predictions.config_cli set bet_percent 5
uv run python -m predictions.config_cli delete bet_percent  # revert to default
uv run python -m predictions.config_cli reset               # reset all overrides
```

Run the API without Docker:

```bash
uv run uvicorn predictions.api:app --reload
```

### Docker

```bash
docker build -t kalshi-trading .
docker run --rm -p 8000:8000 --env-file .env kalshi-trading
```

### Updating runtime config remotely

```bash
curl -X PUT https://your-api-domain.example/api/config \
  -H "Authorization: Bearer $API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key": "min_yes_price", "value": "92"}'
```

---

## Deployment

SST v3 provisions the full AWS stack from [`sst.config.ts`](sst.config.ts):

- VPC with EC2-based NAT (to keep cost low).
- ECS Fargate service running the API + scanner in a single container.
- S3 bucket for periodic DB snapshots.
- Next.js dashboard via OpenNext (Lambda + CloudFront).
- Cloudflare DNS records for both the API and the dashboard.

### First-time setup

```bash
# Set SST secrets (not env vars — these are encrypted at rest in AWS)
npx sst secret set KalshiApiKey "your-kalshi-api-key-id"
npx sst secret set KalshiPrivateKey "-----BEGIN RSA PRIVATE KEY-----\n…"
npx sst secret set DashboardPassword "your-dashboard-password"
npx sst secret set ApiToken "your-api-bearer-token"
```

Update the `domain.name` fields in `sst.config.ts` to your own domain before deploying.

### Deploy

```bash
pnpm sst:deploy       # assumes direnv + `assume` for AWS SSO; adjust to your setup
pnpm sst:remove       # tear down
```

---

## Development

```bash
# Format + lint Python
uv run ruff format .
uv run ruff check . --fix
uv run ty check

# Run the pytest suite (async tests via pytest-asyncio)
uv run pytest tests/

# Format + lint dashboard
(cd dashboard && pnpm fmt && pnpm lint)

# Run the pre-commit hook manually against staged changes
bash scripts/pre-commit-check.sh
```

The WebSocket test auto-skips when `KALSHI_API_KEY` is not set, so the
suite runs cleanly in any dev environment without live credentials.

The pre-commit hook (installed by `install.sh` or manually symlinked to `.git/hooks/pre-commit`) runs `ruff format` + `ruff check --fix` + `ty check` on staged `src/` and `tests/` Python files, and `oxfmt` on staged dashboard TS/TSX.

---

## Run as a Home Assistant add-on (dry-run only)

This repo ships as a HA add-on alongside the SST/AWS deploy. The add-on
runs the scanner and dashboard in a single container, exposes the
dashboard on port 8000, and stores SQLite + strategies under `/data`
(included in HA backups). `DRY_RUN=true` is hardcoded in `run.sh` and
`trading_paused=true` is seeded on first boot — three independent
locks prevent live orders.

### One-time setup

1. **Add the add-on repository.** In HA → Settings → Add-ons → Add-on
   Store → ⋮ (top right) → Repositories → paste:

   ```
   https://github.com/petrapa6/kalshi-trading
   ```

2. **Install "Kalshi Trading"** from the now-visible repo entry. HA
   Supervisor builds the image on-device (first build takes ~5–10 min on
   a Raspberry Pi).

3. **Configure secrets** in the add-on's Configuration tab:
   - `kalshi_api_key` — from Kalshi
   - `kalshi_private_key` — PEM contents, multi-line
   - `api_token` — generate with `openssl rand -hex 32`
   - `dashboard_password` — login password
   - `api_football_key` — optional, only for soccer backtest

4. **Start the add-on.** Watch the log for `[kalshi] Seeded
   trading_paused=true (first boot)` and `[kalshi] next started`.

### Expose via Cloudflare Tunnel

1. Install the [Cloudflared HA add-on](https://github.com/brenner-tobias/ha-addons)
   if not already installed.
2. In its config, add an ingress rule:

   ```yaml
   - hostname: trading.petra-czech.cc
     service: http://homeassistant.local:8000
   ```

3. In Cloudflare DNS, create a CNAME for `trading.petra-czech.cc`
   pointing at the tunnel UUID (Cloudflare's dashboard handles this
   automatically when you create the tunnel).

### Gate access with Cloudflare Access

1. In Cloudflare Zero Trust → Access → Applications → Add an application
   (Self-hosted).
2. Application domain: `trading.petra-czech.cc`.
3. Policy: include rule "Emails: petracekpav@gmail.com" (one-time PIN or
   Google OAuth).

Cloudflare Access is defense-in-depth. The dashboard password is the
second lock; if you skip Access setup entirely the add-on is still
protected by the password.

### Updates

`Settings → Add-ons → Kalshi Trading → ⋮ → Check for updates` pulls the
latest commit from `master` and rebuilds the image. `/data/predictions.db`
and `/data/strategies.yaml` survive upgrades.

### Local build (for HAOS parity testing)

```bash
docker build -t kalshi-trading:local .
docker run --rm -p 8000:8000 \
    -v "$(pwd)/.haos-smoke-data:/data" \
    --env-file .haos-smoke.env \
    kalshi-trading:local
```

Open `http://localhost:8000`. The existing `pnpm dev:api` + `pnpm
dev:dashboard` workflow is unchanged and remains the fast inner loop.

---

## License

See [`LICENSE`](LICENSE).
