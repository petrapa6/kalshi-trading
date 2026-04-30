"""Integration test: verify Kalshi WebSocket connects, subscribes, and receives data."""

import asyncio
import os

import pytest
from dotenv import load_dotenv

from predictions.kalshi_client import KalshiClient, KalshiWebSocket

load_dotenv()


def _load_client() -> KalshiClient | None:
    key_id = os.environ.get("KALSHI_API_KEY")
    key_pem = os.environ.get("KALSHI_PRIVATE_KEY")
    key_path = os.environ.get("KALSHI_PRIVATE_KEY_PATH")
    if not key_id:
        return None
    if key_pem:
        return KalshiClient.from_key_string(key_id, key_pem)
    if key_path:
        return KalshiClient.from_key_file(key_id, key_path)
    return None


@pytest.mark.skipif(
    not os.environ.get("KALSHI_API_KEY"),
    reason="Needs live Kalshi credentials (KALSHI_API_KEY + key)",
)
async def test_ws_connects_and_receives():
    client = _load_client()
    if client is None:
        pytest.skip("no Kalshi private key configured")

    balance = await client.get_balance()
    assert "balance" in balance

    test_series = ["KXNBAGAME", "KXNHLGAME", "KXMLBGAME", "KXMLSGAME", "KXEPLGAME"]
    test_tickers: list[str] = []
    for series in test_series:
        try:
            data = await client.get_events(
                status="open",
                series_ticker=series,
                with_nested_markets=True,
                limit=5,
            )
        except Exception:
            continue
        for event in data.get("events", []):
            for market in event.get("markets", []):
                if market.get("status") in ("active", "open"):
                    test_tickers.append(market["ticker"])
                    if len(test_tickers) >= 3:
                        break
            if len(test_tickers) >= 3:
                break
        if len(test_tickers) >= 3:
            break

    if not test_tickers:
        pytest.skip("no active markets right now — WS subscription untestable")

    ws = KalshiWebSocket(client)
    await ws.connect()

    received: list[dict] = []

    def on_any(msg: dict) -> None:
        received.append(msg)

    ws.on("ticker", on_any)
    ws.on("subscribed", on_any)

    await ws.subscribe(["ticker"], test_tickers)

    try:
        await asyncio.wait_for(ws.listen(), timeout=10)
    except asyncio.TimeoutError:
        pass
    finally:
        await ws.close()

    got_subscribed = any(m.get("type") == "subscribed" for m in received)
    assert got_subscribed or received, "WebSocket connected but received no messages at all"
