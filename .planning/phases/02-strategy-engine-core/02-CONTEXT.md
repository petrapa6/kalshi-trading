# Phase 2: Strategy Engine Core - Context

**Gathered:** 2026-04-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Build the YAML-driven strategy definition system: `strategies.yaml` at the
repo root, a Python loader with strict Pydantic validation, a new
`GET /api/strategies` endpoint, and dashboard backtest integration that
exposes per-trigger slider groups with add/remove. The strategy file
becomes the single source of truth for both the backtest (this phase) and
(Phase 3) the live scanner.

**In scope (Phase 2):**

- `strategies.yaml` at repo root — fresh reference strategies + commented
  `WHAT_IF_STRATEGIES` translations
- New Python loader + Pydantic models (likely `src/predictions/strategies.py`,
  planner judgment)
- `STRATEGIES_PATH` env override (one-line read); update `.env.example`
- New `GET /api/strategies` endpoint returning
  `{strategies: [{name, description, triggers}, ...]}`
- Dashboard backtest changes:
  - Strategy dropdown with "— Custom —" option and Custom auto-snap on edit
  - Per-trigger slider groups with (+)/(-) buttons
  - Page-level season selector still drives data loading
  - Sport-mismatched trigger groups grayed out with tooltip
  - Multi-trigger backtest engine (OR-of-AND, first-fire-wins per match)
  - Read-only info text for `min_yes_price` / `max_yes_price` per trigger

**Out of scope (deferred to Phase 3+):**

- `WHAT_IF_STRATEGIES` removal in `scanner.py` (Phase 3, STR-04)
- `stretch_opportunities` table archival (Phase 3, STR-04)
- Live scanner consuming strategies (Phase 3, DRY-01/DRY-02)
- Strategy editor / save-back to YAML (deferred — see deferred ideas)
- `lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields (deferred)
- New analytics dashboard page (Phase 4)

</domain>

<decisions>
## Implementation Decisions

### Schema vocabulary & cross-engine fit

- **D-01:** `min_minute` is **game-clock minutes elapsed since start**,
  sport-aware. For Phase 2 (backtest only) this maps directly to a soccer
  goal's `minute` field. Phase 3 will need a per-sport `total_game_seconds`
  / period-length lookup to compute
  `elapsed = total_game_seconds − clock_seconds` in scanner context.
  Documented in CONTEXT.md so Phase 3 doesn't have to re-derive.

- **D-02:** `sport` field uses ESPN sport_path notation (e.g.,
  `soccer/eng.1`, `basketball/nba`). Reuses scanner's existing taxonomy
  (`KALSHI_TO_ESPN`, `lead:<path>` config keys, `MIN_SCORE_LEAD`). Backtest
  needs a small mapping from season filename to sport_path:
  `epl_*` → `soccer/eng.1`, `laliga_*` → `soccer/esp.1`,
  `bundesliga_*` → `soccer/ger.1`, `seriea_*` → `soccer/ita.1`,
  `ligue1_*` → `soccer/fra.1`, `mls_*` → `soccer/usa.1`.

- **D-03:** Sport matching is **exact**. Missing `sport` field in a trigger
  means "any sport" (per REQUIREMENTS §STR-02 "missing field = no
  constraint"). Multi-league strategies use multiple triggers, one per
  league.

- **D-04:** Initial `strategies.yaml` ships with **2–4 fresh reference
  strategies** tuned for the new schema, PLUS **commented-out translations
  of the 5 existing `WHAT_IF_STRATEGIES`** (`low_price`, `lower_price`,
  `loose_leads`, `early_entry`, `yolo`) as schema usage examples. Note:
  WHAT_IF's `lead_pct` semantics don't translate cleanly to flat
  `min_lead` — the commented examples should either pick a representative
  per-sport flat value or show how to express the strategy via multiple
  per-sport triggers (planner's choice; document the translation in YAML
  comments).

### File location, top-level shape, validation strictness

- **D-05:** YAML top-level shape is `strategies:` mapping
  (dict-of-strategies):

  ```yaml
  strategies:
    conservative_late_lead:
      description: "Late game, modest lead, premium price"
      triggers:
        - {sport: soccer/eng.1, min_minute: 80, min_lead: 2, min_yes_price: 92}
    early_value:
      triggers: [...]
  ```

  Strategy names are unique by construction (dict keys). Each strategy has
  `description` (string, optional) and `triggers` (list, required, min
  length 1 per REQUIREMENTS §STR-02).

- **D-06:** Pydantic validation uses `extra="forbid"`. Unknown fields in a
  trigger or strategy raise `ValidationError` at load time. Catches typos
  (`min_minutes` with extra 's' → error). Future fields require explicit
  code change — no silent forward-compat.

- **D-07:** **All-or-nothing validation.** Any error in any strategy
  rejects the entire file. Loader logs the validation error and proceeds
  with **zero strategies** (same outcome as missing file per REQUIREMENTS
  §STR-01 — malformed should not be more severe than missing).

- **D-08:** `STRATEGIES_PATH` env var is implemented in Phase 2:
  `path = os.getenv("STRATEGIES_PATH", "strategies.yaml")`. Update
  `.env.example` to document it. Lets tests point at fixture YAML files
  without monkeypatching.

### Dashboard data path

- **D-09:** Dashboard reads strategies via a new `GET /api/strategies`
  endpoint. **Python loader is the single source of truth.** Endpoint
  goes through the existing `/api/[...path]/route.ts` proxy
  (Bearer-auth pattern). Dashboard fetches once on mount; YAML edits
  require a manual page reload to reflect (auto-refresh is Phase 4
  scope, if at all).

- **D-10:** API response shape:

  ```json
  {"strategies": [
    {"name": "conservative_late_lead", "description": "...", "triggers": [...]}
  ]}
  ```

  List preserves YAML insertion order (Python 3.7+ dict iteration). `name`
  is duplicated from the dict key for ergonomic client consumption.
  Wrapping in `{strategies: [...]}` leaves room for sibling fields
  (e.g., `version`) in the future.

### Backtest preset UX (BT-07 — narrowed)

- **D-11:** **BT-07 is intentionally narrowed.** The literal REQUIREMENTS
  text says "pre-populates the parameter sliders (sport, min_lead,
  min_minute, min_yes_price, max_yes_price)" — but the Phase 1 backtest
  engine has no Kalshi prices in its data and uses `contract_price_cents`
  for the price-paid math. So:

  - **Backtest sliders that exist (per trigger group):** `sport` (dropdown),
    `min_minute` (slider), `min_lead` (slider).
  - **`min_yes_price` and `max_yes_price`** are surfaced as **read-only
    info text** under each trigger group (e.g., "Live trading: 92¢–99¢").
    Not sliders. Not used by the backtest engine.
  - **`contract_price_cents`** slider from Phase 1 stays at the **page
    top (financial section)**, single instance, **not per-trigger**.

  Planner: this narrowing is **intentional** and supersedes the literal
  REQUIREMENTS wording.

- **D-12:** **Multi-trigger engine semantics:** walk goals chronologically
  per match; first goal that satisfies ANY trigger's AND-conditions fires
  the bet. **Sport-mismatched triggers** (sport ≠ loaded season's
  sport_path) are **silently skipped** during evaluation. Mirrors how the
  live scanner will behave (fire once when conditions first met).
  `runBacktest`'s `BacktestParams` shape changes to accept
  `triggers: Trigger[]` instead of flat `min_minute` / `min_lead`. Internal
  capital math (Phase 1 D-01..D-17) stays identical.

- **D-13:** **Initial state:** page loads with **one default trigger
  group** (sport = current season's sport_path, min_minute = 75,
  min_lead = 2). Strategy dropdown has a `"— Custom —"` option that is
  preselected on load. As soon as the user edits any field (or +/- a
  trigger group), the dropdown auto-snaps back to `"— Custom —"` to
  signal the trigger set no longer matches any preset. Picking a named
  strategy replaces all trigger groups with that strategy's triggers.

- **D-14:** **Trigger group UI shape:**

  - **Financial attributes** (`initial_capital`, `bet_fraction`,
    `contract_price_cents`) live at the **top of the sidebar**, single
    instance, **not per-trigger**.
  - Below that: a list of trigger-group cards, separated by light
    dividers. Each card has: sport dropdown, min_minute slider, min_lead
    slider, read-only info text for `min_yes_price` / `max_yes_price`.
  - **(-) button** on each trigger card, **hidden when only one trigger
    exists**. Clicking shows native `window.confirm("Delete this
    trigger?")`.
  - **(+) button** below the last card, with a bottom divider. Click
    creates a new trigger group, **pre-filled as a copy of the last
    existing trigger group** (so users can quickly variant-iterate).

- **D-15:** Sport dropdown is **per-trigger**. The page-level **season
  selector** still decides which JSON file is loaded into the engine. If
  a trigger's sport ≠ the loaded season's sport_path, that trigger card
  is rendered grayed/dim with a tooltip "Skipped — no `<sport>` data
  loaded". The trigger remains in the strategy state (round-trips
  correctly when the user changes seasons), it just doesn't fire.

- **D-16:** Trigger edits (+/-, slider changes) are **ephemeral** — they
  affect only the current backtest run. **No save-back to
  `strategies.yaml`.** The YAML file is hand-edited only. Aligns with
  REQUIREMENTS.md `Future Requirements` listing "Strategy editor in the
  dashboard UI" as deferred.

- **D-17:** Trigger delete uses **native `window.confirm()`**. No new
  modal component. Aligns with the dashboard's lean style (no
  toast/modal lib in dashboard today). Confirmation copy:
  "Delete this trigger?".

- **D-18:** **Summary panel** (Phase 1's 7 cards: Scanned, Bet on, Wins,
  Losses, Win rate, Final capital, Gain) reflects only triggers that
  actually fired (i.e., sport-matched). Below the cards, a muted line
  appears when triggers are skipped: "N of M triggers skipped: `<list of
  sport_paths>` (no data for current season)". Honest about what the
  numbers represent.

### Claude's Discretion

- **Module location** for the loader (e.g., `src/predictions/strategies.py`
  vs folding into an existing module). Likely a new module per
  CONVENTIONS.md "New external integration → its own module" — though a
  YAML loader isn't strictly an integration. Planner judgment call.

- **Pydantic class layout** (`StrategiesFile`, `Strategy`, `Trigger`).

- **Caching strategy** for `GET /api/strategies` (re-read per request vs
  TTL cache). For Phase 2, re-read per request is fine; the Phase 3
  scanner will likely cache per loop.

- **Test fixtures** under `tests/fixtures/strategies-*.yaml` and pytest
  helpers (parallel to `isolated_db`).

- **Exact UI copy** for skipped-trigger tooltip and the "— Custom —"
  dropdown label.

- Whether the **per-trigger sport dropdown** lists ALL known sport_paths
  (`KALSHI_TO_ESPN` keys) or only soccer leagues with backtest data.

- How `description` is rendered (tooltip on dropdown? subtle subtitle?
  separate paragraph?).

- Whether `BacktestTrade` gains a `trigger_index: number` field for Phase
  4 analytics. Phase 2 can leave it out; Phase 4 picks up if needed.

</decisions>

<specifics>
## Specific Ideas

- The user wants the backtest UI to feel like a **lightweight strategy
  builder**: trigger groups with (+)/(-), "— Custom —" dropdown state,
  copy-of-last-trigger as default for new groups. One notch beyond a pure
  "load a preset" flow but stops short of a full editor (no save-back).

- Native `window.confirm()` is **explicitly fine** — matches the lean
  dashboard style (no modal/toast libs in dashboard today).

- Sport-mismatched trigger groups should be **grayed but visible**, not
  hidden — the user prioritizes transparency over visual cleanliness.

- The 5 existing `WHAT_IF_STRATEGIES` should ship as **commented YAML**
  in the initial file — to act as templates without adding noise to the
  active strategy list.

- BT-07's literal "min_yes_price/max_yes_price as sliders" was the user's
  initial REQUIREMENTS wording, but during this discussion they
  re-scoped to **info-text-only** in backtest. Phase 3 is where these
  fields actually filter (live scanner).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner) MUST read these before acting.**

### Phase scope and acceptance

- `.planning/ROADMAP.md` § Phase 2 — phase goal, depends-on, success
  criteria (all 4 must be TRUE). Note: success criterion #2 references
  "Backtest page strategy dropdown is populated from `strategies.yaml`;
  selecting a strategy pre-fills parameter sliders" — D-11 narrows this
  so only sport/min_minute/min_lead are sliders; min_yes_price /
  max_yes_price are read-only info text.

- `.planning/REQUIREMENTS.md` § BT-07, STR-01, STR-02, STR-03 — canonical
  functional requirements. STR-04, DRY-01, DRY-02, DASH-03, DASH-04 are
  out of Phase 2 scope (Phase 3 / Phase 4).

- `.planning/PROJECT.md` § Active / Constraints / Key Decisions — no-new-deps
  rule, integer-cents invariant, oxfmt 4-space indent,
  `pnpm fmt:check && pnpm lint && pnpm build` gate, `uv run ruff …` Python
  gate.

- `.planning/STATE.md` § Blockers/Concerns — flagged Phase 2 vocabulary
  mismatch (resolved via D-01..D-03) and Phase 3 settlement filtering
  concern (still open, out of Phase 2 scope).

### Prior phase context

- `.planning/phases/01-backtest-p-l-math/01-CONTEXT.md` — Phase 1's
  contract-math decisions. Most relevant carryovers:
  - Phase 1 D-01..D-04: `contract_price_cents` is the single price field
    in backtest; floor remainder returns to capital. Phase 2 D-11 keeps
    this intact.
  - Phase 1 D-13: `BacktestTrade` schema is minimal. Phase 2 may need a
    `trigger_index: number` field if the planner judges per-trigger
    analytics worth the schema cost (Claude's Discretion).
  - Phase 1 D-17: zero-contract trades stay in the engine output but are
    excluded from win/loss tallies. Phase 2 inherits.

- `.planning/phases/01-backtest-p-l-math/01-PATTERNS.md` — patterns for
  TS slider components, sidebar layout, summary cards.

### Code conventions

- `.planning/codebase/CONVENTIONS.md` — Python: `uv` + `ruff` + `ty`,
  Pydantic for boundaries, `_CONFIG_DEFAULTS` pattern for runtime
  tunables, log-and-continue for scanner-loop failures. TS: oxfmt
  4-space, server-side proxy pattern, functional components.

- `.planning/codebase/STRUCTURE.md` — repo layout. New module location
  guidance: "New external integration → its own module under
  `src/predictions/`, mirror the `kalshi_client.py` pattern".

- `.planning/codebase/ARCHITECTURE.md` — auth model (Bearer through
  proxy), runtime config flow, scanner shape. Phase 2 adds a new endpoint
  behind `Depends(_check_token)` like all other endpoints.

- `.planning/codebase/TESTING.md` — pytest conventions; `isolated_db` /
  `isolated_soccer_db` fixtures. Phase 2 likely adds `tmp_path`-based
  YAML fixtures or a `tests/fixtures/strategies-*.yaml` directory.

### Code references (relevant existing code)

- `src/predictions/scanner.py:261` — `WHAT_IF_STRATEGIES` dict (5
  strategies). Source for D-04 commented translations.

- `src/predictions/scanner.py:300+` — `scan_kalshi_with_espn`. Phase 2
  does NOT modify this; Phase 3 will (per STR-04).

- `src/predictions/scanner.py` `KALSHI_TO_ESPN` / `MIN_SCORE_LEAD` —
  authoritative sport_path catalog. Reuse for D-02 / sport dropdown.

- `src/predictions/db.py:217` — `_CONFIG_DEFAULTS` and `get_config_int(key)`
  pattern. Phase 2 does NOT add a new config key unless the planner
  identifies a runtime tunable.

- `src/predictions/api.py:258` — `_check_token` dep. New endpoint must
  use `Depends(_check_token)`.

- `dashboard/app/backtest/backtest.ts` — current engine. Phase 2 evolves
  `runBacktest` to accept a list of triggers (OR semantics).

- `dashboard/app/backtest/page.tsx` — current UI. Phase 2 redoes the
  sidebar to support multiple trigger groups + dropdown.

- `dashboard/app/backtest/seasons.ts` — existing static catalog of season
  files. Phase 2 needs to extend it (or add a sibling file) with the
  season-filename → sport_path mapping per D-02.

- `dashboard/app/api/[...path]/route.ts` — server-side proxy with Bearer
  injection. New endpoint needs no proxy change — the catch-all routes it.

### Origin / dependencies

- `.planning/todos/pending/2026-04-29-backtest-contract-based-pnl.md` —
  resolved by Phase 1; not consumed by Phase 2.

- `.env.example` — must be updated with `STRATEGIES_PATH` (per D-08).

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable assets

- **`detectFire(match, min_minute, min_lead)`** in
  `dashboard/app/backtest/backtest.ts:87` — pure, capital-independent.
  Phase 2 wraps a list of triggers around this: walk goals chronologically;
  short-circuit on first goal that satisfies ANY trigger's AND-conditions.
  Refactor signature to accept `Trigger[]` (planner judgment) or wrap
  externally and keep `detectFire` single-trigger.

- **`runBacktest`** in `backtest.ts:124` — orchestrator. Phase 2 changes
  its `BacktestParams` shape to include `triggers: Trigger[]` instead of
  flat `min_minute` / `min_lead`. Internal capital math (Phase 1
  D-01..D-17) stays identical.

- **`SeasonFile`** type in `dashboard/app/backtest/seasons.ts` — extend
  with `sport_path` metadata (or add a parallel constant) per D-02.

- **`SummaryCard`** component in `page.tsx` — reuse as-is. Add a small
  text line below for the "N triggers skipped" note (D-18).

- **Pydantic models pattern** in `src/predictions/api.py` — mirror this
  for the strategy schema. Hot-reload pattern via `Depends` if needed.

- **httpx-based test fixtures** in `tests/conftest.py` — extend for the
  `GET /api/strategies` endpoint test (TestClient-based, parallel to
  `tests/test_backtest_api.py`).

### Established patterns

- **Single boundary per integration:** YAML loading is a new boundary;
  `extract_cents`-style "single drift point" applies — only one place
  parses YAML, everything else sees Pydantic models. Likely
  `src/predictions/strategies.py::load_strategies(path) -> list[Strategy]`.

- **Bearer-auth on every endpoint** except `GET /` — the new
  `GET /api/strategies` follows suit.

- **No silent feature flags** (CONVENTIONS.md) — `STRATEGIES_PATH` env is
  acceptable because it's a path override, not a feature toggle.

- **Server-side proxy pattern** — dashboard's `/api/[...path]/route.ts`
  forwards everything; no per-endpoint proxy changes needed.

- **Page-level state in client component** — `dashboard/app/backtest/page.tsx`
  is a 520-line client component (`"use client"`). Phase 2 grows it
  (multi-trigger state). May warrant a small refactor (extract
  trigger-group state machine into a hook) — planner judgment.

### Integration points

- **`api.py` lifespan** — no change. Strategies are loaded on demand by
  the endpoint (or per scan loop in Phase 3); not loaded at startup.

- **Working directory** for `STRATEGIES_PATH` resolution — the API runs
  from the repo root in dev (`pnpm dev:api`) and `/app` in production.
  Default `"strategies.yaml"` resolves relative to CWD; document in
  `.env.example` if non-obvious.

- **`tests/`** — new `tests/test_strategies.py` for Pydantic
  loader/validator; new `tests/test_strategies_api.py` for the FastAPI
  endpoint. Use `tmp_path` or fixture YAML files.

- **`dashboard/app/backtest/page.tsx:218–221`** — Phase 1 helper text
  block for the contract-price input. Phase 2 may keep, modify, or
  replace depending on the multi-trigger UI redesign.

</code_context>

<deferred>
## Deferred Ideas

- **"Save as new strategy" button** — let users persist UI tweaks back to
  `strategies.yaml` as a new named entry. Out of Phase 2 scope; the
  REQUIREMENTS.md `Future Requirements` already lists "Strategy editor in
  the dashboard UI". Bring back when there's signal that hand-editing
  YAML is a friction point.

- **`lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields** —
  per REQUIREMENTS.md `Future Requirements`. Defer until v1.3 or until
  Phase 3 reveals scanner needs them.

- **Per-trigger `bet_percent` override** — per REQUIREMENTS.md.

- **Hot-reload of `strategies.yaml`** — open dry-run trades under changed
  strategies create mismatched state; design needed. Defer.

- **Per-trigger analytics breakdown** — `BacktestTrade` could record which
  trigger fired (`trigger_index` column). Useful for Phase 4 analytics
  ("did the early-entry trigger ever win?"). Phase 2 can leave this out;
  Phase 4 picks up if needed.

- **JSON Schema export for editor autocompletion** — pydantic →
  JSON Schema → `.vscode/settings.json` association. Nice-to-have, not
  blocking.

- **`GET /api/sports` endpoint** — would let the dashboard sport dropdown
  stay in sync with `KALSHI_TO_ESPN` without a hand-maintained TS list.
  Phase 2 may inline a TS constant; if it drifts, this becomes the
  cleanup.

- **Sub-dropdown to pick which trigger to load** (vs auto-loading all
  triggers) — discussed and rejected. The "render all triggers as slider
  groups" model (D-14) is more transparent and editable.

</deferred>

---

*Phase: 02-strategy-engine-core*
*Context gathered: 2026-04-30*

## Revision — 2026-04-30 (during 02-04 checkpoint review)

**D-02 OVERRIDE.** The original D-02 locked `sport = ESPN sport_path` (e.g., `soccer/eng.1`). The user revised this during 02-04 sidebar review:
- `trigger.sport` is now a SPORT FAMILY literal: `football`, `baseball`, `tennis`, …
- UK terminology: `football`, never `soccer`.
- League selection is a separate dropdown (renamed from Season). League list is filtered by the page-level Sport.
- All triggers in a backtest run share the page-level Sport. Per-trigger Sport dropdown removed from the UI.
- Strategies are visible in the Strategy dropdown only when ALL their triggers match the selected Sport.

This rewrites strategies.yaml data values (not the loader schema), the fixture YAMLs, the dashboard TS layer's Season→League rename, and the 02-04 sidebar UX. Cross-plan revision committed as:
- `refactor(02-rev): rename sport semantics to family-only (football); rename Season→League`
- `refactor(02-04): replace sidebar with Sport→League→Strategy hierarchy`
- `docs(02-rev): record cross-plan revision and D-02 override`

The original D-02 above is preserved verbatim for audit trail. Phase 3's live scanner must read THIS revision, not D-02.
