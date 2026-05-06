"""Tests for Phase 04 analytics endpoints (DASH-03).

Wave 0: stubs marked xfail. Wave 1 plans (04-01) implement the endpoints,
remove the xfail marker per test, and the test bodies are filled in.
Validates GET /api/strategy-analytics and GET /api/strategies-summary
in src/predictions/api.py.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


@pytest.mark.xfail(strict=True, reason="Wave 1 implements GET /api/strategy-analytics")
def test_analytics_returns_correct_stats(client, isolated_db):
    """DASH-03: GET /api/strategy-analytics?strategy=alpha returns correct
    stats (total/wins/losses/win_rate/realized_pnl_cents) for a strategy
    with seeded settled_win + settled_loss + dry_run rows.

    Composite filter (D-04) applies; fixtures use seed_trades from
    conftest. Wave 1 fills in the seed rows + assertions.
    """
    pytest.fail("not yet implemented (Wave 1)")


@pytest.mark.xfail(strict=True, reason="Wave 1 implements pnl_curve running sum")
def test_analytics_pnl_curve_running_sum(client, isolated_db):
    """DASH-03 / D-05 / D-09: pnl_curve in the response is a running sum
    of pnl_cents over settled trades, ordered by settled_at ascending.
    Each entry has {x: settled_at ISO string, y: running_pnl_cents,
    ticker, trade_pnl}.

    Wave 1 seeds 3+ settled trades with known pnl_cents and asserts the
    cumulative arithmetic.
    """
    pytest.fail("not yet implemented (Wave 1)")


@pytest.mark.xfail(strict=True, reason="Wave 1 implements zero-trade strategy handling")
def test_analytics_zero_trade_strategy(client, isolated_db):
    """DASH-03 / Success criterion 4: GET /api/strategy-analytics?strategy=zero
    for a strategy with no Trade rows returns 200 with all-zero stats and
    an empty pnl_curve (NOT 404, NOT 500). Trade list is also empty.

    Wave 1 implements + seeds NO rows for the queried strategy.
    """
    pytest.fail("not yet implemented (Wave 1)")


@pytest.mark.xfail(strict=True, reason="Wave 1 implements YAML+DB merge")
def test_summary_includes_zero_trade_strategies(client, isolated_db, tmp_path, monkeypatch):
    """DASH-03 / D-11: GET /api/strategies-summary merges DB GROUP BY
    results with YAML strategy names so zero-trade strategies appear in
    the response with all-zero stats. Without the merge, GROUP BY
    silently omits them.

    Wave 1 writes a strategies.yaml fixture via tmp_path, seeds rows for
    ONE strategy only, and asserts both strategies appear in the summary.
    """
    pytest.fail("not yet implemented (Wave 1)")


@pytest.mark.xfail(strict=True, reason="Wave 1 implements summary aggregation")
def test_summary_aggregation(client, isolated_db, tmp_path, monkeypatch):
    """DASH-03 / D-06: GET /api/strategies-summary returns
    [{name, total_trades, wins, losses, pnl_cents}] per strategy. Wins
    count rows with status='settled_win'; losses count
    status='settled_loss'; pnl_cents sums pnl_cents across all rows for
    the strategy.

    Wave 1 seeds multi-strategy multi-status rows and asserts each
    strategy's per-row aggregation.
    """
    pytest.fail("not yet implemented (Wave 1)")


@pytest.mark.xfail(strict=True, reason="Wave 1 wires Depends(_check_token) on both endpoints")
def test_endpoints_require_auth(client):
    """DASH-03 / Threat T-04-02: Both GET /api/strategy-analytics and
    GET /api/strategies-summary return 401 when called without a Bearer
    token. Mirrors tests/test_strategies_api.py::test_endpoint_requires_auth.

    No DB seeding required — the auth check fires before any query.
    """
    pytest.fail("not yet implemented (Wave 1)")


@pytest.mark.xfail(
    strict=True, reason="Wave 1 applies Phase 03 D-16 composite filter symmetrically"
)
def test_composite_filter_excludes_legacy_trades(client, isolated_db):
    """DASH-03 / Phase 03 D-16 symmetry: a Trade row with
    dry_run=True AND strategy_name=NULL (legacy process-level dry-run)
    does NOT appear in /api/strategy-analytics or /api/strategies-summary
    results. Only dry_run=True+strategy_name SET, or dry_run=False, count.

    Wave 1 seeds one legacy dry-run row and one strategy dry-run row with
    the same ticker, asserts only the latter is counted.
    """
    pytest.fail("not yet implemented (Wave 1)")
