"""Tests for Phase 04 analytics endpoints (DASH-03).

Wave 0: stubs marked xfail. Wave 1 plans (04-01) implement the endpoints,
remove the xfail marker per test, and the test bodies are filled in.
Validates GET /api/strategy-analytics and GET /api/strategies-summary
in src/predictions/api.py.
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


def _make_row(
    ticker: str,
    status: str,
    pnl: int | None,
    *,
    dry_run: bool = True,
    strategy_name: str | None = "alpha",
    placed_at: datetime | None = None,
    settled_at: datetime | None = None,
) -> dict:
    placed = placed_at or datetime(2026, 5, 1, 12, 0, tzinfo=timezone.utc)
    if settled_at is None and status not in ("dry_run",):
        settled_at = datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)
    return dict(
        ticker=ticker,
        side="yes",
        action="buy",
        count=1,
        yes_price=70,
        cost_cents=70,
        potential_profit_cents=30,
        status=status,
        pnl_cents=pnl,
        dry_run=dry_run,
        strategy_name=strategy_name,
        placed_at=placed,
        settled_at=settled_at,
    )


def test_analytics_returns_correct_stats(client, isolated_db):
    """DASH-03: GET /api/strategy-analytics?strategy=alpha returns correct
    stats (total/wins/losses/win_rate/realized_pnl_cents) for a strategy
    with seeded settled_win + settled_loss + dry_run rows.
    """
    seed_trades(
        isolated_db,
        [
            _make_row("KX-1", "settled_win", 50),
            _make_row("KX-2", "settled_win", 30),
            _make_row("KX-3", "settled_loss", -40),
            _make_row("KX-4", "dry_run", None, settled_at=None),
        ],
    )

    resp = client.get(
        "/api/strategy-analytics?strategy=alpha",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["total_trades"] == 4
    assert data["stats"]["wins"] == 2
    assert data["stats"]["losses"] == 1
    assert data["stats"]["open_trades"] == 1
    assert data["stats"]["win_rate"] == 66.7
    assert data["stats"]["realized_pnl_cents"] == 40
    assert len(data["trades"]) == 4


def test_analytics_pnl_curve_running_sum(client, isolated_db):
    """DASH-03 / D-05 / D-09: pnl_curve is a running sum of pnl_cents
    over settled trades, ordered by settled_at ascending.
    """
    t1 = datetime(2026, 5, 1, 13, 0, tzinfo=timezone.utc)
    t2 = datetime(2026, 5, 1, 14, 0, tzinfo=timezone.utc)
    t3 = datetime(2026, 5, 1, 15, 0, tzinfo=timezone.utc)
    seed_trades(
        isolated_db,
        [
            _make_row("KX-1", "settled_win", 50, settled_at=t1),
            _make_row("KX-2", "settled_loss", -20, settled_at=t2),
            _make_row("KX-3", "settled_win", 30, settled_at=t3),
        ],
    )

    resp = client.get(
        "/api/strategy-analytics?strategy=alpha",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    # SQLite strips tzinfo on round-trip — compare against the naive ISO form.
    assert data["pnl_curve"] == [
        {"x": t1.replace(tzinfo=None).isoformat(), "y": 50, "ticker": "KX-1", "trade_pnl": 50},
        {"x": t2.replace(tzinfo=None).isoformat(), "y": 30, "ticker": "KX-2", "trade_pnl": -20},
        {"x": t3.replace(tzinfo=None).isoformat(), "y": 60, "ticker": "KX-3", "trade_pnl": 30},
    ]


def test_analytics_zero_trade_strategy(client, isolated_db):
    """DASH-03 / Success criterion 4: GET /api/strategy-analytics?strategy=zero
    for a strategy with no Trade rows returns 200 with all-zero stats and
    an empty pnl_curve (NOT 404, NOT 500). Trade list is also empty.
    """
    # Seed a row for a different strategy to confirm filter exclusion.
    seed_trades(
        isolated_db,
        [_make_row("KX-OTHER", "settled_win", 99, strategy_name="other")],
    )

    resp = client.get(
        "/api/strategy-analytics?strategy=phantom",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"] == {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "open_trades": 0,
        "win_rate": 0.0,
        "realized_pnl_cents": 0,
    }
    assert data["trades"] == []
    assert data["pnl_curve"] == []


def _write_strategies_yaml(tmp_path, names: list[str]) -> str:
    """Helper for summary tests — write a minimal strategies.yaml with the
    given names, all using a basic single-trigger config. Returns the path.
    """
    body = "strategies:\n"
    for name in names:
        body += f"  {name}:\n"
        body += "    triggers:\n"
        body += "      - sport: football\n"
        body += "        min_minute: 80\n"
    f = tmp_path / "s.yaml"
    f.write_text(body)
    return str(f)


def test_summary_includes_zero_trade_strategies(client, isolated_db, tmp_path, monkeypatch):
    """DASH-03 / D-11: GET /api/strategies-summary merges DB GROUP BY
    results with YAML strategy names so zero-trade strategies appear in
    the response with all-zero stats. Without the merge, GROUP BY
    silently omits them.
    """
    yaml_path = _write_strategies_yaml(tmp_path, ["alpha", "lonely"])
    monkeypatch.setenv("STRATEGIES_PATH", yaml_path)

    seed_trades(
        isolated_db,
        [_make_row("KX-1", "settled_win", 50, strategy_name="alpha")],
    )

    resp = client.get(
        "/api/strategies-summary",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    by_name = {s["name"]: s for s in data["strategies"]}
    assert "alpha" in by_name
    assert "lonely" in by_name
    assert by_name["lonely"] == {
        "name": "lonely",
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "pnl_cents": 0,
    }


def test_summary_aggregation(client, isolated_db, tmp_path, monkeypatch):
    """DASH-03 / D-06: GET /api/strategies-summary returns
    [{name, total_trades, wins, losses, pnl_cents}] per strategy.
    """
    yaml_path = _write_strategies_yaml(tmp_path, ["alpha", "beta"])
    monkeypatch.setenv("STRATEGIES_PATH", yaml_path)

    seed_trades(
        isolated_db,
        [
            _make_row("KX-A1", "settled_win", 50, strategy_name="alpha"),
            _make_row("KX-A2", "settled_win", 30, strategy_name="alpha"),
            _make_row("KX-A3", "settled_loss", -20, strategy_name="alpha"),
            _make_row("KX-B1", "settled_win", 100, strategy_name="beta"),
        ],
    )

    resp = client.get(
        "/api/strategies-summary",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    by_name = {s["name"]: s for s in data["strategies"]}
    assert by_name["alpha"] == {
        "name": "alpha",
        "total_trades": 3,
        "wins": 2,
        "losses": 1,
        "pnl_cents": 60,
    }
    assert by_name["beta"] == {
        "name": "beta",
        "total_trades": 1,
        "wins": 1,
        "losses": 0,
        "pnl_cents": 100,
    }


def test_endpoints_require_auth(client):
    """DASH-03 / Threat T-04-02: Both GET /api/strategy-analytics and
    GET /api/strategies-summary return 401 when called without a Bearer token.
    """
    resp = client.get("/api/strategy-analytics?strategy=alpha")
    assert resp.status_code == 401
    resp = client.get("/api/strategies-summary")
    assert resp.status_code == 401


def test_composite_filter_excludes_legacy_trades(client, isolated_db):
    """DASH-03 / Phase 03 D-16 symmetry: a Trade row with
    dry_run=True AND strategy_name=NULL (legacy process-level dry-run)
    does NOT appear in /api/strategy-analytics results. Only
    dry_run=True+strategy_name SET, or dry_run=False, count.
    """
    seed_trades(
        isolated_db,
        [
            # Legacy process-level dry-run (no strategy attribution)
            _make_row(
                "KX-Legacy",
                "dry_run",
                None,
                dry_run=True,
                strategy_name=None,
                settled_at=None,
            ),
            # Phase 03 strategy fire (D-13)
            _make_row(
                "KX-Alpha",
                "dry_run",
                None,
                dry_run=True,
                strategy_name="alpha",
                settled_at=None,
            ),
        ],
    )

    resp = client.get(
        "/api/strategy-analytics?strategy=alpha",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["stats"]["total_trades"] == 1
    tickers = [t["ticker"] for t in data["trades"]]
    assert "KX-Alpha" in tickers
    assert "KX-Legacy" not in tickers
