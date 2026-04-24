"""Soccer backtest: simulate trigger-based trading strategies on historical matches."""

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
