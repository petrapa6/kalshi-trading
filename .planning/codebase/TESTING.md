---
last_mapped_commit: d010a403e3997670cdce46c100b8d39438c4783d
last_mapped: 2026-04-30
---

# Testing Patterns

**Analysis Date:** 2026-04-30

## Test Framework

**Runner:**
- `pytest` (version >=8.0)
  - Config: `pyproject.toml` `[tool.pytest.ini_options]`
  - Async mode: `asyncio_mode = "auto"` (via `pytest-asyncio` >=0.24)
  - Test paths: `tests/`

**Assertion library:**
- `pytest` built-in assert statements (no external assertion library needed)
- Async support via `pytest-asyncio`

**Run commands:**
```bash
uv run pytest tests/                    # Run all tests
uv run pytest tests/ -v                 # Verbose (show each test)
uv run pytest tests/ -k test_mlb        # Run tests matching pattern
uv run pytest tests/test_ws.py          # Run single file
uv run pytest tests/test_ws.py::test_ws_connects_and_receives  # Run single test
```

## Test File Organization

**Location:**
- Co-located in `tests/` directory (parallel to `src/`)
- Structure: `tests/test_<module>.py` maps to `src/predictions/<module>.py`

**Current test files:**
- `tests/test_sport_stats.py` — Unit tests for stats aggregation
- `tests/test_ws.py` — Integration test for WebSocket connectivity

**Naming:**
- Files: `test_<feature>.py`
- Tests: `test_<what_is_being_tested>()`
- Fixtures: lowercase, suffixed with `_fixture` if helper

**Marked skips:**
- `@pytest.mark.skipif()` for integration tests requiring external credentials
  - Example: WebSocket test skipped if `KALSHI_API_KEY` not set

## Test Structure

**Basic unit test (from `test_sport_stats.py`):**
```python
def test_mlb_and_mlbst_are_kept_distinct():
    """Document what this test verifies."""
    # Setup: Create test data
    session = get_session()
    session.add(
        Trade(
            ticker="KXMLBSTGAME-TEST-BOS-NYY",
            status="settled_win",
            pnl_cents=100,
            dry_run=False,
        )
    )
    session.commit()
    session.close()
    
    # Execute: Call the function under test
    stats = get_total_sport_stats()["stats"]
    
    # Assert: Verify expectations
    assert "MLBST" in stats
    assert stats["MLBST"]["wins"] == 1
    assert stats["MLBST"]["pnl"] == 100
```

**Async test structure (from `test_ws.py`):**
```python
@pytest.mark.skipif(not os.environ.get("KALSHI_API_KEY"), 
                     reason="Needs live Kalshi credentials")
async def test_ws_connects_and_receives():
    """Mark as async; pytest-asyncio runs it automatically."""
    client = _load_client()
    if client is None:
        pytest.skip("no Kalshi private key configured")
    
    # Execute async operations
    balance = await client.get_balance()
    
    # Assert
    assert "balance" in balance
```

**Pattern notes:**
- No explicit `setUp`/`tearDown`; each test manages its own database session
- Setup phase before execute; execute phase isolated from setup
- Skip tests gracefully when external dependencies (credentials) are missing
- Assertions are specific (check exact field values, not just truthy)

## Mocking

**Framework:** `unittest.mock` (Python standard library) — available but not heavily used in current tests

**What is actually tested:**
- `test_sport_stats.py`: Direct integration with SQLAlchemy models and API functions (no mocks)
- `test_ws.py`: Real WebSocket connection to Kalshi (conditional on credentials)

**What to mock in future tests:**
- External HTTP calls (ESPN, Kalshi REST) → use `httpx.AsyncClient` mock or `pytest-httpx`
- File I/O (loading private keys) → mock `open()` or use temporary files
- Time-based logic (game clocks, timers) → mock `datetime.now()` or `time.time()`

**What NOT to mock:**
- Database access in unit tests of query logic (use in-memory SQLite if needed)
- Core business logic (filtering, matching) — test with real data structures

## Fixtures and Test Data

**Current approach:**
- No pytest fixtures defined; tests create their own data
- Inline setup in test function bodies
- Database access: `get_session()` from `db.py` module

**Example from `test_sport_stats.py`:**
```python
session = get_session()
session.add(Trade(...))
session.add(StretchOpportunity(...))
session.commit()
session.close()
```

**Future fixture pattern (if needed):**
```python
@pytest.fixture
def session():
    """Provide a fresh SQLAlchemy session for each test."""
    s = get_session()
    yield s
    s.rollback()
    s.close()

def test_something(session):
    session.add(Trade(...))
    session.commit()
    # test assertions
```

**Location:** Fixtures can live in `tests/conftest.py` (pytest auto-imports)

## Coverage

**Requirements:** No explicit coverage target enforced in CI

**View coverage:**
```bash
uv run pytest tests/ --cov=predictions --cov-report=html
# Opens htmlcov/index.html in browser
```

**Coverage gaps (see CONCERNS.md):**
- Scanner loop (`run_scanner()`) not unit-tested; runs in production via API lifespan
- Kalshi WebSocket message handlers not exercised by unit tests
- Settlement duality (WS vs REST) lacks regression tests
- Dashboard `page.tsx` monolith has no component tests (102 KB file)

## Test Types

**Unit Tests:**
- **Scope:** Individual functions, database queries
- **Approach:** Call function with known inputs; verify output
- **Example:** `test_mlb_and_mlbst_are_kept_distinct()` — calls `get_total_sport_stats()`, checks aggregation logic
- **Database:** Uses real SQLite (in-memory not configured; uses default test DB path)

**Integration Tests:**
- **Scope:** External system interaction (Kalshi API, WebSocket, ESPN)
- **Approach:** Conditional on credentials; verifies client behavior
- **Example:** `test_ws_connects_and_receives()` — connects to live Kalshi WS, subscribes to markets, waits for messages
- **Skip condition:** `@pytest.mark.skipif(not KALSHI_API_KEY)` allows CI to run without credentials

**E2E Tests:**
- **Framework:** Not used
- **Alternative:** Manual testing via `pnpm dev:api` + dashboard
- **Verification:** See CLAUDE.md "Verification before claiming done" section

## Common Patterns

**Async test with timeout:**
```python
try:
    await asyncio.wait_for(ws.listen(), timeout=10)
except asyncio.TimeoutError:
    pass  # Expected if no messages arrive in 10 seconds
finally:
    await ws.close()
```

**Skip with custom message:**
```python
if client is None:
    pytest.skip("no Kalshi private key configured")
```

**Assertion on collection membership:**
```python
got_subscribed = any(m.get("type") == "subscribed" for m in received)
assert got_subscribed or received
```

## Pre-Commit Hook (Quality Gate)

**Script location:** `scripts/pre-commit-check.sh`

**What it does:**
1. Formats Python files with `ruff format` (modifies in place)
2. Lints Python files with `ruff check --fix` (auto-fixes where possible)
3. Re-adds modified files to git staging
4. Type-checks Python with `ty check` (no fixes, just reports)
5. Formats TypeScript/TSX in dashboard with `oxfmt` (modifies in place)

**What it does NOT do:**
- Does NOT scan for secrets (API keys, tokens, credentials)
- Does NOT run the test suite
- Does NOT check for commented-out code

**Manual steps required before commit:**
```bash
# Before committing, scan staged diff for secrets manually:
git diff --cached | grep -i "api.key\|private\|secret\|password"

# If found: abort and remove from staging
git reset HEAD <file>

# Then:
pnpm pre-commit-check  # Runs the hook manually
uv run pytest tests/    # Run tests (not automatic)
```

## Test Execution Checklist (CLAUDE.md verification gate)

When claiming a change is done, verify:

**Python:**
```bash
uv run ruff check .
uv run ruff format --check .
uv run ty check
uv run pytest tests/
```

**Dashboard (if UI changes):**
```bash
cd dashboard && pnpm lint && pnpm fmt:check && pnpm build
```

**Backend behavior (if API/scanner changes):**
```bash
pnpm dev:api
# Hit endpoint with curl or browser:
curl http://localhost:8000/
# Should return {"status": "ok"}
```

**Do NOT claim a UI change works without loading the dashboard in a browser** — type checking is not feature checking.

## Known Test Gaps

**Not tested:**
- Scanner lifespan (`run_scanner()` async loop) — runs live in production; no unit tests
- WebSocket market lifecycle handlers (`on_lifecycle()`) — tested indirectly via integration test
- Settlement duality race conditions (WS arrival vs REST poll) — no regression tests
- Trade placement edge cases (order rejection, timeout, duplicate order ID) — needs mock Kalshi client
- ESPN API timeouts and retries — currently swallows exceptions, no resilience test
- Backtest settlement reconciliation for soccer matches — partial data not tested

**Why gaps exist:**
- Scanner is a long-running background task (hard to unit test in isolation)
- External APIs (Kalshi, ESPN) are non-deterministic; mocking required for reliability
- Database state mutations are sequential and interdependent (reset between tests needed)

## Future Testing Recommendations

**Priority 1: Settlement edge cases**
- Mock Kalshi API responses for order placement failures, timeouts
- Test trade settlement when WS message arrives before REST query
- Mock ESPN timeouts to verify backoff behavior

**Priority 2: Scanner loop unit tests**
- Extract core matching logic (`match_kalshi_to_espn()`) into pure function; unit test
- Mock market data; test filters (price, lead, volume) in isolation

**Priority 3: Dashboard component tests**
- Break `dashboard/app/page.tsx` into smaller components
- Unit test chart rendering, trade table sorting, auth flow

**Priority 4: Backtest regression tests**
- Add fixtures for historical soccer matches (canned data)
- Verify backtests reproduce expected P&L for known scenarios

---

*Testing analysis: 2026-04-30*
