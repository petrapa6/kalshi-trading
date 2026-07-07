"""Pure bet-decision stage (#8).

Shared by the live scan path and the strategy path. No I/O: callers
read config / clocks and pass plain values in.
"""

from datetime import datetime, timedelta

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


def live_trigger(min_yes_price: int, min_lead: int) -> Trigger:
    """The live scan path's bet decision as a Trigger: price band + lead.

    Timing is enforced upstream — the ESPN cache only holds final-minutes
    games — so no min_minute here.
    """
    return Trigger(min_yes_price=min_yes_price, max_yes_price=99, min_lead=min_lead)


def trigger_matches(
    trigger: Trigger,
    *,
    family: str | None,
    elapsed: int | None,
    score_diff: int,
    yes_ask: int,
) -> bool:
    """Evaluate a single trigger's AND-conditions.

    Missing field on the trigger means "no constraint on that dimension"
    (per Phase 2 D-03 / STR-02). For min_minute on a clockless sport
    (elapsed is None), the trigger does NOT match.
    """
    if trigger.sport is not None and trigger.sport != family:
        return False
    if trigger.min_minute is not None:
        if elapsed is None:
            return False
        if elapsed < trigger.min_minute:
            return False
    if trigger.min_lead is not None and score_diff < trigger.min_lead:
        return False
    if trigger.min_yes_price is not None and yes_ask < trigger.min_yes_price:
        return False
    if trigger.max_yes_price is not None and yes_ask > trigger.max_yes_price:
        return False
    return True
