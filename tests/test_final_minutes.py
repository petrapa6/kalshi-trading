"""Tests for the pure final-minutes check (issue #6).

Thresholds are passed in by the caller; no DB involved.
"""

from predictions.db import get_final_seconds_thresholds, set_config
from predictions.espn import GameState, is_in_final_minutes


def make_game(
    sport_path: str, *, period: int, clock_seconds: float, state: str = "in"
) -> GameState:
    return GameState(
        espn_id="401",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=period,
        display_clock="0:00",
        clock_seconds=clock_seconds,
        state=state,
        status_name="STATUS_IN_PROGRESS",
        sport_path=sport_path,
    )


def test_down_clock_inside_threshold():
    game = make_game("basketball/nba", period=4, clock_seconds=170)
    assert is_in_final_minutes(game, {"basketball/nba": 180}) is True


def test_down_clock_outside_threshold():
    game = make_game("basketball/nba", period=4, clock_seconds=200)
    assert is_in_final_minutes(game, {"basketball/nba": 180}) is False


def test_up_clock_past_threshold():
    game = make_game("soccer/eng.1", period=2, clock_seconds=4600)
    assert is_in_final_minutes(game, {"soccer/eng.1": 4500}) is True


def test_up_clock_before_threshold():
    game = make_game("soccer/eng.1", period=2, clock_seconds=4400)
    assert is_in_final_minutes(game, {"soccer/eng.1": 4500}) is False


def test_clockless_final_period_needs_no_threshold():
    game = make_game("baseball/mlb", period=9, clock_seconds=0)
    assert is_in_final_minutes(game, {}) is True


def test_not_live_game_is_never_in_final_minutes():
    game = make_game("baseball/mlb", period=9, clock_seconds=0, state="post")
    assert is_in_final_minutes(game, {}) is False


def test_earlier_period_is_not_final_minutes():
    game = make_game("basketball/nba", period=3, clock_seconds=170)
    assert is_in_final_minutes(game, {"basketball/nba": 180}) is False


def test_thresholds_default_to_registry_and_skip_clockless():
    thresholds = get_final_seconds_thresholds()
    assert thresholds["basketball/nba"] == 180
    assert thresholds["soccer/eng.1"] == 4500
    assert "baseball/mlb" not in thresholds


def test_thresholds_db_override_wins():
    set_config("final_seconds:basketball/nba", "120")
    assert get_final_seconds_thresholds()["basketball/nba"] == 120


def test_thresholds_zero_override_falls_back_to_default():
    set_config("final_seconds:basketball/nba", "0")
    assert get_final_seconds_thresholds()["basketball/nba"] == 180
