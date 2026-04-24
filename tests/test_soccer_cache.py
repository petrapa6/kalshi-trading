from datetime import datetime, timezone

import httpx
import pytest
from sqlalchemy import inspect


def test_init_soccer_db_creates_tables():
    from predictions import soccer_cache

    soccer_cache.init_soccer_db()

    names = set(inspect(soccer_cache.engine).get_table_names())
    assert {"soccer_matches", "soccer_goals"}.issubset(names)


def test_soccer_match_round_trip():
    from predictions.soccer_cache import SessionLocal, SoccerGoal, SoccerMatch, init_soccer_db

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


def _mock_transport(responses: list[tuple[int, dict]]) -> httpx.MockTransport:
    """Build a MockTransport that returns the given (status, json) tuples in order."""
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = next(iterator)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


async def test_client_sends_auth_header():
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
            1: _fixture_detail_body(
                1,
                [
                    {"minute": 30, "injuryTime": None, "team": {"id": 101}, "type": "REGULAR"},
                    {"minute": 80, "injuryTime": None, "team": {"id": 201}, "type": "REGULAR"},
                ],
            ),
            2: _fixture_detail_body(2, []),
        },
    )

    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert result.partial is False
    assert result.missing_count == 0
    assert len(result.matches) == 2
    assert fake.detail_calls == 2


async def test_ensure_matches_cached_skips_already_cached():
    from datetime import datetime, timezone

    from predictions.soccer_cache import (
        SessionLocal,
        SoccerMatch,
        ensure_matches_cached,
        init_soccer_db,
    )

    init_soccer_db()
    # Pre-populate match fd:1
    session = SessionLocal()
    session.add(
        SoccerMatch(
            id="fd:1",
            competition="PL",
            kickoff_at=datetime(2026, 4, 1, 14, tzinfo=timezone.utc),
            home_team="Home1",
            away_team="Away1",
            home_score=2,
            away_score=1,
            status="FINISHED",
            fetched_at=datetime.now(timezone.utc),
        )
    )
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
    from predictions.soccer_cache import (
        SessionLocal,
        SoccerGoal,
        ensure_matches_cached,
        init_soccer_db,
    )

    init_soccer_db()
    # Home team ID is 101; away is 201. An own-goal with team.id=101 means
    # home accidentally scored into their own net → beneficiary is away.
    fake = _FakeFootballClient(
        list_body=_fixture_list_body([1]),
        detail_bodies={
            1: _fixture_detail_body(
                1,
                [
                    {"minute": 30, "injuryTime": None, "team": {"id": 101}, "type": "OWN"},
                ],
            )
        },
    )
    await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    session = SessionLocal()
    goal = session.query(SoccerGoal).one()
    assert goal.side == "away"
    assert goal.is_own_goal == 1
    session.close()
