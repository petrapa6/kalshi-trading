"""Soccer historical-match cache, backed by its own SQLite DB and fed by football-data.org."""

import os
from datetime import datetime, timezone
from typing import Protocol

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


from dataclasses import dataclass


class _FootballClientLike(Protocol):
    async def list_matches(self, league: str, date_from: str, date_to: str) -> dict: ...
    async def get_match_goals(self, match_id: int) -> dict: ...


@dataclass
class EnsureResult:
    matches: list[SoccerMatch]
    partial: bool
    missing_count: int


def _parse_iso_utc(s: str) -> datetime:
    """Parse ISO-8601 (football-data.org uses trailing 'Z')."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _ingest_goals(session, match_id_str: str, home_team_id: int, raw_goals: list[dict]) -> None:
    """Insert SoccerGoal rows, flipping own-goal scorer to beneficiary side."""
    for seq, g in enumerate(raw_goals, start=1):
        minute = int(g.get("minute") or 0)
        stoppage = int(g.get("injuryTime") or 0)
        scorer_team_id = (g.get("team") or {}).get("id")
        gtype = (g.get("type") or "REGULAR").upper()
        scoring_side = "home" if scorer_team_id == home_team_id else "away"
        # Own-goal: "team.id" is the conceder in football-data.org's payload.
        # The beneficiary — and hence the side that counts on the scoreboard —
        # is the OPPOSITE side.
        if gtype == "OWN":
            scoring_side = "away" if scoring_side == "home" else "home"
        session.add(
            SoccerGoal(
                match_id=match_id_str,
                sequence=seq,
                minute=minute,
                stoppage=stoppage,
                side=scoring_side,
                is_own_goal=1 if gtype == "OWN" else 0,
            )
        )


async def ensure_matches_cached(
    league: str,
    date_from: str,
    date_to: str,
    *,
    client: _FootballClientLike | None = None,
) -> EnsureResult:
    """Fetch any missing FINISHED matches in the range and persist them.

    Returns all FINISHED matches currently in the cache for (league, range),
    plus a partial flag + missing_count on rate-limit mid-fetch.
    """
    if client is None:
        api_key = os.getenv("FOOTBALL_DATA_API_KEY", "")
        if not api_key:
            raise RuntimeError("FOOTBALL_DATA_API_KEY is not set")
        client = FootballDataClient(api_key=api_key)

    list_body = await client.list_matches(league, date_from, date_to)
    raw_matches = [m for m in list_body.get("matches", []) if m.get("status") == "FINISHED"]

    partial = False
    missing = 0
    session = SessionLocal()
    try:
        existing_ids = {
            row[0]
            for row in session.query(SoccerMatch.id).filter(SoccerMatch.competition == league).all()
        }
        for i, m in enumerate(raw_matches):
            match_id_str = f"fd:{m['id']}"
            if match_id_str in existing_ids:
                continue
            try:
                detail = await client.get_match_goals(m["id"])
            except RateLimitedError:
                partial = True
                missing = len(raw_matches) - i
                break

            home_team_id = m["homeTeam"]["id"]
            full_time = (m.get("score") or {}).get("fullTime") or {}
            match_row = SoccerMatch(
                id=match_id_str,
                competition=league,
                kickoff_at=_parse_iso_utc(m["utcDate"]),
                home_team=m["homeTeam"]["name"],
                away_team=m["awayTeam"]["name"],
                home_score=int(full_time.get("home") or 0),
                away_score=int(full_time.get("away") or 0),
                status="FINISHED",
                fetched_at=datetime.now(timezone.utc),
            )
            session.add(match_row)
            _ingest_goals(session, match_id_str, home_team_id, detail.get("goals") or [])
            session.commit()

        # Return all currently-cached matches for the range.
        start = _parse_iso_utc(f"{date_from}T00:00:00Z")
        end = _parse_iso_utc(f"{date_to}T23:59:59Z")
        cached = (
            session.query(SoccerMatch)
            .filter(
                SoccerMatch.competition == league,
                SoccerMatch.kickoff_at >= start,
                SoccerMatch.kickoff_at <= end,
            )
            .order_by(SoccerMatch.kickoff_at)
            .all()
        )
        # Detach from session so the caller can read attributes after .close().
        for m in cached:
            session.expunge(m)
    finally:
        session.close()

    return EnsureResult(matches=cached, partial=partial, missing_count=missing)
