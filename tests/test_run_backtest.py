from datetime import date

import pytest
from pydantic import ValidationError


def test_backtest_request_defaults_and_validation():
    from predictions.backtest import BacktestRequest

    # Valid minimum
    req = BacktestRequest(
        league="PL",
        date_from=date(2026, 3, 1),
        date_to=date(2026, 4, 1),
        min_minute=75,
        min_lead=2,
        min_yes_price=0,
        initial_balance_cents=100000,
        bet_percent=0.02,
    )
    assert req.league == "PL"

    # Unknown league rejected
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="SPL",  # ty: ignore[invalid-argument-type]
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )

    # date_from > date_to rejected
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 5, 1),
            date_to=date(2026, 3, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )

    # Out-of-range numeric params rejected
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=0,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=6,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=100,
            initial_balance_cents=100000,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=999,
            bet_percent=0.02,
        )
    with pytest.raises(ValidationError):
        BacktestRequest(
            league="PL",
            date_from=date(2026, 3, 1),
            date_to=date(2026, 4, 1),
            min_minute=75,
            min_lead=2,
            min_yes_price=0,
            initial_balance_cents=100000,
            bet_percent=0.2,
        )
