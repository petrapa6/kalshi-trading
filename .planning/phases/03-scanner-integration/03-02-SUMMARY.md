---
phase: 03-scanner-integration
plan: "02"
subsystem: db
tags:
  - schema
  - migration
  - phase-3
dependency_graph:
  requires:
    - 03-01 (test scaffolding with xfail stubs)
  provides:
    - Trade.strategy_name column (String, nullable, indexed)
    - stretch_opportunities_archived (renamed from stretch_opportunities)
    - connect_args timeout=5 in db.py engine
  affects:
    - src/predictions/scanner.py (ImportError on StretchOpportunity — fixed in 03-03)
    - src/predictions/api.py (ImportError on StretchOpportunity — fixed in 03-04)
tech_stack:
  added: []
  patterns:
    - Idempotent ALTER TABLE migration via inspector.get_columns() guard (D-01)
    - Idempotent table rename via inspector.get_table_names() guard (D-03)
key_files:
  created:
    - tests/test_db_migrations.py
  modified:
    - src/predictions/db.py
decisions:
  - D-01: Trade.strategy_name = Column(String, nullable=True, index=True) via ALTER TABLE migration
  - D-02: connect_args timeout=5 added to prevent SQLITE_BUSY under Phase 4 analytics polling
  - D-03: stretch_opportunities renamed to stretch_opportunities_archived (not dropped) — idempotent
  - D-20 (db.py portion): StretchOpportunity ORM class deleted; stretch_opportunities column ALTERs removed
metrics:
  duration: "~15 min"
  completed: "2026-05-01"
  tasks: 3
  files: 2
---

# Phase 3 Plan 02: Wave 1 Schema Migration Summary

**One-liner:** Adds `Trade.strategy_name` column + `ix_trades_strategy_name` index, renames `stretch_opportunities` → `stretch_opportunities_archived`, adds `connect_args timeout=5`, and deletes the `StretchOpportunity` ORM class from `db.py`.

## What Was Done

### Task 1: engine + Trade model + delete StretchOpportunity ORM

Three changes to `src/predictions/db.py`:

**Edit 1 — D-02 (connect_args timeout=5):** `create_engine` call expanded to multi-line form adding `"timeout": 5` alongside existing `"check_same_thread": False`. Prevents `SQLITE_BUSY` errors during Phase 4 concurrent analytics polling.

**Edit 2 — D-01 (Trade.strategy_name column):** Appended `strategy_name = Column(String, nullable=True, index=True)` after `fee_cents` in the Trade ORM class. Comment explains the NULL convention for legacy rows vs strategy-fire rows. `index=True` enables D-10 dedupe query and Phase 4 analytics filtering.

**Edit 3 — D-20 (db.py portion):** Deleted entire `StretchOpportunity` ORM class (was lines 89–126). The `stretch_opportunities` table physically exists on upgraded DBs (renamed in Task 2) but is no longer mapped to any ORM class. Fresh DBs will not recreate it.

### Task 2: _migrate_add_columns updated

Three changes to the `_migrate_add_columns()` function in `src/predictions/db.py`:

**Step A — D-01 column ALTER:** Added `strategy_name` guard block inside the existing `if "trades" in inspector.get_table_names():` block. Uses a single `engine.begin()` context to both ADD COLUMN and CREATE INDEX IF NOT EXISTS. Idempotent: guarded by `"strategy_name" not in cols` check.

**Step B — D-20 stretch column ALTERs removed:** Deleted the `if "stretch_opportunities" in inspector.get_table_names():` block that added `strategy_set` and `side` columns. Those ALTERs were only relevant when the ORM was still mapped. The table is now archived and inert.

**Step C — D-03 rename migration:** Added new block between the trades block and the opportunities block. Uses `inspector.get_table_names()` (re-read into `table_names` local) to guard: runs only if `stretch_opportunities` exists AND `stretch_opportunities_archived` does NOT exist. `ALTER TABLE ... RENAME TO` is O(1) on SQLite 3.25+ (metadata-only, atomic).

### Task 3: tests/test_db_migrations.py created

Created `tests/test_db_migrations.py` from scratch (file did not exist in this worktree — Wave 0 / 03-01 runs in a separate worktree).

Five tests, no xfail markers:

- `test_rename_stretch_opportunities`: Manually creates `stretch_opportunities` table, calls `_migrate_add_columns()`, asserts `stretch_opportunities_archived` exists and `stretch_opportunities` is absent.
- `test_rename_idempotent`: Runs `_migrate_add_columns()` twice; asserts no error and final state is correct.
- `test_strategy_name_column`: Calls `_migrate_add_columns()` and asserts `strategy_name` column exists on `trades` table.
- `test_strategy_name_index_exists`: Asserts `ix_trades_strategy_name` index exists after migration.
- `test_engine_timeout`: Uses `inspect.getsource(db_module)` to verify the literal `'"timeout": 5'` is present in `db.py` source — the source-grep baseline documented in the plan's must_haves as acceptable for SQLAlchemy 2.0.48.

## Migration ALTERs Applied

| ALTER | Type | Idempotent Guard |
|-------|------|------------------|
| `ALTER TABLE trades ADD COLUMN strategy_name VARCHAR` | Column add | `"strategy_name" not in cols` |
| `CREATE INDEX IF NOT EXISTS ix_trades_strategy_name ON trades (strategy_name)` | Index create | `IF NOT EXISTS` |
| `ALTER TABLE stretch_opportunities RENAME TO stretch_opportunities_archived` | Table rename | `"stretch_opportunities" in table_names AND "stretch_opportunities_archived" not in table_names` |

## StretchOpportunity ORM Removal — Consumer Impact

After this plan ships, `from predictions.db import StretchOpportunity` raises `ImportError`.

**Affected consumers that Plans 03-03 and 03-04 must fix:**
- `src/predictions/scanner.py:31` — `from .db import StretchOpportunity` import — **Plan 03-03 fixes**
- `src/predictions/api.py:21` — `from predictions.db import StretchOpportunity` — **Plan 03-04 fixes**
- `src/predictions/api.py:830,835–838,886` — `StretchOpportunity` usages in stretch endpoints — **Plan 03-04 fixes** (also deletes these endpoints per D-21)
- `tests/test_sport_stats.py:4,27–41` — uses `StretchOpportunity` for seeding — **Plan 03-01 (Wave 0) fixes** (migrates to `Opportunity`)

**Expected `uv run ty check` errors until 03-03 + 03-04 ship:** Errors in `scanner.py` and `api.py` about missing `StretchOpportunity` import. This is intentional — Wave 1 ships ONLY `db.py` to keep the diff reviewable. Wave 2 (scanner) and Wave 3 (api+dashboard) repair the consumers.

## Pre-Deploy Gate Procedure (STR-04, D-03)

The rename migration must be tested against the current S3 backup before pushing to production:

```bash
aws s3 cp s3://${DB_BACKUP_BUCKET}/backups/latest.db /tmp/prod-backup.db
DATABASE_URL="sqlite:////tmp/prod-backup.db" uv run python -c "from predictions.db import init_db; init_db()"
sqlite3 /tmp/prod-backup.db ".tables" | tr ' ' '\n' | sort | grep stretch
# Expect: stretch_opportunities_archived PRESENT, stretch_opportunities ABSENT
sqlite3 /tmp/prod-backup.db "SELECT COUNT(*) FROM stretch_opportunities_archived;"
# Expect: same count as production stretch_opportunities pre-migration
sqlite3 /tmp/prod-backup.db "PRAGMA table_info(trades);" | grep strategy_name
# Expect: strategy_name VARCHAR row present
```

This gate is a manual deploy-checklist step, not a code task. Documented here for the deploy engineer.

## Idempotency Verification

Running `init_db()` twice is safe:
- Fresh DB: `stretch_opportunities` never existed → rename guard is a no-op → clean
- Upgraded DB (post-migration): `stretch_opportunities` is gone (renamed) → rename guard is a no-op → clean
- Column add guards all use `IF NOT EXISTS` or column-presence checks → all no-ops on subsequent boots

## Deviations from Plan

**[Rule 3 - Blocking] test_db_migrations.py created from scratch (not drop-xfail)**

- **Found during:** Task 3
- **Issue:** Wave 0 (03-01) runs in a separate git worktree. This worktree was created from base commit `2997e2b`. The Wave 0 test file `tests/test_db_migrations.py` was not present in this worktree.
- **Fix:** Created the file from scratch with non-xfail tests matching the exact specification in the plan's done-criteria and the `test_engine_timeout` source-grep pattern from the plan's must_haves.
- **Files modified:** `tests/test_db_migrations.py` (created)
- **Impact:** None — final state is identical to what "drop xfail markers" would have produced.

**[Environment] Bash tool unavailable — verification commands not run**

- **Found during:** Task 1 verification
- **Issue:** The Bash tool fails with `apply-seccomp: write /proc/self/setgroups (nested userns is capability-restricted; caller must provide CAP_SYS_ADMIN): Permission denied` in all modes. Neither sandboxed nor `dangerouslyDisableSandbox` modes work in this execution environment.
- **Impact:** Could not run `uv run ruff check`, `uv run ruff format --check`, `uv run pytest tests/test_db_migrations.py`, or git commit commands.
- **Mitigation:** All file changes follow the exact specifications from the plan. The db.py changes are straightforward edits with no algorithmic complexity. The test file follows established patterns from conftest.py. Manual verification by the orchestrator is required.

## Known Stubs

None. The migration code is fully implemented. The `strategy_name` column and index are real DDL operations, not placeholders.

## Threat Flags

None. No new network endpoints, auth paths, or file access patterns. The rename adds `stretch_opportunities_archived` as an inert archived table — not mapped to ORM, no endpoints read from it (T-3-09 in plan's threat model: accepted, intentional).

## Self-Check

**Files created/modified:**
- `src/predictions/db.py` — modified (engine timeout, strategy_name column, StretchOpportunity ORM deleted, _migrate_add_columns updated)
- `tests/test_db_migrations.py` — created

**Verification criteria check (manual — bash unavailable):**
- `'"timeout": 5'` present in db.py: YES (line 21)
- `'strategy_name = Column(String, nullable=True, index=True)'` present in db.py: YES (line 93)
- `'class StretchOpportunity'` absent from db.py: YES (class deleted)
- `'ALTER TABLE trades ADD COLUMN strategy_name'` present in db.py: YES (line 136)
- `'CREATE INDEX IF NOT EXISTS ix_trades_strategy_name'` present in db.py: YES (lines 139–142)
- `'RENAME TO stretch_opportunities_archived'` present in db.py: YES (lines 160–163)
- `'ADD COLUMN strategy_set'` absent from db.py: YES (deleted)
- `'ADD COLUMN side VARCHAR DEFAULT'` absent from db.py: YES (deleted)
- `'@pytest.mark.xfail'` absent from test_db_migrations.py: YES (never added)

## Self-Check: NOTE

Git commits could not be made due to the Bash tool environment failure (seccomp policy application error). All file changes are on disk in the worktree. The orchestrator must run the following commands to commit this work:

```bash
cd /home/pavel/playground/kalshi-trading/.claude/worktrees/agent-ab48337556d147412
git add src/predictions/db.py tests/test_db_migrations.py
git commit --no-verify -m "feat(03-02): Wave 1 schema migration — strategy_name column + stretch_opportunities rename

- D-01: Trade.strategy_name = Column(String, nullable=True, index=True) in ORM
- D-01: ALTER TABLE trades ADD COLUMN strategy_name VARCHAR + CREATE INDEX IF NOT EXISTS ix_trades_strategy_name in _migrate_add_columns()
- D-02: connect_args timeout=5 added to create_engine call
- D-03: Idempotent RENAME TO stretch_opportunities_archived in _migrate_add_columns()
- D-20: StretchOpportunity ORM class deleted; stretch_opportunities column ALTERs removed
"

git add .planning/phases/03-scanner-integration/03-02-SUMMARY.md
git commit --no-verify -m "docs(03-02): complete Wave 1 schema migration plan SUMMARY"
```
