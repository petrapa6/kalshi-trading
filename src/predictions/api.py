"""FastAPI backend serving dashboard data and live game tracking."""

import asyncio
import logging
import os
import tempfile
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

import yaml
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sqlalchemy import case, desc, func

from predictions import backtest as backtest_mod
from predictions.backtest import BacktestRequest, BacktestResponse
from predictions.db import (
    BalanceSnapshot,
    Opportunity,
    Scan,
    Trade,
    dry_run_enabled,
    get_all_config,
    get_final_seconds_thresholds,
    get_session,
    init_db,
    set_config,
)
from predictions.espn import (
    get_scoreboard,
    is_in_final_minutes,
    match_kalshi_to_espn,
)
from predictions.kalshi_client import KalshiClient, extract_cents, extract_volume
from predictions.sports import (
    KALSHI_TO_ESPN,
    SPORT_BY_PATH,
    SPORT_CLOCK_DIR,
    SPORT_DISPLAY_NAMES,
    SPORT_FINAL_PERIOD,
    TICKER_PREFIX_LABELS,
)
from predictions.strategies import load_strategies, parse_strategies_text

# --- Pydantic response models ---


class PopulationStats(BaseModel):
    trades: int
    wins: int
    losses: int
    win_rate: float
    realized_pnl_cents: int
    total_cost_cents: int
    total_potential_profit_cents: int
    total_fees_cents: int
    open_positions: int
    open_cost_cents: int
    open_potential_profit_cents: int


class StatsResponse(BaseModel):
    live: PopulationStats
    dry_run: PopulationStats
    balance_cents: int
    portfolio_value_cents: int
    total_scans: int
    total_opportunities: int


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
    strategy_name: Optional[str] = None


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


class TriggerResponse(BaseModel):
    sport: Optional[str] = None
    sport_path: Optional[str] = None
    min_minute: Optional[int] = None
    min_lead: Optional[int] = None
    final_minutes: Optional[bool] = None
    min_volume: Optional[int] = None
    min_yes_price: Optional[int] = None
    max_yes_price: Optional[int] = None


class StrategyResponse(BaseModel):
    name: str
    description: Optional[str] = None
    triggers: list[TriggerResponse]


class StrategiesResponse(BaseModel):
    strategies: list[StrategyResponse]


class StrategyRawResponse(BaseModel):
    content: str


class StrategyRawUpdate(BaseModel):
    content: str


class RawStrategyEntry(BaseModel):
    name: str
    live: bool
    description: Optional[str] = None
    triggers: list[TriggerResponse]


class StrategyRawSaveResponse(BaseModel):
    strategies: list[RawStrategyEntry]


class StrategyAnalyticsStats(BaseModel):
    total_trades: int
    wins: int
    losses: int
    open_trades: int
    win_rate: float
    realized_pnl_cents: int


class StrategyAnalyticsTrade(BaseModel):
    id: int
    placed_at: Optional[datetime] = None
    settled_at: Optional[datetime] = None
    ticker: str
    yes_price: int
    count: int
    cost_cents: int
    pnl_cents: Optional[int] = None
    status: str


class StrategyAnalyticsPnlPoint(BaseModel):
    x: Optional[datetime] = None
    y: int
    ticker: str
    trade_pnl: int


class StrategyAnalyticsResponse(BaseModel):
    stats: StrategyAnalyticsStats
    trades: list[StrategyAnalyticsTrade]
    pnl_curve: list[StrategyAnalyticsPnlPoint]


class StrategySummaryEntry(BaseModel):
    name: str
    total_trades: int
    wins: int
    losses: int
    pnl_cents: int


class StrategiesSummaryResponse(BaseModel):
    strategies: list[StrategySummaryEntry]


# --- App ---

log = logging.getLogger(__name__)
_kalshi_client: KalshiClient | None = None


async def _run_scanner_loop():
    """Run the scanner in the background as a native async task."""
    from predictions.scanner import run_scanner

    bet_percent = float(os.getenv("BET_PERCENT", "5.0"))
    interval = int(os.getenv("POLL_INTERVAL_SECONDS", "30"))

    log.info(
        f"Starting scanner: bet_percent={bet_percent}%, "
        f"interval={interval}s (dry-run mode via DB config)"
    )
    await run_scanner(
        bet_percent=bet_percent,
        poll_interval=interval,
    )


@asynccontextmanager
async def lifespan(_app: FastAPI):
    global _kalshi_client
    init_db()
    # Soccer cache is independent: own engine + DB. The cache is ephemeral
    # (rebuilds on each container start) per the spec's deferred "Persistent
    # cache" follow-up. Without this init, /api/backtest/soccer crashes on
    # first request.
    from predictions.soccer_cache import init_soccer_db

    init_soccer_db()

    if os.getenv("KALSHI_API_KEY"):
        key_id = os.environ["KALSHI_API_KEY"]
        key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
        if key_pem:
            _kalshi_client = KalshiClient.from_key_string(key_id, key_pem)
        else:
            key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH", "")
            _kalshi_client = KalshiClient.from_key_file(key_id, key_path)

        asyncio.create_task(_run_scanner_loop())
    yield


app = FastAPI(title="Predictions Dashboard API", lifespan=lifespan)
_cors_extra = [o.strip() for o in os.getenv("CORS_ORIGINS", "").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,  # type: ignore[arg-type]  # starlette typing issue
    allow_origins=[
        "http://localhost:3777",
        "http://localhost:3000",
        *_cors_extra,
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


# Canonical open-trade statuses: a position is open once placed (live sits in
# placed/filled, dry-run in dry_run) until it settles or errors. Mirrors the
# scanner's open-trade filter.
_OPEN_STATUSES = ("placed", "filled", "dry_run")


def _population_stats(session) -> dict[bool, PopulationStats]:
    """Aggregate both Trade populations in a single grouped pass, keyed by
    dry_run. Non-error rows count as trades; open positions are the canonical
    open statuses; fees only count rows that recorded a fee_cents (pre-tracking
    rows are NULL, not inferred). Missing populations default to all-zero.
    """
    non_error = Trade.status != "error"
    is_open = Trade.status.in_(_OPEN_STATUSES)

    rows = (
        session.query(
            Trade.dry_run,
            func.sum(case((non_error, 1), else_=0)),
            func.sum(case((Trade.status == "settled_win", 1), else_=0)),
            func.sum(case((Trade.status == "settled_loss", 1), else_=0)),
            func.sum(case((Trade.pnl_cents.isnot(None), Trade.pnl_cents), else_=0)),
            func.sum(case((non_error, Trade.cost_cents), else_=0)),
            func.sum(case((non_error, Trade.potential_profit_cents), else_=0)),
            func.sum(case((Trade.fee_cents.isnot(None), Trade.fee_cents), else_=0)),
            func.sum(case((is_open, 1), else_=0)),
            func.sum(case((is_open, Trade.cost_cents), else_=0)),
            func.sum(case((is_open, Trade.potential_profit_cents), else_=0)),
        )
        .group_by(Trade.dry_run)
        .all()
    )

    stats = {is_dry: _empty_population() for is_dry in (False, True)}
    for row in rows:
        (
            is_dry,
            trades,
            wins,
            losses,
            realized_pnl,
            total_cost,
            total_potential,
            total_fees,
            open_positions,
            open_cost,
            open_potential,
        ) = row
        settled = wins + losses
        win_rate = round(wins / settled * 100, 1) if settled > 0 else 0.0
        stats[bool(is_dry)] = PopulationStats(
            trades=trades,
            wins=wins,
            losses=losses,
            win_rate=win_rate,
            realized_pnl_cents=realized_pnl or 0,
            total_cost_cents=total_cost or 0,
            total_potential_profit_cents=total_potential or 0,
            total_fees_cents=total_fees or 0,
            open_positions=open_positions,
            open_cost_cents=open_cost or 0,
            open_potential_profit_cents=open_potential or 0,
        )
    return stats


def _empty_population() -> PopulationStats:
    return PopulationStats(
        trades=0,
        wins=0,
        losses=0,
        win_rate=0.0,
        realized_pnl_cents=0,
        total_cost_cents=0,
        total_potential_profit_cents=0,
        total_fees_cents=0,
        open_positions=0,
        open_cost_cents=0,
        open_potential_profit_cents=0,
    )


@app.get("/api/stats", response_model=StatsResponse, dependencies=[Depends(_check_token)])
def get_stats():
    session = get_session()

    populations = _population_stats(session)
    live = populations[False]
    dry_run = populations[True]

    total_scans = session.query(Scan).count()
    total_opportunities = session.query(func.count(func.distinct(Opportunity.ticker))).scalar() or 0

    latest_balance = (
        session.query(BalanceSnapshot).order_by(desc(BalanceSnapshot.recorded_at)).first()
    )

    session.close()

    return StatsResponse(
        live=live,
        dry_run=dry_run,
        balance_cents=latest_balance.balance_cents if latest_balance else 0,
        portfolio_value_cents=latest_balance.portfolio_value_cents if latest_balance else 0,
        total_scans=total_scans,
        total_opportunities=total_opportunities,
    )


@app.get(
    "/api/strategies",
    response_model=StrategiesResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(_check_token)],
)
def get_strategies():
    strategies = load_strategies()
    return StrategiesResponse(
        strategies=[
            StrategyResponse(
                name=s.name,
                description=s.description,
                triggers=[TriggerResponse(**t.model_dump()) for t in s.triggers],
            )
            for s in strategies
        ]
    )


def _strategies_path() -> str:
    return os.getenv("STRATEGIES_PATH", "strategies.yaml")


@app.get(
    "/api/strategies/raw",
    response_model=StrategyRawResponse,
    dependencies=[Depends(_check_token)],
)
def get_strategies_raw():
    """Raw catalog file text for the dashboard editor. Missing file → empty."""
    try:
        with open(_strategies_path(), encoding="utf-8") as f:
            content = f.read()
    except FileNotFoundError:
        content = ""
    return StrategyRawResponse(content=content)


@app.put(
    "/api/strategies/raw",
    response_model=StrategyRawSaveResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(_check_token)],
)
def put_strategies_raw(body: StrategyRawUpdate):
    """Validate submitted catalog text, then atomically replace the file.

    Validation runs first: on any error the running file is left untouched
    and the loader's message is returned verbatim (422). On success the file
    is written temp-file-then-rename so a concurrent scan tick never reads a
    half-written catalog; the next tick re-reads it (hot reload, ADR-0002).
    """
    try:
        # ValidationError subclasses ValueError, so this covers schema
        # violations, empty documents, and malformed/unsafe YAML.
        strategies = parse_strategies_text(body.content)
    except (yaml.YAMLError, ValueError) as e:
        raise HTTPException(status_code=422, detail=str(e))

    path = _strategies_path()
    dir_ = os.path.dirname(os.path.abspath(path))
    fd, tmp = tempfile.mkstemp(dir=dir_, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(body.content)
        os.replace(tmp, path)
    except BaseException:
        os.unlink(tmp)
        raise

    return StrategyRawSaveResponse(
        strategies=[
            RawStrategyEntry(
                name=s.name,
                live=s.live,
                description=s.description,
                triggers=[TriggerResponse(**t.model_dump()) for t in s.triggers],
            )
            for s in strategies
        ]
    )


@app.get(
    "/api/strategy-analytics",
    response_model=StrategyAnalyticsResponse,
    dependencies=[Depends(_check_token)],
)
def get_strategy_analytics(strategy: str):
    """Per-strategy analytics for the dashboard /analytics page.

    DASH-03 / D-04: returns stat aggregates, full trade log (newest first),
    and a per-trade-step running P&L curve over settled trades.
    """
    session = get_session()

    strategy_filter = Trade.strategy_name == strategy

    total = session.query(Trade).filter(strategy_filter).count()
    wins = session.query(Trade).filter(strategy_filter, Trade.status == "settled_win").count()
    losses = session.query(Trade).filter(strategy_filter, Trade.status == "settled_loss").count()
    open_trades = (
        session.query(Trade).filter(strategy_filter, Trade.status.in_(_OPEN_STATUSES)).count()
    )
    settled = wins + losses
    win_rate = round(wins / settled * 100, 1) if settled > 0 else 0.0

    realized_pnl = (
        session.query(func.sum(Trade.pnl_cents))
        .filter(strategy_filter, Trade.pnl_cents.isnot(None))
        .scalar()
        or 0
    )

    # Trade log — newest first
    trade_rows = session.query(Trade).filter(strategy_filter).order_by(desc(Trade.placed_at)).all()
    trades = [
        StrategyAnalyticsTrade(
            id=t.id,
            placed_at=t.placed_at,
            settled_at=t.settled_at,
            ticker=t.ticker,
            yes_price=t.yes_price,
            count=t.count,
            cost_cents=t.cost_cents,
            pnl_cents=t.pnl_cents,
            status=t.status,
        )
        for t in trade_rows
    ]

    # P&L curve — settled only, oldest first, running sum in Python
    # (D-05: SQLite version-dependent window functions; do not use SQL).
    settled_rows = (
        session.query(Trade)
        .filter(
            strategy_filter,
            Trade.status.in_(("settled_win", "settled_loss")),
        )
        .order_by(Trade.settled_at)
        .all()
    )
    pnl_curve: list[StrategyAnalyticsPnlPoint] = []
    running = 0
    for t in settled_rows:
        # Pitfall 5: skip rows where settled_at is NULL — never plot a point
        # with x=None (recharts silently misplaces it).
        if t.settled_at is None:
            continue
        trade_pnl = t.pnl_cents or 0
        running += trade_pnl
        pnl_curve.append(
            StrategyAnalyticsPnlPoint(
                x=t.settled_at,
                y=running,
                ticker=t.ticker,
                trade_pnl=trade_pnl,
            )
        )

    session.close()
    return StrategyAnalyticsResponse(
        stats=StrategyAnalyticsStats(
            total_trades=total,
            wins=wins,
            losses=losses,
            open_trades=open_trades,
            win_rate=win_rate,
            realized_pnl_cents=realized_pnl,
        ),
        trades=trades,
        pnl_curve=pnl_curve,
    )


@app.get(
    "/api/strategies-summary",
    response_model=StrategiesSummaryResponse,
    dependencies=[Depends(_check_token)],
)
def get_strategies_summary():
    """Per-strategy mini-stats for the analytics sidebar.

    DASH-03 / D-06: returns one entry per strategy (totals/wins/losses/
    pnl_cents). YAML strategies with zero trades are included with
    all-zero stats (D-11) by merging load_strategies() with the DB
    GROUP BY result. Orphaned DB-only strategies (rows whose strategy_name
    is no longer in YAML) are appended so their historical data stays
    visible.
    """
    session = get_session()

    filter_expr = Trade.strategy_name.isnot(None)

    rows = (
        session.query(
            Trade.strategy_name,
            func.count(Trade.id),
            func.sum(case((Trade.status == "settled_win", 1), else_=0)),
            func.sum(case((Trade.status == "settled_loss", 1), else_=0)),
            func.sum(case((Trade.pnl_cents.isnot(None), Trade.pnl_cents), else_=0)),
        )
        .filter(filter_expr)
        .group_by(Trade.strategy_name)
        .all()
    )
    session.close()

    db_by_name: dict[str, dict] = {}
    for name, total, wins, losses, pnl in rows:
        db_by_name[name] = {
            "name": name,
            "total_trades": int(total or 0),
            "wins": int(wins or 0),
            "losses": int(losses or 0),
            "pnl_cents": int(pnl or 0),
        }

    # Merge with YAML — YAML strategies first in YAML order; orphans appended.
    yaml_strategies = load_strategies()
    result: list[StrategySummaryEntry] = []
    seen: set[str] = set()
    for s in yaml_strategies:
        agg = db_by_name.get(
            s.name,
            {
                "name": s.name,
                "total_trades": 0,
                "wins": 0,
                "losses": 0,
                "pnl_cents": 0,
            },
        )
        result.append(StrategySummaryEntry(**agg))
        seen.add(s.name)
    for name, agg in db_by_name.items():
        if name in seen:
            continue
        result.append(StrategySummaryEntry(**agg))

    return StrategiesSummaryResponse(strategies=result)


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
                strategy_name=t.strategy_name,
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
            Trade.settled_at,
            Trade.strategy_name,
        )
        # Both populations: the dashboard filters live vs dry-run client-side
        # (issue #16). Charts that want live-only re-filter on dry_run.
        .filter(Trade.status.in_(("settled_win", "settled_loss")))
        .order_by(desc(Trade.placed_at))
        .limit(limit)
        .all()
    )

    def _iso(dt):
        return dt.isoformat() if hasattr(dt, "isoformat") else str(dt) if dt else None

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
            "placed_at": _iso(r[8]),
            "settled_at": _iso(r[9]),
            "strategy_name": r[10],
        }
        for r in rows
    ]
    session.close()
    return {"trades": result}


@app.get("/api/sport-stats", dependencies=[Depends(_check_token)])
def get_total_sport_stats():
    """Aggregates total unique matches seen by the scanner and actual trading PnL by sport."""
    session = get_session()

    # Phase 3 D-19: source from opportunities table (replacing
    # stretch_opportunities). Behavior change: `played` is now distinct
    # event_tickers seen by the scanner per series — i.e. games scanned,
    # not near-miss rows. Same response shape; aggregation logic below
    # is unchanged.
    from sqlalchemy import text

    seen_matches = session.execute(
        text(
            "SELECT series_ticker, COUNT(DISTINCT event_ticker) "
            "FROM opportunities "
            "WHERE series_ticker IS NOT NULL "
            "GROUP BY series_ticker"
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

    def get_label_from_ticker(t: str):
        for prefix, label in TICKER_PREFIX_LABELS:
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

    thresholds = get_final_seconds_thresholds()
    for sport_path, _primary_series, games in espn_results:
        min_lead = SPORT_BY_PATH[sport_path].default_lead
        for g in games:
            if g.state != "in":
                continue

            meets_score_lead = g.score_diff >= min_lead
            in_final_minutes = is_in_final_minutes(g, thresholds)
            is_target = in_final_minutes and meets_score_lead
            is_watching = (
                not is_target
                and g.state == "in"
                and (in_final_minutes or meets_score_lead or g.is_final_period)
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
                "is_final_minutes": in_final_minutes,
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
                            from predictions.teams import espn_to_kalshi_codes

                            espn_team = ""
                            for team in (g.home_team, g.away_team):
                                if kalshi_code in [c.upper() for c in espn_to_kalshi_codes(team)]:
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


@app.delete("/api/config", dependencies=[Depends(_check_token)])
def reset_config_endpoint():
    """Wipe all DB config overrides remotely, reverting to db.py defaults."""
    from predictions.db import reset_all_config

    reset_all_config()
    log.info("All config overrides wiped remotely via API.")
    return {"status": "ok", "message": "Config reset to defaults."}


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
    dry_run = dry_run_enabled()

    sports = []
    for sport_path, kalshi_series in sorted([(v, k) for k, v in KALSHI_TO_ESPN.items()]):
        clock_dir = SPORT_CLOCK_DIR.get(sport_path, "down")
        final_secs = int(cfg.get(f"final_seconds:{sport_path}", "0")) or (
            SPORT_BY_PATH[sport_path].default_final_seconds or 0
        )

        sports.append(
            {
                "sport_path": sport_path,
                "name": SPORT_DISPLAY_NAMES.get(sport_path, sport_path),
                "kalshi_series": kalshi_series,
                "final_period": SPORT_FINAL_PERIOD.get(sport_path, 4),
                "clock_direction": clock_dir,
                "final_minutes_desc": _format_final_minutes(clock_dir, final_secs),
                "final_minutes_seconds": (None if clock_dir == "none" else final_secs),
            }
        )

    return {
        "trading": {
            "bet_percent": int(cfg.get("bet_percent", "5")),
            "max_positions": int(cfg.get("max_positions", "30")),
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


@app.post(
    "/api/backtest/soccer",
    response_model=BacktestResponse,
    dependencies=[Depends(_check_token)],
)
async def post_backtest_soccer(req: BacktestRequest):
    if not os.getenv("API_FOOTBALL_KEY"):
        raise HTTPException(503, "API_FOOTBALL_KEY is not configured")
    return await backtest_mod.run_backtest(req)
