"""Soccer backtest: simulate trigger-based trading strategies on historical matches."""

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
