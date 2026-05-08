# Phase 4: Analytics Dashboard - Context

**Gathered:** 2026-05-06
**Status:** Ready for planning

<domain>
## Phase Boundary

Build a new authenticated dashboard surface (`/analytics`) that lets the user inspect per-strategy dry-run trading performance — strategy selector, summary stat cards (total/wins/losses/win rate/realized P&L), cumulative P&L line chart, and a per-trade log — auto-refreshing every 5 minutes to surface live activity without manual reload.

The page consumes the strategy attribution data Phase 03 wrote to `Trade.strategy_name` (D-01 in `03-CONTEXT.md`) and the dry-run trade rows produced by `place_strategy_trade` (D-13 in `03-CONTEXT.md`). It must apply the same composite settlement filter (Phase 03 D-16) and use the same contract-math P&L formulas (Phase 03 D-18) so the analytics view reflects the same trades the scanner is reconciling.

**In scope (Phase 04):**

- New standalone Next.js route `dashboard/app/analytics/page.tsx` (mirrors `dashboard/app/backtest/page.tsx`)
- Cross-links from existing strategy-name mentions in `dashboard/app/page.tsx` to `/analytics?strategy=<name>` (planner enumerates the call sites)
- New `GET /api/strategy-analytics?strategy=<name>` endpoint returning `{stats, trades, pnl_curve}` for the detail view
- New `GET /api/strategies-summary` endpoint (planner-verified shape) for the sidebar's per-strategy mini-stats
- Sidebar UI with at-a-glance per-strategy mini-stats; URL `?strategy=<name>` for deep-link/refresh stability
- Stat cards: total trades, wins, losses, win rate, realized P&L
- Cumulative P&L line chart (recharts); per-trade-step x-axis on settled trades
- Trade log table (date, ticker, entry price, contracts, P&L, status)
- 5-minute auto-refresh
- Header-link discoverability from main `page.tsx` (alongside the existing Backtest link)
- Behind the existing `checkAuth` cookie gate

**Out of scope (deferred):**

- Strategy editor / save-back to `strategies.yaml` (Future Requirements; Phase 02 deferred)
- Hot-reload of `strategies.yaml` without container restart (Future Requirements)
- Per-trigger analytics (`trigger_index` column on `Trade`) — Phase 03 deferred; revisit if usage signals demand
- Per-strategy `bet_percent` override (Future Requirements)
- Migrating the existing hand-rolled `PnlChart` at `page.tsx:255–687` to recharts (follow-up cleanup phase, conditional on Phase 04 success)
- Real-money trading — milestone is dry-run only; `trading_paused` kill switch remains
- CLI commands for analytics access — out of v1.2 scope per REQUIREMENTS.md
- Time-window filtering (last 7d / 30d / all-time) on the analytics page
- Comparison/diff view between two strategies (single-strategy detail view only)

</domain>

<success_criteria>
## Success Criteria (Locked by ROADMAP.md § Phase 4)

These are pre-decided and downstream agents must verify each:

1. A new dashboard page (behind `checkAuth` gate) shows a strategy selector, summary stat cards (total trades, wins, losses, win rate, realized P&L), and a cumulative P&L line chart for the selected strategy.
2. A trade log table on the analytics page shows per-trade detail (date, ticker, entry price, contracts, P&L, status) for the selected strategy.
3. The page auto-refreshes every 5 minutes; new dry-run trades appear without a manual reload.
4. Strategies with zero trades appear in the selector but show empty charts and zeroed stat cards rather than 404 or blank page.

</success_criteria>

<decisions>
## Implementation Decisions

### Page architecture & navigation

- **D-01:** New standalone Next.js route at `dashboard/app/analytics/page.tsx` (mirrors the `dashboard/app/backtest/page.tsx` pattern). The 98KB `dashboard/app/page.tsx` monolith does **not** grow further. The new page authenticates via the same `checkAuth()` from `dashboard/app/actions.ts` and uses the same server-side proxy at `dashboard/app/api/[...path]/route.ts` for Bearer-token injection. URL parameter `?strategy=<name>` reflects the selected strategy and is refresh-stable / deep-linkable.

- **D-02:** Strategy names that appear elsewhere in the main dashboard become clickable links to `/analytics?strategy=<name>`. **Planner action:** enumerate the call sites in `dashboard/app/page.tsx` where `Trade.strategy_name` (or any rendered "strategy" text) appears — at minimum the trades table area (`page.tsx:2620+`) once strategy_name surfaces in the JSON. Wrap each in a small `<Link>` component or `<a>` tag. This is intentional scope: the analytics page is the destination; the main dashboard is the discovery surface.

- **D-03:** Header link "Analytics" added to `dashboard/app/page.tsx` near any existing nav link to `/backtest`. Single-line addition; no new nav-component refactor (would belong in its own phase). Aligned with the lean dashboard style — no sidebar navigation component is introduced.

### API endpoint shape

- **D-04:** **Detail view** is served by a single new endpoint `GET /api/strategy-analytics?strategy=<name>` returning `{stats, trades, pnl_curve}` in one response. One DB query budget per 5-min auto-refresh per browser tab. Bearer-auth via `dependencies=[Depends(_check_token)]` like every other endpoint. The endpoint reads the `Trade` table with the **same composite filter as Phase 03 D-16**: `Trade.strategy_name == :name AND (Trade.dry_run == False OR (Trade.dry_run == True AND Trade.strategy_name.isnot(None)))`. Note: with `strategy_name == :name` already filtering, the `dry_run/strategy_name` clause is redundant but **must still be applied** so this query stays in lockstep with the settlement query if the schema ever evolves (e.g., legacy data migrations).

- **D-05:** **Aggregation runs in SQL** in the endpoint handler. One query per metric using `SUM/COUNT/CASE` (totals, wins, losses); win rate computed in Python from those counts. P&L curve produced by ordering `SELECT settled_at, pnl_cents FROM trades WHERE strategy_name=:n AND status IN ('settled_win', 'settled_loss') ORDER BY settled_at` and computing the running sum in Python (SQLite has no window functions in older versions; the Python sum is O(N) and N is small). Mirrors the existing `/api/stats` aggregation pattern in `src/predictions/api.py:270`.

- **D-06:** **Sidebar mini-stats** are served by a separate small endpoint. **Planner choice (lean toward (a)):**
  - **(a) (recommended)** New `GET /api/strategies-summary` endpoint returning a list of `{name, total_trades, wins, losses, pnl_cents}` per strategy — keeps `/api/strategies` semantic-pure (definition data; consumed by the backtest page) and `/api/strategies-summary` analytics-focused. One SQL query: `SELECT strategy_name, COUNT(*), SUM(CASE WHEN status='settled_win' THEN 1 ELSE 0 END), SUM(CASE WHEN status='settled_loss' THEN 1 ELSE 0 END), SUM(pnl_cents) FROM trades WHERE strategy_name IS NOT NULL GROUP BY strategy_name`.
  - **(b)** Fold mini-stats into the existing `/api/strategies` response — saves an endpoint but mixes concerns; backtest page would receive analytics fields it doesn't use.
  Planner picks one; document the choice in the plan summary. Both refresh on the same 5-min cadence as the detail endpoint.

- **D-07:** **No in-memory cache layer.** The 5-min refresh cadence already self-limits DB pressure; per-tab fetches are at most 2/refresh × N tabs. The `connect_args timeout=5` from Phase 03 D-02 is the sole `SQLITE_BUSY` buffer. If polling pressure grows beyond this (more tabs, shorter refresh), revisit by switching SQLite to WAL mode or moving analytics to a read replica — both are out of Phase 04 scope and recorded in `STATE.md` Blockers/Concerns.

### Charting approach

- **D-08:** **recharts** (already in `dashboard/package.json` @ 3.8.1, currently unused) for the cumulative P&L line chart on the analytics page. Components: `<ResponsiveContainer><LineChart><XAxis/><YAxis/><Tooltip/><Line/></LineChart></ResponsiveContainer>`. Bundle size impact (~80KB if not already tree-shaken) is acceptable. **The existing hand-rolled SVG `PnlChart` at `dashboard/app/page.tsx:255–687` is NOT migrated in this phase** — it stays as-is. This is a deliberate one-way pattern shift: new analytics code uses recharts; existing balance-curve code stays hand-rolled. Migration of the legacy chart is recorded in deferred ideas.

- **D-09:** **P&L curve x-axis: per-trade step** (not time-bucketed). For each settled trade, `x = settled_at` (datetime), `y = running pnl_cents` sum. Trades with status `dry_run` (still open) are excluded from the curve points but their pending count contributes to the stat cards as "open trades" (planner adds an "Open" stat card if the locked five aren't sufficient — Claude's discretion). Y-axis formatted in dollars (`pnl_cents / 100` with 2 decimals). Tooltip on hover shows date, ticker, single-trade P&L, running total.

### Strategy selector UX

- **D-10:** **Sidebar list** with at-a-glance per-strategy mini-stats. Left column lists every strategy from `/api/strategies-summary` (D-06) with a compact line per row showing P&L, W/L counts, win rate (e.g., `+$12.30 · 3W/2L · 60%`). Click anywhere on the row drills into the detail view in the main panel (URL updates to `?strategy=<name>`). On page load, default selection is the first strategy in the list (or whatever `?strategy=` parameter specifies if present).

- **D-11:** **Zero-trade strategies** appear in the selector with mini-stats `0 · 0W/0L · —` (or similar zeros-only formatting). When selected, all stat cards show 0, the P&L chart shows an empty plot (no points, just axes), and the trade log table shows an empty body. **No explanatory copy** ("strategy hasn't fired yet" etc.) per user preference — clean zeros only. This satisfies ROADMAP success criterion #4.

### Auto-refresh

- **D-12:** **5-minute auto-refresh** via React `useEffect` + `setInterval(fetchAnalytics, 5 * 60 * 1000)` — same pattern as the existing 60s `fetchSlow` interval at `dashboard/app/page.tsx:2238`. Both endpoints (`/api/strategy-analytics` for the selected strategy + `/api/strategies-summary` for the sidebar) refetch on each tick. **Cleanup**: clear the interval on unmount (component cleanup in the `useEffect` return). No SWR/React Query (would be a new dep; PROJECT.md "no new packages without strong reason"). Refresh feedback UX (silent vs subtle indicator) is Claude's discretion.

### Claude's Discretion

- **Open-trade stat handling.** ROADMAP locks five stat cards (total, wins, losses, win rate, realized P&L). If "total trades" already counts opens, that may be sufficient. If the planner judges a sixth "Open trades" card is clearer, add it — both are within ROADMAP intent.

- **Trade log column choices and widths.** ROADMAP locks date / ticker / entry price / contracts / P&L / status. Whether to show `placed_at` or `settled_at` (or both with one as a tooltip), how to format ticker (KXEPL-MARSEILLE vs short form), whether to show contracts as a number or "$X cost" — planner judgment. Sort default: newest first.

- **Trade log filtering / sorting controls.** ROADMAP doesn't require filters. Default to chronological-newest-first, no filter UI. If the planner judges a status-filter dropdown is cheap to add (open/won/lost/all), allowed but not required.

- **Refresh feedback UX.** Silent vs `<span>Updating…</span>` indicator vs last-refreshed timestamp — planner picks. Lean toward subtle ("Last updated 12:34") since the dashboard's existing pattern is silent polling.

- **Mobile / responsive layout.** Existing dashboard is responsive; analytics page should follow. Sidebar collapse behavior on narrow viewports is planner discretion (drawer? top dropdown? horizontal scroll?).

- **Loading / skeleton state.** First fetch + auto-refresh both have loading windows. Planner picks: skeleton component, spinner, or just held-stale-data pattern. Lean toward held-stale (existing dashboard does this; less flicker).

- **Empty-state illustration.** No-trades-yet view is allowed to be visually empty (no stylized illustration); per D-11, no copy.

- **URL state for sidebar collapse / panel widths.** Not required to persist.

</decisions>

<specifics>
## Specific Ideas

- The user **explicitly chose recharts** over the hand-rolled SVG approach despite the recommendation to stay consistent with the existing PnlChart. Read this as deliberate: the user wants to evaluate recharts as the new default for new charts. Migration of the legacy chart is the natural follow-up (deferred), but Phase 04 stops at "introduce recharts for new code."

- The user **explicitly chose the sidebar list with at-a-glance mini-stats** over the simpler dropdown. Implication: the sidebar must show real numerical signals at a glance (P&L, win rate), not just names. Plan time accordingly — this is more UI work than a `<select>`.

- The user **chose clean zeros for empty strategies** over an explanatory empty state ("strategy hasn't fired since loading"). Aligns with the lean dashboard style. Don't reintroduce explanatory copy in trade log empty rows or chart empty plots.

- The user **chose the cross-link approach** (option C in the page-architecture question). Plan must include enumerating strategy-name surfacing locations in `dashboard/app/page.tsx` and converting them to `<Link href="/analytics?strategy=...">` — this is more files-touched than option A would have been. Phase 03 added `Trade.strategy_name` to the trades query; the planner verifies whether the trades table already shows it (per Phase 03 SUMMARY) and where else strategy mentions appear.

- **Composite settlement filter symmetry:** the analytics queries MUST apply the same `dry_run==False OR (dry_run==True AND strategy_name IS NOT NULL)` filter that Phase 03 D-16 enforces in `check_settlements`. With `strategy_name == :name` already in the WHERE clause this is technically redundant, but applying it keeps the analytics query in lockstep with the settlement query — preventing drift if the schema ever changes.

- **No CLI surface in Phase 04** per REQUIREMENTS Out of Scope. The analytics page is the only consumer of the new endpoints in v1.2.

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents (researcher, planner, executor) MUST read these before acting.**

### Phase scope and acceptance

- `.planning/ROADMAP.md` § Phase 4 — phase goal, depends-on (Phase 3), **4 success criteria** that must all be TRUE. Criterion #4 (zero-trade strategies show in selector with empty/zeroed UI) is the most easily missed.

- `.planning/REQUIREMENTS.md` § DASH-03, DASH-04 — canonical functional requirements. DASH-03 specifies the trade-log columns (date, ticker, price, contracts, P&L, status) and the cumulative P&L line chart. DASH-04 specifies the 5-min auto-refresh cadence.

- `.planning/PROJECT.md` § Active / Constraints / Key Decisions — no-new-packages rule (recharts already in deps qualifies as "already approved"), integer-cents invariant, oxfmt 4-space indent, `pnpm fmt:check && pnpm lint && pnpm build` gate, all dashboard pages behind `checkAuth`, `trading_paused` kill switch invariant.

- `.planning/STATE.md` § Blockers/Concerns — **Phase 4 entries:** (1) `/api/sport-stats` semantics changed by Phase 03 D-19 — Phase 04 analytics queries must NOT regress to old "near-miss rows" semantics; (2) `connect_args timeout=5` is the sole `SQLITE_BUSY` buffer — Phase 04 query design respects this; (3) low-priority alias-amplification YAML safe_load max-file-size note (only relevant if a future strategy editor is added — not in this phase).

### Prior-phase context (must read)

- `.planning/phases/03-scanner-integration/03-CONTEXT.md` — Phase 3 decisions Phase 04 depends on. **Critical sections:**
  - **D-01** (`Trade.strategy_name = Column(String, nullable=True, index=True)`) — the indexed column Phase 04 queries.
  - **D-02** (`connect_args timeout=5`) — sole `SQLITE_BUSY` buffer. Phase 04 must not blow past this.
  - **D-13** (`place_strategy_trade` writes `dry_run=True`, `strategy_name=<name>`, `yes_price=opp["yes_ask"]`, `count=max_cost_cents // yes_price`) — defines the row shape the analytics page reads.
  - **D-16** (composite settlement filter) — Phase 04 analytics queries apply the same filter for symmetry. See Specifics above.
  - **D-18** (P&L math: win = `count × (100 − yes_price)`; loss = `−count × yes_price`; status flow `dry_run → settled_win | settled_loss | error`; no fee on dry-runs) — analytics displays these `pnl_cents` values directly.
  - **D-19** (`/api/sport-stats` re-sourced from `opportunities` table; "played" = distinct events scanned) — if Phase 04 adds any sport-related rollup, follow this convention.
  - **D-21** (deletion of `/api/stretch-stats`, `/api/stretch`, dashboard "What If? Strategy Comparison" tab) — Phase 04 must NOT reintroduce stretch-related endpoints or UI. The analytics page replaces what the deleted Strategy tab partially attempted.

- `.planning/phases/02-strategy-engine-core/02-CONTEXT.md` — **Critical sections:**
  - **D-09** (`GET /api/strategies` endpoint) — already exists; Phase 04 reads it (or extends it / parallels it for mini-stats per D-06 above).
  - **`Revision — 2026-04-30 (D-02 OVERRIDE)`** — sport family literals (`football`, `basketball`, …) are the YAML vocabulary; `soccer` is never used. Analytics surfaces strategy names; doesn't directly render sport, but if it does (via a strategy summary), use UK terminology.

- `.planning/phases/01-backtest-p-l-math/01-CONTEXT.md` — Phase 1 contract-math formulas. Phase 04 mirrors these in the analytics view (`yes_price` cents, `count` integer, `pnl_cents` integer). **Integer cents throughout** — convert to dollar string only at the API boundary or final UI render.

### Code conventions

- `.planning/codebase/CONVENTIONS.md` — Python: `uv` + `ruff` + `ty`; Pydantic for boundaries; **dashboard pages behind `checkAuth`**; **no new packages without strong reason** (recharts already in deps qualifies as "already approved"); oxfmt 4-space indent; `pnpm fmt:check && pnpm lint && pnpm build` gate.

- `.planning/codebase/ARCHITECTURE.md` — auth model (Bearer through proxy), runtime config flow, integer-cents invariant. Phase 04 adds new authenticated endpoints behind `Depends(_check_token)` and a new authenticated page behind `checkAuth`.

- `.planning/codebase/STRUCTURE.md` — repo layout. **New dashboard page location:** `dashboard/app/analytics/page.tsx` (sibling of `dashboard/app/backtest/page.tsx`). **New backend endpoint location:** `src/predictions/api.py` next to existing endpoints.

- `.planning/codebase/TESTING.md` — pytest conventions; `isolated_db` / `isolated_soccer_db` fixtures. Phase 04 adds `tests/test_strategy_analytics.py` (or similar) seeding `Trade` rows with `strategy_name` set across `settled_win`, `settled_loss`, `dry_run` statuses.

- `.planning/codebase/CONCERNS.md` — known tech debt around `dashboard/app/page.tsx` size (98KB monolith). Phase 04 explicitly avoids growing it further (D-01 standalone route).

### Code references (existing code Phase 04 reads or modifies)

#### Backend (Python / FastAPI)

- `src/predictions/api.py:265` — root `GET /` health check (the only no-auth endpoint).
- `src/predictions/api.py:270` — `GET /api/stats` — pattern to mirror for `GET /api/strategy-analytics` (Pydantic response model, `Depends(_check_token)`, SQL aggregation).
- `src/predictions/api.py:374` — `GET /api/trades` — pattern for trade-list endpoints; query+limit shape.
- `src/predictions/api.py:461` — `GET /api/sport-stats` — Phase 03 D-19 just rewired this; if Phase 04 adds any sport-rollup logic, it follows D-19's "distinct events from `opportunities`" semantics.
- `src/predictions/db.py` `Trade` model — `strategy_name`, `pnl_cents`, `placed_at`, `settled_at`, `status`, `yes_price`, `count`, `ticker`, `dry_run` fields. All used by analytics queries.
- `src/predictions/db.py` `_check_token` (Depends) — Bearer-auth dependency; new endpoints reuse.

#### Dashboard (Next.js / TypeScript)

- `dashboard/app/page.tsx` — main dashboard SPA (98KB monolith). Phase 04 modifies it minimally: (a) add header link to /analytics (D-03); (b) wrap strategy-name mentions in cross-links (D-02). Do NOT add the analytics page itself here.
- `dashboard/app/page.tsx:209` — `StatCard` component definition. The analytics page reuses this (or a sibling component) for stat cards. Verify the import path; consider extracting to a shared module if it's currently scoped inside `page.tsx`.
- `dashboard/app/page.tsx:255–687` — hand-rolled `PnlChart` component. **NOT migrated in Phase 04** (deferred). Phase 04's chart uses recharts (D-08) — different pattern; coexistence is intentional.
- `dashboard/app/page.tsx:2238` — existing `setInterval(fetchSlow, 60000)` pattern. Phase 04 mirrors this with 5-minute interval (D-12).
- `dashboard/app/page.tsx:2620+` — existing trades table area; one of the cross-link sites the planner enumerates (D-02).
- `dashboard/app/backtest/page.tsx` — existing standalone-route reference; Phase 04 mirrors its structure.
- `dashboard/app/actions.ts` — `checkAuth()` server action. Both /backtest and /analytics use it.
- `dashboard/app/api/[...path]/route.ts` — server-side proxy that injects Bearer token. New endpoints automatically routed; no per-endpoint proxy change.
- `dashboard/package.json` — `recharts: ^3.8.1` already pinned; no `pnpm add` required.

### Origin / dependencies

- `tests/test_strategies.py` (Phase 02) — test fixture/setup pattern for strategy-related tests.
- `tests/conftest.py` `isolated_db` fixture — extends with seeded `Trade` rows (multi-strategy, multi-status) for analytics endpoint tests.
- `.env.example` — no new env vars in Phase 04.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets

- **`StatCard` component** at `dashboard/app/page.tsx:209` — existing card component for the dashboard's stat tiles. Analytics page reuses it for total trades / wins / losses / win rate / realized P&L. Planner verifies whether it's exported or buried inside `page.tsx`; if buried, extract to `dashboard/app/components/StatCard.tsx` (or similar) once and import from both pages.

- **`checkAuth()`** in `dashboard/app/actions.ts` — server action that validates the `predictions_auth` cookie. Wrap the analytics route's server component with this check; redirect to login on failure (mirror `backtest/page.tsx` if it does this, or `page.tsx` otherwise).

- **`/api/[...path]/route.ts` proxy** — automatic Bearer-token injection for any new `/api/*` endpoint. Phase 04 needs zero proxy changes.

- **`setInterval` pattern at `page.tsx:2238`** — `useEffect(() => { const i = setInterval(fetchSlow, 60000); return () => clearInterval(i); }, [])`. Phase 04 mirrors at 5 min.

- **SQL aggregation pattern in `/api/stats`** (`api.py:270`) — pattern for SUM/COUNT/CASE in a single query with Pydantic response model. The analytics endpoint follows this shape.

- **`isolated_db` fixture in `tests/conftest.py`** — seedable SQLAlchemy session for endpoint tests. Phase 04 extends with multi-strategy `Trade` rows.

### Established Patterns

- **Single-drift-point integration boundaries.** `extract_cents` is the only Kalshi price extractor; `load_strategies` is the only YAML reader; `_check_token` is the only Bearer-auth dependency. Phase 04 adds new endpoints that **reuse `_check_token`** — no new auth surface. The analytics page reads strategy names through `/api/strategies` (existing) and analytics aggregates through new endpoints — no new YAML reads, no new price extractors.

- **Bearer-auth on every endpoint** except `GET /` — analytics endpoints use `dependencies=[Depends(_check_token)]`.

- **`checkAuth` cookie gate on every dashboard page** — analytics page enforces this server-side; cookie verified before any client render.

- **Lean dashboard style** — no toast/modal libs, no UI component library, no client-side state library. Phase 04 sticks to React local state + `useEffect` + `fetch`.

- **Integer cents throughout** — `yes_price`, `pnl_cents`, `cost_cents` all in cents. Convert to dollars only at the boundary (rendering or API JSON response, planner choice). Phase 04 follows the integer-cents invariant.

- **No silent feature flags** (CONVENTIONS.md). Phase 04 introduces no toggle.

- **Permissive logging + log-and-continue** in scanner loops — does not apply to API endpoints (which are request-scoped) but the analytics page itself should not crash on a single bad row; render an error placeholder, log to console.

### Integration Points

- **`Trade.strategy_name` index** (Phase 03 D-01) — analytics queries filter by `strategy_name`, leveraging the existing index. No new indexes needed for Phase 04.
- **Composite settlement filter** (Phase 03 D-16) — applied symmetrically in analytics queries (Specifics above).
- **`Trade.status` enum** (`placed`, `filled`, `settled_win`, `settled_loss`, `dry_run`, `error`) — analytics segments trades by these statuses for stat cards and chart.
- **`/api/strategies` endpoint** (Phase 02 D-09) — sidebar reads strategy names from this; analytics page may use it to render the strategy `description` next to the name.
- **`page.tsx` strategy-name mentions** (D-02) — planner enumerates and converts to `<Link>` cross-links.

</code_context>

<deferred>
## Deferred Ideas

- **Migrate hand-rolled `PnlChart` at `page.tsx:255–687` to recharts** — out of Phase 04 scope. Schedule as a follow-up cleanup phase (not auto-numbered) once Phase 04's recharts integration ships and is stable in production.
- **Per-trigger analytics breakdown (`trigger_index` column on `Trade`)** — Phase 03 deferred. Phase 04 omits trigger-level breakdown entirely. Revisit if usage signals demand.
- **Time-window filtering** (last 7d / 30d / all-time) on the analytics page — not in ROADMAP success criteria. Plan can add later.
- **Strategy comparison / diff view** between two strategies side-by-side — not in ROADMAP. Single-strategy detail view only.
- **CLI commands for analytics access** — out of v1.2 scope per REQUIREMENTS Out of Scope.
- **Strategy editor in dashboard / save-back to `strategies.yaml`** — Future Requirements (Phase 02 deferred). Plan rejects.
- **Hot-reload of `strategies.yaml`** — Future Requirements; design needed for in-flight strategy mismatches.
- **Per-strategy `bet_percent` override** — Future Requirements.
- **Real-time WS push of new trades** — overkill given the 5-min cadence requirement. If users genuinely need sub-minute freshness, revisit in a future phase.
- **SWR / React Query** — would be a new dep; Phase 04 uses raw `useEffect` + `fetch` per existing dashboard pattern.
- **Per-strategy `enabled: false` flag in YAML** — Phase 03 deferred; not relevant here.
- **WAL mode / read replica for SQLite** — only if `connect_args timeout=5` proves insufficient under analytics polling pressure. Not pre-emptively applied.

</deferred>

---

*Phase: 04-analytics-dashboard*
*Context gathered: 2026-05-06*
