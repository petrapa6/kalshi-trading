# Known Issues Fixes — Design

**Date:** 2026-04-24
**Status:** Approved

Fix 7 of the 9 "Known Issues" listed in `docs/project.md`. Skips:
- #4 `dashboard/app/page.tsx` monolith — own session.
- #8 Stretch P&L sizing — requires schema + algorithm redesign; separate spec.

## Commit Plan

Six commits, each independently reversible. Pure-Python fixes first, then the schema change, then pytest migration, then chore.

### 1. `fix(scanner): subtract fee from P&L in WebSocket settlement path` (#1)

**File:** `src/predictions/scanner.py` — `run_scanner::on_lifecycle`.

```python
# Trade WIN case:
trade.pnl_cents = trade.potential_profit_cents - (trade.fee_cents or 0)
# Trade LOSS case:
trade.pnl_cents = -trade.cost_cents - (trade.fee_cents or 0)
```

Matches `check_settlements` precisely. WS handler is the primary settlement path, so real-trade P&L had been overstated by the fee amount on every win.

### 2. `fix(api): remove hardcoded $200 starting-balance from /api/stats` (#2)

**File:** `src/predictions/api.py` — `get_stats`.

Delete the `balance_cents - 20000` heuristic (~lines 306–313). Return `total_fees = recorded_fees` only. Honest under-reporting for pre-fee-tracking trades beats inferred falsehood.

### 3. `refactor(scanner): snapshot market_prices per loop to avoid race` (#6)

**File:** `src/predictions/scanner.py` — wherever `market_prices` is iterated.

```python
prices_snapshot = dict(market_prices)   # shallow copy — cheap
# ...iterate prices_snapshot instead...
```

WS handler mutates `market_prices` concurrently with scan-loop reads. A per-loop shallow copy gives a consistent view without requiring `asyncio.Lock`.

### 4. `refactor(db,scanner): record stretch bet side to unblock NO strategies` (#9)

**Files:** `src/predictions/db.py`, `src/predictions/scanner.py`.

1. Add `side = Column(String, default="yes")` to `StretchOpportunity`.
2. Extend `_migrate_add_columns` with a `stretch_opportunities.side` `VARCHAR DEFAULT 'yes'` migration, following the existing `strategy_set` pattern.
3. Pass `side="yes"` explicitly at every `StretchOpportunity(...)` construction (scanner.py).
4. Replace `result == "yes"` with `result == stretch.side` in `check_stretch_settlements` and in the WS lifecycle stretch branch.
5. P&L math (`stretch.yes_ask * 5`, `(100 - stretch.yes_ask) * 5`) stays — still correct for YES bets, NO bets aren't added here.

### 5. `test: migrate tests to pytest + pytest-asyncio` (#5)

**Files:** `pyproject.toml`, `tests/test_sport_stats.py`, `tests/test_ws.py`, `CLAUDE.md`, `README.md`.

- Add `pytest>=8`, `pytest-asyncio>=0.24` to `[dependency-groups].dev`.
- Add `[tool.pytest.ini_options] asyncio_mode = "auto"` to pyproject.toml.
- Rewrite both scripts as pytest tests: `asyncio.run(main())` → `async def test_...`, `print(...)` → `assert`.
- `test_ws.py` requires live Kalshi credentials — decorate with `@pytest.mark.skipif(not os.getenv("KALSHI_API_KEY"), reason="needs Kalshi creds")`.
- Update CLAUDE.md Quick-commands line and README's Development section: `uv run pytest tests/`.

### 6. `chore: fix asyncio import + EFS mermaid drift` (#7 + #3)

**Files:** `src/predictions/kalshi_client.py`, `README.md`, `docs/project.md`.

- Delete the inner `import asyncio` inside `_rate_limit` — `asyncio` is already imported at the top of the file.
- README mermaid `DB` node: `"SQLite on /tmp (prod)<br/>S3 snapshots every 30 min<br/>trades, balance, opportunities"`.
- `docs/project.md` architecture-section Mermaid: same correction.

## Verification

| Commit | Check |
|---|---|
| all | `python3 -c "import ast; ast.parse(open(f).read())"` on every edited `.py` |
| 1 | `grep -n "pnl_cents = trade.potential_profit_cents" src/predictions/scanner.py` → matches `on_lifecycle` only and subtracts fee |
| 2 | `grep -n "20000\|true_pnl\|unrecorded_fees" src/predictions/api.py` → zero matches |
| 3 | `grep -n "for .* in market_prices" src/predictions/scanner.py` → zero matches after change |
| 4 | `grep -n '== "yes"' src/predictions/scanner.py` → zero remaining in stretch branches |
| 5 | `python3 -m py_compile tests/*.py`; `grep -n "def test_" tests/*.py` → ≥1 per file |
| 6 | `grep -nE "EFS" README.md docs/project.md` → only in "Known Issues" references, not in architecture |
| all | `git log --oneline` matches the six-commit plan |

**Out-of-shell** (user runs post-session): `uv sync`, `uv run pytest tests/`, `uv run ty check`, `uv run ruff check .`, `docker build .`, dashboard `pnpm build`.

## Open Risks

- **Schema migration (#9) runs on every startup** via `init_db() → _migrate_add_columns()`. The existing pattern uses raw `ALTER TABLE … ADD COLUMN …` — safe for SQLite (idempotent via `if "side" not in cols` guard). No data loss risk.
- **Pytest rename** changes the invocation — the `install.sh` script doesn't run tests, so no script breakage. `scripts/pre-commit-check.sh` already only runs `ruff` + `ty`, so unaffected.
- **`tests/test_ws.py` will now skip** in sessions without `KALSHI_API_KEY`. That's correct — it was never runnable without creds.
