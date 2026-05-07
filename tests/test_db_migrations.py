"""Migration tests for Phase 3 schema changes.

Covers D-01 (strategy_name column), D-02 (connect_args timeout),
D-03 (stretch_opportunities → stretch_opportunities_archived rename).

The autouse isolated_db fixture from conftest.py patches predictions.db.engine
with a fresh in-memory SQLite. It calls Base.metadata.create_all(engine) which,
after D-20, does NOT create stretch_opportunities (StretchOpportunity ORM is
gone). Tests that exercise the rename guard must CREATE the table manually
via text() before invoking _migrate_add_columns().
"""

import inspect as _stdlib_inspect

import pytest
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import sessionmaker

import predictions.db as db_module
from predictions.db import _migrate_add_columns


@pytest.fixture
def fresh_engine(monkeypatch):
    """In-memory engine with Base schema created (no stretch_opportunities table).

    Replaces the autouse isolated_db engine so migration tests control
    exactly what tables exist before calling _migrate_add_columns().
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    db_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def test_rename_stretch_opportunities(fresh_engine):
    """D-03: stretch_opportunities is renamed to stretch_opportunities_archived."""
    # Manually create the legacy table (simulates an upgraded DB pre-Phase-3)
    with fresh_engine.begin() as conn:
        conn.execute(text("CREATE TABLE stretch_opportunities (id INTEGER PRIMARY KEY)"))

    _migrate_add_columns()

    inspector = inspect(fresh_engine)
    table_names = inspector.get_table_names()
    assert "stretch_opportunities_archived" in table_names, (
        "stretch_opportunities should be renamed to stretch_opportunities_archived"
    )
    assert "stretch_opportunities" not in table_names, (
        "stretch_opportunities should no longer exist after rename"
    )


def test_rename_idempotent(fresh_engine):
    """D-03: Running _migrate_add_columns() twice does not error."""
    # Manually create the legacy table
    with fresh_engine.begin() as conn:
        conn.execute(text("CREATE TABLE stretch_opportunities (id INTEGER PRIMARY KEY)"))

    # First run — should rename
    _migrate_add_columns()

    # Second run — should be a no-op (stretch_opportunities_archived already exists,
    # stretch_opportunities does not)
    _migrate_add_columns()

    inspector = inspect(fresh_engine)
    table_names = inspector.get_table_names()
    assert "stretch_opportunities_archived" in table_names
    assert "stretch_opportunities" not in table_names


def test_strategy_name_column(fresh_engine):
    """D-01: trades table gains strategy_name VARCHAR column."""
    _migrate_add_columns()

    inspector = inspect(fresh_engine)
    cols = {c["name"] for c in inspector.get_columns("trades")}
    assert "strategy_name" in cols, "strategy_name column must exist on trades table"


def test_strategy_name_index_exists(fresh_engine):
    """D-01: ix_trades_strategy_name index is created on trades (strategy_name)."""
    _migrate_add_columns()

    inspector = inspect(fresh_engine)
    indexes = {idx["name"] for idx in inspector.get_indexes("trades")}
    assert "ix_trades_strategy_name" in indexes, (
        "ix_trades_strategy_name index must exist for Phase 4 analytics filtering"
    )


def test_engine_timeout(isolated_db):
    """D-02: db.py:19 connect_args includes timeout=5."""
    src = _stdlib_inspect.getsource(db_module)
    assert '"timeout": 5' in src, (
        "db.py must include connect_args={'check_same_thread': False, 'timeout': 5}"
    )


def test_backfill_settled_at(fresh_engine):
    """Phase 04 gap closure: historical settled rows get settled_at backfilled
    from placed_at so /api/strategy-analytics renders a P&L curve immediately
    after deploy (the column was never written by the settlement path before).
    """
    from datetime import datetime, timezone

    from predictions.db import Trade

    placed = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    Session = sessionmaker(bind=fresh_engine)
    session = Session()
    session.add_all(
        [
            Trade(
                ticker="KX-WIN",
                event_ticker="KX-WIN",
                status="settled_win",
                pnl_cents=50,
                placed_at=placed,
                settled_at=None,
            ),
            Trade(
                ticker="KX-LOSS",
                event_ticker="KX-LOSS",
                status="settled_loss",
                pnl_cents=-100,
                placed_at=placed,
                settled_at=None,
            ),
            Trade(
                ticker="KX-OPEN",
                event_ticker="KX-OPEN",
                status="placed",
                placed_at=placed,
                settled_at=None,
            ),
        ]
    )
    session.commit()
    session.close()

    _migrate_add_columns()

    session = Session()
    win = session.query(Trade).filter(Trade.ticker == "KX-WIN").one()
    loss = session.query(Trade).filter(Trade.ticker == "KX-LOSS").one()
    open_trade = session.query(Trade).filter(Trade.ticker == "KX-OPEN").one()
    # SQLite strips tzinfo from DateTime columns; compare naive UTC datetimes.
    placed_naive = placed.replace(tzinfo=None)
    assert win.settled_at == placed_naive, "settled_win row must be backfilled to placed_at"
    assert loss.settled_at == placed_naive, "settled_loss row must be backfilled to placed_at"
    assert open_trade.settled_at is None, "non-settled rows must remain NULL"
    session.close()


def test_backfill_settled_at_idempotent(fresh_engine):
    """Backfill must not overwrite already-set settled_at on subsequent runs."""
    from datetime import datetime, timezone

    from predictions.db import Trade

    placed = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    real_settled = datetime(2026, 5, 1, 13, 30, tzinfo=timezone.utc)
    Session = sessionmaker(bind=fresh_engine)
    session = Session()
    session.add(
        Trade(
            ticker="KX-DONE",
            event_ticker="KX-DONE",
            status="settled_win",
            pnl_cents=50,
            placed_at=placed,
            settled_at=real_settled,
        )
    )
    session.commit()
    session.close()

    _migrate_add_columns()
    _migrate_add_columns()

    session = Session()
    trade = session.query(Trade).filter(Trade.ticker == "KX-DONE").one()
    # SQLite strips tzinfo from DateTime columns; compare naive UTC datetimes.
    assert trade.settled_at == real_settled.replace(tzinfo=None), (
        "rows with non-NULL settled_at must not be touched"
    )
    session.close()
