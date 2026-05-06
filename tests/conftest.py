"""Shared pytest fixtures — isolate tests from the real SQLite DB."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import predictions.db as db_module


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Point `predictions.db` at a fresh in-memory SQLite for every test.

    The production db module binds the engine at import time via DATABASE_URL.
    Monkey-patching `engine` and `SessionLocal` ensures every call through
    `get_session()` hits the test DB, not the real predictions.db.

    StaticPool is required so the `:memory:` database is shared across
    connections within the same engine — without it, FastAPI TestClient
    requests run on a worker thread and open a fresh connection that sees
    an empty `:memory:` DB. With StaticPool, all sessions reuse the one
    connection that holds the seeded tables.
    """
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    db_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


@pytest.fixture(autouse=True)
def isolated_soccer_db(monkeypatch):
    """Point `predictions.soccer_cache` at a fresh in-memory SQLite for every test."""
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    try:
        import predictions.soccer_cache as soccer_module
    except ImportError:
        # Module doesn't exist yet (first task) — skip patching.
        yield None
        return

    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(soccer_module, "engine", engine)
    monkeypatch.setattr(soccer_module, "SessionLocal", SessionLocal)
    soccer_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()


def seed_trades(engine, rows: list[dict]) -> None:
    """Insert Trade rows into the engine yielded by `isolated_db`.

    Each row dict is unpacked as **kwargs to the Trade ORM constructor —
    callers control which columns to populate. Required columns per the
    Trade model: ticker, side, count, yes_price, cost_cents,
    potential_profit_cents, status. Optional but commonly set in
    analytics tests: strategy_name, pnl_cents, settled_at, placed_at,
    dry_run.
    """
    from sqlalchemy.orm import sessionmaker

    from predictions.db import Trade

    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        for row in rows:
            session.add(Trade(**row))
        session.commit()
    finally:
        session.close()
