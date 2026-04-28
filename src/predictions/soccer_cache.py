"""Soccer historical-match cache, backed by its own SQLite DB and fed by API-Football v3."""

import os
from dataclasses import dataclass
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

    id = Column(String, primary_key=True)  # "af:<api_football_fixture_id>"
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


API_FOOTBALL_BASE_URL = "https://v3.football.api-sports.io"

_LEAGUE_IDS: dict[str, int] = {"PL": 39, "PD": 140, "BL1": 78}

_FINISHED_STATUSES = {"FT", "AET", "PEN"}


class RateLimitedError(Exception):
    """Raised when API-Football returns HTTP 429."""


def _season_for_date(date_str: str) -> int:
    """Return the 4-digit European season start year for a YYYY-MM-DD date.

    The European soccer season runs Aug–Jul. Jan–Jul dates belong to the
    season that started the previous calendar year.
    """
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return dt.year if dt.month >= 8 else dt.year - 1


def _synthesize_goals(events: list[dict]) -> list[dict]:
    return [e for e in events if e.get("type") == "Goal" and e.get("detail") != "Missed Penalty"]


class ApiFootballClient:
    """Thin async wrapper over API-Football v3 (api-sports.io).

    Does not retry. On HTTP 429 raises RateLimitedError so the caller can
    surface partial results to the user. Other non-2xx responses raise
    httpx.HTTPStatusError via raise_for_status. A 200 response with a
    non-empty errors array raises RuntimeError.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str = API_FOOTBALL_BASE_URL,
        transport: httpx.AsyncBaseTransport | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._client = httpx.AsyncClient(
            base_url=base_url,
            headers={"x-apisports-key": api_key},
            timeout=timeout,
            transport=transport,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _check_errors(self, body: dict) -> None:
        errors = body.get("errors")
        if errors:
            raise RuntimeError(f"API-Football error: {errors}")

    async def list_matches(self, league: str, date_from: str, date_to: str) -> dict:
        league_id = _LEAGUE_IDS[league]
        season_from = _season_for_date(date_from)
        season_to = _season_for_date(date_to)

        all_responses: list[dict] = []
        for season in range(season_from, season_to + 1):
            resp = await self._client.get(
                "/fixtures",
                params={
                    "league": league_id,
                    "season": season,
                    "from": date_from,
                    "to": date_to,
                    "status": "FT-AET-PEN",
                },
            )
            if resp.status_code == 429:
                raise RateLimitedError("API-Football rate limit hit on list_matches")
            resp.raise_for_status()
            body = resp.json()
            self._check_errors(body)
            all_responses.extend(body.get("response", []))

        return {"errors": [], "response": all_responses}

    async def get_match_goals(self, match_id: int) -> dict:
        resp = await self._client.get("/fixtures", params={"ids": str(match_id)})
        if resp.status_code == 429:
            raise RateLimitedError("API-Football rate limit hit on get_match_goals")
        resp.raise_for_status()
        body = resp.json()
        self._check_errors(body)
        items = body.get("response", [])
        if not items:
            return {}
        item = items[0]
        item = dict(item)
        item["goals"] = _synthesize_goals(item.get("events", []))
        return item

    async def get_match_goals_batch(self, match_ids: list[int]) -> dict[int, dict]:
        ids_str = "-".join(str(i) for i in match_ids)
        resp = await self._client.get("/fixtures", params={"ids": ids_str})
        if resp.status_code == 429:
            raise RateLimitedError("API-Football rate limit hit on get_match_goals_batch")
        resp.raise_for_status()
        body = resp.json()
        self._check_errors(body)
        result: dict[int, dict] = {}
        for item in body.get("response", []):
            fixture_id = int(item["fixture"]["id"])
            item = dict(item)
            item["goals"] = _synthesize_goals(item.get("events", []))
            result[fixture_id] = item
        return result


class _SoccerClientLike(Protocol):
    async def list_matches(self, league: str, date_from: str, date_to: str) -> dict: ...
    async def get_match_goals(self, match_id: int) -> dict: ...
    async def get_match_goals_batch(self, match_ids: list[int]) -> dict[int, dict]: ...


@dataclass
class EnsureResult:
    matches: list[SoccerMatch]
    partial: bool
    missing_count: int


def _parse_iso_utc(s: str) -> datetime:
    """Parse ISO-8601 with optional trailing Z or offset."""
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def _ingest_goals(session, match_id_str: str, home_team_id: int, raw_goals: list[dict]) -> None:
    """Insert SoccerGoal rows, flipping own-goal scorer to beneficiary side."""
    for seq, g in enumerate(raw_goals, start=1):
        time_obj = g.get("time") or {}
        minute = int(time_obj.get("elapsed") or 0)
        stoppage = int(time_obj.get("extra") or 0)
        scorer_team_id = (g.get("team") or {}).get("id")
        is_own = g.get("detail") == "Own Goal"
        scoring_side = "home" if scorer_team_id == home_team_id else "away"
        # Own-goal: the listed team is the conceder; beneficiary is the opposite side.
        if is_own:
            scoring_side = "away" if scoring_side == "home" else "home"
        session.add(
            SoccerGoal(
                match_id=match_id_str,
                sequence=seq,
                minute=minute,
                stoppage=stoppage,
                side=scoring_side,
                is_own_goal=1 if is_own else 0,
            )
        )


_BATCH_SIZE = 20


async def ensure_matches_cached(
    league: str,
    date_from: str,
    date_to: str,
    *,
    client: _SoccerClientLike | None = None,
) -> EnsureResult:
    """Fetch any missing FINISHED matches in the range and persist them.

    Returns all FINISHED matches currently in the cache for (league, range),
    plus a partial flag + missing_count on rate-limit mid-fetch.
    """
    if client is None:
        api_key = os.getenv("API_FOOTBALL_KEY", "")
        if not api_key:
            raise RuntimeError("API_FOOTBALL_KEY is not set")
        client = ApiFootballClient(api_key=api_key)

    list_body = await client.list_matches(league, date_from, date_to)
    raw_matches = [
        m
        for m in list_body.get("response", [])
        if m.get("fixture", {}).get("status", {}).get("short") in _FINISHED_STATUSES
    ]

    partial = False
    missing = 0
    session = SessionLocal()
    try:
        existing_ids = {
            row[0]
            for row in session.query(SoccerMatch.id).filter(SoccerMatch.competition == league).all()
        }

        to_fetch = [m for m in raw_matches if f"af:{m['fixture']['id']}" not in existing_ids]

        committed_count = 0
        for chunk_start in range(0, len(to_fetch), _BATCH_SIZE):
            chunk = to_fetch[chunk_start : chunk_start + _BATCH_SIZE]
            chunk_ids = [int(m["fixture"]["id"]) for m in chunk]

            try:
                batch = await client.get_match_goals_batch(chunk_ids)
            except RateLimitedError:
                partial = True
                missing = len(to_fetch) - committed_count
                break

            for m in chunk:
                fixture_id = int(m["fixture"]["id"])
                match_id_str = f"af:{fixture_id}"
                detail = batch.get(fixture_id, {})

                home_team_id = m["teams"]["home"]["id"]
                match_row = SoccerMatch(
                    id=match_id_str,
                    competition=league,
                    kickoff_at=_parse_iso_utc(m["fixture"]["date"]),
                    home_team=m["teams"]["home"]["name"],
                    away_team=m["teams"]["away"]["name"],
                    home_score=int(m["goals"].get("home") or 0),
                    away_score=int(m["goals"].get("away") or 0),
                    status="FINISHED",
                    fetched_at=datetime.now(timezone.utc),
                )
                session.add(match_row)
                _ingest_goals(session, match_id_str, home_team_id, detail.get("goals") or [])
                session.commit()
                committed_count += 1

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
