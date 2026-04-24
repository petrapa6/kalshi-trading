# Kalshi Trading Scanner — Claude guidance

Session rules for working in this repo. For architecture, data flow, and module-level structure, read [`docs/project.md`](docs/project.md)

## Quick commands

```bash
./install.sh                         # one-shot bootstrap (uv + pnpm + env + hook)
pnpm dev:api                         # API + scanner on :8000 (needs .env)
pnpm dev:dashboard                   # Dashboard on :3777
pnpm cli config                      # TUI: show config (needs API_TOKEN env)
uv run ruff check . && uv run ruff format --check . && uv run ty check
(cd dashboard && pnpm lint && pnpm fmt:check && pnpm build)
uv run pytest tests/                 # pytest suite (async via pytest-asyncio)
pnpm sst:deploy                      # Production deploy (needs AWS + Cloudflare)
```

## Stack at a glance

- **Backend**: Python 3.13, FastAPI, SQLAlchemy 2, SQLite, `asyncio`, `websockets`.
- **Dashboard**: Next.js 16 + React 19 + Tailwind CSS 4 (read-only UI).
- **CLI**: React-ink TUI under `cli/` (preferred over direct DB access).
- **Infra**: SST v3 → AWS ECS Fargate + S3 + Cloudflare DNS.

## Tooling conventions

- **Python**: `uv` (not pip/poetry), `ruff` (not black/flake8/isort), `ty`
  (not mypy/pyright). Run from the repo root — the `predictions` package is
  installed editable via hatchling's src-layout.
- **JS/TS**: `pnpm` (not npm/yarn), `oxfmt` + `oxlint` (not
  prettier/eslint). Dashboard uses 4-space indent per `oxfmt.json`.
- **No dev server in a CI sense**: local dev uses `pnpm dev:api` +
  `pnpm dev:dashboard`, or full stack in Docker via `sst dev`.
- **CLI first**: for config changes, stats, and trade inspection, prefer
  `pnpm cli …` over hitting the API with curl or touching the DB.

## Core invariants (do not violate)

- **Internal prices are integer cents (0–100).** The single boundary where
  Kalshi's dollar-string format enters is `src/predictions/kalshi_client.py`
  — `extract_cents()` and `extract_volume()`. Everywhere else, prices are
  integers. Do not introduce parallel converters.
- **Order placement still takes integer cents** even though reads are
  strings. `yes_price` / `no_price` in `POST /portfolio/orders` are ints.
- **Runtime config lives in the SQLite `config` table**, read each scan
  loop (~5 s). Defaults are in `src/predictions/db.py::_CONFIG_DEFAULTS`.
  Call `get_config_int("key")` — never hardcode.
- **`trading_paused == "true"`** is the kill switch. Check before any
  order-placement code path you touch.
- **`DRY_RUN` env var** is read at process start only. Real trades have
  `dry_run=False`; dry runs have `status="dry_run"` and are excluded from
  `/api/stats` counts.
- **`DATABASE_URL` default** = `sqlite:///<repo-root>/predictions.db`
  (computed from `__file__` in `db.py`, so it always lands at the repo
  root regardless of CWD). Production overrides to `/tmp/predictions.db`
  in the Docker container, with durability via S3 snapshots every 30 min.
- **CLI auth**: `pnpm cli …` requires `API_TOKEN` in env (or `--token`).
  Point it at a non-default backend with `GETRICH_API_URL` or `--api-url`.

## Security

- **Never commit secrets.** API tokens, Kalshi keys, Cloudflare tokens,
  passwords, and `*.pem` files must never appear in tracked files.
  Use `$API_TOKEN`, `$KALSHI_API_KEY` placeholders in docs.
- **Secrets sources**: SST secrets (`npx sst secret set …`) for
  production; `.env` (gitignored) for local. The canonical schema is
  [`.env.example`](.env.example).
- **Before every commit**: scan staged changes for secrets (API keys,
  tokens, `BEGIN * PRIVATE KEY`, passwords). If found, abort and fix.
- The pre-commit hook (`scripts/pre-commit-check.sh`) does formatting and
  type-checking but does NOT scan for secrets — do the scan yourself.

## Working relationship

- Be direct and concise. No sycophancy. Challenge assumptions.
- Always prefer the correct fix over the quick one.
- Don't add features, refactoring, or new abstractions beyond what the
  task requires. Don't design for hypothetical future requirements.
- Don't add error handling, fallbacks, or validation for cases that can't
  happen. Trust framework guarantees; validate only at system boundaries.
- Default to writing no comments. Only add one when the WHY is non-obvious.
- When touching shared interfaces (Trade/Opportunity schemas, config keys,
  API endpoints), flag the blast radius and ask before restructuring.

## Autonomy bounds

- Act without asking when the change is reversible, contained to existing
  files, no external side effects, clearly within the current task.
- Ask before: creating new files, adding/removing dependencies, changing
  shared interfaces, touching CI or infra (`sst.config.ts`, `Dockerfile`).
- When unsure, state the action + intent in one line before doing it.

## Git + commits

- Ask before committing unless the user says otherwise.
- Write clear summary commit messages; prefer multiple logical commits
  over one giant one.
- Never amend pushed commits. Never `--no-verify` hooks unless explicitly
  asked.
- Never commit `.env`, `.env.local`, `predictions.db`, `scanner.log`, or
  anything under `__pycache__/` / `node_modules/` / `.next/` / `.sst/`.

## Verification before claiming done

- Python: `uv run ruff check . && uv run ruff format --check . && uv run ty check`.
- Dashboard: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`.
- For backend behaviour changes, start the API locally (`pnpm dev:api`)
  and hit the affected endpoint. `curl http://localhost:8000/` returns
  `{"status": "ok"}` when healthy.
- Don't claim a UI change works without loading the dashboard in a
  browser — type checking isn't feature checking.

## Code Intelligence

Prefer LSP over Grep/Glob/Read for navigation:
- `goToDefinition` / `goToImplementation` to jump to source.
- `findReferences` before renaming or changing a signature.
- `workspaceSymbol` / `documentSymbol` / `hover` for discovery.
- Grep/Glob only for text/pattern searches where LSP doesn't help.

After writing or editing code, pause briefly for LSP, then check
diagnostics. Fix type errors and missing imports immediately.

---

@docs/project.md
