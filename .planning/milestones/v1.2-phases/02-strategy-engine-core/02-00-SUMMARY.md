---
phase: 02-strategy-engine-core
plan: 00
subsystem: infra
tags: [pyyaml, pydantic, pytest, xfail, yaml, fixtures, bootstrap]

# Dependency graph
requires:
  - phase: 01-backtest-p-l-math
    provides: contract-based backtest engine that Wave 1 will rewire to consume Trigger[]
provides:
  - pyyaml>=6.0 declared dep + uv.lock entry (only justified Python dep for Phase 2)
  - strategies.yaml at repo root with 2 active strategies + 5 commented WHAT_IF translations
  - STRATEGIES_PATH env var documented in .env.example
  - tests/fixtures/strategies-{good,empty,malformed,unknown-field}.yaml fixture set
  - tests/test_strategies.py + tests/test_strategies_api.py with 12 xfail-marked stubs
affects:
  - 02-01-PLAN (loader implements load_strategies, flips 8 stubs in test_strategies.py)
  - 02-02-PLAN (endpoint implements GET /api/strategies, flips 4 stubs in test_strategies_api.py)
  - 02-03-PLAN (multi-trigger engine consumes the strategies catalog)
  - 02-04-PLAN (UI fetches /api/strategies on mount)
  - phase 03 scanner integration (Phase 3 reuses load_strategies and STRATEGIES_PATH)

# Tech tracking
tech-stack:
  added: [pyyaml>=6.0]
  patterns:
    - "YAML fixture-file directory under tests/fixtures/ (new convention; previously tests used in-memory DB only)"
    - "xfail-stub-first Wave 0 pattern: per-test ID stubs marked @pytest.mark.xfail(reason=\"Wave N implements ...\") so Wave 1 plans can reference test IDs in <verify> blocks without producing red bars before implementation"

key-files:
  created:
    - strategies.yaml
    - tests/test_strategies.py
    - tests/test_strategies_api.py
    - tests/fixtures/strategies-good.yaml
    - tests/fixtures/strategies-empty.yaml
    - tests/fixtures/strategies-malformed.yaml
    - tests/fixtures/strategies-unknown-field.yaml
    - .planning/phases/02-strategy-engine-core/deferred-items.md
  modified:
    - pyproject.toml
    - uv.lock
    - .env.example

key-decisions:
  - "Used `uv add pyyaml>=6.0` (canonical command) instead of hand-editing pyproject.toml + `uv sync`; uv inserted the entry in alphabetical position automatically"
  - "STRATEGIES_PATH env var line stays commented out in .env.example because the default (`strategies.yaml` relative to CWD) already resolves correctly in dev (repo root) and prod (Dockerfile WORKDIR=/app)"
  - "tests/fixtures/strategies-empty.yaml created via `:` redirect (zero bytes), not `touch` plus content; `yaml.safe_load(open(...))` returns None for zero-byte files which is the loader path Wave 1 must handle explicitly"
  - "All five WHAT_IF translations (low_price, lower_price, loose_leads, early_entry, yolo) shipped as commented YAML blocks with note that lead_pct does not translate cleanly to flat min_lead — operators choose representative per-league values when uncommenting"
  - "Wrote test stubs without importing predictions.strategies at module scope; lazy `from predictions.strategies import load_strategies` inside each test body so xfail collection succeeds before Wave 1 creates the module"

patterns-established:
  - "Wave 0 bootstrap: declared deps + fixtures + xfail stubs ship together so Wave 1 plans have green-feedback infrastructure already in place when they begin"
  - "STRICT YAML fixtures: tests/fixtures/strategies-*.yaml each exercise exactly one loader path (happy / empty / malformed / unknown-field) — keeps fixture files focused and one-purpose"

requirements-completed: [STR-01, STR-02, BT-07]

# Metrics
duration: ~5min
completed: 2026-04-30
---

# Phase 2 Plan 00: Strategy Engine Bootstrap Summary

**PyYAML dep added, repo-root strategies.yaml shipped with 2 active + 5 commented WHAT_IF translations, four loader fixture YAMLs and twelve xfail-marked pytest stubs prepared so Wave 1 plans can reference test IDs without producing red bars at first commit.**

## Performance

- **Duration:** ~5 min
- **Started:** 2026-04-30T11:10:22Z
- **Completed:** 2026-04-30T11:14:57Z
- **Tasks:** 3
- **Files modified:** 11 (4 modified, 7 created)

## Accomplishments

- **PyYAML dependency declared.** `uv add pyyaml>=6.0` placed the entry alphabetically between `python-dotenv` and `sqlalchemy` in pyproject.toml; uv.lock now resolves pyyaml==6.0.3.
- **STRATEGIES_PATH documented.** `.env.example` gains a "--- Strategies engine ---" section explaining the env var; line stays commented out because the default resolves correctly in both dev and prod.
- **Starter strategies catalog.** `strategies.yaml` at repo root ships with two active strategies (`conservative_late_lead`, `early_value`) plus all five WHAT_IF_STRATEGIES translated as commented YAML blocks (with caveats about `lead_pct` non-translation).
- **Four fixture YAMLs.** `tests/fixtures/strategies-{good,empty,malformed,unknown-field}.yaml` exercise the four loader paths Wave 1 must handle: happy path, zero-byte file (`yaml.safe_load → None`), `triggers: []` (Pydantic `min_length=1` reject), unknown field via `min_minutes` typo (Pydantic `extra="forbid"` reject).
- **Twelve xfail-marked test stubs.** `tests/test_strategies.py` (8 stubs covering STR-01/02 incl. `yaml.safe_load` vs `!!python/object` security check T-02-03) and `tests/test_strategies_api.py` (4 stubs covering STR-03 endpoint behavior). All stubs lazy-import `predictions.strategies` and `predictions.api` so collection succeeds before Wave 1 creates the loader module. Pytest reports 12 xfailed; ruff and ruff format clean on these files.

## Task Commits

Each task was committed atomically:

1. **Task 1: Add pyyaml dep + update .env.example** — `5dc0cc8` (chore)
2. **Task 2: Create starter strategies.yaml + test fixture YAMLs** — `1cd62df` (chore)
3. **Task 3: Create xfail-marked test stubs** — `6cc21cd` (test)

**Plan metadata commit:** appended at the end of execution.

## Files Created/Modified

### Created

- `strategies.yaml` — repo-root strategy catalog (D-05 shape: `strategies:` mapping → `description?` + `triggers` list); 2 active strategies + 5 commented WHAT_IF translations
- `tests/fixtures/strategies-good.yaml` — happy-path single-strategy fixture
- `tests/fixtures/strategies-empty.yaml` — zero-byte file (Wave 1 loader must handle `yaml.safe_load → None`)
- `tests/fixtures/strategies-malformed.yaml` — strategy with `triggers: []` (rejected by `min_length=1` in Wave 1)
- `tests/fixtures/strategies-unknown-field.yaml` — trigger with `min_minutes` typo (rejected by `extra="forbid"` in Wave 1)
- `tests/test_strategies.py` — 8 xfail-marked stubs for the loader (`load_empty_file`, `missing_file_returns_empty`, `valid_file_loads`, `strategies_path_env`, `empty_triggers_rejected`, `unknown_field_rejected`, `one_bad_strategy_rejects_file`, `yaml_safe_load_rejects_python_object_tags`)
- `tests/test_strategies_api.py` — 4 xfail-marked stubs for the endpoint (`endpoint_requires_auth`, `endpoint_response_shape`, `endpoint_preserves_yaml_order`, `endpoint_missing_file_returns_empty`)
- `.planning/phases/02-strategy-engine-core/deferred-items.md` — log of pre-existing lint/format/ty issues out of scope for this plan

### Modified

- `pyproject.toml` — `pyyaml>=6.0` added to `[project] dependencies` (alphabetical order)
- `uv.lock` — pyyaml==6.0.3 entry resolved
- `.env.example` — new "--- Strategies engine ---" section documenting `STRATEGIES_PATH`

## Decisions Made

- **`uv add` over hand-edit + `uv sync`.** Plan suggested either path; chose canonical `uv add pyyaml>=6.0` for atomic pyproject.toml + uv.lock update. uv placed the entry in correct alphabetical position automatically — no manual reorder needed.
- **STRATEGIES_PATH stays commented.** Default (`strategies.yaml` relative to CWD) resolves correctly in dev (repo root) and prod (Dockerfile WORKDIR=/app), so the variable is documented but not active.
- **Updated `.env.example` comment to satisfy `grep -c 'STRATEGIES_PATH' == 2` acceptance.** The plan's verbatim snippet had STRATEGIES_PATH appearing only on the var line itself. To meet the acceptance count, prepended `STRATEGIES_PATH —` to the description sentence so both occurrences exist (one in description, one on the commented variable line).
- **Lazy imports inside test bodies.** All tests `from predictions.strategies import load_strategies` inside the function body, not at module top-level — so collection succeeds even though Wave 1 has not created `predictions.strategies` yet.

## Deviations from Plan

None substantive. Two minor adjustments tracked:

### Adjustments

**1. [Adjustment - Acceptance match] Reworded `.env.example` comment to mention STRATEGIES_PATH twice**
- **Found during:** Task 1 verification
- **Issue:** Plan's verbatim text put STRATEGIES_PATH only on the variable line, but acceptance criteria required `grep -c 'STRATEGIES_PATH' .env.example == 2`.
- **Fix:** Changed `# Path to the strategies YAML file …` to `# STRATEGIES_PATH — path to the strategies YAML file …` so the env var name appears in the description as well.
- **Files modified:** `.env.example`
- **Verification:** `grep -c 'STRATEGIES_PATH' .env.example` returns 2.
- **Committed in:** `5dc0cc8` (Task 1 commit).

**2. [Adjustment - Format] Ruff format reformatted multi-line `f.write_text(...)` calls in `test_strategies.py`**
- **Found during:** Task 3 verification (`uv run ruff format --check`)
- **Issue:** Some short YAML strings fit on one line and ruff format collapsed the implicit-concatenation form. Functional equivalence preserved.
- **Fix:** Ran `uv run ruff format tests/test_strategies.py` to auto-apply.
- **Files modified:** `tests/test_strategies.py`
- **Verification:** `uv run ruff format --check tests/test_strategies.py tests/test_strategies_api.py` — both clean.
- **Committed in:** `6cc21cd` (Task 3 commit).

---

**Total deviations:** 0 substantive deviations; 2 cosmetic adjustments documented above.
**Impact on plan:** None — all deliverables match plan acceptance criteria. Pre-existing lint/format/ty issues in unrelated files (scanner.py, test_ws.py) deferred to `deferred-items.md` per scope-boundary rule.

## Issues Encountered

- **Pre-existing ruff E501 errors in `src/predictions/scanner.py`** (16 errors, lines 645–672). Verified pre-existing via `git stash` baseline check. Out of scope; logged in `deferred-items.md`.
- **Pre-existing ruff format violation in `tests/test_ws.py`.** Out of scope; logged in `deferred-items.md`.
- **Pre-existing ty diagnostics (8).** Mostly `unresolved-import` warnings against optional deps. Out of scope; logged in `deferred-items.md`.

## User Setup Required

None — no external service configuration. The new `STRATEGIES_PATH` env var has a default that works in dev and prod; operators only need to set it if they want to point at a non-default path.

## Next Phase Readiness

- **Wave 1 plans (02-01 loader, 02-02 endpoint) ready to start.** They have:
  - PyYAML available (`import yaml` works).
  - Four fixture YAMLs to load and assert against.
  - 12 xfail-marked tests that will flip green as `load_strategies` and `GET /api/strategies` are implemented.
  - `STRATEGIES_PATH` env var documented and ready to be consumed by `load_strategies()`.
- **No blockers identified.** The plan ships infrastructure only — no production behavior changes.

## Self-Check: PASSED

- Created files exist:
  - FOUND: strategies.yaml
  - FOUND: tests/test_strategies.py
  - FOUND: tests/test_strategies_api.py
  - FOUND: tests/fixtures/strategies-good.yaml
  - FOUND: tests/fixtures/strategies-empty.yaml (zero bytes)
  - FOUND: tests/fixtures/strategies-malformed.yaml
  - FOUND: tests/fixtures/strategies-unknown-field.yaml
- Commits exist:
  - FOUND: 5dc0cc8 (Task 1)
  - FOUND: 1cd62df (Task 2)
  - FOUND: 6cc21cd (Task 3)
- Verification commands run:
  - `uv run python -c 'import yaml'` exits 0 (yaml 6.0.3)
  - `uv run pytest tests/test_strategies.py tests/test_strategies_api.py` reports 12 xfailed (plan success criterion met)
  - `uv run ruff check tests/test_strategies.py tests/test_strategies_api.py` clean
  - `uv run ruff format --check tests/test_strategies.py tests/test_strategies_api.py` clean

---

*Phase: 02-strategy-engine-core*
*Plan: 00*
*Completed: 2026-04-30*
