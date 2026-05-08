---
phase: 3
slug: scanner-integration
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-05-01
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.
> Sourced from `03-RESEARCH.md` § Validation Architecture (lines 931–984).
> The planner refines per-task IDs in step 4 once plans are written.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | `pytest >= 8.0` + `pytest-asyncio >= 0.24` (`asyncio_mode = "auto"`) — already installed (`pyproject.toml` `[dependency-groups] dev`) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` (lines 39–41) |
| **Quick run command** | `uv run pytest tests/test_scanner_strategies.py tests/test_strategy_settlement.py tests/test_db_migrations.py -x` |
| **Full suite command** | `uv run pytest tests/` |
| **Estimated runtime** | ~5 s quick / <30 s full |

---

## Sampling Rate

- **After every task commit:** Run the **Quick run command** (the three new test files; <5 s).
- **After every plan wave:** Run the **Full suite command** (all phases; <30 s).
- **Before `/gsd-verify-work`:** Full suite green AND
  `uv run ruff check . && uv run ruff format --check . && uv run ty check` AND
  the manual smoke test from "Manual-Only Verifications" item 3 below.
- **Max feedback latency:** 5 s per-task / 30 s per-wave.

---

## Per-Requirement Verification Map

> Plan/Wave/Task IDs are filled by the planner in step 4 after PLAN.md files
> exist. The Test Type, Automated Command, and File Exists columns are locked
> from research.

| Requirement | Behavior | Test Type | Automated Command | File Exists | Plan/Wave/Task (RED stub → GREEN) |
|-------------|----------|-----------|-------------------|-------------|-----------------------------------|
| STR-04 | `stretch_opportunities` renamed (not dropped); `stretch_opportunities_archived` exists with same row count | unit (migration) | `uv run pytest tests/test_db_migrations.py::test_rename_stretch_opportunities -x` | ❌ W0 | 03-01/W0/T1 (RED stub) → 03-02/W1/T3 (GREEN) |
| STR-04 | `_migrate_add_columns()` is idempotent on a renamed DB | unit (migration) | `uv run pytest tests/test_db_migrations.py::test_rename_idempotent -x` | ❌ W0 | 03-01/W0/T1 (RED stub) → 03-02/W1/T3 (GREEN) |
| STR-04 | `WHAT_IF_STRATEGIES` no longer importable from `predictions.scanner` | unit (deletion) | `uv run pytest tests/test_scanner_strategies.py::test_what_if_strategies_removed -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T3 (GREEN) |
| STR-04 | `/api/sport-stats` returns counts derived from `opportunities` (`COUNT(DISTINCT event_ticker)` semantics) | unit (API) | `uv run pytest tests/test_sport_stats.py -x` | ✅ (modify) | 03-01/W0/T4 (modify-test) → 03-04/W3/T1 (GREEN) |
| DRY-01 | Strategy fire writes `Trade(dry_run=True, strategy_name=<name>, yes_price=<live yes_ask>)`; no Kalshi REST call | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_evaluate_strategies_fires_dry_run_trade -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T2b (GREEN) |
| DRY-01 | Process-level `DRY_RUN` env var does not change strategy fire behavior | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_strategy_fire_independent_of_dry_run_env -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T2a+T2b (GREEN) |
| DRY-01 | First-trigger-wins per `(strategy, market)` tick | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_first_trigger_wins -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T2b (GREEN) |
| DRY-01 | Per-strategy dedupe by `(strategy_name, ticker)` | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_per_strategy_dedupe -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T2b (GREEN) |
| DRY-01 | Multiple strategies CAN fire on the same ticker (one Trade row each) | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_multi_strategy_fire_same_ticker -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T2b (GREEN) |
| DRY-01 | `trading_paused == "true"` blocks strategy trade writes (success criterion #3, D-23) | unit (eval) | `uv run pytest tests/test_scanner_strategies.py::test_trading_paused_blocks_strategy_fire -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T2b (GREEN) |
| DRY-01 | `elapsed_minutes()` correct for soccer (count-up), basketball (count-down), `None` for baseball/tennis | unit (pure) | `uv run pytest tests/test_scanner_strategies.py::test_elapsed_minutes_per_sport -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T1 (GREEN) |
| DRY-01 | `SPORT_PATH_TO_FAMILY` reverse lookup returns correct family | unit (pure) | `uv run pytest tests/test_scanner_strategies.py::test_sport_path_to_family -x` | ❌ W0 | 03-01/W0/T2 (RED stub) → 03-03/W2/T1 (GREEN) |
| DRY-02 | `Trade.strategy_name` column accepts NULL + str; index exists | unit (schema) | `uv run pytest tests/test_db_migrations.py::test_strategy_name_column -x` | ❌ W0 | 03-01/W0/T1 (RED stub) → 03-02/W1/T1 (GREEN) |
| DRY-02 | `check_settlements` (REST fallback) updates `dry_run=True AND strategy_name IS NOT NULL` rows | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_check_settlements_updates_strategy_trades -x` | ❌ W0 | 03-01/W0/T3 (RED stub) → 03-03/W2/T3 (GREEN) |
| DRY-02 | `on_lifecycle` (WS primary) updates the same trade set as `check_settlements` (D-17 symmetry) | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_on_lifecycle_updates_strategy_trades -x` | ❌ W0 | 03-01/W0/T3 (RED stub) → 03-03/W2/T3 (GREEN) |
| DRY-02 | Win P&L: `count × (100 − yes_price)`; loss P&L: `−count × yes_price`; no fee | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_strategy_pnl_math -x` | ❌ W0 | 03-01/W0/T3 (RED stub) → 03-03/W2/T3 (GREEN) |
| DRY-02 | `check_settlements` does NOT update legacy process-level dry-runs (`dry_run=True AND strategy_name IS NULL`) | unit (settlement) | `uv run pytest tests/test_strategy_settlement.py::test_legacy_dry_runs_not_settled -x` | ❌ W0 | 03-01/W0/T3 (RED stub) → 03-03/W2/T3 (GREEN) |
| Success #5 | `engine.connect_args` includes `"timeout": 5` | unit (config) | `uv run pytest tests/test_db_migrations.py::test_engine_timeout -x` | ❌ W0 | 03-01/W0/T1 (RED stub, source-grep) → 03-02/W1/T2 (GREEN) |

*Status legend: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_scanner_strategies.py` — DRY-01 coverage (eval, dedupe, paused, helpers)
- [ ] `tests/test_strategy_settlement.py` — DRY-02 coverage (WS + REST symmetry, P&L math)
- [ ] `tests/test_db_migrations.py` — STR-04 (rename) + DRY-02 (column add) + success #5 (timeout)
- [ ] `tests/test_sport_stats.py` — MODIFY existing: seed `Opportunity` rows in place of `StretchOpportunity` (per D-22)

**No new fixtures needed.** `tests/conftest.py::isolated_db` and `isolated_soccer_db` cover everything; tests construct `Trade`, `Opportunity`, and `Strategy` (Pydantic) inline.

**No framework install needed.** `pytest` + `pytest-asyncio` already in `pyproject.toml [dependency-groups] dev` (lines 43–49).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| D-03 pre-deploy gate (S3 backup rename roundtrip) | STR-04 | Requires live S3 access + a backed-up copy of the prod DB | `aws s3 cp s3://<backup-bucket>/predictions.db /tmp/predictions-backup.db`, then `DATABASE_URL=sqlite:////tmp/predictions-backup.db uv run python -c "from predictions.db import init_db; init_db()"`; sqlite3 verify `stretch_opportunities_archived` exists with original row count and `stretch_opportunities` is gone |
| A1 — soccer cumulative-clock assumption | DRY-01 | Requires live ESPN response on a second-half match | `curl https://site.api.espn.com/apis/site/v2/sports/soccer/eng.1/scoreboard` → inspect `displayClock` and `period` on a live in-progress 2nd-half match. Verify clock counts up cumulatively (e.g., `60:23` at minute 60) rather than restarting at zero in period 2. Updates the `elapsed_minutes()` formula if assumption fails. |
| End-to-end strategy fire on production-like data | DRY-01 | Needs running scanner + live Kalshi WS + live ESPN | Boot `pnpm dev:api` with a `strategies.yaml` containing one wide-trigger strategy (e.g., `min_minute: 30`, `min_lead: 1`); watch `scanner.log` for one fire; verify `Trade` row in DB with `strategy_name` set, `dry_run=true`, `yes_price` matching live `yes_ask`. |
| Dashboard `/api/sport-stats` rendering | STR-04 | Visual confirmation post-D-19 semantic shift (count → distinct events) | Load dashboard, navigate to "Sports" tab, verify chart renders with the new `COUNT(DISTINCT event_ticker)` numbers and the values look sane (a typical NBA night should be ~5–15, not 0 or 1000). |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or are listed under Wave 0 Requirements
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references in the per-requirement map (4 files: 3 new + 1 modified)
- [ ] No watch-mode flags
- [ ] Feedback latency < 5 s per-task / 30 s per-wave
- [ ] `nyquist_compliant: true` set in frontmatter once planner fills per-task rows

**Approval:** Plan/Wave/Task column filled per planner revision (2026-05-01); `nyquist_compliant: true` set in frontmatter. Awaiting gsd-plan-checker re-verification.
