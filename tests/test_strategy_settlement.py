"""Settlement reconciliation tests for Phase 3 (D-16, D-17, D-18).

Wave 0 stubs — turn green when Plan 03-03 ships scanner.py
check_settlements + on_lifecycle filter changes.

`on_lifecycle` is currently a closure inside `run_scanner`. The
Wave-2 executor must extract it to a module-level function for
testability (planner judgment per PATTERNS.md). If the executor
keeps it as a closure, these tests will need to refactor — flag in
summary.
"""

from typing import cast

import predictions.db as db_module
from predictions.db import Trade
from predictions.kalshi_client import KalshiClient


class FakeClient:
    """Minimal KalshiClient stand-in for settlement tests."""

    def __init__(self, market_state: dict[str, dict]):
        self.market_state = market_state

    async def get_market(self, ticker: str) -> dict:
        return self.market_state.get(ticker, {"status": "open"})

    async def get_balance(self) -> dict:
        return {"balance": 100000, "portfolio_value": 100000}


async def test_check_settlements_updates_strategy_trades(isolated_db):
    """D-18: check_settlements settles strategy dry-run trades (dry_run=True, strategy_name set)."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-T1",
            event_ticker="KX-T1",
            status="dry_run",
            dry_run=True,
            strategy_name="s1",
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    client = FakeClient({"KX-T1": {"status": "finalized", "result": "yes"}})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-T1").one()
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 25  # count * (100 - yes_price) = 5 * (100 - 95) = 25
    # The /api/strategy-analytics P&L curve filters out NULL settled_at rows;
    # if the writer ever stops setting this, the chart silently goes blank in
    # production while realized_pnl_cents stat still totals correctly.
    assert trade.settled_at is not None
    session.close()


async def test_on_lifecycle_updates_strategy_trades(isolated_db):
    """D-17: on_lifecycle applies same combined filter as check_settlements."""
    from predictions.scanner import on_lifecycle

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-T1",
            event_ticker="KX-T1",
            status="dry_run",
            dry_run=True,
            strategy_name="s1",
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    msg = {
        "msg": {
            "market_ticker": "KX-T1",
            "market_status": "finalized",
            "result": "yes",
        }
    }
    await on_lifecycle(msg)

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-T1").one()
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 25
    assert trade.settled_at is not None
    session.close()


async def test_strategy_pnl_math(isolated_db):
    """D-18: P&L math for strategy dry-runs — win and loss cases."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-WIN",
            event_ticker="KX-WIN",
            status="dry_run",
            dry_run=True,
            strategy_name="s1",
            side="yes",
            count=10,
            yes_price=95,
            cost_cents=950,
            potential_profit_cents=50,
        )
    )
    session.add(
        Trade(
            ticker="KX-LOSS",
            event_ticker="KX-LOSS",
            status="dry_run",
            dry_run=True,
            strategy_name="s1",
            side="yes",
            count=10,
            yes_price=95,
            cost_cents=950,
            potential_profit_cents=50,
        )
    )
    session.commit()
    session.close()

    client = FakeClient(
        {
            "KX-WIN": {"status": "finalized", "result": "yes"},
            "KX-LOSS": {"status": "finalized", "result": "no"},
        }
    )
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    win_trade = session.query(Trade).filter(Trade.ticker == "KX-WIN").one()
    loss_trade = session.query(Trade).filter(Trade.ticker == "KX-LOSS").one()
    # WIN: count * (100 - yes_price) = 10 * (100 - 95) = 50
    assert win_trade.status == "settled_win"
    assert win_trade.pnl_cents == 50
    # LOSS: -count * yes_price = -10 * 95 = -950
    assert loss_trade.status == "settled_loss"
    assert loss_trade.pnl_cents == -950
    session.close()


async def test_legacy_dry_runs_not_settled(isolated_db):
    """D-16 negation: legacy process-level dry-runs (strategy_name=None) are NOT settled."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-LEG",
            event_ticker="KX-LEG",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
        )
    )
    session.commit()
    session.close()

    client = FakeClient({"KX-LEG": {"status": "finalized", "result": "yes"}})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-LEG").one()
    assert trade.status == "dry_run"
    assert trade.pnl_cents is None
    session.close()


async def test_settlement_filter_symmetry(isolated_db):
    """D-17: check_settlements and on_lifecycle update the exact same trade set."""
    from predictions.scanner import check_settlements, on_lifecycle

    session = db_module.get_session()
    # Real placed trade
    session.add(
        Trade(
            ticker="KX-REAL",
            event_ticker="KX-REAL",
            status="placed",
            dry_run=False,
            strategy_name=None,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    # Strategy dry-run trade
    session.add(
        Trade(
            ticker="KX-STRAT",
            event_ticker="KX-STRAT",
            status="dry_run",
            dry_run=True,
            strategy_name="s1",
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    # Legacy process-level dry-run (should NOT be settled by either path)
    session.add(
        Trade(
            ticker="KX-LEG",
            event_ticker="KX-LEG",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
        )
    )
    # Already-settled trade (should be ignored by both paths)
    session.add(
        Trade(
            ticker="KX-DONE",
            event_ticker="KX-DONE",
            status="settled_win",
            dry_run=False,
            strategy_name=None,
            pnl_cents=50,
        )
    )
    session.commit()
    session.close()

    market_state = {
        "KX-REAL": {"status": "finalized", "result": "yes"},
        "KX-STRAT": {"status": "finalized", "result": "yes"},
        "KX-LEG": {"status": "finalized", "result": "yes"},
        "KX-DONE": {"status": "finalized", "result": "yes"},
    }
    client = FakeClient(market_state)

    # Run check_settlements (REST fallback path)
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    real_after_rest = session.query(Trade).filter(Trade.ticker == "KX-REAL").one().status
    strat_after_rest = session.query(Trade).filter(Trade.ticker == "KX-STRAT").one().status
    leg_after_rest = session.query(Trade).filter(Trade.ticker == "KX-LEG").one().status
    done_after_rest = session.query(Trade).filter(Trade.ticker == "KX-DONE").one().status
    session.close()

    # Reset settled trades back to open state for on_lifecycle test
    session = db_module.get_session()
    for ticker, orig_status in [("KX-REAL", "placed"), ("KX-STRAT", "dry_run")]:
        t = session.query(Trade).filter(Trade.ticker == ticker).one()
        t.status = orig_status
        t.pnl_cents = None
        t.settled_at = None
    session.commit()
    session.close()

    # Run on_lifecycle (WS primary path) for the same tickers
    for ticker in ["KX-REAL", "KX-STRAT", "KX-LEG", "KX-DONE"]:
        await on_lifecycle(
            {"msg": {"market_ticker": ticker, "market_status": "finalized", "result": "yes"}}
        )

    session = db_module.get_session()
    real_after_ws = session.query(Trade).filter(Trade.ticker == "KX-REAL").one().status
    strat_after_ws = session.query(Trade).filter(Trade.ticker == "KX-STRAT").one().status
    leg_after_ws = session.query(Trade).filter(Trade.ticker == "KX-LEG").one().status
    done_after_ws = session.query(Trade).filter(Trade.ticker == "KX-DONE").one().status
    session.close()

    # Both paths must produce the same outcome for each trade
    assert real_after_rest == real_after_ws == "settled_win"
    assert strat_after_rest == strat_after_ws == "settled_win"
    assert leg_after_rest == leg_after_ws == "dry_run"  # unchanged
    assert done_after_rest == done_after_ws == "settled_win"  # already settled, unchanged
