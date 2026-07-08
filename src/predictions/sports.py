"""Sport registry: the single canonical catalog of sports and series.

Two tables — Sport (keyed by ESPN sport path) and Series (keyed by Kalshi
series prefix) — plus derived views that replace the per-sport dicts that
previously lived in espn.py, scanner.py, api.py, and db.py. Pure data:
imports nothing from this package so even db.py can depend on it.
"""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

ClockDir = Literal["down", "up", "none"]


@dataclass(frozen=True)
class Sport:
    path: str
    family: str
    clock: ClockDir
    final_period: int
    period_secs: int | None
    display_name: str
    default_lead: int
    default_final_seconds: int | None


@dataclass(frozen=True)
class Series:
    prefix: str
    label: str | None
    sport_path: str | None
    matchable: bool = True


# Strategy-vocabulary families (UK terminology, Phase 2 D-02 OVERRIDE):
# an explicit set, not derived from SPORTS, so enabling a new sport can't
# silently widen what strategies.yaml `sport:` accepts.
FAMILIES: frozenset[str] = frozenset(
    {"football", "basketball", "baseball", "american_football", "hockey", "tennis"}
)

SPORTS: tuple[Sport, ...] = (
    Sport("basketball/nba", "basketball", "down", 4, 12 * 60, "NBA", 12, 180),
    Sport(
        "basketball/mens-college-basketball",
        "basketball",
        "down",
        2,
        20 * 60,
        "NCAAMB",
        12,
        180,
    ),
    Sport("hockey/nhl", "hockey", "down", 3, 20 * 60, "NHL", 2, 300),
    Sport("football/nfl", "american_football", "down", 4, 15 * 60, "NFL", 10, 300),
    Sport(
        "football/college-football",
        "american_football",
        "down",
        4,
        15 * 60,
        "NCAAFB",
        10,
        300,
    ),
    Sport("baseball/mlb", "baseball", "none", 9, None, "MLB", 3, None),
    Sport("soccer/eng.1", "football", "up", 2, 45 * 60, "EPL", 2, 4500),
    Sport("soccer/esp.1", "football", "up", 2, 45 * 60, "La Liga", 2, 4500),
    Sport("soccer/usa.1", "football", "up", 2, 45 * 60, "MLS", 2, 4500),
    Sport("mma/ufc", "mma", "down", 5, 5 * 60, "UFC", 0, 300),
)

SERIES: tuple[Series, ...] = (
    Series("KXNBAGAME", "NBA", "basketball/nba"),
    Series("KXNFLGAME", "NFL", "football/nfl"),
    Series("KXNHLGAME", "NHL", "hockey/nhl"),
    Series("KXMLBGAME", "MLB", "baseball/mlb"),
    Series("KXNCAAMBGAME", "NCAAMB", "basketball/mens-college-basketball"),
    Series("KXNCAAFBGAME", "NCAAFB", "football/college-football"),
    # UFC markets are scanned but deliberately never matched to ESPN.
    Series("KXUFCFIGHT", "UFC", "mma/ufc", matchable=False),
    Series("KXLALIGAGAME", "La Liga", "soccer/esp.1"),
    Series("KXEPLGAME", "EPL", "soccer/eng.1"),
    Series("KXMLSGAME", "MLS", "soccer/usa.1"),
    Series("KXMLBSTGAME", "MLBST", "baseball/mlb"),
    Series("KXTENNISGAME", None, None, matchable=False),
)

SPORT_BY_PATH: dict[str, Sport] = {s.path: s for s in SPORTS}

# --- Derived views (drop-in replacements for the pre-registry dicts) ---

KALSHI_TO_ESPN: dict[str, str] = {
    s.prefix: s.sport_path for s in SERIES if s.matchable and s.sport_path
}

SPORT_FINAL_PERIOD: dict[str, int] = {s.path: s.final_period for s in SPORTS}

SPORT_FAMILY_TO_PATHS: dict[str, frozenset[str]] = {
    family: frozenset(
        path for path in KALSHI_TO_ESPN.values() if SPORT_BY_PATH[path].family == family
    )
    for family in FAMILIES
}

SPORT_PATH_TO_FAMILY: dict[str, str] = {
    path: family for family, paths in SPORT_FAMILY_TO_PATHS.items() for path in paths
}

SPORT_PERIOD_LENGTH_SECS: dict[str, int] = {
    s.path: s.period_secs for s in SPORTS if s.period_secs is not None
}

CLOCKLESS_SPORT_PATHS: frozenset[str] = frozenset(s.path for s in SPORTS if s.clock == "none")

COUNT_UP_SPORT_PATHS: frozenset[str] = frozenset(s.path for s in SPORTS if s.clock == "up")

SPORTS_GAME_SERIES: list[str] = [s.prefix for s in SERIES]

SPORT_DISPLAY_NAMES: dict[str, str] = {s.path: s.display_name for s in SPORTS}

SPORT_CLOCK_DIR: dict[str, ClockDir] = {s.path: s.clock for s in SPORTS}

# Most-specific-first so KXMLBSTGAME wins over KXMLBGAME.
TICKER_PREFIX_LABELS: list[tuple[str, str]] = sorted(
    ((s.prefix, s.label) for s in SERIES if s.label is not None),
    key=lambda pair: len(pair[0]),
    reverse=True,
)

CONFIG_LEAD_DEFAULTS: dict[str, str] = {f"lead:{s.path}": str(s.default_lead) for s in SPORTS}

CONFIG_FINAL_SECONDS_DEFAULTS: dict[str, str] = {
    f"final_seconds:{s.path}": str(s.default_final_seconds)
    for s in SPORTS
    if s.default_final_seconds is not None
}


def crossed_final_clock(
    sport_path: str, clock_seconds: float, thresholds: Mapping[str, int]
) -> bool | None:
    """Direction-aware end-of-game clock check.

    Returns whether a clocked sport has crossed its end-of-game threshold
    (count-down: at/under; count-up: at/over). Returns None for clockless
    sports, which have no clock threshold — callers decide what that means.
    thresholds maps sport_path -> final_seconds.
    """
    clock = SPORT_CLOCK_DIR[sport_path]
    if clock == "none":
        return None
    if clock == "up":
        return clock_seconds >= thresholds[sport_path]
    return clock_seconds <= thresholds[sport_path]
