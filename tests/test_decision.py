"""Direct unit tests for the pure bet-decision stage (#8)."""

from datetime import datetime, timedelta, timezone

from predictions.decision import live_trigger, trigger_matches, within_expiry_window
from predictions.strategies import Trigger


def test_price_band_boundaries():
    trigger = Trigger(min_yes_price=91, max_yes_price=99)

    def decide(yes_ask: int) -> bool:
        return trigger_matches(trigger, family=None, elapsed=None, score_diff=0, yes_ask=yes_ask)

    assert not decide(90)
    assert decide(91)
    assert decide(99)
    assert not decide(100)


def test_lead_threshold_boundary():
    trigger = Trigger(min_lead=12)

    def decide(lead: int) -> bool:
        return trigger_matches(trigger, family=None, elapsed=None, score_diff=lead, yes_ask=95)

    assert not decide(11)
    assert decide(12)


def test_timing_gate_min_minute():
    trigger = Trigger(min_minute=45)

    def decide(elapsed: int | None) -> bool:
        return trigger_matches(trigger, family=None, elapsed=elapsed, score_diff=0, yes_ask=95)

    assert not decide(None)  # clockless sport never satisfies a minute gate
    assert not decide(44)
    assert decide(45)


def test_sport_family_constraint():
    trigger = Trigger(sport="basketball")

    def decide(family: str | None) -> bool:
        return trigger_matches(trigger, family=family, elapsed=None, score_diff=0, yes_ask=95)

    assert decide("basketball")
    assert not decide("american_football")
    assert not decide(None)


def test_expiry_window_bounds():
    now = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)

    def exp(delta: timedelta) -> str:
        return (now + delta).isoformat().replace("+00:00", "Z")

    assert within_expiry_window(exp(timedelta(hours=1)), now)
    assert within_expiry_window(exp(timedelta(hours=-1)), now)
    assert not within_expiry_window(exp(timedelta(hours=13)), now)  # future game in series
    assert not within_expiry_window(exp(timedelta(hours=-13)), now)  # stale market


def test_expiry_window_missing_or_malformed_passes():
    now = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    assert within_expiry_window("", now)
    assert within_expiry_window("not-a-timestamp", now)


def test_live_trigger_is_price_band_plus_lead():
    trigger = live_trigger(min_yes_price=91, min_lead=12)

    def decide(yes_ask: int, lead: int) -> bool:
        return trigger_matches(trigger, family=None, elapsed=None, score_diff=lead, yes_ask=yes_ask)

    assert decide(94, 12)
    assert not decide(90, 12)  # under price floor
    assert not decide(100, 12)  # over 99c cap
    assert not decide(94, 11)  # lead too small
    # no sport/timing constraint: clockless + unknown family still passes
    assert decide(94, 12) and decide(99, 30)
