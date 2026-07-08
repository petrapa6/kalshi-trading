"""Direct unit tests for the pure bet-decision stage (#8)."""

from datetime import datetime, timedelta, timezone

from predictions.decision import trigger_matches, within_expiry_window
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


def test_sport_path_constraint():
    trigger = Trigger(sport_path="hockey/nhl")

    def decide(sport_path: str | None) -> bool:
        return trigger_matches(
            trigger, family=None, elapsed=None, score_diff=0, yes_ask=95, sport_path=sport_path
        )

    assert decide("hockey/nhl")
    assert not decide("basketball/nba")
    assert not decide(None)


def test_min_volume_threshold():
    trigger = Trigger(min_volume=200)

    def decide(volume: int | None) -> bool:
        return trigger_matches(
            trigger, family=None, elapsed=None, score_diff=0, yes_ask=95, volume=volume
        )

    assert not decide(199)
    assert decide(200)
    assert not decide(None)  # no volume data can't satisfy a volume gate


def test_final_minutes_count_down_sport():
    trigger = Trigger(final_minutes=True)
    thresholds = {"basketball/nba": 180}

    def decide(clock_seconds: float) -> bool:
        return trigger_matches(
            trigger,
            family=None,
            elapsed=None,
            score_diff=0,
            yes_ask=95,
            sport_path="basketball/nba",
            clock_seconds=clock_seconds,
            thresholds=thresholds,
        )

    assert decide(170)  # inside the final-minutes window
    assert not decide(200)  # threshold not yet crossed


def test_final_minutes_count_up_sport():
    trigger = Trigger(final_minutes=True)
    thresholds = {"soccer/eng.1": 4500}

    def decide(clock_seconds: float) -> bool:
        return trigger_matches(
            trigger,
            family=None,
            elapsed=None,
            score_diff=0,
            yes_ask=95,
            sport_path="soccer/eng.1",
            clock_seconds=clock_seconds,
            thresholds=thresholds,
        )

    assert decide(4600)  # past the threshold
    assert not decide(4400)  # before the threshold


def test_final_minutes_never_matches_clockless_sport():
    trigger = Trigger(final_minutes=True)

    matched = trigger_matches(
        trigger,
        family=None,
        elapsed=None,
        score_diff=0,
        yes_ask=95,
        sport_path="baseball/mlb",
        clock_seconds=0.0,
        thresholds={},
    )
    assert not matched


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


def test_expiry_window_naive_timestamp_passes():
    # Kalshi timestamp without a timezone offset must not raise (naive - aware)
    now = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
    assert within_expiry_window("2026-07-07T22:00:00", now)
