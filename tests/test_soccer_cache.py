from datetime import datetime, timezone

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
