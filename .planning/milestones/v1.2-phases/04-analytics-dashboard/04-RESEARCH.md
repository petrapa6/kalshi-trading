# Phase 4: Analytics Dashboard - Research

**Researched:** 2026-05-06
**Domain:** Next.js 16 / FastAPI / recharts / SQLite analytics
**Confidence:** HIGH

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- **D-01:** New standalone route `dashboard/app/analytics/page.tsx` — the 98KB `page.tsx` monolith does NOT grow further. Auth via `checkAuth()` from `actions.ts`. URL param `?strategy=<name>` is refresh-stable.
- **D-02:** Strategy names in main dashboard become `<Link href="/analytics?strategy=<name>">` cross-links. Planner enumerates call sites.
- **D-03:** Header link "Analytics" added to `page.tsx` near the existing `/backtest` link. No new nav-component.
- **D-04:** Single endpoint `GET /api/strategy-analytics?strategy=<name>` returning `{stats, trades, pnl_curve}`. Composite filter `Trade.strategy_name == :name AND (Trade.dry_run == False OR (Trade.dry_run == True AND Trade.strategy_name.isnot(None)))` for symmetry with Phase 03 D-16.
- **D-05:** SQL aggregation in endpoint handler (SUM/COUNT/CASE). Running P&L sum in Python (not SQL window function — SQLite version-dependent).
- **D-06:** Separate `GET /api/strategies-summary` endpoint (option a). Returns `[{name, total_trades, wins, losses, pnl_cents}]`. Keeps `/api/strategies` semantic-pure.
- **D-07:** No in-memory cache. `connect_args timeout=5` is the sole SQLITE_BUSY buffer.
- **D-08:** recharts 3.8.1 (already in `dashboard/package.json`) for cumulative P&L line chart. Existing hand-rolled `PnlChart` at `page.tsx:255–687` is NOT migrated.
- **D-09:** P&L curve x-axis = per-trade step (x=`settled_at`, y=running `pnl_cents`). Running sum in Python. Y-axis in dollars (`pnl_cents / 100`). Tooltip: date, ticker, single-trade P&L, running total.
- **D-10:** Sidebar list with per-strategy mini-stats (`+$12.30 · 3W/2L · 60%`). Click drills into detail. URL updates to `?strategy=<name>`.
- **D-11:** Zero-trade strategies: appear in selector with `0 · 0W/0L · —`. Stat cards show 0. Empty chart (no points, just axes). Empty table body. NO explanatory copy.
- **D-12:** 5-minute `setInterval` auto-refresh. Mirror `page.tsx:2238` pattern. Both endpoints refresh each tick. Clear interval on unmount. No SWR/React Query.

### Claude's Discretion

- Open-trade stat handling: fifth stat card ("Open trades") allowed if planner judges it clearer.
- Trade log column details: `placed_at` vs `settled_at`, ticker format, column widths — planner judgment. Default sort: newest first.
- Trade log filter/sort controls: default chronological-newest-first, no filter UI required. Status-filter dropdown allowed if cheap.
- Refresh feedback UX: lean toward subtle last-updated timestamp.
- Mobile/responsive layout: sidebar collapse behavior on narrow viewports.
- Loading/skeleton state: lean toward held-stale-data pattern.

### Deferred Ideas (OUT OF SCOPE)

- Migrate hand-rolled `PnlChart` to recharts.
- Per-trigger analytics (`trigger_index` column).
- Time-window filtering (7d/30d/all-time).
- Strategy comparison/diff view.
- CLI commands for analytics.
- Strategy editor / save-back to `strategies.yaml`.
- Hot-reload of `strategies.yaml`.
- Per-strategy `bet_percent` override.
- Real-time WS push of new trades.
- SWR / React Query.
- WAL mode / read replica for SQLite.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DASH-03 | New dashboard page: strategy selector, summary stat cards (total trades, wins, losses, win rate, realized P&L), cumulative P&L line chart, trade log table (date, ticker, price, contracts, P&L, status); behind `checkAuth` gate | D-04 endpoint shape + recharts LineChart API + StatCard reuse + isolated_db test fixtures |
| DASH-04 | Analytics page auto-refreshes every 5 minutes to show new dry-run activity without a manual reload | setInterval pattern at `page.tsx:2238` — mirror with 300_000ms interval; cleanup on unmount |
</phase_requirements>

---

## Summary

Phase 4 is a pure feature addition: two new FastAPI endpoints and one new Next.js route. No schema migrations, no new npm/Python dependencies, no shared-interface changes beyond adding `strategy_name` to `TradeResponse` (required so the cross-link in D-02 can work — see Critical Gap below).

The backend work is straightforward SQL aggregation mirroring the existing `/api/stats` pattern. The frontend work is the heavier side: a sidebar-plus-detail layout, recharts integration (first use in the codebase), and the `?strategy=` URL-param state management. The page must handle zero-trade strategies cleanly throughout all three UI zones (sidebar, stat cards, chart).

The most important pre-flight finding: `strategy_name` is stored in the `Trade` DB model and the `trades` table, but is NOT in `TradeResponse` (the Pydantic model) and NOT in the dashboard's `Trade` TypeScript interface. The D-02 cross-link task requires `strategy_name` to be visible in the `/api/trades` response so the trades table can render `<Link>` elements. This is a one-field addition to `TradeResponse` that must land as part of this phase.

**Primary recommendation:** Implement in wave order — Wave 0 (test stubs + env check), Wave 1 (backend endpoints), Wave 2 (analytics page), Wave 3 (cross-links + nav header). This order means the planner can verify the API contract before building the frontend against it.

---

## Architectural Responsibility Map

| Capability | Primary Tier | Secondary Tier | Rationale |
|------------|-------------|----------------|-----------|
| Strategy analytics aggregation (totals, wins, P&L sum) | API / Backend | — | SQL runs server-side; frontend receives pre-aggregated numbers |
| P&L curve running sum | API / Backend | — | D-05: Python running sum in endpoint handler, not client-side |
| Sidebar mini-stats list | Frontend (client component) | API | Reads from `/api/strategies-summary` |
| Detail stat cards | Frontend (client component) | API | Reads from `/api/strategy-analytics` |
| Cumulative P&L chart | Frontend (client component) | — | recharts renders `pnl_curve` array from API |
| Trade log table | Frontend (client component) | — | Renders `trades` array from API |
| `?strategy=` URL state | Browser / Client | — | `useSearchParams` / `window.location.search` in client component |
| Auth gate (`checkAuth`) | Frontend Server (SSR) | — | Server action called at the top of the page component |
| Bearer token injection | Frontend Server (proxy) | — | `dashboard/app/api/[...path]/route.ts` — zero changes needed |

---

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| FastAPI | 0.135.1 | New endpoints (`/api/strategy-analytics`, `/api/strategies-summary`) | Already in use; `@app.get` + Pydantic models pattern [VERIFIED: src/predictions/api.py] |
| SQLAlchemy 2.x | 2.0.48 | `session.query(Trade).filter(...)` aggregation | Already in use; no new ORM patterns needed [VERIFIED: src/predictions/db.py] |
| Pydantic v2 | bundled with FastAPI | `StrategyAnalyticsResponse`, `StrategiesSummaryResponse` models | All API boundaries use Pydantic [VERIFIED: api.py Pydantic models] |
| recharts | 3.8.1 | `LineChart`, `ResponsiveContainer`, `XAxis`, `YAxis`, `Tooltip`, `Line` | Already pinned in `dashboard/package.json`; `^3.8.1` [VERIFIED: dashboard/package.json] |
| React 19 | 19.2.3 | `useEffect`, `useState`, `useCallback` for polling and state | Dashboard standard [VERIFIED: dashboard/package.json] |
| Next.js 16 | 16.1.6 | New `/analytics` route; `useSearchParams` for URL param | Dashboard standard [VERIFIED: dashboard/package.json] |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| zod | 4.0.0-beta | Optional: TypeScript schema validation for API responses | Already in deps; use if typing the analytics API response precisely |
| `@types/react` | ^19 | TypeScript types for React hooks | Auto-included; no action needed |

**No new packages required.** recharts is already pinned; no `pnpm add` needed. [VERIFIED: dashboard/package.json]

---

## Architecture Patterns

### System Architecture Diagram

```
Browser
  │
  ├─ GET /analytics?strategy=<name>
  │      │
  │      ▼
  │  [Server Component: checkAuth()]
  │  Redirects to login if cookie absent
  │      │ auth OK
  │      ▼
  │  [Client Component: AnalyticsPage]
  │      │
  │      ├─ on mount / strategy change
  │      │    ├─ fetch /api/strategies-summary  ──────────────────────────────┐
  │      │    └─ fetch /api/strategy-analytics?strategy=<name>  ──────────┐   │
  │      │                                                                 │   │
  │      │   setInterval(fetchAll, 5 * 60 * 1000)                         │   │
  │      │   → clearInterval on unmount                                   │   │
  │      │                                                                 │   │
  │      ├─ Sidebar (strategies-summary)  ◄────────────────────────────────┘   │
  │      │    └─ each row: name + mini-stats + clickable                       │
  │      │         │ click → setSelected(name) + URL pushState               │
  │      │         ▼                                                           │
  │      └─ Detail Panel  ◄──────────────────────────────────────────────────┘
  │           ├─ StatCards (total, wins, losses, win_rate, pnl_cents)
  │           ├─ recharts LineChart (pnl_curve: [{x: settled_at, y: running_pnl_cents}])
  │           └─ Trade log table (trades[])
  │
  ▼ (proxy adds Bearer token)
dashboard/app/api/[...path]/route.ts
  │
  ▼
FastAPI  src/predictions/api.py
  ├─ GET /api/strategies-summary
  │    └─ SELECT strategy_name, COUNT(*), SUM(wins), SUM(losses), SUM(pnl_cents)
  │         FROM trades WHERE strategy_name IS NOT NULL GROUP BY strategy_name
  │         + LEFT JOIN /api/strategies names (to include zero-trade strategies)
  │
  └─ GET /api/strategy-analytics?strategy=<name>
       ├─ SQL: totals, wins, losses via CASE
       ├─ SQL: trades list ORDER BY settled_at ASC (settled only for curve)
       ├─ Python: running sum → pnl_curve array
       └─ Response: {stats: {...}, trades: [...], pnl_curve: [...]}
            │
            ▼
        SQLite (predictions.db)
        Trade table — strategy_name indexed (Phase 03 D-01)
```

### Recommended Project Structure

```
dashboard/app/
├── analytics/
│   └── page.tsx          # New standalone route (mirrors backtest/page.tsx)
├── page.tsx              # Minimal changes: +1 nav link, +strategy_name on Trade interface
├── actions.ts            # Unchanged — checkAuth() reused as-is
└── api/[...path]/route.ts  # Unchanged — proxy auto-routes new endpoints

src/predictions/
└── api.py                # +2 new endpoints + strategy_name field on TradeResponse

tests/
└── test_strategy_analytics.py   # New — FastAPI TestClient tests
```

### Pattern 1: Analytics Endpoint — SQL Aggregation Shape

Mirror of the existing `/api/stats` at `api.py:270`. [VERIFIED: src/predictions/api.py:270]

```python
# Source: mirrors api.py:270 GET /api/stats pattern
@app.get("/api/strategy-analytics", dependencies=[Depends(_check_token)])
def get_strategy_analytics(strategy: str):
    session = get_session()

    # Composite filter — D-04 + Phase 03 D-16 symmetry
    base = session.query(Trade).filter(
        Trade.strategy_name == strategy,
        (Trade.dry_run == False) | (
            (Trade.dry_run == True) & (Trade.strategy_name.isnot(None))
        ),
    )

    total = base.count()
    wins = base.filter(Trade.status == "settled_win").count()
    losses = base.filter(Trade.status == "settled_loss").count()
    open_trades = base.filter(Trade.status == "dry_run").count()
    settled = wins + losses
    win_rate = round(wins / settled * 100, 1) if settled > 0 else 0.0

    realized_pnl = (
        session.query(func.sum(Trade.pnl_cents))
        .filter(
            Trade.strategy_name == strategy,
            Trade.pnl_cents.isnot(None),
        )
        .scalar() or 0
    )

    # Trades for log table — newest first
    trade_rows = (
        base
        .order_by(desc(Trade.placed_at))
        .all()
    )

    # P&L curve — settled only, oldest first, running sum in Python (D-05 / D-09)
    settled_rows = (
        base
        .filter(Trade.status.in_(("settled_win", "settled_loss")))
        .order_by(Trade.settled_at)
        .all()
    )
    running = 0
    pnl_curve = []
    for t in settled_rows:
        running += (t.pnl_cents or 0)
        pnl_curve.append({
            "x": t.settled_at.isoformat() if t.settled_at else None,
            "y": running,
            "ticker": t.ticker,
            "trade_pnl": t.pnl_cents,
        })

    session.close()
    return StrategyAnalyticsResponse(...)
```

### Pattern 2: Strategies Summary Endpoint

```python
# Source: D-06 option (a) — new endpoint, no change to /api/strategies
@app.get("/api/strategies-summary", dependencies=[Depends(_check_token)])
def get_strategies_summary():
    session = get_session()

    # All strategy names that have ever fired (from trades table)
    rows = (
        session.query(
            Trade.strategy_name,
            func.count(Trade.id),
            func.sum(func.case((Trade.status == "settled_win", 1), else_=0)),
            func.sum(func.case((Trade.status == "settled_loss", 1), else_=0)),
            func.sum(Trade.pnl_cents),
        )
        .filter(Trade.strategy_name.isnot(None))
        .group_by(Trade.strategy_name)
        .all()
    )

    # Merge with all strategy names from YAML to include zero-trade strategies
    all_strategies = load_strategies()
    # build dict keyed by name from rows...
    session.close()
    return ...
```

**Key insight for zero-trade strategies (D-11):** The DB-only GROUP BY will silently omit strategies that have never fired. The endpoint must merge DB results with `load_strategies()` YAML names, so zero-trade strategies appear with all-zero stats. This is the most easily missed implementation detail. [VERIFIED: Trade table has strategy_name index, load_strategies() exists in api.py imports]

### Pattern 3: recharts Cumulative P&L Line Chart

[VERIFIED: recharts 3.8.1 pinned in dashboard/package.json; API confirmed via official README + refine.dev article]

```typescript
// Source: recharts README + refine.dev/blog/recharts
import {
    LineChart,
    Line,
    XAxis,
    YAxis,
    Tooltip,
    CartesianGrid,
    ResponsiveContainer,
} from "recharts";

// Data shape from API pnl_curve:
// [{ x: "2026-05-01T12:00:00", y: 450, ticker: "KXNBA-...", trade_pnl: 150 }]

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
        <Line
            type="monotone"
            dataKey="y"
            stroke="#d97706"
            dot={false}
            strokeWidth={2}
        />
    </LineChart>
</ResponsiveContainer>
```

**Empty state (D-11):** When `pnlCurve.length === 0`, render `<ResponsiveContainer>` with empty `data={[]}` — recharts renders axes only, no lines, no crash. No copy needed per D-11.

### Pattern 4: 5-Minute setInterval (D-12)

Mirror of `page.tsx:2238`. [VERIFIED: dashboard/app/page.tsx:2238]

```typescript
// Source: dashboard/app/page.tsx:2238 — existing fetchSlow pattern
useEffect(() => {
    if (!authed) return;
    const fetchAll = async () => {
        // fetch /api/strategies-summary + /api/strategy-analytics?strategy=selected
    };
    fetchAll();                                       // immediate on mount
    const id = setInterval(fetchAll, 5 * 60 * 1000); // 5-minute cadence
    return () => clearInterval(id);                   // cleanup on unmount
}, [authed, selected]);   // re-register when selected strategy changes
```

**Dependency array:** Include `selected` so the interval always fetches the currently selected strategy. If `selected` changes mid-interval, the old interval is cleared and a new one starts immediately.

### Pattern 5: StatCard Reuse

`StatCard` is defined at `page.tsx:209` as a local function component (not exported). [VERIFIED: dashboard/app/page.tsx:209]

**Decision for planner:** Either (a) extract `StatCard` to `dashboard/app/components/StatCard.tsx` and import from both `page.tsx` and `analytics/page.tsx`, or (b) re-declare it locally in `analytics/page.tsx` (duplication, but avoids touching the monolith). Option (a) is the correct fix but requires modifying `page.tsx` (removing the local definition). Given the no-grow-monolith constraint, **option (a) is preferred** — it is a net reduction in `page.tsx` size and the shared component is used by both pages. This is a one-file extraction; planner should include it as a sub-task.

The `backtest/page.tsx` pattern shows that sibling pages have their own `SummaryCard` (line 51 in backtest). The planner can choose to keep `StatCard` in `page.tsx` and re-declare a local variant in `analytics/page.tsx` to avoid the extract complexity. Both are valid.

### Pattern 6: Auth Gate (Server Component)

Mirror of `backtest/page.tsx` top-level auth check. [VERIFIED: dashboard/app/actions.ts:27, dashboard/app/backtest/page.tsx:1-5]

```typescript
// dashboard/app/analytics/page.tsx — top of file
"use client";
import { useEffect, useState } from "react";
import { checkAuth } from "../actions";

// Then in the component:
const [authed, setAuthed] = useState<boolean | null>(null);
useEffect(() => {
    checkAuth().then(setAuthed);
}, []);

if (authed === null) return <div className="min-h-screen bg-black" />;
if (!authed) return <LoginForm ... />;  // or redirect
```

Note: `backtest/page.tsx` imports `checkAuth` from `"../actions"` which is the correct relative path for `app/analytics/page.tsx` as well.

### Pattern 7: URL Param (`?strategy=<name>`)

Next.js client components use `useSearchParams` from `"next/navigation"` for reading URL params. `window.history.pushState` or Next.js router for writing. [ASSUMED — standard Next.js 13+ client-side pattern; verify if Next.js 16 has any change]

```typescript
import { useSearchParams } from "next/navigation";

const searchParams = useSearchParams();
const initialStrategy = searchParams.get("strategy") ?? null;
const [selected, setSelected] = useState<string | null>(initialStrategy);

// On strategy click:
const selectStrategy = (name: string) => {
    setSelected(name);
    const url = new URL(window.location.href);
    url.searchParams.set("strategy", name);
    window.history.pushState({}, "", url.toString());
};
```

### Pattern 8: Cross-Link — strategy_name Gap

**Critical finding:** `strategy_name` is NOT currently in `TradeResponse` or the dashboard `Trade` TypeScript interface. [VERIFIED: src/predictions/api.py TradeResponse class (lines 60-76), dashboard/app/page.tsx Trade interface (lines 30-46)]

To enable D-02 cross-links in the trades table, the planner must include:

1. Add `strategy_name: Optional[str] = None` to `TradeResponse` in `api.py`
2. Update the `TradeResponse(...)` constructor call in `get_trades()` to include `strategy_name=t.strategy_name`
3. Add `strategy_name?: string | null` to the `Trade` interface in `page.tsx`
4. In the trades table render loop, wrap strategy_name in `<Link href={"/analytics?strategy=" + t.strategy_name}>`

This is a minimal, safe field addition. `response_model_exclude_none=True` is NOT set on `/api/trades` (unlike `/api/strategies`), so `null` values in existing trades will serialize as `null` in JSON — no breaking change.

### Anti-Patterns to Avoid

- **Don't use SQL window functions for running sum.** SQLite's window function support depends on the SQLite version compiled into Python. The D-05 decision explicitly mandates Python-side running sum. Never use `SUM(...) OVER (ORDER BY settled_at)`.
- **Don't filter by `dry_run == True` only.** The composite filter from D-04/D-16 must be applied verbatim, even though `strategy_name == :name` makes the `dry_run` clause technically redundant.
- **Don't call `load_strategies()` without handling the missing-file case.** It returns an empty list on missing file (per Phase 02 STR-01). Handle gracefully in the summary endpoint.
- **Don't add `strategy_name` to the `strategies-summary` response by omitting zero-trade strategies.** The GROUP BY will naturally exclude them; the explicit merge with YAML names is mandatory for D-11 (zero-trade strategies must appear).
- **Don't import recharts at the top level of a server component.** The analytics page must be `"use client"` since recharts uses browser APIs.
- **Don't call `recharts` components with `data={undefined}`.** Always provide an empty array `[]` when there are no data points.
- **Don't add explanatory empty-state copy per D-11.** Clean zeros only.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Responsive chart container | Custom `<div>` with resize listener | `<ResponsiveContainer>` from recharts | Handles ResizeObserver, SSR dimensions, edge cases [VERIFIED: recharts API] |
| Y-axis dollar formatting | Manual SVG text | `tickFormatter` prop on `<YAxis>` | recharts handles positioning, rotation, overflow automatically |
| Tooltip rendering | Custom hover state + position | `content` prop on `<Tooltip>` | recharts tracks pointer position, visibility, payload binding |
| Auth cookie validation | Any new cookie logic | `checkAuth()` from `actions.ts` | Single drift point — hardcoded salt already there, don't add a second |
| Bearer token injection | Any `fetch(url, {headers: {Authorization}})` in analytics page | The `/api/[...path]/route.ts` proxy | Token injection happens server-side in the proxy; client-side `fetch("/api/...")` gets it for free [VERIFIED: dashboard/app/api/[...path]/route.ts] |

---

## Runtime State Inventory

Step 2.5: SKIPPED — Phase 4 is a greenfield feature addition (new route, new endpoints). No renames, refactors, or migrations. `strategy_name` column was added in Phase 3 and already exists. No stored data requires migration.

---

## Environment Availability Audit

Step 2.6: SKIPPED — Phase 4 has no new external tool dependencies. recharts is already installed (`node_modules` at `dashboard/node_modules/recharts`). Python and Node.js runtimes are project prerequisites already satisfied.

---

## Common Pitfalls

### Pitfall 1: Zero-trade strategies silently absent from sidebar

**What goes wrong:** `/api/strategies-summary` uses GROUP BY on the trades table. Strategies with no trades produce no row — they never appear in the sidebar or selector.
**Why it happens:** SQL GROUP BY returns only groups with at least one row.
**How to avoid:** In `get_strategies_summary()`, call `load_strategies()` to get the full YAML name list, then LEFT JOIN / merge with the DB aggregation results. Zero-trade strategies get all-zero stats.
**Warning signs:** DASH-03 success criterion 4 fails — a strategy that exists in YAML but has no trades is missing from the selector.

### Pitfall 2: SQLITE_BUSY under analytics polling

**What goes wrong:** At 5-min refresh × N browser tabs, the analytics queries race with the scanner's 5s write loop, exceeding `connect_args timeout=5`.
**Why it happens:** SQLite uses file-level locking by default (not WAL). A read query during a scanner write blocks until the writer commits.
**How to avoid:** Keep analytics queries fast (single indexed filter on `strategy_name`). Do NOT add aggregations that full-scan the table. The Phase 03 D-01 `strategy_name` index makes these queries O(log N) per strategy.
**Warning signs:** HTTP 500 from the analytics endpoint with "database is locked" in logs.

### Pitfall 3: recharts in a server component causes hydration error

**What goes wrong:** If `analytics/page.tsx` is not marked `"use client"`, recharts (which uses DOM APIs) throws on the server render.
**Why it happens:** Next.js 16 defaults to Server Components. recharts requires browser globals.
**How to avoid:** Ensure `"use client";` is the first line of `analytics/page.tsx`.
**Warning signs:** `ReferenceError: document is not defined` during `pnpm build`.

### Pitfall 4: `useSearchParams` requires Suspense boundary

**What goes wrong:** In Next.js 13+, `useSearchParams()` must be wrapped in a `<Suspense>` boundary or the build fails.
**Why it happens:** Next.js defers search param reading until client hydration; the build-time static pass cannot resolve it.
**How to avoid:** Either (a) wrap the component that calls `useSearchParams` in `<Suspense>`, or (b) initialize selected from `window.location.search` in a `useEffect` instead. Option (b) avoids Suspense and matches the existing dashboard's pattern (no Suspense in `page.tsx`). [ASSUMED — standard Next.js 13+ behavior; verify with `pnpm build`]
**Warning signs:** Build-time error: "useSearchParams() should be wrapped in a suspense boundary."

### Pitfall 5: pnl_curve contains null settled_at values

**What goes wrong:** `Trade.settled_at` is nullable. If a dry_run strategy trade settled via the WS path without a `settled_at` value being recorded, the curve point has `x: null` and recharts silently drops or misplaces the point.
**Why it happens:** Phase 03 D-13 sets `status="dry_run"` at creation; settlement updates `settled_at`. A DB corruption or missed settlement write could leave `settled_at` null even for `status="settled_win"`.
**How to avoid:** In the Python running-sum loop, skip or fall back to `placed_at` when `settled_at is None`.
**Warning signs:** P&L curve shows fewer points than expected wins+losses.

### Pitfall 6: recharts ResponsiveContainer needs explicit parent height

**What goes wrong:** `<ResponsiveContainer height="100%">` inside a flex container with no explicit height renders at 0px.
**Why it happens:** `height="100%"` is relative to the parent; if the parent has no explicit height, the chart collapses.
**How to avoid:** Either set `height={260}` (fixed pixels) on `ResponsiveContainer`, or ensure the parent `<div>` has an explicit height set via Tailwind (e.g., `h-64`). Fixed pixel height is simpler. [VERIFIED: recharts docs pattern]

---

## Code Examples

### SQL Aggregation for stats object (verified pattern)

```python
# Source: mirrors api.py:296-299 wins/losses/win_rate pattern [VERIFIED]
wins = base.filter(Trade.status == "settled_win").count()
losses = base.filter(Trade.status == "settled_loss").count()
settled = wins + losses
win_rate = (wins / settled * 100) if settled > 0 else 0.0
```

### SQLAlchemy CASE expression for strategies-summary (verified pattern)

```python
# Source: SQLAlchemy 2.x CASE expression syntax [ASSUMED - verify against actual SQLAlchemy version]
from sqlalchemy import case
wins_expr = func.sum(case((Trade.status == "settled_win", 1), else_=0))
losses_expr = func.sum(case((Trade.status == "settled_loss", 1), else_=0))
```

### Dollar formatting in TypeScript (project pattern)

```typescript
// Source: dashboard/app/page.tsx cents() helper pattern [VERIFIED: page.tsx uses cents()]
function fmt(cents: number): string {
    return (cents / 100).toLocaleString(undefined, {
        minimumFractionDigits: 2,
        maximumFractionDigits: 2,
    });
}
// Usage: +$12.30 format
const sign = pnl >= 0 ? "+" : "";
`${sign}$${fmt(Math.abs(pnl))}`;
```

### TradeResponse extension (verified safe)

```python
# Source: api.py TradeResponse (lines 60-76) [VERIFIED]
class TradeResponse(BaseModel):
    ...
    strategy_name: Optional[str] = None  # ADD THIS FIELD
```

---

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hand-rolled SVG charts (page.tsx:255–687) | recharts (Phase 4+) | Phase 04 introduces it | Phase 04 sets recharts as the new default for new charts; old chart coexists intentionally |
| `/api/strategies` for definition only | + new `/api/strategies-summary` for analytics | Phase 04 | Semantic separation: definitions vs performance data |
| `TradeResponse` without strategy_name | `TradeResponse` + `strategy_name` field | Phase 04 (D-02 enabler) | Cross-link requires field to be in API response |

**Deprecated/outdated:**

- `StretchOpportunity` / `stretch_opportunities_archived` table — deleted in Phase 03. Phase 04 must not reintroduce any reference to it. [VERIFIED: Phase 03 D-21, D-20]

---

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | `useSearchParams()` from `next/navigation` requires Suspense in Next.js 16 | Patterns 7, Pitfall 4 | Could use `useSearchParams` without Suspense if Next.js 16 relaxed the restriction; low risk — Suspense wrapper is cheap insurance |
| A2 | SQLAlchemy 2.x CASE syntax is `func.sum(case((condition, value), else_=0))` | Code Examples | Minor API difference from 1.x; if wrong, executor hits a type error immediately and can fix |
| A3 | `window.history.pushState` is the right mechanism for URL param updates without Next.js router re-render | Pattern 7 | If Next.js 16 has a preferred client-side navigation API for `useSearchParams` updates, this may cause stale search param reads; verify with `pnpm build` |

**Three assumptions total — all low-risk and immediately detectable from build/type errors.**

---

## Open Questions

1. **StatCard extraction scope**
   - What we know: `StatCard` at `page.tsx:209` is a local function — not exported. `backtest/page.tsx` has its own local `SummaryCard`.
   - What's unclear: Should planner extract to `dashboard/app/components/StatCard.tsx` (touches monolith, correct fix) or re-declare locally in `analytics/page.tsx` (duplication, zero monolith touch)?
   - Recommendation: Re-declare locally. The extraction is correct engineering but adds a second modified file to the monolith-touch list. At this phase, keeping monolith changes to minimum (D-01) is higher priority than DRY. Mark extraction as a follow-up item.

2. **`cents()` helper in analytics page**
   - What we know: `cents()` function is defined locally in `page.tsx` (not exported). `backtest/page.tsx` has `formatEuro()` instead.
   - What's unclear: Does analytics page need dollar formatting inline or can it reuse something?
   - Recommendation: Define a local `fmt(cents: number): string` in `analytics/page.tsx`. One-liner; no extraction needed.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest 8.0 + pytest-asyncio 0.24 (`asyncio_mode = "auto"`) |
| Config file | `pyproject.toml` `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/test_strategy_analytics.py -x` |
| Full suite command | `uv run pytest tests/` |

Dashboard build gate (type-checking proxy for component correctness): `cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DASH-03 | `/api/strategy-analytics` returns correct stats for strategy with settled trades | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_analytics_returns_correct_stats -x` | ❌ Wave 0 |
| DASH-03 | `/api/strategy-analytics` returns correct pnl_curve (running sum) | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_analytics_pnl_curve_running_sum -x` | ❌ Wave 0 |
| DASH-03 | `/api/strategy-analytics` returns zeroed stats for zero-trade strategy | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_analytics_zero_trade_strategy -x` | ❌ Wave 0 |
| DASH-03 | `/api/strategies-summary` includes zero-trade strategies from YAML | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_summary_includes_zero_trade_strategies -x` | ❌ Wave 0 |
| DASH-03 | `/api/strategies-summary` returns correct per-strategy aggregates | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_summary_aggregation -x` | ❌ Wave 0 |
| DASH-03 | Both endpoints require Bearer auth (401 on missing token) | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_endpoints_require_auth -x` | ❌ Wave 0 |
| DASH-03 | D-04 composite filter excludes trades without strategy_name | integration (TestClient) | `uv run pytest tests/test_strategy_analytics.py::test_composite_filter_excludes_legacy_trades -x` | ❌ Wave 0 |
| DASH-04 | 5-minute auto-refresh pattern (setInterval) | manual-only | Load analytics page, wait 5 min, verify new trades appear | — |
| DASH-03 | Analytics page renders without crash (SSR/build) | build gate | `cd dashboard && pnpm build` | ❌ Wave 0 (new file) |

**Manual-only justification:** Auto-refresh cadence (5 min) cannot be unit-tested without time mocking; the setInterval pattern is visually verified in the browser during UAT.

### Sampling Rate

- **Per task commit:** `uv run pytest tests/test_strategy_analytics.py -x`
- **Per wave merge:** `uv run pytest tests/ && cd dashboard && pnpm lint && pnpm fmt:check && pnpm build`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps

- [ ] `tests/test_strategy_analytics.py` — covers all DASH-03 backend requirements (7 test stubs above)
- [ ] `tests/conftest.py` — already has `isolated_db` fixture; extend with helper to seed multi-strategy `Trade` rows

*(Dashboard component testing is not in scope — the existing codebase has no component test infrastructure, and adding it is a separate concern.)*

---

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | `checkAuth()` cookie gate on page; `Depends(_check_token)` Bearer on endpoints — both already in use |
| V3 Session Management | yes | Existing 30-day `httpOnly` cookie in `actions.ts` — no changes |
| V4 Access Control | no | No per-strategy access control; all authenticated users see all strategies |
| V5 Input Validation | yes | `strategy` query param is a string — sanitize via Pydantic or URL decode; no raw SQL interpolation |
| V6 Cryptography | no | No new crypto surfaces |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via `strategy` param | Tampering | SQLAlchemy parameterized query `filter(Trade.strategy_name == strategy)` — ORM handles escaping [VERIFIED: SQLAlchemy parameterization] |
| Unauthenticated analytics read | Information Disclosure | `Depends(_check_token)` on both new endpoints, `checkAuth()` on the page |
| Path traversal via `[...path]` proxy | Elevation of Privilege | Proxy already in use for all endpoints; no new surface [VERIFIED: route.ts] |

---

## Sources

### Primary (HIGH confidence)

- `src/predictions/api.py` — `TradeResponse`, `_check_token`, `get_stats`, `get_trades`, `get_strategies` — endpoint patterns directly verified
- `src/predictions/db.py` — `Trade` model fields including `strategy_name`, `settled_at`, `pnl_cents`; `connect_args timeout=5`
- `dashboard/package.json` — `recharts: "^3.8.1"` pinned
- `dashboard/app/page.tsx:209` — `StatCard` component definition (local, not exported)
- `dashboard/app/page.tsx:2238` — `setInterval(fetchSlow, 60000)` pattern
- `dashboard/app/actions.ts` — `checkAuth()` server action
- `dashboard/app/api/[...path]/route.ts` — Bearer token proxy auto-routing
- `dashboard/app/backtest/page.tsx` — standalone-route reference for auth pattern
- `tests/conftest.py` — `isolated_db` fixture (in-memory SQLite, autouse)
- `tests/test_strategies_api.py` — `TestClient` fixture pattern for FastAPI tests

### Secondary (MEDIUM confidence)

- recharts README (raw.githubusercontent.com) — `LineChart` basic API (width, height, data, margin, XAxis, Tooltip, Line)
- refine.dev/blog/recharts — `ResponsiveContainer` + `LineChart` + `XAxis`/`YAxis`/`Tooltip` composition pattern with time-series data shape

### Tertiary (LOW confidence)

- None — all critical claims verified against source files or official docs.

---

## Metadata

**Confidence breakdown:**

- Standard stack: HIGH — all libraries verified against package.json and source files
- Architecture: HIGH — endpoint patterns verified against api.py; proxy verified against route.ts
- recharts API: MEDIUM — verified against recharts README and secondary article; storybook unavailable
- Pitfalls: HIGH — derived from direct code inspection (strategy_name gap, StatCard locality, zero-trade GROUP BY omission)

**Research date:** 2026-05-06
**Valid until:** 2026-06-06 (stable stack; recharts API changes slowly)
