---
title: STACK
focus: tech
last_mapped: 2026-04-29
last_mapped_commit: f2c2f78
---

# Technology Stack

Single-process FastAPI backend (with an embedded asyncio scanner) + Next.js dashboard + React-ink CLI, deployed on AWS via SST.

## Languages & Runtimes

| Layer | Language | Runtime | Pinned in |
|---|---|---|---|
| Backend | Python 3.13 | CPython 3.13.3-slim-bookworm | `pyproject.toml` (`requires-python = ">=3.13"`), `Dockerfile` |
| Dashboard | TypeScript 5 | Node (Next.js 16 server) | `dashboard/package.json` |
| CLI | TypeScript 5 (tsx loader) | Node (ESM) | `cli/package.json` (`"type": "module"`, runs via `tsx src/index.tsx`) |
| Infra | TypeScript | SST v3 / Pulumi engine | `sst.config.ts` |

## Backend (Python)

Defined in `pyproject.toml`. Direct dependencies:

| Package | Min version | Purpose |
|---|---|---|
| `fastapi` | 0.135.1 | HTTP API |
| `uvicorn` | 0.41.0 | ASGI server (`uv run uvicorn predictions.api:app …`) |
| `sqlalchemy` | 2.0.48 | ORM over SQLite |
| `httpx` | 0.28 | Async HTTP client (Kalshi REST + ESPN + API-Football) |
| `websockets` | 16.0 | Kalshi v2 WS client |
| `cryptography` | 46.0.5 | RSA-PSS signing for Kalshi auth |
| `boto3` | 1.42.63 | S3 backup uploads / restore |
| `python-dotenv` | 1.2.2 | Local `.env` loading at process start |

Pydantic is pulled in transitively by FastAPI (used for response models and the `BacktestRequest`/`BacktestResponse` schemas in `src/predictions/api.py` and `src/predictions/backtest.py`).

Dev deps (group `dev` in `pyproject.toml`): `ruff>=0.15.5`, `ty>=0.0.21`, `pytest>=8.0`, `pytest-asyncio>=0.24`.

Build system: **Hatchling** with src-layout. Wheel package is `predictions` rooted at `src/predictions` (`[tool.hatch.build.targets.wheel]`). Editable install via `uv sync`.

## Dashboard (Next.js)

Defined in `dashboard/package.json`. Next.js 16 + React 19 + Tailwind 4.

| Package | Version | Purpose |
|---|---|---|
| `next` | 16.1.6 | App-router framework |
| `react` / `react-dom` | 19.2.3 | UI runtime |
| `recharts` | ^3.8.1 | Chart components (P&L curves, histograms, backtest bankroll) |
| `react-tweet` | ^3.3.0 | Embedded tweet component |
| `zod` | ^4.0.0-beta.20250305 | Runtime schema validation |
| `tailwindcss` + `@tailwindcss/postcss` | ^4 | Styling (PostCSS pipeline via `dashboard/postcss.config.mjs`) |
| `oxfmt` | ^0.7 | Formatter |
| `oxlint` | ^0.16 | Linter |
| `typescript` | ^5 | Type checker |

Dashboard scripts (`dashboard/package.json`):

- `pnpm dev` → `next dev -p 3777`
- `pnpm build` → `next build`
- `pnpm lint` → `oxlint`
- `pnpm fmt:check` → `oxfmt --check .`

## CLI (React-ink)

Defined in `cli/package.json`. ESM-only.

| Package | Version | Purpose |
|---|---|---|
| `ink` | ^6.8.0 | Terminal UI |
| `ink-big-text` | ^2.0.0 | Banner |
| `meow` | ^13.2.0 | Argument parsing |
| `react` | ^19.0.0 | Component runtime |
| `tsx` | ^4.19.0 (dev) | TypeScript loader |

Entry: `cli/src/index.tsx` (parses args via `meow`, then renders `<App>` from `cli/src/app.tsx`).

## Infrastructure

Defined in `sst.config.ts` and `Dockerfile`.

- **SST v3** (`sst@^4.2.2` in root `package.json`) drives infra.
- **AWS region**: `us-east-2`.
- **Compute**: `sst.aws.Cluster` → ECS Fargate task with `cpu: "0.25 vCPU"`, `memory: "0.5 GB"`. NAT EC2 `t3.micro`.
- **Storage**: `sst.aws.Bucket("DbBackups")` (`linked` to the API service so it gets IAM access).
- **Dashboard hosting**: `sst.aws.Nextjs("Dashboard", { path: "dashboard" })` (OpenNext).
- **DNS / TLS**: Cloudflare via `sst.cloudflare.dns()` for both API and dashboard subdomains. Cloudflare provider is enabled (`cloudflare: true`).
- **Container**: Two-step `Dockerfile` — `uv sync --frozen --no-dev --no-install-project` first (caches deps), then `COPY src/`, then a second `uv sync` to install the package itself. `CACHE_BUST` build-arg is bumped each `sst:deploy` (`Date.now().toString()`).

Process command: `uv run uvicorn predictions.api:app --host 0.0.0.0 --port 8000`.

Public surface: `443/https → 8000/http`, attached to `api.your-domain.example` (placeholder in committed config).

## SST Secrets

Created in `sst.config.ts::run`:

- `DashboardPassword` → injected as `DASHBOARD_PASSWORD` env on the dashboard Nextjs service
- `KalshiApiKey` → `KALSHI_API_KEY` on the API
- `KalshiPrivateKey` → `KALSHI_PRIVATE_KEY` on the API
- `ApiToken` → `API_TOKEN` on both API and dashboard
- `ApiFootballKey` → `API_FOOTBALL_KEY` on the API

Set per stage with `npx sst secret set <Name> <value>`.

## Tooling Conventions

| Tool | Where | Notes |
|---|---|---|
| `uv` | Python deps + run | `uv sync`, `uv run …`. Lockfile `uv.lock` is committed. |
| `pnpm@10.8.1` | JS workspace mgr | Pinned via `packageManager` in root `package.json`. Workspace declared in `pnpm-workspace.yaml`: `cli/`, `dashboard/`. |
| `ruff` | Python format + lint | `line-length = 100`, `indent-width = 4`. Selected rules: `E`, `F`, `W`, `I`. Ignored: `E402`, `E712`. |
| `ty` | Python type check | `python-version = "3.13"`, `python-platform = "linux"`, `root = ["src"]`. |
| `pytest` + `pytest-asyncio` | Python tests | `asyncio_mode = "auto"`, `testpaths = ["tests"]`. |
| `oxfmt` | TS format | `dashboard/oxfmt.json` and `cli/` use 4-space indent, line width 100. |
| `oxlint` | TS lint | Config at `dashboard/oxlint.json` (`no-unused-vars: warn`, `no-console: off`). |

`scripts/pre-commit-check.sh` runs ruff format + check + ty on staged Python, and oxfmt on staged dashboard TS. **Does not** run pytest, oxlint, or any secret scan.

## Top-level Scripts (root `package.json`)

- `pnpm dev` → `sst dev` (full stack via SST)
- `pnpm dev:api` → uvicorn on `:8000` with `--reload`
- `pnpm dev:dashboard` → Next.js on `:3777`
- `pnpm sst:deploy` / `pnpm sst:remove` → AWS deploy/remove (assumes `smooai.dev` AWS profile via `assume`)
- `pnpm cli` → run the CLI workspace (`pnpm --filter cli start`)
- `pnpm pre-commit-check` → `bash scripts/pre-commit-check.sh`

## Configuration Surfaces

| Source | Lifecycle | Examples |
|---|---|---|
| Process env (`.env` locally, SST in prod) | Read at process start; some at every call | `KALSHI_API_KEY`, `KALSHI_PRIVATE_KEY[_PATH]`, `API_TOKEN`, `DRY_RUN`, `DATABASE_URL`, `DB_BACKUP_BUCKET`, `API_FOOTBALL_KEY`, `SOCCER_CACHE_DB_PATH`, `CORS_ORIGINS`, `MIN_YES_PRICE`, `BET_PERCENT`, `POLL_INTERVAL_SECONDS` |
| SQLite `config` table (`predictions.db::config`) | Re-read every scan loop (~5 s) | `min_yes_price`, `bet_percent`, `max_positions`, `min_volume`, `stretch_price_min`, `trading_paused`, `lead:<sport>/<league>`, `final_seconds:<sport>/<league>`. Defaults in `src/predictions/db.py::_CONFIG_DEFAULTS`. |
| In-code constants | Process start | `WHAT_IF_STRATEGIES` in `src/predictions/scanner.py:261-298`, `KALSHI_TO_ESPN` and `SPORT_FINAL_PERIOD` in `src/predictions/espn.py:16-44`. |

The canonical env schema is `.env.example` at the repo root; `.env` is gitignored.
