"""Golden + invariant tests for the sport registry (predictions.sports).

The golden literals are copied verbatim from the module-level dicts that
predated the registry (espn.py, scanner.py, api.py, db.py at beb1904).
They pin the derived views to the exact production-effective values so the
registry swap is provably behavior-preserving. The one deliberate absence:
scanner.py's dead MIN_SCORE_LEAD values (NBA/NCAAMB 8) — production reads
the config defaults (12), and the registry keeps the production values.
"""

from predictions import sports
from predictions.sports import SERIES, SPORTS

# --- Golden: derived views reproduce the pre-registry dicts exactly ---


def test_kalshi_to_espn_golden():
    assert sports.KALSHI_TO_ESPN == {
        "KXNBAGAME": "basketball/nba",
        "KXNHLGAME": "hockey/nhl",
        "KXNFLGAME": "football/nfl",
        "KXMLBGAME": "baseball/mlb",
        "KXNCAAMBGAME": "basketball/mens-college-basketball",
        "KXNCAAFBGAME": "football/college-football",
        "KXEPLGAME": "soccer/eng.1",
        "KXLALIGAGAME": "soccer/esp.1",
        "KXMLSGAME": "soccer/usa.1",
        "KXMLBSTGAME": "baseball/mlb",
    }


def test_kalshi_to_espn_excludes_unmatchable_series():
    assert "KXUFCFIGHT" not in sports.KALSHI_TO_ESPN
    assert "KXTENNISGAME" not in sports.KALSHI_TO_ESPN


def test_sport_final_period_golden():
    assert sports.SPORT_FINAL_PERIOD == {
        "basketball/nba": 4,
        "hockey/nhl": 3,
        "football/nfl": 4,
        "baseball/mlb": 9,
        "basketball/mens-college-basketball": 2,
        "football/college-football": 4,
        "mma/ufc": 5,
        "soccer/eng.1": 2,
        "soccer/esp.1": 2,
        "soccer/usa.1": 2,
    }


def test_sport_family_to_paths_golden():
    assert sports.SPORT_FAMILY_TO_PATHS == {
        "football": frozenset({"soccer/eng.1", "soccer/esp.1", "soccer/usa.1"}),
        "basketball": frozenset({"basketball/nba", "basketball/mens-college-basketball"}),
        "baseball": frozenset({"baseball/mlb"}),
        "american_football": frozenset({"football/nfl", "football/college-football"}),
        "hockey": frozenset({"hockey/nhl"}),
        "tennis": frozenset(),
    }


def test_sport_path_to_family_golden():
    assert sports.SPORT_PATH_TO_FAMILY == {
        "soccer/eng.1": "football",
        "soccer/esp.1": "football",
        "soccer/usa.1": "football",
        "basketball/nba": "basketball",
        "basketball/mens-college-basketball": "basketball",
        "baseball/mlb": "baseball",
        "football/nfl": "american_football",
        "football/college-football": "american_football",
        "hockey/nhl": "hockey",
    }


def test_sport_period_length_secs_golden():
    assert sports.SPORT_PERIOD_LENGTH_SECS == {
        "basketball/nba": 12 * 60,
        "basketball/mens-college-basketball": 20 * 60,
        "football/nfl": 15 * 60,
        "football/college-football": 15 * 60,
        "hockey/nhl": 20 * 60,
        "soccer/eng.1": 45 * 60,
        "soccer/esp.1": 45 * 60,
        "soccer/usa.1": 45 * 60,
        "mma/ufc": 5 * 60,
    }


def test_clockless_and_count_up_golden():
    assert sports.CLOCKLESS_SPORT_PATHS == frozenset({"baseball/mlb"})
    assert sports.COUNT_UP_SPORT_PATHS == frozenset(
        {"soccer/eng.1", "soccer/esp.1", "soccer/usa.1"}
    )


def test_sports_game_series_golden():
    assert sports.SPORTS_GAME_SERIES == [
        "KXNBAGAME",
        "KXNFLGAME",
        "KXNHLGAME",
        "KXMLBGAME",
        "KXNCAAMBGAME",
        "KXNCAAFBGAME",
        "KXUFCFIGHT",
        "KXLALIGAGAME",
        "KXEPLGAME",
        "KXMLSGAME",
        "KXMLBSTGAME",
        "KXTENNISGAME",
    ]


def test_sport_display_names_golden():
    assert sports.SPORT_DISPLAY_NAMES == {
        "basketball/nba": "NBA",
        "basketball/mens-college-basketball": "NCAAMB",
        "hockey/nhl": "NHL",
        "football/nfl": "NFL",
        "football/college-football": "NCAAFB",
        "baseball/mlb": "MLB",
        "soccer/eng.1": "EPL",
        "soccer/esp.1": "La Liga",
        "soccer/usa.1": "MLS",
        "mma/ufc": "UFC",
    }


def test_sport_clock_dir_golden():
    assert sports.SPORT_CLOCK_DIR == {
        "basketball/nba": "down",
        "basketball/mens-college-basketball": "down",
        "hockey/nhl": "down",
        "football/nfl": "down",
        "football/college-football": "down",
        "baseball/mlb": "none",
        "soccer/eng.1": "up",
        "soccer/esp.1": "up",
        "soccer/usa.1": "up",
        "mma/ufc": "down",
    }


def test_ticker_prefix_map_labels_match_old_map():
    """Old api.py map used short prefixes; derived map uses full series
    prefixes. Equivalence is per-ticker: every real trade ticker starts with
    its full series prefix, so labels must agree with the old short-prefix map.
    """
    old_map = [
        ("KXMLBST", "MLBST"),
        ("KXMLB", "MLB"),
        ("KXNBA", "NBA"),
        ("KXNHL", "NHL"),
        ("KXNFL", "NFL"),
        ("KXNCAAMB", "NCAAMB"),
        ("KXNCAAFB", "NCAAFB"),
        ("KXEPL", "EPL"),
        ("KXLALIGA", "La Liga"),
        ("KXMLSG", "MLS"),
        ("KXUFC", "UFC"),
    ]

    def old_label(t: str) -> str:
        for prefix, label in old_map:
            if t.startswith(prefix):
                return label
        return "Other"

    def new_label(t: str) -> str:
        for prefix, label in sports.TICKER_PREFIX_LABELS:
            if t.startswith(prefix):
                return label
        return "Other"

    for series in SERIES:
        ticker = f"{series.prefix}-26JUL07SEADAL-SEA"
        assert new_label(ticker) == old_label(ticker), series.prefix


def test_ticker_prefix_labels_most_specific_first():
    prefixes = [p for p, _ in sports.TICKER_PREFIX_LABELS]
    assert prefixes == sorted(prefixes, key=len, reverse=True)


# --- Golden pin: config defaults keep production-effective values ---


def test_config_defaults_per_sport_golden():
    from predictions.db import _CONFIG_DEFAULTS

    leads = {k: v for k, v in _CONFIG_DEFAULTS.items() if k.startswith("lead:")}
    assert leads == {
        "lead:basketball/nba": "12",
        "lead:basketball/mens-college-basketball": "12",
        "lead:hockey/nhl": "2",
        "lead:football/nfl": "10",
        "lead:football/college-football": "10",
        "lead:baseball/mlb": "3",
        "lead:soccer/eng.1": "2",
        "lead:soccer/esp.1": "2",
        "lead:soccer/usa.1": "2",
        "lead:mma/ufc": "0",
    }
    finals = {k: v for k, v in _CONFIG_DEFAULTS.items() if k.startswith("final_seconds:")}
    assert finals == {
        "final_seconds:basketball/nba": "180",
        "final_seconds:basketball/mens-college-basketball": "180",
        "final_seconds:hockey/nhl": "300",
        "final_seconds:football/nfl": "300",
        "final_seconds:football/college-football": "300",
        "final_seconds:soccer/eng.1": "4500",
        "final_seconds:soccer/esp.1": "4500",
        "final_seconds:soccer/usa.1": "4500",
        "final_seconds:mma/ufc": "300",
    }


# --- Invariants: impossible to state before the registry existed ---


def test_every_matchable_series_references_a_sport():
    paths = {s.path for s in SPORTS}
    for series in SERIES:
        if series.matchable:
            assert series.sport_path in paths, series.prefix


def test_matchable_series_family_is_in_strategy_vocabulary():
    by_path = {s.path: s for s in SPORTS}
    for series in SERIES:
        if series.matchable:
            assert series.sport_path is not None, series.prefix
            assert by_path[series.sport_path].family in sports.FAMILIES, series.prefix


def test_clock_semantics_consistent():
    for sport in SPORTS:
        if sport.clock == "none":
            assert sport.period_secs is None, sport.path
            assert sport.default_final_seconds is None, sport.path
        else:
            assert sport.period_secs is not None, sport.path
            assert sport.default_final_seconds is not None, sport.path


def test_sport_paths_and_series_prefixes_unique():
    paths = [s.path for s in SPORTS]
    assert len(paths) == len(set(paths))
    prefixes = [s.prefix for s in SERIES]
    assert len(prefixes) == len(set(prefixes))
