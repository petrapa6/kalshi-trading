"""Issue #16: /api/stats returns both live + dry-run populations, and
/api/histogram-trades returns both populations with strategy_name +
settled_at so the dashboard can filter client-side without refetch.
"""

from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

from conftest import seed_trades


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


def _row(
    ticker: str,
    status: str,
    pnl: int | None,
    *,
    dry_run: bool,
    cost_cents: int = 70,
    potential: int = 30,
    fee_cents: int | None = None,
    strategy_name: str | None = "alpha",
    settled_at: datetime | None = None,
) -> dict:
    placed = datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    if settled_at is None and status in ("settled_win", "settled_loss"):
        settled_at = datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)
    return dict(
        ticker=ticker,
        side="yes",
        action="buy",
        count=1,
        yes_price=70,
        cost_cents=cost_cents,
        potential_profit_cents=potential,
        status=status,
        pnl_cents=pnl,
        fee_cents=fee_cents,
        dry_run=dry_run,
        strategy_name=strategy_name,
        placed_at=placed,
        settled_at=settled_at,
    )


def _auth():
    return {"Authorization": "Bearer test-token"}


def test_stats_partitions_populations(client, isolated_db):
    """Live and dry-run aggregates partition correctly on a mixed fixture:
    wins/losses/realized P&L/fees/open positions land in the right bucket.
    """
    seed_trades(
        isolated_db,
        [
            # live: 1 win (+50), 1 loss (-20), 1 open (placed)
            _row("L-W", "settled_win", 50, dry_run=False, fee_cents=3),
            _row("L-L", "settled_loss", -20, dry_run=False, fee_cents=2),
            _row("L-O", "placed", None, dry_run=False, cost_cents=90, potential=10),
            # dry: 2 wins (+30,+40), 1 open (dry_run)
            _row("D-W1", "settled_win", 30, dry_run=True),
            _row("D-W2", "settled_win", 40, dry_run=True),
            _row("D-O", "dry_run", None, dry_run=True, cost_cents=80, potential=20),
        ],
    )

    resp = client.get("/api/stats", headers=_auth())
    assert resp.status_code == 200
    data = resp.json()

    live = data["live"]
    assert live["wins"] == 1
    assert live["losses"] == 1
    assert live["win_rate"] == 50.0
    assert live["realized_pnl_cents"] == 30  # 50 - 20
    assert live["total_fees_cents"] == 5  # 3 + 2
    assert live["open_positions"] == 1
    assert live["open_cost_cents"] == 90
    assert live["open_potential_profit_cents"] == 10
    assert live["trades"] == 3

    dry = data["dry_run"]
    assert dry["wins"] == 2
    assert dry["losses"] == 0
    assert dry["win_rate"] == 100.0
    assert dry["realized_pnl_cents"] == 70  # 30 + 40
    assert dry["total_fees_cents"] == 0
    assert dry["open_positions"] == 1
    assert dry["open_cost_cents"] == 80
    assert dry["open_potential_profit_cents"] == 20
    assert dry["trades"] == 3

    # Globals are population-independent and present.
    assert "balance_cents" in data
    assert "portfolio_value_cents" in data
    assert "total_scans" in data
    assert "total_opportunities" in data


def test_stats_empty_win_rate_is_zero(client, isolated_db):
    """No settled trades in a population → win_rate 0.0, no divide-by-zero."""
    seed_trades(isolated_db, [_row("D-O", "dry_run", None, dry_run=True)])
    data = client.get("/api/stats", headers=_auth()).json()
    assert data["live"]["win_rate"] == 0.0
    assert data["dry_run"]["win_rate"] == 0.0
    assert data["live"]["trades"] == 0


def test_stats_requires_auth(client):
    assert client.get("/api/stats").status_code == 401


def test_histogram_trades_returns_both_populations(client, isolated_db):
    """Drop the dry_run==False hard filter: settled trades from both
    populations come back, each carrying strategy_name + settled_at.
    """
    t1 = datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)
    seed_trades(
        isolated_db,
        [
            _row("L-W", "settled_win", 50, dry_run=False, strategy_name="main", settled_at=t1),
            _row("D-W", "settled_win", 30, dry_run=True, strategy_name="alpha", settled_at=t1),
        ],
    )
    data = client.get("/api/histogram-trades", headers=_auth()).json()
    by_ticker = {t["ticker"]: t for t in data["trades"]}
    assert set(by_ticker) == {"L-W", "D-W"}
    assert by_ticker["L-W"]["dry_run"] is False
    assert by_ticker["D-W"]["dry_run"] is True
    assert by_ticker["D-W"]["strategy_name"] == "alpha"
    assert by_ticker["L-W"]["strategy_name"] == "main"
    assert by_ticker["D-W"]["settled_at"] == t1.replace(tzinfo=None).isoformat()
