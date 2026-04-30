---
phase: 02-strategy-engine-core
plan: 02
subsystem: api
tags: [fastapi, pydantic, pydantic-v2, bearer-auth, response-model, strategies-endpoint]

# Dependency graph
requires:
  - phase: 02-strategy-engine-core
    provides: load_strategies + Strategy/Trigger Pydantic models (02-01); 4 xfail-marked endpoint test stubs (02-00)
provides:
  - GET /api/strategies endpoint behind Depends(_check_token) Bearer auth (T-02-01 mitigation)
  - TriggerResponse, StrategyResponse, StrategiesResponse Pydantic response models in api.py
  - response_model_exclude_none=True convention so Optional YAML fields are absent (not null) in JSON
  - 4 STR-03 endpoint tests flipped from xfail to passing (auth, response shape, YAML order, missing-file)
affects:
  - 02-03-PLAN (multi-trigger backtest engine — consumes the same Trigger shape via the JSON contract)
  - 02-04-PLAN (UI fetches /api/strategies on mount — TypeScript interface uses optional `?:` props)
  - phase 03 scanner integration (Phase 3 reuses load_strategies directly; the endpoint becomes one of two consumers, not the only one)

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "response_model_exclude_none=True on read-only catalog endpoints — absent Pydantic fields stay absent in JSON instead of becoming null. New convention; preserves operator-set/unset distinction for downstream TypeScript clients"
    - "Module-level `from predictions.strategies import load_strategies` — no circular-import risk because strategies.py does not import from api.py. Lazy import was offered as an option in 02-PATTERNS.md but rejected as unnecessary"
    - "STRATEGIES_PATH env var still read at exactly ONE site (inside load_strategies); the endpoint calls load_strategies() with no path argument so the single-source-of-truth invariant from 02-01 holds"

key-files:
  created: []
  modified:
    - src/predictions/api.py
    - tests/test_strategies_api.py
    - .planning/phases/02-strategy-engine-core/deferred-items.md

key-decisions:
  - "Module-level loader import (not lazy). 02-PATTERNS.md offered both; chose module-level because strategies.py does not import api.py (no cycle) and it surfaces the dep at module-load time which catches missing-module bugs earlier."
  - "Endpoint placed BETWEEN get_stats and get_trades. The plan suggested 'after get_stats, before get_trades' — followed verbatim. Keeps the read-only GET endpoint cluster together."
  - "Three separate response models (TriggerResponse / StrategyResponse / StrategiesResponse) instead of returning the loader's domain models directly. Mirrors api.py's existing Trade vs TradeResponse separation and lets the JSON wrapper enforce {strategies: [...]} shape independent of how the loader internally represents strategies."

requirements-completed: [STR-03]

# Metrics
duration: ~2.5min
completed: 2026-04-30
---

# Phase 2 Plan 02: GET /api/strategies Endpoint Summary

**Authenticated `GET /api/strategies` endpoint added to api.py with three Pydantic response models and `response_model_exclude_none=True` so absent YAML fields stay absent in JSON; 4 STR-03 tests flipped from xfail to passing.**

## Performance

- **Duration:** ~2.5 min
- **Started:** 2026-04-30T11:28:18Z
- **Completed:** 2026-04-30T11:30:45Z
- **Tasks:** 2
- **Files modified:** 3 (2 modified for tasks, 1 metadata for deferred-items log)

## Accomplishments

- **Endpoint shipped.** `GET /api/strategies` lives in `src/predictions/api.py` between `get_stats` and `get_trades`. Decorator carries `response_model=StrategiesResponse`, `response_model_exclude_none=True`, and `dependencies=[Depends(_check_token)]`.
- **Three response models.** `TriggerResponse`, `StrategyResponse`, `StrategiesResponse` defined in the response-models block (after `StretchStatsResponse`, before the `# --- App ---` divider). Separate from the loader's domain `Strategy`/`Trigger` models so the JSON wrapper enforces the `{strategies: [...]}` shape independently.
- **Loader integration.** `from predictions.strategies import load_strategies` added at the module top in alphabetical order after `from predictions.scanner import MIN_SCORE_LEAD`. The handler calls `load_strategies()` with no argument so STRATEGIES_PATH stays read at the single site inside the loader.
- **Threat T-02-01 mitigated.** Auth gate test (`test_endpoint_requires_auth`) confirms 401 without Bearer header. Bad-token request also returns 401 (`Invalid token`). Manual smoke test against live uvicorn confirms anonymous + bad-token requests both rejected.
- **Optional fields exclude_none verified.** Manual smoke against `strategies.yaml` shows the second `early_value` trigger (with no `max_yes_price`) returns JSON `{"sport":"soccer/esp.1","min_minute":65,"min_lead":3,"min_yes_price":88}` — the absent field is absent in the response, not null.
- **All 4 endpoint tests pass.** `tests/test_strategies_api.py` xfail markers all removed; pytest reports 4 PASSED, 0 XFAILED. Full suite: 60 passed, 1 skipped (pre-existing `test_ws`), 0 failed, no regressions.

## Task Commits

Each task was committed atomically:

1. **Task 1: feat — endpoint + response models** — `46a396d`
2. **Task 2: test — flip xfail stubs to passing** — `6989be9`

**Plan metadata commit:** appended at the end of execution.

## Files Created/Modified

### Modified

- `src/predictions/api.py` (+39 lines) — module import for `load_strategies`; three new Pydantic response models (`TriggerResponse`, `StrategyResponse`, `StrategiesResponse`); one new endpoint handler (`get_strategies`).
- `tests/test_strategies_api.py` (-8/+1 lines) — removed 4 `@pytest.mark.xfail(...)` decorators; trimmed the now-stale "Stubs are xfail-marked" docstring sentence. Test bodies unchanged.
- `.planning/phases/02-strategy-engine-core/deferred-items.md` — appended the 2 pre-existing `api.py` E501 errors to the deferred-issues log.

## Decisions Made

- **Module-level vs lazy loader import.** 02-PATTERNS.md offered the lazy form (`def get_strategies(): from predictions.strategies import load_strategies; ...`). Chose module-level because `strategies.py` has no path back to `api.py` — no circular-import risk — and module-level import surfaces missing-module errors at startup rather than first request. Aligns with how `from predictions.scanner import MIN_SCORE_LEAD` is already imported at the top of api.py.
- **Three response models, not reusing loader Strategy/Trigger.** Mirrors api.py's existing separation between SQL ORM/loader models and `*Response` API DTOs (TradeResponse, OpportunityResponse, BalanceSnapshotResponse). The wrapper response model `StrategiesResponse` lets the JSON shape `{strategies: [...]}` be enforced separately from however the loader chooses to represent strategies internally.
- **Endpoint placement.** Plan said "after get_stats, before get_trades". Followed verbatim. Logically the endpoint is read-only and clusters with the other GET handlers; placing it before `get_trades` keeps the GET block contiguous and follows insertion-order convention.
- **`load_strategies()` called without argument.** Plan was explicit (`02-PATTERNS.md` anti-pattern: don't read STRATEGIES_PATH twice). Followed verbatim. The endpoint trusts the loader to read the env var.

## Deviations from Plan

### Auto-fixed Issues

None. Both tasks executed exactly as specified in the plan.

### Out-of-scope discoveries (logged, not fixed)

**1. Pre-existing E501 errors in `src/predictions/api.py`**
- **Found during:** Task 1 verification (`uv run ruff check src/predictions/api.py` exits 1)
- **Issue:** Lines 489 and 495 of `api.py` (a long comment and an inline SQL string in `get_total_sport_stats`) violate the 100-char rule. Verified pre-existing via `git stash` baseline check — both errors exist on the file unchanged from before this plan.
- **Action:** Logged to `deferred-items.md`. Not in 02-02's blast radius. The pre-commit hook uses `ruff check --fix || true` which is non-gating, so the commit proceeded normally. Format check (`ruff format --check`) and `ty check` are clean on the file.
- **Scope:** Stand-alone lint-cleanup pass; deferred per scope-boundary rule. The 4 STR-03 xfail tests on this plan all pass.

---

**Total deviations:** 0 substantive deviations. All deliverables match plan acceptance criteria.
**Impact on plan:** None.

## Issues Encountered

- **Pre-existing `api.py` E501 errors block plan-file ruff check.** The plan's per-task `<verify>` block calls `uv run ruff check src/predictions/api.py` which exits 1 due to two long lines (489, 495) that pre-date this plan. Confirmed via `git stash` baseline. Logged to deferred-items.md and proceeded — the pre-commit hook is non-gating on lint and the commit landed clean. All my changes themselves pass ruff lint and ruff format.

## User Setup Required

None — no new environment variables, secrets, or external service configuration. The endpoint reuses the existing `API_TOKEN` Bearer auth pattern.

## Next Phase Readiness

- **Plan 02-03 (multi-trigger backtest engine) ready.** The TypeScript `Trigger` interface in 02-03 will mirror the JSON shape from this endpoint: `{ sport?: string; min_minute?: number; min_lead?: number; min_yes_price?: number; max_yes_price?: number }`. Optional fields are `?:` because of `response_model_exclude_none=True`.
- **Plan 02-04 (dashboard fetch) ready.** The dashboard's `useEffect` mount-time fetch can `fetch("/api/strategies", { cache: "no-store" })` and unwrap `data.strategies` directly. The empty-strategies case is `200 + {strategies: []}`, not 404 — UI should render the dropdown with only "— Custom —" if the array is empty, no error UI needed.
- **Phase 3 (live scanner integration) ready.** Phase 3 will reuse `load_strategies()` directly from `scanner.py` per loop, not via the API. The endpoint stays as the dashboard's data path; the scanner has a parallel direct path. Both reuse the same loader, the same `STRATEGIES_PATH` env var, and the same Pydantic models (no JSON round-trip).

## Self-Check: PASSED

- Modified files exist with expected changes:
  - FOUND: src/predictions/api.py (39 lines added; 3 response models + 1 endpoint + 1 import)
  - FOUND: tests/test_strategies_api.py (xfail count == 0)
- Commits exist on `master`:
  - FOUND: 46a396d (Task 1: feat — endpoint + models)
  - FOUND: 6989be9 (Task 2: test — flip xfail stubs)
- Acceptance grep counts (all per-plan thresholds met):
  - `from predictions.strategies import load_strategies` in api.py: 1 (==1) ✓
  - `class TriggerResponse`: 1 (==1) ✓
  - `class StrategyResponse`: 1 (==1) ✓
  - `class StrategiesResponse`: 1 (==1) ✓
  - `"/api/strategies"`: 1 (==1) ✓
  - `response_model_exclude_none=True`: 1 (==1) ✓
  - `Depends(_check_token)` on get_strategies: 1 (>=1) ✓
  - `@pytest.mark.xfail` in test_strategies_api.py: 0 (==0) ✓
- Verification commands run:
  - `uv run pytest tests/test_strategies_api.py -v` reports 4 PASSED, 0 FAILED, 0 XFAILED, 0 XPASSED
  - `uv run pytest tests/test_strategies.py tests/test_strategies_api.py -v` reports 12 PASSED total
  - `uv run pytest tests/` reports 60 passed, 1 skipped — no regressions
  - `uv run ruff format --check src/predictions/api.py tests/test_strategies_api.py` exits 0
  - `uv run ty check` exits 0 (project-wide)
  - Manual smoke against live uvicorn confirms 200 with 2-strategy JSON for auth'd request, 401 for unauth'd, 401 for bad-token request; `max_yes_price` correctly absent from `early_value` second trigger (proves `response_model_exclude_none=True`)

---

*Phase: 02-strategy-engine-core*
*Plan: 02*
*Completed: 2026-04-30*
