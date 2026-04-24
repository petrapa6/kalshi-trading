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
