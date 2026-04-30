"""Tests for GET /api/strategies (src/predictions/api.py).

Stubs are xfail-marked; Wave 1 (plan 02-02) flips them to passing.
"""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


@pytest.mark.xfail(reason="Wave 1 (02-02) implements GET /api/strategies")
def test_endpoint_requires_auth(client):
    """T-02-01: missing Bearer token returns 401, never leaks data."""
    resp = client.get("/api/strategies")
    assert resp.status_code == 401


@pytest.mark.xfail(reason="Wave 1 (02-02) implements GET /api/strategies")
def test_endpoint_response_shape(client, tmp_path, monkeypatch):
    """STR-03 / D-10: response is {strategies: [{name, description, triggers}]}."""
    f = tmp_path / "s.yaml"
    f.write_text(
        "strategies:\n"
        "  alpha:\n"
        '    description: "A strategy"\n'
        "    triggers:\n"
        "      - sport: soccer/eng.1\n"
        "        min_minute: 80\n"
        "        min_lead: 2\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    resp = client.get(
        "/api/strategies",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
    assert isinstance(data["strategies"], list)
    assert data["strategies"][0]["name"] == "alpha"
    assert data["strategies"][0]["description"] == "A strategy"
    assert data["strategies"][0]["triggers"][0]["min_minute"] == 80


@pytest.mark.xfail(reason="Wave 1 (02-02) implements GET /api/strategies")
def test_endpoint_preserves_yaml_order(client, tmp_path, monkeypatch):
    """D-10: list preserves YAML insertion order (Python 3.7+ dict iteration)."""
    f = tmp_path / "ordered.yaml"
    f.write_text(
        "strategies:\n"
        "  zebra:\n"
        "    triggers:\n"
        "      - min_lead: 2\n"
        "  alpha:\n"
        "    triggers:\n"
        "      - min_lead: 2\n"
        "  monkey:\n"
        "    triggers:\n"
        "      - min_lead: 2\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    resp = client.get(
        "/api/strategies",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()["strategies"]]
    assert names == ["zebra", "alpha", "monkey"]


@pytest.mark.xfail(reason="Wave 1 (02-02) implements GET /api/strategies")
def test_endpoint_missing_file_returns_empty(client, monkeypatch):
    """STR-01: missing file path → 200 with {strategies: []}."""
    monkeypatch.setenv("STRATEGIES_PATH", "/nonexistent/path.yaml")
    resp = client.get(
        "/api/strategies",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"strategies": []}
