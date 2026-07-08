"""Integration test for scan_kalshi_with_espn.

Fake Kalshi client + one matching ESPN game → asserts the opportunity is
recorded. Placement moved out of this path in ADR-0002 (the single gate now
lives in evaluate_strategies); this function only discovers + records.
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


async def test_scan_records_opportunity_without_placing():
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

    await scan_kalshi_with_espn(
        client=cast(KalshiClient, FakeKalshiClient(events)),
        espn_final={"KXNBAGAME": [game]},
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

    # Placement is no longer this path's job.
    assert trades == []
