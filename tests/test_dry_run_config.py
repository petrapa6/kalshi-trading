"""Runtime dry-run mode: DB config seam (issue #12).

Dry-run is a runtime DB config value (`dry_run`), read per scan tick.
Absence or any value other than the literal "false" means dry-run ON.
Only "false" starts real-money placement. No DRY_RUN env anywhere.
"""

from datetime import datetime, timedelta, timezone
from typing import cast

import pytest
from fastapi.testclient import TestClient

import predictions.db as db_module
from predictions.db import Trade, dry_run_enabled, set_config
from predictions.espn import GameState
from predictions.kalshi_client import KalshiClient
from predictions.scanner import scan_kalshi_with_espn, settle_trade


# --- dry_run_enabled() semantics ---


def test_missing_config_is_dry_run_on():
    assert dry_run_enabled() is True


def test_literal_false_is_live():
    set_config("dry_run", "false")
    assert dry_run_enabled() is False


def test_true_is_dry_run_on():
    set_config("dry_run", "true")
    assert dry_run_enabled() is True


# --- scan-tick seam: config drives placement, no restart ---


def _nba_events():
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    return [
        {
            "event_ticker": "KXNBAGAME-26JUL07LALSEA",
            "title": "Los Angeles at Seattle",
            "markets": [
                {
                    "ticker": "KXNBAGAME-26JUL07LALSEA-SEA",
                    "status": "active",
                    "volume": 500,
                    "yes_bid": 93,
                    "yes_ask": 94,
                    "yes_sub_title": "Seattle wins",
                    "close_time": exp,
                    "expected_expiration_time": exp,
                }
            ],
        }
    ]


def _nba_game():
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


class FakeKalshiClient:
    def __init__(self, events: list[dict]):
        self._events = events
        self.orders_placed: list[dict] = []

    async def get_events(self, **kwargs) -> dict:
        return {"events": self._events, "cursor": ""}

    async def create_order(self, **kwargs) -> dict:
        self.orders_placed.append(kwargs)
        return {"order": {"order_id": "ord-1", "fee": 3}}


async def _run_scan(client):
    set_config("lead:basketball/nba", "12")
    await scan_kalshi_with_espn(
        client=cast(KalshiClient, client),
        espn_final={"KXNBAGAME": [_nba_game()]},
        min_yes_price=91,
        max_bet_cents=1000,
    )


async def test_dry_run_mode_places_no_order():
    set_config("dry_run", "true")
    client = FakeKalshiClient(_nba_events())

    await _run_scan(client)

    assert client.orders_placed == []
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is True
    assert trades[0].status == "dry_run"


async def test_missing_config_defaults_to_dry_run():
    client = FakeKalshiClient(_nba_events())

    await _run_scan(client)

    assert client.orders_placed == []
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is True


async def test_live_mode_places_order():
    set_config("dry_run", "false")
    client = FakeKalshiClient(_nba_events())

    await _run_scan(client)

    assert len(client.orders_placed) == 1
    assert client.orders_placed[0]["ticker"] == "KXNBAGAME-26JUL07LALSEA-SEA"
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    assert trades[0].dry_run is False
    assert trades[0].status == "placed"
    assert trades[0].order_id == "ord-1"


# --- previous-mode positions keep their placement-time tag ---


async def test_open_dry_run_position_settles_with_original_tag():
    """A dry-run trade placed under the old mode keeps dry_run=True through
    settlement even after the runtime mode flips to live."""
    set_config("dry_run", "true")
    client = FakeKalshiClient(_nba_events())
    await _run_scan(client)

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
