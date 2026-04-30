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
