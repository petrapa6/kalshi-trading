# Deferred Items — Phase 02 Strategy Engine Core

Pre-existing issues discovered during execution. Not in scope for this plan.

## ~~Pre-existing ruff E501 errors in src/predictions/scanner.py~~ — RESOLVED in 02-05

- ~~16 E501 (line too long) errors in `src/predictions/scanner.py` around lines 645-672.~~
- Resolved by commit `613f7e4` (`chore(lint): clear pre-existing ruff debt for
  Phase 2 Criterion #4`) during 02-05 finalization. The actual count was 4 in
  scanner.py (the "16" figure conflated all repo-wide E501s). Fixed by wrapping
  long comments at logical boundaries; no behavior change.

## ~~Pre-existing ruff format violations in tests/test_ws.py~~ — RESOLVED in 02-05

- ~~`uv run ruff format --check .` reports `tests/test_ws.py` as needing
  reformatting (verified via baseline check; pre-dates Plan 02-00).~~
- Resolved by commit `613f7e4` via `ruff format`.

## ~~Pre-existing ty unresolved-import diagnostics~~ — RESOLVED (no action needed)

- ~~`uv run ty check` reports 8 diagnostics (verified via baseline check;
  pre-dates Plan 02-00). Mostly `unresolved-import` warnings.~~
- Resolved transparently — `uv run ty check` reports `All checks passed!` as of
  02-05 verification. Likely a side effect of dep installations during 02-00
  (PyYAML, pytest, etc.) populating the resolver's cache.

## ~~Pre-existing ruff E501 errors in src/predictions/api.py~~ — RESOLVED in 02-05

- ~~2 E501 (line too long) errors in `src/predictions/api.py` at lines 489
  and 495 (a comment and a SQL string literal in `get_total_sport_stats`).~~
- Resolved by commit `613f7e4`. Comment wrapped; SQL string split across two
  string literals (Python implicit concatenation), no semantic change.

## ~~Undocumented but pre-existing E501 in src/predictions/config_cli.py:14~~ — RESOLVED in 02-05

- 1 E501 in `src/predictions/config_cli.py:14` — surfaced during 02-05's full-repo
  ruff sweep, was NOT logged in deferred-items.md previously. Verified pre-existing
  via `git log` (file last touched in `c6111ea`, well before Phase 2).
- Resolved by commit `613f7e4`. Trimmed two help-text comments in the CLI
  docstring; no behavior change (docstrings are display-only).

## ~~Undocumented but pre-existing E501s in .claude/skills/fetch-football-season/scripts/fetch_football_season.py~~ — RESOLVED in 02-05

- 9 E501 errors at lines 33-40 and 160 in the LEAGUES dict alignment + an
  argparse line. Pre-existing per `git log` (introduced in `4bc9a44`,
  pre-Phase-2).
- Resolved by commit `613f7e4` via `ruff format` — the formatter collapsed the
  column-aligned LEAGUES dict to single-spaced fields, dropping all 9 lines
  below the 100-char limit. No semantic change.

## Pre-existing oxfmt failures in dashboard/

- `cd dashboard && pnpm fmt:check` fails on 3 files: `app/actions.ts`,
  `app/api/[...path]/route.ts`, `sst-env.d.ts`. Verified pre-existing
  during Plan 02-03 baseline (these files are unrelated to 02-03's
  modifications in `app/backtest/`).
- The 3 files in 02-03's blast radius (`app/backtest/seasons.ts`,
  `app/backtest/backtest.ts`, `app/backtest/page.tsx`) are fmt-clean.
- Scope: stand-alone formatter pass — `pnpm fmt` would auto-fix all 3.
  Not in 02-03's blast radius. Note: not blocking Phase 2 Criterion #4
  (which scopes to Python tooling only).
