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
