from datetime import date

import pytest
from pydantic import ValidationError


def test_backtest_request_defaults_and_validation():
    from predictions.backtest import BacktestRequest

    # Valid minimum
    req = BacktestRequest(
        league="PL",
        date_from=date(2026, 3, 1),
        date_to=date(2026, 4, 1),
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
            league="SPL",  # ty: ignore[invalid-argument-type]
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
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
            date_from=date(2026, 5, 1),
            date_to=date(2026, 3, 1),
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
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=0,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=6,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=100,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=999,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.2,
        )


from datetime import datetime, timedelta, timezone


def _make_cached_match(
    *,
    match_id: str,
    kickoff: datetime,
    home: str,
    away: str,
    final_home: int,
    final_away: int,
    goals: list[tuple[int, int, str, int]],
):
    from predictions.soccer_cache import SessionLocal, SoccerGoal, SoccerMatch

    s = SessionLocal()
    s.add(
        SoccerMatch(
            id=match_id,
            competition="PL",
            kickoff_at=kickoff,
            home_team=home,
            away_team=away,
            home_score=final_home,
            away_score=final_away,
            status="FINISHED",
            fetched_at=datetime.now(timezone.utc),
        )
    )
    for i, (minute, stoppage, side, own) in enumerate(goals, start=1):
        s.add(
            SoccerGoal(
                match_id=match_id,
                sequence=i,
                minute=minute,
                stoppage=stoppage,
                side=side,
                is_own_goal=own,
            )
        )
    s.commit()
    s.close()


def _seed_opp(kickoff, fire_minute, home, away, leading, yes_ask):
    """Seed an Opportunity at the expected fire timestamp.

    NOTE the spec was updated in Task 7: the leading-team filter checks
    yes_sub_title (not title), so populate yes_sub_title with the leading
    team name and put the matchup label in title.
    """
    from predictions.db import Opportunity, get_session

    s = get_session()
    s.add(
        Opportunity(
            ticker="KXEPLGAME-1",
            series_ticker="KXEPLGAME",
            title=f"{home} vs {away}",
            yes_sub_title=leading,
            yes_ask=yes_ask,
            yes_bid=yes_ask - 2,
            spread=2,
            volume=100,
            found_at=kickoff + timedelta(minutes=fire_minute),
        )
    )
    s.commit()
    s.close()


async def _run(req_kwargs=None):
    from typing import Any
    from unittest.mock import patch

    from predictions.backtest import BacktestRequest, run_backtest
    from predictions.soccer_cache import EnsureResult, SessionLocal, SoccerMatch

    s = SessionLocal()
    cached = s.query(SoccerMatch).order_by(SoccerMatch.kickoff_at).all()
    for m in cached:
        s.expunge(m)
    s.close()

    result = EnsureResult(matches=cached, partial=False, missing_count=0)

    async def fake_ensure(*args, **kwargs):
        return result

    base: dict[str, Any] = dict(
        league="PL",
        date_from="2026-03-01",
        date_to="2026-04-20",
        min_minute=75,
        min_lead=2,
        min_yes_price=0,
        initial_balance_cents=100000,
        bet_percent=0.02,
    )
    base.update(req_kwargs or {})
    req = BacktestRequest(**base)

    with patch("predictions.backtest.ensure_matches_cached", fake_ensure):
        return await run_backtest(req)


async def test_run_backtest_win_path_with_price():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=1,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0), (85, 0, "away", 0)],
    )
    _seed_opp(
        kickoff, fire_minute=75, home="Arsenal", away="Chelsea", leading="Arsenal", yes_ask=94
    )

    resp = await _run()

    assert resp.summary.matches_scanned == 1
    assert resp.summary.matches_bet_on == 1
    assert resp.summary.matches_with_price_data == 1
    assert resp.summary.wins == 1
    assert resp.summary.losses == 0
    assert resp.trades[0].count == 21
    assert resp.trades[0].cost_cents == 1974
    assert resp.trades[0].pnl_cents == 126
    assert resp.summary.final_balance_cents == 100126


async def test_run_backtest_loss_path_with_price():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=3,
        goals=[
            (30, 0, "home", 0),
            (60, 0, "home", 0),
            (80, 0, "away", 0),
            (85, 0, "away", 0),
            (90, 0, "away", 0),
        ],
    )
    _seed_opp(kickoff, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=94)

    resp = await _run()
    assert resp.summary.wins == 0
    assert resp.summary.losses == 1
    assert resp.trades[0].pnl_cents == -1974
    assert resp.summary.final_balance_cents == 100000 - 1974


async def test_no_price_counts_in_winrate_but_not_in_pnl():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    # No Opportunity seeded.

    resp = await _run()
    assert resp.summary.matches_bet_on == 1
    assert resp.summary.matches_with_price_data == 0
    assert resp.summary.wins == 1
    assert resp.trades[0].observed_yes_ask_cents is None
    assert resp.trades[0].pnl_cents is None
    assert resp.trades[0].count is None
    assert resp.summary.final_balance_cents == 100000  # unchanged
    assert len(resp.bankroll_curve) == 1


async def test_min_yes_price_skips_when_observed_too_low():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _seed_opp(kickoff, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=80)

    resp = await _run({"min_yes_price": 90})
    assert resp.summary.matches_bet_on == 0
    assert resp.summary.wins == 0
    assert len(resp.trades) == 0


async def test_min_yes_price_ignored_when_no_observation():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    resp = await _run({"min_yes_price": 90})
    assert resp.summary.matches_bet_on == 1
    assert resp.summary.wins == 1


async def test_bankroll_compounds_chronologically():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff1 = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    kickoff2 = datetime(2026, 4, 2, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff1,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _make_cached_match(
        match_id="fd:2",
        kickoff=kickoff2,
        home="Liverpool",
        away="Tottenham Hotspur",
        final_home=2,
        final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _seed_opp(kickoff1, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=90)
    _seed_opp(kickoff2, 75, "Liverpool", "Tottenham Hotspur", "Liverpool", yes_ask=90)

    resp = await _run()
    assert resp.trades[0].bankroll_after_cents == 100220
    assert resp.trades[1].bankroll_after_cents == 100440
    assert resp.summary.final_balance_cents == 100440


async def test_bankroll_curve_starts_at_date_from_with_initial_balance():
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()
    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _make_cached_match(
        match_id="fd:1",
        kickoff=kickoff,
        home="Arsenal",
        away="Chelsea",
        final_home=2,
        final_away=0,
        goals=[(30, 0, "home", 0), (60, 0, "home", 0)],
    )
    _seed_opp(kickoff, 75, "Arsenal", "Chelsea", "Arsenal", yes_ask=90)

    resp = await _run()
    assert resp.bankroll_curve[0].balance_cents == 100000
    assert resp.bankroll_curve[0].t.isoformat().startswith("2026-03-01")
    assert len(resp.bankroll_curve) == 2
    assert resp.bankroll_curve[1].t == kickoff
