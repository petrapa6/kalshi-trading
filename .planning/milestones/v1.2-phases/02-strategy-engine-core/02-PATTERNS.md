# Phase 2: Strategy Engine Core - Pattern Map

**Mapped:** 2026-04-30
**Files analyzed:** 13 new/modified files
**Analogs found:** 12 / 13 (1 has no codebase analog — YAML fixture files are novel)

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|-------------------|------|-----------|----------------|---------------|
| `src/predictions/strategies.py` | model + loader | file-I/O → transform | `src/predictions/api.py` (Pydantic models section) | role-match |
| `src/predictions/api.py` | endpoint | request-response | `src/predictions/api.py` lines 274, 358 | exact (self) |
| `tests/test_strategies.py` | test | batch | `tests/test_run_backtest.py` | exact |
| `tests/test_strategies_api.py` | test | request-response | `tests/test_backtest_api.py` | exact |
| `tests/fixtures/strategies-valid.yaml` | fixture | file-I/O | none — novel | none |
| `tests/fixtures/strategies-no-triggers.yaml` | fixture | file-I/O | none — novel | none |
| `tests/fixtures/strategies-unknown-field.yaml` | fixture | file-I/O | none — novel | none |
| `tests/fixtures/strategies-empty.yaml` | fixture | file-I/O | none — novel | none |
| `strategies.yaml` | config | file-I/O | none — novel | none |
| `dashboard/app/backtest/backtest.ts` | engine utility | transform | `dashboard/app/backtest/backtest.ts` (self) | exact (self-modification) |
| `dashboard/app/backtest/seasons.ts` | data catalog | transform | `dashboard/app/backtest/seasons.ts` (self) | exact (self-modification) |
| `dashboard/app/backtest/page.tsx` | component | request-response + event-driven | `dashboard/app/backtest/page.tsx` (self) | exact (self-modification) |
| `pyproject.toml` | config | — | `pyproject.toml` lines 6-15 | exact (self) |
| `.env.example` | config | — | `.env.example` | exact (self) |

---

## Pattern Assignments

### `src/predictions/strategies.py` (model + loader, file-I/O)

**Analog:** `src/predictions/api.py` lines 40-147 (Pydantic model definitions)

**Imports pattern** — mirror `api.py` stdlib-first isort order:
```python
# src/predictions/strategies.py — full import block shape
import logging
import os
from typing import Annotated, Optional

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError
```

**Pydantic model pattern** (from `api.py` lines 40-80, `TradeResponse` shape):
```python
# api.py lines 60-80 — existing Optional field + BaseModel pattern to mirror
class TradeResponse(BaseModel):
    id: int
    placed_at: Optional[datetime] = None
    ticker: str
    yes_price: int
    status: str
    pnl_cents: Optional[int] = None
```

**New models must add `extra="forbid"` via ConfigDict — no existing analog uses it, so copy from RESEARCH.md Pattern 1:**
```python
class Trigger(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sport: Optional[str] = None
    min_minute: Optional[int] = None
    min_lead: Optional[int] = None
    min_yes_price: Optional[int] = None
    max_yes_price: Optional[int] = None


class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = ""          # injected by loader from dict key; not in YAML
    description: Optional[str] = None
    triggers: Annotated[list[Trigger], Field(min_length=1)]


class StrategiesFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategies: dict[str, Strategy]
```

**Loader error-handling pattern** — the project's own error-handling convention (CONVENTIONS.md: "catch known exceptions explicitly; never blanket `except Exception`"). Extend to file I/O:
```python
log = logging.getLogger(__name__)   # matches api.py line 151 pattern


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
        log.warning("Failed to read strategies file %s: %s", path, e)
        return []
    if raw is None:
        log.warning("strategies.yaml is empty — running with no strategies")
        return []
    try:
        parsed = StrategiesFile.model_validate(raw)
    except ValidationError as e:
        log.warning("strategies.yaml validation failed:\n%s", e)
        return []
    return [
        Strategy.model_validate({**s.model_dump(), "name": name})
        for name, s in parsed.strategies.items()
    ]
```

**Pitfall:** Use `model_validate()` not `parse_obj()` (Pydantic v2). Use `model_dump()` not `dict()`. Both v1 aliases raise `AttributeError` at runtime.

**Pitfall:** Never `import yaml` without `pyyaml` in `pyproject.toml`. It is not yet a declared dependency — add `"pyyaml>=6.0"` to `[project] dependencies` before writing the import.

---

### `src/predictions/api.py` — add `GET /api/strategies` (endpoint, request-response)

**Analog:** `src/predictions/api.py` lines 274, 358 — `get_stats` and `get_trades` endpoints

**Existing endpoint pattern** (lines 274–276, 358–359):
```python
@app.get("/api/stats", response_model=StatsResponse, dependencies=[Depends(_check_token)])
def get_stats():
    session = get_session()
    ...

@app.get("/api/trades", response_model=TradesListResponse, dependencies=[Depends(_check_token)])
def get_trades(limit: int = 50, offset: int = 0):
    ...
```

**Existing `_check_token` dependency** (lines 258–266):
```python
def _check_token(authorization: str | None = Header(None)):
    """Verify Bearer token for mutable endpoints."""
    expected = os.getenv("API_TOKEN", "")
    if not expected:
        raise HTTPException(403, "API_TOKEN not configured")
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(401, "Missing Bearer token")
    if authorization.removeprefix("Bearer ") != expected:
        raise HTTPException(401, "Invalid token")
```

**Existing Pydantic response model pattern** (lines 40–57 for flat model, lines 78–115 for list-wrapper):
```python
class TradesListResponse(BaseModel):
    trades: list[TradeResponse]
```

**New endpoint — copy this exact shape:**
```python
# Add near the top Pydantic block (after existing response models, before "--- App ---")
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


# Add endpoint after existing GET endpoints (e.g., after get_stats):
@app.get(
    "/api/strategies",
    response_model=StrategiesResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(_check_token)],
)
def get_strategies():
    from predictions.strategies import load_strategies

    strategies = load_strategies()
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

**Import to add** — place in local imports block per isort order:
```python
from predictions.strategies import load_strategies
```
Or use the lazy import shown above (inside the handler) to avoid circular import risks at startup.

**Pitfall:** `response_model_exclude_none=True` causes absent trigger fields to be omitted from JSON entirely (TypeScript sees `undefined`, not `null`). This is the preferred convention for this endpoint — use `trigger.sport !== undefined` checks on the TypeScript side.

---

### `tests/test_strategies.py` (unit test, file-I/O)

**Analog:** `tests/test_run_backtest.py` lines 1–60 — Pydantic ValidationError test pattern

**Imports pattern** (from `test_run_backtest.py` lines 1–5):
```python
import pytest
from pydantic import ValidationError
```

**ValidationError assertion pattern** (from `test_run_backtest.py` lines 24–34):
```python
with pytest.raises(ValidationError):
    BacktestRequest(
        league="SPL",   # invalid value triggers ValidationError
        ...
    )
```

**Pattern for YAML fixture loading** — use `tmp_path` fixture (built-in pytest) or `tests/fixtures/` static files. The project uses `monkeypatch` extensively (see `conftest.py`). Combine:
```python
def test_valid_file_loads(tmp_path):
    from predictions.strategies import load_strategies

    f = tmp_path / "strategies.yaml"
    f.write_text("""
strategies:
  my_strat:
    triggers:
      - sport: soccer/eng.1
        min_minute: 80
        min_lead: 2
""")
    result = load_strategies(str(f))
    assert len(result) == 1
    assert result[0].name == "my_strat"


def test_missing_file_returns_empty():
    from predictions.strategies import load_strategies

    result = load_strategies("/nonexistent/path.yaml")
    assert result == []


def test_unknown_trigger_field_rejected(tmp_path):
    from predictions.strategies import load_strategies

    f = tmp_path / "bad.yaml"
    f.write_text("""
strategies:
  s:
    triggers:
      - min_minutes: 80   # typo — extra field
""")
    result = load_strategies(str(f))
    assert result == []
```

**STRATEGIES_PATH env pattern** — mirrors `monkeypatch.setenv` from `test_backtest_api.py`:
```python
def test_strategies_path_env(tmp_path, monkeypatch):
    from predictions.strategies import load_strategies

    f = tmp_path / "custom.yaml"
    f.write_text("strategies:\n  s:\n    triggers:\n      - min_lead: 2\n")
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    result = load_strategies()   # no path arg — reads from env
    assert len(result) == 1
```

---

### `tests/test_strategies_api.py` (integration test, request-response)

**Analog:** `tests/test_backtest_api.py` lines 1–103 — exact pattern to copy

**Client fixture pattern** (from `test_backtest_api.py` lines 5–10):
```python
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)
```

**Auth test pattern** (from `test_backtest_api.py` lines 13–15):
```python
def test_strategies_requires_bearer(client):
    resp = client.get("/api/strategies")
    assert resp.status_code == 401
```

**Happy path test with env override:**
```python
def test_get_strategies_shape(client, tmp_path, monkeypatch):
    f = tmp_path / "s.yaml"
    f.write_text("""
strategies:
  test_strat:
    description: "A test strategy"
    triggers:
      - sport: soccer/eng.1
        min_minute: 80
        min_lead: 2
""")
    monkeypatch.setenv("STRATEGIES_PATH", str(f))
    resp = client.get("/api/strategies", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
    assert data["strategies"][0]["name"] == "test_strat"
    assert data["strategies"][0]["triggers"][0]["min_minute"] == 80
```

**Missing file test:**
```python
def test_get_strategies_missing_file(client, monkeypatch):
    monkeypatch.setenv("STRATEGIES_PATH", "/nonexistent/path.yaml")
    resp = client.get("/api/strategies", headers={"Authorization": "Bearer test-token"})
    assert resp.status_code == 200
    assert resp.json() == {"strategies": []}
```

**Pitfall:** The `client` fixture imports `predictions.api` inside the fixture body (after `monkeypatch.setenv`). This ordering matters — the module may cache env vars at import time for other things. Copy the deferred-import pattern exactly.

---

### `dashboard/app/backtest/backtest.ts` (engine utility, transform)

**Analog:** `dashboard/app/backtest/backtest.ts` lines 1–222 — self-modification

**Current `BacktestParams` interface** (lines 5–11) to be replaced:
```typescript
// CURRENT (Phase 1) — replace this:
export interface BacktestParams {
    min_minute: number;
    min_lead: number;
    initial_capital: number;
    bet_fraction: number;
    contract_price_cents: number;
}
```

**New `Trigger` interface and updated `BacktestParams`** — add above the existing interface block:
```typescript
// NEW — add at top of Types section
export interface Trigger {
    sport?: string;           // undefined = no sport constraint
    min_minute?: number;      // undefined = no constraint
    min_lead?: number;        // undefined = no constraint
    min_yes_price?: number;   // read-only info in backtest; not evaluated
    max_yes_price?: number;   // read-only info in backtest; not evaluated
}

export interface BacktestParams {
    triggers: Trigger[];            // replaces min_minute + min_lead
    initial_capital: number;
    bet_fraction: number;
    contract_price_cents: number;
}
```

**Current `detectFire` function** (lines 87–122) — keep signature unchanged, add `detectFireMulti` alongside it:
```typescript
// NEW — add after existing detectFire, before runBacktest
// season_sport_path: from SeasonOption.sport_path; used to skip mismatched triggers
function detectFireMulti(
    match: Match,
    triggers: Trigger[],
    season_sport_path: string,
): FireOutcome | null {
    const { home: finalHome, away: finalAway } = parseScore(match.final_score);

    for (const goal of match.goals) {
        const { minute } = parseGoalTime(goal.time);
        const { home, away } = parseScore(goal.score);
        const lead = Math.abs(home - away);

        for (const trigger of triggers) {
            if (trigger.sport !== undefined && trigger.sport !== season_sport_path) {
                continue;    // silently skip mismatched trigger (D-12)
            }
            const minuteOk = trigger.min_minute === undefined || minute >= trigger.min_minute;
            const leadOk = trigger.min_lead === undefined || lead >= trigger.min_lead;
            if (minuteOk && leadOk) {
                const leading_side: "home" | "away" = home > away ? "home" : "away";
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

**Updated `runBacktest` signature** — change the call from `detectFire` to `detectFireMulti`; add `season_sport_path` parameter:
```typescript
// MODIFIED — runBacktest now accepts season_sport_path
export function runBacktest(
    file: SeasonFile,
    params: BacktestParams,
    season_sport_path: string,
): BacktestResult {
    const { triggers, initial_capital, bet_fraction, contract_price_cents } = params;
    // ...
    // replace: const fire = detectFire(match, min_minute, min_lead);
    // with:
    const fire = detectFireMulti(match, triggers, season_sport_path);
    // rest of function body unchanged
}
```

**Pitfall:** `detectFire` (lines 87–122) is only called by `runBacktest` — confirmed no external callers. Safe to leave it in place alongside `detectFireMulti` or remove it; keeping it avoids churn if Phase 3 needs the single-trigger variant.

---

### `dashboard/app/backtest/seasons.ts` (data catalog, transform)

**Analog:** `dashboard/app/backtest/seasons.ts` lines 59–135 — self-modification

**Existing `LEAGUE_NAMES` constant pattern** (lines 59–66):
```typescript
const LEAGUE_NAMES: Record<string, string> = {
    bundesliga: "Bundesliga",
    epl: "EPL",
    laliga: "La Liga",
    ligue1: "Ligue 1",
    mls: "MLS",
    seriea: "Serie A",
};
```

**Add parallel `LEAGUE_SPORT_PATH` constant** immediately after `LEAGUE_NAMES`:
```typescript
// NEW — parallel to LEAGUE_NAMES; used by page.tsx to derive season sport_path
export const LEAGUE_SPORT_PATH: Record<string, string> = {
    bundesliga: "soccer/ger.1",
    epl: "soccer/eng.1",
    laliga: "soccer/esp.1",
    ligue1: "soccer/fra.1",
    mls: "soccer/usa.1",
    seriea: "soccer/ita.1",
};
```

**Extend `SeasonOption` interface** (lines 91–95) — add `sport_path` field:
```typescript
export interface SeasonOption {
    key: string;
    parsed: ParsedFilename;
    data: SeasonFile;
    sport_path: string;   // NEW — e.g. "soccer/eng.1"; "" if not in mapping
}
```

**Update `SEASONS` construction** (lines 120–135) — inject `sport_path` in the flatMap return:
```typescript
// In the IMPORTS.flatMap callback, change the return object:
return [{ key: filename, parsed, data, sport_path: LEAGUE_SPORT_PATH[parsed.league] ?? "" }];
```

---

### `dashboard/app/backtest/page.tsx` (component, request-response + event-driven)

**Analog:** `dashboard/app/backtest/page.tsx` lines 83–320 — self-modification

**Existing `useEffect` auth check pattern** (lines 92–97) — copy shape for strategies fetch:
```typescript
// EXISTING auth useEffect (lines 92–97) — copy structure for strategies fetch
useEffect(() => {
    checkAuth().then((ok) => {
        if (!ok) window.location.href = "/";
        else setAuthed(true);
    });
}, []);
```

**New strategies fetch pattern** — add alongside the auth useEffect:
```typescript
// NEW — fetch strategies once on mount; failure leaves dropdown at Custom-only
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

**Existing `useMemo` pattern for `runBacktest`** (lines 104–123) — update dep array and call:
```typescript
// EXISTING (lines 104–123) — replace min_minute/min_lead state with triggers
const result = useMemo(
    () =>
        selected
            ? runBacktest(selected.data, {
                  triggers,                        // NEW: replaces min_minute + min_lead
                  initial_capital: initialCapital,
                  bet_fraction: betFractionPct / 100,
                  contract_price_cents: contractPriceCents,
              }, selected.sport_path)              // NEW: season_sport_path arg
            : null,
    [selected, triggers, initialCapital, betFractionPct, contractPriceCents],
);
```

**State replacement** — remove `minMinute`/`minLead` useState, add `triggers`/`selectedStrategy`/`strategies`:
```typescript
// REMOVE:
const [minMinute, setMinMinute] = useState(75);
const [minLead, setMinLead] = useState(2);

// ADD:
const [triggers, setTriggers] = useState<Trigger[]>([
    { sport: selected?.sport_path ?? "soccer/eng.1", min_minute: 75, min_lead: 2 },
]);
const [selectedStrategy, setSelectedStrategy] = useState<string>("__custom__");
```

**Trigger mutation handlers** — use functional updater form to avoid stale closure (RESEARCH.md Pitfall 7):
```typescript
// Always use functional updater — never capture triggers via closure
function updateTrigger(idx: number, patch: Partial<Trigger>) {
    setSelectedStrategy("__custom__");
    setTriggers((prev) => prev.map((t, i) => (i === idx ? { ...t, ...patch } : t)));
}

function addTrigger() {
    setSelectedStrategy("__custom__");
    setTriggers((prev) => [...prev, { ...prev[prev.length - 1] }]);
}

function removeTrigger(idx: number) {
    if (!window.confirm("Delete this trigger?")) return;
    setSelectedStrategy("__custom__");
    setTriggers((prev) => prev.filter((_, i) => i !== idx));
}

function handleStrategyChange(name: string) {
    if (name === "__custom__") { setSelectedStrategy("__custom__"); return; }
    const strat = strategies.find((s) => s.name === name);
    if (!strat) return;
    setSelectedStrategy(name);
    setTriggers(strat.triggers.map((t) => ({ ...t })));
}
```

**Existing slider markup pattern** (lines 162–183) — copy for per-trigger cards:
```typescript
// EXISTING slider shape (lines 162–175) — copy for min_minute per trigger card
<div>
    <label className="block text-sm text-gray-300 mb-1">
        Min minute: {minMinute}
    </label>
    <input
        type="range"
        min={1}
        max={90}
        value={minMinute}
        onChange={(e) => setMinMinute(Number(e.target.value))}
        className="w-full"
    />
</div>
```

**Existing `SummaryCard` component** (lines 15–38) — reuse as-is. Add "N of M triggers skipped" line below the card grid:
```typescript
// After the SummaryCard grid section, add (D-18):
{(() => {
    const skipped = triggers.filter(
        (t) => t.sport !== undefined && t.sport !== (selected?.sport_path ?? ""),
    );
    if (skipped.length === 0) return null;
    const sports = [...new Set(skipped.map((t) => t.sport))].join(", ");
    return (
        <p className="text-xs text-gray-500 mt-2">
            {skipped.length} of {triggers.length} trigger{triggers.length !== 1 ? "s" : ""} skipped: {sports} (no data for current season)
        </p>
    );
})()}
```

**Existing `select` markup pattern** (lines 141–159) — copy for strategy dropdown and sport dropdown:
```typescript
// EXISTING season select (lines 148–159) — copy shape for strategy dropdown
<select
    value={selectedKey}
    onChange={(e) => setSelectedKey(e.target.value)}
    className="w-full bg-black border border-gray-700 rounded px-2 py-1"
>
    {SEASONS.map((s) => (
        <option key={s.key} value={s.key}>{s.parsed.label}</option>
    ))}
</select>
```

**Sport-mismatch graying pattern** (from RESEARCH.md Pattern for mismatch indicator):
```typescript
// Per trigger card — dim when trigger.sport != season's sport_path
const mismatched =
    trigger.sport !== undefined && trigger.sport !== (selected?.sport_path ?? "");

<div
    className={`p-3 rounded border space-y-2 ${mismatched ? "opacity-40 border-gray-700" : "border-gray-600"}`}
>
    {mismatched && (
        <p className="text-xs text-yellow-600">
            Skipped — no {trigger.sport} data loaded
        </p>
    )}
    {/* sliders */}
</div>
```

**TypeScript interface for API response** — add at top of page.tsx:
```typescript
interface ApiTrigger {
    sport?: string;
    min_minute?: number;
    min_lead?: number;
    min_yes_price?: number;
    max_yes_price?: number;
}

interface ApiStrategy {
    name: string;
    description?: string;
    triggers: ApiTrigger[];
}
```

---

### `pyproject.toml` (config — dep addition)

**Analog:** `pyproject.toml` lines 6–15 — self-modification

**Existing `[project] dependencies` block** (lines 6–15):
```toml
dependencies = [
    "boto3>=1.42.63",
    "cryptography>=46.0.5",
    "fastapi>=0.135.1",
    "httpx>=0.28",
    "python-dotenv>=1.2.2",
    "sqlalchemy>=2.0.48",
    "uvicorn>=0.41.0",
    "websockets>=16.0",
]
```

Add `"pyyaml>=6.0"` in alphabetical position. Then run `uv sync` (not `uv add` which may reorder).

**Pitfall:** After editing `pyproject.toml` directly, `uv.lock` will be stale. Run `uv sync` to regenerate the lockfile. Do not commit `pyproject.toml` without also committing the updated `uv.lock`.

---

### `strategies.yaml` (config — new file at repo root)

**No codebase analog.** Shape is defined by D-05.

The file must conform to `StrategiesFile` Pydantic shape: `strategies:` mapping → strategy name → `{description?, triggers: [{...}]}`.

Content: 2–4 active strategies + 5 commented WHAT_IF translations. Reference `src/predictions/scanner.py` line 261 (`WHAT_IF_STRATEGIES`) for the source values.

---

### `tests/fixtures/strategies-*.yaml` (fixture files — new directory)

**No codebase analog.** The `tests/fixtures/` directory does not yet exist (RESEARCH.md assumption A2 — verify before creating).

Each file exercises one loader path:

| File | Content | Tests |
|------|---------|-------|
| `strategies-valid.yaml` | 1+ well-formed strategy | happy path |
| `strategies-no-triggers.yaml` | strategy with `triggers: []` | D-07 all-or-nothing |
| `strategies-unknown-field.yaml` | trigger with extra field (e.g., `min_minutes: 80`) | D-06 extra="forbid" |
| `strategies-empty.yaml` | zero bytes | `yaml.safe_load → None` path |

Alternatively, inline YAML content via `tmp_path` in tests (shown in `test_strategies.py` pattern above). Either approach works; `tmp_path` avoids the new directory.

---

### `.env.example` (config — one-line addition)

**Analog:** `.env.example` (self) — add one line with the same comment style as existing variables.

Add after the last existing variable:
```bash
# Path to strategies YAML file (default: "strategies.yaml" relative to CWD)
# STRATEGIES_PATH=strategies.yaml
```

---

## Shared Patterns

### Bearer Auth Dependency
**Source:** `src/predictions/api.py` lines 258–266
**Apply to:** `GET /api/strategies` endpoint

Every authenticated endpoint uses `dependencies=[Depends(_check_token)]` in the decorator. No per-handler auth logic. The `_check_token` function already exists — do not duplicate it.

### Pydantic v2 API
**Source:** `src/predictions/api.py` (all response models)
**Apply to:** `strategies.py` models, new response models in `api.py`

- Always `BaseModel` (not dataclass)
- Always `model_validate(dict)` not `parse_obj(dict)`
- Always `instance.model_dump()` not `instance.dict()`
- `Optional[T] = None` for nullable fields

### Module Logger
**Source:** `src/predictions/api.py` line 151
**Apply to:** `src/predictions/strategies.py`

```python
log = logging.getLogger(__name__)
```

One logger per module. Log `warning` for operator-visible issues (missing file, validation error). Log `info` for nominal events (e.g., "loaded N strategies").

### TestClient Fixture
**Source:** `tests/test_backtest_api.py` lines 5–10
**Apply to:** `tests/test_strategies_api.py`

```python
@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app
    return TestClient(app)
```

Import `predictions.api` inside the fixture body, after `monkeypatch.setenv`, to avoid module-level env capture issues.

### oxfmt 4-space indent
**Source:** `dashboard/oxfmt.json`
**Apply to:** All TypeScript changes in `backtest.ts`, `seasons.ts`, `page.tsx`

Run `cd dashboard && pnpm fmt` after TypeScript edits. The pre-commit hook does not auto-fix; failing `pnpm fmt:check` blocks the commit.

### Functional `setTriggers` updater
**Source:** React best practice; documented in RESEARCH.md Pitfall 7
**Apply to:** All trigger state mutations in `page.tsx`

Always use `setTriggers((prev) => ...)` form — never capture `triggers` directly in event handlers to avoid stale closure bugs.

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| `tests/fixtures/*.yaml` | fixture | file-I/O | No YAML fixture files exist in the codebase; project tests use in-memory DB fixtures via SQLAlchemy. Use `tmp_path` instead to avoid creating a new directory. |

---

## Metadata

**Analog search scope:** `src/predictions/`, `tests/`, `dashboard/app/backtest/`, `dashboard/app/api/`
**Files read:** `api.py`, `backtest.ts`, `seasons.ts`, `page.tsx`, `route.ts`, `conftest.py`, `test_backtest_api.py`, `test_run_backtest.py`, `pyproject.toml`, `STRUCTURE.md`, `CONVENTIONS.md`
**Pattern extraction date:** 2026-04-30

---

## PATTERN MAPPING COMPLETE
