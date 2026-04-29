---
name: fetch-football-season
description: Use when fetching complete historical football/soccer season match data with per-minute goal times. Covers EPL, La Liga, Bundesliga, Serie A, Ligue 1, UCL, MLS.
---

# fetch-football-season

## Overview

Script that fetches all completed matches for a football league season from ESPN's public API (no auth, no external dependencies). Outputs structured JSON: one entry per match, with each goal as `{time, score}`.

## Usage

```bash
python3 ~/.claude/skills/fetch-football-season/scripts/fetch_football_season.py LEAGUE YEAR [--out FILE]
```

`YEAR` is the **end-year** of the season — `2025` fetches 2024/25 for split-season leagues.

```bash
# EPL 2024/25 season → epl_2025.json
python3 ... EPL 2025

# Bundesliga 2023/24 → bundesliga_2024.json
python3 ... BUNDESLIGA 2024

# MLS 2025 calendar season → mls_2025.json
python3 ... MLS 2025 --out mls_2025.json
```

Runtime: ~2 min per season (~300 day-by-day requests at 0.3 s each).

## Supported Leagues

| Code | League | Season format |
|---|---|---|
| `EPL` / `PL` | English Premier League | Aug–Jun (split) |
| `LALIGA` | La Liga | Aug–Jun (split) |
| `BUNDESLIGA` | Bundesliga | Aug–Jun (split) |
| `SERIEA` | Serie A | Aug–Jun (split) |
| `LIGUE1` | Ligue 1 | Aug–Jun (split) |
| `UCL` | UEFA Champions League | Aug–Jun (split) |
| `MLS` | Major League Soccer | Mar–Dec |

## Output Format

```json
{
  "matches": [
    {
      "id": "704279",
      "date": "2024-08-16",
      "home_team": "Manchester United",
      "away_team": "Fulham",
      "final_score": "1:0",
      "goals": [
        { "time": "87|0",  "score": "1:0" }
      ]
    },
    {
      "id": "704350",
      "date": "2024-09-14",
      "home_team": "Brighton & Hove Albion",
      "away_team": "Ipswich Town",
      "final_score": "0:0",
      "goals": []
    }
  ]
}
```

**`time`** format: `"minute|stoppage"` — e.g. `"90|3"` for a 90+3' goal.  
**`score`** reflects the running score **after** that goal (home:away).  
Goalless matches are included with `"goals": []`.  
Own goals are attributed to the **beneficiary** side.

## Implementation Notes

- Walks day-by-day across the season; deduplicates events by ESPN event ID.
- Uses `scoringPlay: true` (not `type.text`) to identify goals reliably.
- ESPN clock format is `"90'+5'"` for stoppage time — both apostrophe positions handled.
- Own-goal flip: ESPN records the conceding team on own-goal details; script inverts to beneficiary.
