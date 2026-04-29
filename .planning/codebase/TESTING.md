---
title: TESTING
focus: quality
last_mapped: 2026-04-29
last_mapped_commit: f2c2f78
---

# Testing

The Python backend has a small but real pytest suite focused on the soccer backtest module and its FastAPI endpoint. Two legacy tests pre-date the suite and are essentially manual scripts. The dashboard and CLI have no tests at all.

## Backend (Python)

### Framework

- **`pytest>=8.0`** + **`pytest-asyncio>=0.24`** (dev group in `pyproject.toml`).
- Async mode is **`auto`** — `async def test_*` functions run as coroutines automatically without an `@pytest.mark.asyncio` decorator. Configured at `pyproject.toml`:
  ```toml
  [tool.pytest.ini_options]
  asyncio_mode = "auto"
  testpaths = ["tests"]
  ```

### Run

From the repo root:

```bash
uv run pytest tests/
```

Single file / single test:

```bash
uv run pytest tests/test_backtest_api.py
uv run pytest tests/test_simulate_match.py::test_<name>
```

### Layout

| File | Type | What it covers |
|---|---|---|
| `tests/conftest.py` | fixtures | Auto-use `isolated_db` and `isolated_soccer_db` fixtures — both monkeypatch `engine` + `SessionLocal` to fresh in-memory SQLite per test |
| `tests/test_simulate_match.py` | unit | `predictions.backtest.simulate_match` — strategy trigger logic |
| `tests/test_find_observed_yes_ask.py` | unit | `predictions.backtest.find_observed_yes_ask` — Kalshi price lookup against historical opportunity rows |
| `tests/test_run_backtest.py` | integration | `predictions.backtest.run_backtest` orchestrator end-to-end with mocked API-Football client |
| `tests/test_soccer_cache.py` | integration | `predictions.soccer_cache` — DB round-trip; `ApiFootballClient` against `httpx.MockTransport`; rate-limit (429); batched fixture-detail chunking |
| `tests/test_backtest_api.py` | integration | FastAPI `TestClient` against `POST /api/backtest/soccer` — auth (`401`), missing key (`503`), date validation (`422`), happy path (`200`) with patched `run_backtest` |
| `tests/test_sport_stats.py` | legacy script | Standalone — predates the suite. Not currently exercised by the rest of the codebase. |
| `tests/test_ws.py` | legacy script | Standalone Kalshi WS sanity check — talks to live Kalshi if creds present. Not a real unit test. |

### Conftest pattern

`tests/conftest.py` defines two **autouse** fixtures that swap the engine and `SessionLocal` for both DB modules to fresh in-memory SQLite per test, then create all tables:

```python
@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    db_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
```

The same shape is repeated for `predictions.soccer_cache`. The `import predictions.soccer_cache as soccer_module` is wrapped in a `try/except ImportError` so tests still run if the soccer cache module changes.

**Why autouse:** the production modules bind their engine at import time via `DATABASE_URL`. Without monkeypatching, every test would scribble on the real `predictions.db` at the repo root.

### Mocking patterns

- **`httpx.MockTransport`** for upstream HTTP. Pattern: build a list of `(status, json_body)` tuples, hand them to a transport, inject the transport into the client under test. See `tests/test_soccer_cache.py:_mock_transport`.
- **`unittest.mock.AsyncMock` + `patch`** for replacing `predictions.backtest.run_backtest` in the API test (`tests/test_backtest_api.py::test_backtest_200_happy_path`).
- **Fake clients** that satisfy a Protocol (e.g. `_FakeApiFootballClient` implementing the `_SoccerClientLike` protocol from `soccer_cache.py:204`). Used to inject controlled match/goal data into `run_backtest` without going over the wire.
- **`monkeypatch.setenv`** for `API_TOKEN`, `API_FOOTBALL_KEY`, etc. inside the test.

### FastAPI testing

`tests/test_backtest_api.py` shows the canonical pattern:

```python
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app
    return TestClient(app)
```

The `from predictions.api import app` import happens **inside** the fixture so it runs *after* the env var is set. This matters because `_check_token` reads `os.getenv("API_TOKEN")` per request, but importing `api` early would still pull in dependencies that read env at import time (`scanner.py` calls `load_dotenv()` at import).

### What is NOT tested

- The four async loops in `scanner.run_scanner` (`espn_loop`, `kalshi_scan_loop`, `ws_loop`, `backup_loop`).
- `KalshiClient` or `KalshiWebSocket` — no mocked transport, no signature verification test.
- `extract_cents` / `extract_volume` (the integer-cents invariant boundary).
- ESPN fetcher (`espn.get_scoreboard`, `match_kalshi_to_espn`).
- The Bearer-auth dependency (`_check_token`) is covered indirectly by `test_backtest_api.py::test_backtest_requires_bearer` only.
- Database migration logic (`_migrate_add_columns`).
- `WHAT_IF_STRATEGIES` evaluation (`_evaluate_what_if_strategies`).
- Settlement logic (`check_settlements`, `check_stretch_settlements`, `on_lifecycle`).
- S3 backup / restore (`_download_db`, `_backup_db_sync`, `scanner.backup_db`).

### Coverage at a glance

| Module | Has tests? |
|---|---|
| `src/predictions/backtest.py` | ✅ unit + integration |
| `src/predictions/soccer_cache.py` | ✅ DB round-trip + mocked transport |
| `src/predictions/api.py` | ⚠️ only `/api/backtest/soccer` + auth |
| `src/predictions/scanner.py` | ❌ |
| `src/predictions/kalshi_client.py` | ❌ |
| `src/predictions/espn.py` | ❌ |
| `src/predictions/db.py` | ⚠️ exercised transitively by other tests |
| `src/predictions/config_cli.py` | ❌ |

## Dashboard (Next.js)

No tests committed. No test-runner dep in `dashboard/package.json`. CI gating is `pnpm lint && pnpm fmt:check && pnpm build` only (per `CLAUDE.md`).

## CLI (React-ink)

No tests committed. No test-runner dep in `cli/package.json`.

## CI

There is no CI test gate beyond the local pre-commit hook (`scripts/pre-commit-check.sh`), which **does not run pytest**. Tests are a developer responsibility on the way to a PR.

## Conventions for new tests

- Put new Python tests under `tests/` as `test_<thing>.py`. Conftest gives you isolated in-memory DBs for free.
- For HTTP tests, use `httpx.MockTransport` (sync) — don't import requests-mock or responses.
- For FastAPI endpoints, use `fastapi.testclient.TestClient` and import `app` *inside* the fixture after setting env.
- Async tests need no decorator (asyncio_mode=auto); just `async def test_*`.
- Reach for `unittest.mock.patch` only when you can't inject — prefer the Protocol + fake-client pattern from `tests/test_soccer_cache.py::_FakeApiFootballClient`.
- Do not hit live Kalshi / ESPN / API-Football from tests. The two legacy files (`test_sport_stats.py`, `test_ws.py`) are exempt only because they predate the discipline.
