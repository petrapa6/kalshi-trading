"""Strategy evaluation tests for Phase 3 (D-04..D-15, D-23).

Wave 0 stubs — turn green when Plan 03-03 ships scanner.py changes.
"""

import pytest

import predictions.db as db_module
from predictions.db import Trade


async def test_evaluate_strategies_fires_dry_run_trade(isolated_db, monkeypatch, tmp_path):
    """DRY-01: evaluate_strategies writes a dry_run Trade row when a trigger fires."""
    import predictions.scanner as scanner_module
    from predictions.espn import GameState
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n  s1:\n    triggers:\n      - sport: basketball\n        min_yes_price: 90\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            "KXNBAGAME-20260101-SEALAL": {
                "yes_ask": 95,
                "volume": 100,
                "title": "T",
                "event_ticker": "KXNBAGAME-20260101",
                "ticker": "KXNBAGAME-20260101-SEALAL",
                "series_ticker": "KXNBAGAME",
            }
        },
    )
    game = GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="1:00",
        clock_seconds=60.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )
    espn_final_period = {"KXNBAGAME": [game]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert len(trades) == 1
    t = trades[0]
    assert t.dry_run is True
    assert t.status == "dry_run"
    assert t.strategy_name == "s1"
    assert t.yes_price == 95
    assert t.count == 5  # 500 // 95 == 5


async def test_strategy_fire_independent_of_live_mode(isolated_db, monkeypatch, tmp_path):
    """D-13: strategy dry_run is hardcoded True, not driven by the runtime
    dry-run mode — a strategy fires as a dry-run even when live mode is on."""
    import predictions.scanner as scanner_module
    from predictions.espn import GameState
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n  s1:\n    triggers:\n      - sport: basketball\n        min_yes_price: 90\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    db_module.set_config("dry_run", "false")
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            "KXNBAGAME-20260101-SEALAL": {
                "yes_ask": 95,
                "volume": 100,
                "title": "T",
                "event_ticker": "KXNBAGAME-20260101",
                "ticker": "KXNBAGAME-20260101-SEALAL",
                "series_ticker": "KXNBAGAME",
            }
        },
    )
    game = GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="1:00",
        clock_seconds=60.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )
    espn_final_period = {"KXNBAGAME": [game]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is True


async def test_first_trigger_wins(isolated_db, monkeypatch, tmp_path):
    """D-12: first matching trigger fires, not all matching triggers."""
    import predictions.scanner as scanner_module
    from predictions.espn import GameState
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n"
        "  s1:\n"
        "    triggers:\n"
        "      - sport: basketball\n"
        "        min_yes_price: 90\n"
        "      - sport: basketball\n"
        "        min_yes_price: 85\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            "KXNBAGAME-20260101-SEALAL": {
                "yes_ask": 95,
                "volume": 100,
                "title": "T",
                "event_ticker": "KXNBAGAME-20260101",
                "ticker": "KXNBAGAME-20260101-SEALAL",
                "series_ticker": "KXNBAGAME",
            }
        },
    )
    game = GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="1:00",
        clock_seconds=60.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )
    espn_final_period = {"KXNBAGAME": [game]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert len(trades) == 1


async def test_per_strategy_dedupe(isolated_db, monkeypatch, tmp_path):
    """D-10: strategy fires at most once per (strategy_name, ticker)."""
    import predictions.scanner as scanner_module
    from predictions.espn import GameState
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n  s1:\n    triggers:\n      - sport: basketball\n        min_yes_price: 90\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            "KXNBAGAME-20260101-SEALAL": {
                "yes_ask": 95,
                "volume": 100,
                "title": "T",
                "event_ticker": "KXNBAGAME-20260101",
                "ticker": "KXNBAGAME-20260101-SEALAL",
                "series_ticker": "KXNBAGAME",
            }
        },
    )
    game = GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="1:00",
        clock_seconds=60.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )
    espn_final_period = {"KXNBAGAME": [game]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert len(trades) == 1


async def test_multi_strategy_fire_same_ticker(isolated_db, monkeypatch, tmp_path):
    """D-11: multiple strategies can fire on the same ticker, one Trade row each."""
    import predictions.scanner as scanner_module
    from predictions.espn import GameState
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n"
        "  s1:\n"
        "    triggers:\n"
        "      - sport: basketball\n"
        "        min_yes_price: 90\n"
        "  s2:\n"
        "    triggers:\n"
        "      - sport: basketball\n"
        "        min_yes_price: 85\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            "KXNBAGAME-20260101-SEALAL": {
                "yes_ask": 95,
                "volume": 100,
                "title": "T",
                "event_ticker": "KXNBAGAME-20260101",
                "ticker": "KXNBAGAME-20260101-SEALAL",
                "series_ticker": "KXNBAGAME",
            }
        },
    )
    game = GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="1:00",
        clock_seconds=60.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )
    espn_final_period = {"KXNBAGAME": [game]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name.in_(["s1", "s2"])).all()
    session.close()
    assert len(trades) == 2
    strategy_names = {t.strategy_name for t in trades}
    assert strategy_names == {"s1", "s2"}


async def test_trading_paused_blocks_strategy_fire(isolated_db, monkeypatch, tmp_path):
    """D-23: trading_paused kills evaluate_strategies at the loop level."""
    import predictions.scanner as scanner_module
    from predictions.espn import GameState
    from predictions.scanner import evaluate_strategies

    db_module.set_config("trading_paused", "true")

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n  s1:\n    triggers:\n      - sport: basketball\n        min_yes_price: 90\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            "KXNBAGAME-20260101-SEALAL": {
                "yes_ask": 95,
                "volume": 100,
                "title": "T",
                "event_ticker": "KXNBAGAME-20260101",
                "ticker": "KXNBAGAME-20260101-SEALAL",
                "series_ticker": "KXNBAGAME",
            }
        },
    )
    game = GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="1:00",
        clock_seconds=60.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )
    espn_final_period = {"KXNBAGAME": [game]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert len(trades) == 0


def _nba_market_prices(volume: int) -> dict:
    return {
        "KXNBAGAME-20260101-SEALAL": {
            "yes_ask": 95,
            "volume": volume,
            "title": "T",
            "event_ticker": "KXNBAGAME-20260101",
            "ticker": "KXNBAGAME-20260101-SEALAL",
            "series_ticker": "KXNBAGAME",
        }
    }


def _nba_game(clock_seconds: float):
    from predictions.espn import GameState

    return GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="0:00",
        clock_seconds=clock_seconds,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )


async def test_new_fields_fire_when_conditions_hold(isolated_db, monkeypatch, tmp_path):
    """Issue #13: a strategy gated on sport_path + final_minutes + min_volume
    fires when the game is inside the final-minutes window and volume clears."""
    import predictions.scanner as scanner_module
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n"
        "  s1:\n"
        "    triggers:\n"
        "      - sport_path: basketball/nba\n"
        "        final_minutes: true\n"
        "        min_volume: 300\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(scanner_module, "market_prices", _nba_market_prices(volume=500))
    # NBA final-seconds threshold is 180; 60s left in P4 is inside the window.
    espn_final_period = {"KXNBAGAME": [_nba_game(clock_seconds=60.0)]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert len(trades) == 1


async def test_final_minutes_skips_outside_window(isolated_db, monkeypatch, tmp_path):
    """Issue #13: same strategy does NOT fire before the clock threshold."""
    import predictions.scanner as scanner_module
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n"
        "  s1:\n"
        "    triggers:\n"
        "      - sport_path: basketball/nba\n"
        "        final_minutes: true\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    monkeypatch.setattr(scanner_module, "market_prices", _nba_market_prices(volume=500))
    # 300s left in P4 is still outside the 180s NBA final-minutes threshold.
    espn_final_period = {"KXNBAGAME": [_nba_game(clock_seconds=300.0)]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert trades == []


async def test_min_volume_skips_thin_market(isolated_db, monkeypatch, tmp_path):
    """Issue #13: a per-strategy min_volume above market volume blocks the fire."""
    import predictions.scanner as scanner_module
    from predictions.scanner import evaluate_strategies

    f = tmp_path / "strats.yaml"
    f.write_text(
        "strategies:\n  s1:\n    triggers:\n      - sport: basketball\n        min_volume: 1000\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    # 500 clears the global MIN_VOLUME gate but not the strategy's min_volume=1000.
    monkeypatch.setattr(scanner_module, "market_prices", _nba_market_prices(volume=500))
    espn_final_period = {"KXNBAGAME": [_nba_game(clock_seconds=60.0)]}

    session = db_module.get_session()
    await evaluate_strategies(session, espn_final_period, max_bet_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).filter(Trade.strategy_name == "s1").all()
    session.close()
    assert trades == []


def test_elapsed_minutes_per_sport():
    """D-09: elapsed_minutes returns game-clock minutes elapsed since start."""
    from predictions.scanner import elapsed_minutes

    # Soccer (count-up): 2700s at start of 2nd half = 45 min elapsed
    assert elapsed_minutes("soccer/eng.1", 2700, 1) == 45

    # Basketball NBA (count-down): P4, 60s on clock → 3*12 + (12 - 1) = 47 min elapsed
    assert elapsed_minutes("basketball/nba", 60, 4) == 47

    # Baseball (clockless): not supported, returns None
    assert elapsed_minutes("baseball/mlb", 0, 9) is None

    # Unknown sport: returns None
    assert elapsed_minutes("unknown/sport", 0, 1) is None


def test_sport_path_to_family():
    """D-08: SPORT_PATH_TO_FAMILY maps ESPN sport paths to family literals."""
    from predictions.scanner import SPORT_PATH_TO_FAMILY

    assert SPORT_PATH_TO_FAMILY["soccer/eng.1"] == "football"
    assert SPORT_PATH_TO_FAMILY["basketball/nba"] == "basketball"
    assert SPORT_PATH_TO_FAMILY["football/nfl"] == "american_football"
    assert SPORT_PATH_TO_FAMILY["baseball/mlb"] == "baseball"


def test_what_if_strategies_removed():
    """D-20: WHAT_IF_STRATEGIES is deleted from scanner.py."""
    with pytest.raises(ImportError):
        exec("from predictions.scanner import WHAT_IF_STRATEGIES")
