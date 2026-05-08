# Phase 2: Strategy Engine Core - Research

**Researched:** 2026-04-30
**Domain:** YAML-driven strategy definition system — Python loader, Pydantic v2 validation, FastAPI endpoint, React multi-trigger backtest UI
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** `min_minute` = game-clock minutes elapsed since start. Soccer: maps directly to goal `minute` field. Phase 3 will need per-sport clock math.
- **D-02:** `sport` uses ESPN sport_path notation (`soccer/eng.1`, `basketball/nba`, etc). Season filename → sport_path mapping: `epl_*` → `soccer/eng.1`, `laliga_*` → `soccer/esp.1`, `bundesliga_*` → `soccer/ger.1`, `seriea_*` → `soccer/ita.1`, `ligue1_*` → `soccer/fra.1`, `mls_*` → `soccer/usa.1`.
- **D-03:** Sport matching is exact. Missing `sport` field = no constraint.
- **D-04:** `strategies.yaml` ships with 2-4 fresh strategies + commented WHAT_IF translations (5 existing strategies).
- **D-05:** YAML top-level: `strategies:` mapping (dict-of-strategies). Each strategy has optional `description` and required `triggers` (list, min length 1).
- **D-06:** Pydantic uses `extra="forbid"`. Unknown fields raise ValidationError.
- **D-07:** All-or-nothing validation. Any error rejects entire file → zero strategies (same as missing file).
- **D-08:** `STRATEGIES_PATH` env var, default `"strategies.yaml"`. Update `.env.example`.
- **D-09:** Dashboard reads via `GET /api/strategies`. Python loader is single source of truth. Fetch once on mount.
- **D-10:** API response: `{"strategies": [{"name": "...", "description": "...", "triggers": [...]}]}`. List preserves YAML insertion order. `name` duplicated from dict key.
- **D-11:** BT-07 narrowed: backtest sliders per trigger = sport dropdown + min_minute + min_lead only. `min_yes_price`/`max_yes_price` = read-only info text. `contract_price_cents` stays at sidebar top, single instance.
- **D-12:** Multi-trigger engine: walk goals chronologically per match; first goal satisfying ANY trigger's AND-conditions fires. Sport-mismatched triggers silently skipped.
- **D-13:** Page loads with one default trigger (sport = current season's sport_path, min_minute = 75, min_lead = 2). Strategy dropdown defaults to `"— Custom —"`. Any field edit snaps to Custom. Picking a strategy replaces all triggers.
- **D-14:** Financial attributes (initial_capital, bet_fraction, contract_price_cents) at sidebar top, single instance. Below: trigger-group cards with sport dropdown + min_minute slider + min_lead slider + info text for min_yes_price/max_yes_price. (-) hidden when only one trigger. (+) copies last trigger.
- **D-15:** Sport dropdown is per-trigger. Page-level season selector still drives data loading. Mismatched trigger cards rendered grayed/dim with tooltip "Skipped — no `<sport>` data loaded".
- **D-16:** Trigger edits are ephemeral — no save-back to YAML.
- **D-17:** Trigger delete uses native `window.confirm("Delete this trigger?")`.
- **D-18:** "N of M triggers skipped" muted line under summary cards when triggers are skipped.

### Claude's Discretion

- Module location for loader (`src/predictions/strategies.py` vs folding into existing module).
- Pydantic class layout (`StrategiesFile`, `Strategy`, `Trigger`).
- Caching strategy for `GET /api/strategies` (re-read per request is fine for Phase 2).
- Test fixtures (`tests/fixtures/strategies-*.yaml` vs `tmp_path` inline).
- Exact UI copy for skipped-trigger tooltip and "— Custom —" label.
- Whether per-trigger sport dropdown lists ALL known sport_paths or only soccer leagues with backtest data.
- How `description` is rendered (tooltip, subtitle, etc.).
- Whether `BacktestTrade` gains a `trigger_index: number` field (Phase 4 can add if needed; leave out of Phase 2).

### Deferred Ideas (OUT OF SCOPE)

- Save-back to YAML from UI
- `lead_pct`, `series_ticker`, `max_countdown_secs` trigger fields
- Per-trigger `bet_percent` override
- Hot-reload of strategies.yaml
- Per-trigger analytics breakdown / `trigger_index` on BacktestTrade
- JSON Schema export for editor autocompletion
- `GET /api/sports` endpoint
- Sub-dropdown to pick which trigger to load

</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| STR-01 | Named strategies in `strategies.yaml`; `STRATEGIES_PATH` env override; missing file → warning + zero strategies | Loader pattern: `yaml.safe_load` + Pydantic validation + all-or-nothing error handling |
| STR-02 | Each strategy: multi-trigger (OR-of-AND); `triggers` list min length 1; supported fields: sport, min_lead, min_minute, min_yes_price, max_yes_price; missing field = no constraint | Pydantic v2 `model_config = ConfigDict(extra="forbid")` + `Annotated[list[Trigger], Field(min_length=1)]` |
| STR-03 | Strategy definitions drive both backtest simulator and live scanner (single source of truth) | `GET /api/strategies` endpoint + dashboard fetch; Phase 3 will consume loader directly |
| BT-07 | Backtest page strategy dropdown populated from `strategies.yaml`; selecting pre-fills sport/min_minute/min_lead sliders; sliders remain editable; narrowed per D-11 | Multi-trigger state machine in React + `useEffect` mount fetch + `useMemo` for engine |

</phase_requirements>

---

## Summary

Phase 2 adds three interconnected pieces: (1) a new Python module `src/predictions/strategies.py` containing Pydantic v2 models and a loader function, (2) a new `GET /api/strategies` FastAPI endpoint, and (3) a significant rework of `dashboard/app/backtest/page.tsx` to support multi-trigger groups driven from those strategies.

**Critical pre-work finding:** PyYAML (`pyyaml`) is **NOT in pyproject.toml or uv.lock**. The project has a strict no-new-deps rule, so this requires an explicit exception or use of Python's stdlib `json` for an alternative (YAML is not stdlib). PyYAML must be added as a dependency. This is the one case where adding a dep is justified and unavoidable given YAML is the locked file format (D-05). See the Open Questions section.

Pydantic v2.12.5 is already installed (pulled in transitively by FastAPI). The `extra="forbid"` pattern and `ConfigDict` API are confirmed available. FastAPI 0.135.1 is installed.

**Primary recommendation:** Add `pyyaml` to pyproject.toml as a production dependency before writing any loader code.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| YAML parsing + Pydantic validation | API / Backend (`strategies.py`) | — | Single boundary principle; all callers see typed models, never raw YAML dicts |
| `GET /api/strategies` serving | API / Backend (`api.py`) | — | Follows existing Bearer-auth endpoint pattern; no new auth layer needed |
| Strategy fetching in dashboard | Frontend Server (proxy) → Browser | — | Existing `/api/[...path]/route.ts` catch-all proxy injects Bearer; dashboard fetches on mount |
| Multi-trigger state machine | Browser (client component) | — | `page.tsx` is `"use client"` ; all trigger state is ephemeral client-side |
| Sport-path → season mapping | Browser (static constant) | — | `seasons.ts` extended with `sport_path` field; no server needed for static mapping |
| Backtest engine (multi-trigger) | Browser (pure function) | — | `backtest.ts` `runBacktest` already pure; extend `BacktestParams` to `triggers: Trigger[]` |

---

## Standard Stack

### Core (already installed)
| Library | Version (verified) | Purpose | Notes |
|---------|---------|---------|-------|
| pydantic | 2.12.5 | Strategy model validation | [VERIFIED: uv.lock line 373-385] — pulled by FastAPI |
| fastapi | 0.135.1 | API endpoint | [VERIFIED: uv.lock line 200-205] |
| python-dotenv | 1.2.2 | `os.getenv` + `.env` loading | [VERIFIED: uv.lock] |

### Needs to be added
| Library | Purpose | Status |
|---------|---------|--------|
| pyyaml | Parse `strategies.yaml` | [VERIFIED: NOT in uv.lock or pyproject.toml — must add] |

**Installation (after approval to add dep):**
```bash
uv add pyyaml
```

This updates both `pyproject.toml` and `uv.lock`. It is the only dependency change required for this phase.

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PyYAML | `tomllib` (stdlib 3.11+) | TOML has different syntax; would require changing D-05's locked YAML format — not acceptable |
| PyYAML | `json` (stdlib) | Would require changing file format to JSON — contradicts YAML decision in D-05 |
| PyYAML | `ruamel.yaml` | Preserves comments, round-trips — overkill; comments are only needed for documentation in the file, not for programmatic write-back (D-16 forbids save-back) |

---

## Architecture Patterns

### System Architecture Diagram

```
strategies.yaml (repo root, CWD-relative)
        │
        │  os.getenv("STRATEGIES_PATH", "strategies.yaml")
        │  yaml.safe_load()  ──────────── PermissionError / FileNotFoundError
        │  Pydantic validation            → log warning, return []
        ▼
src/predictions/strategies.py
  load_strategies(path) → list[Strategy]
  StrategiesFile, Strategy, Trigger (extra="forbid")
        │
        ├──────────────────────────────────────────────
        │                                              │
        ▼                                              ▼
src/predictions/api.py                    (Phase 3) scanner.py
  GET /api/strategies                       load_strategies() per scan loop
  → {strategies: [{name, description,
                    triggers: [...]}]}
        │
        │  Bearer auth via /api/[...path]/route.ts proxy
        ▼
dashboard/app/backtest/page.tsx
  useEffect → fetch("/api/strategies") on mount
  state: strategies[], selectedStrategy, triggers[]
        │
        ├── Strategy dropdown (—Custom— + named)
        ├── Trigger group cards (sport, min_minute, min_lead, info text)
        │   (+)/(-) buttons, grayed-out when sport-mismatched
        └── useMemo → runBacktest(file, {triggers: Trigger[], ...})
                           │
                           ▼
            backtest.ts: multi-trigger OR-of-AND walk
            → BacktestResult (existing summary + trades)
```

### Recommended Project Structure

```
# New Python files:
src/predictions/strategies.py       # Pydantic models + loader

# New test files:
tests/test_strategies.py            # Loader + Pydantic validation unit tests
tests/test_strategies_api.py        # FastAPI endpoint tests (TestClient)
tests/fixtures/                     # YAML fixtures
tests/fixtures/strategies-valid.yaml
tests/fixtures/strategies-no-triggers.yaml
tests/fixtures/strategies-unknown-field.yaml
tests/fixtures/strategies-empty-triggers-list.yaml

# Modified files:
src/predictions/api.py              # Add GET /api/strategies endpoint + StrategiesResponse model
dashboard/app/backtest/backtest.ts  # Extend BacktestParams, new Trigger type, multi-trigger runBacktest
dashboard/app/backtest/seasons.ts   # Add sport_path to SeasonOption (or parallel constant)
dashboard/app/backtest/page.tsx     # Multi-trigger UI, strategy dropdown, fetch strategies
.env.example                        # Document STRATEGIES_PATH
strategies.yaml                     # New file at repo root
```

### Pattern 1: Pydantic v2 Strict Validation Models

**What:** Three nested models with `extra="forbid"` at every level. All-or-nothing: catch `ValidationError` at top level, log it, return `[]`.

**When to use:** Any external file format parsed at a trust boundary.

```python
# Source: Pydantic v2 docs + confirmed working pattern for v2.12.5 [CITED: pydantic.dev/docs]
from typing import Annotated, Optional
from pydantic import BaseModel, ConfigDict, Field

class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sport: Optional[str] = None
    min_minute: Optional[int] = None
    min_lead: Optional[int] = None
    min_yes_price: Optional[int] = None
    max_yes_price: Optional[int] = None


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: Optional[str] = None
    triggers: Annotated[list[Trigger], Field(min_length=1)]


class StrategiesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategies: dict[str, Strategy]
```

**Key insight:** `min_length=1` on the `triggers` list enforces STR-02's requirement that every strategy has at least one trigger. An empty `triggers: []` raises `ValidationError` during `StrategiesFile` construction — the all-or-nothing handler catches it and returns `[]`.

**Note on `extra="forbid"` with Optional fields:** In Pydantic v2, `Optional[str] = None` means the field is not required and defaults to `None`. When `extra="forbid"`, providing a field name NOT in the model (e.g., `min_minutes` with a typo) raises `ValidationError`. Fields explicitly typed as `Optional` with a default of `None` are allowed to be absent — they are not "extra" fields. [VERIFIED: confirmed in pydantic.dev docs]

### Pattern 2: YAML Loader — All-or-Nothing

**What:** Single public function; caller sees `list[Strategy]` or empty list, never raw errors.

```python
# Source: PyYAML docs [CITED: pyyaml.org/wiki/PyYAMLDocumentation]
import logging
import os
import yaml
from pydantic import ValidationError
from predictions.strategies import Strategy, StrategiesFile

log = logging.getLogger(__name__)


def load_strategies(path: str | None = None) -> list[Strategy]:
    """Load and validate strategies from YAML. Returns [] on any error."""
    if path is None:
        path = os.getenv("STRATEGIES_PATH", "strategies.yaml")
    try:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
    except FileNotFoundError:
        log.warning("strategies.yaml not found at %s — running with no strategies", path)
        return []
    except OSError as e:
        log.warning("Failed to read strategies file %s: %s — running with no strategies", path, e)
        return []

    if raw is None:
        # Empty file: yaml.safe_load returns None for zero-document stream
        log.warning("strategies.yaml is empty — running with no strategies")
        return []

    try:
        parsed = StrategiesFile.model_validate(raw)
    except ValidationError as e:
        log.warning("strategies.yaml validation failed — running with no strategies:\n%s", e)
        return []

    # Convert dict-of-strategies to list, injecting the dict key as `name`
    return [
        Strategy.model_validate({**s.model_dump(), "name": name})
        for name, s in parsed.strategies.items()
    ]
```

**Edge cases covered:**
- Missing file → FileNotFoundError → warning + `[]`
- Permission error → OSError → warning + `[]`
- Empty file → `yaml.safe_load` returns `None` → warning + `[]`
- `strategies: null` in YAML → `None` dict value → ValidationError (StrategiesFile.strategies requires `dict`) → all-or-nothing → `[]`
- `strategies: {}` → empty dict → valid but returns `[]` (no strategies, no warning — edge case: acceptable per STR-01 which says "missing file → warning", not "empty file → warning")
- `strategies: []` → list, not dict → ValidationError → `[]` (D-07 says reject)
- Unknown field in any trigger → ValidationError at trigger level → propagates up → `[]`
- `min_minutes: 75` typo → extra field on Trigger → ValidationError → `[]`

**NOTE:** The `Strategy` model needs a `name` field added for the list conversion above. Alternatively, return a separate `NamedStrategy` dataclass from `load_strategies`. Planner should decide; both work.

### Pattern 3: FastAPI Endpoint — Per-Request Load

**What:** Load strategies fresh on each API call (Phase 2 scope; Phase 3 scanner caches per loop).

```python
# Source: mirrors existing api.py pattern [VERIFIED: src/predictions/api.py lines 274, 358, 445]
from predictions.strategies import load_strategies

class TriggerResponse(BaseModel):
    sport: Optional[str] = None
    min_minute: Optional[int] = None
    min_lead: Optional[int] = None
    min_yes_price: Optional[int] = None
    max_yes_price: Optional[int] = None


class StrategyResponse(BaseModel):
    name: str
    description: Optional[str] = None
    triggers: list[TriggerResponse]


class StrategiesResponse(BaseModel):
    strategies: list[StrategyResponse]


@app.get("/api/strategies", response_model=StrategiesResponse, dependencies=[Depends(_check_token)])
def get_strategies():
    path = os.getenv("STRATEGIES_PATH", "strategies.yaml")
    strategies = load_strategies(path)
    return StrategiesResponse(
        strategies=[
            StrategyResponse(
                name=s.name,
                description=s.description,
                triggers=[TriggerResponse(**t.model_dump()) for t in s.triggers],
            )
            for s in strategies
        ]
    )
```

**Note:** FastAPI serializes Pydantic models to JSON correctly for `Optional` fields. Fields set to `None` are included as `null` in JSON unless `response_model_exclude_none=True` is set. For trigger fields, including `null` values is fine (client checks truthiness). Alternatively, add `response_model_exclude_none=True` to the decorator to suppress null fields — the planner should decide based on what's easier to consume in TypeScript.

### Pattern 4: Multi-Trigger Engine in TypeScript

**What:** Replace flat `min_minute`/`min_lead` params with `triggers: Trigger[]` in `BacktestParams`. Walk triggers in order for each goal; first match fires.

```typescript
// Source: extends existing backtest.ts detectFire pattern [VERIFIED: dashboard/app/backtest/backtest.ts]

export interface Trigger {
    sport?: string;           // undefined = no constraint
    min_minute?: number;      // undefined = no constraint
    min_lead?: number;        // undefined = no constraint
    min_yes_price?: number;   // info only in backtest — not evaluated
    max_yes_price?: number;   // info only in backtest — not evaluated
}

export interface BacktestParams {
    triggers: Trigger[];           // replaces min_minute + min_lead
    initial_capital: number;
    bet_fraction: number;
    contract_price_cents: number;
}

// Multi-trigger version of detectFire — OR-of-AND semantics
// sport_path: the season's sport_path, used to skip mismatched triggers
function detectFireMulti(
    match: Match,
    triggers: Trigger[],
    season_sport_path: string,
): FireOutcome | null {
    for (const goal of match.goals) {
        const { minute } = parseGoalTime(goal.time);
        const { home, away } = parseScore(goal.score);
        const lead = Math.abs(home - away);

        for (const trigger of triggers) {
            // Skip sport-mismatched triggers silently
            if (trigger.sport !== undefined && trigger.sport !== season_sport_path) {
                continue;
            }
            const minuteOk = trigger.min_minute === undefined || minute >= trigger.min_minute;
            const leadOk = trigger.min_lead === undefined || lead >= trigger.min_lead;
            if (minuteOk && leadOk) {
                const leading_side: "home" | "away" = home > away ? "home" : "away";
                const { home: finalHome, away: finalAway } = parseScore(match.final_score);
                const result: "win" | "loss" =
                    (leading_side === "home" && finalHome > finalAway) ||
                    (leading_side === "away" && finalAway > finalHome)
                        ? "win" : "loss";
                return {
                    match, final_home: finalHome, final_away: finalAway,
                    fired_at_minute: minute,
                    score_at_fire_home: home, score_at_fire_away: away,
                    leading_side, result,
                };
            }
        }
    }
    return null;
}
```

**Backward compatibility note:** The existing `detectFire(match, min_minute, min_lead)` function can remain as-is; `runBacktest` now calls `detectFireMulti` instead. No callers of the old signature need updating since `detectFire` is only called inside `runBacktest`. Alternatively, the planner can rename `detectFire` to `detectFireMulti` with the new signature and update the single call site.

### Pattern 5: React Multi-Trigger State Machine

**What:** Page-level state holds `triggers: Trigger[]` and `selectedStrategy: string`. Edits snap to `"__custom__"`.

```typescript
// Source: extends existing page.tsx useState pattern [VERIFIED: dashboard/app/backtest/page.tsx]

const DEFAULT_TRIGGER: Trigger = { sport: "soccer/eng.1", min_minute: 75, min_lead: 2 };

// Derive initial sport from selected season
const [triggers, setTriggers] = useState<Trigger[]>([DEFAULT_TRIGGER]);
const [selectedStrategy, setSelectedStrategy] = useState<string>("__custom__");
const [strategies, setStrategies] = useState<StrategyWithName[]>([]);

// On strategy dropdown change:
function handleStrategyChange(name: string) {
    if (name === "__custom__") {
        setSelectedStrategy("__custom__");
        return;
    }
    const strat = strategies.find((s) => s.name === name);
    if (!strat) return;
    setSelectedStrategy(name);
    setTriggers(strat.triggers.map(apiTriggerToTrigger));
}

// On any trigger field edit — snap to custom:
function updateTrigger(idx: number, patch: Partial<Trigger>) {
    setSelectedStrategy("__custom__");
    setTriggers((prev) =>
        prev.map((t, i) => (i === idx ? { ...t, ...patch } : t)),
    );
}

// Add trigger (copy of last):
function addTrigger() {
    setSelectedStrategy("__custom__");
    setTriggers((prev) => [...prev, { ...prev[prev.length - 1] }]);
}

// Remove trigger (with confirm):
function removeTrigger(idx: number) {
    if (!window.confirm("Delete this trigger?")) return;
    setSelectedStrategy("__custom__");
    setTriggers((prev) => prev.filter((_, i) => i !== idx));
}
```

**Stale closure avoidance:** Using the functional `setTriggers((prev) => ...)` form avoids stale closure bugs where an `onChange` callback captures an outdated `triggers` value from its creation scope. Always pass an updater function when the new state depends on the old state.

**useMemo dependency:** `triggers` array needs to be in the `useMemo` dep array for `runBacktest`. Because the array is replaced on every edit, `useMemo` will recompute correctly — no JSON.stringify needed.

### Pattern 6: SeasonOption with sport_path

**What:** `seasons.ts` `SeasonOption` gains a `sport_path` field via a mapping constant.

```typescript
// Source: extends existing seasons.ts LEAGUE_NAMES pattern [VERIFIED: dashboard/app/backtest/seasons.ts]

const LEAGUE_SPORT_PATH: Record<string, string> = {
    bundesliga: "soccer/ger.1",
    epl: "soccer/eng.1",
    laliga: "soccer/esp.1",
    ligue1: "soccer/fra.1",
    mls: "soccer/usa.1",
    seriea: "soccer/ita.1",
};

// In parseSeasonFilename or in the SeasonOption construction:
// sport_path: LEAGUE_SPORT_PATH[league] ?? ""
```

The `season_sport_path` (from the selected `SeasonOption`) is passed into `runBacktest` so the engine can silently skip mismatched triggers (D-12).

### Anti-Patterns to Avoid

- **`yaml.load` instead of `yaml.safe_load`:** Arbitrary code execution risk. Always `yaml.safe_load`. [CITED: pyyaml.org]
- **Catching `Exception` in loader:** Over-broad; masks programming errors. Catch `FileNotFoundError`, `OSError` (I/O), and `pydantic.ValidationError` (schema) explicitly.
- **Multiple `os.getenv("STRATEGIES_PATH")` calls:** Single call in `load_strategies`; `api.py` passes the path, doesn't resolve it itself — avoids the env var being read in two places.
- **Importing `load_strategies` at module level and calling it at import time:** Loader is called on-demand (per-request in Phase 2, per-loop in Phase 3). Never load at import time; working directory may differ between dev and production.
- **Relying on `model.dict()` in Pydantic v2:** Use `model.model_dump()`. `dict()` is deprecated in v2.
- **Not passing `season_sport_path` to `runBacktest`:** The engine cannot skip mismatched triggers without knowing which sport is loaded. Must be a parameter.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| YAML parsing | Custom tokenizer/regex | `yaml.safe_load` (PyYAML) | YAML has 72 edge cases including multiline strings, anchors, aliases, typed scalars — regex will miss all of them |
| Schema validation | `isinstance` checks on raw dicts | Pydantic v2 `ValidationError` | Pydantic handles Optional fields, type coercion, nested validation, error message formatting, and JSON serialization all in one |
| Typo detection | Manual field name checking | `extra="forbid"` | Pydantic raises `ValidationError` with the exact unexpected field name, costs zero lines of code |
| Bearer auth in tests | Rolling custom auth middleware | `os.environ["API_TOKEN"] = "test"` in test setup | The `_check_token` dep reads from env; override with monkeypatch or env injection |
| Loading strategy per endpoint call | TTL cache, background refresh | Per-request `open()` + parse | File is <1KB and rarely accessed; OS page cache makes re-reads cheap; Phase 3 scanner handles caching |

---

## Runtime State Inventory

This section is not applicable — Phase 2 adds a new file (`strategies.yaml`) and new code. It does not rename or migrate any existing stored data. The existing `WHAT_IF_STRATEGIES` dict in `scanner.py` is NOT modified in this phase (that's Phase 3/STR-04).

---

## Common Pitfalls

### Pitfall 1: Working Directory Ambiguity

**What goes wrong:** `"strategies.yaml"` as default path resolves relative to the process CWD. In `pnpm dev:api` (dev), CWD is the repo root — correct. In production ECS Fargate, the Dockerfile `WORKDIR` is `/app` and the file is copied to `/app/strategies.yaml` — also correct. However, if someone runs `uvicorn predictions.api:app` from inside `src/`, the path resolves to `src/strategies.yaml` — file not found, silent warning.

**Why it happens:** Python's `open()` uses the process CWD, not the file's location.

**How to avoid:** Document in `.env.example` that `STRATEGIES_PATH` defaults to `"strategies.yaml"` relative to CWD. For production, the Dockerfile must `COPY strategies.yaml /app/strategies.yaml`. Add this to Phase 3's Dockerfile checklist. In Phase 2, dev usage is always from repo root — no action needed now.

**Warning signs:** `"strategies.yaml not found"` warning in logs when the file clearly exists.

### Pitfall 2: `strategies: null` vs `strategies: {}` vs Missing Key

**What goes wrong:** Three distinct YAML states that all look like "no strategies" at a glance:
- File is completely empty → `yaml.safe_load` returns `None` → handled explicitly
- File has `strategies:` with no value → YAML parses as `strategies: None` → `StrategiesFile(strategies=None)` → Pydantic ValidationError (dict expected) → all-or-nothing → `[]`
- File has `strategies: {}` → valid empty dict → `StrategiesFile` constructs → returns `[]` (no warning)

**Why it matters:** `strategies: {}` silently returns zero strategies with no log output. Users who write this accidentally get no trades and no warning. This is intentional by D-07 logic (only error states log warnings), but could confuse operators. Document in `.env.example` or `strategies.yaml` comments.

**How to avoid:** Planner should decide if `strategies: {}` (valid-but-empty) should also emit a warning. Lean recommendation: emit `log.info("strategies.yaml loaded with 0 strategies")` so it's visible at INFO level without being alarming.

### Pitfall 3: PyYAML Absent from Deps

**What goes wrong:** `import yaml` at the top of `strategies.py` raises `ModuleNotFoundError` in a fresh environment.

**Why it happens:** PyYAML is not in `pyproject.toml` and not in `uv.lock`. [VERIFIED: searched uv.lock, not present]

**How to avoid:** Add `pyyaml>=6.0` to `pyproject.toml` `[project] dependencies` and run `uv sync`. This is the one new Python dependency this phase requires. The no-new-deps rule should be overridden for this case — there is no stdlib alternative for YAML parsing, and the file format is locked (D-05).

### Pitfall 4: Pydantic v2 `model_validate` vs `parse_obj`

**What goes wrong:** Using `Model.parse_obj(data)` (Pydantic v1 API) raises `AttributeError` in Pydantic v2.

**Why it happens:** v2 renamed `parse_obj` → `model_validate`. The codebase has existing Pydantic v2 usage in `api.py` (confirmed `BaseModel` imports), but uses response models that don't call `model_validate` directly — so there are no existing call-site examples to follow.

**How to avoid:** Always use `Model.model_validate(raw_dict)`. Use `instance.model_dump()` not `instance.dict()`.

### Pitfall 5: FastAPI Pydantic Response Serialization of Optional Fields

**What goes wrong:** `TriggerResponse(sport=None, min_minute=None, ...)` serializes to `{"sport": null, "min_minute": null, ...}` in the JSON response. TypeScript client then needs to distinguish `null` from `undefined`.

**How to avoid:** Add `response_model_exclude_none=True` to `@app.get("/api/strategies", ...)` if you want to suppress null fields:
```python
@app.get("/api/strategies", response_model=StrategiesResponse,
         response_model_exclude_none=True, dependencies=[Depends(_check_token)])
```
This makes trigger fields absent (TypeScript `undefined`) when not set. The planner should pick one convention and document it. Using `null` is simpler to reason about; `undefined`/absent requires optional chaining.

### Pitfall 6: Multi-Trigger Engine — All Triggers Sport-Mismatched

**What goes wrong:** A strategy with 3 triggers for `basketball/nba`, `basketball/nba`, `basketball/nba` is loaded while a soccer season is displayed. All 3 triggers are skipped silently. The engine fires zero trades. The summary shows "0 bet on, 3 of 3 triggers skipped."

**Why it matters:** Not a bug — this is exactly the specified behavior (D-18, D-15). But it looks like a broken backtest to users who don't notice the muted line.

**How to avoid:** The "N of M triggers skipped" line (D-18) addresses this. When M == N (all skipped), the message would be "3 of 3 triggers skipped: basketball/nba (no data for current season)". The grayed-out trigger cards (D-15) provide additional visual confirmation.

### Pitfall 7: React Stale State in Trigger Update Handlers

**What goes wrong:** An `onChange` handler in a trigger card captures `triggers` via closure at render time. If the user rapidly edits two fields in different trigger cards, the second update may overwrite the first because both handlers captured the same stale `triggers` array.

**How to avoid:** Always use the functional updater form for `setTriggers`:
```typescript
setTriggers((prev) => prev.map((t, i) => i === idx ? { ...t, ...patch } : t));
```
Never do:
```typescript
setTriggers(triggers.map((t, i) => i === idx ? { ...t, ...patch } : t));
// ↑ stale closure: `triggers` captured at render time, not current state
```

### Pitfall 8: Bearer Auth in TestClient

**What goes wrong:** `TestClient(app).get("/api/strategies")` returns `403 API_TOKEN not configured` in tests because `API_TOKEN` env var is not set.

**How to avoid:** In test fixtures or test bodies, set the env var before calling the endpoint:
```python
import os
os.environ["API_TOKEN"] = "test-token"
response = client.get("/api/strategies", headers={"Authorization": "Bearer test-token"})
```
Or use a `pytest.fixture` that sets and clears the env var via `monkeypatch`:
```python
@pytest.fixture
def api_client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from fastapi.testclient import TestClient
    from predictions.api import app
    return TestClient(app), "test-token"
```

---

## Code Examples

### YAML shape the loader expects (D-05)

```yaml
# strategies.yaml
strategies:
  conservative_late_lead:
    description: "Late game, solid lead, premium price"
    triggers:
      - sport: soccer/eng.1
        min_minute: 80
        min_lead: 2
        min_yes_price: 92
        max_yes_price: 99
  early_value:
    description: "Earlier entry, requires bigger lead"
    triggers:
      - sport: soccer/eng.1
        min_minute: 65
        min_lead: 3
        min_yes_price: 88

  # ------- WHAT_IF_STRATEGIES translations (commented out) -------
  # low_price:
  #   description: "Lower Price (90¢) — translation of WHAT_IF low_price"
  #   triggers:
  #     - min_minute: 75    # countup_secs: 4500 = 75 min elapsed
  #       min_lead: 2       # lead_pct: 100 of configured lead (≈2 for EPL)
  #       min_yes_price: 90
  # ...
```

### API response shape (D-10)

```json
{
  "strategies": [
    {
      "name": "conservative_late_lead",
      "description": "Late game, solid lead, premium price",
      "triggers": [
        {"sport": "soccer/eng.1", "min_minute": 80, "min_lead": 2, "min_yes_price": 92, "max_yes_price": 99}
      ]
    }
  ]
}
```

With `response_model_exclude_none=True`, triggers without all fields would omit null keys:
```json
{"sport": "soccer/eng.1", "min_minute": 80, "min_lead": 2, "min_yes_price": 92}
```

### Dashboard fetch pattern (on mount, following existing page.tsx style)

```typescript
// Source: extends existing useEffect pattern in page.tsx [VERIFIED: dashboard/app/backtest/page.tsx:92-97]
const [strategies, setStrategies] = useState<ApiStrategy[]>([]);

useEffect(() => {
    fetch("/api/strategies", { cache: "no-store" })
        .then((r) => r.json())
        .then((data: { strategies: ApiStrategy[] }) => setStrategies(data.strategies))
        .catch(() => {
            // Strategies unavailable — Custom mode still works
        });
}, []);
```

The catch handler is intentional: if the API is unreachable or `strategies.yaml` is missing, the dropdown will show only "— Custom —" and the user can still use the backtest manually.

### Trigger card sport-mismatch graying

```typescript
// Determines if a trigger's sport matches the currently-loaded season
function isTriggerMismatched(trigger: Trigger, seasonSportPath: string): boolean {
    return trigger.sport !== undefined && trigger.sport !== seasonSportPath;
}

// In JSX:
const mismatched = isTriggerMismatched(trigger, selected?.sport_path ?? "");
<div className={`p-3 rounded border ${mismatched ? "opacity-40 border-gray-700" : "border-gray-600"}`}>
    {mismatched && (
        <p className="text-xs text-yellow-500 mb-2" title={`Skipped — no ${trigger.sport} data loaded`}>
            ⚠ Skipped — no {trigger.sport} data loaded
        </p>
    )}
    {/* ... sliders ... */}
</div>
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `WHAT_IF_STRATEGIES` hardcoded dict in `scanner.py` | `strategies.yaml` at repo root | Phase 2 (this phase) | Scanner can be reconfigured without code changes |
| Flat `min_minute` / `min_lead` in `BacktestParams` | `triggers: Trigger[]` array | Phase 2 (this phase) | Supports OR-of-AND multi-trigger evaluation |
| Single-trigger `detectFire(match, min_minute, min_lead)` | Multi-trigger `detectFireMulti` or equivalent wrapper | Phase 2 (this phase) | First-fire-wins semantics across trigger set |
| Pydantic v1 `.dict()` / `.parse_obj()` | Pydantic v2 `.model_dump()` / `.model_validate()` | Already v2 in codebase | Consistent with existing api.py; don't regress to v1 aliases |

**Deprecated/outdated:**
- `Trigger.dict()`: Use `Trigger.model_dump()` in Pydantic v2.
- `Model.parse_obj(d)`: Use `Model.model_validate(d)` in Pydantic v2.
- `yaml.load(f)` without `Loader=`: Use `yaml.safe_load(f)` — PyYAML emits a `FullLoader` warning for bare `load()` since v5.1.

---

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 8.x + pytest-asyncio 0.24 |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` — `asyncio_mode = "auto"`, `testpaths = ["tests"]` |
| Quick run command | `uv run pytest tests/test_strategies.py tests/test_strategies_api.py -x` |
| Full suite command | `uv run pytest tests/` |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| STR-01 | Missing file → warning + empty list | unit | `pytest tests/test_strategies.py::test_missing_file_returns_empty -x` | ❌ Wave 0 |
| STR-01 | Valid file → non-empty list | unit | `pytest tests/test_strategies.py::test_valid_file_loads -x` | ❌ Wave 0 |
| STR-01 | STRATEGIES_PATH env override | unit | `pytest tests/test_strategies.py::test_strategies_path_env -x` | ❌ Wave 0 |
| STR-02 | Empty triggers list (`triggers: []`) rejected | unit | `pytest tests/test_strategies.py::test_empty_triggers_rejected -x` | ❌ Wave 0 |
| STR-02 | Unknown field in trigger rejected (`extra="forbid"`) | unit | `pytest tests/test_strategies.py::test_unknown_trigger_field_rejected -x` | ❌ Wave 0 |
| STR-02 | Malformed YAML rejects entire file (all-or-nothing) | unit | `pytest tests/test_strategies.py::test_malformed_file_returns_empty -x` | ❌ Wave 0 |
| STR-02 | Missing `sport` in trigger = no sport constraint | unit | `pytest tests/test_strategies.py::test_missing_sport_no_constraint -x` | ❌ Wave 0 |
| STR-03 | `GET /api/strategies` returns correct JSON shape | integration | `pytest tests/test_strategies_api.py::test_get_strategies_shape -x` | ❌ Wave 0 |
| STR-03 | `GET /api/strategies` without auth returns 401 | integration | `pytest tests/test_strategies_api.py::test_get_strategies_unauthed -x` | ❌ Wave 0 |
| STR-03 | `GET /api/strategies` with missing file returns `{"strategies": []}` | integration | `pytest tests/test_strategies_api.py::test_get_strategies_missing_file -x` | ❌ Wave 0 |
| BT-07 | Multi-trigger runBacktest fires on first matching trigger per match | unit (TS) | `pnpm build` (tsc) + manual browser test | ❌ Wave 0 |
| BT-07 | Sport-mismatched triggers silently skipped in engine | unit (TS) | `pnpm build` + manual browser test | ❌ Wave 0 |

**TypeScript engine tests:** No TS test runner is configured in this project (no jest, vitest). BT-07 engine behaviors are verified via `pnpm build` (TypeScript compilation catches type errors) and manual browser testing. This is consistent with the project's existing test approach for the backtest engine (Phase 1 used the same approach).

### Sampling Rate
- **Per task commit:** `uv run pytest tests/test_strategies.py tests/test_strategies_api.py -x && uv run ruff check . && uv run ruff format --check . && uv run ty check`
- **Per wave merge:** `uv run pytest tests/ && cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] `tests/test_strategies.py` — covers STR-01, STR-02 unit tests
- [ ] `tests/test_strategies_api.py` — covers STR-03 endpoint tests
- [ ] `tests/fixtures/strategies-valid.yaml` — at least one valid strategy
- [ ] `tests/fixtures/strategies-no-triggers.yaml` — strategy with `triggers: []`
- [ ] `tests/fixtures/strategies-unknown-field.yaml` — trigger with unknown field
- [ ] `tests/fixtures/strategies-empty.yaml` — empty file (tests `yaml.safe_load → None`)
- [ ] `src/predictions/strategies.py` — new module (must exist before tests can import it)

---

## Recommended File Layout

```
# New files (to create):
strategies.yaml                                          # repo root — locked location (D-05)
src/predictions/strategies.py                            # loader + Pydantic models
tests/test_strategies.py                                 # unit tests for loader/validator
tests/test_strategies_api.py                             # FastAPI endpoint tests
tests/fixtures/strategies-valid.yaml                     # well-formed fixture
tests/fixtures/strategies-no-triggers.yaml               # empty triggers list
tests/fixtures/strategies-unknown-field.yaml             # extra field on trigger
tests/fixtures/strategies-empty.yaml                     # zero-byte or blank file

# Modified files:
src/predictions/api.py           # add StrategiesResponse + GET /api/strategies
pyproject.toml                   # add pyyaml>=6.0 to [project] dependencies
.env.example                     # document STRATEGIES_PATH (one line)
dashboard/app/backtest/backtest.ts   # Trigger type, multi-trigger BacktestParams, new engine
dashboard/app/backtest/seasons.ts    # add sport_path to LEAGUE_SPORT_PATH + SeasonOption
dashboard/app/backtest/page.tsx      # multi-trigger UI, strategy dropdown, fetch
```

**Module location rationale (Claude's Discretion, resolved):** Create `src/predictions/strategies.py` as a new module. Rationale: (1) CONVENTIONS.md guidance says "New external integration → its own module" — a YAML file is a new external input boundary; (2) `strategies.py` will be imported by both `api.py` and (in Phase 3) `scanner.py` — a single shared module avoids duplication; (3) `api.py` is already 500+ lines; adding models + loader there would grow it further in the direction of the known anti-pattern.

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `pyyaml` is not a transitive dep of any existing package in the lock file | Standard Stack | [VERIFIED: searched uv.lock — not present] — risk = zero |
| A2 | `tests/fixtures/` directory does not yet exist | Recommended File Layout | [ASSUMED] — planner should verify; if it exists, reuse it |
| A3 | `fastapi.testclient.TestClient` is available (it ships with fastapi extras or httpx) | Pitfall 8 | [VERIFIED: httpx 0.28.1 is in uv.lock, which TestClient requires] |
| A4 | The `detectFire` function has no external callers outside `runBacktest` | Pattern 4 | [VERIFIED: 01-PATTERNS.md confirms zero callers outside page.tsx/backtest.ts] |
| A5 | Page-level `page.tsx` is 320 lines post-Phase-1 (not 520 as stated in Phase 2 brief) | Architecture | [VERIFIED: file is 321 lines] — Phase 2 context brief said "520 LOC" but that was pre-Phase-1 |
| A6 | `BacktestTrade` needs no `trigger_index` field in Phase 2 | Phase Requirements | [ASSUMED per D-13 / CONTEXT.md Deferred] — correct if Phase 4 handles analytics |

---

## Open Questions for Planner

1. **PyYAML dependency addition**
   - What we know: PyYAML is not in the project's deps. The file format is YAML (D-05). No stdlib alternative exists for YAML parsing.
   - Recommendation: Add `pyyaml>=6.0` to `pyproject.toml`. This is the only new Python dep and is unavoidable given the locked YAML format. Treat as a justified exception to the no-new-deps rule, or flag for user confirmation.

2. **`response_model_exclude_none` on `GET /api/strategies`**
   - What we know: Optional trigger fields (sport, min_minute, etc.) will be `null` in JSON if not set, or absent if `exclude_none=True`.
   - What's unclear: Which representation is easier for the TypeScript client? `null` → check `!= null`; absent → optional chaining `?.`.
   - Recommendation: Use `response_model_exclude_none=True` so the TypeScript interface can use optional properties (`sport?: string`) and the client checks `trigger.sport !== undefined`. More idiomatic TypeScript.

3. **`StrategiesFile` vs `NamedStrategy` naming**
   - What we know: `load_strategies()` needs to add `name` to each strategy (the dict key). Options: (a) add a `name` field to `Strategy` model and inject it, or (b) return a separate `NamedStrategy(Strategy)` subclass, or (c) return `list[tuple[str, Strategy]]`.
   - Recommendation: Add `name: str` directly to the `Strategy` Pydantic model with a default of `""` (so the YAML parser doesn't require it — dict keys aren't model fields). The loader injects the name after parsing. Simplest approach.

4. **Sport dropdown contents in per-trigger UI**
   - What we know: `KALSHI_TO_ESPN` in `espn.py` has ~12 sport paths. Only 6 have backtest data (the season JSONs).
   - Recommendation: List only the 6 sports with backtest data in the per-trigger sport dropdown (the `LEAGUE_SPORT_PATH` keys). If a loaded strategy has a trigger with a sport not in this list, the grayed-out card shows it — users can still see it, just can't edit to it. This avoids confusing options that will always be "skipped".

5. **`strategy.description` rendering**
   - What we know: Description is optional. The dropdown already shows `strategy.name`.
   - Recommendation: Render description as a small subtitle under the selected strategy in the dropdown area (e.g., a `<p className="text-xs text-gray-400">` below the `<select>`). Tooltip on `<option>` tags is not reliably styled cross-browser.

---

## Environment Availability

All dependencies are already available; Phase 2 adds only one new Python package.

| Dependency | Required By | Available | Version | Fallback |
|------------|------------|-----------|---------|----------|
| pydantic | strategies.py models | ✓ (transitive via FastAPI) | 2.12.5 | — |
| fastapi + TestClient | test_strategies_api.py | ✓ | 0.135.1 | — |
| httpx | TestClient (required by fastapi[test]) | ✓ | 0.28.1 | — |
| pytest | test runner | ✓ | ≥8.0 | — |
| pyyaml | strategies.py loader | ✗ | — | No stdlib alternative — must add dep |
| uv | dependency management | ✓ | (installed) | — |

**Missing dependencies with no fallback:**
- `pyyaml` — required for YAML parsing; must be added via `uv add pyyaml` before Wave 0 can begin

**Missing dependencies with fallback:**
- None

---

## Security Domain

`security_enforcement` is not explicitly set to `false` in `.planning/config.json` (file may not exist). Treating as enabled.

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes — `GET /api/strategies` must be gated | Existing `Depends(_check_token)` Bearer pattern |
| V3 Session Management | no | Bearer token is stateless |
| V4 Access Control | yes — strategies endpoint is read-only, Bearer sufficient | `Depends(_check_token)` |
| V5 Input Validation | yes — YAML input at filesystem boundary | Pydantic v2 `extra="forbid"` + `ValidationError` catch |
| V6 Cryptography | no — no new crypto |  |

### Known Threat Patterns for this stack

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| YAML arbitrary object injection | Tampering / Elevation of Privilege | `yaml.safe_load` only — never `yaml.load` |
| Unauthenticated strategy enumeration | Information Disclosure | `Depends(_check_token)` on endpoint |
| Path traversal via STRATEGIES_PATH | Tampering | `STRATEGIES_PATH` is server-side env var, not user input — low risk; document that it should not be user-controlled |
| YAML billion-laughs / alias amplification | Denial of Service | PyYAML SafeLoader is NOT protected against alias amplification by default. For a local file read by an operator, risk is low. For Phase 3 if YAML is ever user-editable, add a file size limit check. |

---

## Sources

### Primary (HIGH confidence)
- `uv.lock` (searched) — confirmed pydantic 2.12.5, fastapi 0.135.1, httpx 0.28.1 are present; pyyaml is absent
- `pyproject.toml` (read directly) — confirmed no pyyaml in dependencies
- `src/predictions/api.py` (read lines 1-50, 240-320, 400-470) — verified `_check_token`, `Depends`, `BaseModel` patterns
- `dashboard/app/backtest/backtest.ts` (read full) — verified `detectFire`, `runBacktest`, `BacktestParams` current shape
- `dashboard/app/backtest/page.tsx` (read full) — verified current 321-line structure, state hooks, `useMemo` pattern
- `dashboard/app/backtest/seasons.ts` (read full) — verified `SeasonOption`, `LEAGUE_NAMES`, static import pattern
- `tests/conftest.py` (read full) — verified `isolated_db` pattern; no `isolated_soccer_db`-style YAML fixtures yet
- `dashboard/app/api/[...path]/route.ts` (read full) — verified catch-all proxy with Bearer injection
- `.planning/phases/01-backtest-p-l-math/01-PATTERNS.md` (read full) — verified Phase 1 patterns for page.tsx structure

### Secondary (MEDIUM confidence)
- [CITED: pydantic.dev/docs] — confirmed `ConfigDict(extra='forbid')` and `Annotated[list, Field(min_length=1)]` syntax for Pydantic v2
- [CITED: pyyaml.org/wiki/PyYAMLDocumentation] — confirmed `yaml.safe_load` vs `yaml.load` distinction; `None` return for empty file

### Tertiary (LOW confidence)
- None — all critical claims verified from primary sources.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — verified from uv.lock; pyyaml absence is VERIFIED
- Architecture: HIGH — all patterns derived from actual existing code
- Pitfalls: HIGH for Python pitfalls (all verified); MEDIUM for React stale closure (standard React knowledge, not verified via tool)
- Test fixtures: MEDIUM — `tests/fixtures/` directory existence assumed (A2)

**Research date:** 2026-04-30
**Valid until:** 2026-05-30 (stable deps; short-lived for React/Next.js aspects)
