"""Happy-path integration test for scan_kalshi_with_espn (#8).

Fake Kalshi client + one matching ESPN game → asserts the same
opportunity is recorded and the same dry-run bet placed. Pins wiring
behavior across the decision-stage extraction.
"""

from datetime import datetime, timedelta, timezone
from typing import cast

import predictions.db as db_module
from predictions.db import Opportunity, Scan, Trade
from predictions.espn import GameState
from predictions.kalshi_client import KalshiClient
from predictions.scanner import scan_kalshi_with_espn


class FakeKalshiClient:
    def __init__(self, events: list[dict]):
        self._events = events

    async def get_events(self, **kwargs) -> dict:
        return {"events": self._events, "cursor": ""}


async def test_scan_records_opportunity_and_places_dry_run_bet():
    exp = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    events = [
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
    game = GameState(
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
    db_module.set_config("lead:basketball/nba", "12")

    await scan_kalshi_with_espn(
        client=cast(KalshiClient, FakeKalshiClient(events)),
        espn_final={"KXNBAGAME": [game]},
        min_yes_price=91,
        max_bet_cents=1000,
        dry_run=True,
    )

    session = db_module.get_session()
    scans = session.query(Scan).all()
    opps = session.query(Opportunity).all()
    trades = session.query(Trade).all()
    session.close()

    assert len(scans) == 1
    assert scans[0].opportunities_found == 1

    assert len(opps) == 1
    opp = opps[0]
    assert opp.ticker == "KXNBAGAME-26JUL07LALSEA-SEA"
    assert opp.yes_ask == 94
    assert opp.spread == 6
    assert opp.sport_path == "basketball/nba"
    assert opp.espn_score_diff == 12

    assert len(trades) == 1
    t = trades[0]
    assert t.ticker == "KXNBAGAME-26JUL07LALSEA-SEA"
    assert t.dry_run is True
    assert t.yes_price == 94
    assert t.count == 10  # 1000 // 94
