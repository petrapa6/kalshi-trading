---
title: CONCERNS
focus: concerns
last_mapped: 2026-04-29
last_mapped_commit: f2c2f78
---

# Concerns: Tech Debt, Risks, Fragile Areas

Inventory of the load-bearing weaknesses. Severity tags follow `docs/project.md` conventions: **[Critical]** = data loss / wrong trades possible, **[High]** = correctness or security exposure, **[Medium]** = friction / maintainability, **[Low]** = polish.

## Durability & data loss

- **[Medium] SQLite at `/tmp/predictions.db` in production.** ECS task-local — wiped on restart. Durability comes from the 30-min S3 snapshot loop (`src/predictions/scanner.py::backup_db`) and the lifespan restore (`src/predictions/api.py::_download_db`). Worst-case data loss window is ~30 min on a hard crash. No EFS volume mounted; no managed DB. Fix options: shorten the backup interval, attach a persistent volume, or migrate to RDS/Aurora. Already called out in `docs/project.md` Known Issues.
- **[Medium] Backup loop is best-effort.** `backup_db` catches every exception and logs a warning (`scanner.py:776-777`); a sustained S3 failure leaves the most recent snapshot stale and there is no alerting.
- **[Medium] Soccer cache is intentionally ephemeral.** `init_soccer_db()` runs in lifespan but the file lives at `/tmp/soccer-cache.db` with no S3 backup. Every container start re-fetches against API-Football, eating the 100 req/day free-tier budget. Acceptable for now per the spec's deferred follow-up; failure mode is a `RateLimitedError` from `soccer_cache.py:96`.

## Correctness / fragile invariants

- **[High] Settlement P&L is computed in two places.** WS-driven `on_lifecycle` (`scanner.py:822-870`) and REST-poll fallback `check_settlements` / `check_stretch_settlements` (`scanner.py:202`, `707`). They differ slightly — fee subtraction, the `or "yes"` default for `stretch.side`. Editing either without editing both can silently desync stored P&L. Already flagged in `docs/project.md`.
- **[High] Integer-cents-only invariant rests on one function.** `extract_cents` in `src/predictions/kalshi_client.py:19-27` is the single boundary between Kalshi's dollar-string format and internal integer-cents. There are no tests covering it. Any future code that reads Kalshi responses directly bypasses normalization.
- **[High] Order placement still requires integer cents** even though reads are dollar strings (`POST /portfolio/orders` in `src/predictions/scanner.py::place_bet`). A driver-by author who "unifies" both paths to dollar strings will break orders silently.
- **[High] `trading_paused == "true"` kill switch is convention, not enforcement.** Order-placement code paths must call `get_config_int("trading_paused")` before placing — there is no central gate that wraps `place_bet`. New trade paths added in future could miss the check.
- **[Medium] `DRY_RUN` is read at process start only.** Toggling at runtime via env or config has no effect; only restart applies it. Easy to misunderstand because `min_yes_price` and friends *are* runtime-tunable via DB config.
- **[Medium] `_migrate_add_columns()` is the migration system.** Inline `ALTER TABLE ADD COLUMN` calls in `src/predictions/db.py:152-208`, idempotent via `inspect(engine).get_columns(...)`. No alembic / no down-migrations / no schema versioning. Acceptable now; will hurt as the schema grows or if a column needs renaming or backfilling.

## Concurrency

- **[Medium] `market_prices` is a module-level dict shared across loops.** Mutated in WS handlers (`on_ticker` in `scanner.py:807-822`), in `kalshi_scan_loop` (during cold-start population), and read by the API handler `/api/live-games`. No lock — relies on the GIL + cooperative async. A future synchronous worker (or threaded code) accessing this dict would race.
- **[Medium] `subscribed_tickers`, `ticker_sub_sid`, `lifecycle_sub_sid`** are closure state in `run_scanner`. If `ws_loop` reconnects while `kalshi_scan_loop` is in the middle of subscribing, the SIDs can drift. Code path covers the common reconnect case but is hard to reason about.

## Auth / security

- **[High] Single shared `API_TOKEN` for all callers.** Dashboard server, CLI, and any other consumer all use the same long-lived secret. No rotation, no per-client identity, no audit log. `_check_token` (`src/predictions/api.py:258`) is a constant-time-ish equality check.
- **[High] No commit-time secret scanning.** `scripts/pre-commit-check.sh` runs format + check + ty only. `CLAUDE.md` makes it the developer's manual responsibility. A leak is one careless commit away. Adding a `gitleaks` hook would close this gap.
- **[Medium] RSA private key handling.** `KalshiClient.from_key_file` reads PEM unconditionally (`src/predictions/kalshi_client.py:54`). In production the key arrives via the `KALSHI_PRIVATE_KEY` env (multi-line string) thanks to `from_key_string` (line 64). Mishandling — copy-pasting the PEM into shell history or leaving it in `.env` — is the most likely real-world failure.
- **[Medium] Dashboard password is sha256 with a hardcoded salt** (`dashboard/app/actions.ts:9`: `crypto.createHash("sha256").update(PASSWORD + "salt123").digest("hex")`). Cookie value is therefore deterministic per password. Not an authentication bypass on its own — the cookie is `httpOnly`, `secure` in prod — but it's a noticeable departure from "use bcrypt/argon2".
- **[Medium] CORS allowlist is permissive when `CORS_ORIGINS` is set sloppily.** `src/predictions/api.py:248-256` always allows `http://localhost:3777` and `http://localhost:3000`, plus whatever is in `CORS_ORIGINS`. Documented but easy to footgun.

## Tech debt / maintainability

- **[High refactor] `dashboard/app/page.tsx` is a 2972-line monolith.** Single `"use client"` component does auth, all data fetching, charts, tables. 16 internal sub-components in one file. Already flagged in `docs/project.md`. Not a bug; a maintainability cliff. Would benefit from its own brainstorm → plan → execute cycle.
- **[Medium] `src/predictions/scanner.py` is a 1039-line file** with `run_scanner` defining four nested coroutines and the on-handlers as closures. The closure-captured state makes refactoring scary. `_evaluate_what_if_strategies` (line 579) is 128 lines.
- **[Medium] `src/predictions/api.py` is 977 lines** of endpoint definitions mixed with helpers (`_run_scanner_loop`, `_download_db`, `_backup_db_sync`, `_get_live_games`, `_compute_stretch_stats`, `_format_final_minutes`). Could be split into `routes/` once it grows further.
- **[Low] `WHAT_IF_STRATEGIES` is a module-level dict.** Adding a strategy requires editing both the dict and the `_evaluate_what_if_strategies` consumer. Five strategies + a "default" near-miss bucket. Fine at the current scale.

## Operations / single point of failure

- **[Medium] One ECS Fargate task, no replicas.** Defined in `sst.config.ts` as a single `cluster.addService("Api", ...)` with `cpu: "0.25 vCPU"`, `memory: "0.5 GB"`. Restart → `_download_db` → up to 30 min of trade history can be lost (matches the durability section above). Trading windows missed during the restart window.
- **[Medium] `pnpm sst:deploy` requires `assume smooai.dev`** before invoking SST. Anyone without that AWS profile setup can't deploy. Friction, not a bug.
- **[Medium] `Dockerfile` `CACHE_BUST` arg uses `Date.now().toString()`** (`sst.config.ts:24`), which forces a rebuild of the `COPY src/` layer every deploy. Intentional but defeats Docker layer caching across deploys when only deps changed.

## Observability

- **[Medium] All telemetry is `log.info` / `log.warning` to stdout / `scanner.log`.** No structured logs, no metrics emitter, no tracing. Hard to answer "how often did the WS reconnect?", "how many orders rejected today?" without grepping a 3 MB log file.
- **[Medium] `scanner.log` is 3.2 MB on disk locally.** No rotation. If the same file lands inside the container, it'll grow until disk pressure on `/tmp`.

## Testing gaps

- **[Medium] No tests for the integer-cents boundary** (`extract_cents`, `extract_volume`). The system's most important invariant has zero coverage.
- **[Medium] No tests for the four scanner loops, `KalshiClient`, `KalshiWebSocket`, settlement logic, or `_migrate_add_columns`.** See `TESTING.md` for the full gap list.
- **[Medium] No dashboard or CLI tests at all.** No test-runner deps in either `dashboard/package.json` or `cli/package.json`.

## Recent changes worth keeping an eye on

Branch `feat/soccer-backtest`, commits `2e0c2c5` → `f2c2f78`:

- Provider swap from football-data.org to API-Football v3, including env rename `FOOTBALL_DATA_API_KEY` → `API_FOOTBALL_KEY`, batched fixture-detail calls (up to 20 ids per request), and rewritten test fixtures.
- Watch points:
  - The 100-req/day free-tier limit on API-Football. Hitting it raises `RateLimitedError` (`soccer_cache.py:96`); the API endpoint surfaces this as `503`.
  - The cache lives at `/tmp/soccer-cache.db` in prod with no S3 backup, so every container restart re-warms the cache and burns the daily quota.
- The `dashboard/app/page.tsx` and `dashboard/app/backtest/page.tsx` files have uncommitted modifications on this branch (`git status`), so the dashboard surface is mid-edit.

## In-code TODO/FIXME annotations

`grep -rinE "TODO|FIXME|XXX|HACK"` on `src/`, `dashboard/app/page.tsx`, `dashboard/app/backtest/page.tsx`, `cli/src/` returns **no matches** as of 2026-04-29. The project does not lean on inline annotations; concerns surface here and in `docs/project.md` Known Issues instead.

## Already accepted (per `docs/project.md`)

These are documented and triaged — not ignored, but not blocking either:

- The 30-min SQLite durability window in production.
- The `dashboard/app/page.tsx` monolith.

When introducing new work, treat both as constraints rather than things to opportunistically fix.
