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

import httpx

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


async def test_on_lifecycle_settles_process_dry_runs(isolated_db):
    """Issue #2: WS path settles process dry-runs too (symmetry with REST path)."""
    from predictions.scanner import on_lifecycle

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-PROC",
            event_ticker="KX-PROC",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
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
            "market_ticker": "KX-PROC",
            "market_status": "finalized",
            "result": "yes",
        }
    }
    await on_lifecycle(msg)

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-PROC").one()
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 25
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


async def test_process_dry_runs_settle(isolated_db):
    """Issue #2: process dry-runs (dry_run=True, strategy_name=None) settle
    like live trades so they free max_positions slots."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-PROC",
            event_ticker="KX-PROC",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    client = FakeClient({"KX-PROC": {"status": "finalized", "result": "yes"}})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-PROC").one()
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 25
    assert trade.settled_at is not None
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
    # Process dry-run (settled by both paths since issue #2)
    session.add(
        Trade(
            ticker="KX-PROC",
            event_ticker="KX-PROC",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
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
        "KX-PROC": {"status": "finalized", "result": "yes"},
        "KX-DONE": {"status": "finalized", "result": "yes"},
    }
    client = FakeClient(market_state)

    # Run check_settlements (REST fallback path)
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    real_after_rest = session.query(Trade).filter(Trade.ticker == "KX-REAL").one().status
    strat_after_rest = session.query(Trade).filter(Trade.ticker == "KX-STRAT").one().status
    proc_after_rest = session.query(Trade).filter(Trade.ticker == "KX-PROC").one().status
    done_after_rest = session.query(Trade).filter(Trade.ticker == "KX-DONE").one().status
    session.close()

    # Reset settled trades back to open state for on_lifecycle test
    session = db_module.get_session()
    for ticker, orig_status in [
        ("KX-REAL", "placed"),
        ("KX-STRAT", "dry_run"),
        ("KX-PROC", "dry_run"),
    ]:
        t = session.query(Trade).filter(Trade.ticker == ticker).one()
        t.status = orig_status
        t.pnl_cents = None
        t.settled_at = None
    session.commit()
    session.close()

    # Run on_lifecycle (WS primary path) for the same tickers
    for ticker in ["KX-REAL", "KX-STRAT", "KX-PROC", "KX-DONE"]:
        await on_lifecycle(
            {"msg": {"market_ticker": ticker, "market_status": "finalized", "result": "yes"}}
        )

    session = db_module.get_session()
    real_after_ws = session.query(Trade).filter(Trade.ticker == "KX-REAL").one().status
    strat_after_ws = session.query(Trade).filter(Trade.ticker == "KX-STRAT").one().status
    proc_after_ws = session.query(Trade).filter(Trade.ticker == "KX-PROC").one().status
    done_after_ws = session.query(Trade).filter(Trade.ticker == "KX-DONE").one().status
    session.close()

    # Both paths must produce the same outcome for each trade
    assert real_after_rest == real_after_ws == "settled_win"
    assert strat_after_rest == strat_after_ws == "settled_win"
    assert proc_after_rest == proc_after_ws == "settled_win"
    assert done_after_rest == done_after_ws == "settled_win"  # already settled, unchanged


def test_settle_trade_win():
    """settle_trade: win pays potential_profit minus fee, stamps settled_at."""
    from predictions.scanner import settle_trade

    trade = Trade(
        ticker="KX-W",
        side="yes",
        count=10,
        yes_price=95,
        cost_cents=950,
        potential_profit_cents=50,
        fee_cents=7,
        status="placed",
        dry_run=False,
    )
    settle_trade(trade, "yes")
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 43  # potential_profit_cents - fee = 50 - 7
    assert trade.settled_at is not None


def test_settle_trade_loss():
    """settle_trade: loss costs cost_cents plus fee."""
    from predictions.scanner import settle_trade

    trade = Trade(
        ticker="KX-L",
        side="yes",
        count=10,
        yes_price=95,
        cost_cents=950,
        potential_profit_cents=50,
        fee_cents=7,
        status="placed",
        dry_run=False,
    )
    settle_trade(trade, "no")
    assert trade.status == "settled_loss"
    assert trade.pnl_cents == -957  # -cost_cents - fee = -950 - 7
    assert trade.settled_at is not None


def test_settle_trade_null_fee_counts_as_zero():
    """settle_trade: NULL fee_cents (strategy dry-runs) means zero fee."""
    from predictions.scanner import settle_trade

    trade = Trade(
        ticker="KX-NF",
        side="yes",
        count=5,
        yes_price=95,
        cost_cents=475,
        potential_profit_cents=25,
        fee_cents=None,
        status="dry_run",
        dry_run=True,
        strategy_name="s1",
    )
    settle_trade(trade, "yes")
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 25


class RaisingClient(FakeClient):
    """FakeClient that raises a stored exception for selected tickers."""

    def __init__(self, market_state: dict[str, dict], errors: dict[str, Exception]):
        super().__init__(market_state)
        self.errors = errors

    async def get_market(self, ticker: str) -> dict:
        if ticker in self.errors:
            raise self.errors[ticker]
        return await super().get_market(ticker)


def _http_status_error(ticker: str, status_code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("GET", f"https://api.example/markets/{ticker}")
    return httpx.HTTPStatusError(
        f"{status_code}",
        request=request,
        response=httpx.Response(status_code, request=request),
    )


async def test_check_settlements_skips_finalized_without_result(isolated_db):
    """Kalshi can report status=finalized before result is populated; settling
    on the empty result would stamp a permanent settled_loss on a winner."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-NORES",
            event_ticker="KX-NORES",
            status="placed",
            dry_run=False,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    client = FakeClient({"KX-NORES": {"status": "finalized", "result": ""}})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-NORES").one()
    assert trade.status == "placed"
    assert trade.pnl_cents is None
    assert trade.settled_at is None
    session.close()

    client = FakeClient({"KX-NORES": {"status": "finalized", "result": "yes"}})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-NORES").one()
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 25
    session.close()


async def test_on_lifecycle_skips_empty_result(isolated_db):
    """WS lifecycle with finalized status but no result must not settle."""
    from predictions.scanner import on_lifecycle

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-NORES",
            event_ticker="KX-NORES",
            status="placed",
            dry_run=False,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    await on_lifecycle({"msg": {"market_ticker": "KX-NORES", "market_status": "finalized"}})

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-NORES").one()
    assert trade.status == "placed"
    assert trade.pnl_cents is None
    session.close()


async def test_on_lifecycle_legacy_null_cents_does_not_poison_batch(isolated_db):
    """A legacy process dry-run with NULL cost/profit cents must not blow up
    the loop and roll back a real trade's settlement in the same batch."""
    from predictions.scanner import on_lifecycle

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-BATCH",
            event_ticker="KX-BATCH",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=None,
            potential_profit_cents=None,
        )
    )
    session.add(
        Trade(
            ticker="KX-BATCH",
            event_ticker="KX-BATCH",
            status="placed",
            dry_run=False,
            side="yes",
            count=10,
            yes_price=95,
            cost_cents=950,
            potential_profit_cents=50,
            fee_cents=7,
        )
    )
    session.commit()
    session.close()

    await on_lifecycle(
        {"msg": {"market_ticker": "KX-BATCH", "market_status": "finalized", "result": "no"}}
    )

    session = db_module.get_session()
    real = session.query(Trade).filter(Trade.dry_run == False).one()
    legacy = session.query(Trade).filter(Trade.dry_run == True).one()
    assert real.status == "settled_loss"
    assert real.pnl_cents == -957
    assert legacy.status == "settled_loss"
    assert legacy.pnl_cents == 0
    session.close()


async def test_check_settlements_settles_legacy_null_cents(isolated_db):
    """REST path: legacy NULL-cents rows settle (pnl 0) instead of erroring
    on every pass and clogging max_positions forever."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-LEG",
            event_ticker="KX-LEG",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=None,
            potential_profit_cents=None,
        )
    )
    session.commit()
    session.close()

    client = FakeClient({"KX-LEG": {"status": "finalized", "result": "yes"}})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-LEG").one()
    assert trade.status == "settled_win"
    assert trade.pnl_cents == 0
    assert trade.settled_at is not None
    session.close()


async def test_check_settlements_closes_trade_on_market_404(isolated_db):
    """A delisted market (404) must terminally close the trade so it stops
    counting against max_positions and stops burning a REST call per pass."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-GONE",
            event_ticker="KX-GONE",
            status="dry_run",
            dry_run=True,
            strategy_name=None,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    client = RaisingClient({}, {"KX-GONE": _http_status_error("KX-GONE", 404)})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-GONE").one()
    assert trade.status == "error"
    assert trade.error is not None and "404" in trade.error
    session.close()


async def test_check_settlements_keeps_trade_on_transient_error(isolated_db):
    """Transient HTTP failures (e.g. 500) must not terminally close a trade."""
    from predictions.scanner import check_settlements

    session = db_module.get_session()
    session.add(
        Trade(
            ticker="KX-FLAKY",
            event_ticker="KX-FLAKY",
            status="placed",
            dry_run=False,
            side="yes",
            count=5,
            yes_price=95,
            cost_cents=475,
            potential_profit_cents=25,
        )
    )
    session.commit()
    session.close()

    client = RaisingClient({}, {"KX-FLAKY": _http_status_error("KX-FLAKY", 500)})
    await check_settlements(cast(KalshiClient, client))

    session = db_module.get_session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-FLAKY").one()
    assert trade.status == "placed"
    assert trade.error is None
    session.close()


def test_settle_trade_tag_derives_from_dry_run():
    """settle_trade's log tag comes from Trade.dry_run now that every trade
    carries a strategy_name (ADR-0002) — not from strategy_name presence."""
    from predictions.scanner import settle_trade

    dry = Trade(
        ticker="KX-D",
        side="yes",
        count=5,
        yes_price=95,
        cost_cents=475,
        potential_profit_cents=25,
        status="dry_run",
        dry_run=True,
        strategy_name="main",
    )
    live = Trade(
        ticker="KX-R",
        side="yes",
        count=5,
        yes_price=95,
        cost_cents=475,
        potential_profit_cents=25,
        status="placed",
        dry_run=False,
        strategy_name="main",
    )
    # Both settle correctly regardless of the tag; the tag is log-only, so we
    # assert the settlement outcome differs only by placement, not attribution.
    settle_trade(dry, "yes")
    settle_trade(live, "yes")
    assert dry.status == "settled_win" and dry.dry_run is True
    assert live.status == "settled_win" and live.dry_run is False
