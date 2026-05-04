---
phase: 3
slug: scanner-integration
status: verified
threats_open: 0
asvs_level: 1
created: 2026-05-04
---

# Phase 3 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail. Verified by gsd-security-auditor against working-tree source on 2026-05-04.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| API lifespan startup ↔ on-disk SQLite | `init_db()` runs migrations once on boot; rename + ALTERs touch the on-disk schema before scanner spawns | Schema DDL only (no row data) |
| API lifespan startup ↔ S3 backup | `_download_db()` pulls latest backup before `init_db`; migrations apply to backed-up schema | Encrypted DB blob |
| Scanner async loops ↔ `predictions.db` Session | One session per scan-loop iteration; `place_strategy_trade` owns its commit; `check_settlements` + `on_lifecycle` each open + close their own | Trade rows (cents-scale ints) |
| Scanner ↔ Kalshi REST | `place_bet` may call `client.create_order`; `place_strategy_trade` does NOT (invariant); `record_balance` is read-only | Order intent, balance |
| Scanner ↔ Kalshi WS | `on_lifecycle` consumes `market_lifecycle_v2` settlement messages | Settlement results |
| Scanner ↔ ESPN | Read-only via `get_categorized_games` | Public game state |
| Bearer-auth gate ↔ FastAPI endpoints | `Depends(_check_token)` on `/api/sport-stats`; deleted endpoints (`/api/stretch-stats`, DELETE `/api/stretch`) had auth and are gone — net auth surface unchanged | API_TOKEN bearer |
| Dashboard ↔ `/api/sport-stats` | Slow-poll (60s); response shape `{stats: {...}}` unchanged; consumer rendering invariant | Aggregated counts |
| Test runner ↔ in-memory SQLite | `isolated_db` fixture monkeypatches `predictions.db.engine` — production DB never touched by tests | Test fixtures only |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation | Status |
|-----------|----------|-----------|-------------|------------|--------|
| T-01-3-01 | Tampering | Strategy YAML in test fixtures (Plan 03-01) | accept | Test-only inputs via `tmp_path`; `yaml.safe_load` rejects `!!python/*` tags | closed |
| T-01-3-02 | Information disclosure | Test logs may print yes_ask / strategy names | accept | Synthetic data only; pytest captures logs by default | closed |
| T-01-3-03 | DoS | xfail tests run on every `pytest tests/` (Plan 03-01) | accept | xfail stubs ~10ms each; +200ms on a 30s suite | closed |
| T-01-3-05 | Tampering | `tests/test_db_migrations.py` CREATEs `stretch_opportunities` to test rename guard | mitigate | Manual CREATE TABLE inside autouse `isolated_db` in-memory engine (`tests/test_db_migrations.py:30-34, 43, 61`) — production DBs untouched | closed |
| T-02-3-05 | Tampering / data loss | RENAME executes against unbacked-up DB; rollback impossible (Plan 03-02) | mitigate | Idempotent guard `inspector.get_table_names()` (`db.py:150-154`); pre-deploy S3 backup gate (STR-04, deploy checklist); `init_db` runs at API lifespan startup before scanner spawns | closed |
| T-02-3-07 | Tampering | SQL injection via `text()` raw queries in `_migrate_add_columns` | accept | All ALTER strings static literals (`db.py:129-141, 156-158, 175-184`); no user input flows in | closed |
| T-02-3-08 | DoS | Migration time / SQLite locks during ALTER on large prod DB | accept | RENAME O(1) on SQLite 3.25+ (metadata-only); CREATE INDEX sub-second on ~10K trades; `connect_args timeout=5` (`db.py:21`) handles incidental BUSY | closed |
| T-02-3-09 | Information disclosure | `stretch_opportunities_archived` retained — old WHAT_IF data persists | accept | Intentional per D-03; no ORM mapping, no endpoint reads from archive table | closed |
| T-02-3-10 | Tampering / repudiation | Idempotency guard fails / partial rename on power loss | accept | SQLite RENAME atomic via single `engine.begin()` COMMIT (`db.py:155`); WAL recovery rolls back | closed |
| T-03-3-01 | Tampering | `strategies.yaml` malformed YAML triggers crash | mitigate | `load_strategies` catches FileNotFoundError/OSError/YAMLError/ValidationError, returns [] (`strategies.py:67-92`); `evaluate_strategies` defense-in-depth try/except (`scanner.py:497-501`); both log WARNING, no raise into scan loop | closed |
| T-03-3-02 | Tampering / data integrity | Mismatched `dry_run` flag attribution between strategy fire and real-money trade rows | mitigate | `place_strategy_trade` HARDCODES `dry_run=True` + `status="dry_run"` + `strategy_name=<name>` (`scanner.py:466-468`); `place_bet` unchanged (preserves process-level DRY_RUN). Tests `test_evaluate_strategies_fires_dry_run_trade`, `test_strategy_fire_independent_of_dry_run_env` (`tests/test_scanner_strategies.py:12, 68`). Severity: HIGH | closed |
| T-03-3-03 | Tampering / data integrity | Settlement filter drift between WS `on_lifecycle` and REST `check_settlements` paths | mitigate | Identical filter literal `Trade.status.in_(("placed","filled","dry_run")) AND or_(dry_run==False, and_(dry_run==True, strategy_name.isnot(None)))` at `scanner.py:285-295` and `scanner.py:346-357`; test `test_settlement_filter_symmetry` (`tests/test_strategy_settlement.py:185`). Severity: HIGH | closed |
| T-03-3-04 | Tampering / kill-switch bypass | `trading_paused` gate fails — eval runs and writes a row while paused | mitigate | Loop-level early-return at top of `evaluate_strategies` (`scanner.py:492-494`); placement (not callee-level) closes check-then-write race; test `test_trading_paused_blocks_strategy_fire` (`tests/test_scanner_strategies.py:287`). Severity: HIGH | closed |
| T-03-3-06 | Information disclosure | scanner.log lines containing strategy_name + ticker + yes_price | accept | scanner.log local-only on Fargate container; strategies.yaml committed to repo (no marginal exposure) | closed |
| T-03-3-08 | DoS | `evaluate_strategies` iterates markets × strategies × triggers per tick | accept | Production scale ≤200 markets × 10 strategies × 5 triggers = ~10K iterations/tick; sub-millisecond. `existing` set O(1) per check (`scanner.py:529`) | closed |
| T-03-3-11 | Tampering | Concurrent `on_lifecycle` + `check_settlements` double-update on same ticker | accept | Both paths only transition placed/filled/dry_run → settled_*; status filter excludes terminal `settled_*` (`scanner.py:288, 350`); idempotent on same Kalshi result | closed |
| T-04-3-06 | Information disclosure | `/api/sport-stats` semantic shift could mislead a consumer | accept | Documented inline (`api.py:466-470`); UI consumes shape-unchanged response; manual UAT covers sane numbers | closed |
| T-04-3-07 | Tampering | SQL injection in new sport-stats `text()` query | accept | Static SQL string, no user input (`api.py:473-480`) | closed |
| T-04-3-12 | DoS / data integrity | `COUNT(DISTINCT event_ticker)` under analytics polling | accept | `ix_opportunities_found_at` exists (`db.py:43`); ~50K rows in prod; aggregation sub-second; bearer-auth gates poll rate (`api.py:461`) | closed |
| T-04-3-13 | Elevation of privilege | DELETE `/api/stretch` removed | accept | Capability removed not added; data preserved in `stretch_opportunities_archived`; no new admin path | closed |
| T-04-3-14 | Information disclosure / runtime crash | Dashboard dangling refs to deleted `stretchStats`/`StretchStats`/`StrategySetStats` | mitigate | Strict grep for `stretchStats|StretchStats|StrategySetStats|stretch-stats|stretchOpps|StretchOpportunity` against `dashboard/app/page.tsx` returns 0 matches; `pnpm build` passes (TypeScript gate) | closed |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-3-01 | T-01-3-01, T-01-3-02, T-01-3-03 | Test-only surface — synthetic data, captured logs, trivial runtime | Plan 03-01 (D-22) | 2026-05-01 |
| AR-3-02 | T-02-3-07 | Static SQL DDL only; no user input touches `text()` strings | Plan 03-02 | 2026-05-01 |
| AR-3-03 | T-02-3-08 | SQLite 3.25+ DDL costs are documented (RENAME O(1), index sub-second); `timeout=5` covers BUSY | Plan 03-02 (D-02) | 2026-05-01 |
| AR-3-04 | T-02-3-09 | `stretch_opportunities_archived` retention is intentional per D-03 — preserves Phase 1/2 data for forensic SELECT if needed | Plan 03-02 (D-03) | 2026-05-01 |
| AR-3-05 | T-02-3-10 | SQLite atomicity guarantees + WAL recovery; no application-level rollback needed | Plan 03-02 | 2026-05-01 |
| AR-3-06 | T-03-3-06 | scanner.log not exfiltrated; strategies.yaml already public in repo | Plan 03-03 | 2026-05-02 |
| AR-3-07 | T-03-3-08 | Multiplicative loop bounded by realistic production scale; analytical cost negligible | Plan 03-03 | 2026-05-02 |
| AR-3-08 | T-03-3-11 | Settlement transition idempotent on terminal status — concurrent updates converge | Plan 03-03 | 2026-05-02 |
| AR-3-09 | T-04-3-06 | Semantic shift documented inline; UI rendering invariant on response shape | Plan 03-04 (D-19) | 2026-05-02 |
| AR-3-10 | T-04-3-07 | Static SQL string; no user-controlled fragment in query | Plan 03-04 | 2026-05-02 |
| AR-3-11 | T-04-3-12 | Indexed table + bearer-auth-gated polling; aggregation cost bounded | Plan 03-04 | 2026-05-02 |
| AR-3-12 | T-04-3-13 | Capability removal does not introduce new admin path; archival data still accessible via ad-hoc SQL if needed | Plan 03-04 (D-21) | 2026-05-02 |

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-04 | 21 | 21 | 0 | gsd-security-auditor (verified mitigations against working-tree source for waves 03-01 through 03-04) |

### 2026-05-04 audit notes

- Working tree contains uncommitted Phase 03-03 + 03-04 source changes — that working tree is what was audited.
- Settlement filter symmetry (T-03-3-03) verified line-for-line identical between `scanner.py:285-295` (REST) and `scanner.py:346-357` (WS).
- `trading_paused` kill switch (T-03-3-04) confirmed at loop entry (`scanner.py:492`), not callee level — closes the Plan 03-03 Pitfall #2 race.
- Migration idempotency (T-02-3-05) confirmed via `inspector.get_table_names()` guard at `db.py:150-154`.
- Pre-deploy S3 backup gate (STR-04) is process-level / deploy-checklist; not code-verifiable in this audit (correctly out of scope).
- 03-03 + 03-04 SUMMARY files contain no "Threat Flags" section — executors detected no new attack surface beyond the registered threats.

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-04
