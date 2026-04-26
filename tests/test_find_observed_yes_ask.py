def test_normalize_team_name_casefold_and_whitespace():
    from predictions.backtest import _normalize_team

    assert _normalize_team("Manchester United FC") == "manchester united"
    assert _normalize_team("  Arsenal  ") == "arsenal"
    assert _normalize_team("FC Bayern München") == "bayern munchen"


def test_team_aliases_resolve_common_variants():
    from predictions.backtest import _canonical_team

    assert _canonical_team("Man Utd") == _canonical_team("Manchester United")
    assert _canonical_team("Spurs") == _canonical_team("Tottenham Hotspur")
    assert _canonical_team("Bayern") == _canonical_team("Bayern Munich")
    assert _canonical_team("Atleti") == _canonical_team("Atletico Madrid")


def test_market_title_contains_both_teams_matches():
    from predictions.backtest import _market_mentions_both_teams

    assert _market_mentions_both_teams(
        "Arsenal vs Chelsea — will Arsenal win?", "Arsenal", "Chelsea"
    )
    assert _market_mentions_both_teams("Chelsea at Arsenal", "Arsenal", "Chelsea")
    assert not _market_mentions_both_teams("Arsenal vs Liverpool", "Arsenal", "Chelsea")


def test_market_title_via_alias():
    from predictions.backtest import _market_mentions_both_teams

    assert _market_mentions_both_teams(
        "Man Utd vs Tottenham", "Manchester United", "Tottenham Hotspur"
    )


def test_shared_prefix_teams_do_not_collide():
    """Regression: "real" alias for Real Madrid must NOT absorb the "real" in
    "real sociedad". Tokenizer-based canonicalization prevents the false
    negative on shared-prefix La Liga fixtures."""
    from predictions.backtest import _market_mentions_both_teams

    assert _market_mentions_both_teams(
        "Real Madrid vs Real Sociedad", "Real Madrid", "Real Sociedad"
    )


def test_bundesliga_dotted_prefix_strips_correctly():
    """Regression: "1. FC Köln" must strip the "1. " prefix even though the
    literal dot is later removed by alphanumeric filtering."""
    from predictions.backtest import _normalize_team

    assert _normalize_team("1. FC Köln") == "koln"


from datetime import datetime, timedelta, timezone


def _seed_opportunity(**kwargs):
    from predictions.db import Opportunity, get_session

    session = get_session()
    session.add(Opportunity(**kwargs))
    session.commit()
    session.close()


def _fake_match(kickoff: datetime, home: str, away: str):
    from types import SimpleNamespace

    return SimpleNamespace(
        id="fd:x",
        kickoff_at=kickoff,
        home_team=home,
        away_team=away,
        home_score=0,
        away_score=0,
        goals=[],
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
    _seed_opportunity(
        ticker="KXEPLGAME-001",
        series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea",
        yes_sub_title="Arsenal",
        yes_ask=85,
        yes_bid=80,
        spread=5,
        volume=100,
        found_at=target - timedelta(minutes=20),
    )
    _seed_opportunity(
        ticker="KXEPLGAME-001",
        series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea",
        yes_sub_title="Arsenal",
        yes_ask=94,
        yes_bid=90,
        spread=4,
        volume=100,
        found_at=target - timedelta(minutes=5),
    )
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    price = find_observed_yes_ask(m, fire_minute=80, leading_side="home")
    assert price == 94


def test_ignores_rows_outside_window():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _seed_opportunity(
        ticker="KXEPLGAME-001",
        series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea",
        yes_sub_title="Arsenal",
        yes_ask=94,
        yes_bid=90,
        spread=4,
        volume=100,
        found_at=kickoff - timedelta(minutes=40),
    )
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    assert find_observed_yes_ask(m, fire_minute=80, leading_side="home") is None


def test_alias_match_resolves_manchester_united():
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    _seed_opportunity(
        ticker="KXEPLGAME-001",
        series_ticker="KXEPLGAME",
        title="Man Utd vs Chelsea",
        yes_sub_title="Man Utd",
        yes_ask=92,
        yes_bid=88,
        spread=4,
        volume=100,
        found_at=kickoff + timedelta(minutes=75),
    )
    m = _fake_match(kickoff, "Manchester United", "Chelsea")
    assert find_observed_yes_ask(m, fire_minute=75, leading_side="home") == 92


def test_requires_leading_team_in_yes_sub_title():
    """When two markets exist on the same matchup (one for each team's YES),
    only the one whose yes_sub_title matches the leading side is picked.
    On real Kalshi data, `title` is the matchup label ('Arsenal vs Chelsea')
    and `yes_sub_title` carries the team-specific YES outcome ('Arsenal' or
    'Chelsea')."""
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    # Wrong-side market for Chelsea-to-win — must be ignored when leading=home (Arsenal).
    _seed_opportunity(
        ticker="KXEPLGAME-002",
        series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea",
        yes_sub_title="Chelsea",
        yes_ask=20,
        yes_bid=18,
        spread=2,
        volume=100,
        found_at=kickoff + timedelta(minutes=75),
    )
    # Right-side market for Arsenal-to-win — must be picked.
    _seed_opportunity(
        ticker="KXEPLGAME-001",
        series_ticker="KXEPLGAME",
        title="Arsenal vs Chelsea",
        yes_sub_title="Arsenal",
        yes_ask=88,
        yes_bid=85,
        spread=3,
        volume=100,
        found_at=kickoff + timedelta(minutes=75),
    )
    m = _fake_match(kickoff, "Arsenal", "Chelsea")
    assert find_observed_yes_ask(m, fire_minute=75, leading_side="home") == 88


def test_shared_prefix_yes_sub_title_does_not_collide():
    """Regression: 'Real' alone in yes_sub_title must not match when leading is
    Real Sociedad (or Real Madrid). Token-membership prevents the substring
    collision."""
    from predictions.backtest import find_observed_yes_ask

    kickoff = datetime(2026, 4, 1, 14, 0, tzinfo=timezone.utc)
    # yes_sub_title="Real Sociedad" with leading=home=Real Madrid → must NOT match.
    _seed_opportunity(
        ticker="KXLALIGAGAME-001",
        series_ticker="KXLALIGAGAME",
        title="Real Madrid vs Real Sociedad",
        yes_sub_title="Real Sociedad",
        yes_ask=30,
        yes_bid=28,
        spread=2,
        volume=100,
        found_at=kickoff + timedelta(minutes=75),
    )
    m = _fake_match(kickoff, "Real Madrid", "Real Sociedad")
    assert find_observed_yes_ask(m, fire_minute=75, leading_side="home") is None
