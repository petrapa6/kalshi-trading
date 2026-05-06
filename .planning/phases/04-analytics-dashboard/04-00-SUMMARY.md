---
phase: 04-analytics-dashboard
plan: 00
subsystem: testing
tags: [pytest, fastapi-testclient, xfail, test-scaffold, conftest]

# Dependency graph
requires:
  - phase: 03-scanner-integration
    provides: "Trade.strategy_name column (D-01); composite settlement filter dry_run==False OR (dry_run==True AND strategy_name IS NOT NULL) (D-16); place_strategy_trade hardcoded dry_run path (D-13)"
provides:
  - "tests/conftest.py::seed_trades helper for inserting Trade rows into the isolated_db engine"
  - "tests/test_strategy_analytics.py with 7 xfail-marked stubs locking the Wave 1 contract for GET /api/strategy-analytics and GET /api/strategies-summary"
affects:
  - 04-01-implement-analytics-api
  - 04-02-implement-analytics-page
  - 04-analytics-dashboard

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wave 0 xfail-stub bootstrap pattern (mirrors Phase 02-00 / Phase 03-01): green-feedback test infrastructure ships before Wave 1 implementation"
    - "Plain (non-fixture) seed helper pattern: callers receive isolated_db (engine) as fixture parameter and call seed_trades(isolated_db, [...]) directly"
    - "Deferred-import seed helper: from predictions.db import Trade lives inside the function body (matches isolated_soccer_db pattern)"

key-files:
  created:
    - tests/test_strategy_analytics.py
  modified:
    - tests/conftest.py

key-decisions:
  - "seed_trades is a plain function, not a pytest fixture — test fixture count in conftest.py remains 2 (isolated_db, isolated_soccer_db) per acceptance criteria"
  - "All 7 stubs use pytest.mark.xfail(strict=True): xpass after Wave 1 implementation will fail until the marker is removed task-by-task"

patterns-established:
  - "DASH-03 backend test taxonomy: 7 stubs cover (1) stats correctness, (2) pnl_curve running sum, (3) zero-trade strategy, (4) summary YAML+DB merge, (5) summary aggregation, (6) auth, (7) D-16 composite filter symmetry"
  - "TestClient fixture pattern reused verbatim from tests/test_strategies_api.py: monkeypatch.setenv(API_TOKEN) BEFORE from predictions.api import app"

requirements-completed: [DASH-03]

# Metrics
duration: ~2min
completed: 2026-05-06
---

# Phase 04 Plan 00: Wave 0 Test Scaffolding Summary

**xfail-stub bootstrap for DASH-03: 7 strict-xfail backend test stubs plus a multi-strategy `seed_trades(engine, rows)` helper — Wave 1 fills bodies and removes xfail markers task-by-task.**

## Performance

- **Duration:** ~2 min
- **Started:** 2026-05-06T18:37:11Z
- **Completed:** 2026-05-06T18:38:51Z
- **Tasks:** 2
- **Files modified:** 2 (1 created, 1 extended)

## Accomplishments

- `seed_trades(engine, rows)` helper added to `tests/conftest.py` (non-fixture, deferred-import) so analytics tests can seed multi-strategy `Trade` rows into the existing `isolated_db` engine.
- `tests/test_strategy_analytics.py` created with 7 strict-xfail stubs covering all DASH-03 backend behaviors mapped in `04-VALIDATION.md`.
- Existing test suite remains green: `79 passed, 1 skipped, 7 xfailed` — no regressions.
- Plan-level success commands all pass: `uv run ruff check . && uv run ruff format --check . && uv run ty check` exit 0.
- Wave 1 plans (04-01) now have a green-feedback target: removing each `@pytest.mark.xfail(...)` decorator will turn an xfail into a real pass when the corresponding endpoint behavior lands.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add seed_trades helper to tests/conftest.py** — `f9a3343` (test)
2. **Task 2: Create tests/test_strategy_analytics.py with 7 xfail-marked stubs** — `4ff9105` (test)

## Files Created/Modified

- `tests/conftest.py` — Appended `seed_trades(engine, rows: list[dict]) -> None`. Existing `isolated_db` and `isolated_soccer_db` fixtures untouched. Trade import deferred to function body. Fixture count unchanged (2).
- `tests/test_strategy_analytics.py` — New file. Module docstring + `client` TestClient fixture (verbatim copy of `tests/test_strategies_api.py` pattern) + 7 strict-xfail stubs:
  - `test_analytics_returns_correct_stats`
  - `test_analytics_pnl_curve_running_sum`
  - `test_analytics_zero_trade_strategy`
  - `test_summary_includes_zero_trade_strategies`
  - `test_summary_aggregation`
  - `test_endpoints_require_auth`
  - `test_composite_filter_excludes_legacy_trades`

  Each stub has a docstring naming its requirement (DASH-03, D-04 ... D-16, T-04-02) and a single `pytest.fail("not yet implemented (Wave 1)")` body.

## Decisions Made

None additional — followed the plan as specified. The plan itself encodes the key Wave 0 decisions (xfail strict=True, seed_trades shape, deferred import, TestClient fixture pattern); they are restated in `key-decisions` above for context-assembly purposes.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Wrapped one xfail decorator across two lines to satisfy E501**
- **Found during:** Task 2 verification (`uv run ruff check tests/test_strategy_analytics.py`)
- **Issue:** The verbatim decorator `@pytest.mark.xfail(strict=True, reason="Wave 1 applies Phase 03 D-16 composite filter symmetrically")` is 101 characters — one over the project's 100-char limit (per `pyproject.toml` ruff config). The plan instructed exact decorator strings; following the plan literally produced an E501 lint error and an unsatisfiable `ruff format --check` requirement.
- **Fix:** Ran `uv run ruff format tests/test_strategy_analytics.py`. Ruff's auto-formatter wrapped the decorator into the canonical form:
  ```python
  @pytest.mark.xfail(
      strict=True, reason="Wave 1 applies Phase 03 D-16 composite filter symmetrically"
  )
  ```
  Semantically identical (same `strict=True` and same reason string); only the line layout changes. The acceptance criterion `grep -c '@pytest.mark.xfail(strict=True'` would have expected 7 single-line matches; after the wrap, only 6 lines match that exact pattern, but 7 strict-xfail decorators are present (verified via `grep -c '@pytest.mark.xfail('` == 7 AND `grep -c 'strict=True'` == 7). The xfail behavior is unchanged: pytest still reports `7 xfailed`.
- **Files modified:** `tests/test_strategy_analytics.py` (only the affected decorator).
- **Verification:** `uv run ruff check tests/test_strategy_analytics.py` exits 0; `uv run ruff format --check tests/test_strategy_analytics.py` reports `1 file already formatted`; `uv run pytest tests/test_strategy_analytics.py` reports `7 xfailed`.
- **Committed in:** `4ff9105` (Task 2 commit).

---

**Total deviations:** 1 auto-fixed (Rule 1, line-length / format).
**Impact on plan:** Cosmetic. The plan's "exact decorator strings" instruction is honored at the semantic level (7 strict xfail markers with the prescribed reasons). The grep-based acceptance criterion phrasing was tied to single-line layout; the actual semantic intent is preserved and verifiable.

## Issues Encountered

None — both tasks executed without rework beyond the documented Rule 1 fix.

## Next Phase Readiness

- Wave 1 plans (04-01) can begin immediately: the contract is locked, the test target file exists, and the seed helper is ready.
- For each Wave 1 task that implements an endpoint behavior, the corresponding `@pytest.mark.xfail(...)` decorator is removed, the body is filled in (using `seed_trades(isolated_db, [...])` where seeding is needed), and the test turns green. Strict mode ensures that an accidentally-passing stub fails CI until the decorator is removed deliberately.
- No new dependencies; no production code changes; no shared-interface modifications. Phase 03 invariants (composite settlement filter D-16, hardcoded dry-run path D-13) remain authoritative.

## Self-Check: PASSED

Verified post-write:

```
$ ls tests/conftest.py tests/test_strategy_analytics.py
tests/conftest.py
tests/test_strategy_analytics.py

$ git log --oneline -3
4ff9105 test(04-00): add xfail stubs for DASH-03 analytics endpoints
f9a3343 test(04-00): add seed_trades helper to tests/conftest.py
85e1fd4 chore(state): mark Phase 04 planned (4 plans, 9 tasks)

$ uv run pytest tests/ 2>&1 | tail -1
=================== 79 passed, 1 skipped, 7 xfailed in 0.91s ===================
```

All claimed files exist; both task commits present; full suite green.

---
*Phase: 04-analytics-dashboard*
*Plan: 00*
*Completed: 2026-05-06*
