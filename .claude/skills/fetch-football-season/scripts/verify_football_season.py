#!/usr/bin/env python3
"""Verify a fetched football-season JSON: running goal tally must equal final_score.

Default mode is read-only — reports any matches where the last goal's running
score doesn't match the `final_score` field (or where final_score is non-zero
but `goals` is empty). Exits 0 if clean, 1 if any mismatches found.

With --fix --league LEAGUE, mismatched matches are re-fetched from ESPN's
scoreboard for their date and rebuilt via build_match(). If the rebuild is
consistent, it replaces the original record. Matches still mismatched after
re-fetch are reported as unfixable (likely missing goals in ESPN's data).

Usage:
    python3 verify_football_season.py epl_2024_25_season.json
    python3 verify_football_season.py epl_2024_25_season.json --fix --league EPL
"""

import argparse
import importlib.util
import json
import sys
import time
import urllib.error
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("ffs", HERE / "fetch_football_season.py")
assert _spec is not None and _spec.loader is not None, "sibling fetch_football_season.py missing"
ffs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ffs)


def _parse_score(s: str) -> tuple[int, int]:
    h, a = s.split(":")
    return int(h), int(a)


def _running(goals: list[dict]) -> tuple[int, int]:
    if not goals:
        return 0, 0
    return _parse_score(goals[-1]["score"])


def is_consistent(match: dict) -> bool:
    return _running(match["goals"]) == _parse_score(match["final_score"])


def find_mismatches(matches: list[dict]) -> list[dict]:
    return [m for m in matches if not is_consistent(m)]


def refetch(scoreboard_url: str, match: dict) -> dict | None:
    d = date.fromisoformat(match["date"])
    try:
        events = ffs.fetch_day(scoreboard_url, d)
    except urllib.error.URLError as exc:
        print(f"  refetch error for {match['id']}: {exc}", file=sys.stderr)
        return None
    for e in events:
        if e.get("id") == match["id"]:
            return ffs.build_match(e)
    return None


def _describe(m: dict) -> str:
    rh, ra = _running(m["goals"])
    return (
        f"  {m['id']} {m['date']} {m['home_team']} vs {m['away_team']}: "
        f"running={rh}:{ra} vs final={m['final_score']}"
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument("json_file", type=Path, help="Path to season JSON file")
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Re-fetch mismatched matches and write fixes back to the file",
    )
    parser.add_argument(
        "--league",
        choices=sorted(ffs.LEAGUES),
        metavar="LEAGUE",
        help=f"League code (required with --fix): {', '.join(sorted(ffs.LEAGUES))}",
    )
    args = parser.parse_args()

    if args.fix and not args.league:
        parser.error("--fix requires --league")

    data = json.loads(args.json_file.read_text())
    matches: list[dict] = data["matches"]
    bad = find_mismatches(matches)

    print(f"File:          {args.json_file}")
    print(f"Total matches: {len(matches)}")
    print(f"Mismatches:    {len(bad)}")

    if not bad:
        print("All running goal totals match final_score. ✓")
        sys.exit(0)

    for m in bad[:20]:
        print(_describe(m))
    if len(bad) > 20:
        print(f"  ... and {len(bad) - 20} more")

    if not args.fix:
        sys.exit(1)

    info = ffs.LEAGUES[args.league]
    scoreboard_url = f"{ffs.ESPN_BASE}/{info['path']}/scoreboard"
    print(f"\nRe-fetching {len(bad)} match(es) from ESPN ({args.league}) ...")

    idx_by_id = {m["id"]: i for i, m in enumerate(matches)}
    fixed = 0
    still_bad: list[dict] = []
    for m in bad:
        new_m = refetch(scoreboard_url, m)
        time.sleep(ffs.REQUEST_DELAY)
        if new_m is None:
            still_bad.append(m)
            continue
        if is_consistent(new_m):
            matches[idx_by_id[m["id"]]] = new_m
            fixed += 1
        else:
            still_bad.append(new_m)

    if fixed:
        args.json_file.write_text(json.dumps({"matches": matches}, indent=2))

    print(f"\nFixed:     {fixed}")
    print(f"Still bad: {len(still_bad)}")
    for m in still_bad:
        print(_describe(m))

    sys.exit(0 if not still_bad else 1)


if __name__ == "__main__":
    main()
