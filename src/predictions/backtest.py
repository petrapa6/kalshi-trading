"""Soccer backtest: simulate trigger-based trading strategies on historical matches."""

import re
import unicodedata
from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timezone
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

LeagueCode = Literal["PL", "PD", "BL1"]


class BacktestRequest(BaseModel):
    league: LeagueCode
    date_from: date
    date_to: date
    min_minute: int = Field(ge=1, le=90)
    min_lead: int = Field(ge=1, le=5)
    min_yes_price: int = Field(ge=0, le=99)
    initial_balance_cents: int = Field(ge=1000)
    bet_percent: float = Field(ge=0.005, le=0.10)

    @model_validator(mode="after")
    def _date_range_valid(self):
        if self.date_from > self.date_to:
            raise ValueError("date_from must be <= date_to")
        if self.date_to > datetime.now(timezone.utc).date():
            raise ValueError("date_to cannot be in the future")
        return self


class BacktestTrade(BaseModel):
    match_id: str
    kickoff_at: datetime
    league: LeagueCode
    home_team: str
    away_team: str
    final_home: int
    final_away: int
    fired_at_minute: int
    score_at_fire_home: int
    score_at_fire_away: int
    leading_side: Literal["home", "away"]
    result: Literal["win", "loss"]
    observed_yes_ask_cents: Optional[int] = None
    count: Optional[int] = None
    cost_cents: Optional[int] = None
    pnl_cents: Optional[int] = None
    bankroll_after_cents: int


class BacktestCurvePoint(BaseModel):
    t: datetime
    balance_cents: int


class BacktestSummary(BaseModel):
    matches_scanned: int
    matches_bet_on: int
    matches_with_price_data: int
    wins: int
    losses: int
    win_rate: float
    initial_balance_cents: int
    final_balance_cents: int
    pnl_cents: int
    pnl_pct: float


class BacktestResponse(BaseModel):
    summary: BacktestSummary
    trades: list[BacktestTrade]
    bankroll_curve: list[BacktestCurvePoint]
    partial: bool
    missing_count: int


@dataclass
class Trigger:
    fired_at_minute: int
    score_at_fire_home: int
    score_at_fire_away: int
    leading_side: Literal["home", "away"]


def simulate_match(match, req: BacktestRequest) -> Trigger | None:
    """Walk minutes 1..90, applying goals in sequence order per minute.

    Fires once on the first minute >= req.min_minute at which
    abs(home - away) >= req.min_lead. Subsequent goals are ignored.

    `match.goals` must be an iterable of objects with .minute, .stoppage,
    .side ('home'|'away', beneficiary), .sequence — `is_own_goal` is
    informational and does NOT affect the side column (the ingestion
    layer already flipped own-goal rows to the beneficiary).
    """
    goals_by_minute: dict[int, list] = defaultdict(list)
    for g in match.goals:
        goals_by_minute[g.minute].append(g)
    # sequence is chronological by construction in soccer_cache._ingest_goals,
    # so sorting by it orders same-minute goals in real scoring order.
    for minute, gs in goals_by_minute.items():
        gs.sort(key=lambda x: x.sequence)

    home_score = 0
    away_score = 0
    for minute in range(1, 91):
        for g in goals_by_minute.get(minute, ()):
            if g.side == "home":
                home_score += 1
            else:
                away_score += 1
        if minute < req.min_minute:
            continue
        diff = home_score - away_score
        if abs(diff) >= req.min_lead:
            return Trigger(
                fired_at_minute=minute,
                score_at_fire_home=home_score,
                score_at_fire_away=away_score,
                leading_side="home" if diff > 0 else "away",
            )
    return None


# Canonical team-name aliases. Each entry maps an alias to its canonical
# display name. Lookup is case-insensitive after _normalize_team. This is
# the systematic-correction surface — grow lazily as Kalshi/football-data
# mismatches are observed.
_TEAM_ALIASES: dict[str, str] = {
    # Premier League
    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "brighton": "brighton hove albion",
    "brighton and hove albion": "brighton hove albion",
    "brighton & hove albion": "brighton hove albion",
    "newcastle": "newcastle united",
    "nott'm forest": "nottingham forest",
    "leeds": "leeds united",
    "west ham": "west ham united",
    # La Liga
    "atletico madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atleti": "atletico madrid",
    "real": "real madrid",
    "real madrid": "real madrid",
    "barca": "barcelona",
    "barça": "barcelona",
    "fc barcelona": "barcelona",
    "athletic bilbao": "athletic club",
    "real sociedad": "real sociedad",
    # Bundesliga
    "bayern": "bayern munchen",
    "bayern munich": "bayern munchen",
    "bayern munchen": "bayern munchen",
    "fc bayern munchen": "bayern munchen",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
    "gladbach": "borussia monchengladbach",
    "monchengladbach": "borussia monchengladbach",
    "rb leipzig": "rb leipzig",
    "leipzig": "rb leipzig",
    "schalke": "schalke 04",
    "union berlin": "union berlin",
    "eintracht frankfurt": "eintracht frankfurt",
    "frankfurt": "eintracht frankfurt",
    "freiburg": "sc freiburg",
    "stuttgart": "vfb stuttgart",
}

_NOISE_PREFIXES = ("1. ", "fc ", "afc ")
_NOISE_SUFFIXES = (" fc", " cf", " sc", " ac", " afc", " cfc")


def _normalize_team(name: str) -> str:
    """Lower-case, strip accents + leading/trailing club suffixes, collapse whitespace."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    # Strip noise prefixes BEFORE alphanumeric filtering so patterns like
    # "1. " (with a literal dot) can still match before the dot is normalized away.
    for pref in _NOISE_PREFIXES:
        if s.startswith(pref):
            s = s[len(pref) :].strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suf in _NOISE_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s


def _canonical_team(name: str) -> str:
    """Return the canonical (alias-resolved) form of a team name."""
    norm = _normalize_team(name)
    return _TEAM_ALIASES.get(norm, norm)


def _canonicalize_title(market_title: str) -> str:
    """Tokenize a normalized title and rewrite alias phrases to canonical forms.

    Walks tokens left-to-right; at each position tries the longest matching
    alias-phrase and advances past the consumed tokens. Once an alias is
    consumed, shorter aliases cannot re-enter the same span — this prevents
    "real" → "real madrid" from firing on the "real" in "real sociedad".
    """
    tokens = _normalize_team(market_title).split()
    # Pre-split aliases into token tuples so membership comparison is token-level.
    alias_items = sorted(
        ((alias.split(), canon) for alias, canon in _TEAM_ALIASES.items()),
        key=lambda item: -len(item[0]),
    )
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        for alias_tokens, canon in alias_items:
            k = len(alias_tokens)
            if k <= n - i and tokens[i : i + k] == alias_tokens:
                out.append(canon)
                i += k
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def _market_mentions_both_teams(market_title: str, team_a: str, team_b: str) -> bool:
    """Conservative containment check: the title must contain both canonical
    forms as substrings. Prefers a non-match over a wrong match.
    """
    title_canon = _canonicalize_title(market_title)
    a = _canonical_team(team_a)
    b = _canonical_team(team_b)
    return a in title_canon and b in title_canon
