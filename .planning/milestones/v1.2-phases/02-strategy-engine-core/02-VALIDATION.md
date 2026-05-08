---
phase: 2
slug: strategy-engine-core
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-30
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (Python) + manual UI dogfood (TypeScript — no jest/vitest configured) |
| **Config file** | `pyproject.toml` (pytest section); `tests/conftest.py` (fixtures) |
| **Quick run command** | `uv run pytest tests/test_strategies.py tests/test_strategies_api.py -x` |
| **Full suite command** | `uv run pytest tests/ && (cd dashboard && pnpm build && pnpm fmt:check && pnpm lint)` |
| **Estimated runtime** | ~30-45 seconds (pytest) + ~15s (dashboard build) |

---

## Sampling Rate

- **After every task commit:** Run `uv run ruff check . && uv run ty check && uv run pytest tests/test_strategies.py tests/test_strategies_api.py -x` (Python tasks)
- **After every dashboard task:** Run `(cd dashboard && pnpm fmt:check && pnpm lint && pnpm build)`
- **After every plan wave:** Run full suite command above
- **Before `/gsd-verify-work`:** Full suite must be green; manual UI dogfood checklist completed
- **Max feedback latency:** ~45 seconds for Python; ~20 seconds for TypeScript

---

## Per-Task Verification Map

> Filled in during PLAN.md generation; planner inserts each task with `<automated>` block referencing the row here.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 02-00-01 | 00 | 0 | STR-01 (deps) | — | PyYAML installed | smoke | `uv run python -c "import yaml; assert yaml.__version__"` | ❌ W0 | ⬜ pending |
| 02-01-01 | 01 | 1 | STR-01 | — | Empty file rejected → empty list | unit | `uv run pytest tests/test_strategies.py::test_load_empty_file -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | STR-02 | — | `extra="forbid"` + `min_length=1` | unit | `uv run pytest tests/test_strategies.py::test_unknown_field_rejected -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | STR-02 | — | All-or-nothing rejection | unit | `uv run pytest tests/test_strategies.py::test_one_bad_strategy_rejects_file -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 1 | STR-01 | — | `STRATEGIES_PATH` env override | unit | `uv run pytest tests/test_strategies.py::test_strategies_path_env -x` | ❌ W0 | ⬜ pending |
| 02-02-01 | 02 | 1 | STR-03 | T-02-01 (auth) | Bearer auth on `GET /api/strategies` | unit | `uv run pytest tests/test_strategies_api.py::test_endpoint_requires_auth -x` | ❌ W0 | ⬜ pending |
| 02-02-02 | 02 | 1 | STR-03 | — | Response shape `{strategies: [...]}` | unit | `uv run pytest tests/test_strategies_api.py::test_endpoint_response_shape -x` | ❌ W0 | ⬜ pending |
| 02-02-03 | 02 | 1 | STR-03 | — | Insertion order preserved | unit | `uv run pytest tests/test_strategies_api.py::test_endpoint_preserves_yaml_order -x` | ❌ W0 | ⬜ pending |
| 02-03-01 | 03 | 2 | BT-07 | — | Multi-trigger OR-of-AND, first-fire-wins | unit | `pnpm --filter dashboard build` (type-check covers `runBacktest` shape) | ❌ W0 | ⬜ pending |
| 02-03-02 | 03 | 2 | BT-07 | — | Sport-mismatched triggers silently skipped | manual | UI: load EPL season, set basketball trigger, observe gray card + zero fires | ✅ | ⬜ pending |
| 02-04-01 | 04 | 2 | BT-07 | — | Strategy dropdown populated from `/api/strategies` | manual | UI: dashboard loads, dropdown contains YAML strategies + "— Custom —" sentinel | ✅ | ⬜ pending |
| 02-04-02 | 04 | 2 | BT-07 | — | Auto-snap to "— Custom —" on edit | manual | UI: select preset, drag any slider, dropdown returns to "— Custom —" | ✅ | ⬜ pending |
| 02-04-03 | 04 | 2 | BT-07 | — | (+) clones last trigger; (-) hidden when only 1 trigger | manual | UI: click +; new card appears with copied values; click -; native window.confirm | ✅ | ⬜ pending |
| 02-05-01 | 05 | 3 | STR-01..03, BT-07 | — | Full pipeline green | smoke | `uv run pytest tests/ && cd dashboard && pnpm build` | ✅ | ⬜ pending |

> Planner replaces this exemplar table during PLAN.md generation.
> Each row maps 1:1 to a task `<automated>` or `<manual>` block.

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyproject.toml` — add `pyyaml>=6.0` to dependencies (`uv add pyyaml`)
- [ ] `tests/test_strategies.py` — pytest stubs for STR-01, STR-02 (one stub per row in the per-task table)
- [ ] `tests/test_strategies_api.py` — pytest stubs for STR-03 using TestClient + monkeypatch API_TOKEN
- [ ] `tests/fixtures/strategies-good.yaml`, `strategies-empty.yaml`, `strategies-malformed.yaml`, `strategies-unknown-field.yaml` — fixture files (planner judgment: tmp_path inline vs checked-in fixtures; researcher recommends checked-in for reuse)
- [ ] `strategies.yaml` (repo root) — minimal valid file so dashboard dev server has data to render

*If a planner-recommended dependency exception is taken (PyYAML), it must be flagged as a `[BLOCKING]` Wave 0 task and committed before any Wave 1 work begins.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Strategy dropdown populated and "— Custom —" present | BT-07 | UI render check; no JSDOM tests in repo | Run `pnpm dev:dashboard`, open backtest page, verify dropdown shows YAML strategies + "— Custom —" |
| Auto-snap to "— Custom —" on slider edit | BT-07 | Requires real React event loop | Select preset, drag min_minute slider, observe dropdown auto-changes to "— Custom —" |
| (+)/(-) trigger group buttons | BT-07 | Visual + interactive | Click (+); copy of last group appears. Click (-); native window.confirm. Click cancel; no change. Click OK; group removed. |
| Sport-mismatched triggers grayed with tooltip | BT-07, D-15 | CSS state + hover tooltip | Load EPL season; create trigger with `sport: basketball/nba`; verify card grayed + tooltip "Skipped — no basketball/nba data loaded" |
| `min_yes_price` / `max_yes_price` rendered as info text | BT-07, D-11 | Visual confirmation that they are NOT sliders | Verify each trigger card shows "Live trading: 92¢–99¢" as static text, no slider control |
| "N of M triggers skipped" muted line | BT-07, D-18 | Conditional render under summary cards | Load season; set 2 triggers, one mismatched; run backtest; verify "1 of 2 triggers skipped: basketball/nba" line appears |
| `STRATEGIES_PATH` env override works in dev | STR-01, D-08 | Process-level env override | Run `STRATEGIES_PATH=/tmp/alt.yaml pnpm dev:api`, hit `/api/strategies`, verify alt content returned |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies — *planner fills in*
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify — *checker validates*
- [ ] Wave 0 covers all MISSING references (PyYAML dep, test fixture files, test stubs) — *planner verifies*
- [ ] No watch-mode flags (no `--watch`, `--ui`, etc. — only one-shot commands) — *checker validates*
- [ ] Feedback latency < 60s — *measured during execution*
- [ ] `nyquist_compliant: true` set in frontmatter — *flipped after first wave passes*

**Approval:** pending
