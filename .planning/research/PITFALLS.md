# Pitfalls Research — v1.2 Strategy Engine

**Project:** Kalshi Trading Scanner
**Researched:** 2026-04-29
**Confidence:** HIGH — findings based on direct codebase inspection

---

## Critical Pitfalls

| # | Pitfall | Severity | Relevant Phase |
|---|---------|----------|----------------|
| 1 | Kalshi has no `dry_run` order flag — DRY-01 requirement is ambiguous | Critical | DRY-01 spec |
| 2 | 5–10 API calls/loop: rate limiter adds ~1s latency to 5s cycle | Critical | DRY-01 implementation |
| 3 | `stretch_opportunities` replacement destroys historical data if done as drop+recreate | Critical | STR-04 |
| 4 | `DRY_RUN=false` in production causes real orders for all strategy evaluations | Critical | DRY-01 |
| 5 | Dry-run trades filtered out of settlement reconciliation — P&L always null | Critical | DRY-02 |
| 6 | YAML schema drift: backtest uses `minute`/`goal_diff` (soccer), scanner uses `clock_seconds`/`score_diff` (all sports) | High | STR-01 |
| 7 | OR-of-AND edge cases: empty AND-set fires on everything; boundary exactness bugs | High | STR-02 |
| 8 | Analytics auto-refresh + SQLite busy timeout defaults to 0ms — 500 errors under contention | Moderate | DASH-04 |
| 9 | `Trade` table needs `strategy_name` column before any scanner code that sets it | Moderate | DRY-02 |
| 10 | PyYAML coerces `yes`/`no` to Python booleans | Minor | STR-01 |

---

## Detailed Analysis

### 1 — Kalshi dry_run flag does not exist

`POST /portfolio/orders` has no `dry_run` or `paper_trading` parameter. A call with extra fields either gets rejected or silently ignored. Options:
- **(a) Use existing local simulation path** — already works, zero cost, zero API calls (recommended)
- **(b) Use Kalshi demo environment** — separate `BASE_URL` + separate credentials, real API calls

The requirement "real API calls, dry_run=True flag" must be clarified before Phase 3 implementation begins.

**Prevention:** Clarify DRY-01 intent in the Phase 3 plan before writing any code.

### 2 — Rate limiter accumulation

`KalshiClient._rate_limit()` enforces 100ms between API calls. Ten strategy dry-run orders = ~1 second of mandated sleep per scan loop iteration on a 5-second cycle. On a busy game night the scanner degrades exactly when timing precision matters most.

**Prevention:** If Kalshi API calls are needed per strategy, batch them via `asyncio.gather`. If using local simulation, this pitfall is irrelevant.

### 3 — stretch_opportunities replacement destroys historical data

`ALTER TABLE DROP TABLE stretch_opportunities` is irreversible. The S3 backup overwrites every 30 minutes. The correct pattern:

    ALTER TABLE stretch_opportunities RENAME TO stretch_opportunities_archived;

Then remove all write paths that populate it. Leave the archived table as dead storage — SQLite can't reliably drop it anyway. Never use DROP TABLE for STR-04.

**Prevention:** STR-04 implementation must use RENAME, not DROP. Write and test migration against a copy of the S3 backup before deploying.

### 4 — DRY_RUN env var inheritance causes real orders

`DRY_RUN=false` in production flows through `run_scanner(dry_run=dry)` into `place_bet(dry_run=dry)`. Strategy evaluation orders will use the same flag. With `DRY_RUN=false`, all strategy orders would be live real-money orders.

**Prevention:** The strategy evaluation path in scanner.py must hardcode `dry_run=True` unconditionally, regardless of the process-level `DRY_RUN` env var. This is non-negotiable.

### 5 — Settlement filter excludes dry-run trades

```python
# scanner.py check_settlements()
.filter(Trade.status.in_(("placed", "filled")), Trade.dry_run == False)
```

Strategy dry-run trades (`dry_run=True`, `status="dry_run"`) are permanently excluded from settlement reconciliation. P&L will always be null. The `on_lifecycle` WebSocket handler has the same exclusion.

**Prevention:** DRY-02 must add a parallel settlement path that targets `dry_run=True AND strategy_name IS NOT NULL AND status="dry_run"` and computes P&L when the market settles.

### 6 — YAML schema drift between backtest and scanner

The backtest engine uses soccer-specific fields: `minute` (elapsed int), `goal_diff`. The live scanner uses sport-agnostic ESPN `GameState` fields: `clock_seconds` (countdown or countup), `score_diff`, `period`, `sport_path`.

A unified `strategies.yaml` condition like `min_minute: 75` has no direct equivalent for NBA (which uses countdown `clock_seconds`). Either:
- Condition fields are sport-scoped (each condition has a `sport` field and the evaluator picks vocabulary)
- There are separate evaluation paths per context (backtest vs live)

This must be designed explicitly in STR-01 before any code is written.

**Prevention:** Define the condition vocabulary explicitly in the YAML spec for STR-01, specifying which fields apply to which sports and contexts.

### 7 — OR-of-AND edge cases

Four specific bugs to guard against:

- **Empty AND-set:** `triggers: [[]]` evaluates as vacuous truth — fires on every market. Pydantic: `min_length=1` on the inner list.
- **Empty condition dict:** `all([])` returns `True` in Python. Must be `all(...) and len(conditions) > 0`.
- **Boundary exactness:** `min_minute: 75` should fire at minute 75, not 76. Test with `elapsed_seconds = 75 * 60` exactly.
- **OR short-circuit:** The first passing AND-set stops evaluation. Condition ordering in YAML is performance-relevant — document this.

**Prevention:** Unit tests for condition evaluator covering empty sets, exact boundaries, and multi-trigger cases before any scanner integration.

### 8 — SQLite busy timeout

`db.py` creates the engine with `connect_args={"check_same_thread": False}` but no `timeout` parameter. SQLite's default busy timeout is 0ms — it returns `SQLITE_BUSY` immediately. The analytics page polling at 10–15s from multiple browser tabs collides with the scanner writing every 5s, causing unhandled exceptions and 500 errors.

**Prevention:** Add `"timeout": 5` to `connect_args` in `db.py`. Poll analytics at 10–15s minimum.

### 9 — Migration order matters

If scanner code referencing `Trade.strategy_name` deploys before the `ALTER TABLE` migration runs, the scanner crashes on the first strategy dry-run with `OperationalError: table trades has no column named strategy_name`.

**Prevention:** DB migration always precedes code that references the new column. The migration is in `_migrate_add_columns()` which runs at `init_db()` — ensure this runs before the scanner loop starts. This is already the existing pattern; just don't break it.

### 10 — PyYAML boolean coercion

`yaml.safe_load` converts `yes`, `no`, `true`, `false`, `on`, `off` (case-insensitive) to Python booleans. A strategy field named `side: yes` becomes `{'side': True}`.

**Prevention:** Quote string values in YAML that could be interpreted as booleans. Add Pydantic validators that reject `bool` where `str` is expected. The field `enabled: true` is intentionally a boolean — document this in the YAML schema.
