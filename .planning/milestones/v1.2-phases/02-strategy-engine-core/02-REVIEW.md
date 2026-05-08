---
phase: 02-strategy-engine-core
reviewed: 2026-04-30T00:00:00Z
depth: standard
files_reviewed: 13
files_reviewed_list:
  - src/predictions/strategies.py
  - src/predictions/api.py
  - tests/test_strategies.py
  - tests/test_strategies_api.py
  - tests/fixtures/strategies-good.yaml
  - tests/fixtures/strategies-malformed.yaml
  - tests/fixtures/strategies-unknown-field.yaml
  - tests/fixtures/strategies-empty.yaml
  - strategies.yaml
  - .env.example
  - pyproject.toml
  - dashboard/app/backtest/backtest.ts
  - dashboard/app/backtest/seasons.ts
  - dashboard/app/backtest/page.tsx
findings:
  critical: 0
  warning: 4
  info: 5
  total: 9
status: issues_found
---

# Phase 02: Code Review Report

**Reviewed:** 2026-04-30
**Depth:** standard
**Files Reviewed:** 13
**Status:** issues_found

## Summary

Phase 02 ships a Pydantic-v2 strategy loader, a Bearer-protected
`/api/strategies` endpoint, a multi-trigger OR-of-AND backtest engine,
and a Sport→League→Strategy sidebar. The security-sensitive bits look
correct: `yaml.safe_load` is used (and a test specifically guards
`!!python/object`); `extra="forbid"` is set on every model;
`triggers` carries `min_length=1`; the new endpoint reuses the existing
`_check_token` Bearer dependency; the dashboard fetch flows through the
already-authenticated Next.js proxy. No criticals found.

The sport-family rename is fully consistent inside Phase 02 scope —
`strategies.yaml`, fixtures, `backtest.ts`, `seasons.ts`, and `page.tsx`
all use `"football"`. The `soccer/eng.1`-style strings still present in
`scanner.py`/`espn.py`/`db.py`/`api.py` are pre-existing live-scanner /
config-key surfaces and are out of scope per the D-02 override (live
scanner mapping deferred to Phase 3).

The findings below are correctness/quality issues, ranked by risk:

1. The dashboard strategies fetch crashes the page if the proxy returns
   a non-strategies JSON body (e.g., `{error: "Unauthorized"}`).
2. Two-step Pydantic validation is fragile / wasteful and will silently
   accept malformed strategies if `Strategy` ever gains a stricter
   second-pass-only constraint.
3. Tabular minor issues around magic numbers, throwing in render-path
   helpers, and validation gaps.

## Warnings

### WR-01: Dashboard crashes when `/api/strategies` returns a non-strategies JSON body

**File:** `dashboard/app/backtest/page.tsx:147-156`
**Issue:** The fetch promise chain calls `r.json()` unconditionally, then
`setStrategies(data.strategies)`. The Next.js proxy at
`dashboard/app/api/[...path]/route.ts:8` returns
`NextResponse.json({ error: "Unauthorized" }, { status: 401 })` when the
auth cookie is missing/expired, and the FastAPI backend can return
`{detail: "..."}` JSON for 401/403/500. In all those branches `r.json()`
resolves successfully (it's valid JSON), `data.strategies` is
`undefined`, and `setStrategies(undefined as any)` poisons state. Any
subsequent `strategies.filter(...)` (line 173) or `strategies.find(...)`
(lines 212, 239) throws `TypeError: Cannot read properties of undefined`
during render — the `.catch` block (line 153) does NOT cover this path
because the promise resolves successfully. With cookie-based auth on
Next.js proxy, this triggers any time the user's session has just
expired between dashboard load and backtest navigation.
**Fix:**
```ts
useEffect(() => {
  fetch("/api/strategies", { cache: "no-store" })
    .then(async (r) => {
      if (!r.ok) return;
      const data = await r.json();
      if (Array.isArray(data?.strategies)) setStrategies(data.strategies);
    })
    .catch(() => {});
}, []);
```

### WR-02: Two-step Pydantic validation is brittle and bypasses `extra="forbid"` on the second pass

**File:** `src/predictions/strategies.py:96-100`
**Issue:** The loader parses the file via `StrategiesFile.model_validate(raw)`,
then for each strategy calls `strat.model_dump()`, injects `name`, and
calls `Strategy.model_validate(data)` a second time. Two issues:
1. `model_dump()` of an already-parsed `Strategy` includes ALL fields
   (e.g., `name=""`, `description=None`, `triggers=[...]`) so the
   second `model_validate` is purely redundant work — it doesn't add
   any check the first pass didn't already do. The single statement
   `strat.name = name; result.append(strat)` would be equivalent and
   ~2× faster on the hot path (loader is called per request).
2. The pattern silently breaks if anyone later adds a field-level
   validator to `Strategy` that depends on `name` being non-empty. The
   first-pass validation receives `name=""` for every strategy (it's
   never present in the YAML body), so a `@field_validator("name")`
   with `min_length=1` would reject the entire file before the loader
   ever gets a chance to inject the real key. Future-Phase-3 land mine.

The cleanest fix is to drop `name` from `Strategy` entirely and have
the loader build the list manually, which also makes `name` impossible
to spoof from inside the YAML body:

**Fix:**
```python
class Strategy(BaseModel):
    model_config = ConfigDict(extra="forbid")
    description: Optional[str] = None
    triggers: Annotated[list[Trigger], Field(min_length=1)]


@dataclass(frozen=True)
class LoadedStrategy:
    name: str
    description: Optional[str]
    triggers: list[Trigger]


def load_strategies(...) -> list[LoadedStrategy]:
    ...
    return [
        LoadedStrategy(name=name, description=s.description, triggers=s.triggers)
        for name, s in parsed.strategies.items()
    ]
```
If keeping `Strategy` as the public DTO is required, at minimum
collapse the redundant validation:
```python
result: list[Strategy] = []
for name, strat in parsed.strategies.items():
    strat.name = name  # mutating; Strategy is not frozen
    result.append(strat)
```

### WR-03: `parseScore` / `parseGoalTime` throw inside the render-driven `useMemo`

**File:** `dashboard/app/backtest/backtest.ts:67-89` (callers at 110, 113, 156, 159)
**Issue:** Both helpers `throw new Error(...)` on malformed input. They
are invoked from `runBacktest` which is invoked from a `useMemo` in
`page.tsx:218-233`. A single corrupt fixture row (e.g., a goal with
`time: "12"` missing the pipe, or `score: "1-0"` with a dash) escapes
the entire render with an uncaught exception, crashing the backtest
page rather than skipping the bad fixture. JSON files are bundled at
build time so today's data is fine, but this is a fragile boundary —
any future hand-edited or scraped season file silently turns into a
production page-load crash with no fallback.
**Fix:** Either (a) validate the JSON shape once on import in
`seasons.ts` with descriptive errors at build time, or (b) make the
helpers return `null` and have `detectFire`/`detectFireMulti` skip
unparseable goals with a `console.warn` in dev:
```ts
function parseGoalTime(time: string): { minute: number; stoppage: number } | null {
  const parts = time.split("|");
  if (parts.length !== 2) return null;
  const minute = parseInt(parts[0], 10);
  const stoppage = parseInt(parts[1], 10);
  if (Number.isNaN(minute) || minute < 0 || Number.isNaN(stoppage) || stoppage < 0) return null;
  return { minute, stoppage };
}
```

### WR-04: `Strategy.name` accepts empty / whitespace-only YAML keys

**File:** `src/predictions/strategies.py:37`, `src/predictions/api.py:158-161`
**Issue:** `Strategy.name` is typed `str = ""` with no length constraint.
A YAML file like:
```yaml
strategies:
  "":
    triggers:
      - min_lead: 2
  "   ":
    triggers:
      - min_lead: 2
```
loads cleanly. The dashboard `<option key={s.name} value={s.name}>` at
`page.tsx:298-302` renders duplicate empty strings, React logs a key
warning, `handleStrategyChange("")` matches `CUSTOM_KEY` semantics
neither way, and the user sees two blank, un-pickable rows.
**Fix:** Reject empty / whitespace keys explicitly in the loader:
```python
for name, strat in parsed.strategies.items():
    if not name or not name.strip():
        log.warning("strategies file %s contains empty/whitespace key — rejecting file", path)
        return []
    ...
```
Or if `name` stays in the model, add `Annotated[str, Field(min_length=1)]`
and inject before the redundant `model_validate` (per WR-02 fix).

## Info

### IN-01: Magic-number defaults duplicated between page and helper

**File:** `dashboard/app/backtest/page.tsx:32-34, 122-129, 132-134`
**Issue:** The default trigger `{ min_minute: 75, min_lead: 2 }` and the
fallback sport `"football"` are repeated three times (`SPORTS[0]?.value
?? "football"` appears at lines 122, 126, 134). One `DEFAULT_SPORT`
constant up-top would remove the drift risk if `SPORTS` is ever
re-ordered or the fallback changes.
**Fix:** Extract `const DEFAULT_SPORT = SPORTS[0]?.value ?? "football";`
at module scope and reuse.

### IN-02: `removeTrigger` uses native `window.confirm`

**File:** `dashboard/app/backtest/page.tsx:201-205`
**Issue:** `window.confirm` is a synchronous, blocking, OS-styled
dialog. The rest of the dashboard appears not to use confirms (config
mutations are direct), so this introduces a UX inconsistency and is
also untestable (Playwright/RTL needs special handling). Given
`triggers.length > 1` already gates the button (line 418), and Add
Trigger is one click away to undo, the confirm probably isn't
warranted at all.
**Fix:** Drop the confirm or replace with a custom inline "Delete?"
toggle.

### IN-03: `_check_token` returns 403 for missing config but 401 for missing/invalid token

**File:** `src/predictions/api.py:277-285`
**Issue:** Pre-existing in `api.py` (not introduced by Phase 02 but
inherited by `/api/strategies`). When `API_TOKEN` env var is unset, the
endpoint returns `403 "API_TOKEN not configured"`, exposing
operational state to unauthenticated callers. `404` or `500` (server
misconfiguration) would be a better fingerprint-resistance posture, or
fail at startup. Not a blocker because production must set the var,
but worth documenting.
**Fix:** Either fail at startup if `API_TOKEN` is unset and
`DRY_RUN=false`, or collapse to a generic 401 to avoid leaking config
state.

### IN-04: `detectFire` (single-trigger) is exported but no longer used by `runBacktest`

**File:** `dashboard/app/backtest/backtest.ts:105-140`
**Issue:** `runBacktest` calls only `detectFireMulti`. `detectFire` is
exported (`export function detectFire`) but I cannot find a caller in
this phase's diff — Grep should confirm but it looks like dead public
API after the multi-trigger refactor. If it's still used by tests,
fine; if not, drop it before the surface congeals.
**Fix:** If unused, delete; if kept for tests only, mark with a
`/** @internal */` comment or move into `__tests__/`.

### IN-05: `match.goals` order assumed but not enforced

**File:** `dashboard/app/backtest/backtest.ts:112-113, 158-159`
**Issue:** Both `detectFire` and `detectFireMulti` walk `match.goals`
in array order and assume that translates to chronological order. The
season JSONs do appear to be sorted (the sample EPL match has minute
87 single-goal), but the comment at line 158 says "walks goals
chronologically" — that is a property of the input, not the code. If
a future scraper writes goals out-of-order (e.g., reverse-chronological
from a livestream replay), `runBacktest` silently fires on the wrong
goal and reports stale `score_at_fire`.
**Fix:** Either explicitly sort once at the top of `detectFireMulti`:
```ts
const sorted = [...match.goals].sort((a, b) => {
  const ta = parseGoalTime(a.time), tb = parseGoalTime(b.time);
  return ta.minute - tb.minute || ta.stoppage - tb.stoppage;
});
```
or document the precondition in `seasons.ts`'s `Goal` type and validate
on import.

---

_Reviewed: 2026-04-30_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
