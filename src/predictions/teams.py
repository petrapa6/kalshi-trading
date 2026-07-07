"""Team identity reconciliation: one home for matching ESPN, Kalshi, and
API-Football team identities.

Two surfaces of the same concept, differing by key space:
- abbreviation reconciliation (ESPN scoreboard codes vs Kalshi ticker codes),
  used by the live matcher in espn.py;
- full-name canonicalization (aliases, accent/noise stripping), used by the
  backtest matcher against recorded market titles.
"""

import re
import unicodedata

# ESPN abbreviations that differ from Kalshi ticker abbreviations.
# Only entries where ESPN and Kalshi use DIFFERENT codes.
# Map ESPN abbreviation → list of Kalshi equivalents to check.
ESPN_TO_KALSHI_ABBR: dict[str, list[str]] = {
    # NBA
    "GS": ["GSW"],
    "UTAH": ["UTA"],
    "SA": ["SAS"],
    # MLS
    "DC": ["DCU"],
    "LA": ["LAG", "LA"],  # ESPN "LA" = LA Galaxy; Kalshi uses "LAG"
    # NFL
    "JAX": ["JAC"],
}


def espn_to_kalshi_codes(espn_abbr: str) -> list[str]:
    """Return Kalshi codes that an ESPN abbreviation could map to."""
    codes = ESPN_TO_KALSHI_ABBR.get(espn_abbr.upper(), [])
    # Always include the original ESPN abbreviation itself
    if espn_abbr.upper() not in [c.upper() for c in codes]:
        codes = [espn_abbr.upper()] + codes
    return codes


# Canonical team-name aliases. Each entry maps an alias to its canonical
# display name. Lookup is case-insensitive after normalize_team. This is
# the systematic-correction surface — grow lazily as Kalshi/API-Football
# mismatches are observed.
TEAM_ALIASES: dict[str, str] = {
    # Premier League
    "man utd": "manchester united",
    "man united": "manchester united",
    "manchester utd": "manchester united",
    "man city": "manchester city",
    "spurs": "tottenham hotspur",
    "tottenham": "tottenham hotspur",
    "wolves": "wolverhampton wanderers",
    "brighton": "brighton hove albion",
    "brighton and hove albion": "brighton hove albion",
    "brighton & hove albion": "brighton hove albion",
    "newcastle": "newcastle united",
    "nott'm forest": "nottingham forest",
    "leeds": "leeds united",
    "west ham": "west ham united",
    # La Liga
    "atletico madrid": "atletico madrid",
    "atletico": "atletico madrid",
    "atleti": "atletico madrid",
    "real": "real madrid",
    "real madrid": "real madrid",
    "barca": "barcelona",
    "barça": "barcelona",
    "fc barcelona": "barcelona",
    "athletic bilbao": "athletic club",
    "real sociedad": "real sociedad",
    # Bundesliga
    "bayern": "bayern munchen",
    "bayern munich": "bayern munchen",
    "bayern munchen": "bayern munchen",
    "fc bayern munchen": "bayern munchen",
    "dortmund": "borussia dortmund",
    "bvb": "borussia dortmund",
    "leverkusen": "bayer leverkusen",
    "gladbach": "borussia monchengladbach",
    "monchengladbach": "borussia monchengladbach",
    "rb leipzig": "rb leipzig",
    "leipzig": "rb leipzig",
    "schalke": "schalke 04",
    "union berlin": "union berlin",
    "eintracht frankfurt": "eintracht frankfurt",
    "frankfurt": "eintracht frankfurt",
    "freiburg": "sc freiburg",
    "stuttgart": "vfb stuttgart",
}

_NOISE_PREFIXES = ("1. ", "fc ", "afc ")
_NOISE_SUFFIXES = (" fc", " cf", " sc", " ac", " afc", " cfc")


def normalize_team(name: str) -> str:
    """Lower-case, strip accents + leading/trailing club suffixes, collapse whitespace."""
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    s = s.lower().strip()
    # Strip noise prefixes BEFORE alphanumeric filtering so patterns like
    # "1. " (with a literal dot) can still match before the dot is normalized away.
    for pref in _NOISE_PREFIXES:
        if s.startswith(pref):
            s = s[len(pref) :].strip()
    s = re.sub(r"[^a-z0-9\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    for suf in _NOISE_SUFFIXES:
        if s.endswith(suf):
            s = s[: -len(suf)].strip()
    return s


def canonical_team(name: str) -> str:
    """Return the canonical (alias-resolved) form of a team name."""
    norm = normalize_team(name)
    return TEAM_ALIASES.get(norm, norm)


def canonicalize_title(market_title: str) -> str:
    """Tokenize a normalized title and rewrite alias phrases to canonical forms.

    Walks tokens left-to-right; at each position tries the longest matching
    alias-phrase and advances past the consumed tokens. Once an alias is
    consumed, shorter aliases cannot re-enter the same span — this prevents
    "real" → "real madrid" from firing on the "real" in "real sociedad".
    """
    tokens = normalize_team(market_title).split()
    # Pre-split aliases into token tuples so membership comparison is token-level.
    alias_items = sorted(
        ((alias.split(), canon) for alias, canon in TEAM_ALIASES.items()),
        key=lambda item: -len(item[0]),
    )
    out: list[str] = []
    i = 0
    n = len(tokens)
    while i < n:
        matched = False
        for alias_tokens, canon in alias_items:
            k = len(alias_tokens)
            if k <= n - i and tokens[i : i + k] == alias_tokens:
                out.append(canon)
                i += k
                matched = True
                break
        if not matched:
            out.append(tokens[i])
            i += 1
    return " ".join(out)


def market_mentions_both_teams(market_title: str, team_a: str, team_b: str) -> bool:
    """Conservative containment check: the title must contain both canonical
    forms as substrings. Prefers a non-match over a wrong match.
    """
    title_canon = canonicalize_title(market_title)
    a = canonical_team(team_a)
    b = canonical_team(team_b)
    return a in title_canon and b in title_canon
