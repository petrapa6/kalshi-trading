"""
Kalshi Sports Market Scanner

Scans for sports prediction markets where:
  1. Yes price >= 88 cents (outcome nearly decided)
  2. ESPN confirms the game is in its FINAL MINUTES
     (4th quarter <=5 min, 9th inning, 2nd half final minutes, etc)
  3. Sufficient liquidity to trade

Uses ESPN live scoreboard to verify game state, so we only buy
when a game is truly almost over - not just pre-game favorites.

Strategy: Buy Yes at 88-99c on nearly-finished games,
collect $1 at settlement. High volume, high win rate.
"""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

from predictions.db import (
    BalanceSnapshot,
    Opportunity,
    Scan,
    Trade,
    get_config,
    get_config_int,
    get_final_seconds_thresholds,
    get_session,
    init_db,
)
from predictions.decision import live_trigger, trigger_matches, within_expiry_window
from predictions.espn import (
    get_categorized_games,
    match_kalshi_to_espn,
)
from predictions.kalshi_client import KalshiClient, KalshiWebSocket, extract_cents, extract_volume
from predictions.sports import (
    CLOCKLESS_SPORT_PATHS,
    COUNT_UP_SPORT_PATHS,
    SPORT_PATH_TO_FAMILY,
    SPORT_PERIOD_LENGTH_SECS,
    SPORTS_GAME_SERIES,
)
from predictions.strategies import Strategy, load_strategies

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("scanner.log"),
    ],
)
log = logging.getLogger(__name__)

# Module-level market prices dict, populated by WS/API in run_scanner
market_prices: dict[str, dict] = {}


@dataclass(frozen=True)
class MarketOpportunity:
    """Typed currency between market discovery and order placement (#7).

    Core identity + price are required; ESPN game context is optional
    because the strategy path fires off the slim WS price cache, which
    has no ESPN display state.
    """

    ticker: str
    event_ticker: str
    title: str
    yes_ask: int  # integer cents
    yes_bid: int | None = None
    yes_sub_title: str = ""
    volume: int | None = None
    close_time: str = ""
    expected_expiration: str = ""
    series_ticker: str = ""
    sport_path: str | None = None
    espn_period: int | None = None
    espn_clock: str | None = None
    espn_clock_seconds: int | None = None
    espn_home: str | None = None
    espn_away: str | None = None
    espn_home_score: int | None = None
    espn_away_score: int | None = None
    espn_lead: int = 0

    @property
    def spread(self) -> int:
        return 100 - self.yes_ask

    @property
    def espn_score(self) -> str:
        return f"{self.espn_away_score}-{self.espn_home_score}"


# Minimum volume on the market to ensure there's liquidity
MIN_VOLUME = 50


def elapsed_minutes(sport_path: str, clock_seconds: float, period: int) -> int | None:
    """Return game-clock minutes elapsed since start, or None if not derivable.

    Returns None for clockless sports (baseball, tennis) — caller logs +
    skips min_minute triggers for these. Returns None for unknown
    sport_paths — caller logs + skips.
    """
    if sport_path in CLOCKLESS_SPORT_PATHS:
        return None
    period_secs = SPORT_PERIOD_LENGTH_SECS.get(sport_path)
    if period_secs is None:
        return None
    if sport_path in COUNT_UP_SPORT_PATHS:
        return int(clock_seconds // 60)
    completed_periods = max(0, period - 1)
    elapsed_in_current = max(0, period_secs - int(clock_seconds))
    return (completed_periods * period_secs + elapsed_in_current) // 60


def load_client() -> KalshiClient:
    key_id = os.environ["KALSHI_API_KEY"]
    # Support private key as env var (for ECS) or file path (for local)
    key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
    if key_pem:
        return KalshiClient.from_key_string(key_id, key_pem)
    key_path = os.environ["KALSHI_PRIVATE_KEY_PATH"]
    return KalshiClient.from_key_file(key_id, key_path)


async def find_sports_game_series(client: KalshiClient) -> list[str]:
    """Discover sports game series (not futures/awards)."""
    series_data = await client.get_series()
    game_tickers = []
    for s in series_data.get("series", []):
        ticker = s.get("ticker", "")
        # Match known game series or anything with "GAME" / "FIGHT" / "MATCH" in ticker
        if any(ticker.startswith(p) for p in SPORTS_GAME_SERIES):
            game_tickers.append(ticker)
        elif s.get("category", "") == "Sports" and any(
            kw in ticker.upper() for kw in ["GAME", "FIGHT", "MATCH", "BOUT"]
        ):
            game_tickers.append(ticker)
    return game_tickers


def has_liquidity(market: dict, min_volume: int = MIN_VOLUME) -> bool:
    """Check that the market has enough volume/liquidity to trade."""
    volume = extract_volume(market) or 0
    # Also check there's actually a bid (someone's on the other side)
    yes_bid = extract_cents(market, "yes_bid") or 0
    return volume >= min_volume and yes_bid > 0


async def place_bet(
    client: KalshiClient | None,
    opp: MarketOpportunity,
    max_cost_cents: int,
    dry_run: bool = True,
) -> Optional[dict]:
    """`client` may be None only when dry_run=True (tests); the live
    branch requires one."""
    yes_price = opp.yes_ask
    count = max_cost_cents // yes_price
    if count < 1:
        log.info(f"  Cannot afford any contracts at {yes_price}c (budget: {max_cost_cents}c)")
        return None

    profit_per_contract = 100 - yes_price
    total_profit_if_win = count * profit_per_contract
    total_cost = count * yes_price

    log.info(
        f"  Order: BUY {count}x YES @ {yes_price}c = ${total_cost / 100:.2f} cost, "
        f"${total_profit_if_win / 100:.2f} potential profit | "
        f"ESPN: P{opp.espn_period} {opp.espn_clock}"
    )

    session = get_session()
    trade = Trade(
        ticker=opp.ticker,
        event_ticker=opp.event_ticker,
        title=opp.title,
        side="yes",
        action="buy",
        count=count,
        yes_price=yes_price,
        cost_cents=total_cost,
        potential_profit_cents=total_profit_if_win,
        dry_run=dry_run,
        espn_clock_seconds=opp.espn_clock_seconds,
    )

    if dry_run:
        log.info("  [DRY RUN] Order not placed")
        trade.status = "dry_run"
        session.add(trade)
        session.commit()
        session.close()
        return {"dry_run": True, "count": count, "yes_price": yes_price}

    assert client is not None
    try:
        result = await client.create_order(
            ticker=opp.ticker,
            side="yes",
            action="buy",
            count=count,
            yes_price=yes_price,
        )
        log.info(f"  Order placed: {result}")
        order = result.get("order", {})
        trade.order_id = order.get("order_id", "")
        # Kalshi usually returns fee in cents. Use extract_cents to handle potential
        # string formatting
        trade.fee_cents = (
            extract_cents(order, "fee") if "fee_dollars" in order else int(order.get("fee", 0))
        )
        trade.status = "placed"
        session.add(trade)
        session.commit()
        session.close()
        return result
    except Exception as e:
        log.error(f"  Order failed: {e}")
        trade.status = "error"
        trade.error = str(e)
        session.add(trade)
        session.commit()
        session.close()
        return None


def settle_trade(trade: Trade, result: str) -> None:
    """Apply the settlement transition to a trade in place (pure, no I/O).

    Single home for the win/loss/fee/status/pnl_cents math; both
    settlement discovery paths (check_settlements, on_lifecycle) call it.
    """
    fee = trade.fee_cents or 0
    tag = "STRATEGY" if trade.strategy_name else "REAL"
    trade.settled_at = datetime.now(timezone.utc)
    if result == trade.side:
        trade.status = "settled_win"
        trade.pnl_cents = trade.potential_profit_cents - fee
        log.info(
            f"  {tag} WIN: {trade.ticker} settled {result} | P&L: +${trade.pnl_cents / 100:.2f}"
        )
    else:
        trade.status = "settled_loss"
        trade.pnl_cents = -trade.cost_cents - fee
        log.info(
            f"  {tag} LOSS: {trade.ticker} settled {result} | P&L: ${trade.pnl_cents / 100:.2f}"
        )


async def check_settlements(client: KalshiClient):
    """Check open trades for settlement and update P&L."""
    session = get_session()
    open_trades = (
        session.query(Trade).filter(Trade.status.in_(("placed", "filled", "dry_run"))).all()
    )

    for trade in open_trades:
        try:
            market = await client.get_market(trade.ticker)
            status = market.get("status", "")
            result = market.get("result", "")

            if status in ("finalized", "settled"):
                settle_trade(trade, result)
        except Exception as e:
            log.warning(f"  Failed to check {trade.ticker}: {e}")

    session.commit()
    session.close()


async def on_lifecycle(msg: dict, client: KalshiClient | None = None) -> None:
    """WS market_lifecycle_v2 handler — settle trades on finalized markets.

    Module-level (extracted from run_scanner closure) so tests can call
    it directly.

    `client` is optional so tests can call this without a Kalshi
    client; production passes one so post-settlement record_balance runs.
    """
    data = msg.get("msg", {})
    ticker = data.get("market_ticker", "")
    new_status = data.get("market_status", "")
    result = data.get("result", "")
    if new_status not in ("finalized", "settled") or not ticker:
        return

    log.info(f"WS lifecycle: {ticker} -> {new_status} result={result}")
    session = get_session()
    open_trades = (
        session.query(Trade)
        .filter(
            Trade.ticker == ticker,
            Trade.status.in_(("placed", "filled", "dry_run")),
        )
        .all()
    )
    for trade in open_trades:
        settle_trade(trade, result)
    session.commit()
    session.close()
    if client is not None:
        await record_balance(client)


async def record_balance(client: KalshiClient):
    try:
        balance = await client.get_balance()
        session = get_session()
        snap = BalanceSnapshot(
            balance_cents=balance.get("balance", 0),
            portfolio_value_cents=balance.get("portfolio_value", 0),
        )
        session.add(snap)
        session.commit()
        session.close()
        bal = balance.get("balance", 0) / 100
        port = balance.get("portfolio_value", 0) / 100
        log.info(f"Balance: ${bal:.2f}, Portfolio: ${port:.2f}")
    except Exception as e:
        log.warning(f"Failed to record balance: {e}")


def place_strategy_trade(
    session,
    opp: MarketOpportunity,
    strategy_name: str,
    max_cost_cents: int,
) -> None:
    """Write a dry-run Trade row from a strategy fire (D-13).

    NEVER calls Kalshi REST. Distinct from place_bet's process-level
    DRY_RUN branch — see 03-CONTEXT.md D-13 specifics. yes_price is
    sourced from market_prices cache (Kalshi yes_ask, integer cents).
    """
    yes_price = opp.yes_ask
    if not yes_price:
        log.warning("place_strategy_trade: missing yes_ask for %s", opp.ticker)
        return
    count = max_cost_cents // yes_price
    if count < 1:
        log.info(
            "place_strategy_trade %s: cannot afford any contracts at %dc (budget %dc)",
            strategy_name,
            yes_price,
            max_cost_cents,
        )
        return

    total_cost = count * yes_price
    total_profit = count * (100 - yes_price)
    log.info(
        f"STRATEGY FIRE {strategy_name}: BUY {count}x YES {opp.ticker} @ {yes_price}c = "
        f"${total_cost / 100:.2f} cost, ${total_profit / 100:.2f} potential profit"
    )

    trade = Trade(
        ticker=opp.ticker,
        event_ticker=opp.event_ticker,
        title=opp.title,
        side="yes",
        action="buy",
        count=count,
        yes_price=yes_price,
        cost_cents=total_cost,
        potential_profit_cents=total_profit,
        status="dry_run",
        dry_run=True,
        strategy_name=strategy_name,
        espn_clock_seconds=opp.espn_clock_seconds,
    )
    session.add(trade)
    session.commit()


async def evaluate_strategies(
    session,
    espn_final_period: dict,
    max_bet_cents: int,
    strategies: list[Strategy] | None = None,
) -> int:
    """Per-iteration: evaluate every loaded strategy against every live market.

    D-14: max_bet_cents is supplied by the caller. D-23 (supersedes D-15):
    loop-level trading_paused early-exit. D-04 cadence: same scan tick
    (~5s), no new asyncio loop. D-05: load strategies once per tick if
    not provided, log+skip on parse error. D-06: markets × strategies ×
    triggers with first-trigger-wins. D-10: per-strategy dedupe. D-11:
    multiple strategies CAN fire on the same ticker.

    Returns count of new strategy fires this tick.
    """
    if get_config("trading_paused") == "true":
        log.info("evaluate_strategies: trading paused via config — skipping tick")
        return 0

    if strategies is None:
        try:
            strategies = load_strategies()
        except Exception as e:
            log.warning("evaluate_strategies: failed to load strategies: %s", e)
            return 0
    if not strategies:
        return 0

    existing: set[tuple[str, str]] = {
        (sn, t)
        for sn, t in session.query(Trade.strategy_name, Trade.ticker)
        .filter(Trade.strategy_name.isnot(None))
        .all()
    }

    fired_this_tick = 0
    for _series_ticker, espn_games in espn_final_period.items():
        for game in espn_games:
            sport_path = game.sport_path
            family = SPORT_PATH_TO_FAMILY.get(sport_path)
            elapsed = elapsed_minutes(sport_path, game.clock_seconds, game.period)

            for ticker, prices in list(market_prices.items()):
                yes_ask = prices.get("yes_ask")
                volume = prices.get("volume", 0) or 0
                if not yes_ask or volume < MIN_VOLUME:
                    continue
                title = prices.get("title", "")
                if not match_kalshi_to_espn(ticker, title, [game]):
                    continue

                for strategy in strategies:
                    if (strategy.name, ticker) in existing:
                        continue
                    for trigger in strategy.triggers:
                        if not trigger_matches(
                            trigger,
                            family=family,
                            elapsed=elapsed,
                            score_diff=game.score_diff,
                            yes_ask=yes_ask,
                        ):
                            continue
                        try:
                            place_strategy_trade(
                                session=session,
                                opp=MarketOpportunity(
                                    ticker=ticker,
                                    event_ticker=prices.get("event_ticker", ""),
                                    title=title,
                                    yes_ask=yes_ask,
                                    espn_clock_seconds=int(game.clock_seconds),
                                ),
                                strategy_name=strategy.name,
                                max_cost_cents=max_bet_cents,
                            )
                            existing.add((strategy.name, ticker))
                            fired_this_tick += 1
                        except Exception as e:
                            log.warning(
                                "place_strategy_trade failed strategy=%s ticker=%s: %s",
                                strategy.name,
                                ticker,
                                e,
                            )
                        break  # D-12: first-trigger-wins per (strategy, market) tick

    if fired_this_tick:
        log.info("evaluate_strategies: fired %d strategy trades", fired_this_tick)
    return fired_this_tick


async def scan_kalshi_with_espn(
    client: KalshiClient,
    espn_final: dict,
    min_yes_price: int,
    max_bet_cents: int,
    dry_run: bool,
):
    """Scan Kalshi markets against cached ESPN game state and place bets.

    D-14: max_bet_cents is computed ONCE per scan iteration by the
    caller (kalshi_scan_loop) and passed in here. Same value is also
    passed to evaluate_strategies. NO balance fetch inside this function.
    """
    opportunities: list[MarketOpportunity] = []

    if not espn_final:
        log.info("No ESPN games in final minutes — skipping Kalshi scan")
        return

    # max_bet_cents was computed by caller (D-14); no balance fetch here.

    # Scan Kalshi markets against ESPN games
    for series_ticker, espn_games in espn_final.items():
        try:
            cursor = None
            while True:
                data = await client.get_events(
                    status="open",
                    series_ticker=series_ticker,
                    with_nested_markets=True,
                    cursor=cursor,
                )
                events = data.get("events", [])
                if not events:
                    break

                for event in events:
                    event_ticker = event.get("event_ticker", "")
                    title = event.get("title", "")
                    markets = event.get("markets", [])

                    for market in markets:
                        status = market.get("status", "")
                        if status not in ("active", "open"):
                            continue
                        if not has_liquidity(market):
                            continue

                        if not within_expiry_window(
                            market.get("expected_expiration_time", ""),
                            datetime.now(timezone.utc),
                        ):
                            continue

                        yes_bid = extract_cents(market, "yes_bid")
                        yes_ask = extract_cents(market, "yes_ask")
                        ticker = market.get("ticker", "")
                        if not yes_ask:
                            continue

                        espn_game = match_kalshi_to_espn(ticker, title, espn_games)
                        if not espn_game:
                            continue

                        min_lead = get_config_int(f"lead:{espn_game.sport_path}")
                        if not trigger_matches(
                            live_trigger(min_yes_price, min_lead),
                            family=None,
                            elapsed=None,
                            score_diff=espn_game.score_diff,
                            yes_ask=yes_ask,
                        ):
                            continue

                        log.info(f"new opportunity: {title}")
                        opportunities.append(
                            MarketOpportunity(
                                ticker=ticker,
                                event_ticker=event_ticker,
                                title=title,
                                yes_sub_title=market.get("yes_sub_title", ""),
                                yes_bid=yes_bid,
                                yes_ask=yes_ask,
                                volume=extract_volume(market),
                                close_time=market.get("close_time", ""),
                                expected_expiration=market.get("expected_expiration_time", ""),
                                series_ticker=series_ticker,
                                sport_path=espn_game.sport_path,
                                espn_period=espn_game.period,
                                espn_clock=espn_game.display_clock,
                                espn_clock_seconds=int(espn_game.clock_seconds),
                                espn_home=espn_game.home_team,
                                espn_away=espn_game.away_team,
                                espn_home_score=espn_game.home_score,
                                espn_away_score=espn_game.away_score,
                                espn_lead=espn_game.score_diff,
                            )
                        )

                cursor = data.get("cursor", "")
                if not cursor:
                    break

        except Exception as e:
            log.warning(f"Error scanning series {series_ticker}: {e}")
            continue

    opportunities.sort(key=lambda x: (-x.spread, -x.espn_lead))

    # Record scan and process opportunities
    session = get_session()
    scan = Scan(opportunities_found=len(opportunities))
    session.add(scan)
    session.commit()
    scan_id = scan.id

    if not opportunities:
        log.info("No Kalshi opportunities matched ESPN games")
    else:
        open_statuses = ("placed", "filled", "dry_run")
        open_trades = (
            session.query(Trade)
            .filter(Trade.status.in_(open_statuses), Trade.dry_run == dry_run)
            .all()
        )
        open_event_tickers = {t.event_ticker for t in open_trades}
        open_count = len(open_trades)

        log.info(
            f"Found {len(opportunities)} opportunities on live games "
            f"({open_count}/20 open positions):"
        )
        for opp in opportunities:
            log.info(
                f"  {opp.ticker} | {opp.yes_sub_title} | "
                f"Yes Ask: {opp.yes_ask}c | Spread: {opp.spread}c | "
                f"ESPN: P{opp.espn_period} {opp.espn_clock} "
                f"{opp.espn_away}@{opp.espn_home} {opp.espn_score} | "
                f"Vol: {opp.volume}"
            )

            db_opp = Opportunity(
                scan_id=scan_id,
                ticker=opp.ticker,
                event_ticker=opp.event_ticker,
                series_ticker=opp.series_ticker,
                title=opp.title,
                yes_sub_title=opp.yes_sub_title,
                yes_bid=opp.yes_bid,
                yes_ask=opp.yes_ask,
                spread=opp.spread,
                volume=opp.volume,
                close_time=opp.close_time,
                sport_path=opp.sport_path,
                espn_period=opp.espn_period,
                espn_clock=opp.espn_clock,
                espn_home=opp.espn_home,
                espn_away=opp.espn_away,
                espn_home_score=opp.espn_home_score,
                espn_away_score=opp.espn_away_score,
                espn_score_diff=opp.espn_lead,
            )
            session.add(db_opp)

            if opp.event_ticker in open_event_tickers:
                log.info(f"  SKIP: already have position on {opp.event_ticker}")
                continue

            max_pos = get_config_int("max_positions") or 20
            if open_count >= max_pos:
                log.info("  SKIP: at max 20 open positions")
                continue

            if get_config("trading_paused") == "true":
                log.info("  SKIP: trading is paused via config")
                continue

            result = await place_bet(client, opp, max_cost_cents=max_bet_cents, dry_run=dry_run)
            if result:
                open_event_tickers.add(opp.event_ticker)
                open_count += 1

    session.commit()
    session.close()


async def backup_db():
    """Copy SQLite DB to S3 if bucket is configured."""
    bucket = os.getenv("DB_BACKUP_BUCKET")
    if not bucket:
        return
    db_url = os.getenv("DATABASE_URL", "")
    db_path = db_url.replace("sqlite:///", "") if db_url.startswith("sqlite:///") else None
    if not db_path or not os.path.exists(db_path):
        return
    try:
        import shutil
        from datetime import datetime, timezone

        import boto3

        # Copy to temp file first (safe while DB is in use)
        tmp = db_path + ".backup"
        shutil.copy2(db_path, tmp)

        s3 = boto3.client("s3")
        now = datetime.now(timezone.utc)
        key = f"backups/{now.strftime('%Y-%m-%d/%H%M')}-predictions.db"
        s3.upload_file(tmp, bucket, key)

        # Also keep a "latest" copy for easy restore
        s3.upload_file(tmp, bucket, "backups/latest.db")
        os.remove(tmp)
        log.info(f"DB backed up to s3://{bucket}/{key}")
    except Exception as e:
        log.warning(f"DB backup failed: {e}")


async def run_scanner(
    min_yes_price: int = 88,
    bet_percent: float = 5.0,
    poll_interval: int = 30,
    dry_run: bool = True,
):
    init_db()
    client = load_client()
    await record_balance(client)

    espn_interval = 10  # Refresh ESPN game state every 10s

    # Shared state protected by locks
    espn_cache: dict = {}
    espn_final_period_cache: dict = {}
    espn_lock = asyncio.Lock()

    # Track live market prices from WebSocket ticker updates (module-level for what-if access)
    global market_prices
    market_prices = {}  # ticker -> {yes_bid, yes_ask, volume}

    # Track which market tickers we're subscribed to
    subscribed_tickers: set[str] = set()
    ticker_sub_sid: int | None = None
    lifecycle_sub_sid: int | None = None

    ws = KalshiWebSocket(client)

    def on_ticker(msg: dict):
        """Handle real-time price updates from WebSocket."""
        data = msg.get("msg", {})
        ticker = data.get("market_ticker", "")
        if ticker:
            yes_bid = extract_cents(data, "yes_bid")
            yes_ask = extract_cents(data, "yes_ask")
            volume = extract_volume(data)
            # Warn if both prices are zero — could indicate WS switched field names
            if yes_ask == 0 and yes_bid == 0 and data:
                log.warning(f"WS ticker: zero prices for {ticker} — keys: {list(data.keys())}")
            market_prices[ticker] = {
                "yes_bid": yes_bid,
                "yes_ask": yes_ask,
                "volume": volume,
                "open_interest": data.get("open_interest", 0),
            }

    async def on_lifecycle_cb(msg: dict):
        await on_lifecycle(msg, client)

    ws.on("ticker", on_ticker)
    ws.on("market_lifecycle_v2", on_lifecycle_cb)

    async def espn_loop():
        """Refresh ESPN final-minutes games every 10s."""
        nonlocal espn_cache, espn_final_period_cache
        while True:
            try:
                log.info("ESPN: refreshing live game state...")
                fresh, fresh_fp = await get_categorized_games(get_final_seconds_thresholds())
                async with espn_lock:
                    espn_cache = fresh
                    espn_final_period_cache = fresh_fp
                total = sum(len(g) for g in fresh.values())
                if total:
                    log.info(f"ESPN: {total} games in final minutes across {list(fresh.keys())}")
                    for games in fresh.values():
                        for g in games:
                            log.info(
                                f"  ESPN: {g.away_team} @ {g.home_team} | "
                                f"{g.away_score}-{g.home_score} | "
                                f"P{g.period} {g.display_clock} | "
                                f"Lead: {g.score_diff}pts by {g.leading_team}"
                            )
                else:
                    log.info("ESPN: no games in final minutes")
            except Exception as e:
                log.warning(f"ESPN refresh error: {e}")
            await asyncio.sleep(espn_interval)

    async def kalshi_scan_loop():
        """Fetch Kalshi events, subscribe to new tickers, evaluate."""
        nonlocal ticker_sub_sid, lifecycle_sub_sid
        kalshi_interval = 5  # Discover new markets every 5s

        # Wait for first ESPN fetch + WS connect
        await asyncio.sleep(3)

        while True:
            try:
                log.info("=" * 60)
                # Re-read config each loop so changes take effect immediately
                cur_price = get_config_int("min_yes_price") or min_yes_price
                cur_bet_percent_str = get_config("bet_percent")
                cur_bet_percent = float(cur_bet_percent_str) if cur_bet_percent_str else bet_percent
                log.info(f"Kalshi: scanning for Yes >= {cur_price}c...")
                async with espn_lock:
                    current_espn = dict(espn_cache)
                    current_espn_fp = dict(espn_final_period_cache)

                # Discover all active market tickers from Kalshi API
                # Include both final-minutes and final-period series for what-if tracking
                all_series = set(current_espn.keys()) | set(current_espn_fp.keys())
                new_tickers: set[str] = set()
                for series_ticker in all_series:
                    try:
                        cursor = None
                        while True:
                            data = await client.get_events(
                                status="open",
                                series_ticker=series_ticker,
                                with_nested_markets=True,
                                cursor=cursor,
                            )
                            for event in data.get("events", []):
                                event_title = event.get("title", "")
                                event_ticker = event.get("event_ticker", "")
                                for market in event.get("markets", []):
                                    t = market.get("ticker", "")
                                    if t and market.get("status") in ("active", "open"):
                                        new_tickers.add(t)
                                        # Seed prices from API if WS hasn't updated yet.
                                        # title + event_ticker added per Phase 3 D-04
                                        # so evaluate_strategies can match_kalshi_to_espn.
                                        if t not in market_prices:
                                            market_prices[t] = {
                                                "yes_bid": extract_cents(market, "yes_bid"),
                                                "yes_ask": extract_cents(market, "yes_ask"),
                                                "volume": extract_volume(market),
                                                "title": event_title,
                                                "event_ticker": event_ticker,
                                            }
                            cursor = data.get("cursor", "")
                            if not cursor:
                                break
                    except Exception as e:
                        log.warning(f"Error fetching series {series_ticker}: {e}")

                # Subscribe to any new tickers via WebSocket
                to_add = new_tickers - subscribed_tickers
                if to_add:
                    tickers_list = list(to_add)
                    try:
                        if ticker_sub_sid is None:
                            ticker_sub_sid = await ws.subscribe(["ticker"], tickers_list)
                            lifecycle_sub_sid = await ws.subscribe(
                                ["market_lifecycle_v2"], tickers_list
                            )
                        else:
                            assert ticker_sub_sid is not None
                            assert lifecycle_sub_sid is not None
                            await ws.update_subscription(ticker_sub_sid, tickers_list)
                            await ws.update_subscription(lifecycle_sub_sid, tickers_list)
                        subscribed_tickers.update(to_add)
                        n = len(to_add)
                        total = len(subscribed_tickers)
                        log.info(f"WS: subscribed to {n} new tickers ({total} total)")
                    except Exception as e:
                        log.warning(f"WS subscribe error: {e}")

                # D-14: compute max_bet_cents ONCE per scan iteration.
                # Reused for both place_bet (via scan_kalshi_with_espn)
                # and evaluate_strategies. NO second balance fetch.
                try:
                    balance_data = await client.get_balance()
                    available_cash = balance_data.get("balance", 0)
                except Exception as e:
                    log.warning(f"Failed to fetch balance for bet sizing: {e}")
                    available_cash = 0
                max_bet_cents = int(available_cash * (cur_bet_percent / 100.0))

                # Now evaluate using real-time prices from WS
                await scan_kalshi_with_espn(
                    client,
                    current_espn,
                    cur_price,
                    max_bet_cents,
                    dry_run,
                )

                # Phase 3 D-04: per-tick strategy evaluation. Reuses
                # max_bet_cents from above (D-14 — same value the
                # live-trade path just used).
                eval_session = get_session()
                try:
                    await evaluate_strategies(eval_session, current_espn_fp, max_bet_cents)
                finally:
                    eval_session.close()

                # Settlement checks as fallback (WS lifecycle handles most)
                await check_settlements(client)
                await record_balance(client)
            except Exception as e:
                log.warning(f"Kalshi scan error: {e}")

            await asyncio.sleep(kalshi_interval)

    async def ws_loop():
        """Maintain WebSocket connection and listen for events."""
        while True:
            try:
                await ws.connect()
                await ws.listen()
            except Exception as e:
                log.warning(f"WS loop error: {e}, restarting in 5s...")
                await asyncio.sleep(5)

    async def backup_loop():
        """Back up DB to S3 every 30 minutes."""
        while True:
            await asyncio.sleep(1800)  # 30 min
            await backup_db()

    # Run all loops concurrently
    await asyncio.gather(espn_loop(), kalshi_scan_loop(), ws_loop(), backup_loop())


if __name__ == "__main__":
    min_price = int(os.getenv("MIN_YES_PRICE", "88"))
    bet_percent = float(os.getenv("BET_PERCENT", "5.0"))
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    dry = os.getenv("DRY_RUN", "true").lower() == "true"

    log.info(
        f"Starting scanner: min_price={min_price}c, bet_percent={bet_percent}%, "
        f"ESPN=10s, Kalshi=5s, dry_run={dry}"
    )
    asyncio.run(
        run_scanner(
            min_yes_price=min_price,
            bet_percent=bet_percent,
            poll_interval=interval,
            dry_run=dry,
        )
    )
