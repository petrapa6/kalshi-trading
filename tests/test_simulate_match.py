from datetime import date, datetime, timezone


def _match(goals):
    """Build a stand-in for SoccerMatch with a goals attribute.

    `goals` is a list of (minute, stoppage, side, is_own_goal, sequence?) tuples.
    """
    from types import SimpleNamespace

    goal_objs = []
    for i, g in enumerate(goals, start=1):
        minute, stoppage, side, is_own = g
        goal_objs.append(
            SimpleNamespace(
                sequence=i,
                minute=minute,
                stoppage=stoppage,
                side=side,
                is_own_goal=is_own,
            )
        )
    return SimpleNamespace(
        id="fd:x",
        home_team="H",
        away_team="A",
        kickoff_at=datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc),
        home_score=sum(1 for (_, _, s, _) in goals if s == "home"),
        away_score=sum(1 for (_, _, s, _) in goals if s == "away"),
        goals=goal_objs,
    )


def _req(min_minute=75, min_lead=2):
    from predictions.backtest import BacktestRequest

    return BacktestRequest(
        league="PL",
        date_from=date(2026, 3, 1),
        date_to=date(2026, 4, 20),
        min_minute=min_minute,
        min_lead=min_lead,
        min_yes_price=0,
        initial_balance_cents=100000,
        bet_percent=0.02,
    )


def test_fires_when_lead_established_before_min_minute():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (40, 0, "home", 0)])
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

    m = _match([(20, 0, "home", 0), (60, 0, "away", 0)])
    assert simulate_match(m, _req(min_minute=75, min_lead=2)) is None


def test_does_not_fire_when_lead_only_held_before_min_minute():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (40, 0, "home", 0), (70, 0, "away", 0), (72, 0, "away", 0)])
    assert simulate_match(m, _req(min_minute=75, min_lead=2)) is None


def test_fire_once_ignores_later_goals():
    from predictions.backtest import simulate_match

    m = _match([(20, 0, "home", 0), (40, 0, "home", 0), (80, 0, "home", 0)])
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    assert trig is not None
    assert trig.fired_at_minute == 75
    assert trig.score_at_fire_home == 2


def test_stoppage_time_goal_at_90_plus_triggers_at_minute_90():
    from predictions.backtest import simulate_match

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

    m = _match([(20, 0, "home", 0), (60, 0, "home", 1), (70, 0, "home", 0)])
    trig = simulate_match(m, _req(min_minute=75, min_lead=2))
    assert trig is not None
    assert trig.score_at_fire_home == 3
    assert trig.score_at_fire_away == 0
    assert trig.leading_side == "home"


def test_goals_at_same_minute_applied_before_trigger_check():
    from predictions.backtest import simulate_match

    m = _match([(75, 0, "home", 0), (75, 0, "away", 0)])
    assert simulate_match(m, _req(min_minute=75, min_lead=1)) is None
