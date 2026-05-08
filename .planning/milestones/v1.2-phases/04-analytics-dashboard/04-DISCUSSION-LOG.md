# Phase 4: Analytics Dashboard - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-05-06
**Phase:** 04-analytics-dashboard
**Mode:** discuss (default, interactive)
**Areas discussed:** Page architecture & nav, API endpoint shape, Charting approach, Strategy selector UX

---

## Page architecture & nav

### Q1: Where should the analytics page live?

| Option | Description | Selected |
|--------|-------------|----------|
| Standalone /analytics route | New file dashboard/app/analytics/page.tsx, mirroring the backtest page pattern. Keeps page.tsx from growing further. Own checkAuth check via the same actions.ts. | |
| New tab on the existing page.tsx | Single-SPA navigation, no route change. Adds ~1-3KB more to the 98KB monolith. | |
| Standalone route + cross-link from each strategy mention | Standalone page, plus link strategy names wherever they appear in the main dashboard to /analytics?strategy=name. More integration surface, more code touched. | ✓ |

**User's choice:** Standalone route + cross-link from each strategy mention.
**Notes:** The cross-link choice expands scope: planner must enumerate strategy-name surfacing locations in dashboard/app/page.tsx (notably the trades table where strategy_name surfaces post-Phase 03) and wrap each in a clickable Link. Captured as D-01 + D-02 in CONTEXT.md.

### Q2: How should the analytics page be discoverable from the main dashboard?

| Option | Description | Selected |
|--------|-------------|----------|
| Header link on main page | Add a single 'Analytics' link near the existing header in page.tsx. Minimal blast radius. | ✓ |
| Sidebar/menu component | Introduce a real navigation component shared between pages. Opens a refactor that would belong in its own phase. | |
| Direct-URL only | Page exists at /analytics but no link from main page. Lowest blast radius; weakest UX. | |

**User's choice:** Header link on main page (Recommended).
**Notes:** Captured as D-03 in CONTEXT.md.

---

## API endpoint shape

### Q3: How many endpoints should serve the analytics page?

| Option | Description | Selected |
|--------|-------------|----------|
| Single combined endpoint | GET /api/strategy-analytics?strategy=name returns {stats, trades, pnl_curve} in one response. One DB hit per refresh per tab. Friendly to SQLITE_BUSY (D-02 timeout=5 is the only buffer). | ✓ |
| Two endpoints (stats + trades) | GET /api/strategy-stats + GET /api/strategy-trades. Cleaner separation but 2x DB queries per refresh. | |
| Three endpoints | Most separation, 3x DB pressure. Probably overkill. | |

**User's choice:** Single combined endpoint (Recommended).
**Notes:** Captured as D-04 in CONTEXT.md. Note: this decision applies to the detail view; the sidebar's per-strategy mini-stats (decided later in Q8) added a second endpoint surface — handled in D-06.

### Q4: Where should aggregation be computed?

| Option | Description | Selected |
|--------|-------------|----------|
| SQL GROUP BY in the endpoint | One SQL query per metric using SUM/COUNT/CASE. Mirrors existing /api/stats pattern. | ✓ |
| Python loop after SELECT * | Fetch all trades for a strategy, compute totals in Python. Acceptable if total trades stays small. | |
| Cache layer (5-min TTL in api.py) | Compute once per refresh window, cache in-process. Adds invalidation surface. Probably premature. | |

**User's choice:** SQL GROUP BY in the endpoint (Recommended).
**Notes:** Captured as D-05 in CONTEXT.md. P&L curve uses a Python running sum after SQL ORDER BY (SQLite's window function support is version-dependent).

---

## Charting approach

### Q5: Which charting library should the cumulative P&L line chart use?

| Option | Description | Selected |
|--------|-------------|----------|
| Hand-rolled SVG | Mirror the existing PnlChart at page.tsx:255–687. Consistent visual style. ~150 lines of focused SVG. recharts stays unused. | |
| recharts (already in package.json) | <LineChart>/<XAxis>/<YAxis>/<Tooltip>/<ResponsiveContainer> — maybe ~30 lines. Introduces a second charting pattern. | ✓ |
| Reuse the existing PnlChart component as-is | If PnlChart is generic enough, import and render it on /analytics. Risk: it may be tightly coupled to balance-curve semantics. | |

**User's choice:** recharts (already in package.json).
**Notes:** Deliberate departure from the existing hand-rolled pattern. Implication: existing PnlChart at page.tsx:255–687 stays as-is in this phase; migration to recharts deferred as a follow-up cleanup conditional on Phase 04 success. Captured as D-08 in CONTEXT.md.

### Q6: How should the P&L curve x-axis be bucketed?

| Option | Description | Selected |
|--------|-------------|----------|
| Per-trade step | x = settled_at, y = running pnl_cents sum. One point per settled trade. Honest representation of when P&L actually changed. | ✓ |
| Daily buckets | Sum P&L by day. Smoother curve, less informative when trade volume is low. | |
| Both — toggle | Add a small toggle UI. More code. Premature for a fresh analytics surface. | |

**User's choice:** Per-trade step (Recommended).
**Notes:** Captured as D-09 in CONTEXT.md.

---

## Strategy selector UX

### Q7: How should the user pick which strategy to inspect?

| Option | Description | Selected |
|--------|-------------|----------|
| Sidebar list with at-a-glance mini-stats | Left sidebar lists all strategies with mini stat (e.g., '+$12 · 3W/2L · 60%'). Click to drill down. Comparison at a glance. Requires fetching minimum stats for ALL strategies on load. | ✓ |
| Dropdown only | Single <select> at the top, mirrors the existing strategy dropdown in dashboard/app/backtest/page.tsx. | |
| Tabs across the top | One tab per strategy with totals badge. Works for ~5 strategies, gets cramped past that. | |

**User's choice:** Sidebar list with at-a-glance mini-stats (Recommended).
**Notes:** Implication: sidebar must show real numerical signals at a glance, not just names. This is more UI work than a <select>. Drove a follow-up sub-decision (D-06) on the data shape: a separate /api/strategies-summary endpoint feeds the sidebar; the existing /api/strategies endpoint stays definition-only. Captured as D-10 in CONTEXT.md.

### Q8: What about strategies with zero trades?

| Option | Description | Selected |
|--------|-------------|----------|
| Listed in selector + empty state with hint | Strategy appears in the selector. Stat cards = 0; chart shows '— No trades yet' with a one-liner explanation. | |
| Listed + just zeros (no explanatory text) | Cards = 0, chart blank, table empty — no commentary. Cleaner but ambiguous: is the strategy broken, paused, or just hasn't fired? | ✓ |
| Hide zero-trade strategies | Filter them out. Violates ROADMAP success criterion #4. | |

**User's choice:** Listed + just zeros (no explanatory text).
**Notes:** Aligns with the lean dashboard style. Don't reintroduce explanatory copy in trade log empty rows or chart empty plots. Satisfies ROADMAP success criterion #4. Captured as D-11 in CONTEXT.md.

---

## Final gate

| Option | Description | Selected |
|--------|-------------|----------|
| I'm ready for context | Decisions sufficient; write CONTEXT.md and proceed to /gsd-plan-phase 4. | ✓ |
| Discuss trade log details | Trade log columns / sort / filter / open-trade handling. | |
| Discuss auto-refresh feedback UX | Silent vs subtle indicator vs toast. | |
| Discuss URL/deep-link & mobile | Time-window filters in URL, mobile sidebar collapse. | |

**User's choice:** I'm ready for context (Recommended).
**Notes:** Smaller details (loading states, exact column order, refresh feedback UX, mobile responsive shape) deferred to Claude's discretion in CONTEXT.md.

---

## Claude's Discretion

Areas left to the planner:
- Open-trade stat handling (add a 6th "Open trades" card or fold into "total")
- Trade log column choices and widths (placed_at vs settled_at; ticker formatting; contracts vs $cost display)
- Trade log filtering / sorting controls (default chronological-newest-first; status filter optional)
- Refresh feedback UX (silent vs "Updating…" indicator vs last-refreshed timestamp; lean toward subtle)
- Mobile / responsive layout for sidebar (drawer, top dropdown, horizontal scroll)
- Loading / skeleton state (held-stale-data preferred over flicker)
- Whether to expose the empty state with an illustration or stay visually empty (empty per D-11)
- A or B for D-06 (`/api/strategies-summary` separate endpoint vs folded into `/api/strategies`); recommended A
- Whether `StatCard` is exported or buried in `page.tsx`; if buried, extract to a shared module

## Deferred Ideas

- Migrate existing hand-rolled PnlChart at page.tsx:255–687 to recharts — follow-up cleanup phase, conditional on Phase 04 recharts integration shipping well.
- Per-trigger analytics breakdown (trigger_index column on Trade) — Phase 03 deferred; usage-driven.
- Time-window filtering on the analytics page — not in ROADMAP.
- Strategy comparison / diff view — single-strategy detail only.
- CLI commands for analytics — out of v1.2 scope.
- Strategy editor in dashboard / save-back to strategies.yaml — Future Requirements.
- Hot-reload of strategies.yaml — Future Requirements.
- Per-strategy bet_percent override — Future Requirements.
- Real-time WS push of new trades — overkill given 5-min cadence.
- SWR / React Query — would be a new dep; raw fetch is fine.
- WAL mode / read replica for SQLite — only if connect_args timeout=5 proves insufficient.
