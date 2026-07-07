import os
from datetime import datetime, timezone

from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import Boolean, Column, DateTime, Integer, String, Text, and_, create_engine, or_
from sqlalchemy.orm import declarative_base, sessionmaker

from predictions.sports import CONFIG_FINAL_SECONDS_DEFAULTS, CONFIG_LEAD_DEFAULTS, SPORTS

# Default SQLite path at the repo root (src/predictions/db.py → repo/predictions.db)
_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_default_db = os.path.join(_repo_root, "predictions.db")
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    f"sqlite:///{_default_db}",
)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 5},
)
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class Scan(Base):
    __tablename__ = "scans"

    id = Column(Integer, primary_key=True)
    scanned_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    opportunities_found = Column(Integer, default=0)


class Opportunity(Base):
    __tablename__ = "opportunities"

    id = Column(Integer, primary_key=True)
    scan_id = Column(Integer, nullable=True)
    # Indexed because backtest.find_observed_yes_ask scans by time-window per
    # match. Without the index, each lookup is O(n) over a table that grows
    # by ~12 rows/min from the live scanner.
    found_at = Column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    ticker = Column(String, index=True)
    event_ticker = Column(String)
    series_ticker = Column(String)
    title = Column(Text)
    yes_sub_title = Column(Text)
    yes_bid = Column(Integer)
    yes_ask = Column(Integer)
    spread = Column(Integer)
    volume = Column(Integer)
    close_time = Column(String)
    # ESPN game state at time of opportunity
    sport_path = Column(String, nullable=True)
    espn_period = Column(Integer, nullable=True)
    espn_clock = Column(String, nullable=True)
    espn_home = Column(String, nullable=True)
    espn_away = Column(String, nullable=True)
    espn_home_score = Column(Integer, nullable=True)
    espn_away_score = Column(Integer, nullable=True)
    espn_score_diff = Column(Integer, nullable=True)


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True)
    placed_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    ticker = Column(String, index=True)
    event_ticker = Column(String)
    title = Column(Text)
    side = Column(String)  # yes/no
    action = Column(String)  # buy/sell
    count = Column(Integer)
    yes_price = Column(Integer)  # cents
    cost_cents = Column(Integer)
    potential_profit_cents = Column(Integer)
    status = Column(String, default="placed")  # placed, filled, settled_win, settled_loss
    settled_at = Column(DateTime, nullable=True)
    pnl_cents = Column(Integer, nullable=True)
    dry_run = Column(Boolean, default=True)
    order_id = Column(String, nullable=True)
    error = Column(Text, nullable=True)
    # ESPN game state at time of trade
    espn_clock_seconds = Column(
        Integer, nullable=True
    )  # seconds remaining (or elapsed for count-up sports)
    fee_cents = Column(Integer, nullable=True)  # trading fees charged by Kalshi
    # Strategy attribution: NULL for legacy real trades + legacy
    # process-level dry-runs (DRY_RUN env). Set to a strategy.name
    # string for dry-run strategy fires (D-13).
    strategy_name = Column(String, nullable=True, index=True)


def countable_trades():
    """SQLAlchemy filter for trades that count: live trades and strategy
    dry-runs. Legacy process-level dry-runs (dry_run=True, strategy_name
    NULL) never count (D-16)."""
    return or_(
        Trade.dry_run == False,
        and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)),
    )


class BalanceSnapshot(Base):
    __tablename__ = "balance_snapshots"

    id = Column(Integer, primary_key=True)
    recorded_at = Column(DateTime, default=lambda: datetime.now(timezone.utc))
    balance_cents = Column(Integer)
    portfolio_value_cents = Column(Integer, nullable=True)


class ConfigEntry(Base):
    """Key-value config store for runtime-tunable parameters."""

    __tablename__ = "config"

    key = Column(String, primary_key=True)
    value = Column(Text, nullable=False)


def init_db():
    Base.metadata.create_all(engine)
    # Add columns that may not exist in older DBs
    _migrate_add_columns()


def _migrate_add_columns():
    """Add columns to existing tables if they don't exist."""
    from sqlalchemy import inspect, text

    inspector = inspect(engine)
    if "trades" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("trades")}
        if "espn_clock_seconds" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN espn_clock_seconds INTEGER"))
        if "fee_cents" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN fee_cents INTEGER"))
        if "strategy_name" not in cols:
            with engine.begin() as conn:
                conn.execute(text("ALTER TABLE trades ADD COLUMN strategy_name VARCHAR"))
                conn.execute(
                    text(
                        "CREATE INDEX IF NOT EXISTS ix_trades_strategy_name "
                        "ON trades (strategy_name)"
                    )
                )

        # Backfill settled_at for historical settled rows. The settlement
        # writer in scanner.py predates this column being read by anyone, so
        # production rows have settled_at IS NULL. The /api/strategy-analytics
        # P&L curve filters NULL settled_at out, which would render every
        # historical strategy as an empty chart until a fresh trade settles.
        # placed_at is the closest available proxy (settle delay is minutes
        # to hours for sports markets). Idempotent: only touches NULL rows.
        with engine.begin() as conn:
            conn.execute(
                text(
                    "UPDATE trades SET settled_at = placed_at "
                    "WHERE settled_at IS NULL "
                    "AND status IN ('settled_win', 'settled_loss')"
                )
            )

    # D-03 — rename legacy WHAT_IF tracking table for archival access.
    # Idempotent: guarded by table-presence; runs once on upgraded DBs,
    # no-op on fresh DBs (where stretch_opportunities never existed)
    # and on subsequent boots (where the rename has already happened).
    # NOTE: pre-deploy gate per STR-04 — test against a current S3
    # backup copy locally before pushing to prod (see 03-CONTEXT.md
    # D-03 + DEPLOY checklist).
    table_names = inspector.get_table_names()
    if (
        "stretch_opportunities" in table_names
        and "stretch_opportunities_archived" not in table_names
    ):
        with engine.begin() as conn:
            conn.execute(
                text("ALTER TABLE stretch_opportunities RENAME TO stretch_opportunities_archived")
            )

    if "opportunities" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("opportunities")}
        espn_cols = {
            "sport_path": "VARCHAR",
            "espn_period": "INTEGER",
            "espn_clock": "VARCHAR",
            "espn_home": "VARCHAR",
            "espn_away": "VARCHAR",
            "espn_home_score": "INTEGER",
            "espn_away_score": "INTEGER",
            "espn_score_diff": "INTEGER",
        }
        with engine.begin() as conn:
            for col_name, col_type in espn_cols.items():
                if col_name not in cols:
                    conn.execute(
                        text(f"ALTER TABLE opportunities ADD COLUMN {col_name} {col_type}")
                    )
            # Backfill the found_at index on older DBs that pre-date the
            # backtest feature. Idempotent thanks to IF NOT EXISTS.
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_opportunities_found_at "
                    "ON opportunities (found_at)"
                )
            )


def get_session():
    return SessionLocal()


# --- Runtime config helpers ---

# Defaults used when no DB override exists
_CONFIG_DEFAULTS: dict[str, str] = {
    "min_yes_price": "91",  # 92
    "bet_percent": "10",  # 5
    "max_positions": "20",
    "min_volume": "50",
    "stretch_price_min": "85",
    "trading_paused": "false",
    # Per-sport defaults (lead:<path>, final_seconds:<path>) come from the
    # sport registry; DB rows override them.
    **CONFIG_LEAD_DEFAULTS,
    **CONFIG_FINAL_SECONDS_DEFAULTS,
}


def get_config(key: str) -> str:
    """Get a config value from DB, falling back to defaults."""
    session = get_session()
    entry = session.query(ConfigEntry).filter_by(key=key).first()
    session.close()
    if entry:
        return entry.value
    return _CONFIG_DEFAULTS.get(key, "")


def get_config_int(key: str) -> int:
    return int(get_config(key) or "0")


def get_final_seconds_thresholds() -> dict[str, int]:
    """final_seconds thresholds per clocked sport_path (DB override or registry default)."""
    return {
        s.path: get_config_int(f"final_seconds:{s.path}") or s.default_final_seconds
        for s in SPORTS
        if s.clock != "none" and s.default_final_seconds is not None
    }


def set_config(key: str, value: str):
    """Set a config value in the DB."""
    session = get_session()
    entry = session.query(ConfigEntry).filter_by(key=key).first()
    if entry:
        entry.value = value
    else:
        session.add(ConfigEntry(key=key, value=value))
    session.commit()
    session.close()


def get_all_config() -> dict[str, str]:
    """Get all config as a dict (defaults merged with DB overrides)."""
    result = dict(_CONFIG_DEFAULTS)
    session = get_session()
    for entry in session.query(ConfigEntry).all():
        result[entry.key] = entry.value
    session.close()
    return result


def reset_all_config():
    """Remove all manual configuration overrides, resetting to defaults."""
    session = get_session()
    session.query(ConfigEntry).delete()
    session.commit()
    session.close()
