import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


def test_backtest_requires_bearer(client):
    resp = client.post("/api/backtest/soccer", json={})
    assert resp.status_code == 401


def test_backtest_returns_503_when_api_key_missing(client, monkeypatch):
    monkeypatch.delenv("FOOTBALL_DATA_API_KEY", raising=False)
    body = {
        "league": "PL",
        "date_from": "2026-03-01",
        "date_to": "2026-04-01",
        "min_minute": 75,
        "min_lead": 2,
        "min_yes_price": 0,
        "initial_balance_cents": 100000,
        "bet_percent": 0.02,
    }
    resp = client.post(
        "/api/backtest/soccer",
        json=body,
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 503


def test_backtest_validation_400_on_bad_date_range(client, monkeypatch):
    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "k")
    body = {
        "league": "PL",
        "date_from": "2026-05-01",
        "date_to": "2026-03-01",
        "min_minute": 75,
        "min_lead": 2,
        "min_yes_price": 0,
        "initial_balance_cents": 100000,
        "bet_percent": 0.02,
    }
    resp = client.post(
        "/api/backtest/soccer",
        json=body,
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code in (400, 422)


def test_backtest_200_happy_path(client, monkeypatch):
    from unittest.mock import AsyncMock, patch

    from predictions.backtest import BacktestResponse, BacktestSummary

    monkeypatch.setenv("FOOTBALL_DATA_API_KEY", "k")
    fake = BacktestResponse(
        summary=BacktestSummary(
            matches_scanned=0,
            matches_bet_on=0,
            matches_with_price_data=0,
            wins=0,
            losses=0,
            win_rate=0.0,
            initial_balance_cents=100000,
            final_balance_cents=100000,
            pnl_cents=0,
            pnl_pct=0.0,
        ),
        trades=[],
        bankroll_curve=[],
        partial=False,
        missing_count=0,
    )
    with patch("predictions.backtest.run_backtest", AsyncMock(return_value=fake)):
        body = {
            "league": "PL",
            "date_from": "2026-03-01",
            "date_to": "2026-04-01",
            "min_minute": 75,
            "min_lead": 2,
            "min_yes_price": 0,
            "initial_balance_cents": 100000,
            "bet_percent": 0.02,
        }
        resp = client.post(
            "/api/backtest/soccer",
            json=body,
            headers={"Authorization": "Bearer test-token"},
        )
    assert resp.status_code == 200
    assert resp.json()["summary"]["matches_scanned"] == 0
