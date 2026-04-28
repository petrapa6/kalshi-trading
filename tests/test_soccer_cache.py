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

    fetched = session.query(SoccerMatch).filter_by(id="fd:1").one()
    assert fetched.home_team == "Arsenal"
    assert len(session.query(SoccerGoal).filter_by(match_id="fd:1").all()) == 1
    session.close()


def _mock_transport(responses: list[tuple[int, dict]]) -> httpx.MockTransport:
    """Build a MockTransport that returns the given (status, json) tuples in order."""
    iterator = iter(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        status, body = next(iterator)
        return httpx.Response(status, json=body)

    return httpx.MockTransport(handler)


async def test_client_sends_auth_header():
    from predictions.soccer_cache import ApiFootballClient

    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        captured["url"] = str(request.url)
        return httpx.Response(200, json={"errors": [], "response": []})

    transport = httpx.MockTransport(handler)
    client = ApiFootballClient(api_key="secret-xyz", transport=transport)
    await client.list_matches("PL", "2026-03-01", "2026-03-31")

    assert captured["headers"]["x-apisports-key"] == "secret-xyz"
    assert "/fixtures" in captured["url"]
    assert "league=39" in captured["url"]
    assert "season=" in captured["url"]
    assert "from=2026-03-01" in captured["url"]
    assert "status=FT-AET-PEN" in captured["url"]


async def test_client_raises_rate_limited_on_429():
    from predictions.soccer_cache import ApiFootballClient, RateLimitedError

    client = ApiFootballClient(
        api_key="k", transport=_mock_transport([(429, {"message": "rate limited"})])
    )

    with pytest.raises(RateLimitedError):
        await client.list_matches("PL", "2026-03-01", "2026-03-31")


async def test_client_get_match_goals_shape():
    from predictions.soccer_cache import ApiFootballClient

    body = {
        "errors": [],
        "response": [
            {
                "fixture": {
                    "id": 42,
                    "date": "2026-04-01T14:00:00+00:00",
                    "status": {"short": "FT"},
                },
                "league": {"id": 39, "season": 2025},
                "teams": {
                    "home": {"id": 1, "name": "Arsenal"},
                    "away": {"id": 2, "name": "Chelsea"},
                },
                "goals": {"home": 1, "away": 1},
                "events": [
                    {
                        "time": {"elapsed": 30, "extra": None},
                        "team": {"id": 1, "name": "Arsenal"},
                        "type": "Goal",
                        "detail": "Normal Goal",
                    },
                    {
                        "time": {"elapsed": 90, "extra": 3},
                        "team": {"id": 2, "name": "Chelsea"},
                        "type": "Goal",
                        "detail": "Own Goal",
                    },
                    {
                        "time": {"elapsed": 45, "extra": None},
                        "team": {"id": 1, "name": "Arsenal"},
                        "type": "Goal",
                        "detail": "Missed Penalty",
                    },
                ],
            }
        ],
    }
    client = ApiFootballClient(api_key="k", transport=_mock_transport([(200, body)]))
    detail = await client.get_match_goals(42)
    # Missed Penalty is filtered out; only 2 goal events remain
    assert len(detail["goals"]) == 2
    assert detail["goals"][0]["time"]["elapsed"] == 30
    assert detail["goals"][1]["detail"] == "Own Goal"


# ---------------------------------------------------------------------------
# Fake client for integration-style tests
# ---------------------------------------------------------------------------


class _FakeApiFootballClient:
    def __init__(
        self,
        list_body: dict,
        batch_bodies: dict[frozenset, dict[int, dict]],
        raise_after_batches: int | None = None,
    ):
        self.list_body = list_body
        self.batch_bodies = batch_bodies
        self.raise_after = raise_after_batches
        self.batch_calls = 0
        self.list_calls = 0

    async def list_matches(self, league, date_from, date_to):
        self.list_calls += 1
        return self.list_body

    async def get_match_goals(self, match_id):
        for k, v in self.batch_bodies.items():
            if match_id in k:
                return v.get(match_id, {})
        return {}

    async def get_match_goals_batch(self, match_ids: list[int]) -> dict[int, dict]:
        from predictions.soccer_cache import RateLimitedError

        self.batch_calls += 1
        if self.raise_after is not None and self.batch_calls > self.raise_after:
            raise RateLimitedError("boom")
        # Return whatever we have for these ids
        result = {}
        for mid in match_ids:
            for k, v in self.batch_bodies.items():
                if mid in k:
                    if mid in v:
                        result[mid] = v[mid]
        return result


def _af_fixture(mid: int, status: str = "FT") -> dict:
    """Build a single API-Football v3 fixture entry (list-call shape)."""
    return {
        "fixture": {
            "id": mid,
            "date": "2026-04-01T14:00:00+00:00",
            "status": {"short": status},
        },
        "league": {"id": 39, "season": 2025},
        "teams": {
            "home": {"id": 100 + mid, "name": f"Home{mid}"},
            "away": {"id": 200 + mid, "name": f"Away{mid}"},
        },
        "goals": {"home": 2, "away": 1},
    }


def _fixture_list_body(ids: list[int], status: str = "FT") -> dict:
    return {"errors": [], "response": [_af_fixture(mid, status) for mid in ids]}


def _af_detail(mid: int, events: list[dict] | None = None) -> dict:
    """Build a single API-Football v3 fixture detail (batch-call shape)."""
    item = dict(_af_fixture(mid))
    item["events"] = events or []
    item["goals"] = [
        e for e in (events or []) if e.get("type") == "Goal" and e.get("detail") != "Missed Penalty"
    ]
    return item


async def test_ensure_matches_cached_inserts_all_on_cold_cache():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()

    ids = list(range(1, 26))  # 25 fixtures
    list_body = _fixture_list_body(ids)

    # Two batches: [1..20] and [21..25]
    batch1_ids = ids[:20]
    batch2_ids = ids[20:]
    batch_bodies = {
        frozenset(batch1_ids): {mid: _af_detail(mid) for mid in batch1_ids},
        frozenset(batch2_ids): {mid: _af_detail(mid) for mid in batch2_ids},
    }

    fake = _FakeApiFootballClient(list_body=list_body, batch_bodies=batch_bodies)

    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert result.partial is False
    assert result.missing_count == 0
    assert len(result.matches) == 25
    assert fake.batch_calls == 2


async def test_ensure_matches_cached_skips_already_cached():
    from predictions.soccer_cache import (
        SessionLocal,
        SoccerMatch,
        ensure_matches_cached,
        init_soccer_db,
    )

    init_soccer_db()
    # Pre-populate match af:1
    session = SessionLocal()
    session.merge(
        SoccerMatch(
            id="af:1",
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

    list_body = _fixture_list_body([1, 2])
    batch_bodies = {frozenset([2]): {2: _af_detail(2)}}
    fake = _FakeApiFootballClient(list_body=list_body, batch_bodies=batch_bodies)

    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    # Only match 2 required a batch fetch; match 1 was already cached as af:1.
    assert fake.batch_calls == 1
    assert len(result.matches) == 2


async def test_ensure_matches_cached_partial_on_rate_limit():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()

    ids = [1, 2, 3]
    list_body = _fixture_list_body(ids)
    batch_bodies = {frozenset(ids): {mid: _af_detail(mid) for mid in ids}}

    # Succeed on first batch, raise on second — but with only 3 fixtures,
    # they all fit in one batch. Use raise_after_batches=0 to fail immediately.
    fake = _FakeApiFootballClient(
        list_body=list_body,
        batch_bodies=batch_bodies,
        raise_after_batches=0,  # raise on the very first batch call
    )
    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert result.partial is True
    assert result.missing_count == 3
    assert len(result.matches) == 0


async def test_ensure_matches_cached_skips_non_finished():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()
    body = _fixture_list_body([9], status="NS")
    fake = _FakeApiFootballClient(list_body=body, batch_bodies={})
    result = await ensure_matches_cached("PL", "2027-01-01", "2027-01-31", client=fake)
    assert len(result.matches) == 0
    assert fake.batch_calls == 0


async def test_own_goal_is_flipped_to_beneficiary():
    from predictions.soccer_cache import (
        SessionLocal,
        SoccerGoal,
        ensure_matches_cached,
        init_soccer_db,
    )

    init_soccer_db()
    # Home team ID for fixture 1 is 101; an own-goal with team.id=101 means
    # home accidentally scored into their own net → beneficiary is away.
    own_goal_event = {
        "time": {"elapsed": 30, "extra": None},
        "team": {"id": 101, "name": "Home1"},
        "type": "Goal",
        "detail": "Own Goal",
    }
    list_body = _fixture_list_body([1])
    batch_bodies = {frozenset([1]): {1: _af_detail(1, [own_goal_event])}}
    fake = _FakeApiFootballClient(list_body=list_body, batch_bodies=batch_bodies)

    await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    session = SessionLocal()
    goal = session.query(SoccerGoal).filter_by(match_id="af:1").one()
    assert goal.side == "away"
    assert goal.is_own_goal == 1
    session.close()


# ---------------------------------------------------------------------------
# New tests: stoppage time, 0-0 game, batch chunking
# ---------------------------------------------------------------------------


async def test_stoppage_time_goal_extra_field():
    from predictions.soccer_cache import (
        SessionLocal,
        SoccerGoal,
        ensure_matches_cached,
        init_soccer_db,
    )

    init_soccer_db()
    stoppage_goal_event = {
        "time": {"elapsed": 90, "extra": 4},
        "team": {"id": 101, "name": "Home1"},
        "type": "Goal",
        "detail": "Normal Goal",
    }
    list_body = _fixture_list_body([1])
    batch_bodies = {frozenset([1]): {1: _af_detail(1, [stoppage_goal_event])}}
    fake = _FakeApiFootballClient(list_body=list_body, batch_bodies=batch_bodies)

    await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    session = SessionLocal()
    goal = session.query(SoccerGoal).filter_by(match_id="af:1").one()
    assert goal.minute == 90
    assert goal.stoppage == 4
    session.close()


async def test_empty_event_list_zero_zero_game():
    from predictions.soccer_cache import (
        SessionLocal,
        SoccerGoal,
        ensure_matches_cached,
        init_soccer_db,
    )

    init_soccer_db()
    # Fixture with no events and 0-0 score
    zero_zero = dict(_af_fixture(99))
    zero_zero["goals"] = {"home": 0, "away": 0}
    zero_zero["events"] = []
    list_body = {"errors": [], "response": [zero_zero]}

    detail = dict(zero_zero)
    detail["goals"] = []
    batch_bodies = {frozenset([99]): {99: detail}}
    fake = _FakeApiFootballClient(list_body=list_body, batch_bodies=batch_bodies)

    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert len(result.matches) == 1
    session = SessionLocal()
    goals = session.query(SoccerGoal).filter_by(match_id="af:99").all()
    assert len(goals) == 0
    session.close()


async def test_batch_chunking_max_20():
    from predictions.soccer_cache import ensure_matches_cached, init_soccer_db

    init_soccer_db()

    ids = list(range(1, 42))  # 41 fixtures
    list_body = _fixture_list_body(ids)

    chunk1 = ids[:20]  # 20
    chunk2 = ids[20:40]  # 20
    chunk3 = ids[40:]  # 1

    batch_bodies = {
        frozenset(chunk1): {mid: _af_detail(mid) for mid in chunk1},
        frozenset(chunk2): {mid: _af_detail(mid) for mid in chunk2},
        frozenset(chunk3): {mid: _af_detail(mid) for mid in chunk3},
    }

    fake = _FakeApiFootballClient(list_body=list_body, batch_bodies=batch_bodies)

    result = await ensure_matches_cached("PL", "2026-03-01", "2026-04-30", client=fake)

    assert fake.batch_calls == 3
    assert len(result.matches) == 41
    assert result.partial is False


async def test_cross_season_range_makes_two_list_calls():
    """A date range straddling the Jul→Aug season boundary triggers two /fixtures
    list calls (one per season). 2025-06-01 → season 2024; 2025-09-01 → season 2025."""
    from predictions.soccer_cache import ApiFootballClient

    call_count = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal call_count
        call_count += 1
        return httpx.Response(200, json={"errors": [], "response": []})

    transport = httpx.MockTransport(handler)
    client = ApiFootballClient(api_key="k", transport=transport)
    await client.list_matches("PL", "2025-06-01", "2025-09-01")

    assert call_count == 2


async def test_non_empty_errors_array_raises_runtime_error():
    """HTTP 200 with a non-empty errors[] field must raise RuntimeError, not silently
    return empty results."""
    from predictions.soccer_cache import ApiFootballClient

    body = {"errors": ["Token is invalid"], "response": []}
    client = ApiFootballClient(api_key="k", transport=_mock_transport([(200, body)]))

    with pytest.raises(RuntimeError, match="API-Football error"):
        await client.list_matches("PL", "2026-03-01", "2026-03-31")
