# Phase 04: Analytics Dashboard - Pattern Map

**Mapped:** 2026-05-06
**Files analyzed:** 8 (3 new, 5 modified surfaces)
**Analogs found:** 8 / 8

---

## File Classification

| New/Modified File | Role | Data Flow | Closest Analog | Match Quality |
|---|---|---|---|---|
| `dashboard/app/analytics/page.tsx` | page (client component) | request-response + polling | `dashboard/app/backtest/page.tsx` | role-match (different data, same structure) |
| `src/predictions/api.py` — `GET /api/strategy-analytics` | endpoint | request-response, CRUD aggregation | `src/predictions/api.py:270` `get_stats` | exact |
| `src/predictions/api.py` — `GET /api/strategies-summary` | endpoint | request-response, GROUP BY aggregation | `src/predictions/api.py:461` `get_total_sport_stats` | role-match |
| `tests/test_strategy_analytics.py` | test | request-response (TestClient) | `tests/test_strategies_api.py` | exact |
| `src/predictions/api.py` `TradeResponse` + `get_trades()` | model + constructor | CRUD | `src/predictions/api.py:60-76` + `api.py:391-413` | exact (field addition) |
| `dashboard/app/page.tsx` — header nav link | UI fragment | — | `dashboard/app/page.tsx:2308-2313` | exact |
| `dashboard/app/page.tsx` — trades table cross-link | UI fragment | — | `dashboard/app/page.tsx:2654-2660` | exact (wrapping) |
| `tests/conftest.py` — seed helper | fixture | — | `tests/conftest.py:10-24` `isolated_db` | role-match |

---

## Pattern Assignments

### 1. `dashboard/app/analytics/page.tsx` (NEW — page, polling)

**Action:** CREATE

**Analog:** `dashboard/app/backtest/page.tsx`

**File structure / auth pattern** (backtest/page.tsx:1-7, 119-145, 235):
```typescript
"use client";

import { useEffect, useMemo, useState } from "react";
import { checkAuth } from "../actions";

// ... local helpers and sub-components above the default export ...

export default function BacktestPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  // ...

  useEffect(() => {
    checkAuth().then((ok) => {
      if (!ok) window.location.href = "/";
      else setAuthed(true);
    });
  }, []);

  // ...

  if (!authed) return <div className="min-h-screen bg-black" />;
  // ... rest of JSX
}
```

**Notes:**
- `checkAuth` import path from `analytics/page.tsx` is `"../actions"` — identical to backtest.
- backtest redirects to `"/"` on auth failure; analytics should match.
- `authed` is `boolean | null` (null = loading). The null guard renders a blank black screen — copy exactly; the main `Dashboard` in `page.tsx:2255-2256` does the same.
- The analytics page is `"use client"` because it uses recharts (browser DOM required) and `useEffect`. This is mandatory — do NOT attempt a server component.

**Header / page frame** (backtest/page.tsx:242-251):
```typescript
return (
  <div className="min-h-screen bg-black text-white p-6">
    <header className="flex items-center justify-between mb-6">
      <a href="/" className="text-sm text-gray-400 hover:text-white">
        ← Dashboard
      </a>
      <h1 className="text-2xl font-semibold">Strategy Backtest</h1>
      <span className="text-sm text-gray-400" />
    </header>
    <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-6">
      <aside className="space-y-4 bg-gray-900 p-4 rounded">
        {/* sidebar */}
      </aside>
      <main className="space-y-6">
        {/* detail panel */}
      </main>
    </div>
  </div>
);
```

**Local `SummaryCard` component** (backtest/page.tsx:51-74 — local, NOT exported):
```typescript
function SummaryCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const valueClass =
    tone === "positive"
      ? "text-green-400"
      : tone === "negative"
        ? "text-red-400"
        : "text-white";
  return (
    <div className="bg-gray-900 rounded p-3">
      <div className="text-xs uppercase tracking-wider text-gray-400">{label}</div>
      <div className={`text-lg font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}
```

**Notes on StatCard choice:** `page.tsx:209` `StatCard` uses amber/zinc styling with `gold-glow` and `animate-fade-in` class; backtest's `SummaryCard` uses gray styling. Analytics should pick one — the backtest `SummaryCard` is simpler and already in the "sibling page" context. Re-declare locally in `analytics/page.tsx` (same pattern backtest uses). Do not extract from `page.tsx` in this phase (avoids monolith touch beyond the two locked changes).

**Local `cents` formatter** (page.tsx:131-133):
```typescript
function cents(c: number): string {
  return `$${(c / 100).toFixed(2)}`;
}
```
Re-declare locally in `analytics/page.tsx` — not exported from `page.tsx`.

---

### 2. `GET /api/strategy-analytics` endpoint (NEW in `src/predictions/api.py`)

**Action:** CREATE (add to api.py after existing endpoints)

**Analog:** `src/predictions/api.py:270-351` (`get_stats`)

**Pydantic response model pattern** (api.py:40-57):
```python
class StatsResponse(BaseModel):
    total_trades: int
    live_trades: int
    # ... all fields typed, no Optional unless nullable
    win_rate: float
```

**Route decorator + auth pattern** (api.py:270):
```python
@app.get("/api/stats", response_model=StatsResponse, dependencies=[Depends(_check_token)])
def get_stats():
    session = get_session()
    # ... queries ...
    session.close()
    return StatsResponse(...)
```

**SQL aggregation pattern** (api.py:274-299):
```python
total_trades = session.query(Trade).filter(Trade.status != "error").count()

total_pnl = (
    session.query(func.sum(Trade.pnl_cents)).filter(Trade.pnl_cents.isnot(None)).scalar() or 0
)

wins = session.query(Trade).filter(Trade.status == "settled_win").count()
losses = session.query(Trade).filter(Trade.status == "settled_loss").count()
settled = wins + losses
win_rate = (wins / settled * 100) if settled > 0 else 0
# ...
session.close()
return StatsResponse(
    wins=wins,
    losses=losses,
    win_rate=round(win_rate, 1),
    # ...
)
```

**Notes for `get_strategy_analytics`:**
- Apply composite filter per D-04: `Trade.strategy_name == strategy, (Trade.dry_run == False) | ((Trade.dry_run == True) & (Trade.strategy_name.isnot(None)))`. With `strategy_name == strategy` already set, the `dry_run` clause is redundant but must still be included for D-16 symmetry.
- P&L curve: run Python for-loop running sum — do NOT use SQL window functions (RESEARCH.md Anti-Patterns #1; SQLite version-dependent).
- Skip `pnl_curve` points where `settled_at is None` — fall back to `placed_at` or skip entirely (RESEARCH.md Pitfall 5).
- Query returns `{stats: {...}, trades: [...], pnl_curve: [...]}` — define three Pydantic sub-models.

---

### 3. `GET /api/strategies-summary` endpoint (NEW in `src/predictions/api.py`)

**Action:** CREATE (add to api.py)

**Analog:** `src/predictions/api.py:461-541` (`get_total_sport_stats`) — GROUP BY + Python merge

**GROUP BY + Python merge pattern** (api.py:461-530):
```python
@app.get("/api/sport-stats", dependencies=[Depends(_check_token)])
def get_total_sport_stats():
    session = get_session()

    from sqlalchemy import text
    seen_matches = session.execute(
        text(
            "SELECT series_ticker, COUNT(DISTINCT event_ticker) "
            "FROM opportunities "
            "WHERE series_ticker IS NOT NULL "
            "GROUP BY series_ticker"
        )
    ).fetchall()

    # ... Python post-processing into stats dict ...
    session.close()
    stats: dict[str, dict] = {}
    # build and return
```

**Notes for `get_strategies_summary`:**
- Use ORM GROUP BY (not raw text) since `Trade.strategy_name` is a mapped column.
- After DB GROUP BY, merge with `load_strategies()` YAML name list to include zero-trade strategies (the most critical omission risk — RESEARCH.md Pitfall 1). Strategies in YAML but absent from DB rows get all-zero stats.
- SQLAlchemy 2.x CASE syntax (verify against actual version — RESEARCH.md A2):
  ```python
  from sqlalchemy import case
  wins_expr = func.sum(case((Trade.status == "settled_win", 1), else_=0))
  ```
- `response_model_exclude_none=True` is NOT needed here (no None fields in the summary shape). Match the behavior of `/api/stats` (no exclude_none) rather than `/api/strategies` (which does use it).

---

### 4. `tests/test_strategy_analytics.py` (NEW)

**Action:** CREATE

**Analog:** `tests/test_strategies_api.py`

**Full file pattern** (test_strategies_api.py:1-81):
```python
"""Tests for GET /api/strategies (src/predictions/api.py)."""

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("API_TOKEN", "test-token")
    from predictions.api import app

    return TestClient(app)


def test_endpoint_requires_auth(client):
    """T-02-01: missing Bearer token returns 401, never leaks data."""
    resp = client.get("/api/strategies")
    assert resp.status_code == 401


def test_endpoint_response_shape(client, tmp_path, monkeypatch):
    """STR-03 / D-10: response is {strategies: [...]}."""
    # ...
    resp = client.get(
        "/api/strategies",
        headers={"Authorization": "Bearer test-token"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "strategies" in data
```

**Notes:**
- The `client` fixture uses `monkeypatch.setenv("API_TOKEN", "test-token")` then imports `from predictions.api import app`. Copy this exact pattern — the import must happen AFTER monkeypatch to pick up the env var.
- `isolated_db` (autouse=True in conftest.py) fires automatically — no explicit fixture reference needed in most tests, but seed helper functions will use the `engine` yielded by `isolated_db`.
- Auth header: `headers={"Authorization": "Bearer test-token"}` — exact string.
- The test file should cover the 7 cases listed in RESEARCH.md Validation Architecture: correct stats, pnl_curve running sum, zero-trade strategy, summary includes zero-trade YAML strategies, summary aggregation, 401 on missing token, composite filter excludes legacy trades.

---

### 5. `TradeResponse` `strategy_name` field addition + `get_trades()` constructor

**Action:** MODIFY `src/predictions/api.py`

**Current shape** (api.py:60-76):
```python
class TradeResponse(BaseModel):
    id: int
    placed_at: Optional[datetime] = None
    ticker: str
    event_ticker: Optional[str] = None
    title: Optional[str] = None
    side: str
    count: int
    yes_price: int
    cost_cents: int
    potential_profit_cents: int
    status: str
    pnl_cents: Optional[int] = None
    dry_run: bool
    error: Optional[str] = None
    espn_clock_seconds: Optional[int] = None
```

**Field to add** (append after `espn_clock_seconds`):
```python
    strategy_name: Optional[str] = None
```

**Constructor call to update** (api.py:391-408):
```python
result.append(
    TradeResponse(
        id=t.id,
        placed_at=t.placed_at,
        ticker=t.ticker,
        event_ticker=t.event_ticker,
        title=t.title,
        side=t.side,
        count=t.count,
        yes_price=t.yes_price,
        cost_cents=t.cost_cents,
        potential_profit_cents=t.potential_profit_cents,
        status=t.status,
        pnl_cents=t.pnl_cents,
        dry_run=t.dry_run,
        error=t.error,
        espn_clock_seconds=t.espn_clock_seconds,
        # ADD: strategy_name=t.strategy_name,
    )
)
```

**Notes:**
- `response_model_exclude_none=True` is NOT set on `/api/trades` (it is on `/api/strategies`). So `null` values serialize as `null` in JSON — no breaking change to existing consumers.
- This field addition also requires updating the `Trade` TypeScript interface in `dashboard/app/page.tsx` (item 7 below).

---

### 6. `dashboard/app/page.tsx` — header "Analytics" link (MODIFY)

**Action:** MODIFY `dashboard/app/page.tsx`

**Analog:** `dashboard/app/page.tsx:2308-2313` (existing backtest link)

**Current backtest link** (page.tsx:2308-2313):
```tsx
<a
  href="/backtest"
  className="inline-block mt-2 px-4 py-2 rounded-lg text-sm font-bold transition-all bg-zinc-900 text-zinc-400 hover:text-amber-500 hover:bg-zinc-800"
>
  Strategy Backtest →
</a>
```

**Planner adds analytics link after the backtest `<a>` tag** (same parent `<div>`, same className pattern):
```tsx
<a
  href="/analytics"
  className="inline-block mt-2 ml-2 px-4 py-2 rounded-lg text-sm font-bold transition-all bg-zinc-900 text-zinc-400 hover:text-amber-500 hover:bg-zinc-800"
>
  Analytics →
</a>
```

**Notes:**
- Single-line sibling addition; no nav-component refactor (D-03).
- Use `<a>` not Next.js `<Link>` — backtest uses `<a href>` throughout `page.tsx`, consistent with the existing pattern (no next/link import in page.tsx).

---

### 7. `dashboard/app/page.tsx` — trades table cross-link + `Trade` interface (MODIFY)

**Action:** MODIFY `dashboard/app/page.tsx`

**Trades table cell to wrap** (page.tsx:2654-2660):
```tsx
<td className="p-3">
  <div className="text-amber-100 truncate max-w-xs">
    {t.title}
  </div>
  <div className="text-amber-800 text-xs">
    {t.ticker}
  </div>
</td>
```

**After modification** — add strategy_name cross-link row below ticker:
```tsx
<td className="p-3">
  <div className="text-amber-100 truncate max-w-xs">
    {t.title}
  </div>
  <div className="text-amber-800 text-xs">
    {t.ticker}
  </div>
  {t.strategy_name && (
    <a
      href={`/analytics?strategy=${encodeURIComponent(t.strategy_name)}`}
      className="text-xs text-amber-600 hover:text-amber-400"
    >
      {t.strategy_name}
    </a>
  )}
</td>
```

**`Trade` interface addition** (page.tsx:30-46, after `espn_clock_seconds`):
```typescript
interface Trade {
  id: number;
  placed_at: string;
  ticker: string;
  event_ticker: string;
  title: string;
  side: string;
  count: number;
  yes_price: number;
  cost_cents: number;
  potential_profit_cents: number;
  status: string;
  pnl_cents: number | null;
  dry_run: boolean;
  error: string | null;
  espn_clock_seconds: number | null;
  strategy_name?: string | null;  // ADD THIS FIELD
}
```

**Notes:**
- Use `<a href>` not `<Link>` — page.tsx does not import `next/link`.
- `encodeURIComponent` on the strategy name to handle names with spaces or special characters in the URL.
- Conditional render (`t.strategy_name &&`) means legacy trades without strategy_name render no cross-link — safe for existing rows.

---

### 8. 5-minute `setInterval` auto-refresh pattern

**Action:** COPY into `dashboard/app/analytics/page.tsx`

**Analog:** `dashboard/app/page.tsx:2219-2240` (fetchSlow interval)

**Full `useEffect` block to mirror** (page.tsx:2219-2240):
```typescript
useEffect(() => {
  if (!authed) return;

  const fetchSlow = async () => {
    try {
      const [tradesRes, configRes, ssRes] = await Promise.all([
        fetch(`${API}/api/histogram-trades?limit=10000`),
        fetch(`${API}/api/config`),
        fetch(`${API}/api/sport-stats`),
      ]);
      if (tradesRes.ok) setAllTrades((await tradesRes.json()).trades ?? []);
      if (configRes.ok) setConfig(await configRes.json());
      if (ssRes.ok) setSportStats((await ssRes.json()).stats);
    } catch {
      // non-critical
    }
  };

  fetchSlow();
  const interval = setInterval(fetchSlow, 60000);
  return () => clearInterval(interval);
}, [authed]);
```

**Analytics page version** — mirror with 5-minute cadence and `selected` in dependency array (D-12):
```typescript
useEffect(() => {
  if (!authed) return;

  const fetchAll = async () => {
    try {
      const [summaryRes, detailRes] = await Promise.all([
        fetch(`/api/strategies-summary`),
        selected ? fetch(`/api/strategy-analytics?strategy=${encodeURIComponent(selected)}`) : null,
      ]);
      if (summaryRes.ok) setSummary((await summaryRes.json()).strategies ?? []);
      if (detailRes?.ok) setDetail(await detailRes.json());
    } catch {
      // non-critical
    }
  };

  fetchAll();
  const interval = setInterval(fetchAll, 5 * 60 * 1000);
  return () => clearInterval(interval);
}, [authed, selected]);
```

**Notes:**
- The `API` constant in `page.tsx` is `""` (empty string) — client-side fetches go to the same origin and the Next.js proxy intercepts them. Use the same convention in `analytics/page.tsx`.
- `catch {}` empty catch is the project pattern for non-critical background polling — do not add toast/error-state on polling failure.
- `selected` in the dependency array means the interval re-registers when strategy selection changes — the old interval is cleared and a new one starts immediately with the new strategy.

---

### 9. recharts `LineChart` pattern (first use in repo)

**Action:** INTRODUCE in `dashboard/app/analytics/page.tsx`

**Analog:** None in codebase — first recharts usage. Use RESEARCH.md Pattern 3 as the source.

**Import block** (from RESEARCH.md:282-292):
```typescript
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  CartesianGrid,
  ResponsiveContainer,
} from "recharts";
```

**Component pattern** (from RESEARCH.md:297-331):
```typescript
<ResponsiveContainer width="100%" height={260}>
  <LineChart data={pnlCurve} margin={{ top: 5, right: 20, left: 10, bottom: 5 }}>
    <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
    <XAxis
      dataKey="x"
      tickFormatter={(v) => new Date(v).toLocaleDateString()}
      tick={{ fill: "#a1a1aa", fontSize: 11 }}
    />
    <YAxis
      tickFormatter={(v) => `$${(v / 100).toFixed(2)}`}
      tick={{ fill: "#a1a1aa", fontSize: 11 }}
    />
    <Tooltip
      content={({ active, payload }) => {
        if (!active || !payload?.length) return null;
        const d = payload[0].payload;
        return (
          <div className="bg-zinc-900 border border-zinc-700 p-2 text-xs">
            <div>{new Date(d.x).toLocaleString()}</div>
            <div>{d.ticker}</div>
            <div>Trade: {d.trade_pnl >= 0 ? "+" : ""}{(d.trade_pnl / 100).toFixed(2)}</div>
            <div>Running: {d.y >= 0 ? "+" : ""}{(d.y / 100).toFixed(2)}</div>
          </div>
        );
      }}
    />
    <Line type="monotone" dataKey="y" stroke="#d97706" dot={false} strokeWidth={2} />
  </LineChart>
</ResponsiveContainer>
```

**Critical pitfalls:**
1. **Height collapse (RESEARCH.md Pitfall 6):** Always use `height={260}` (fixed pixels) on `ResponsiveContainer`. Do NOT use `height="100%"` — the parent flex container has no explicit height, so the chart collapses to 0px.
2. **Empty data:** Pass `data={[]}` when `pnlCurve.length === 0` — recharts renders axes with no lines, no crash. Never pass `data={undefined}`.
3. **Server component crash (RESEARCH.md Pitfall 3):** The analytics page must be `"use client"` — recharts uses browser DOM APIs.
4. **`data={undefined}`:** Never. Always `data={pnlCurve ?? []}`.

---

### 10. `tests/conftest.py` — multi-strategy seed helper (MODIFY)

**Action:** MODIFY `tests/conftest.py`

**Analog:** `tests/conftest.py:10-24` (`isolated_db` fixture)

**Current `isolated_db`** (conftest.py:10-24):
```python
@pytest.fixture(autouse=True)
def isolated_db(monkeypatch):
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    SessionLocal = sessionmaker(bind=engine)
    monkeypatch.setattr(db_module, "engine", engine)
    monkeypatch.setattr(db_module, "SessionLocal", SessionLocal)
    db_module.Base.metadata.create_all(engine)
    yield engine
    engine.dispose()
```

**Extension needed:** Add a non-autouse helper fixture for seeding multi-strategy `Trade` rows. The analytics tests need rows with `strategy_name`, `status` in `("settled_win", "settled_loss", "dry_run")`, and `pnl_cents` set. Pattern: add a `seed_trades(engine, rows)` helper function that the `test_strategy_analytics.py` test fixtures call explicitly.

**Seed helper shape** (new function in conftest.py, after existing fixtures):
```python
def seed_trades(engine, rows: list[dict]):
    """Insert Trade rows into the isolated in-memory DB for analytics tests."""
    from sqlalchemy.orm import sessionmaker
    from predictions.db import Trade
    Session = sessionmaker(bind=engine)
    session = Session()
    for row in rows:
        session.add(Trade(**row))
    session.commit()
    session.close()
```

**Notes:**
- `seed_trades` is a plain function (not a fixture) — called directly in test bodies or test-specific fixtures that receive `isolated_db` (the engine) as a parameter.
- The `isolated_db` fixture already yields `engine` — tests that need seeded data use `def test_foo(isolated_db): seed_trades(isolated_db, [...])`.
- `Trade` fields required for analytics tests: `ticker`, `strategy_name`, `status`, `pnl_cents`, `placed_at`, `settled_at`, `dry_run`, `yes_price`, `count`, `side`, `cost_cents`, `potential_profit_cents`.

---

## Shared Patterns

### Authentication — Backend

**Source:** `src/predictions/api.py:254-262`
**Apply to:** Both new endpoints (`/api/strategy-analytics`, `/api/strategies-summary`)

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

Usage: `@app.get("/api/...", dependencies=[Depends(_check_token)])`

### Authentication — Frontend

**Source:** `dashboard/app/backtest/page.tsx:140-145`
**Apply to:** `dashboard/app/analytics/page.tsx`

```typescript
useEffect(() => {
  checkAuth().then((ok) => {
    if (!ok) window.location.href = "/";
    else setAuthed(true);
  });
}, []);
```

Null guard (render blank screen during auth check):
```typescript
if (!authed) return <div className="min-h-screen bg-black" />;
```

### Fetch + Error Swallow Pattern

**Source:** `dashboard/app/page.tsx:2222-2234`
**Apply to:** All `fetch` calls in `analytics/page.tsx` polling loop

```typescript
try {
  const res = await fetch(`/api/some-endpoint`);
  if (res.ok) setState(await res.json());
} catch {
  // non-critical
}
```

Empty catch is project convention for background polling — no toast, no error state.

### Session Open/Close

**Source:** `src/predictions/api.py:272, 331`
**Apply to:** Both new endpoints

```python
session = get_session()
# ... queries ...
session.close()
return Response(...)
```

Always close the session before returning, even on the happy path (no `with` statement — project uses explicit close).

---

## No Analog Found

| File | Role | Data Flow | Reason |
|------|------|-----------|--------|
| recharts `LineChart` component | UI chart | render | recharts unused in repo; RESEARCH.md Pattern 3 is the reference |
| `useSearchParams` / URL param management | client state | — | No URL-param state in existing pages; RESEARCH.md Pattern 7 is the reference. Note Pitfall 4: wrap in `<Suspense>` or use `window.location.search` in `useEffect` to avoid Next.js 16 build error |

---

## Metadata

**Analog search scope:** `dashboard/app/`, `src/predictions/`, `tests/`
**Files scanned:** 9
**Pattern extraction date:** 2026-05-06
