"""Direct tests for the placement functions via the typed MarketOpportunity object (#7)."""

import predictions.db as db_module
from predictions.db import Trade
from predictions.scanner import MarketOpportunity, place_bet, place_strategy_trade


def test_place_strategy_trade_writes_dry_run_trade():
    opp = MarketOpportunity(
        ticker="KXNBAGAME-20260101-SEALAL",
        event_ticker="KXNBAGAME-20260101",
        title="Seattle at Los Angeles",
        yes_ask=95,
        espn_clock_seconds=60,
    )

    session = db_module.get_session()
    place_strategy_trade(session, opp, strategy_name="s1", max_cost_cents=500)
    session.close()

    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    t = trades[0]
    assert t.ticker == "KXNBAGAME-20260101-SEALAL"
    assert t.event_ticker == "KXNBAGAME-20260101"
    assert t.title == "Seattle at Los Angeles"
    assert t.status == "dry_run"
    assert t.dry_run is True
    assert t.strategy_name == "s1"
    assert t.yes_price == 95
    assert t.count == 5  # 500 // 95
    assert t.cost_cents == 475
    assert t.potential_profit_cents == 25  # 5 * (100 - 95)
    assert t.espn_clock_seconds == 60


async def test_place_bet_dry_run_writes_trade():
    opp = MarketOpportunity(
        ticker="KXNBAGAME-20260101-SEALAL",
        event_ticker="KXNBAGAME-20260101",
        title="Seattle at Los Angeles",
        yes_ask=94,
        espn_period=4,
        espn_clock="0:47",
        espn_clock_seconds=47,
    )

    result = await place_bet(client=None, opp=opp, max_cost_cents=1000, dry_run=True)

    assert result == {"dry_run": True, "count": 10, "yes_price": 94}
    session = db_module.get_session()
    trades = session.query(Trade).all()
    session.close()
    assert len(trades) == 1
    t = trades[0]
    assert t.ticker == "KXNBAGAME-20260101-SEALAL"
    assert t.event_ticker == "KXNBAGAME-20260101"
    assert t.title == "Seattle at Los Angeles"
    assert t.status == "dry_run"
    assert t.dry_run is True
    assert t.yes_price == 94
    assert t.count == 10  # 1000 // 94
    assert t.cost_cents == 940
    assert t.potential_profit_cents == 60  # 10 * (100 - 94)
    assert t.espn_clock_seconds == 47


async def test_place_bet_unaffordable_places_nothing():
    opp = MarketOpportunity(
        ticker="KXNBAGAME-20260101-SEALAL",
        event_ticker="KXNBAGAME-20260101",
        title="Seattle at Los Angeles",
        yes_ask=94,
    )

    result = await place_bet(client=None, opp=opp, max_cost_cents=50, dry_run=True)

    assert result is None
    session = db_module.get_session()
    assert session.query(Trade).count() == 0
    session.close()
