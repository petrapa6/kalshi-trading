"""FastAPI backend serving dashboard data and live game tracking."""

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import desc, func

from predictions.db import (
    BalanceSnapshot,
    Opportunity,
    Scan,
    StretchOpportunity,
    Trade,
    get_all_config,
    get_session,
    init_db,
    set_config,
)
from predictions.espn import (
    KALSHI_TO_ESPN,
    SPORT_FINAL_PERIOD,
    get_scoreboard,
    match_kalshi_to_espn,
)
from predictions.kalshi_client import KalshiClient, extract_cents, extract_volume
from predictions.scanner import MIN_SCORE_LEAD

# --- Pydantic response models ---


class StatsResponse(BaseModel):
    total_trades: int
    live_trades: int
    dry_run_trades: int
    total_cost_cents: int
    total_potential_profit_cents: int
    realized_pnl_cents: int
    total_fees_cents: int
    wins: int
    losses: int
    win_rate: float
    total_scans: int
    total_opportunities: int
    balance_cents: int
    portfolio_value_cents: int
    open_positions: int
    open_cost_cents: int
    open_potential_profit_cents: int


class TradeResponse(BaseModel):
    id: int
    placed_at: Optional[datetime] = None
    ticker: str
    event_ticker: Optional[str] = None
    title: Optional[str] = None
    side: str
    count: int
    yes_price: int
    cost_cents: int
    potential_profit_cents: int
    status: str
    pnl_cents: Optional[int] = None
    dry_run: bool
    error: Optional[str] = None
    espn_clock_seconds: Optional[int] = None


class TradesListResponse(BaseModel):
    trades: list[TradeResponse]


class OpportunityResponse(BaseModel):
    id: int
    found_at: Optional[datetime] = None
    ticker: str
    title: Optional[str] = None
    yes_sub_title: Optional[str] = None
    yes_bid: int
    yes_ask: int
    spread: int
    volume: int
    series_ticker: Optional[str] = None
    sport_path: Optional[str] = None
    espn_period: Optional[int] = None
    espn_clock: Optional[str] = None
    espn_home: Optional[str] = None
    espn_away: Optional[str] = None
    espn_home_score: Optional[int] = None
    espn_away_score: Optional[int] = None
    espn_score_diff: Optional[int] = None


class OpportunitiesListResponse(BaseModel):
    opportunities: list[OpportunityResponse]


class BalanceSnapshotResponse(BaseModel):
    recorded_at: Optional[datetime] = None
    balance_cents: int
    portfolio_value_cents: Optional[int] = None


class BalanceHistoryResponse(BaseModel):
    snapshots: list[BalanceSnapshotResponse]


class ScanResponse(BaseModel):
    id: int
    scanned_at: Optional[datetime] = None
    opportunities_found: int


class ScansListResponse(BaseModel):
    scans: list[ScanResponse]


class StrategySetStats(BaseModel):
    label: str
    total: int
    wins: int
    losses: int
    open: int
    win_rate: float
    hypothetical_pnl_cents: int
    by_reason: dict[str, dict]


class StretchStatsResponse(BaseModel):
    total: int
    wins: int
    losses: int
    open: int
    win_rate: float
    hypothetical_pnl_cents: int
    by_reason: dict[str, dict]
    strategies: dict[str, StrategySetStats]


# --- App ---

log = logging.getLogger(__name__)
_kalshi_client: KalshiClient | None = None


async def _run_scanner_loop():
    """Run the scanner in the background as a native async task."""
    from predictions.scanner import run_scanner

    min_price = int(os.getenv("MIN_YES_PRICE", "88"))
    bet_percent = float(os.getenv("BET_PERCENT", "5.0"))
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))
    dry = os.getenv("DRY_RUN", "true").lower() == "true"

    log.info(
        f"Starting scanner: min_price={min_price}c, "
        f"bet_percent={bet_percent}%, interval={interval}s, dry_run={dry}"
    )
    await run_scanner(
        min_yes_price=min_price,
        bet_percent=bet_percent,
        poll_interval=interval,
        dry_run=dry,
    )


def _download_db():
    bucket = os.getenv("DB_BACKUP_BUCKET")
    db_url = os.getenv("DATABASE_URL", "")
    if not bucket or not db_url.startswith("sqlite:///"):
        return
    db_path = db_url.replace("sqlite:///", "")
    import boto3

    s3 = boto3.client("s3")
    try:
        s3.download_file(bucket, "backups/latest.db", db_path)
        log.info(f"Downloaded latest DB backup from S3 to {db_path}")
    except Exception as e:
        log.warning(f"Could not download DB from S3: {e}")


def _backup_db_sync():
    bucket = os.getenv("DB_BACKUP_BUCKET")
    db_url = os.getenv("DATABASE_URL", "")
    if not bucket or not db_url.startswith("sqlite:///"):
        return
    db_path = db_url.replace("sqlite:///", "")
    if not os.path.exists(db_path):
        return
    from datetime import datetime, timezone

    import boto3

    s3 = boto3.client("s3")
    try:
        now = datetime.now(timezone.utc)
        key = f"backups/{now.strftime('%Y-%m-%d/%H%M')}-predictions.db"
        s3.upload_file(db_path, bucket, key)
        s3.upload_file(db_path, bucket, "backups/latest.db")
        log.info(f"Final DB backup uploaded to S3 ({key})")
    except Exception as e:
        log.warning(f"Final DB backup failed: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _kalshi_client
    _download_db()
    init_db()

    if os.getenv("KALSHI_API_KEY"):
        key_id = os.environ["KALSHI_API_KEY"]
        key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
        if key_pem:
            _kalshi_client = KalshiClient.from_key_string(key_id, key_pem)
        else:
            key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
            _kalshi_client = KalshiClient.from_key_file(key_id, key_path)

        asyncio.create_task(_run_scanner_loop())
    try:
        yield
    finally:
        _backup_db_sync()


app = FastAPI(title="Predictions Dashboard API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]  # starlette typing issue
    allow_origins=[
        "https://matej-kalshi.pp.ua",
        "http://localhost:3777",
        "http://localhost:3000",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)


def _check_token(authorization: str | None = Header(None)):
    """Verify Bearer token for mutable endpoints."""
    expected = os.getenv("API_TOKEN", "")
    if not expected:
        raise HTTPException(403, "API_TOKEN not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    if authorization.removeprefix("Bearer ") != expected:
        raise HTTPException(401, "Invalid token")


@app.get("/")
def health():
    return {"status": "ok"}


@app.get("/api/stats", response_model=StatsResponse, dependencies=[Depends(_check_token)])
def get_stats():
    session = get_session()

    total_trades = session.query(Trade).filter(Trade.status != "error").count()
    live_trades = (
        session.query(Trade).filter(Trade.dry_run == False, Trade.status != "error").count()
    )
    dry_trades = session.query(Trade).filter(Trade.dry_run == True, Trade.status != "error").count()

    total_cost = (
        session.query(func.sum(Trade.cost_cents))
        .filter(Trade.dry_run == False, Trade.status != "error")
        .scalar()
        or 0
    )
    total_potential_profit = (
        session.query(func.sum(Trade.potential_profit_cents))
        .filter(Trade.dry_run == False, Trade.status != "error")
        .scalar()
        or 0
    )
    total_pnl = (
        session.query(func.sum(Trade.pnl_cents)).filter(Trade.pnl_cents.isnot(None)).scalar() or 0
    )

    wins = session.query(Trade).filter(Trade.status == "settled_win").count()
    losses = session.query(Trade).filter(Trade.status == "settled_loss").count()
    settled = wins + losses
    win_rate = (wins / settled * 100) if settled > 0 else 0

    total_scans = session.query(Scan).count()
    total_opportunities = session.query(func.count(func.distinct(Opportunity.ticker))).scalar() or 0

    latest_balance = (
        session.query(BalanceSnapshot).order_by(desc(BalanceSnapshot.recorded_at)).first()
    )
    balance_cents = latest_balance.balance_cents if latest_balance else 0

    recorded_fees = (
        session.query(func.sum(Trade.fee_cents))
        .filter(Trade.fee_cents.isnot(None), Trade.dry_run == False)
        .scalar()
        or 0
    )

    # Old trades did not record fees, so their pnl missed the fee deduction.
    # True net growth of the account = balance_cents - 20000.
    # Therefore, historical unrecorded fees = total_pnl - (balance_cents - 20000).
    total_fees = recorded_fees
    if balance_cents > 0:
        true_pnl = balance_cents - 20000
        unrecorded_fees = total_pnl - true_pnl
        if unrecorded_fees > 0:
            total_fees += unrecorded_fees

    # Open positions (active bets on the line)
    open_trades = (
        session.query(Trade)
        .filter(Trade.status.in_(("placed", "filled")), Trade.dry_run == False)
        .all()
    )
    open_positions = len(open_trades)
    open_cost = sum(t.cost_cents for t in open_trades)
    open_potential = sum(t.potential_profit_cents for t in open_trades)

    session.close()

    return StatsResponse(
        total_trades=total_trades,
        live_trades=live_trades,
        dry_run_trades=dry_trades,
        total_cost_cents=total_cost,
        total_potential_profit_cents=total_potential_profit,
        realized_pnl_cents=total_pnl,
        total_fees_cents=total_fees,
        wins=wins,
        losses=losses,
        win_rate=round(win_rate, 1),
        total_scans=total_scans,
        total_opportunities=total_opportunities,
        balance_cents=balance_cents,
        portfolio_value_cents=latest_balance.portfolio_value_cents if latest_balance else 0,
        open_positions=open_positions,
        open_cost_cents=open_cost,
        open_potential_profit_cents=open_potential,
    )


@app.get("/api/trades", response_model=TradesListResponse, dependencies=[Depends(_check_token)])
def get_trades(limit: int = 50, offset: int = 0):
    session = get_session()
    # Fetch extra trades to account for skipped duplicate errors
    trades = (
        session.query(Trade).order_by(desc(Trade.placed_at)).offset(offset).limit(limit * 10).all()
    )

    seen_error_matches = set()
    result = []
    for t in trades:
        if t.status == "error":
            match_key = t.event_ticker or t.ticker
            if match_key in seen_error_matches:
                continue
            seen_error_matches.add(match_key)

        result.append(
            TradeResponse(
                id=t.id,
                placed_at=t.placed_at,
                ticker=t.ticker,
                event_ticker=t.event_ticker,
                title=t.title,
                side=t.side,
                count=t.count,
                yes_price=t.yes_price,
                cost_cents=t.cost_cents,
                potential_profit_cents=t.potential_profit_cents,
                status=t.status,
                pnl_cents=t.pnl_cents,
                dry_run=t.dry_run,
                error=t.error,
                espn_clock_seconds=t.espn_clock_seconds,
            )
        )
        if len(result) == limit:
            break

    session.close()
    return TradesListResponse(trades=result)


@app.get("/api/histogram-trades", dependencies=[Depends(_check_token)])
def get_histogram_trades(limit: int = 10000):
    session = get_session()
    # Query specific columns to avoid full ORM object overhead and massive JSON payloads
    rows = (
        session.query(
            Trade.id,
            Trade.yes_price,
            Trade.pnl_cents,
            Trade.status,
            Trade.dry_run,
            Trade.espn_clock_seconds,
            Trade.ticker,
            Trade.event_ticker,
            Trade.placed_at,
        )
        .filter(Trade.status.in_(("settled_win", "settled_loss")))
        .filter(Trade.dry_run == False)
        .order_by(desc(Trade.placed_at))
        .limit(limit)
        .all()
    )
    result = [
        {
            "id": r[0],
            "yes_price": r[1],
            "pnl_cents": r[2],
            "status": r[3],
            "dry_run": r[4],
            "espn_clock_seconds": r[5],
            "ticker": r[6],
            "event_ticker": r[7],
            "placed_at": r[8].isoformat()
            if hasattr(r[8], "isoformat")
            else str(r[8])
            if r[8]
            else None,
        }
        for r in rows
    ]
    session.close()
    return {"trades": result}


@app.get("/api/sport-stats", dependencies=[Depends(_check_token)])
def get_total_sport_stats():
    """Aggregates total unique matches seen by the scanner and actual trading PnL by sport."""
    session = get_session()

    # Get all unique matches seen from StretchOpportunities (which tracks all markets reaching final periods)
    # Group by series_ticker and count unique event_tickers
    from sqlalchemy import text

    seen_matches = session.execute(
        text(
            "SELECT series_ticker, COUNT(DISTINCT event_ticker) FROM stretch_opportunities GROUP BY series_ticker"
        )
    ).fetchall()

    # Get actual real-money trades PnL and wins by sport
    # We infer sport from the ticker prefix since Trade lacks sport_path
    real_trades = (
        session.query(Trade.ticker, Trade.status, Trade.pnl_cents)
        .filter(Trade.status.in_(("settled_win", "settled_loss")))
        .filter(Trade.dry_run == False)
        .all()
    )

    session.close()

    stats: dict[str, dict] = {}

    def _add(sport: str):
        if sport not in stats:
            stats[sport] = {"played": 0, "wins": 0, "pnl": 0}

    # Helper to map kalshi ticker prefix to label — most specific match first
    ticker_prefix_map = [
        ("KXMLBST", "MLBST"),
        ("KXMLB", "MLB"),
        ("KXNBA", "NBA"),
        ("KXNHL", "NHL"),
        ("KXNFL", "NFL"),
        ("KXNCAAMB", "NCAAMB"),
        ("KXNCAAFB", "NCAAFB"),
        ("KXEPL", "EPL"),
        ("KXLALIGA", "La Liga"),
        ("KXMLSG", "MLS"),
        ("KXUFC", "UFC"),
    ]

    def get_label_from_ticker(t: str):
        for prefix, label in ticker_prefix_map:
            if t.startswith(prefix):
                return label
        return "Other"

    # Populate played matches
    for series_ticker, count in seen_matches:
        if not series_ticker:
            continue
        label = get_label_from_ticker(series_ticker)
        _add(label)
        stats[label]["played"] += count

    # Populate real PnL
    for t_ticker, t_status, t_pnl in real_trades:
        label = get_label_from_ticker(t_ticker)
        _add(label)
        if t_status == "settled_win":
            stats[label]["wins"] += 1
        stats[label]["pnl"] += t_pnl or 0

    return {"stats": stats}


@app.get(
    "/api/opportunities",
    response_model=OpportunitiesListResponse,
    dependencies=[Depends(_check_token)],
)
def get_opportunities(limit: int = 50, offset: int = 0):
    session = get_session()
    opps = (
        session.query(Opportunity)
        .order_by(desc(Opportunity.found_at))
        .offset(offset)
        .limit(limit)
        .all()
    )
    result = [
        OpportunityResponse(
            id=o.id,
            found_at=o.found_at,
            ticker=o.ticker,
            title=o.title,
            yes_sub_title=o.yes_sub_title,
            yes_bid=o.yes_bid,
            yes_ask=o.yes_ask,
            spread=o.spread,
            volume=o.volume,
            series_ticker=o.series_ticker,
        )
        for o in opps
    ]
    session.close()
    return OpportunitiesListResponse(opportunities=result)


@app.get(
    "/api/balance-history",
    response_model=BalanceHistoryResponse,
    dependencies=[Depends(_check_token)],
)
def get_balance_history(limit: int = 500):
    session = get_session()
    # Get the most recent snapshots (descending), then reverse for chronological order
    snapshots = (
        session.query(BalanceSnapshot)
        .order_by(desc(BalanceSnapshot.recorded_at))
        .limit(limit)
        .all()
    )
    snapshots.reverse()

    # Downsample: keep first, last, and any where balance/portfolio changed
    if len(snapshots) > 2:
        filtered = [snapshots[0]]
        for s in snapshots[1:-1]:
            prev = filtered[-1]
            if (
                s.balance_cents != prev.balance_cents
                or s.portfolio_value_cents != prev.portfolio_value_cents
            ):
                filtered.append(s)
        filtered.append(snapshots[-1])
        snapshots = filtered

    result = [
        BalanceSnapshotResponse(
            recorded_at=s.recorded_at,
            balance_cents=s.balance_cents,
            portfolio_value_cents=s.portfolio_value_cents,
        )
        for s in snapshots
    ]
    session.close()
    return BalanceHistoryResponse(snapshots=result)


@app.get("/api/scans", response_model=ScansListResponse, dependencies=[Depends(_check_token)])
def get_scans(limit: int = 50):
    session = get_session()
    scans = session.query(Scan).order_by(desc(Scan.scanned_at)).limit(limit).all()
    result = [
        ScanResponse(
            id=s.id,
            scanned_at=s.scanned_at,
            opportunities_found=s.opportunities_found,
        )
        for s in scans
    ]
    session.close()
    return ScansListResponse(scans=result)


async def _get_live_games() -> list[dict]:
    """Fetch all live games across all sports from ESPN, enriched with Kalshi prices."""
    all_games = []

    # Fetch Kalshi markets for all sports series in parallel
    kalshi_markets: dict[str, list[dict]] = {}
    if _kalshi_client:
        client = _kalshi_client

        async def fetch_kalshi(series_ticker: str):
            try:
                data = await client.get_events(
                    status="open",
                    series_ticker=series_ticker,
                    with_nested_markets=True,
                )
                return series_ticker, data.get("events", [])
            except Exception:
                return series_ticker, []

        kalshi_results = await asyncio.gather(*(fetch_kalshi(s) for s in KALSHI_TO_ESPN))
        for series, events in kalshi_results:
            kalshi_markets[series] = events

    # Deduplicate sport paths (e.g. KXMLBGAME and KXMLBSTGAME both map to baseball/mlb)
    seen_sport_paths: set[str] = set()
    unique_sports: list[tuple[str, str]] = []  # (series, sport_path)
    # Collect all series per sport_path for Kalshi market matching
    series_by_sport: dict[str, list[str]] = {}
    for series, sport_path in KALSHI_TO_ESPN.items():
        series_by_sport.setdefault(sport_path, []).append(series)
        if sport_path not in seen_sport_paths:
            seen_sport_paths.add(sport_path)
            unique_sports.append((series, sport_path))

    # Fetch ESPN scoreboards in parallel
    async def fetch_espn(s_path: str, p_series: str):
        games = await get_scoreboard(s_path)
        return s_path, p_series, games

    espn_results = await asyncio.gather(
        *(fetch_espn(path, series) for series, path in unique_sports)
    )

    for sport_path, _primary_series, games in espn_results:
        for g in games:
            if g.state != "in":
                continue

            min_lead = MIN_SCORE_LEAD.get(sport_path, 5)
            meets_score_lead = g.score_diff >= min_lead
            is_target = g.is_in_final_minutes and meets_score_lead
            is_watching = (
                not is_target
                and g.state == "in"
                and (g.is_in_final_minutes or meets_score_lead or g.is_final_period)
            )

            # Check if we have an active trade on this event
            has_bet = False
            session = get_session()
            for series in series_by_sport[sport_path]:
                bet_count = (
                    session.query(Trade)
                    .filter(
                        Trade.event_ticker.like(f"{series}%"),
                        Trade.status.in_(("placed", "filled")),
                    )
                    .all()
                )
                for t in bet_count:
                    if (
                        g.home_team.upper() in (t.event_ticker or "").upper()
                        or g.away_team.upper() in (t.event_ticker or "").upper()
                    ):
                        has_bet = True
                        break
                if has_bet:
                    break
            session.close()

            game_data: dict = {
                "espn_id": g.espn_id,
                "sport": sport_path,
                "series": _primary_series,
                "home_team": g.home_team,
                "away_team": g.away_team,
                "home_score": g.home_score,
                "away_score": g.away_score,
                "period": g.period,
                "display_clock": g.display_clock,
                "clock_seconds": g.clock_seconds,
                "state": g.state,
                "is_final_minutes": g.is_in_final_minutes,
                "is_target": is_target,
                "is_watching": is_watching,
                "has_bet": has_bet,
                "score_diff": g.score_diff,
                "min_score_lead": min_lead,
                "final_period": g.final_period,
                "kalshi_markets": [],
            }

            # Match Kalshi markets from ALL series for this sport
            seen_tickers: set[str] = set()
            for series in series_by_sport[sport_path]:
                for event in kalshi_markets.get(series, []):
                    title = event.get("title", "")
                    for market in event.get("markets", []):
                        ticker = market.get("ticker", "")
                        if ticker in seen_tickers:
                            continue
                        if market.get("status") not in ("active", "open"):
                            continue
                        matched = match_kalshi_to_espn(ticker, title, [g])
                        if matched:
                            kalshi_code = ticker.split("-")[-1].upper() if "-" in ticker else ""
                            from predictions.espn import _espn_to_kalshi_codes

                            espn_team = ""
                            for team in (g.home_team, g.away_team):
                                if kalshi_code in [c.upper() for c in _espn_to_kalshi_codes(team)]:
                                    espn_team = team
                                    break
                            game_data["kalshi_markets"].append(
                                {
                                    "ticker": ticker,
                                    "team": espn_team,
                                    "yes_sub_title": market.get("yes_sub_title", ""),
                                    "yes_bid": extract_cents(market, "yes_bid"),
                                    "yes_ask": extract_cents(market, "yes_ask"),
                                    "volume": extract_volume(market),
                                }
                            )
                            seen_tickers.add(ticker)

            all_games.append(game_data)
    return all_games


@app.get("/api/live-games", dependencies=[Depends(_check_token)])
async def get_live_games():
    return {"games": await _get_live_games()}


def _compute_stretch_stats(stretches: list) -> dict:
    """Compute stats for a list of stretch opportunities."""
    total = len(stretches)
    wins = sum(1 for s in stretches if s.status == "settled_win")
    losses = sum(1 for s in stretches if s.status == "settled_loss")
    open_count = sum(1 for s in stretches if s.status == "open")
    settled = wins + losses
    win_rate = (wins / settled * 100) if settled > 0 else 0
    hyp_pnl = sum(s.pnl_cents or 0 for s in stretches)

    by_reason: dict[str, dict] = {}
    for s in stretches:
        for reason in (s.reason or "unknown").split(","):
            reason = reason.strip()
            if reason not in by_reason:
                by_reason[reason] = {"total": 0, "wins": 0, "losses": 0, "pnl_cents": 0}
            by_reason[reason]["total"] += 1
            if s.status == "settled_win":
                by_reason[reason]["wins"] += 1
            elif s.status == "settled_loss":
                by_reason[reason]["losses"] += 1
            by_reason[reason]["pnl_cents"] += s.pnl_cents or 0

    return {
        "total": total,
        "wins": wins,
        "losses": losses,
        "open": open_count,
        "win_rate": round(win_rate, 1),
        "hypothetical_pnl_cents": hyp_pnl,
        "by_reason": by_reason,
    }


@app.get(
    "/api/stretch-stats", response_model=StretchStatsResponse, dependencies=[Depends(_check_token)]
)
def get_stretch_stats():
    from predictions.scanner import WHAT_IF_STRATEGIES

    session = get_session()
    # Query specific columns only to avoid loading 10K+ full ORM objects
    rows = session.query(
        StretchOpportunity.status,
        StretchOpportunity.pnl_cents,
        StretchOpportunity.reason,
        StretchOpportunity.strategy_set,
    ).all()

    # Reconstruct into lightweight namedtuple-like structs for fast stats computing
    from collections import namedtuple

    SData = namedtuple("SData", ["status", "pnl_cents", "reason", "strategy_set"])
    all_stretches = [SData(r[0], r[1], r[2], r[3]) for r in rows]

    # Overall stats (all strategy sets combined)
    overall = _compute_stretch_stats(all_stretches)

    # Per-strategy stats
    by_strategy: dict[str, list] = {}
    for s in all_stretches:
        strat = s.strategy_set or "default"
        by_strategy.setdefault(strat, []).append(s)

    strategies = {}
    # Always include all defined strategies even if empty
    for name, cfg in WHAT_IF_STRATEGIES.items():
        strat_stretches = by_strategy.get(name, [])
        stats = _compute_stretch_stats(strat_stretches)
        strategies[name] = StrategySetStats(
            label=str(cfg["label"]),
            **stats,
        )

    # Include "default" (the original stretch set) if it has data
    if "default" in by_strategy:
        stats = _compute_stretch_stats(by_strategy["default"])
        strategies["default"] = StrategySetStats(
            label="Default (near-miss)",
            **stats,
        )

    session.close()
    return StretchStatsResponse(
        **overall,
        strategies=strategies,
    )


@app.delete("/api/stretch", dependencies=[Depends(_check_token)])
def clear_stretch_opportunities():
    """Wipe all shadow tracking history remotely."""
    try:
        session = get_session()
        session.query(StretchOpportunity).delete()
        session.commit()
        session.close()
        log.info("Shadow statistics wiped remotely via API.")
        return {"status": "ok", "message": "Shadow statistics wiped."}
    except Exception as e:
        log.error(f"Failed to wipe stretch opportunities: {e}")
        from fastapi import HTTPException

        raise HTTPException(status_code=500, detail="Failed to clear shadow opportunities")


@app.delete("/api/config", dependencies=[Depends(_check_token)])
def reset_config_endpoint():
    """Wipe all DB config overrides remotely, reverting to db.py defaults."""
    from predictions.db import reset_all_config

    reset_all_config()
    log.info("All config overrides wiped remotely via API.")
    return {"status": "ok", "message": "Config reset to defaults."}


SPORT_DISPLAY_NAMES = {
    "basketball/nba": "NBA",
    "basketball/mens-college-basketball": "NCAAMB",
    "hockey/nhl": "NHL",
    "football/nfl": "NFL",
    "football/college-football": "NCAAFB",
    "baseball/mlb": "MLB",
    "soccer/eng.1": "EPL",
    "soccer/esp.1": "La Liga",
    "soccer/usa.1": "MLS",
    "mma/ufc": "UFC",
}

# Clock direction per sport: "down" = countdown, "up" = counts up, "none" = no clock
SPORT_CLOCK_DIR = {
    "basketball/nba": "down",
    "basketball/mens-college-basketball": "down",
    "hockey/nhl": "down",
    "football/nfl": "down",
    "football/college-football": "down",
    "baseball/mlb": "none",
    "soccer/eng.1": "up",
    "soccer/esp.1": "up",
    "soccer/usa.1": "up",
    "mma/ufc": "down",
}


def _format_final_minutes(clock_dir: str, secs: int) -> str:
    if clock_dir == "none":
        return "final period"
    if clock_dir == "up":
        return f"{secs // 60}th minute"
    mins = secs // 60
    remainder = secs % 60
    return f"{mins}:{remainder:02d} remaining"


@app.get("/api/config", dependencies=[Depends(_check_token)])
def get_config_endpoint():
    cfg = get_all_config()
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    sports = []
    for sport_path, kalshi_series in sorted([(v, k) for k, v in KALSHI_TO_ESPN.items()]):
        clock_dir = SPORT_CLOCK_DIR.get(sport_path, "down")
        final_secs = int(cfg.get(f"final_seconds:{sport_path}", "0"))
        if not final_secs:
            final_secs = 4500 if clock_dir == "up" else 300
        lead = int(cfg.get(f"lead:{sport_path}", "0"))
        if not lead and sport_path in MIN_SCORE_LEAD:
            lead = MIN_SCORE_LEAD[sport_path]
        stretch_lead = max(1, lead - (lead * 4 // 10))

        sports.append(
            {
                "sport_path": sport_path,
                "name": SPORT_DISPLAY_NAMES.get(sport_path, sport_path),
                "kalshi_series": kalshi_series,
                "final_period": SPORT_FINAL_PERIOD.get(sport_path, 4),
                "min_score_lead": lead,
                "stretch_score_lead": stretch_lead,
                "clock_direction": clock_dir,
                "final_minutes_desc": _format_final_minutes(clock_dir, final_secs),
                "final_minutes_seconds": (None if clock_dir == "none" else final_secs),
            }
        )

    return {
        "trading": {
            "min_yes_price": int(cfg.get("min_yes_price", "92")),
            "bet_percent": int(cfg.get("bet_percent", "5")),
            "max_positions": int(cfg.get("max_positions", "20")),
            "min_volume": int(cfg.get("min_volume", "50")),
            "dry_run": dry_run,
            "paused": cfg.get("trading_paused", "false") == "true",
        },
        "stretch": {
            "price_min": int(cfg.get("stretch_price_min", "85")),
        },
        "polling": {
            "espn_interval_s": 10,
            "kalshi_scan_interval_s": 5,
            "kalshi_ws": True,
            "db_backup_interval_s": 1800,
        },
        "sports": sports,
    }


class ConfigUpdate(BaseModel):
    key: str
    value: str


@app.put("/api/config", dependencies=[Depends(_check_token)])
def update_config(body: ConfigUpdate):
    set_config(body.key, body.value)
    return {"ok": True, "key": body.key, "value": body.value}
