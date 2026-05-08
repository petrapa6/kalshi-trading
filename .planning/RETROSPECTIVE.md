# Retrospective

## Milestone: v1.2 — Strategy Engine

**Shipped:** 2026-05-08
**Phases:** 4 | **Plans:** 17 | **Duration:** 10 days (2026-04-29 → 2026-05-08)

### What Was Built

- File-driven strategy engine: `strategies.yaml` with multi-trigger OR-of-AND conditions; single `load_strategies()` source of truth across backtest + live scanner
- Contract-based backtest math (replaces `avg_win_yield`)
- Live scanner dry-run trading with hardcoded `dry_run=True` (env-independent) and `trading_paused` early-exit symmetry with live trades
- Per-strategy `/analytics` dashboard page with auth gate, recharts cumulative P&L curve, stat cards, trade log, 5-min auto-refresh
- Settlement reconciliation symmetry: byte-identical composite filter on REST + WS settlement paths, both writing `settled_at` (CR-01 fix)
- Stretch system decommissioned: `WHAT_IF_STRATEGIES`/`_evaluate_what_if_strategies` removed; `stretch_opportunities` renamed (not dropped) for rollback safety

### What Worked

- **Single-boundary discipline** — every load-bearing invariant (YAML read, `dry_run=True`, settlement filter) lives at exactly one site, mirroring the existing `extract_cents` pattern from `kalshi_client.py`. Made code review and security audit straightforward.
- **Wave-based execution per phase** — Phase 02/03/04 each followed Wave 0 (test scaffolding with xfail stubs) → Wave 1 (schema/loader) → Wave 2 (logic) → Wave 3 (integration). The xfail stubs gave Wave 1+ plans green-feedback test infrastructure already in place.
- **Phase 04 catching CR-01 in verification** — Phase 03 added the `settled_at` column but never wrote it; Phase 04's verification surfaced the empty-chart symptom and the gap was atomically closed (writer + idempotent backfill + tests) in the same session. Cross-phase verification working as designed.
- **Composite settlement filter symmetry (D-16)** — both settlement paths use byte-identical filter; the symmetric mirror on the analytics read path (`api.py:438-441`) means schema evolution shifts both ends together.
- **Documented intentional deviations** — STR-04 RENAME-not-DROP and D-09 chart-axis settled_at were both deliberate departures from REQUIREMENTS, captured in the decision log + audit's `intentional_deviations` field. Future maintainers reading the artifact see "satisfied via deviation" not "gap."

### What Was Inefficient

- **REQUIREMENTS.md checkbox drift** — same pattern as v1.1: 6 boxes for shipped requirements (BT-06, STR-04, DRY-01, DRY-02, DASH-03, DASH-04) were never updated during execution. Audit had to reconcile via 3-source cross-reference.
- **Phase 03 missing VERIFICATION.md** — work shipped 2026-05-05 but the formal verification artifact was never produced. Backfilled retroactively during the v1.2 audit. The phase-execute workflow didn't enforce "verification artifact exists" as a gate.
- **SUMMARY.md `requirements-completed` frontmatter inconsistency** — Phase 01 + 02 + 04 plans had it; Phase 03 plans didn't. Added work for the audit to map work-shipped → REQ-IDs from body content rather than frontmatter.
- **D-02 sport-field override mid-Phase-2** — original plan had `trigger.sport` as ESPN sport_path; revised to sport-family literal mid-phase. Phase 3 had to read the addendum, not the original D-02. Mid-phase pivots survive the artifact but cost reading-time.

### Patterns Established

- **Hardcoded invariants over env-conditional behavior** (D-13 pattern): when an invariant is structurally important, hardcode it at the call site rather than reading config/env. Makes it structurally impossible to violate even if the env var is flipped accidentally.
- **RENAME-not-DROP for schema deprecation** (STR-04 / D-03): on production data, prefer rename (idempotent + reversible) over drop (data loss). Test against S3 backup first. Delete the ORM class so fresh DBs don't recreate the table.
- **Composite filter symmetry** (D-16 pattern): when a read path mirrors a write path, express the filter byte-identically in both — schema evolution shifts both ends together.
- **`connect_args timeout=5` for SQLite under polling pressure** (D-02): pre-emptive 5-second buffer when concurrent readers are added; revisit only if pressure exceeds it.
- **Three-source requirement cross-reference at audit time** — REQUIREMENTS.md checkbox + VERIFICATION.md status + SUMMARY frontmatter. When one is stale, the other two substantiate. The 3-source pattern is what made retroactive Phase 03 verification safe.

### Key Lessons

- **Mark REQUIREMENTS.md `[x]` during phase execution, not at milestone close.** Same lesson as v1.1; recurring pattern. Worth a hook or a phase-execute step.
- **Enforce VERIFICATION.md as a gate before phase is marked complete.** Phase 03's missing artifact wasn't caught until the v1.2 audit. The phase-transition workflow should refuse to advance without it.
- **`SUMMARY.md` `requirements-completed` frontmatter is cheap insurance** — when consistently present, it makes audits mostly mechanical. When inconsistent (Phase 03), audits do extra work mapping body content to REQ-IDs.
- **Verification re-runs are valuable.** Phase 04's first verification was `gaps_found` (6/8) — CR-01 fix shipped immediately, re-verification flipped to `complete` (8/8). The re-run pattern is what kept the milestone close-able.
- **Skip a git tag if release tags don't correlate to deployments.** This project doesn't gate deploys on tags; the milestone audit + archive + MILESTONES.md entry are the canonical cut markers. Re-evaluate if release tagging starts driving deployment.

### Cost Observations

- Sessions: ~5 (per-phase) + 1 (milestone close)
- Notable: 30,404 LOC insertions but the bulk is season JSON fixtures (BT-07 needed live data to test against). Pure code delta is much smaller.
- Test suite stayed fast: 88 tests, ~1.1s wall.

---

## Milestone: v1.1 — Local-JSON Backtest

**Shipped:** 2026-04-29
**Quick Tasks:** 4 | **Plans:** 4 | **Duration:** 1 session (~single day)

### What Was Built

- Self-contained backtest page driven entirely by pre-fetched season JSONs — no network calls, no Kalshi price dependency
- `seasons.ts` static import catalog + `backtest.ts` pure strategy engine (clean separation of data from logic)
- Capital simulation with compound bet sizing; configurable `avgWinYield` parameter
- 6 leagues selectable: EPL, LaLiga, Bundesliga, Ligue 1, Serie A, MLS

### What Worked

- **Quick tasks over formal phases** — scope was tightly contained to `dashboard/app/backtest/`; the quick task format matched the actual effort size. No overhead from multi-step planning.
- **Audit before close** — running `/gsd-audit-milestone` before completion caught the `seasons.ts` FILENAME_RE gap and corrected `LEAGUE_NAMES` keys before they became tech debt.
- **Static imports decision** — the `import.meta.glob` dead-end was caught early (it silently returns `{}` in Next.js 16 production builds); the static-import fallback was correct and documented.

### What Was Inefficient

- REQUIREMENTS.md traceability table was never updated to `[x]` during execution — had to be corrected at milestone close. The quick-task format doesn't have a natural "mark requirements complete" step.
- `260429-k6u` committed the LaLiga wiring before the 3 other JSONs (from chore `4608cf3`) were added to the catalog — required a follow-on fix. Could have been done in one pass.

### Patterns Established

- **Quick task format** suits contained, sub-day dashboard work in this repo. Formal phase planning adds overhead that isn't justified for single-file refactors.
- **Static import catalog** (`IMPORTS` array in `seasons.ts`) is the established pattern for adding new seasons. The TODO comment in `seasons.ts` is the canonical reminder.
- **`pnpm exec oxfmt <specific files>`** vs `pnpm fmt:check` — running the formatter on specific files avoids false-positive pre-existing failures in unrelated files (`app/page.tsx`, `actions.ts`, etc.).

### Key Lessons

- When executing quick tasks, mark REQUIREMENTS.md traceability rows complete during execution, not at milestone close.
- Batch related file additions (all new season JSONs) into the same task/commit rather than adding one per task.
- The `FILENAME_RE` and `LEAGUE_NAMES` correction pattern will recur every time a new league format is added — automate or document a checklist.

### Cost Observations

- Sessions: 1 (all 4 tasks in one session)
- Notable: extremely tight scope made this the fastest GSD milestone to date

---

## Cross-Milestone Trends

| Milestone | Tasks/Phases | Duration | Tech debt incurred |
|-----------|-------------|----------|-------------------|
| v1.0 | pre-GSD | n/a | `page.tsx` 102 KB monolith; `pnpm fmt:check` failures |
| v1.1 | 4 quick tasks | 1 session | Hand-maintained import catalog; no fee modeling; `simulateMatch` shim |
| v1.2 | 4 phases / 17 plans | 10 days | 4 advisories (WR-01..WR-04); 1 backlog item (Phase 999.1 popstate); SQLite WAL mode pending if polling pressure grows |
