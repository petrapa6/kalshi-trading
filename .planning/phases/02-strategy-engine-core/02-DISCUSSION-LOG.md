# Phase 2: Strategy Engine Core - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-30
**Phase:** 02-strategy-engine-core
**Areas discussed:** Schema vocabulary & cross-engine fit, File location/shape/validation, Dashboard data path, Backtest preset UX

---

## Schema vocabulary & cross-engine fit

### Q1 — `min_minute` semantics for non-soccer sports

| Option | Description | Selected |
|--------|-------------|----------|
| Game-clock minutes elapsed since start | Sport-aware: soccer = goal minute; NBA = `(period−1)·period_length + (period_length − clock_seconds)` / 60. min_minute=75 = "last 25%-ish" universally. | ✓ |
| Soccer-only field; non-soccer uses different fields in v1.3 | Stays soccer-specific; non-soccer ignores it for now. | |
| Wall-clock minutes since market open | Sport-agnostic but loses meaning across halftime / breaks. | |

**User's choice:** Game-clock minutes elapsed since start (Recommended)
**Notes:** Locks D-01. Phase 3 needs per-sport `total_game_seconds` lookup.

### Q2 — `sport` field format

| Option | Description | Selected |
|--------|-------------|----------|
| ESPN sport_path (`soccer/eng.1`, `basketball/nba`) | Reuses scanner taxonomy. Backtest needs filename → sport_path map. | ✓ |
| Coarse sport tag (`soccer`, `basketball`) | Simpler; loses league granularity. | |
| Sport list per trigger | More flexible; introduces list-vs-string ambiguity. | |

**User's choice:** ESPN sport_path (Recommended)
**Notes:** Locks D-02. Backtest needs file→sport_path lookup.

### Q3 — `sport` matching semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Exact match; missing sport = matches all sports | Aligns with REQUIREMENTS §STR-02 "missing field = no constraint". | ✓ |
| Prefix match (sport_path startsWith) | Fewer triggers for cross-league strategies; ambiguous. | |
| Dual exact/prefix | Most ergonomic; hidden behavior swap. | |

**User's choice:** Exact match (Recommended)
**Notes:** Locks D-03.

### Q4 — Initial `strategies.yaml` content

| Option | Description | Selected |
|--------|-------------|----------|
| Fresh reference strategies | 2–4 hand-crafted, schema-aligned. | (combined) |
| Translate the 5 WHAT_IF strategies verbatim | Preserves history; lead_pct doesn't translate cleanly. | |
| Empty file with comments only | Cleanest; awkward dashboard demo path. | |

**User's choice:** "Pick 1) fresh reference strategies but add commented translation of the 5 existing strategies into the file"
**Notes:** Locks D-04. Hybrid: 2–4 fresh strategies live, 5 WHAT_IF translations as commented examples.

---

## File location, top-level shape, validation strictness

### Q1 — Top-level YAML shape

| Option | Description | Selected |
|--------|-------------|----------|
| Dict-of-strategies (`strategies:` map keyed by name) | Matches WHAT_IF shape; unique names by construction. | ✓ |
| List with explicit `name` field | Preserves declaration order; allows duplicate-name validation. | |
| Top-level keys ARE strategy names | Leanest; risks colliding with future top-level config. | |

**User's choice:** Dict-of-strategies (Recommended)
**Notes:** Locks D-05.

### Q2 — Unknown field handling

| Option | Description | Selected |
|--------|-------------|----------|
| Strict reject (Pydantic `extra=forbid`) | Catches typos; explicit schema evolution. | ✓ |
| Pass-through with warning | Forward-compat; typos pass silently. | |
| Ignore silently | Simplest; typos invisible. | |

**User's choice:** Strict reject (Recommended)
**Notes:** Locks D-06.

### Q3 — Partial validation failures

| Option | Description | Selected |
|--------|-------------|----------|
| All-or-nothing | Any error rejects whole file; loader proceeds with 0 strategies. | ✓ |
| Per-strategy: skip invalid | Graceful degradation; can hide bugs. | |
| Fail loud / crash on startup | Strict mode; conflicts with STR-01 missing-file behavior. | |

**User's choice:** All-or-nothing (Recommended)
**Notes:** Locks D-07.

### Q4 — `STRATEGIES_PATH` env override timing

| Option | Description | Selected |
|--------|-------------|----------|
| Implement now | One-line read; locks contract for Phase 3 + tests. | ✓ |
| Defer to Phase 3 | Hardcode path now. | |

**User's choice:** Implement now (Recommended)
**Notes:** Locks D-08. Update `.env.example`.

---

## Dashboard data path

### Q1 — Data path mechanism

| Option | Description | Selected |
|--------|-------------|----------|
| New `GET /api/strategies` endpoint | Single source of truth in Python; existing proxy pattern. | ✓ |
| Build-time YAML import via Webpack | Static bundle; redeploy required on YAML edit. | |
| Generated JSON sibling at build time | Static import; rebuild forgotten easily. | |
| Server Component reads YAML | Bypasses auth boundary; FS-coupled. | |

**User's choice:** New `GET /api/strategies` endpoint (Recommended)
**Notes:** Locks D-09.

### Q2 — API response shape

| Option | Description | Selected |
|--------|-------------|----------|
| List of objects with `name` field | Direct dropdown mapping; YAML order preserved. | ✓ |
| Dict-of-strategies (mirror YAML) | 1:1 mirror; dropdown extraction work in TS. | |
| Bare list, no top-level wrapper | Simpler; no future-extensibility. | |

**User's choice:** List of objects with `name` field (Recommended)
**Notes:** Locks D-10.

---

## Backtest preset UX

### Q1 — `min_yes_price` / `max_yes_price` slider behavior in backtest

| Option | Description | Selected |
|--------|-------------|----------|
| Drive `contract_price_cents` and act as filter bounds | Sliders functional but max_yes_price decorative. | |
| Show both sliders; ignore both in backtest math | Sliders for preset roundtrip only. | |
| Replace `contract_price_cents` with both sliders + per-trade price simulation | Loses determinism. | |
| Keep `contract_price_cents`; ADD min/max yes_price decorative-only | Three price sliders; busy. | |
| **(User's freeform answer)** Keep `contract_price_cents` (backtest-only); add **info text** that real trading uses min/max_yes_price | No new sliders; honest about scope. | ✓ |

**User's choice:** "Keep `contract_price_cents` as-is (backtest only) and add info (text only) that real trading uses min/max_yes_price"
**Notes:** Locks D-11. Intentionally narrows BT-07's literal text.

### Q2 — Multi-trigger UX shape

| Option | Description | Selected |
|--------|-------------|----------|
| First trigger wins; transparency note | Honors REQUIREMENTS literally; minimal UI. | |
| Sub-dropdown to pick which trigger to load | Most powerful; overengineered for v1.2. | |
| Backtest evaluates all triggers as OR (no slider pre-fill) | Most accurate; sliders disabled. | |
| Refuse: multi-trigger strategies don't appear in dropdown | Tightest scoping. | |
| **(User's freeform answer)** Render every trigger as its own slider group with (+)/(-)/divider; financial attrs stay single | Lightweight strategy builder. | ✓ |

**User's choice:** "Add separate sliders for every trigger - use light UI divider between triggers. … (+) button below the last trigger and bottom UI divider … Financial attributes (capital, contract_price_cents, etc) - keep only once at the top."
**Notes:** Locks D-14. Significant UX expansion; engine becomes multi-trigger.

### Q3 — Multi-trigger engine semantics

| Option | Description | Selected |
|--------|-------------|----------|
| First-goal-matching-any-trigger fires; sport-mismatched skipped | Mirrors live scanner. | ✓ |
| All-triggers-evaluated-independently; multi-fire allowed | Inflates trade counts. | |
| Most-restrictive AND-of-all | Conflicts with REQUIREMENTS §STR-02. | |

**User's choice:** First-goal-matching-any-trigger; sport-mismatched skipped (Recommended)
**Notes:** Locks D-12.

### Q4 — Initial state / dirty indicator

| Option | Description | Selected |
|--------|-------------|----------|
| Default trigger group + "— Custom —" auto-snap on edit | Friction-free start; honest divergence signal. | ✓ |
| First YAML strategy auto-selected, `*` suffix on edit | Cleaner if YAML always populated. | |
| Empty page; user must pick or click (+) | Strict; more friction. | |

**User's choice:** Default trigger + "— Custom —" auto-snap (Recommended)
**Notes:** Locks D-13.

### Q5 — (+) button defaults

| Option | Description | Selected |
|--------|-------------|----------|
| Phase-1 slider defaults; sport = current season's path | Sensible filter + sport pre-matched. | |
| Copy of the last existing trigger group | Variant-iteration workflow. | ✓ |
| Empty/zero values | Forces deliberate input. | |

**User's choice:** Copy of the last existing trigger group
**Notes:** Locks D-14 (specific sub-decision).

### Q6 — Sport dropdown / season selector relationship

| Option | Description | Selected |
|--------|-------------|----------|
| Per-trigger sport; mismatched grayed with tooltip | Honest; preserves multi-sport strategies. | ✓ |
| Per-trigger sport; mismatched hidden | Cleaner visually; obscures full shape. | |
| Single page-level sport (replaces season selector) | Loses per-trigger semantics. | |

**User's choice:** Per-trigger sport; mismatched grayed (Recommended)
**Notes:** Locks D-15.

### Q7 — Edit persistence

| Option | Description | Selected |
|--------|-------------|----------|
| Ephemeral; no save-back | Read-only YAML; file is hand-edited. | ✓ |
| Save-back via "Save as new strategy" | Becomes lite editor; expansion of phase scope. | |

**User's choice:** "Ephemeral but add among possible future expansions"
**Notes:** Locks D-16. Save-back captured in Deferred Ideas.

### Q8 — Trigger delete confirmation style

| Option | Description | Selected |
|--------|-------------|----------|
| Native `window.confirm()` | Zero new components; functional. | ✓ |
| Inline confirmation (button morph) | Better UX in-context. | |
| Custom modal component | Overkill for one usage. | |

**User's choice:** Native `window.confirm()` (Recommended)
**Notes:** Locks D-17.

### Q9 — Summary panel with sport-mismatched triggers

| Option | Description | Selected |
|--------|-------------|----------|
| Active-only with muted "N skipped" note | Honest about what numbers represent. | ✓ |
| Per-trigger breakdown table | More detail; heavier UI. | |
| No mismatch indicator | Cleanest visually; confusing. | |

**User's choice:** Active-only with muted skipped note (Recommended)
**Notes:** Locks D-18.

---

## Claude's Discretion

- Module location for the loader (`src/predictions/strategies.py` likely; planner choice).
- Pydantic class layout (`StrategiesFile`, `Strategy`, `Trigger`).
- Caching strategy for `GET /api/strategies` endpoint.
- Test fixture file layout under `tests/fixtures/strategies-*.yaml`.
- Exact UI copy for skipped-trigger tooltip and the "— Custom —" dropdown label.
- Whether sport dropdown lists ALL `KALSHI_TO_ESPN` sport_paths or only soccer leagues.
- How `description` field is rendered in the dashboard (tooltip, subtitle, paragraph).
- Whether `BacktestTrade` gains a `trigger_index` field for Phase 4 analytics.

## Deferred Ideas

- "Save as new strategy" button — full strategy editor (REQUIREMENTS.md Future).
- `lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields (REQUIREMENTS.md Future).
- Per-trigger `bet_percent` override.
- Hot-reload of `strategies.yaml`.
- Per-trigger analytics breakdown (`trigger_index` on `BacktestTrade`) — Phase 4 may pick up.
- JSON Schema export for editor autocompletion.
- `GET /api/sports` endpoint to keep dashboard sport dropdown in sync with `KALSHI_TO_ESPN`.
- Sub-dropdown to pick which trigger to load (rejected; trigger groups model is more transparent).
