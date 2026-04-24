# Soccer Strategy Backtest — Design Spec

**Date:** 2026-04-24
**Status:** Approved for implementation planning
**Related code:** `src/predictions/scanner.py` (WHAT_IF_STRATEGIES — live-backtesting precedent)

## Summary

A new "Strategy Backtest" page in the dashboard that lets the user define a soccer trading strategy (trigger conditions, bankroll, bet sizing) and see how it would have performed on historical matches in a selected league and date range. Win-rate analytics are always shown; financial P&L is shown only for matches where Kalshi prices were observed by the live scanner.

## Problem

The live scanner runs 5 hardcoded what-if strategies in parallel against live markets and stores outcomes in `StretchOpportunity`. There's no way to:

- Tune strategy parameters freely and see the effect immediately
- Evaluate a strategy over historical matches the scanner didn't scan
- Inspect the specific matches a strategy would have bet on (for failure-mode reasoning)

This feature closes that gap for soccer first (EPL, La Liga, Bundesliga). It relies on football-data.org for historical match data and falls back to winrate-only when Kalshi prices aren't available in the main DB.

## Non-goals

- **Not a live trading feature.** Backtest never places orders; it's read-only.
- **Not multi-sport in v1.** Only soccer (EPL, La Liga, Bundesliga). Other sports are explicit follow-ups.
- **Not a strategy-optimization tool.** No auto-parameter-sweeping, no "best strategy" search. User manually picks params; the page shows the result.
- **Not a perfect P&L simulator.** Price matching is best-effort fuzzy; matches without observed prices are winrate-only (no invented price).
- **Not a saved-strategy feature.** Strategy params are transient UI state; no persistence across sessions.
- **Not a migration of the live scanner.** ESPN remains the live data source; football-data.org is used only for historical backtest.

## Scope

### In scope (v1)

- Soccer only: `PL` (EPL), `PD` (La Liga), `BL1` (Bundesliga) — football-data.org competition codes.
- Historical match data via football-data.org v4, authed with the user's existing API key.
- Ephemeral cache at `/tmp/soccer-cache.db` (prod) / `./soccer-cache.db` (dev) — gitignored.
- Fire-once trigger on `(min_minute, min_lead)`.
- Optional `min_yes_price` filter, active only when a price is observed.
- Bankroll with `bet_percent` sizing (compounding across chronologically-ordered bets).
- Match log (color-coded win/loss), 8 summary cards, bankroll-curve chart (conditional on observed prices).

### Out of scope (v1)

- Other sports, other leagues.
- Persistent cache with S3 backup.
- Extra charts (distributions, win-rate-by-bucket, histograms).
- Saved strategies / shareable URLs.
- Async / progress-stream backend.
- Backtesting against live or in-progress games.

## Strategy model

### The bet

When the trigger fires mid-match, simulate a YES order on the "leading-team-wins" Kalshi market. Settlement:

- **WIN** — leading team wins the match in regulation (90 min + stoppage).
- **LOSS** — match ends in a draw *or* the trailing team comes back to win.

EPL, La Liga, and Bundesliga league play never goes to extra time, so regulation = full time for this scope.

### Parameters

| Param                   | Range / values         | Default         | Description                                             |
|-------------------------|------------------------|-----------------|---------------------------------------------------------|
| `league`                | `PL`, `PD`, `BL1`      | `PL`            | Competition code.                                       |
| `date_from`             | ISO date               | today − 1 month | Range start (inclusive).                                |
| `date_to`               | ISO date, ≤ today      | today           | Range end (inclusive).                                  |
| `min_minute`            | 1–90                   | 75              | Earliest match minute trigger can fire.                 |
| `min_lead`              | 1–5                    | 2               | Minimum goal differential for trigger.                  |
| `min_yes_price`         | 0–99 cents             | 0               | Observed-price filter. 0 = disabled.                    |
| `initial_balance_cents` | ≥ 1000 (= $10)         | 100000 ($1000)  | Starting bankroll.                                      |
| `bet_percent`           | 0.005–0.10 (0.5%–10%)  | 0.02            | Fraction of *current* bankroll per bet (compounding).   |

### Trigger semantics — fire-once

- First minute ≥ `min_minute` at which `abs(home_score − away_score) >= min_lead` → fire the bet.
- Subsequent score changes (goals by either side) do not modify, unwind, or re-fire the bet. Matches real mechanics: you can't un-buy a contract.
- If the condition is never satisfied, no bet is placed. The match is excluded from `trades[]` but counted in `matches_scanned`.
- Walk order: minute 1 → 90. All goals stamped to a given minute are applied (in `sequence` order) *before* the trigger check at that minute.
- Stoppage-time goals (`stoppage > 0`) are applied at the end of their parent minute (45 for first-half stoppage, 90 for second-half). This is a minor simplification — acceptable because trigger minima are typically ≥ 75 (first-half stoppage never matters) and a 90+3 trigger would be impossible to act on in real life anyway.

### Result resolution

- `leading_side == 'home'` → WIN iff `match.home_score > match.away_score`.
- `leading_side == 'away'` → WIN iff `match.away_score > match.home_score`.
- Otherwise LOSS.

### P&L per trade

Let `p = observed_yes_ask_cents`.

**If `p` is known:**

- `bet_cents = round(bankroll_cents * bet_percent)`
- `count = max(1, bet_cents // p)` — integer contracts, floor division
- `cost_cents = count * p`
- `pnl_cents = count * (100 - p)` on WIN, `-cost_cents` on LOSS
- `bankroll_cents += pnl_cents` **before** processing the next chronological trade

**If `p` is unknown:**

- `count`, `cost_cents`, `pnl_cents` all `null`
- `bankroll_cents` unchanged (pass-through for the curve)
- Match still counts in winrate and appears in the log with a "no price" annotation

### `min_yes_price` filter semantics

Applied only when both conditions hold:

1. `min_yes_price > 0`, **and**
2. An observed price exists for this match/trigger.

If both hold and `observed < min_yes_price` → skip the trade entirely (not in `matches_bet_on`, not in winrate).

If no observation exists → filter is **ignored**; the trade proceeds (avoids penalising matches where data is simply missing).

## Data sources

### Match data (primary): football-data.org v4

- **Auth:** `FOOTBALL_DATA_API_KEY` env var. The user already has a key; it's added to `.env.example` and wired as an SST secret.
- **Rate limit:** 10 requests / minute on the free tier. We stay within this by caching FINISHED matches permanently within the cache file's lifetime.
- **Endpoints used:**
  - `GET /v4/competitions/{code}/matches?dateFrom=YYYY-MM-DD&dateTo=YYYY-MM-DD` — fixture list with final scores. One call covers the whole requested date range per league.
  - `GET /v4/matches/{id}` — full match detail including `.goals[]` with `.minute`, `.injuryTime`, `.team.id`, `.type` (for own-goal detection).
- **Competition codes:** `PL`, `PD`, `BL1`.

### Kalshi prices (secondary, best-effort): existing `predictions.db`

No new data collection. Reuses the `Opportunity` table already written by the live scanner.

**`find_observed_yes_ask(match, fire_minute, leading_side)` algorithm:**

1. Normalise team names via a hardcoded alias map (starts with ~30 top teams across three leagues; grown manually as needed).
2. Query `Opportunity` rows where `created_at ∈ [kickoff_at − 30 min, kickoff_at + 150 min]` AND the ticker / market metadata indicates soccer.
3. Filter to rows whose `event_title` / `market_title` fuzzy-matches **both** teams AND whose `market_title` references the leading team.
4. Pick the row whose `created_at` is closest to `kickoff_at + fire_minute × 60 s`.
5. Return its `yes_ask` (integer cents). If no row matches at any step, return `None`.

Fuzzy matching: case-insensitive substring check after normalization, with alias lookup for known mismatches (e.g., "Man Utd" vs "Manchester United"). Deliberately conservative — a non-match is better than a wrong match.

## Architecture

```
┌───────────────────────────────────────────────────────────────────────┐
│ dashboard/app/backtest/page.tsx                                       │
│   Controls → POST /api/backtest/soccer → summary + log + chart        │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                  /api/[...path]/route.ts (proxy, injects Bearer)
                                 │
                                 ▼
┌───────────────────────────────────────────────────────────────────────┐
│ src/predictions/api.py                                                │
│   POST /api/backtest/soccer → backtest.run_backtest(req)              │
└───────────────────────────────────────────────────────────────────────┘
                                 │
                 ┌───────────────┴───────────────┐
                 ▼                               ▼
   ┌──────────────────────────────┐  ┌──────────────────────────────┐
   │ src/predictions/backtest.py  │  │ src/predictions/             │
   │                              │  │   soccer_cache.py            │
   │ • simulate_match()           │  │                              │
   │ • find_observed_yes_ask()    │  │ • FootballDataClient         │
   │ • run_backtest()             │  │ • SoccerMatch / SoccerGoal   │
   │ • BacktestRequest/Response   │  │ • ensure_matches_cached()    │
   │                              │  │                              │
   │ Reads: predictions.db        │  │ Reads/Writes: soccer-cache.db│
   │   (Opportunity)              │  │ Calls: football-data.org v4  │
   └──────────────────────────────┘  └──────────────────────────────┘
```

### Modules and responsibilities

#### `src/predictions/soccer_cache.py` (NEW, ~300 loc)

- `FootballDataClient` — thin async HTTP client.
  - Carries the API key in `X-Auth-Token` header.
  - Exposes `list_matches(league, date_from, date_to)` and `get_match_goals(match_id)`.
  - On HTTP 429 (rate-limited), raises `RateLimitedError`. No in-client retry — the orchestrator decides.
- `SoccerMatch`, `SoccerGoal` SQLAlchemy ORM models.
- `SoccerCacheEngine`-equivalent module-level setup:
  - Reads `SOCCER_CACHE_DB_PATH` (default: repo-root `./soccer-cache.db` in dev, `/tmp/soccer-cache.db` in prod via SST env).
  - Owns `create_engine(...)` and its own `sessionmaker` (does NOT share with `db.py`).
  - `init_soccer_db()` — create tables + inline ALTER migrations (same pattern as `db.py.init_db()`).
- `ensure_matches_cached(league, date_from, date_to) -> EnsureResult` where `EnsureResult = (matches: list[SoccerMatch], partial: bool, missing_count: int)`:
  1. Call `list_matches()` — one API call.
  2. For each returned fixture with `status == 'FINISHED'` and no existing row in `soccer_matches`: call `get_match_goals()`, insert transactionally.
  3. If `RateLimitedError` mid-loop: break, mark `partial=True`, count remaining.
  4. Return matches currently in cache for (league, date range).

#### `src/predictions/backtest.py` (NEW, ~400 loc)

- Pydantic models: `BacktestRequest`, `BacktestResponse`, `BacktestSummary`, `BacktestTrade`, `BacktestCurvePoint`.
- `simulate_match(match: SoccerMatch, req: BacktestRequest) -> Trigger | None` — pure function, no DB.
- `find_observed_yes_ask(match, fire_minute, leading_side, session) -> int | None` — reads `predictions.db.Opportunity`.
- Team-alias map + fuzzy-matching helpers (internal).
- `run_backtest(req: BacktestRequest) -> BacktestResponse` — orchestrator:
  1. `ensure_matches_cached(…)` via `soccer_cache`.
  2. Open a `predictions.db` session.
  3. For each match in chronological order: simulate, look up price, apply `min_yes_price` filter, resolve result, compute P&L, update bankroll, append trade row + curve point.
  4. Build summary.

#### `src/predictions/api.py` (modified)

- Add `POST /api/backtest/soccer` protected by the existing `_check_token` dependency.
- Validates body via `BacktestRequest` model, calls `backtest.run_backtest()`, returns `BacktestResponse`.

### Frontend

#### `dashboard/app/backtest/page.tsx` (NEW, ~500 loc)

- Client component. Auth state comes from the existing `predictions_auth` cookie (same pattern as the main dashboard).
- Layout per UI section below.
- `recharts` for the bankroll line chart (already present in the dashboard's deps).
- Match log: simple `map` render for v1 — if performance becomes an issue with year-long ranges, add virtualization (`react-window` or equivalent) in a follow-up.
- Calls `fetch('/api/backtest/soccer', { method: 'POST', body: JSON.stringify(form) })`. The existing `app/api/[...path]/route.ts` proxy injects the bearer token server-side; no token on the client.

#### `dashboard/app/page.tsx` (modified)

- Add a header link *"Strategy Backtest"* → `/backtest`.

## Storage

### `soccer-cache.db` schema

```sql
CREATE TABLE soccer_matches (
    id           TEXT     PRIMARY KEY,   -- "fd:<football_data_id>"
    competition  TEXT     NOT NULL,      -- 'PL' | 'PD' | 'BL1'
    kickoff_at   DATETIME NOT NULL,
    home_team    TEXT     NOT NULL,
    away_team    TEXT     NOT NULL,
    home_score   INT      NOT NULL,      -- final-time score
    away_score   INT      NOT NULL,
    status       TEXT     NOT NULL,      -- always 'FINISHED' for cached rows
    fetched_at   DATETIME NOT NULL
);
CREATE INDEX idx_soccer_matches_comp_kickoff
    ON soccer_matches(competition, kickoff_at);

CREATE TABLE soccer_goals (
    match_id     TEXT     NOT NULL REFERENCES soccer_matches(id),
    sequence     INT      NOT NULL,      -- 1..N in chronological order
    minute       INT      NOT NULL,      -- regulation minute
    stoppage     INT      NOT NULL DEFAULT 0,
    side         TEXT     NOT NULL,      -- 'home' | 'away'
    is_own_goal  INT      NOT NULL DEFAULT 0,
    PRIMARY KEY (match_id, sequence)
);
```

Migrations: inline `ALTER TABLE` checks in `soccer_cache.init_soccer_db()` (same pattern as `predictions.db.init_db()`).

### Cache policy

- Only `status == 'FINISHED'` matches are written. Scheduled / in-progress / postponed / cancelled are skipped entirely.
- Once written, rows are permanent within the lifetime of the cache file. Match results don't change after the whistle.
- No TTL, no refresh logic.
- File is **ephemeral in production** (`/tmp/soccer-cache.db` → lost on container restart). Rebuild happens lazily on next backtest request.

## API contract

```
POST /api/backtest/soccer
Authorization: Bearer <API_TOKEN>
Content-Type: application/json
```

### Request body

```json
{
  "league": "PL",
  "date_from": "2026-03-24",
  "date_to": "2026-04-24",
  "min_minute": 75,
  "min_lead": 2,
  "min_yes_price": 0,
  "initial_balance_cents": 100000,
  "bet_percent": 0.02
}
```

### Response 200

```json
{
  "summary": {
    "matches_scanned": 107,
    "matches_bet_on": 38,
    "matches_with_price_data": 12,
    "wins": 30,
    "losses": 8,
    "win_rate": 0.789,
    "initial_balance_cents": 100000,
    "final_balance_cents": 104532,
    "pnl_cents": 4532,
    "pnl_pct": 0.0453
  },
  "trades": [
    {
      "match_id": "fd:437893",
      "kickoff_at": "2026-04-22T19:00:00Z",
      "league": "PL",
      "home_team": "Arsenal",
      "away_team": "Chelsea",
      "final_home": 2,
      "final_away": 1,
      "fired_at_minute": 76,
      "score_at_fire_home": 2,
      "score_at_fire_away": 0,
      "leading_side": "home",
      "result": "win",
      "observed_yes_ask_cents": 94,
      "count": 21,
      "cost_cents": 1974,
      "pnl_cents": 126,
      "bankroll_after_cents": 100126
    }
  ],
  "bankroll_curve": [
    { "t": "2026-03-24T00:00:00Z", "balance_cents": 100000 },
    { "t": "2026-04-22T19:00:00Z", "balance_cents": 100126 }
  ],
  "partial": false,
  "missing_count": 0
}
```

### Field nullability in `trades[]`

`observed_yes_ask_cents`, `count`, `cost_cents`, `pnl_cents` are `null` when no price was observed. `bankroll_after_cents` is the running bankroll at that point in the chronological sequence (unchanged from the previous trade when P&L is null).

### `bankroll_curve` contents

First entry is always `{ t: date_from T00:00:00Z, balance_cents: initial_balance_cents }`. Subsequent entries are appended for each trade where `observed_yes_ask_cents` is non-null, at `t = kickoff_at`, with the post-trade bankroll. Trades with a null observed price do **not** add a curve point — the curve only shows the observed-price P&L progression. If no trade had an observed price, the curve contains just the starting point, and the UI hides the chart entirely.

### Error responses

- `400 Bad Request` — validation failure: `date_from > date_to`, `date_to > today`, unknown league, out-of-range numeric param, etc.
- `401 Unauthorized` — missing / invalid bearer token.
- `503 Service Unavailable` — `FOOTBALL_DATA_API_KEY` env var is unset.

### Partial results

When the football-data.org rate limit is hit mid-fetch:

- Backend returns HTTP 200 with `partial: true` and `missing_count: N` (matches not yet cached).
- `summary` and `trades` reflect only the successfully-cached matches.
- UI shows a yellow banner: *"N matches not yet cached — retry in ~60 s."* Submit button re-enables.

## UI specification

### Layout

```
┌──────────────────────────────────────────────────────────────────────┐
│  ← Dashboard                         Strategy Backtest        [user] │
├────────────────────────────┬─────────────────────────────────────────┤
│ Parameters                 │ Results                                  │
│  League       [dropdown]   │  8 summary cards                         │
│  Date from    [date]       │  Bankroll curve  (conditional)           │
│  Date to      [date]       │  Match log       (colored rows)          │
│  Min minute   [slider]     │                                          │
│  Min lead     [slider]     │                                          │
│  Min yes $    [slider]     │                                          │
│  Initial $    [number]     │                                          │
│  Bet %        [slider]     │                                          │
│  [Run backtest]            │                                          │
│  ⓘ footnote                │                                          │
└────────────────────────────┴─────────────────────────────────────────┘
```

- Header: page title + back link to `/` + user email.
- Left rail (~300 px): parameter controls, Run button, info footnote.
- Main area: 8 summary cards → conditional bankroll chart → match log.

### Controls

- **League** dropdown — EPL / La Liga / Bundesliga (mapped to `PL` / `PD` / `BL1`).
- **Date range** — two date inputs with defaults (today − 1 month, today). Client-side validation: `from ≤ to`, `to ≤ today`.
- **Trigger:**
  - `min_minute` slider 1–90 (default 75) with numeric readout.
  - `min_lead` slider 1–5 (default 2) with numeric readout.
  - `min_yes_price` slider 0–99 (default 0). Label reads *"0 = disabled"* at the zero position.
- **Bankroll:**
  - `initial_balance` number input (min $10, default $1000).
  - `bet_percent` slider 0.5%–10% (default 2.0%) with % readout.
- **Run backtest** button — disabled while request is in flight.
- Footnote: *"P&L reflects only matches with observed Kalshi prices. All bets are counted in win rate."*

### Summary cards (8)

Order: Scanned, Bet on, Win rate %, Wins, Losses, P&L %, P&L $, w/ prices.

Each card: label + value. P&L % and P&L $ are color-coded (green positive, red negative). "w/ prices" shows `N / M` format (matches with prices out of total bet on).

### Bankroll curve

- Recharts `LineChart`; X-axis = kickoff time; Y-axis = bankroll $ (derived from cents).
- Rendered only if `summary.matches_with_price_data > 0`.
- Otherwise replaced with a short placeholder: *"No Kalshi price data observed in this range; bankroll curve unavailable."*

### Match log

- Linear list, chronologically oldest-first.
- Each row ~60 px, two-line layout:
  - Line 1: date, matchup, final score, win/loss emoji.
  - Line 2: fire-minute + score at fire, bet $ / P&L / bankroll OR "(no price) · winrate only".
- Color: green-tinted background for WIN, red-tinted for LOSS.

### Loading / empty / error states

- **In flight:** disable submit, skeleton on summary cards, "Running backtest…" label on button.
- **Partial (200 + partial=true):** yellow banner at top of main area.
- **Empty (no fixtures):** *"No fixtures found for this league and date range."*
- **Error:** red banner at top with message; summary / log empty.

## Environment / deployment

Add to `.env.example`:

```
FOOTBALL_DATA_API_KEY=your-key-here
SOCCER_CACHE_DB_PATH=./soccer-cache.db    # dev default; prod overrides to /tmp
```

Add to `sst.config.ts`:

- `FootballDataApiKey` SST secret.
- Inject `FOOTBALL_DATA_API_KEY` into the ECS task environment.
- Inject `SOCCER_CACHE_DB_PATH=/tmp/soccer-cache.db` into the ECS task environment.

Add to `.gitignore`:

```
soccer-cache.db
soccer-cache.db-journal
```

## Testing

Minimum set before claiming done:

### Python — `uv run pytest`

- **`simulate_match`** unit tests, with synthetic matches:
  - Fires at the correct minute when the lead was established earlier.
  - Fires at exactly `min_minute` when the condition already holds.
  - Does not fire when lead never reaches threshold.
  - Does not fire when condition holds before `min_minute`.
  - Fire-once: a subsequent goal that extends the lead does not produce a second trigger or alter the first.
  - Stoppage-time goal at 90+N triggers correctly at minute 90.
  - Own-goal is attributed to the scoring side's opponent (i.e., counts toward the beneficiary).
- **`find_observed_yes_ask`** with a seeded `Opportunity` table:
  - Matches via exact + alias + fuzzy team-name matching.
  - Returns `None` when no matching market is found.
  - Picks the `Opportunity` row whose `created_at` is closest to `kickoff + fire_minute × 60 s` when multiple candidates exist.
  - Ignores rows outside the `[kickoff − 30 min, kickoff + 150 min]` window.
- **`run_backtest`** integration test with seeded soccer-cache + `Opportunity` fixtures:
  - P&L arithmetic: WIN path, LOSS path, mixed sequences.
  - Bankroll compounding respects chronological order.
  - `min_yes_price` filter: skips when `observed < min_yes_price`; ignored when no observation.
  - No-price match counted in winrate and appears in log with null P&L.
- **`soccer_cache.ensure_matches_cached`** tests (mocked HTTP):
  - Cache hit: no API calls when all matches are already present.
  - Cache miss: fetches details only for missing matches.
  - Rate limit: returns `partial=True, missing_count=N`.

### Manual dashboard QA

- Load `/backtest`, run backtest with defaults on EPL, confirm render.
- Confirm bankroll chart appears only when `w/ prices > 0`.
- Confirm error banner on bad date range (server-side 400).
- Confirm partial banner when rate-limit is hit (force via an aggressive range on a cold cache).
- Confirm no regressions on the main dashboard `/`.

## Risks

- **Team-name fuzzy matching may yield false positives** — attaching the wrong market's price to a match. Mitigation: conservative matching (require both team names present in the event title); every fuzzy match is logged for audit; the alias map is the systematic-correction surface.
- **football-data.org API changes** could break the fetch flow. Mitigation: narrow client module; own only the fields we need; keep the raw JSON boundary small.
- **Rate-limit pressure on first-run big ranges.** A full EPL season from scratch = ~380 matches × 1 detail call each = ~38 min of wall clock at 10 req/min. The partial-response UX mitigates UX-wise; the user simply retries.
- **Conflating "no bet placed" with "no data"** in the UI is easy to get wrong. Summary labels ("Scanned", "Bet on", "w/ prices") are deliberately explicit to prevent this.
- **Stoppage-time simplification** (goals collapsed to parent minute 90) produces a trigger timestamp that's off by 1–6 minutes from reality. Acceptable because a minute-90+ trigger is already untradeable in practice.

## Open questions / explicit follow-ups

- **Persistent cache.** If `/tmp` rebuild time becomes a pain point in practice, wire soccer-cache.db into the existing 30-min S3 snapshot loop (`scanner.backup_loop`) following the same pattern as `predictions.db`.
- **Team-alias map.** V1 ships with a hardcoded map of ~30 top teams across the three leagues. Growing it lazily by recording observed Kalshi-market ↔ football-data-match pairings (persisted in the cache DB) is deferred.
- **Other sports.** NBA, NFL, NHL, MLB, MLS, etc. — each needs its own historical data source. Out of v1 by design.
- **Strategy persistence / sharing.** Not in v1. Would require a DB-backed strategy-record table.
- **Async / progress streaming.** Synchronous request/response with partial-on-rate-limit is v1. If users run multi-season backtests where sync times exceed 30 s consistently, consider SSE / polling.
