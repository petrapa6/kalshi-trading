# Retrospective

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
