"""Tests for the raw-YAML catalog editor endpoints (issue #15).

GET /api/strategies/raw   → current catalog file text
PUT /api/strategies/raw   → validate + atomic write + hot reload
"""

import pytest
from fastapi.testclient import TestClient

AUTH = {"Authorization": "Bearer test-token"}

VALID_CATALOG = (
    "strategies:\n"
    "  # a comment that must survive the round-trip\n"
    "  main:\n"
    "    live: true\n"
    "    triggers:\n"
    "      - sport_path: basketball/nba\n"
    "        final_minutes: true\n"
    "        min_yes_price: 92\n"
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


@pytest.fixture
def catalog(tmp_path, monkeypatch):
    f = tmp_path / "strategies.yaml"
    f.write_text(VALID_CATALOG)
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    return f


def test_get_requires_auth(client, catalog):
    assert client.get("/api/strategies/raw").status_code == 401


def test_put_requires_auth(client, catalog):
    assert client.put("/api/strategies/raw", json={"content": "x"}).status_code == 401


def test_get_returns_file_text_verbatim(client, catalog):
    """GET returns the exact file text, comments included."""
    resp = client.get("/api/strategies/raw", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["content"] == VALID_CATALOG


def test_get_missing_file_returns_empty(client, tmp_path, monkeypatch):
    """A not-yet-created catalog reads as empty rather than erroring."""
    monkeypatch.setenv("STRATEGIES_PATH", str(tmp_path / "nope.yaml"))
    resp = client.get("/api/strategies/raw", headers=AUTH)
    assert resp.status_code == 200
    assert resp.json()["content"] == ""


def test_put_valid_persists_and_round_trips(client, catalog):
    """A valid PUT writes the file; a subsequent GET returns it verbatim."""
    new_text = "strategies:\n  alpha:\n    triggers:\n      - min_lead: 5\n"
    resp = client.put("/api/strategies/raw", headers=AUTH, json={"content": new_text})
    assert resp.status_code == 200
    assert catalog.read_text() == new_text
    assert client.get("/api/strategies/raw", headers=AUTH).json()["content"] == new_text


def test_put_response_lists_strategies_with_live_flag(client, catalog):
    """Response includes the parsed strategies with their live flag for the UI warning."""
    resp = client.put("/api/strategies/raw", headers=AUTH, json={"content": VALID_CATALOG})
    assert resp.status_code == 200
    strategies = resp.json()["strategies"]
    assert strategies[0]["name"] == "main"
    assert strategies[0]["live"] is True


def test_put_invalid_returns_422_verbatim_and_leaves_file(client, catalog):
    """Invalid schema → 422 with the loader error; running file untouched."""
    bad = "strategies:\n  s:\n    triggers:\n      - min_minutes: 80\n"  # typo
    resp = client.put("/api/strategies/raw", headers=AUTH, json={"content": bad})
    assert resp.status_code == 422
    assert catalog.read_text() == VALID_CATALOG  # atomic: original intact
    # error text is surfaced verbatim (pydantic mentions the offending field)
    assert "min_minutes" in resp.json()["detail"]


def test_put_malformed_yaml_returns_422_and_leaves_file(client, catalog):
    resp = client.put(
        "/api/strategies/raw", headers=AUTH, json={"content": "strategies: : :\n  - x"}
    )
    assert resp.status_code == 422
    assert catalog.read_text() == VALID_CATALOG


def test_put_then_next_scan_load_uses_new_catalog(client, catalog):
    """Hot reload: after PUT, load_strategies() (called fresh every scan tick)
    sees the new catalog with no process restart."""
    from predictions.strategies import load_strategies

    new_text = "strategies:\n  hotswapped:\n    triggers:\n      - min_lead: 9\n"
    client.put("/api/strategies/raw", headers=AUTH, json={"content": new_text})
    loaded = load_strategies()  # what evaluate_strategies calls each tick
    assert [s.name for s in loaded] == ["hotswapped"]
