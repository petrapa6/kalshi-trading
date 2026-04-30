# Deferred Items — Phase 02 Strategy Engine Core

Pre-existing issues discovered during execution. Not in scope for this plan.

## Pre-existing ruff E501 errors in src/predictions/scanner.py

- 16 E501 (line too long) errors in `src/predictions/scanner.py` around lines 645-672.
- These predate Plan 02-00 (verified via `git stash` baseline check).
- Scope: clean these up in a dedicated lint-cleanup task or as side work in
  Phase 03 when scanner.py is modified for STR-04 / DRY-01.

## Pre-existing ruff format violations in tests/test_ws.py

- `uv run ruff format --check .` reports `tests/test_ws.py` as needing
  reformatting (verified via baseline check; pre-dates Plan 02-00).
- Scope: stand-alone format pass.

## Pre-existing ty unresolved-import diagnostics

- `uv run ty check` reports 8 diagnostics (verified via baseline check;
  pre-dates Plan 02-00). Mostly `unresolved-import` warnings.
- Scope: defer to a typed-environment cleanup task; ty is a young checker
  and most diagnostics are about optional dependencies it cannot resolve.

## Pre-existing ruff E501 errors in src/predictions/api.py

- 2 E501 (line too long) errors in `src/predictions/api.py` at lines 489
  and 495 (a comment and a SQL string literal in `get_total_sport_stats`).
- Verified pre-existing via `git stash` baseline check during Plan 02-02.
- Scope: stand-alone lint cleanup pass; not in 02-02's blast radius.

## Pre-existing oxfmt failures in dashboard/

- `cd dashboard && pnpm fmt:check` fails on 3 files: `app/actions.ts`,
  `app/api/[...path]/route.ts`, `sst-env.d.ts`. Verified pre-existing
  during Plan 02-03 baseline (these files are unrelated to 02-03's
  modifications in `app/backtest/`).
- The 3 files in 02-03's blast radius (`app/backtest/seasons.ts`,
  `app/backtest/backtest.ts`, `app/backtest/page.tsx`) are fmt-clean.
- Scope: stand-alone formatter pass — `pnpm fmt` would auto-fix all 3.
  Not in 02-03's blast radius.
