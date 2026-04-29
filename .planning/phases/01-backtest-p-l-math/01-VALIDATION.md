---
phase: 1
slug: backtest-p-l-math
status: draft
nyquist_compliant: false
wave_0_complete: true
created: 2026-04-29
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | None (no JS test infra in repo — by design, see RESEARCH § Discretion #4) |
| **Config file** | none — Wave 0 not required |
| **Quick run command** | `cd dashboard && pnpm fmt:check && pnpm lint && pnpm build` |
| **Full suite command** | `cd dashboard && pnpm fmt:check && pnpm lint && pnpm build` (same — no separate test step) |
| **Estimated runtime** | ~30 seconds (build dominates) |

---

## Sampling Rate

- **After every task commit:** Run `cd dashboard && pnpm fmt:check && pnpm lint && pnpm build`
- **After every plan wave:** Same command (no separate full suite for this phase)
- **Before `/gsd-verify-work`:** Build green AND manual seams 2–5 verified in browser
- **Max feedback latency:** ~30 seconds

---

## Per-Task Verification Map

> Task IDs `01-NN` are placeholders — the planner assigns real IDs in `01-PLAN.md`. Each plan task should reference the row whose `Test Type` and `Automated Command` it satisfies.

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 01-XX | 01 | 1 | BT-06 | — | N/A (client-side math, no boundary crossed) | smoke (typecheck via `next build`) | `cd dashboard && pnpm build` | ✅ | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 | — | N/A | static (lint, no unused-vars on removed ids) | `cd dashboard && pnpm lint` | ✅ | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 | — | N/A | static (format) | `cd dashboard && pnpm fmt:check` | ✅ | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 (D-16) | — | N/A | static (grep) | `! grep -E 'simulateMatch\|DEFAULT_WIN_YIELD' dashboard/app/backtest/backtest.ts` | ✅ | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 (D-16) | — | N/A | static (grep) | `! grep -E 'avgWinYield\|avg_win_yield' dashboard/app/backtest/page.tsx` | ✅ | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 (D-06) | — | N/A | static (grep) | `grep -F 'a contract_price input (default 97, range 50–99 cents)' .planning/ROADMAP.md` | ✅ | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 (worked example) | — | N/A | manual | Open page, set `initial_capital=1000`, `bet_fraction=0.02`, `contract_price_cents=97`, find a winning trade, verify row reads `"20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"` | manual | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 (D-17) | — | N/A | manual | Open page, set `initial_capital=1`, `bet_fraction=0.5`, `contract_price_cents=97`, verify a zero-contract row appears with capital unchanged | manual | ⬜ pending |
| 01-XX | 01 | 1 | BT-06 (capital conservation) | — | N/A | manual | DevTools: `result.trades.reduce((s,t)=>s+t.pnl_cents,0) === result.summary.final_capital_cents - result.summary.initial_capital_cents` | manual | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*None — existing `pnpm fmt:check && pnpm lint && pnpm build` infrastructure covers all phase requirements. No Vitest install (see RESEARCH § Discretion #4: criterion #1 explicitly says "manual calculation").*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Worked example matches output | BT-06 (criterion #1) | No JS test infra in repo; ROADMAP criterion explicitly says "manual calculation" | `pnpm dev:dashboard` → /backtest → set 1000 EUR / 2% / 97¢ → find any winning trade → row text MUST match `"20 contracts @ 97¢ · €19.40 cost · +€0.60 · capital €1000.60"` |
| Zero-contract row appears | BT-06 (D-17) | Same | `pnpm dev:dashboard` → /backtest → set `initial_capital=1`, `bet_fraction=0.5`, `contract_price_cents=97` → verify a row with `0 contracts` appears with capital unchanged |
| Capital conservation Σpnl=Δcapital | BT-06 | Sum check requires runtime introspection | DevTools console: paste the reduce expression above, expect `true` |
| No negative capital | BT-06 (D-04 + D-17 invariant) | Inspect across many runs | Browse the trade list visually; `capital_after_cents < 0` should never appear. If it does, math is wrong. |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or are flagged manual in the table above
- [ ] Sampling continuity: build runs after every task commit (single-plan phase, trivially satisfied)
- [ ] Wave 0 covers all MISSING references (N/A — no MISSING; existing build/lint/fmt is sufficient)
- [ ] No watch-mode flags (using `next build`, not `next dev`)
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter (set after planner emits 01-PLAN.md and the per-task IDs replace the `01-XX` placeholders above)

**Approval:** pending
