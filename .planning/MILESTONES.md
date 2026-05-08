# Milestones

## v1.2 — Strategy Engine

**Shipped:** 2026-05-08
**Phases:** 4 (01–04) | **Plans:** 17

### Delivered

Replaced the hardcoded `WHAT_IF_STRATEGIES` shadow-backtest list with a file-driven strategy engine. Named strategies in `strategies.yaml` (multi-trigger OR-of-AND conditions) drive both the backtest simulator and the live scanner via a single `load_strategies()` source of truth. The live scanner fires dry-run trades — Kalshi-price-recorded but no API call — and a new `/analytics` dashboard page (auth-gated, 5-min auto-refresh) surfaces per-strategy P&L curve, win rate, stat cards, and trade log. The stretch system (`WHAT_IF_STRATEGIES`, `_evaluate_what_if_strategies`, `stretch_opportunities` ORM) was decommissioned; the underlying table was renamed (not dropped) for rollback safety.

### Key Accomplishments

1. **Strategy engine via `strategies.yaml`** — File-driven OR-of-AND multi-trigger strategies; single `load_strategies()` source of truth for both backtest and live scanner (no parallel YAML parsers).
2. **Contract-based backtest math** — `dashboard/app/backtest/backtest.ts` rewritten around `contracts = floor(stake/price)`, win = `contracts × (100 − price)`, loss = `contracts × price`; `avg_win_yield` removed from UI.
3. **Live scanner dry-run trading** — `evaluate_strategies` + `place_strategy_trade` write `Trade(dry_run=True, strategy_name=…)` rows on every matched trigger; `dry_run=True` is hardcoded (env-independent) and `trading_paused` early-exits the strategy path identically to live trades.
4. **Stretch system decommissioned** — `WHAT_IF_STRATEGIES` and `_evaluate_what_if_strategies` removed; `stretch_opportunities` table renamed (not dropped) for rollback safety; `/api/sport-stats` rerouted to `opportunities`.
5. **Settlement reconciliation symmetry** — Both REST poller (`check_settlements`) and WS handler (`on_lifecycle`) use byte-identical composite filter `dry_run=False OR (dry_run=True AND strategy_name IS NOT NULL)`; both write `settled_at` (CR-01 fix during Phase 04 verification).
6. **Per-strategy analytics dashboard** — New `/analytics` page (auth-gated) with strategy selector, stat cards, recharts cumulative P&L curve, trade log, 5-min auto-refresh.

### Git Range

`9ac8bb9` (v1.1 close) → `1d18332` (HEAD at archive)
- 120 commits over 10 days (2026-04-29 → 2026-05-08)
- 17 `feat(...)` commits
- 122 files changed, 30,404 insertions, 5,289 deletions (insertion count dominated by season JSON fixtures committed during Phase 02 BT-07 work)

### Tech Debt at Close

- WR-01: redundant `or_` clause in settlement filter — dead code, not broken (track for v1.3+ cleanup)
- WR-02: `open_trades` brittle if non-dry-run strategy attribution lands later
- WR-03: `/api/strategies-summary` orphan ordering non-deterministic
- WR-04: analytics popstate listener missing — **deferred to ROADMAP backlog Phase 999.1**
- Concern: `connect_args timeout=5` is the only buffer against `SQLITE_BUSY` under analytics polling. If pressure increases, switch to WAL or move analytics to a read replica.

### Archive

- `.planning/milestones/v1.2-ROADMAP.md`
- `.planning/milestones/v1.2-REQUIREMENTS.md`
- `.planning/milestones/v1.2-MILESTONE-AUDIT.md`
- `.planning/milestones/v1.2-phases/` (full phase artifacts: PLANS, SUMMARYs, VERIFICATIONs, UAT, REVIEWs, SECURITY)

---

## v1.1 — Local-JSON Backtest

**Shipped:** 2026-04-29
**Quick Tasks:** 4 | **Plans:** 4

### Delivered

Replaced the backtest dashboard's dependency on `/api/backtest/soccer` and Kalshi market prices with a fully self-contained, deterministic experience driven by pre-fetched season JSONs in `resources/`. Six leagues now selectable (EPL, LaLiga, Bundesliga, Ligue 1, Serie A, MLS). Capital simulation with compound bet sizing and configurable win yield gives realistic P&L projections with no network calls.

### Key Accomplishments

1. Created `seasons.ts` + `backtest.ts` — clean separation of data catalog from strategy engine; page.tsx reduced to pure UI wiring
2. Replaced API fetch + Kalshi-price bankroll chart with local JSON loader — backtest is now deterministic and works offline
3. Added capital simulation: initial capital, compound bet sizing, final capital + gain analytics
4. Promoted `WIN_YIELD` to configurable `avgWinYield` parameter — enables scenario analysis
5. Extended `FILENAME_RE` for calendar-year league filenames; corrected `LEAGUE_NAMES` keys; wired all 6 season JSONs

### Git Range

`9ac8bb9` (GSD bootstrap) → `a6cb9df` (last commit before milestone close)

### Tech Debt at Close

- Hand-maintained `IMPORTS` array in `seasons.ts` — editing required for each new season
- `simulateMatch` kept as back-compat shim wrapping `detectFire`
- No fee or partial-fill modeling in backtest engine
- Pre-existing `pnpm fmt:check` failures in `app/page.tsx`, `app/actions.ts`, `app/api/[...path]/route.ts`, `sst-env.d.ts` (predates milestone)

### Archive

- `.planning/milestones/v1.1-ROADMAP.md`
- `.planning/milestones/v1.1-REQUIREMENTS.md`
- `.planning/milestones/v1.1-MILESTONE-AUDIT.md`

---

## v1.0 — Production Scanner

**Shipped:** pre-GSD (before scaffolding existed)

See `PROJECT.md` Validated section for the full requirement list (SCAN-*, CFG-*, DASH-*, CLI-*, BT-*, INFRA-*).

No per-phase GSD artifacts exist for v1.0. Architecture and stack are documented in `.planning/codebase/`.
