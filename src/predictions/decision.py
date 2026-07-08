"""Pure bet-decision stage (#8).

Shared by the live scan path and the strategy path. No I/O: callers
read config / clocks and pass plain values in.
"""

from collections.abc import Mapping
from datetime import datetime, timedelta

from predictions.sports import crossed_final_clock
from predictions.strategies import Trigger

EXPIRY_WINDOW = timedelta(hours=12)


def within_expiry_window(exp_str: str, now: datetime, window: timedelta = EXPIRY_WINDOW) -> bool:
    """True when expected expiration is within ±window of now.

    Filters out other games in the series (e.g. Game 2 vs Game 1).
    Empty or unparsable timestamps pass — expiry is a narrowing filter,
    not a data-quality gate.
    """
    if not exp_str:
        return True
    try:
        exp_time = datetime.fromisoformat(exp_str.replace("Z", "+00:00"))
        return abs(exp_time - now) <= window
    except (ValueError, TypeError):
        return True


def trigger_matches(
    trigger: Trigger,
    *,
    family: str | None,
    elapsed: int | None,
    score_diff: int,
    yes_ask: int,
    sport_path: str | None = None,
    clock_seconds: float | None = None,
    thresholds: Mapping[str, int] | None = None,
    volume: int | None = None,
) -> bool:
    """Evaluate a single trigger's AND-conditions.

    Missing field on the trigger means "no constraint on that dimension"
    (per Phase 2 D-03 / STR-02). For min_minute on a clockless sport
    (elapsed is None), the trigger does NOT match.

    final_minutes reuses the live path's direction-aware clock check
    (crossed_final_clock); it never matches clockless sports, which have no
    end-of-game clock threshold. Callers pass the game's clock context and
    the per-sport thresholds as plain values.
    """
    if trigger.sport is not None and trigger.sport != family:
        return False
    if trigger.sport_path is not None and trigger.sport_path != sport_path:
        return False
    if trigger.min_minute is not None:
        if elapsed is None:
            return False
        if elapsed < trigger.min_minute:
            return False
    if trigger.final_minutes:
        if sport_path is None or clock_seconds is None or thresholds is None:
            return False
        if crossed_final_clock(sport_path, clock_seconds, thresholds) is not True:
            return False
    if trigger.min_lead is not None and score_diff < trigger.min_lead:
        return False
    if trigger.min_volume is not None and (volume is None or volume < trigger.min_volume):
        return False
    if trigger.min_yes_price is not None and yes_ask < trigger.min_yes_price:
        return False
    if trigger.max_yes_price is not None and yes_ask > trigger.max_yes_price:
        return False
    return True
