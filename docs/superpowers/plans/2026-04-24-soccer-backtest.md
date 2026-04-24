# Soccer Strategy Backtest Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Strategy Backtest" page to the dashboard that simulates soccer (EPL / La Liga / Bundesliga) trigger-based trading strategies against historical football-data.org match data. Win-rate analytics are always shown; financial P&L is shown only for matches where Kalshi prices were observed by the live scanner.

**Architecture:** Two new backend modules — `soccer_cache.py` (football-data.org client + its own SQLite DB) and `backtest.py` (simulation + orchestration). New `POST /api/backtest/soccer` endpoint on the existing FastAPI app. New `/backtest` page in the Next.js dashboard. The backtest is read-only, synchronous, returns partial results when football-data.org rate-limits mid-fetch.

**Tech Stack:** Python 3.13 (FastAPI + SQLAlchemy 2 + httpx + Pydantic), Next.js 16 + React 19 + Tailwind + recharts (new frontend dep).

**Spec reference:** `docs/superpowers/specs/2026-04-24-soccer-backtest-design.md` — canonical source. When the plan and spec drift, the spec wins; stop and re-align.

---

## File Structure

### New files
- `src/predictions/soccer_cache.py` — football-data.org HTTP client, `SoccerMatch` / `SoccerGoal` ORM models, `init_soccer_db()`, `ensure_matches_cached()`. Owns its own `engine` + `SessionLocal` distinct from `db.py`.
- `src/predictions/backtest.py` — Pydantic request/response models, `simulate_match()` pure function, team-alias map + fuzzy matching, `find_observed_yes_ask()`, `run_backtest()` orchestrator.
- `tests/test_soccer_cache.py`
- `tests/test_simulate_match.py`
- `tests/test_find_observed_yes_ask.py`
- `tests/test_run_backtest.py`
- `dashboard/app/backtest/page.tsx`

### Modified files
- `tests/conftest.py` — add a second isolated-DB fixture for the soccer cache engine.
- `src/predictions/api.py` — add `POST /api/backtest/soccer`.
- `dashboard/app/page.tsx` — add "Strategy Backtest" link in the header.
- `dashboard/package.json` — add `recharts` dep.
- `.env.example` — `FOOTBALL_DATA_API_KEY`, `SOCCER_CACHE_DB_PATH`.
- `sst.config.ts` — `FootballDataApiKey` secret + env wiring.

### No changes needed
- `.gitignore` — existing `*.db` / `*.db-journal` globs already cover `soccer-cache.db*`.
- `pyproject.toml` — `httpx`, `sqlalchemy`, `fastapi`, `pydantic` (via fastapi) are all present.

---

## Task 1: Soccer cache — ORM models + init + isolation fixture

**Files:**
- Create: `src/predictions/soccer_cache.py`
- Modify: `tests/conftest.py`
- Test: `tests/test_soccer_cache.py`

- [ ] **Step 1: Add the isolated-soccer-db fixture to `tests/conftest.py`**

The existing fixture patches `predictions.db`. The soccer cache will have its own `engine` / `SessionLocal`, so we need a parallel fixture. Append this to `tests/conftest.py` (do NOT modify the existing `isolated_db` fixture):

```python
@pytest.fixture(autouse=True)
def isolated_soccer_db(monkeypatch):
    """Point `predictions.soccer_cache` at a fresh in-memory SQLite for every test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    try:
        import predictions.soccer_cache as soccer_module
    except ImportError:
        # Module doesn't exist yet (first task) — skip patching.
        yield None
        return

    engine = create_engine(
        "sqlite:///:memory:", connect_args={"check_same_thread": False}
    )
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(soccer_module, "engine", engine)
    monkeypatch.setattr(soccer_module, "SessionLocal", SessionLocal)
    soccer_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
```

- [ ] **Step 2: Write the failing schema-creation test**

Create `tests/test_soccer_cache.py`:

```python
from datetime import datetime, timezone

from sqlalchemy import inspect


def test_init_soccer_db_creates_tables():
    from predictions import soccer_cache

    soccer_cache.init_soccer_db()

    names = set(inspect(soccer_cache.engine).get_table_names())
    assert {"soccer_matches", "soccer_goals"}.issubset(names)


def test_soccer_match_round_trip():
    from predictions.soccer_cache import SoccerGoal, SoccerMatch, SessionLocal, init_soccer_db

    init_soccer_db()
    session = SessionLocal()
    match = SoccerMatch(
        id="fd:1",
        competition="PL",
        kickoff_at=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
        home_team="Arsenal",
        away_team="Chelsea",
        home_score=2,
        away_score=1,
        status="FINISHED",
        fetched_at=datetime.now(timezone.utc),
    )
    session.add(match)
    session.add(SoccerGoal(match_id="fd:1", sequence=1, minute=30, side="home"))
    session.commit()

    fetched = session.query(SoccerMatch).one()
    assert fetched.home_team == "Arsenal"
    assert len(session.query(SoccerGoal).all()) == 1
    session.close()
```

- [ ] **Step 3: Run the failing test**

Run: `uv run pytest tests/test_soccer_cache.py -v`

Expected: FAIL with `ModuleNotFoundError: No module named 'predictions.soccer_cache'`.

- [ ] **Step 4: Create `src/predictions/soccer_cache.py` with ORM + init**

```python
"""Soccer historical-match cache, backed by its own SQLite DB and fed by football-data.org."""

import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_default_db = os.path.join(_repo_root, "soccer-cache.db")
SOCCER_CACHE_DB_PATH = os.getenv("SOCCER_CACHE_DB_PATH", _default_db)
SOCCER_CACHE_URL = f"sqlite:///{SOCCER_CACHE_DB_PATH}"

engine = create_engine(SOCCER_CACHE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class SoccerMatch(Base):
    __tablename__ = "soccer_matches"

    id = Column(String, primary_key=True)  # "fd:<football_data_id>"
    competition = Column(String, nullable=False)  # 'PL' | 'PD' | 'BL1'
    kickoff_at = Column(DateTime, nullable=False)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    home_score = Column(Integer, nullable=False)
    away_score = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # always 'FINISHED' for cached rows
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (
        Index("idx_soccer_matches_comp_kickoff", "competition", "kickoff_at"),
    )


class SoccerGoal(Base):
    __tablename__ = "soccer_goals"

    match_id = Column(String, ForeignKey("soccer_matches.id"), primary_key=True)
    sequence = Column(Integer, primary_key=True)  # 1..N chronological
    minute = Column(Integer, nullable=False)  # regulation minute
    stoppage = Column(Integer, nullable=False, default=0)
    side = Column(String, nullable=False)  # 'home' | 'away' — beneficiary
    is_own_goal = Column(Integer, nullable=False, default=0)


def init_soccer_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_add_columns()


def _migrate_add_columns() -> None:
    inspector = inspect(engine)
    if "soccer_goals" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("soccer_goals")}
        with engine.begin() as conn:
            if "stoppage" not in cols:
                conn.execute(text("ALTER TABLE soccer_goals ADD COLUMN stoppage INTEGER NOT NULL DEFAULT 0"))
            if "is_own_goal" not in cols:
                conn.execute(text("ALTER TABLE soccer_goals ADD COLUMN is_own_goal INTEGER NOT NULL DEFAULT 0"))


def get_session():
    return SessionLocal()
```

- [ ] **Step 5: Run the tests to confirm pass**

Run: `uv run pytest tests/test_soccer_cache.py -v`
Expected: 2 PASS.

- [ ] **Step 6: Commit**

```bash
git add src/predictions/soccer_cache.py tests/conftest.py tests/test_soccer_cache.py
git commit -m "feat(soccer): add SoccerMatch/SoccerGoal ORM + isolated cache engine"
```

---

## Task 2: `FootballDataClient` — HTTP client with rate-limit signalling

**Files:**
- Modify: `src/predictions/soccer_cache.py`
- Test: `tests/test_soccer_cache.py`

- [ ] **Step 1: Write failing tests for the client**

Append to `tests/test_soccer_cache.py`:

```python
import httpx
import pytest


def _mock_transport(responses: list[tuple[int, dict]]) -> httpx.MockTransport:
    """Build a MockTransport that returns the given (status, json) tuples in order."""
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = next(iterator)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


async def test_client_sends_auth_header(monkeypatch):
    from predictions.soccer_cache import FootballDataClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"matches": []})

    transport = httpx.MockTransport(handler)
    client = FootballDataClient(api_key="secret-xyz", transport=transport)
    await client.list_matches("PL", "2026-03-01", "2026-03-31")

    assert captured["headers"]["x-auth-token"] == "secret-xyz"
    assert "competitions/PL/matches" in captured["url"]
    assert "dateFrom=2026-03-01" in captured["url"]
    assert "dateTo=2026-03-31" in captured["url"]


async def test_client_raises_rate_limited_on_429():
    from predictions.soccer_cache import FootballDataClient, RateLimitedError

    client = FootballDataClient(
        api_key="k", transport=_mock_transport([(429, {"message": "rate limited"})])
    )

    with pytest.raises(RateLimitedError):
        await client.list_matches("PL", "2026-03-01", "2026-03-31")


async def test_client_get_match_goals_shape():
    from predictions.soccer_cache import FootballDataClient

    body = {
        "id": 42,
        "homeTeam": {"id": 1, "name": "Arsenal"},
        "awayTeam": {"id": 2, "name": "Chelsea"},
        "goals": [
            {"minute": 30, "injuryTime": None, "team": {"id": 1}, "type": "REGULAR"},
            {"minute": 90, "injuryTime": 3, "team": {"id": 2}, "type": "OWN"},
        ],
    }
    client = FootballDataClient(api_key="k", transport=_mock_transport([(200, body)]))
    detail = await client.get_match_goals(42)
    assert detail["goals"][0]["minute"] == 30
    assert detail["goals"][1]["type"] == "OWN"
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest tests/test_soccer_cache.py -v`
Expected: 3 FAIL (ImportError on `FootballDataClient` / `RateLimitedError`).

- [ ] **Step 3: Implement the client**

Append to `src/predictions/soccer_cache.py`:

```python
import httpx

FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"


class RateLimitedError(Exception):
    """Raised when football-data.org returns HTTP 429."""


class FootballDataClient:
    """Thin async wrapper over football-data.org v4.

    Does not retry. On HTTP 429 raises RateLimitedError so the caller can
    surface partial results to the user. Other non-2xx responses raise
    httpx.HTTPStatusError via raise_for_status.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FOOTBALL_DATA_BASE_URL,
        transport: httpx.BaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Auth-Token": api_key},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_matches(self, league: str, date_from: str, date_to: str) -> dict:
        resp = await self._client.get(
            f"/competitions/{league}/matches",
            params={"dateFrom": date_from, "dateTo": date_to},
        )
        if resp.status_code == 429:
            raise RateLimitedError("football-data.org rate limit hit on list_matches")
        resp.raise_for_status()
        return resp.json()

    async def get_match_goals(self, match_id: int) -> dict:
        resp = await self._client.get(f"/matches/{match_id}")
        if resp.status_code == 429:
            raise RateLimitedError("football-data.org rate limit hit on get_match_goals")
        resp.raise_for_status()
        return resp.json()
```

- [ ] **Step 4: Run tests — all pass**

Run: `uv run pytest tests/test_soccer_cache.py -v`
Expected: 5 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/predictions/soccer_cache.py tests/test_soccer_cache.py
git commit -m "feat(soccer): add FootballDataClient with rate-limit signalling"
```

---

## Task 3: `ensure_matches_cached()` — orchestrate fetch + persist

**Files:**
- Modify: `src/predictions/soccer_cache.py`
- Test: `tests/test_soccer_cache.py`

- [ ] **Step 1: Write failing tests for the orchestrator**

Append to `tests/test_soccer_cache.py`:

```python
from dataclasses import dataclass


class _FakeFootballClient:
    def __init__(self, list_body, detail_bodies: dict, raise_on_detail_after: int | None = None):
        self.list_body = list_body
        self.detail_bodies = detail_bodies
        self.raise_after = raise_on_detail_after
        self.detail_calls = 0
        self.list_calls = 0

    async def list_matches(self, league, date_from, date_to):
        self.list_calls += 1
        return self.list_body

    async def get_match_goals(self, match_id):
        from predictions.soccer_cache import RateLimitedError
        self.detail_calls += 1
        if self.raise_after is not None and self.detail_calls > self.raise_after:
            raise RateLimitedError("boom")
        return self.detail_bodies[match_id]


def _fixture_list_body(ids: list[int]) -> dict:
    return {
        "matches": [
            {
                "id": mid,
                "status": "FINISHED",
                "utcDate": "2026-04-01T14:00:00Z",
                "homeTeam": {"id": 100 + mid, "name": f"Home{mid}"},
                "awayTeam": {"id": 200 + mid, "name": f"Away{mid}"},
                "score": {"fullTime": {"home": 2, "away": 1}},
            }
            for mid in ids
        ]
    }


def _fixture_detail_body(mid: int, goals: list[dict]) -> dict:
    return {
        "id": mid,
        "homeTeam": {"id": 100 + mid, "name": f"Home{mid}"},
        "awayTeam": {"id": 200 + mid, "name": f"Away{mid}"},
        "goals": goals,
    }


async def test_ensure_matches_cached_inserts_all_on_cold_cache():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()
    fake = _FakeFootballClient(
        list_body=_fixture_list_body([1, 2]),
        detail_bodies={
            1: _fixture_detail_body(1, [
                {"minute": 30, "injuryTime": None, "team": {"id": 101}, "type": "REGULAR"},
                {"minute": 80, "injuryTime": None, "team": {"id": 201}, "type": "REGULAR"},
            ]),
            2: _fixture_detail_body(2, []),
        },
    )

    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert result.partial is False
    assert result.missing_count == 0
    assert len(result.matches) == 2
    assert fake.detail_calls == 2


async def test_ensure_matches_cached_skips_already_cached():
    from predictions.soccer_cache import (
        SoccerMatch,
        SessionLocal,
        ensure_matches_cached,
        init_soccer_db,
    )
    from datetime import datetime, timezone

    init_soccer_db()
    # Pre-populate match fd:1
    session = SessionLocal()
    session.add(SoccerMatch(
        id="fd:1", competition="PL",
        kickoff_at=datetime(2026, 4, 1, 14, tzinfo=timezone.utc),
        home_team="Home1", away_team="Away1",
        home_score=2, away_score=1, status="FINISHED",
        fetched_at=datetime.now(timezone.utc),
    ))
    session.commit()
    session.close()

    fake = _FakeFootballClient(
        list_body=_fixture_list_body([1, 2]),
        detail_bodies={2: _fixture_detail_body(2, [])},
    )
    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    # Only match 2 required a detail fetch; match 1 was already cached.
    assert fake.detail_calls == 1
    assert len(result.matches) == 2


async def test_ensure_matches_cached_partial_on_rate_limit():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()
    fake = _FakeFootballClient(
        list_body=_fixture_list_body([1, 2, 3]),
        detail_bodies={1: _fixture_detail_body(1, [])},
        raise_on_detail_after=1,  # succeed once, then raise
    )
    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert result.partial is True
    assert result.missing_count == 2
    # The one successful fetch landed in cache
    assert len(result.matches) == 1


async def test_ensure_matches_cached_skips_non_finished():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()
    body = {
        "matches": [
            {
                "id": 9,
                "status": "SCHEDULED",
                "utcDate": "2027-01-01T00:00:00Z",
                "homeTeam": {"id": 1, "name": "A"},
                "awayTeam": {"id": 2, "name": "B"},
                "score": {"fullTime": {"home": None, "away": None}},
            }
        ]
    }
    fake = _FakeFootballClient(list_body=body, detail_bodies={})
    result = await ensure_matches_cached("PL", "2027-01-01", "2027-01-31", client=fake)
    assert len(result.matches) == 0
    assert fake.detail_calls == 0


async def test_own_goal_is_flipped_to_beneficiary():
    from predictions.soccer_cache import SoccerGoal, SessionLocal, ensure_matches_cached, init_soccer_db

    init_soccer_db()
    # Home team ID is 101; away is 201. An own-goal with team.id=101 means
    # home accidentally scored into their own net → beneficiary is away.
    fake = _FakeFootballClient(
        list_body=_fixture_list_body([1]),
        detail_bodies={1: _fixture_detail_body(1, [
            {"minute": 30, "injuryTime": None, "team": {"id": 101}, "type": "OWN"},
        ])},
    )
    await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    session = SessionLocal()
    goal = session.query(SoccerGoal).one()
    assert goal.side == "away"
    assert goal.is_own_goal == 1
    session.close()
```

- [ ] **Step 2: Run the failing tests**

Run: `uv run pytest tests/test_soccer_cache.py -v`
Expected: 5 FAIL — `ensure_matches_cached` not defined yet.

- [ ] **Step 3: Implement `ensure_matches_cached`**

Append to `src/predictions/soccer_cache.py`:

```python
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class EnsureResult:
    matches: list[SoccerMatch]
    partial: bool
    missing_count: int


def _parse_iso_utc(s: str) -> datetime:
    """Parse ISO-8601 (football-data.org uses trailing 'Z')."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _ingest_goals(session, match_id_str: str, home_team_id: int, raw_goals: list[dict]) -> None:
    """Insert SoccerGoal rows, flipping own-goal scorer to beneficiary side."""
    for seq, g in enumerate(raw_goals, start=1):
        minute = int(g.get("minute") or 0)
        stoppage = int(g.get("injuryTime") or 0)
        scorer_team_id = (g.get("team") or {}).get("id")
        gtype = (g.get("type") or "REGULAR").upper()
        scoring_side = "home" if scorer_team_id == home_team_id else "away"
        # Own-goal: "team.id" is the conceder in football-data.org's payload.
        # The beneficiary — and hence the side that counts on the scoreboard —
        # is the OPPOSITE side.
        if gtype == "OWN":
            scoring_side = "away" if scoring_side == "home" else "home"
        session.add(SoccerGoal(
            match_id=match_id_str,
            sequence=seq,
            minute=minute,
            stoppage=stoppage,
            side=scoring_side,
            is_own_goal=1 if gtype == "OWN" else 0,
        ))


async def ensure_matches_cached(
    league: str,
    date_from: str,
    date_to: str,
    *,
    client: "FootballDataClient | _FakeFootballClient | None" = None,
) -> EnsureResult:
    """Fetch any missing FINISHED matches in the range and persist them.

    Returns all FINISHED matches currently in the cache for (league, range),
    plus a partial flag + missing_count on rate-limit mid-fetch.
    """
    if client is None:
        api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
        if not api_key:
            raise RuntimeError("FOOTBALL_DATA_API_KEY is not set")
        client = FootballDataClient(api_key=api_key)

    list_body = await client.list_matches(league, date_from, date_to)
    raw_matches = [m for m in list_body.get("matches", []) if m.get("status") == "FINISHED"]

    partial = False
    missing = 0
    session = SessionLocal()
    try:
        existing_ids = {
            row[0]
            for row in session.query(SoccerMatch.id)
            .filter(SoccerMatch.competition == league)
            .all()
        }
        for i, m in enumerate(raw_matches):
            match_id_str = f"fd:{m['id']}"
            if match_id_str in existing_ids:
                continue
            try:
                detail = await client.get_match_goals(m["id"])
            except RateLimitedError:
                partial = True
                missing = len(raw_matches) - i
                break

            home_team_id = m["homeTeam"]["id"]
            full_time = (m.get("score") or {}).get("fullTime") or {}
            match_row = SoccerMatch(
                id=match_id_str,
                competition=league,
                kickoff_at=_parse_iso_utc(m["utcDate"]),
                home_team=m["homeTeam"]["name"],
                away_team=m["awayTeam"]["name"],
                home_score=int(full_time.get("home") or 0),
                away_score=int(full_time.get("away") or 0),
                status="FINISHED",
                fetched_at=datetime.now(timezone.utc),
            )
            session.add(match_row)
            _ingest_goals(session, match_id_str, home_team_id, detail.get("goals") or [])
            session.commit()

        # Return all currently-cached matches for the range.
        start = _parse_iso_utc(f"{date_from}T00:00:00Z")
        end = _parse_iso_utc(f"{date_to}T23:59:59Z")
        cached = (
            session.query(SoccerMatch)
            .filter(
                SoccerMatch.competition == league,
                SoccerMatch.kickoff_at >= start,
                SoccerMatch.kickoff_at <= end,
            )
            .order_by(SoccerMatch.kickoff_at)
            .all()
        )
        # Detach from session so the caller can read attributes after .close().
        for m in cached:
            session.expunge(m)
    finally:
        session.close()

    return EnsureResult(matches=cached, partial=partial, missing_count=missing)
```

- [ ] **Step 4: Run tests — all pass**

Run: `uv run pytest tests/test_soccer_cache.py -v`
Expected: all 10 PASS.

- [ ] **Step 5: Run lint + type check**

Run: `uv run ruff check src/predictions/soccer_cache.py && uv run ruff format --check src/predictions/soccer_cache.py && uv run ty check`
Expected: clean.

- [ ] **Step 6: Commit**

```bash
git add src/predictions/soccer_cache.py tests/test_soccer_cache.py
git commit -m "feat(soccer): add ensure_matches_cached orchestrator with partial-on-rate-limit"
```

---

## Task 4: Backtest — Pydantic request/response models

**Files:**
- Create: `src/predictions/backtest.py`
- Test: `tests/test_run_backtest.py` (model-level validation only at this stage)

- [ ] **Step 1: Write failing validation tests**

Create `tests/test_run_backtest.py`:

```python
import pytest
from pydantic import ValidationError


def test_backtest_request_defaults_and_validation():
    from predictions.backtest import BacktestRequest

    # Valid minimum
    req = BacktestRequest(
        league="PL",
        date_from="2026-03-01",
        date_to="2026-04-01",
        min_minute=75,
        min_lead=2,
        min_yes_price=0,
        initial_balance_cents=100000,
        bet_percent=0.02,
    )
    assert req.league == "PL"

    # Unknown league rejected
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="SPL",  # not allowed
            date_from="2026-03-01",
            date_to="2026-04-01",
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )

    # date_from > date_to rejected
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from="2026-05-01",
            date_to="2026-03-01",
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )

    # Out-of-range numeric params rejected
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from="2026-03-01",
            date_to="2026-04-01",
            min_minute=0,  # must be >= 1
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from="2026-03-01",
            date_to="2026-04-01",
            min_minute=75,
            min_lead=6,  # max 5
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from="2026-03-01",
            date_to="2026-04-01",
            min_minute=75,
            min_lead=2,
            min_yes_price=100,  # must be 0..99
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from="2026-03-01",
            date_to="2026-04-01",
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=999,  # min 1000
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from="2026-03-01",
            date_to="2026-04-01",
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.2,  # max 0.10
        )
```

- [ ] **Step 2: Run test — fails with ImportError**

Run: `uv run pytest tests/test_run_backtest.py -v`
Expected: FAIL — `predictions.backtest` does not exist.

- [ ] **Step 3: Create `src/predictions/backtest.py` with Pydantic models**

```python
"""Soccer backtest: simulate trigger-based trading strategies on historical matches."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

LeagueCode = Literal["PL", "PD", "BL1"]


class BacktestRequest(BaseModel):
    league: LeagueCode
    date_from: date
    date_to: date
    min_minute: int = Field(ge=1, le=90)
    min_lead: int = Field(ge=1, le=5)
    min_yes_price: int = Field(ge=0, le=99)
    initial_balance_cents: int = Field(ge=1000)
    bet_percent: float = Field(ge=0.005, le=0.10)

    @model_validator(mode="after")
    def _date_range_valid(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        if self.date_to > date.today():
            raise ValueError("date_to cannot be in the future")
        return self


class BacktestTrade(BaseModel):
    match_id: str
    kickoff_at: datetime
    league: LeagueCode
    home_team: str
    away_team: str
    final_home: int
    final_away: int
    fired_at_minute: int
    score_at_fire_home: int
    score_at_fire_away: int
    leading_side: Literal["home", "away"]
    result: Literal["win", "loss"]
    observed_yes_ask_cents: Optional[int] = None
    count: Optional[int] = None
    cost_cents: Optional[int] = None
    pnl_cents: Optional[int] = None
    bankroll_after_cents: int


class BacktestCurvePoint(BaseModel):
    t: datetime
    balance_cents: int


class BacktestSummary(BaseModel):
    matches_scanned: int
    matches_bet_on: int
    matches_with_price_data: int
    wins: int
    losses: int
    win_rate: float
    initial_balance_cents: int
    final_balance_cents: int
    pnl_cents: int
    pnl_pct: float


class BacktestResponse(BaseModel):
    summary: BacktestSummary
    trades: list[BacktestTrade]
    bankroll_curve: list[BacktestCurvePoint]
    partial: bool
    missing_count: int
```

- [ ] **Step 4: Run the tests — pass**

Run: `uv run pytest tests/test_run_backtest.py -v`
Expected: 1 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/predictions/backtest.py tests/test_run_backtest.py
git commit -m "feat(backtest): add Pydantic request/response models with validation"
```

---

## Task 5: `simulate_match` — fire-once trigger logic

**Files:**
- Modify: `src/predictions/backtest.py`
- Test: `tests/test_simulate_match.py`

- [ ] **Step 1: Write all failing simulate_match tests**

Create `tests/test_simulate_match.py`:

```python
from datetime import datetime, timezone


def _match(goals):
    """Build a stand-in for SoccerMatch with a goals attribute.

    `goals` is a list of (minute, stoppage, side, is_own_goal, sequence?) tuples.
    """
    from types import SimpleNamespace

    goal_objs = []
    for i, g in enumerate(goals, start=1):
        minute, stoppage, side, is_own = g
        goal_objs.append(SimpleNamespace(
            sequence=i, minute=minute, stoppage=stoppage, side=side, is_own_goal=is_own,
        ))
    return SimpleNamespace(
        id="fd:x",
        home_team="H", away_team="A",
        kickoff_at=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
        home_score=sum(1 for (_, _, s, _) in goals if s == "home"),
        away_score=sum(1 for (_, _, s, _) in goals if s == "away"),
        goals=goal_objs,
    )


def _req(min_minute=75, min_lead=2):
    from predictions.backtest import BacktestRequest
    return BacktestRequest(
        league="PL", date_from="2026-03-01", date_to="2026-04-30",
        min_minute=min_minute, min_lead=min_lead, min_yes_price=0,
        initial_balance_cents=100000, bet_percent=0.02,
    )


def test_fires_when_lead_established_before_min_minute():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (40, 0, "home", 0)])  # 2-0 at min 40
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    assert trig is not None
    assert trig.fired_at_minute == 75
    assert trig.score_at_fire_home == 2
    assert trig.score_at_fire_away == 0
    assert trig.leading_side == "home"


def test_fires_at_exact_minute_when_lead_opens_then():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (75, 0, "home", 0)])
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    assert trig is not None
    assert trig.fired_at_minute == 75


def test_does_not_fire_when_lead_never_reached():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (60, 0, "away", 0)])  # 1-1
    assert simulate_match(m, _req(min_minute=75, min_lead=2)) is None


def test_does_not_fire_when_lead_only_held_before_min_minute():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (40, 0, "home", 0), (70, 0, "away", 0), (72, 0, "away", 0)])
    # 2-0 at 40, 2-1 at 70, 2-2 at 72. At minute 75: diff=0, no fire.
    assert simulate_match(m, _req(min_minute=75, min_lead=2)) is None


def test_fire_once_ignores_later_goals():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (40, 0, "home", 0), (80, 0, "home", 0)])
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    # Trigger at 75 with 2-0, NOT 80 with 3-0.
    assert trig.fired_at_minute == 75
    assert trig.score_at_fire_home == 2


def test_stoppage_time_goal_at_90_plus_triggers_at_minute_90():
    from predictions.backtest import simulate_match

    # 90+3 goal makes it 2-0. Trigger should fire at minute 90.
    m = _match([(30, 0, "home", 0), (90, 3, "home", 0)])
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    assert trig is not None
    assert trig.fired_at_minute == 90
    assert trig.score_at_fire_home == 2


def test_own_goal_counts_for_beneficiary_side():
    """Own-goal rows are already flipped at ingestion time (the `side`
    column stores the beneficiary). This test confirms simulate_match
    trusts the side column and does not double-flip."""
    from predictions.backtest import simulate_match

    # Two rows, both side='home' — one regular, one own-goal (flipped at ingestion).
    m = _match([(20, 0, "home", 0), (60, 0, "home", 1), (70, 0, "home", 0)])
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    assert trig is not None
    assert trig.score_at_fire_home == 3
    assert trig.score_at_fire_away == 0
    assert trig.leading_side == "home"


def test_goals_at_same_minute_applied_before_trigger_check():
    from predictions.backtest import simulate_match

    # Trigger minute is 75. Two goals stamped to minute 75:
    # seq 1 = home (score 1-0), seq 2 = away (score 1-1 → no fire).
    m = _match([(75, 0, "home", 0), (75, 0, "away", 0)])
    assert simulate_match(m, _req(min_minute=75, min_lead=1)) is None
```

- [ ] **Step 2: Run — all fail**

Run: `uv run pytest tests/test_simulate_match.py -v`
Expected: 8 FAIL (ImportError on `simulate_match`).

- [ ] **Step 3: Implement `simulate_match`**

Append to `src/predictions/backtest.py`:

```python
from collections import defaultdict
from dataclasses import dataclass


@dataclass
class Trigger:
    fired_at_minute: int
    score_at_fire_home: int
    score_at_fire_away: int
    leading_side: Literal["home", "away"]


def simulate_match(match, req: BacktestRequest) -> Trigger | None:
    """Walk minutes 1..90, applying goals in sequence order per minute.

    Fires once on the first minute ≥ req.min_minute at which
    abs(home - away) >= req.min_lead. Subsequent goals are ignored.

    `match.goals` must be an iterable of objects with .minute, .stoppage,
    .side ('home'|'away', beneficiary), .sequence — `is_own_goal` is
    informational and does NOT affect the side column (the ingestion
    layer already flipped own-goal rows to the beneficiary).
    """
    goals_by_minute: dict[int, list] = defaultdict(list)
    for g in match.goals:
        goals_by_minute[g.minute].append(g)
    for minute, gs in goals_by_minute.items():
        gs.sort(key=lambda x: x.sequence)

    home_score = 0
    away_score = 0
    for minute in range(1, 91):
        for g in goals_by_minute.get(minute, ()):
            if g.side == "home":
                home_score += 1
            else:
                away_score += 1
        if minute < req.min_minute:
            continue
        diff = home_score - away_score
        if abs(diff) >= req.min_lead:
            return Trigger(
                fired_at_minute=minute,
                score_at_fire_home=home_score,
                score_at_fire_away=away_score,
                leading_side="home" if diff > 0 else "away",
            )
    return None
```

- [ ] **Step 4: Run — all pass**

Run: `uv run pytest tests/test_simulate_match.py -v`
Expected: 8 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/predictions/backtest.py tests/test_simulate_match.py
git commit -m "feat(backtest): add simulate_match fire-once trigger logic"
```

---

## Task 6: Team-alias map + fuzzy matching helpers

**Files:**
- Modify: `src/predictions/backtest.py`
- Test: `tests/test_find_observed_yes_ask.py`

- [ ] **Step 1: Write failing tests for normalization + alias lookup**

Create `tests/test_find_observed_yes_ask.py`:

```python
def test_normalize_team_name_casefold_and_whitespace():
    from predictions.backtest import _normalize_team

    assert _normalize_team("Manchester United FC") == "manchester united"
    assert _normalize_team("  Arsenal  ") == "arsenal"
    assert _normalize_team("FC Bayern München") == "bayern munchen"


def test_team_aliases_resolve_common_variants():
    from predictions.backtest import _canonical_team

    # Both forms must collapse to a shared canonical key.
    assert _canonical_team("Man Utd") == _canonical_team("Manchester United")
    assert _canonical_team("Spurs") == _canonical_team("Tottenham Hotspur")
    assert _canonical_team("Bayern") == _canonical_team("Bayern Munich")
    assert _canonical_team("Atleti") == _canonical_team("Atletico Madrid")


def test_market_title_contains_both_teams_matches():
    from predictions.backtest import _market_mentions_both_teams

    assert _market_mentions_both_teams(
        "Arsenal vs Chelsea — will Arsenal win?", "Arsenal", "Chelsea"
    )
    # Reverse order in title still matches
    assert _market_mentions_both_teams(
        "Chelsea at Arsenal", "Arsenal", "Chelsea"
    )
    # Missing one team — no match
    assert not _market_mentions_both_teams(
        "Arsenal vs Liverpool", "Arsenal", "Chelsea"
    )


def test_market_title_via_alias():
    from predictions.backtest import _market_mentions_both_teams

    assert _market_mentions_both_teams(
        "Man Utd vs Tottenham", "Manchester United", "Tottenham Hotspur"
    )
```

- [ ] **Step 2: Run — all fail**

Run: `uv run pytest tests/test_find_observed_yes_ask.py -v`
Expected: 4 FAIL (ImportError).

- [ ] **Step 3: Implement the alias map + helpers**

Append to `src/predictions/backtest.py`:

```python
import re
import unicodedata

# Canonical team-name aliases. Each entry maps an alias to its canonical
# display name. Lookup is case-insensitive after _normalize_team. This is
# the systematic-correction surface — grow lazily as Kalshi/football-data
# mismatches are observed.
_TEAM_ALIASES: dict[str, str] = {
    # Premier League
    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "brighton": "brighton hove albion",
    "brighton and hove albion": "brighton hove albion",
    "brighton & hove albion": "brighton hove albion",
    "newcastle": "newcastle united",
    "nott'm forest": "nottingham forest",
    "leeds": "leeds united",
    "west ham": "west ham united",
    # La Liga
    "atletico madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atleti": "atletico madrid",
    "real": "real madrid",
    "barca": "barcelona",
    "barça": "barcelona",
    "fc barcelona": "barcelona",
    "athletic bilbao": "athletic club",
    "real sociedad": "real sociedad",
    # Bundesliga
    "bayern": "bayern munchen",
    "bayern munich": "bayern munchen",
    "fc bayern munchen": "bayern munchen",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
    "gladbach": "borussia monchengladbach",
    "monchengladbach": "borussia monchengladbach",
    "rb leipzig": "rb leipzig",
    "leipzig": "rb leipzig",
    "schalke": "schalke 04",
    "union berlin": "union berlin",
    "eintracht frankfurt": "eintracht frankfurt",
    "frankfurt": "eintracht frankfurt",
    "freiburg": "sc freiburg",
    "stuttgart": "vfb stuttgart",
}

_NOISE_SUFFIXES = (" fc", " cf", " sc", " ac", " afc", " cfc")


def _normalize_team(name: str) -> str:
    """Lower-case, strip accents + trailing club suffixes, collapse whitespace."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suf in _NOISE_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s


def _canonical_team(name: str) -> str:
    """Return the canonical (alias-resolved) form of a team name."""
    norm = _normalize_team(name)
    return _TEAM_ALIASES.get(norm, norm)


def _market_mentions_both_teams(market_title: str, team_a: str, team_b: str) -> bool:
    """Conservative containment check: the title must contain both canonical
    forms as substrings. Prefers a non-match over a wrong match.
    """
    title_norm = _normalize_team(market_title)
    a = _canonical_team(team_a)
    b = _canonical_team(team_b)
    return a in title_norm and b in title_norm
```

- [ ] **Step 4: Run — all pass**

Run: `uv run pytest tests/test_find_observed_yes_ask.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/predictions/backtest.py tests/test_find_observed_yes_ask.py
git commit -m "feat(backtest): add team-alias map + conservative fuzzy matching"
```

---

## Task 7: `find_observed_yes_ask` — query predictions.db Opportunity

**Files:**
- Modify: `src/predictions/backtest.py`
- Test: `tests/test_find_observed_yes_ask.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_find_observed_yes_ask.py`:

```python
from datetime import datetime, timedelta, timezone

import pytest


def _seed_opportunity(**kwargs):
    from predictions.db import Opportunity, get_session

    session = get_session()
    session.add(Opportunity(**kwargs))
    session.commit()
    session.close()


def _fake_match(kickoff: datetime, home: str, away: str):
    from types import SimpleNamespace
    return SimpleNamespace(
        id="fd:x", kickoff_at=kickoff, home_team=home, away_team=away,
        home_score=0, away_score=0, goals=[],
    )


def test_returns_none_when_no_matching_opportunity():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    assert find_observed_yes_ask(m, fire_minute=80, leading_side="home") is None


def test_picks_closest_opportunity_to_fire_time():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    target = kickoff + timedelta(minutes=80)
    # Two candidate rows — one 20 min before target, one 5 min before target.
    _seed_opportunity(
        ticker="KXEPLGAME-001", series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea — Arsenal to win",
        yes_ask=85, yes_bid=80, spread=5, volume=100,
        found_at=target - timedelta(minutes=20),
    )
    _seed_opportunity(
        ticker="KXEPLGAME-001", series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea — Arsenal to win",
        yes_ask=94, yes_bid=90, spread=4, volume=100,
        found_at=target - timedelta(minutes=5),
    )
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    price = find_observed_yes_ask(m, fire_minute=80, leading_side="home")
    assert price == 94


def test_ignores_rows_outside_window():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    # 40 min before kickoff — outside the [kickoff - 30 min, kickoff + 150 min] window.
    _seed_opportunity(
        ticker="KXEPLGAME-001", series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea — Arsenal to win",
        yes_ask=94, yes_bid=90, spread=4, volume=100,
        found_at=kickoff - timedelta(minutes=40),
    )
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    assert find_observed_yes_ask(m, fire_minute=80, leading_side="home") is None


def test_alias_match_resolves_manchester_united():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _seed_opportunity(
        ticker="KXEPLGAME-001", series_ticker="KXEPLGAME",
        title="Man Utd vs Chelsea — Man Utd to win",
        yes_ask=92, yes_bid=88, spread=4, volume=100,
        found_at=kickoff + timedelta(minutes=75),
    )
    m = _fake_match(kickoff, "Manchester United", "Chelsea")
    assert find_observed_yes_ask(m, fire_minute=75, leading_side="home") == 92


def test_requires_leading_team_in_title():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    # Market is for Chelsea to win — we want the Arsenal side.
    _seed_opportunity(
        ticker="KXEPLGAME-002", series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea — Chelsea to win",
        yes_ask=20, yes_bid=18, spread=2, volume=100,
        found_at=kickoff + timedelta(minutes=75),
    )
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    # Leading side is 'home' (Arsenal) — should NOT return the Chelsea-to-win market.
    assert find_observed_yes_ask(m, fire_minute=75, leading_side="home") is None
```

- [ ] **Step 2: Run — all fail**

Run: `uv run pytest tests/test_find_observed_yes_ask.py -v`
Expected: 5 FAIL on the new tests.

- [ ] **Step 3: Implement `find_observed_yes_ask`**

Append to `src/predictions/backtest.py`:

```python
from datetime import timedelta


def find_observed_yes_ask(match, fire_minute: int, leading_side: str) -> int | None:
    """Best-effort lookup of the Kalshi YES ask observed by the live scanner
    closest to `kickoff + fire_minute × 60s`.

    Returns None when no market can be confidently matched. Deliberately
    conservative: requires both team names to appear in the market title
    after alias normalization, and the leading team must appear too.
    """
    from predictions.db import Opportunity, get_session

    window_start = match.kickoff_at - timedelta(minutes=30)
    window_end = match.kickoff_at + timedelta(minutes=150)
    target = match.kickoff_at + timedelta(minutes=fire_minute)

    leading_team = match.home_team if leading_side == "home" else match.away_team
    leading_canon = _canonical_team(leading_team)

    session = get_session()
    try:
        rows = (
            session.query(Opportunity)
            .filter(
                Opportunity.found_at >= window_start,
                Opportunity.found_at <= window_end,
            )
            .all()
        )
        best = None
        best_delta = None
        for row in rows:
            title = row.title or ""
            if not _market_mentions_both_teams(title, match.home_team, match.away_team):
                continue
            if leading_canon not in _normalize_team(title):
                continue
            delta = abs((row.found_at - target).total_seconds())
            if best_delta is None or delta < best_delta:
                best = row
                best_delta = delta
        return None if best is None else int(best.yes_ask)
    finally:
        session.close()
```

- [ ] **Step 4: Run — all pass**

Run: `uv run pytest tests/test_find_observed_yes_ask.py -v`
Expected: 9 PASS (5 new + 4 from Task 6).

- [ ] **Step 5: Commit**

```bash
git add src/predictions/backtest.py tests/test_find_observed_yes_ask.py
git commit -m "feat(backtest): add find_observed_yes_ask with alias + fuzzy match"
```

---

## Task 8: `run_backtest` — orchestrator + P&L arithmetic

**Files:**
- Modify: `src/predictions/backtest.py`
- Test: `tests/test_run_backtest.py`

- [ ] **Step 1: Write failing integration tests**

Append to `tests/test_run_backtest.py`:

```python
from datetime import datetime, timedelta, timezone


def _make_cached_match(
    *, match_id: str, kickoff: datetime, home: str, away: str,
    final_home: int, final_away: int, goals: list[tuple[int, int, str, int]],
):
    from predictions.soccer_cache import SoccerGoal, SoccerMatch, SessionLocal

    s = SessionLocal()
    s.add(SoccerMatch(
        id=match_id, competition="PL", kickoff_at=kickoff,
        home_team=home, away_team=away,
        home_score=final_home, away_score=final_away,
        status="FINISHED", fetched_at=datetime.now(timezone.utc),
    ))
    for i, (minute, stoppage, side, own) in enumerate(goals, start=1):
        s.add(SoccerGoal(
            match_id=match_id, sequence=i, minute=minute,
            stoppage=stoppage, side=side, is_own_goal=own,
        ))
    s.commit()
    s.close()


def _seed_opp(kickoff, fire_minute, home, away, leading, yes_ask):
    """Seed an Opportunity at the expected fire timestamp."""
    from predictions.db import Opportunity, get_session
    s = get_session()
    s.add(Opportunity(
        ticker="KXEPLGAME-1", series_ticker="KXEPLGAME",
        title=f"{home} vs {away} — {leading} to win",
        yes_ask=yes_ask, yes_bid=yes_ask - 2, spread=2, volume=100,
        found_at=kickoff + timedelta(minutes=fire_minute),
    ))
    s.commit()
    s.close()


def _run(req_kwargs=None):
    from predictions.backtest import BacktestRequest, run_backtest
    from predictions.soccer_cache import EnsureResult, SessionLocal, SoccerMatch

    from unittest.mock import patch

    s = SessionLocal()
    cached = s.query(SoccerMatch).order_by(SoccerMatch.kickoff_at).all()
    for m in cached:
        s.expunge(m)
    s.close()

    result = EnsureResult(matches=cached, partial=False, missing_count=0)

    async def fake_ensure(*args, **kwargs):
        return result

    base = dict(
        league="PL", date_from="2026-03-01", date_to="2026-04-30",
        min_minute=75, min_lead=2, min_yes_price=0,
        initial_balance_cents=100000, bet_percent=0.02,
    )
    base.update(req_kwargs or {})
    req = BacktestRequest(**base)

    with patch("predictions.backtest.ensure_matches_cached", fake_ensure):
        import asyncio
        return asyncio.run(run_backtest(req))


async def test_run_backtest_win_path_with_price():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff, home="Arsenal", away="Chelsea",
        final_home=2, final_away=1,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0), (85, 0, "away", 0)],
    )
    _seed_opp(kickoff, fire_minute=75, home="Arsenal", away="Chelsea",
              leading="Arsenal", yes_ask=94)

    resp = _run()

    assert resp.summary.matches_scanned == 1
    assert resp.summary.matches_bet_on == 1
    assert resp.summary.matches_with_price_data == 1
    assert resp.summary.wins == 1
    assert resp.summary.losses == 0
    # bet_cents = round(100000 * 0.02) = 2000
    # count = max(1, 2000 // 94) = 21
    # cost = 21 * 94 = 1974; pnl on win = 21 * (100 - 94) = 126
    assert resp.trades[0].count == 21
    assert resp.trades[0].cost_cents == 1974
    assert resp.trades[0].pnl_cents == 126
    assert resp.summary.final_balance_cents == 100126


async def test_run_backtest_loss_path_with_price():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    # Arsenal leads 2-0 at 75 → fire. Chelsea ties then wins.
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff, home="Arsenal", away="Chelsea",
        final_home=2, final_away=3,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0),
               (80, 0, "away", 0), (85, 0, "away", 0), (90, 0, "away", 0)],
    )
    _seed_opp(kickoff, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=94)

    resp = _run()
    assert resp.summary.wins == 0
    assert resp.summary.losses == 1
    assert resp.trades[0].pnl_cents == -1974
    assert resp.summary.final_balance_cents == 100000 - 1974


async def test_no_price_counts_in_winrate_but_not_in_pnl():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff, home="Arsenal", away="Chelsea",
        final_home=2, final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    # No Opportunity seeded.

    resp = _run()
    assert resp.summary.matches_bet_on == 1
    assert resp.summary.matches_with_price_data == 0
    assert resp.summary.wins == 1
    assert resp.trades[0].observed_yes_ask_cents is None
    assert resp.trades[0].pnl_cents is None
    assert resp.trades[0].count is None
    assert resp.summary.final_balance_cents == 100000  # unchanged
    # No curve points added (only start)
    assert len(resp.bankroll_curve) == 1


async def test_min_yes_price_skips_when_observed_too_low():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff, home="Arsenal", away="Chelsea",
        final_home=2, final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _seed_opp(kickoff, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=80)

    resp = _run({"min_yes_price": 90})
    assert resp.summary.matches_bet_on == 0  # skipped
    assert resp.summary.wins == 0
    assert len(resp.trades) == 0


async def test_min_yes_price_ignored_when_no_observation():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff, home="Arsenal", away="Chelsea",
        final_home=2, final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    # No opportunity — min_yes_price must NOT cause a skip.
    resp = _run({"min_yes_price": 90})
    assert resp.summary.matches_bet_on == 1
    assert resp.summary.wins == 1


async def test_bankroll_compounds_chronologically():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff1 = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    kickoff2 = datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff1, home="Arsenal", away="Chelsea",
        final_home=2, final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _make_cached_match(
        match_id="fd:2", kickoff=kickoff2, home="Liverpool", away="Tottenham Hotspur",
        final_home=2, final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _seed_opp(kickoff1, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=90)
    _seed_opp(kickoff2, 75, "Liverpool", "Tottenham Hotspur", "Liverpool", yes_ask=90)

    resp = _run()
    # First: bet_cents=2000 → count=22 → cost=1980 → pnl=220; bankroll=100220
    # Second: bet_cents=round(100220*0.02)=2004 → count=22 → cost=1980 → pnl=220; bankroll=100440
    assert resp.trades[0].bankroll_after_cents == 100220
    assert resp.trades[1].bankroll_after_cents == 100440
    assert resp.summary.final_balance_cents == 100440


async def test_bankroll_curve_starts_at_date_from_with_initial_balance():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1", kickoff=kickoff, home="Arsenal", away="Chelsea",
        final_home=2, final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _seed_opp(kickoff, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=90)

    resp = _run()
    assert resp.bankroll_curve[0].balance_cents == 100000
    assert resp.bankroll_curve[0].t.isoformat().startswith("2026-03-01")
    # One trade with observed price → one additional curve point at kickoff
    assert len(resp.bankroll_curve) == 2
    assert resp.bankroll_curve[1].t == kickoff
```

- [ ] **Step 2: Run — all fail**

Run: `uv run pytest tests/test_run_backtest.py -v`
Expected: FAIL (run_backtest not defined yet).

- [ ] **Step 3: Implement `run_backtest`**

Append to `src/predictions/backtest.py`:

```python
from datetime import time, timezone


async def run_backtest(req: BacktestRequest) -> BacktestResponse:
    """Top-level orchestrator: cache → simulate → price lookup → P&L."""
    from predictions.soccer_cache import ensure_matches_cached

    cache_result = await ensure_matches_cached(
        req.league, req.date_from.isoformat(), req.date_to.isoformat()
    )

    trades: list[BacktestTrade] = []
    curve: list[BacktestCurvePoint] = [
        BacktestCurvePoint(
            t=datetime.combine(req.date_from, time.min, tzinfo=timezone.utc),
            balance_cents=req.initial_balance_cents,
        )
    ]

    bankroll = req.initial_balance_cents
    wins = 0
    losses = 0
    matches_bet_on = 0
    matches_with_price = 0

    # Matches come in chronological order from ensure_matches_cached.
    from predictions.soccer_cache import SessionLocal as SoccerSession, SoccerGoal

    for match in cache_result.matches:
        # Attach goals — the session may have detached the match.
        s = SoccerSession()
        goals = (
            s.query(SoccerGoal)
            .filter(SoccerGoal.match_id == match.id)
            .order_by(SoccerGoal.sequence)
            .all()
        )
        s.close()
        match.goals = goals  # type: ignore[attr-defined]

        trigger = simulate_match(match, req)
        if trigger is None:
            continue

        observed = find_observed_yes_ask(
            match, fire_minute=trigger.fired_at_minute, leading_side=trigger.leading_side
        )

        # min_yes_price filter: only when observed price exists.
        if observed is not None and req.min_yes_price > 0 and observed < req.min_yes_price:
            continue

        # Resolve result from final score.
        if trigger.leading_side == "home":
            won = match.home_score > match.away_score
        else:
            won = match.away_score > match.home_score

        count: int | None = None
        cost_cents: int | None = None
        pnl_cents: int | None = None
        if observed is not None:
            bet_cents = round(bankroll * req.bet_percent)
            count = max(1, bet_cents // observed)
            cost_cents = count * observed
            pnl_cents = count * (100 - observed) if won else -cost_cents
            bankroll += pnl_cents
            matches_with_price += 1

        matches_bet_on += 1
        if won:
            wins += 1
        else:
            losses += 1

        trades.append(BacktestTrade(
            match_id=match.id,
            kickoff_at=match.kickoff_at,
            league=req.league,
            home_team=match.home_team,
            away_team=match.away_team,
            final_home=match.home_score,
            final_away=match.away_score,
            fired_at_minute=trigger.fired_at_minute,
            score_at_fire_home=trigger.score_at_fire_home,
            score_at_fire_away=trigger.score_at_fire_away,
            leading_side=trigger.leading_side,
            result="win" if won else "loss",
            observed_yes_ask_cents=observed,
            count=count,
            cost_cents=cost_cents,
            pnl_cents=pnl_cents,
            bankroll_after_cents=bankroll,
        ))

        if observed is not None:
            curve.append(BacktestCurvePoint(t=match.kickoff_at, balance_cents=bankroll))

    settled = wins + losses
    win_rate = wins / settled if settled else 0.0
    pnl_cents = bankroll - req.initial_balance_cents
    pnl_pct = pnl_cents / req.initial_balance_cents if req.initial_balance_cents else 0.0

    summary = BacktestSummary(
        matches_scanned=len(cache_result.matches),
        matches_bet_on=matches_bet_on,
        matches_with_price_data=matches_with_price,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 4),
        initial_balance_cents=req.initial_balance_cents,
        final_balance_cents=bankroll,
        pnl_cents=pnl_cents,
        pnl_pct=round(pnl_pct, 4),
    )

    return BacktestResponse(
        summary=summary,
        trades=trades,
        bankroll_curve=curve,
        partial=cache_result.partial,
        missing_count=cache_result.missing_count,
    )
```

- [ ] **Step 4: Run — all pass**

Run: `uv run pytest tests/test_run_backtest.py -v`
Expected: 7 PASS (1 model validation + 6 integration).

- [ ] **Step 5: Full Python check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest tests/ -v`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/predictions/backtest.py tests/test_run_backtest.py
git commit -m "feat(backtest): add run_backtest orchestrator with P&L + bankroll curve"
```

---

## Task 9: `POST /api/backtest/soccer` endpoint

**Files:**
- Modify: `src/predictions/api.py`
- Test: `tests/test_backtest_api.py`

- [ ] **Step 1: Write failing API test**

Create `tests/test_backtest_api.py`:

```python
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app
    return TestClient(app)


def test_backtest_requires_bearer(client):
    resp = client.post("/api/backtest/soccer", json={})
    assert resp.status_code == 401


def test_backtest_returns_503_when_api_key_missing(client, monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
    body = {
        "league": "PL", "date_from": "2026-03-01", "date_to": "2026-04-01",
        "min_minute": 75, "min_lead": 2, "min_yes_price": 0,
        "initial_balance_cents": 100000, "bet_percent": 0.02,
    }
    resp = client.post(
        "/api/backtest/soccer",
        json=body,
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 503


def test_backtest_validation_400_on_bad_date_range(client, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "k")
    body = {
        "league": "PL", "date_from": "2026-05-01", "date_to": "2026-03-01",
        "min_minute": 75, "min_lead": 2, "min_yes_price": 0,
        "initial_balance_cents": 100000, "bet_percent": 0.02,
    }
    resp = client.post(
        "/api/backtest/soccer",
        json=body,
        headers={"Authorization": "Bearer test-token"},
    )
    # FastAPI returns 422 for Pydantic ValidationError by default; we map to 400.
    assert resp.status_code in (400, 422)


def test_backtest_200_happy_path(client, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from predictions.backtest import BacktestResponse, BacktestSummary

    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "k")
    fake = BacktestResponse(
        summary=BacktestSummary(
            matches_scanned=0, matches_bet_on=0, matches_with_price_data=0,
            wins=0, losses=0, win_rate=0.0, initial_balance_cents=100000,
            final_balance_cents=100000, pnl_cents=0, pnl_pct=0.0,
        ),
        trades=[], bankroll_curve=[], partial=False, missing_count=0,
    )
    with patch("predictions.backtest.run_backtest", AsyncMock(return_value=fake)):
        body = {
            "league": "PL", "date_from": "2026-03-01", "date_to": "2026-04-01",
            "min_minute": 75, "min_lead": 2, "min_yes_price": 0,
            "initial_balance_cents": 100000, "bet_percent": 0.02,
        }
        resp = client.post(
            "/api/backtest/soccer",
            json=body,
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 200
    assert resp.json()["summary"]["matches_scanned"] == 0
```

- [ ] **Step 2: Run — all fail**

Run: `uv run pytest tests/test_backtest_api.py -v`
Expected: FAIL (endpoint not defined).

- [ ] **Step 3: Register the endpoint**

Add to `src/predictions/api.py`. Place the import near the top with other imports:

```python
from predictions import backtest as backtest_mod
from predictions.backtest import BacktestRequest, BacktestResponse
```

Then append this handler near the other endpoints (e.g., after `update_config`):

```python
@app.post(
    "/api/backtest/soccer",
    response_model=BacktestResponse,
    dependencies=[Depends(_check_token)],
)
async def post_backtest_soccer(req: BacktestRequest):
    if not os.getenv("FOOTBALL_DATA_API_KEY"):
        raise HTTPException(503, "FOOTBALL_DATA_API_KEY is not configured")
    try:
        return await backtest_mod.run_backtest(req)
    except ValueError as e:
        raise HTTPException(400, str(e))
```

- [ ] **Step 4: Run — all pass**

Run: `uv run pytest tests/test_backtest_api.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Full Python check**

Run: `uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest tests/ -v`
Expected: all clean.

- [ ] **Step 6: Commit**

```bash
git add src/predictions/api.py tests/test_backtest_api.py
git commit -m "feat(api): add POST /api/backtest/soccer endpoint"
```

---

## Task 10: Environment + deployment wiring

**Files:**
- Modify: `.env.example`
- Modify: `sst.config.ts`

- [ ] **Step 1: Append to `.env.example`**

Add this block to the end of `.env.example`:

```
# --- Soccer backtest -------------------------------------------------------

# football-data.org v4 API key. Required for the /backtest page. Get one at
# https://www.football-data.org/client/register . Free tier allows 10
# requests/minute which is enough for the backtest cache.
FOOTBALL_DATA_API_KEY=

# Filesystem path for the soccer-match cache SQLite file. Defaults to the
# repo root in dev; production overrides to /tmp/soccer-cache.db via SST.
SOCCER_CACHE_DB_PATH=./soccer-cache.db
```

- [ ] **Step 2: Edit `sst.config.ts`**

After the `const apiToken = new sst.Secret("ApiToken");` line, add:

```typescript
    const footballDataApiKey = new sst.Secret("FootballDataApiKey");
```

Inside the `environment` block of the `Api` service (right before `CORS_ORIGINS`), add:

```typescript
          FOOTBALL_DATA_API_KEY: footballDataApiKey.value,
          SOCCER_CACHE_DB_PATH: "/tmp/soccer-cache.db",
```

Do NOT touch the Dashboard environment block — the frontend never sees this key directly.

- [ ] **Step 3: Verify no-op changes**

Run: `uv run ruff check . && uv run ruff format --check . && uv run ty check`
Expected: clean. (SST config is TypeScript, but not type-checked by our Python tools — a syntax check is implicit at `sst dev` time, which is outside this plan's scope.)

- [ ] **Step 4: Commit**

```bash
git add .env.example sst.config.ts
git commit -m "chore(infra): wire FOOTBALL_DATA_API_KEY secret + SOCCER_CACHE_DB_PATH"
```

---

## Task 11: Add `recharts` dependency to the dashboard

**Files:**
- Modify: `dashboard/package.json`

- [ ] **Step 1: Install recharts**

Run from the repo root:

```bash
pnpm --filter dashboard add recharts@^2
```

- [ ] **Step 2: Verify build still passes**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add dashboard/package.json pnpm-lock.yaml
git commit -m "chore(dashboard): add recharts for backtest bankroll chart"
```

---

## Task 12: `/backtest` page — layout + parameter controls (no submit yet)

**Files:**
- Create: `dashboard/app/backtest/page.tsx`

- [ ] **Step 1: Create the page skeleton**

Write `dashboard/app/backtest/page.tsx`:

```tsx
"use client";

import { useState } from "react";

type League = "PL" | "PD" | "BL1";

interface FormState {
    league: League;
    date_from: string;
    date_to: string;
    min_minute: number;
    min_lead: number;
    min_yes_price: number;
    initial_balance_cents: number;
    bet_percent: number;
}

function defaultForm(): FormState {
    const today = new Date();
    const monthAgo = new Date(today);
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return {
        league: "PL",
        date_from: iso(monthAgo),
        date_to: iso(today),
        min_minute: 75,
        min_lead: 2,
        min_yes_price: 0,
        initial_balance_cents: 100000,
        bet_percent: 0.02,
    };
}

export default function BacktestPage() {
    const [form, setForm] = useState<FormState>(defaultForm);

    const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
        setForm((prev) => ({ ...prev, [key]: value }));
    };

    return (
        <div className="min-h-screen bg-black text-white p-6">
            <header className="flex items-center justify-between mb-6">
                <a href="/" className="text-sm text-gray-400 hover:text-white">
                    ← Dashboard
                </a>
                <h1 className="text-2xl font-semibold">Strategy Backtest</h1>
                <span className="text-sm text-gray-400" />
            </header>
            <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-6">
                <aside className="space-y-4 bg-gray-900 p-4 rounded">
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">League</label>
                        <select
                            value={form.league}
                            onChange={(e) => update("league", e.target.value as League)}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1"
                        >
                            <option value="PL">EPL</option>
                            <option value="PD">La Liga</option>
                            <option value="BL1">Bundesliga</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Date from</label>
                        <input
                            type="date"
                            value={form.date_from}
                            onChange={(e) => update("date_from", e.target.value)}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Date to</label>
                        <input
                            type="date"
                            value={form.date_to}
                            onChange={(e) => update("date_to", e.target.value)}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Min minute: {form.min_minute}
                        </label>
                        <input
                            type="range"
                            min={1}
                            max={90}
                            value={form.min_minute}
                            onChange={(e) => update("min_minute", Number(e.target.value))}
                            className="w-full"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Min lead: {form.min_lead}
                        </label>
                        <input
                            type="range"
                            min={1}
                            max={5}
                            value={form.min_lead}
                            onChange={(e) => update("min_lead", Number(e.target.value))}
                            className="w-full"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Min YES price: {form.min_yes_price === 0 ? "0 = disabled" : `${form.min_yes_price}¢`}
                        </label>
                        <input
                            type="range"
                            min={0}
                            max={99}
                            value={form.min_yes_price}
                            onChange={(e) => update("min_yes_price", Number(e.target.value))}
                            className="w-full"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Initial balance ($)
                        </label>
                        <input
                            type="number"
                            min={10}
                            value={form.initial_balance_cents / 100}
                            onChange={(e) =>
                                update("initial_balance_cents", Math.round(Number(e.target.value) * 100))
                            }
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1"
                        />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Bet %: {(form.bet_percent * 100).toFixed(1)}%
                        </label>
                        <input
                            type="range"
                            min={0.005}
                            max={0.10}
                            step={0.005}
                            value={form.bet_percent}
                            onChange={(e) => update("bet_percent", Number(e.target.value))}
                            className="w-full"
                        />
                    </div>
                    <button
                        disabled
                        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 px-4 py-2 rounded"
                    >
                        Run backtest
                    </button>
                    <p className="text-xs text-gray-500">
                        P&amp;L reflects only matches with observed Kalshi prices. All bets are
                        counted in win rate.
                    </p>
                </aside>
                <main>{/* results placeholder — Tasks 13–16 */}</main>
            </div>
        </div>
    );
}
```

- [ ] **Step 2: Build dashboard, confirm no errors**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Expected: clean build.

- [ ] **Step 3: Manually verify the page loads**

In one terminal: `pnpm dev:api`. In another: `pnpm dev:dashboard`. Open `http://localhost:3777/backtest` (after logging in via `/`). The form renders with all controls; Run button is disabled. No console errors.

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/backtest/page.tsx
git commit -m "feat(dashboard): scaffold /backtest page with parameter controls"
```

---

## Task 13: Wire up submit + summary cards

**Files:**
- Modify: `dashboard/app/backtest/page.tsx`

- [ ] **Step 1: Add result types, state, fetch handler, and summary grid**

Replace the contents of `dashboard/app/backtest/page.tsx` with (builds on Task 12, so preserve the form code):

```tsx
"use client";

import { useState } from "react";

type League = "PL" | "PD" | "BL1";

interface FormState {
    league: League;
    date_from: string;
    date_to: string;
    min_minute: number;
    min_lead: number;
    min_yes_price: number;
    initial_balance_cents: number;
    bet_percent: number;
}

interface BacktestSummary {
    matches_scanned: number;
    matches_bet_on: number;
    matches_with_price_data: number;
    wins: number;
    losses: number;
    win_rate: number;
    initial_balance_cents: number;
    final_balance_cents: number;
    pnl_cents: number;
    pnl_pct: number;
}

interface BacktestTrade {
    match_id: string;
    kickoff_at: string;
    league: League;
    home_team: string;
    away_team: string;
    final_home: number;
    final_away: number;
    fired_at_minute: number;
    score_at_fire_home: number;
    score_at_fire_away: number;
    leading_side: "home" | "away";
    result: "win" | "loss";
    observed_yes_ask_cents: number | null;
    count: number | null;
    cost_cents: number | null;
    pnl_cents: number | null;
    bankroll_after_cents: number;
}

interface BacktestCurvePoint {
    t: string;
    balance_cents: number;
}

interface BacktestResponse {
    summary: BacktestSummary;
    trades: BacktestTrade[];
    bankroll_curve: BacktestCurvePoint[];
    partial: boolean;
    missing_count: number;
}

function defaultForm(): FormState {
    const today = new Date();
    const monthAgo = new Date(today);
    monthAgo.setMonth(monthAgo.getMonth() - 1);
    const iso = (d: Date) => d.toISOString().slice(0, 10);
    return {
        league: "PL",
        date_from: iso(monthAgo),
        date_to: iso(today),
        min_minute: 75,
        min_lead: 2,
        min_yes_price: 0,
        initial_balance_cents: 100000,
        bet_percent: 0.02,
    };
}

function fmtUsd(cents: number): string {
    const dollars = cents / 100;
    return dollars.toLocaleString("en-US", { style: "currency", currency: "USD" });
}

function SummaryCard({
    label, value, color,
}: { label: string; value: string; color?: string }) {
    return (
        <div className="bg-gray-900 rounded p-3">
            <div className="text-xs uppercase tracking-wider text-gray-400">{label}</div>
            <div className={`text-lg font-semibold ${color ?? "text-white"}`}>{value}</div>
        </div>
    );
}

export default function BacktestPage() {
    const [form, setForm] = useState<FormState>(defaultForm);
    const [loading, setLoading] = useState(false);
    const [result, setResult] = useState<BacktestResponse | null>(null);
    const [error, setError] = useState<string | null>(null);

    const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
        setForm((prev) => ({ ...prev, [key]: value }));
    };

    async function handleSubmit() {
        setLoading(true);
        setError(null);
        try {
            const res = await fetch("/api/backtest/soccer", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(form),
            });
            if (res.status === 401) {
                window.location.href = "/";
                return;
            }
            if (!res.ok) {
                const body = await res.text();
                setError(`${res.status}: ${body}`);
                return;
            }
            const data = (await res.json()) as BacktestResponse;
            setResult(data);
        } catch (e: any) {
            setError(e.message || "Network error");
        } finally {
            setLoading(false);
        }
    }

    const pnlColor = (cents: number) =>
        cents > 0 ? "text-green-400" : cents < 0 ? "text-red-400" : "text-white";

    return (
        <div className="min-h-screen bg-black text-white p-6">
            <header className="flex items-center justify-between mb-6">
                <a href="/" className="text-sm text-gray-400 hover:text-white">← Dashboard</a>
                <h1 className="text-2xl font-semibold">Strategy Backtest</h1>
                <span className="text-sm text-gray-400" />
            </header>
            <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-6">
                <aside className="space-y-4 bg-gray-900 p-4 rounded">
                    {/* --- Controls (unchanged from Task 12) --- */}
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">League</label>
                        <select
                            value={form.league}
                            onChange={(e) => update("league", e.target.value as League)}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1"
                        >
                            <option value="PL">EPL</option>
                            <option value="PD">La Liga</option>
                            <option value="BL1">Bundesliga</option>
                        </select>
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Date from</label>
                        <input type="date" value={form.date_from}
                            onChange={(e) => update("date_from", e.target.value)}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Date to</label>
                        <input type="date" value={form.date_to}
                            onChange={(e) => update("date_to", e.target.value)}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Min minute: {form.min_minute}</label>
                        <input type="range" min={1} max={90} value={form.min_minute}
                            onChange={(e) => update("min_minute", Number(e.target.value))} className="w-full" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Min lead: {form.min_lead}</label>
                        <input type="range" min={1} max={5} value={form.min_lead}
                            onChange={(e) => update("min_lead", Number(e.target.value))} className="w-full" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Min YES price: {form.min_yes_price === 0 ? "0 = disabled" : `${form.min_yes_price}¢`}
                        </label>
                        <input type="range" min={0} max={99} value={form.min_yes_price}
                            onChange={(e) => update("min_yes_price", Number(e.target.value))} className="w-full" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">Initial balance ($)</label>
                        <input type="number" min={10} value={form.initial_balance_cents / 100}
                            onChange={(e) => update("initial_balance_cents", Math.round(Number(e.target.value) * 100))}
                            className="w-full bg-black border border-gray-700 rounded px-2 py-1" />
                    </div>
                    <div>
                        <label className="block text-sm text-gray-300 mb-1">
                            Bet %: {(form.bet_percent * 100).toFixed(1)}%
                        </label>
                        <input type="range" min={0.005} max={0.10} step={0.005} value={form.bet_percent}
                            onChange={(e) => update("bet_percent", Number(e.target.value))} className="w-full" />
                    </div>
                    <button
                        onClick={handleSubmit}
                        disabled={loading}
                        className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 px-4 py-2 rounded"
                    >
                        {loading ? "Running backtest…" : "Run backtest"}
                    </button>
                    <p className="text-xs text-gray-500">
                        P&amp;L reflects only matches with observed Kalshi prices. All bets are
                        counted in win rate.
                    </p>
                </aside>
                <main className="space-y-6">
                    {error && (
                        <div className="bg-red-900/40 border border-red-700 text-red-200 rounded p-3 text-sm">
                            {error}
                        </div>
                    )}
                    {result && (
                        <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            <SummaryCard label="Scanned" value={String(result.summary.matches_scanned)} />
                            <SummaryCard label="Bet on" value={String(result.summary.matches_bet_on)} />
                            <SummaryCard
                                label="Win rate"
                                value={`${(result.summary.win_rate * 100).toFixed(1)}%`}
                            />
                            <SummaryCard label="Wins" value={String(result.summary.wins)} />
                            <SummaryCard label="Losses" value={String(result.summary.losses)} />
                            <SummaryCard
                                label="P&L %"
                                value={`${(result.summary.pnl_pct * 100).toFixed(2)}%`}
                                color={pnlColor(result.summary.pnl_cents)}
                            />
                            <SummaryCard
                                label="P&L $"
                                value={fmtUsd(result.summary.pnl_cents)}
                                color={pnlColor(result.summary.pnl_cents)}
                            />
                            <SummaryCard
                                label="w/ prices"
                                value={`${result.summary.matches_with_price_data} / ${result.summary.matches_bet_on}`}
                            />
                        </section>
                    )}
                </main>
            </div>
        </div>
    );
}
```

- [ ] **Step 2: Build + manual verify**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Manually: load `/backtest`, click Run, confirm summary cards render (server-side, if no FOOTBALL_DATA_API_KEY, expect the 503 red banner).

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/backtest/page.tsx
git commit -m "feat(dashboard): wire submit + summary cards on /backtest"
```

---

## Task 14: Bankroll curve chart (conditional render)

**Files:**
- Modify: `dashboard/app/backtest/page.tsx`

- [ ] **Step 1: Import recharts + add chart component**

Inside `dashboard/app/backtest/page.tsx`, add to the imports:

```tsx
import {
    CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis,
} from "recharts";
```

Add this component definition just above `export default function BacktestPage`:

```tsx
function BankrollChart({ points }: { points: BacktestCurvePoint[] }) {
    const data = points.map((p) => ({
        t: new Date(p.t).getTime(),
        balance: p.balance_cents / 100,
    }));
    return (
        <div className="h-64 bg-gray-900 rounded p-3">
            <ResponsiveContainer width="100%" height="100%">
                <LineChart data={data}>
                    <CartesianGrid stroke="#333" />
                    <XAxis
                        dataKey="t"
                        type="number"
                        domain={["dataMin", "dataMax"]}
                        tickFormatter={(t) => new Date(t).toISOString().slice(0, 10)}
                        stroke="#888"
                    />
                    <YAxis stroke="#888" tickFormatter={(v) => `$${v.toFixed(0)}`} />
                    <Tooltip
                        labelFormatter={(t) => new Date(Number(t)).toISOString().slice(0, 16)}
                        formatter={(v: number) => `$${v.toFixed(2)}`}
                        contentStyle={{ background: "#111", border: "1px solid #333" }}
                    />
                    <Line type="monotone" dataKey="balance" stroke="#3b82f6" dot={false} />
                </LineChart>
            </ResponsiveContainer>
        </div>
    );
}
```

Inside the `<main>` block, below the summary cards section and above the closing `</main>`, add:

```tsx
                    {result && (
                        result.summary.matches_with_price_data > 0 ? (
                            <BankrollChart points={result.bankroll_curve} />
                        ) : (
                            <div className="bg-gray-900 rounded p-4 text-sm text-gray-400">
                                No Kalshi price data observed in this range; bankroll curve unavailable.
                            </div>
                        )
                    )}
```

- [ ] **Step 2: Build + manual verify**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Manually: run a backtest with `min_yes_price=0`, confirm either the chart or the placeholder renders depending on whether prices were observed.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/backtest/page.tsx
git commit -m "feat(dashboard): add conditional bankroll curve chart"
```

---

## Task 15: Match log

**Files:**
- Modify: `dashboard/app/backtest/page.tsx`

- [ ] **Step 1: Add a `TradeRow` component + log section**

Add this component above `export default function BacktestPage`:

```tsx
function TradeRow({ trade }: { trade: BacktestTrade }) {
    const won = trade.result === "win";
    const dateStr = new Date(trade.kickoff_at).toISOString().slice(0, 10);
    const emoji = won ? "✅" : "❌";
    const secondLine = trade.observed_yes_ask_cents === null
        ? `Fired min ${trade.fired_at_minute} @ ${trade.score_at_fire_home}-${trade.score_at_fire_away} · (no price) · winrate only`
        : `Fired min ${trade.fired_at_minute} @ ${trade.score_at_fire_home}-${trade.score_at_fire_away} · ` +
          `bet $${(trade.cost_cents! / 100).toFixed(2)} · ` +
          `P&L ${trade.pnl_cents! >= 0 ? "+" : ""}$${(trade.pnl_cents! / 100).toFixed(2)} · ` +
          `bankroll $${(trade.bankroll_after_cents / 100).toFixed(2)}`;
    return (
        <div className={`p-2 rounded ${won ? "bg-green-900/30" : "bg-red-900/30"}`}>
            <div className="text-sm">
                {dateStr} · {trade.home_team} {trade.final_home} – {trade.final_away} {trade.away_team} {emoji}
            </div>
            <div className="text-xs text-gray-400">{secondLine}</div>
        </div>
    );
}
```

Inside `<main>` below the chart block, add:

```tsx
                    {result && result.trades.length > 0 && (
                        <section className="space-y-2">
                            {result.trades.map((t) => (
                                <TradeRow key={t.match_id} trade={t} />
                            ))}
                        </section>
                    )}
                    {result && result.trades.length === 0 && (
                        <div className="text-sm text-gray-400">
                            No fixtures met the trigger in this range.
                        </div>
                    )}
```

- [ ] **Step 2: Build + manual verify**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Manually: rerun the backtest; confirm the log populates with colored rows.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/backtest/page.tsx
git commit -m "feat(dashboard): add colored match log to /backtest"
```

---

## Task 16: Loading, empty, and partial states

**Files:**
- Modify: `dashboard/app/backtest/page.tsx`

- [ ] **Step 1: Add partial banner + loading skeletons**

Inside `<main>`, above the summary-cards block, add:

```tsx
                    {result?.partial && (
                        <div className="bg-yellow-900/40 border border-yellow-700 text-yellow-200 rounded p-3 text-sm">
                            {result.missing_count} matches not yet cached — retry in ~60 s.
                        </div>
                    )}
                    {loading && (
                        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                            {Array.from({ length: 8 }).map((_, i) => (
                                <div key={i} className="h-16 bg-gray-900 rounded animate-pulse" />
                            ))}
                        </div>
                    )}
```

- [ ] **Step 2: Build + manual verify**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Manually:
- Click Run — skeleton cards appear during loading.
- Force a partial via an aggressive range on a cold cache — banner appears.

- [ ] **Step 3: Commit**

```bash
git add dashboard/app/backtest/page.tsx
git commit -m "feat(dashboard): add loading skeleton + partial banner to /backtest"
```

---

## Task 17: Add header link from main dashboard

**Files:**
- Modify: `dashboard/app/page.tsx`

- [ ] **Step 1: Locate the header**

Open `dashboard/app/page.tsx`. Find the top-level header area (search for the "Kalshi" brand text or the user-email area). In this monolithic file, the header is early in the JSX tree — probably around the `<header>` or topmost `<div>` that renders the logged-in chrome.

- [ ] **Step 2: Add a link**

Adjacent to the existing user-email / logout control, insert:

```tsx
<a
    href="/backtest"
    className="text-sm text-blue-400 hover:text-blue-200 underline"
>
    Strategy Backtest
</a>
```

The exact placement is flexible — group it with any existing nav or header controls.

- [ ] **Step 3: Build + manual verify**

Run: `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
Manually: load `/`, confirm the new link appears and navigates to `/backtest`.

- [ ] **Step 4: Commit**

```bash
git add dashboard/app/page.tsx
git commit -m "feat(dashboard): add Strategy Backtest link on main dashboard"
```

---

## Task 18: Final end-to-end verification

**Files:** (none — verification only)

- [ ] **Step 1: Run the full Python check**

```bash
uv run ruff check . && uv run ruff format --check . && uv run ty check && uv run pytest tests/ -v
```
Expected: clean.

- [ ] **Step 2: Run the dashboard check**

```bash
cd dashboard && pnpm lint && pnpm fmt:check && pnpm build
```
Expected: clean.

- [ ] **Step 3: Manual dashboard QA per spec §Manual dashboard QA**

With `pnpm dev:api` + `pnpm dev:dashboard` running and `FOOTBALL_DATA_API_KEY` set in `.env`:

- Load `/backtest`, run with defaults on EPL. Confirm summary cards render.
- Confirm bankroll chart appears only when `w/ prices > 0` (compare against the empty-price placeholder otherwise).
- Submit an invalid date range (`date_from > date_to`) — red banner with backend error.
- Force a partial result via a wide range on a cold cache — yellow banner with `N matches not yet cached`.
- Load `/` — confirm main dashboard still works; no regressions.

- [ ] **Step 4: Mark spec §"Testing" as done**

Cross-check each bullet in the spec's testing section against the committed test files. All items mapped:

- `simulate_match` unit tests → `tests/test_simulate_match.py`
- `find_observed_yes_ask` → `tests/test_find_observed_yes_ask.py`
- `run_backtest` integration → `tests/test_run_backtest.py`
- `soccer_cache.ensure_matches_cached` → `tests/test_soccer_cache.py`
- API endpoint smoke → `tests/test_backtest_api.py`
- Manual dashboard QA → this step.

---

## Spec-to-plan traceability

| Spec section | Task |
|--------------|------|
| §Strategy model — `simulate_match` | Task 5 |
| §Strategy model — `min_yes_price` filter semantics | Task 8 |
| §Data sources — football-data.org client | Task 2 |
| §Data sources — `find_observed_yes_ask` | Tasks 6, 7 |
| §Architecture — `soccer_cache.py` | Tasks 1–3 |
| §Architecture — `backtest.py` | Tasks 4–8 |
| §Architecture — API change | Task 9 |
| §Storage — `soccer-cache.db` schema + migrations | Task 1 |
| §Storage — cache policy (FINISHED-only, permanent) | Task 3 |
| §API contract — request/response shape | Tasks 4, 8 |
| §API contract — 400/401/503 | Task 9 |
| §API contract — partial results | Tasks 3, 8 |
| §UI — layout + controls | Task 12 |
| §UI — summary cards | Task 13 |
| §UI — bankroll curve | Task 14 |
| §UI — match log | Task 15 |
| §UI — loading / partial / empty / error | Tasks 13, 16 |
| §UI — header link from `/` | Task 17 |
| §Environment / deployment | Task 10 |
| §Frontend deps (recharts) | Task 11 |
| §Testing | Tasks 1–9, 18 |
