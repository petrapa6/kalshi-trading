#!/usr/bin/env python3
"""Fetch all matches for a football season with per-minute goal data from ESPN's public API.

No external dependencies — uses only Python stdlib.

Output: JSON file with every completed match; goalless matches appear with goals=[].

Usage:
    python3 fetch_football_season.py EPL 2025
    python3 fetch_football_season.py BUNDESLIGA 2024 --out bundesliga_2024.json

YEAR is the end-year of the season:
    EPL 2025  ->  2024/25 season  (Aug 2024 – Jun 2025)
    MLS 2025  ->  2025 season     (Mar 2025 – Dec 2025)
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, timedelta

ESPN_BASE = "https://site.api.espn.com/apis/site/v2/sports/soccer"
REQUEST_DELAY = 0.3  # seconds between requests

# split_season=True: year is end-year (European Aug–Jun format)
# split_season=False: year IS the season year (e.g. MLS)
LEAGUES: dict[str, dict] = {
    "EPL":        {"path": "eng.1",          "name": "English Premier League",   "split": True,  "shootouts": False},
    "PL":         {"path": "eng.1",          "name": "English Premier League",   "split": True,  "shootouts": False},
    "LALIGA":     {"path": "esp.1",          "name": "La Liga",                  "split": True,  "shootouts": False},
    "BUNDESLIGA": {"path": "ger.1",          "name": "Bundesliga",               "split": True,  "shootouts": False},
    "SERIEA":     {"path": "ita.1",          "name": "Serie A",                  "split": True,  "shootouts": False},
    "LIGUE1":     {"path": "fra.1",          "name": "Ligue 1",                  "split": True,  "shootouts": False},
    "UCL":        {"path": "uefa.champions", "name": "UEFA Champions League",    "split": True,  "shootouts": False},
    "MLS":        {"path": "usa.1",          "name": "Major League Soccer",      "split": False, "shootouts": True},
}


def season_dates(league_key: str, year: int) -> tuple[date, date]:
    info = LEAGUES[league_key]
    if info["split"]:
        return date(year - 1, 8, 1), date(year, 6, 1)
    return date(year, 3, 1), date(year, 12, 31)


def fetch_day(scoreboard_url: str, d: date) -> list[dict]:
    params = urllib.parse.urlencode({"dates": d.strftime("%Y%m%d"), "limit": 50})
    req = urllib.request.Request(
        f"{scoreboard_url}?{params}",
        headers={"User-Agent": "Mozilla/5.0"},
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("events", [])


def _parse_minute(display: str) -> tuple[int, int]:
    """Parse ESPN clock strings to (minute, stoppage).

    ESPN uses two formats:
      "76'"    -> (76, 0)
      "90'+5'" -> (90, 5)   apostrophe appears after base minute too
    """
    s = display.strip()
    m = re.match(r"^(\d+)'?\+(\d+)'?$", s)
    if m:
        return int(m.group(1)), int(m.group(2))
    m = re.match(r"^(\d+)'?$", s)
    if m:
        return int(m.group(1)), 0
    return 0, 0


def build_match(event: dict, *, shootouts: bool = False) -> dict | None:
    """Build a match JSON object from an ESPN event. Returns None if not completed."""
    comps = event.get("competitions", [])
    if not comps:
        return None
    comp = comps[0]
    if not comp.get("status", {}).get("type", {}).get("completed", False):
        return None

    home_team = away_team = home_score = away_score = ""
    team_side: dict[str, str] = {}  # id_str -> "home" | "away"

    for c in comp.get("competitors", []):
        side = c.get("homeAway", "")
        team = c.get("team", {})
        display = team.get("displayName", team.get("shortDisplayName", ""))
        score = c.get("score", "")
        # Map both competitor slot id and team.id — ESPN uses either on goal details
        for id_key in (str(team.get("id", "")), str(c.get("id", ""))):
            if id_key:
                team_side[id_key] = side
        if side == "home":
            home_team, home_score = display, score
        elif side == "away":
            away_team, away_score = display, score

    home_running = away_running = 0
    goals = []
    for detail in comp.get("details", []):
        if not detail.get("scoringPlay", False):
            continue

        clock = detail.get("clock", {})
        minute, stoppage = _parse_minute(clock.get("displayValue", ""))

        detail_team_id = str(detail.get("team", {}).get("id", ""))
        side = team_side.get(detail_team_id, "unknown")

        # ESPN's scoreboard `details` records the beneficiary team on own-goal
        # entries, so trust team_id as-is (verified against EPL 2024/25 own-goals
        # by Tuanzebe and Pinnock — both tagged with the benefiting team's id).

        if side == "home":
            home_running += 1
        else:
            away_running += 1

        goals.append({"time": f"{minute}|{stoppage}", "score": f"{home_running}:{away_running}"})

    # MLS (and similar shootout leagues): ESPN marks penalty kicks as
    # scoringPlay=true, but final_score reflects only regulation+ET goals.
    # Truncate the goals list at the point the final score is first reached.
    if shootouts:
        try:
            home_final = int(home_score)
            away_final = int(away_score)
            if home_running != home_final or away_running != away_final:
                if home_final == 0 and away_final == 0:
                    # 0:0 final — every recorded goal is a penalty kick
                    goals = []
                else:
                    truncated: list[dict] = []
                    for g in goals:
                        truncated.append(g)
                        s = g["score"].split(":")
                        if int(s[0]) == home_final and int(s[1]) == away_final:
                            break
                    goals = truncated
        except (ValueError, IndexError):
            pass

    return {
        "id": event.get("id", ""),
        "date": event.get("date", "")[:10],
        "home_team": home_team,
        "away_team": away_team,
        "final_score": f"{home_score}:{away_score}",
        "goals": goals,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("league", choices=sorted(LEAGUES), metavar="LEAGUE",
                        help=f"League code: {', '.join(sorted(LEAGUES))}")
    parser.add_argument("year", type=int, metavar="YEAR",
                        help="Season end-year (e.g. 2025 fetches 2024/25 for split-season leagues)")
    parser.add_argument("--out", metavar="FILE",
                        help="Output JSON path (default: {league}_{year}.json)")
    args = parser.parse_args()

    league_key = args.league.upper()
    info = LEAGUES[league_key]
    start, end = season_dates(league_key, args.year)
    out_path = args.out or f"{league_key.lower()}_{args.year}.json"
    scoreboard_url = f"{ESPN_BASE}/{info['path']}/scoreboard"

    season_label = f"{args.year - 1}/{args.year}" if info["split"] else str(args.year)
    print(f"Fetching {info['name']} {season_label} ({start} → {end}) …")

    all_events: dict[str, dict] = {}
    days = (end - start).days + 1
    for i in range(days):
        d = start + timedelta(days=i)
        try:
            events = fetch_day(scoreboard_url, d)
        except urllib.error.URLError as exc:
            print(f"  {d}: request error — {exc}", file=sys.stderr)
            time.sleep(2)
            continue

        new = 0
        for e in events:
            if e["id"] not in all_events:
                all_events[e["id"]] = e
                new += 1
        if events:
            print(f"  {d}: {len(events)} event(s) (+{new} new)")
        time.sleep(REQUEST_DELAY)

    print(f"\nTotal unique matches collected: {len(all_events)}")

    matches = []
    shootouts = info.get("shootouts", False)
    for event in all_events.values():
        m = build_match(event, shootouts=shootouts)
        if m:
            matches.append(m)

    matches.sort(key=lambda m: (m["date"], m["id"]))
    total_goals = sum(len(m["goals"]) for m in matches)
    goalless = sum(1 for m in matches if not m["goals"])

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"matches": matches}, f, indent=2)

    print(f"Wrote {len(matches)} matches ({goalless} goalless), {total_goals} goals → {out_path}")


if __name__ == "__main__":
    main()
