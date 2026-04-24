"""Shared pytest fixtures — isolate tests from the real SQLite DB."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import predictions.db as db_module


@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    """Point `predictions.db` at a fresh in-memory SQLite for every test.

    The production db module binds the engine at import time via DATABASE_URL.
    Monkey-patching `engine` and `SessionLocal` ensures every call through
    `get_session()` hits the test DB, not the real predictions.db.
    """
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
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

    try:
        import predictions.soccer_cache as soccer_module
    except ImportError:
        # Module doesn't exist yet (first task) — skip patching.
        yield None
        return

    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(soccer_module, "engine", engine)
    monkeypatch.setattr(soccer_module, "SessionLocal", SessionLocal)
    soccer_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
