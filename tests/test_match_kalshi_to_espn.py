"""Direct table-driven tests for match_kalshi_to_espn (issue #5, phase 1).

Characterization tests for the live matching path — the function that
decides which game a market's money rides on. Team fields on GameState
are ESPN abbreviations (espn.py builds them from team.abbreviation).
"""

import pytest

from predictions.espn import GameState, match_kalshi_to_espn
from predictions.teams import ESPN_TO_KALSHI_ABBR


def make_game(home: str, away: str, sport_path: str = "basketball/nba") -> GameState:
    return GameState(
        espn_id="401234567",
        home_team=home,
        away_team=away,
        home_score=100,
        away_score=90,
        period=4,
        display_clock="2:00",
        clock_seconds=120.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path=sport_path,
    )


# --- Exact abbreviation matching ---


def test_matches_when_both_teams_in_ticker():
    game = make_game("LAC", "NYK")
    assert match_kalshi_to_espn("KXNBAGAME-26MAR07NYKLAC-LAC", "Clippers", [game]) is game


def test_matches_when_both_teams_in_title():
    game = make_game("LAC", "NYK")
    assert match_kalshi_to_espn("KXNBAGAME-OPAQUE", "NYK at LAC winner?", [game]) is game


def test_matches_one_team_from_ticker_other_from_title():
    game = make_game("LAC", "NYK")
    assert match_kalshi_to_espn("KXNBAGAME-26MAR07LAC", "NYK to win", [game]) is game


def test_single_team_match_returns_none():
    """Tomorrow's-game guard: one matching team is not enough — MIL in the
    ticker must not match today's MIL game against a different opponent."""
    game = make_game("MIL", "CHI")
    assert match_kalshi_to_espn("KXNBAGAME-26MAR08MILBOS-MIL", "Bucks", [game]) is None


def test_empty_games_returns_none():
    assert match_kalshi_to_espn("KXNBAGAME-26MAR07NYKLAC-LAC", "t", []) is None


def test_no_match_returns_none():
    game = make_game("DEN", "OKC")
    assert match_kalshi_to_espn("KXNBAGAME-26MAR07NYKLAC-LAC", "Clippers", [game]) is None


def test_picks_the_game_matching_both_teams_among_many():
    games = [make_game("MIL", "CHI"), make_game("LAC", "NYK"), make_game("BOS", "DET")]
    assert match_kalshi_to_espn("KXNBAGAME-26MAR07NYKLAC-LAC", "Clippers", games) is games[1]


def test_lowercase_inputs_match():
    game = make_game("LAC", "NYK")
    assert match_kalshi_to_espn("kxnbagame-26mar07nyklac-lac", "clippers nyk", [game]) is game


# --- ESPN -> Kalshi abbreviation aliases ---

ALIAS_CASES = [
    (espn_abbr, kalshi_code)
    for espn_abbr, codes in ESPN_TO_KALSHI_ABBR.items()
    for kalshi_code in codes
]


@pytest.mark.parametrize(("espn_abbr", "kalshi_code"), ALIAS_CASES)
def test_alias_matches_home_position(espn_abbr: str, kalshi_code: str):
    game = make_game(espn_abbr, "ZZZ")
    ticker = f"KXNBAGAME-26MAR07{kalshi_code}ZZZ-ZZZ"
    assert match_kalshi_to_espn(ticker, "title", [game]) is game


@pytest.mark.parametrize(("espn_abbr", "kalshi_code"), ALIAS_CASES)
def test_alias_matches_away_position(espn_abbr: str, kalshi_code: str):
    game = make_game("ZZZ", espn_abbr)
    ticker = f"KXNBAGAME-26MAR07ZZZ{kalshi_code}-ZZZ"
    assert match_kalshi_to_espn(ticker, "title", [game]) is game


@pytest.mark.parametrize("espn_abbr", sorted(ESPN_TO_KALSHI_ABBR))
def test_espn_abbreviation_itself_also_matches(espn_abbr: str):
    """The ESPN code is always included alongside its Kalshi aliases."""
    game = make_game(espn_abbr, "ZZZ")
    ticker = f"KXNBAGAME-26MAR07{espn_abbr}ZZZ-ZZZ"
    assert match_kalshi_to_espn(ticker, "title", [game]) is game


# --- Soccer ---


def test_soccer_exact_abbreviations_match():
    game = make_game("BET", "GET", sport_path="soccer/esp.1")
    assert match_kalshi_to_espn("KXLALIGAGAME-26MAR08BETGET-GET", "Betis vs Getafe", [game]) is game


def test_soccer_unknown_abbreviations_return_none():
    """Neither the exact loop nor the fuzzy fallback invents a match when
    the ESPN abbreviations appear nowhere in ticker or title."""
    game = make_game("RMA", "BAR", sport_path="soccer/esp.1")
    assert (
        match_kalshi_to_espn(
            "KXLALIGAGAME-26MAR08REALBARCA-BARCA", "Real Madrid vs Barcelona", [game]
        )
        is None
    )


def test_soccer_title_with_full_names_matches_via_abbreviation_substring():
    """Kalshi soccer titles carry full team names; the abbreviation must
    appear as a substring of ticker or title for a match (BET in 'BETIS')."""
    game = make_game("BET", "GET", sport_path="soccer/esp.1")
    assert match_kalshi_to_espn("KXLALIGAGAME-OPAQUE", "BETIS VS GETAFE", [game]) is game
