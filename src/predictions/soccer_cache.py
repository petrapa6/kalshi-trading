"""Soccer historical-match cache, backed by its own SQLite DB and fed by football-data.org."""

import os
from datetime import datetime, timezone

import httpx
from dotenv import load_dotenv

load_dotenv()

from sqlalchemy import (
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    create_engine,
    inspect,
    text,
)
from sqlalchemy.orm import declarative_base, sessionmaker

_repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_default_db = os.path.join(_repo_root, "soccer-cache.db")
SOCCER_CACHE_DB_PATH = os.getenv("SOCCER_CACHE_DB_PATH", _default_db)
SOCCER_CACHE_URL = f"sqlite:///{SOCCER_CACHE_DB_PATH}"

engine = create_engine(SOCCER_CACHE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(bind=engine)
Base = declarative_base()


class SoccerMatch(Base):
    __tablename__ = "soccer_matches"

    id = Column(String, primary_key=True)  # "fd:<football_data_id>"
    competition = Column(String, nullable=False)  # 'PL' | 'PD' | 'BL1'
    kickoff_at = Column(DateTime, nullable=False)
    home_team = Column(String, nullable=False)
    away_team = Column(String, nullable=False)
    home_score = Column(Integer, nullable=False)
    away_score = Column(Integer, nullable=False)
    status = Column(String, nullable=False)  # always 'FINISHED' for cached rows
    fetched_at = Column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))

    __table_args__ = (Index("idx_soccer_matches_comp_kickoff", "competition", "kickoff_at"),)


class SoccerGoal(Base):
    __tablename__ = "soccer_goals"

    match_id = Column(String, ForeignKey("soccer_matches.id"), primary_key=True)
    sequence = Column(Integer, primary_key=True)  # 1..N chronological
    minute = Column(Integer, nullable=False)  # regulation minute
    stoppage = Column(Integer, nullable=False, default=0)
    side = Column(String, nullable=False)  # 'home' | 'away' — beneficiary
    is_own_goal = Column(Integer, nullable=False, default=0)


def init_soccer_db() -> None:
    Base.metadata.create_all(engine)
    _migrate_add_columns()


def _migrate_add_columns() -> None:
    inspector = inspect(engine)
    if "soccer_goals" in inspector.get_table_names():
        cols = {c["name"] for c in inspector.get_columns("soccer_goals")}
        with engine.begin() as conn:
            if "stoppage" not in cols:
                conn.execute(
                    text("ALTER TABLE soccer_goals ADD COLUMN stoppage INTEGER NOT NULL DEFAULT 0")
                )
            if "is_own_goal" not in cols:
                conn.execute(
                    text(
                        "ALTER TABLE soccer_goals ADD COLUMN is_own_goal INTEGER NOT NULL DEFAULT 0"
                    )
                )


def get_session():
    return SessionLocal()


FOOTBALL_DATA_BASE_URL = "https://api.football-data.org/v4"


class RateLimitedError(Exception):
    """Raised when football-data.org returns HTTP 429."""


class FootballDataClient:
    """Thin async wrapper over football-data.org v4.

    Does not retry. On HTTP 429 raises RateLimitedError so the caller can
    surface partial results to the user. Other non-2xx responses raise
    httpx.HTTPStatusError via raise_for_status.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = FOOTBALL_DATA_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"X-Auth-Token": api_key},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def list_matches(self, league: str, date_from: str, date_to: str) -> dict:
        resp = await self._client.get(
            f"/competitions/{league}/matches",
            params={"dateFrom": date_from, "dateTo": date_to},
        )
        if resp.status_code == 429:
            raise RateLimitedError("football-data.org rate limit hit on list_matches")
        resp.raise_for_status()
        return resp.json()

    async def get_match_goals(self, match_id: int) -> dict:
        resp = await self._client.get(f"/matches/{match_id}")
        if resp.status_code == 429:
            raise RateLimitedError("football-data.org rate limit hit on get_match_goals")
        resp.raise_for_status()
        return resp.json()
