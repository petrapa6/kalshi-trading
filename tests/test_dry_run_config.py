"""Runtime dry-run mode + the unified placement gate (issues #12, #14).

Dry-run is a runtime DB config value (`dry_run`), read per scan tick.
Absence or any value other than the literal "false" means dry-run ON.
Only "false" starts real-money placement. No DRY_RUN env anywhere.

Placement is the single responsibility of evaluate_strategies (ADR-0002):
a real order iff the strategy is live-enabled AND dry-run mode is off AND
the kill switch is inactive; otherwise a dry-run trade row.
"""

from typing import cast

import pytest
from fastapi.testclient import TestClient

import predictions.db as db_module
import predictions.scanner as scanner_module
from predictions.db import Trade, dry_run_enabled, set_config
from predictions.espn import GameState
from predictions.kalshi_client import KalshiClient
from predictions.scanner import evaluate_strategies, settle_trade

# --- dry_run_enabled() semantics ---


def test_missing_config_is_dry_run_on():
    assert dry_run_enabled() is True


def test_literal_false_is_live():
    set_config("dry_run", "false")
    assert dry_run_enabled() is False


def test_true_is_dry_run_on():
    set_config("dry_run", "true")
    assert dry_run_enabled() is True


# --- placement truth table at the scan-tick seam (evaluate_strategies) ---

_TICKER = "KXNBAGAME-26JUL07LALSEA-SEA"
_EVENT = "KXNBAGAME-26JUL07LALSEA"


class FakeKalshiClient:
    def __init__(self):
        self.orders_placed: list[dict] = []

    async def create_order(self, **kwargs) -> dict:
        self.orders_placed.append(kwargs)
        return {"order": {"order_id": "ord-1", "fee": 3}}


def _nba_game() -> GameState:
    return GameState(
        espn_id="401234",
        home_team="SEA",
        away_team="LAL",
        home_score=110,
        away_score=98,
        period=4,
        display_clock="0:47",
        clock_seconds=47.0,
        state="in",
        status_name="STATUS_IN_PROGRESS",
        sport_path="basketball/nba",
    )


def _write_strategy(tmp_path, monkeypatch, *, live: bool) -> None:
    live_line = "    live: true\n" if live else ""
    (tmp_path / "s.yaml").write_text(
        "strategies:\n"
        "  main:\n" + live_line + "    triggers:\n"
        "      - sport_path: basketball/nba\n"
        "        min_yes_price: 92\n"
        "        max_yes_price: 99\n"
        "        final_minutes: true\n"
        "        min_volume: 50\n"
        "        min_lead: 12\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(tmp_path / "s.yaml"))


def _seed_prices(monkeypatch) -> None:
    monkeypatch.setattr(
        scanner_module,
        "market_prices",
        {
            _TICKER: {
                "yes_ask": 94,
                "yes_bid": 92,
                "volume": 500,
                "title": "Los Angeles at Seattle",
                "event_ticker": _EVENT,
            }
        },
    )


async def _run(client) -> None:
    session = db_module.get_session()
    await evaluate_strategies(
        session, {"KXNBAGAME": [_nba_game()]}, max_bet_cents=1000, client=cast(KalshiClient, client)
    )
    session.close()


async def test_live_enabled_mode_off_unpaused_places_one_real_order(tmp_path, monkeypatch):
    _write_strategy(tmp_path, monkeypatch, live=True)
    _seed_prices(monkeypatch)
    set_config("dry_run", "false")
    client = FakeKalshiClient()

    await _run(client)

    assert len(client.orders_placed) == 1
    assert client.orders_placed[0]["ticker"] == _TICKER
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is False
    assert trades[0].status == "placed"
    assert trades[0].order_id == "ord-1"
    assert trades[0].strategy_name == "main"


async def test_live_enabled_but_dry_run_mode_on_records_dry_run(tmp_path, monkeypatch):
    _write_strategy(tmp_path, monkeypatch, live=True)
    _seed_prices(monkeypatch)
    set_config("dry_run", "true")
    client = FakeKalshiClient()

    await _run(client)

    assert client.orders_placed == []
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is True
    assert trades[0].status == "dry_run"
    assert trades[0].strategy_name == "main"


async def test_mode_off_but_strategy_not_live_records_dry_run(tmp_path, monkeypatch):
    _write_strategy(tmp_path, monkeypatch, live=False)
    _seed_prices(monkeypatch)
    set_config("dry_run", "false")
    client = FakeKalshiClient()

    await _run(client)

    assert client.orders_placed == []
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is True
    assert trades[0].strategy_name == "main"


async def test_missing_config_defaults_to_dry_run(tmp_path, monkeypatch):
    _write_strategy(tmp_path, monkeypatch, live=True)
    _seed_prices(monkeypatch)
    client = FakeKalshiClient()

    await _run(client)

    assert client.orders_placed == []
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is True


async def test_kill_switch_blocks_fires_entirely(tmp_path, monkeypatch):
    """trading_paused blocks all placement — no orders, no dry-run rows."""
    _write_strategy(tmp_path, monkeypatch, live=True)
    _seed_prices(monkeypatch)
    set_config("dry_run", "false")
    set_config("trading_paused", "true")
    client = FakeKalshiClient()

    await _run(client)

    assert client.orders_placed == []
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert trades == []


# --- previous-mode positions keep their placement-time tag ---


async def test_open_dry_run_position_settles_with_original_tag(tmp_path, monkeypatch):
    """A dry-run trade placed under the old mode keeps dry_run=True through
    settlement even after the runtime mode flips to live."""
    _write_strategy(tmp_path, monkeypatch, live=True)
    _seed_prices(monkeypatch)
    set_config("dry_run", "true")
    await _run(FakeKalshiClient())

    set_config("dry_run", "false")

    session = db_module.get_session()
    trade = session.query(Trade).one()
    settle_trade(trade, "yes")
    session.commit()
    session.close()

    session = db_module.get_session()
    settled = session.query(Trade).one()
    session.close()
    assert settled.dry_run is True
    assert settled.status == "settled_win"


# --- GET /api/config reflects the DB value ---


@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


def _get_config(api_client):
    return api_client.get("/api/config", headers={"Authorization": "Bearer test-token"}).json()


def test_api_config_defaults_to_dry_run(api_client):
    assert _get_config(api_client)["trading"]["dry_run"] is True


def test_api_config_reflects_live_db_value(api_client):
    set_config("dry_run", "false")
    assert _get_config(api_client)["trading"]["dry_run"] is False


def test_api_config_omits_retired_knobs(api_client):
    """min_yes_price / min_volume trading knobs and per-sport lead sliders
    are retired (issue #14) — absent from GET /api/config."""
    cfg = _get_config(api_client)
    assert "min_yes_price" not in cfg["trading"]
    assert "min_volume" not in cfg["trading"]
    for sport in cfg["sports"]:
        assert "min_score_lead" not in sport
        assert "stretch_score_lead" not in sport
