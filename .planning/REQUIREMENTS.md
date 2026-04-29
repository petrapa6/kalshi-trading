# Requirements: Kalshi Trading Scanner

**Defined:** 2026-04-29 (inline bootstrap from existing codebase + active milestone scope)
**Core Value:** Capture the lag between actual game state and Kalshi's market re-pricing.

## v1 Requirements (Validated — already shipped)

See `PROJECT.md` Validated section. These requirements are tracked there with `✓` markers and are sourced from `.planning/codebase/` documents (last mapped on commit `f2c2f78`).

| REQ-ID | Description | Source |
|--------|-------------|--------|
| SCAN-01..04 | Scanner loops, betting filters, settlement duality, WHAT_IF strategies | `codebase/ARCHITECTURE.md` |
| CFG-01..02 | Runtime config from SQLite, kill switch | `codebase/STACK.md` |
| DASH-01..02 | Dashboard read-only views + auth gate | `codebase/INTEGRATIONS.md` |
| CLI-01 | React-ink CLI | `codebase/STRUCTURE.md` |
| BT-01..02 | Soccer backtest endpoint + dashboard page | `dashboard/app/backtest/page.tsx`, `src/predictions/backtest.py` |
| INFRA-01..02 | SST deploy + S3 snapshot durability | `codebase/STACK.md`, `sst.config.ts` |

## Active Milestone Requirements (v1.1 — Soccer Backtest Local-JSON)

### Backtest Dashboard

- [ ] **BT-03**: The backtest page enumerates JSON files under `resources/`, parses league + season from each filename, and uses those parsed values to populate a selector
- [ ] **BT-04**: User picks a `(league, season)` combination via a dropdown; selection drives which dataset is rendered
- [ ] **BT-05**: Strategy config (form controls), summary stats, trade list, and any retained graphs are computed purely from the selected JSON; the `/api/backtest/soccer` fetch path and the Kalshi-price-based bankroll chart are removed from the page

## Future Requirements

Deferred — not in scope for this milestone.

| REQ-ID | Description | Why deferred |
|--------|-------------|--------------|
| BT-06 | Add fetch-season UI flow inside the dashboard | The `fetch-football-season` skill is operator-driven for now |
| BT-07 | Multi-league comparison view (overlay several seasons on one chart) | Single-season MVP first |

## Out of Scope

| Feature | Reason |
|---------|--------|
| Live trading behaviour changes | Frontend-only milestone |
| Removal of `/api/backtest/soccer` endpoint | May still be invoked from scripts/CLI; only dashboard wiring is removed |
| Schema validation library for JSON inputs | Files are produced by our own skill — type assertion at the read site is sufficient |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| BT-03 | quick: Local-JSON Backtest | Pending |
| BT-04 | quick: Local-JSON Backtest | Pending |
| BT-05 | quick: Local-JSON Backtest | Pending |

**Coverage:**
- Active v1.1 requirements: 3 total
- Mapped: 3
- Unmapped: 0 ✓

---
*Requirements defined: 2026-04-29*
*Last updated: 2026-04-29 after inline bootstrap*
