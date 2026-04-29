---
title: CONVENTIONS
focus: quality
last_mapped: 2026-04-29
last_mapped_commit: f2c2f78
---

# Coding Conventions

Two stacks (Python backend, TS frontend/CLI) with hand-picked niche tooling: `uv` + `ruff` + `ty` for Python, `pnpm` + `oxfmt` + `oxlint` for TypeScript. Defer to the linters; this doc records the conventions that aren't auto-enforced.

## Python (backend)

### Tooling

| Concern | Tool | Config |
|---|---|---|
| Dep + venv mgmt | `uv` | `pyproject.toml`, `uv.lock` |
| Format | `ruff format` | `[tool.ruff]` in `pyproject.toml`: `line-length = 100`, `indent-width = 4` |
| Lint | `ruff check` | `[tool.ruff.lint]`: select `E F W I`, ignore `E402 E712` (import order, `== False` for SQLAlchemy filter idiom) |
| Type check | `ty` | `[tool.ty.environment]`: `python-version = "3.13"`, `python-platform = "linux"`, `root = ["src"]` |
| Build | `hatchling` (src-layout) | `[tool.hatch.build.targets.wheel] packages = ["src/predictions"]` |

Run from the repo root. The `predictions` package is installed editable via `uv sync`, so importing as `from predictions.scanner import ...` works in any cwd inside the repo.

### Style

- **Line length 100, 4-space indent.** Enforced by `ruff format`.
- **Type hints throughout.** Modern syntax: `list[str]`, `dict | None`, `Optional[int]` is also fine where mixed with `Header` etc. (see `src/predictions/api.py:258`).
- **No top-level mutable state outside `db.py` engine + `scanner.py:market_prices`.** `market_prices` is intentionally a module global because the API endpoint at `/api/live-games` reads what the scanner writes.
- **Import order is enforced by ruff `I` rule** — stdlib, third-party, local, separated.
- **`E402` (module-level import not at top) is intentionally ignored** so files like `src/predictions/scanner.py` can call `load_dotenv()` before importing modules that depend on env vars (line 23-25). Use sparingly.
- **`E712` ignored** so SQLAlchemy filter idioms like `Trade.dry_run == False` (`scanner.py:847`) don't trigger.

### Async patterns

- The whole stack is `async`/`await`. There's only one event loop (the FastAPI one); the scanner runs as `asyncio.create_task(...)` inside `lifespan` (`api.py:238`).
- Heavy I/O uses `httpx.AsyncClient` (Kalshi, ESPN, API-Football).
- `boto3` is sync — S3 backup work is fine inside async because backups are infrequent (30 min) and small.
- Shared state across loops uses `asyncio.Lock` (`espn_lock` in `run_scanner`).
- Long-lived loops are `while True: try: ... except Exception as e: log.warning(...)` followed by `await asyncio.sleep(interval)`. See `kalshi_scan_loop`, `espn_loop`, `backup_loop` in `src/predictions/scanner.py`.

### Error handling

- **Validate at boundaries; trust internal code.** Pydantic does request validation at the FastAPI boundary; downstream code assumes types.
- **Log + continue** for scanner-loop failures (warn-level, don't kill the loop). Order placement failures bubble up but are caught by the outer scan-loop try.
- **Raise `HTTPException`** from API endpoints for client-facing errors (`401`, `403`, `422`, `503`). Don't return error dicts.
- **`KalshiClient`** uses bare `httpx` exceptions; `extract_cents` and `extract_volume` *do* swallow `ValueError`/`TypeError` and return `0` because malformed prices should not crash the scanner.

### Persistence

- **SQLAlchemy 2 ORM** with declarative `Base` (`src/predictions/db.py:14`).
- **Migrations are inline `ALTER TABLE … ADD COLUMN` calls** in `_migrate_add_columns()` (`db.py:152`), idempotently checked via `inspect(engine).get_columns(...)`. No alembic. Acceptable while the schema is small; revisit if it grows.
- **Sessions are short-lived.** `get_session()` returns a fresh `SessionLocal()` and the caller is responsible for `commit()` / `close()`.
- **DRY for config** — never hardcode tunables. Add to `_CONFIG_DEFAULTS` in `db.py:217`, read with `get_config_int("key")` (`db.py:258`). Re-read every scan loop, so changes via `PUT /api/config` take effect within ~5 s.

### Naming

- snake_case modules, functions, variables.
- PascalCase for SQLAlchemy models and Pydantic models.
- `_` prefix for module-private (`_check_token`, `_download_db`, `_evaluate_what_if_strategies`, `_CONFIG_DEFAULTS`).
- DB columns are snake_case (`yes_price`, `pnl_cents`, `fee_cents`, `espn_clock_seconds`).

### Comments

- Sparse, intent-focused. Examples in code: `db.py:154` ("Add columns to existing tables if they don't exist"), `kalshi_client.py:19` ("Extract Kalshi API price, converting from string dollars if necessary").
- Module docstrings used to summarize the loop (`scanner.py:1-15` lays out the trading premise).
- Don't restate what the code says.

## TypeScript (dashboard + CLI)

### Tooling

- **Package manager**: `pnpm@10.8.1` (pinned via `packageManager` in root `package.json`).
- **Workspace**: declared in `pnpm-workspace.yaml` (`cli`, `dashboard`).
- **Formatter**: `oxfmt` (`dashboard/oxfmt.json`, `cli/` uses package defaults). 4-space indent, line width 100, ignores `.next`, `.open-next`, `node_modules`.
- **Linter**: `oxlint` (`dashboard/oxlint.json`): `no-unused-vars: warn`, `no-console: off`. Ignores `.next`, `node_modules`.
- **Type checker**: `tsc --noEmit` (root script `pnpm typecheck`).

### Style

- **4-space indent** (matches Python). Enforced by oxfmt.
- **Strict TypeScript** (default `tsc` strict mode).
- **Server actions** for any mutation triggered from the dashboard browser — see `dashboard/app/actions.ts`. Never call the backend directly from a client component.
- **Server-side proxy pattern**: all browser ↔ API requests go through `dashboard/app/api/[...path]/route.ts`, which checks `checkAuth()` and injects `Authorization: Bearer ${API_TOKEN}` server-side. The browser never sees the API token.
- **Functional React components**, no class components. Hooks where state is needed.
- **Recharts** for visualizations.

### CLI specifics

- ESM (`"type": "module"` in `cli/package.json`). Imports use `.js` suffix even for `.tsx` files (`cli/src/index.tsx:4`: `import { App } from "./app.js"`).
- Args parsed via `meow`; flags read env vars as defaults (`cli/src/index.tsx:35-50`).
- Two output modes: TUI (default) and `--json` (for scripting). Command set: `config`, `config set <k> <v>`, `stats`, `trades`.

## Config / runtime

- **DB-backed config** is canonical for runtime tunables. The flow is: defaults in `db._CONFIG_DEFAULTS` → seeded into the `config` table on `init_db()` → read every loop with `get_config_int(key)`.
- **Process env** for things that aren't supposed to change at runtime: API keys, DB path, `DRY_RUN`, `API_TOKEN`, `DB_BACKUP_BUCKET`, `CORS_ORIGINS`. The canonical schema is `.env.example`.
- **No silent feature flags.** New behaviors that need toggles get a config key.

## Pre-commit hook

`scripts/pre-commit-check.sh`:

1. On staged Python (`src/**/*.py`, `tests/**/*.py`): `ruff format`, `ruff check --fix`, re-stage, then `uv run ty check` (project-wide).
2. On staged dashboard TS (`dashboard/**/*.ts`, `dashboard/**/*.tsx`): `pnpm oxfmt`, re-stage.

What it **does not** do (per `CLAUDE.md`):

- Run `pytest`.
- Run `oxlint` or `tsc --noEmit`.
- Build the dashboard.
- Scan for secrets — that's a manual step.

Verification command before claiming done (per `CLAUDE.md`):

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check
(cd dashboard && pnpm lint && pnpm fmt:check && pnpm build)
uv run pytest tests/
```

## Commit-message style

From `git log`:

- Conventional-commits prefixes: `feat`, `fix`, `chore`, `docs`, `test`, `perf`, `refactor`.
- Optional scope in parens: `feat(soccer)`, `fix(api)`, `chore(infra)`, `docs(soccer)`.
- Subject in imperative, lower-case after the colon, no trailing period.

Examples:

```
feat(soccer): swap historical-match provider to API-Football v3 with batched fixture-detail
chore(soccer): cleanup unused test fixtures and dead helpers from provider swap
fix(api): wire init_soccer_db into lifespan + index Opportunity.found_at
perf(backtest): batch goal load + hoist imports + drop dead guard
```

## Don't-do list (from CLAUDE.md and docs/project.md)

- Don't introduce parallel converters for prices — keep it at `extract_cents`.
- Don't hardcode tunables — extend `_CONFIG_DEFAULTS` and call `get_config_int`.
- Don't bypass the `trading_paused` check on order paths.
- Don't run `docker buildx use <builder>` — global default leaks to other projects. Use `--builder <name>` per-invocation.
- Don't `--no-verify` the pre-commit hook unless explicitly asked.
- Don't commit `.env`, `predictions.db`, `scanner.log`, `__pycache__/`, `node_modules/`, `.next/`, `.sst/`, `*.pem`.
