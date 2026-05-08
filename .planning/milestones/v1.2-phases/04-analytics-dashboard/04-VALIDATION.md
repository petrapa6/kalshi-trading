---
phase: 04
slug: analytics-dashboard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-06
---

# Phase 04 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 8.0 + pytest-asyncio 0.24 (`asyncio_mode = "auto"`); dashboard build gate as type-checking proxy |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]`; `dashboard/oxfmt.json` for formatting |
| **Quick run command** | `uv run pytest tests/test_strategy_analytics.py -x` |
| **Full suite command** | `uv run pytest tests/ && (cd dashboard && pnpm lint && pnpm fmt:check && pnpm build)` |
| **Estimated runtime** | ~30s (pytest) + ~25s (dashboard build) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/test_strategy_analytics.py -x` (≤5s)
- **After every plan wave:** Run full suite (`pytest tests/ && pnpm lint && pnpm fmt:check && pnpm build`)
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds (pytest); 60 seconds (full suite)

---

## Per-Task Verification Map

> Populated from `04-RESEARCH.md § Validation Architecture`. Task IDs added by planner; resolve `XX-YY` placeholders in the table below as plans are written.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 04-W0-A | TBD | 0 | DASH-03 | T-04-01 | Bearer-required endpoint; SQLAlchemy parameterized query | scaffold | `uv run pytest tests/test_strategy_analytics.py -x` | ❌ W0 | ⬜ pending |
| 04-W1-A | TBD | 1 | DASH-03 | — | Returns correct stats for strategy with settled trades | integration | `uv run pytest tests/test_strategy_analytics.py::test_analytics_returns_correct_stats -x` | ❌ W0 | ⬜ pending |
| 04-W1-B | TBD | 1 | DASH-03 | — | pnl_curve is correct running sum on settled trades | integration | `uv run pytest tests/test_strategy_analytics.py::test_analytics_pnl_curve_running_sum -x` | ❌ W0 | ⬜ pending |
| 04-W1-C | TBD | 1 | DASH-03 | — | Zero-trade strategy returns zeroed stats + empty pnl_curve | integration | `uv run pytest tests/test_strategy_analytics.py::test_analytics_zero_trade_strategy -x` | ❌ W0 | ⬜ pending |
| 04-W1-D | TBD | 1 | DASH-03 | — | `/api/strategies-summary` includes zero-trade strategies from YAML | integration | `uv run pytest tests/test_strategy_analytics.py::test_summary_includes_zero_trade_strategies -x` | ❌ W0 | ⬜ pending |
| 04-W1-E | TBD | 1 | DASH-03 | — | `/api/strategies-summary` aggregation is correct (totals/wins/losses/pnl) | integration | `uv run pytest tests/test_strategy_analytics.py::test_summary_aggregation -x` | ❌ W0 | ⬜ pending |
| 04-W1-F | TBD | 1 | DASH-03 | T-04-02 | Both endpoints reject unauthenticated requests with 401 | integration | `uv run pytest tests/test_strategy_analytics.py::test_endpoints_require_auth -x` | ❌ W0 | ⬜ pending |
| 04-W1-G | TBD | 1 | DASH-03 | — | Phase 03 D-16 composite filter excludes legacy trades (strategy_name IS NULL) symmetrically | integration | `uv run pytest tests/test_strategy_analytics.py::test_composite_filter_excludes_legacy_trades -x` | ❌ W0 | ⬜ pending |
| 04-W2-A | TBD | 2 | DASH-03 | — | Analytics page builds without SSR errors | build gate | `cd dashboard && pnpm build` | ❌ W0 | ⬜ pending |
| 04-W2-B | TBD | 2 | DASH-03 | — | `Trade.strategy_name` field is present in TS Trade interface + API JSON shape | grep + integration | `grep -n 'strategy_name' dashboard/app/page.tsx && grep -n 'strategy_name' src/predictions/api.py` | ❌ W0 | ⬜ pending |
| 04-W3-A | TBD | 3 | DASH-04 | — | 5-minute auto-refresh setInterval present on analytics page | grep | `grep -n '5 \* 60 \* 1000\|300000' dashboard/app/analytics/page.tsx` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_strategy_analytics.py` — xfail-marked stubs for all 7 DASH-03 backend test functions listed above (`test_analytics_returns_correct_stats`, `test_analytics_pnl_curve_running_sum`, `test_analytics_zero_trade_strategy`, `test_summary_includes_zero_trade_strategies`, `test_summary_aggregation`, `test_endpoints_require_auth`, `test_composite_filter_excludes_legacy_trades`)
- [ ] `tests/conftest.py` — extend `isolated_db` fixture (already present) with a helper that seeds multi-strategy `Trade` rows across `settled_win`, `settled_loss`, and `dry_run` statuses
- [ ] No framework install needed — pytest, pytest-asyncio, and FastAPI TestClient pattern already established

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Auto-refresh cadence (5 min) actually fires in browser | DASH-04 | Cannot unit-test setInterval cadence without time mocking; the visual confirmation is part of UAT | Load `/analytics?strategy=<name>`, observe Last-Updated indicator (or insert `console.log` in the fetcher), wait 5 minutes, confirm a new fetch fires and chart/cards refresh |
| recharts `<ResponsiveContainer>` does not collapse to 0px height | DASH-03 (criterion 1) | Visual regression — pure JSX rendering doesn't catch layout collapse | Load `/analytics?strategy=<name>` with at least 2 settled trades; confirm P&L chart renders with non-zero height |
| Cross-links from main dashboard to `/analytics?strategy=…` work | D-02 (CONTEXT.md) | Click-through behavior is interactive | Click any strategy name in the trades table on `/`; confirm navigation to `/analytics?strategy=<name>` and that strategy is preselected |
| Header "Analytics" link visible alongside Backtest | D-03 (CONTEXT.md) | Visual placement | Load `/`; confirm "Analytics" link is present in same nav row as "Backtest" |
| Empty-state UX (zero-trade strategy) | Success criterion 4 | Visual layout review | Select a YAML-defined strategy with zero trades; confirm empty chart axes render, stat cards show 0, trade log table body is empty (no copy) |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references (`test_strategy_analytics.py`)
- [ ] No watch-mode flags (only `-x` for fail-fast)
- [ ] Feedback latency < 30s for quick run; < 60s for full suite
- [ ] `nyquist_compliant: true` set in frontmatter (after Wave 0 implements stubs)

**Approval:** pending
