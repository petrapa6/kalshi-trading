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
