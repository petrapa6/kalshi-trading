"""Tests for GET /api/strategies (src/predictions/api.py)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


def test_endpoint_requires_auth(client):
    """T-02-01: missing Bearer token returns 401, never leaks data."""
    resp = client.get("/api/strategies")
    assert resp.status_code == 401


def test_endpoint_response_shape(client, tmp_path, monkeypatch):
    """STR-03 / D-10: response is {strategies: [{name, description, triggers}]}."""
    f = tmp_path / "s.yaml"
    f.write_text(
        "strategies:\n"
        "  alpha:\n"
        '    description: "A strategy"\n'
        "    triggers:\n"
        "      - sport: football\n"
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


def test_endpoint_exposes_sport_path_final_minutes_volume(client, tmp_path, monkeypatch):
    """Issue #14: triggers using the extended vocabulary (sport_path,
    final_minutes, min_volume) — as the `main` strategy does — surface in the
    response instead of being silently dropped."""
    f = tmp_path / "s.yaml"
    f.write_text(
        "strategies:\n"
        "  main:\n"
        "    live: true\n"
        "    triggers:\n"
        "      - sport_path: basketball/nba\n"
        "        final_minutes: true\n"
        "        min_volume: 50\n"
        "        min_yes_price: 92\n"
    )
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    resp = client.get("/api/strategies", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    trigger = resp.json()["strategies"][0]["triggers"][0]
    assert trigger["sport_path"] == "basketball/nba"
    assert trigger["final_minutes"] is True
    assert trigger["min_volume"] == 50


def test_endpoint_missing_file_returns_empty(client, monkeypatch):
    """STR-01: missing file path → 200 with {strategies: []}."""
    monkeypatch.setenv("STRATEGIES_PATH", "/nonexistent/path.yaml")
    resp = client.get(
        "/api/strategies",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    assert resp.json() == {"strategies": []}
