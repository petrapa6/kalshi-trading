---
phase: 01
slug: backtest-p-l-math
status: verified
threats_open: 0
asvs_level: 1
created: 2026-04-30
verified: 2026-04-30
verifier: orchestrator (no auditor agent — threat register empty in PLAN, retroactive STRIDE pass done inline)
---

# Phase 01 — Security

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Phase 01 (Backtest P&L Math + tri-state UI) shipped pure client-side compute
> with no new server, network, auth, or persistence surfaces. STRIDE-classified
> threat register is empty by construction. Documented here so the next-milestone
> audit can confirm the assessment rather than re-derive it.

---

## Scope of This Phase

Files modified by Phase 01 (commits `a0281bc`, `eb26e23`, `3494f7e`, `20653ec`, `0277022`, `e7948e3`):

- `dashboard/app/backtest/backtest.ts` — pure functions: `runBacktest()`, `detectFire()`. Integer-cents arithmetic. No I/O. No imports beyond `./seasons` (static JSON loader).
- `dashboard/app/backtest/page.tsx` — React component with bounded numeric sliders (`initial_capital`, `bet_size`, `contract_price_cents`, `min_minute`, `min_lead`) and a season selector (enum). Renders a trade list and summary cards. No `fetch`/`POST`, no `useEffect` with side effects, no localStorage writes.
- `dashboard/app/backtest/seasons.ts` — already existed; loads `*.json` from the static `/seasons/` directory at build time.
- Doc-only: `.planning/ROADMAP.md`, `.planning/phases/01-*/...`.

Not modified by this phase: any auth code, any API route under `dashboard/app/api/`, any backend code under `src/predictions/`, any DB migration, any `.env`/secrets file, any `Dockerfile`/`sst.config.ts`.

---

## Trust Boundaries

| Boundary | Description | Data Crossing | New in Phase 01? |
|----------|-------------|---------------|------------------|
| Build → Browser | Static `*.json` season files bundled into the Next.js build, fetched by the client | Public-domain match results (date, teams, scores, kickoff minute) — no PII, no secrets | No (already crossed pre-phase) |
| Browser ↔ Browser memory | User adjusts sliders; React state recomputes `runBacktest()` results in-process | User-controlled numeric inputs only; output is rendered to the same user's DOM | No (slider sliders bounded; existing input pattern) |
| Server ↔ Browser (auth gate) | Phase did **not** modify the existing `checkAuth()` server-action gate on `/backtest` | (unchanged) | No |

**No new trust boundaries crossed.**

---

## STRIDE Pass (retroactive, done inline by orchestrator)

| ID | STRIDE | Component | Disposition | Rationale | Status |
|----|--------|-----------|-------------|-----------|--------|
| T-01-01 | Spoofing | client-side `BacktestPage` | N/A | No auth boundary in scope. The existing `checkAuth()` gate guarding `/backtest` was untouched by this phase. | closed (out of scope) |
| T-01-02 | Tampering | `runBacktest()` inputs (sliders, season JSON) | accept | Inputs are user-controlled and outputs render only to the same user's browser. A user "tampering" with their own backtest harms only their own simulation; no server trust boundary crossed. Slider bounds prevent integer overflow at the math kernel: `initial_capital ≤ Number.MAX_SAFE_INTEGER / 100`, `contract_price_cents ∈ [50, 99]`, `bet_fraction ∈ [0, 1]`. | closed (accepted risk — self-only impact) |
| T-01-03 | Repudiation | n/a | N/A | No action is logged or audited; no claim of "X happened" needs non-repudiation. | closed (out of scope) |
| T-01-04 | Information Disclosure | season JSON files | N/A | Season data is public-domain match results scraped from public sources (already shipped pre-phase). No PII, no secrets, no rate-limited keys. | closed (out of scope) |
| T-01-05 | Denial of Service | `runBacktest()` compute loop | accept | Pure client-side compute, bounded by season size (~380 matches) and a single linear pass. Worst-case latency on a user's own browser is sub-millisecond. A user who DoSes their own page harms only themselves. No DoS amplification path to other users or the server. | closed (accepted risk — self-only impact) |
| T-01-06 | Elevation of Privilege | n/a | N/A | No privilege boundary touched. The page reads its own bundled JSON; nothing it can do touches the user's session, the server's data, or another user's state. | closed (out of scope) |

**Threat surface assessment: empty.** Six STRIDE categories evaluated; all either out of scope (no relevant component touched by this phase) or accepted as self-only-impact risks intrinsic to a client-side simulator the user runs against their own data in their own browser.

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-01-T | T-01-02 (Tampering) | User can manipulate their own browser's backtest state. No cross-user or server impact possible. | Pavel Petracek | 2026-04-30 |
| AR-01-D | T-01-05 (DoS) | User can stall their own page with a pathological input. No amplification path. Compute is bounded by season size. | Pavel Petracek | 2026-04-30 |

---

## Things Worth Watching in Future Phases

These are **NOT** Phase 01 threats. Listed here so the next phase's threat-modeling step can pick them up if applicable:

- **Phase 2 (Strategy Engine Core)** introduces `strategies.yaml` parsing. YAML deserialization of a checked-in file is low-risk, but **STR-01** validation must reject empty trigger blocks — confirm the Pydantic `min_length=1` constraint lands. (Already a success criterion in `ROADMAP.md`.)
- **Phase 3 (Scanner Integration)** adds DB writes for dry-run trades (`Trade` rows with `dry_run=True`). The `trading_paused == "true"` kill-switch interaction with the new path is the obvious threat — STRIDE-T (tampering) on the kill switch must include the dry-run path.
- **Phase 4 (Analytics Dashboard)** adds new API endpoints and a new authenticated page. Standard auth/authz threat model needed at that point.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-04-30 | 6 | 6 | 0 | orchestrator (inline STRIDE pass; no auditor agent — empty threat register in PLAN justified skipping the auditor per `threats_open: 0` workflow rule) |

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer / N/A)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-04-30

---
*Phase 01 (backtest-p-l-math) — security verified. Threat surface for this phase is empty by construction (pure client-side compute, no new boundaries crossed). Phase 02 onward will need a real threat-modeling step at PLAN time.*
