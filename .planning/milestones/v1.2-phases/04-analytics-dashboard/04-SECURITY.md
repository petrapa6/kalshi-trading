---
phase: 04
slug: analytics-dashboard
status: verified
threats_total: 14
threats_closed: 14
threats_open: 0
asvs_level: 1
audited: 2026-05-08
audited_by: /gsd-secure-phase (retroactive)
---

# Phase 04 — Security (Analytics Dashboard)

> Per-phase security contract: threat register, accepted risks, and audit trail.
> Retroactive verification — phase already implemented and committed before audit.

---

## Trust Boundaries

| Boundary | Description | Data Crossing |
|----------|-------------|---------------|
| Browser → Next.js proxy (`/api/[...path]`) | Same-origin fetch from authed dashboard; proxy injects `Authorization: Bearer ${API_TOKEN}` | Strategy name (URL param), session cookie |
| Next.js proxy → FastAPI backend | Server-to-server with bearer token; gated by `checkAuth()` cookie check before forwarding | Strategy name, user identity (token = identity) |
| FastAPI → SQLite | SQLAlchemy ORM session, `connect_args` 5s timeout, `strategy_name` indexed (Phase 03 D-01) | Trade rows filtered by `strategy_name` + composite dry_run filter |
| Strategy name (user input) → SQL filter | Bound parameter via `Trade.strategy_name == strategy` | String, no length cap (input is small + indexed; DoS bounded by index + timeout) |

---

## Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Evidence | Status |
|-----------|----------|-----------|-------------|---------------------|--------|
| T-04-01 | Tampering (SQLi) | `GET /api/strategy-analytics?strategy=` | mitigate | `src/predictions/api.py:438` — `Trade.strategy_name == strategy` (ORM bound param). `grep -cF 'text(' src/predictions/api.py` = 1; the single match is pre-existing (`api.py:692`, `get_total_sport_stats`, no user input). No new raw-SQL strings introduced by this phase. | CLOSED |
| T-04-02 | Information Disclosure | unauthenticated read on new endpoints | mitigate | `src/predictions/api.py:421-425` (`/api/strategy-analytics`) and `:518-522` (`/api/strategies-summary`) both carry `dependencies=[Depends(_check_token)]` literally on the decorator block. | CLOSED |
| T-04-03 | Information Disclosure | legacy NULL-strategy rows leaking into per-strategy results | mitigate | `src/predictions/api.py:438-441`: `(Trade.strategy_name == strategy) & or_(Trade.dry_run == False, and_(Trade.dry_run == True, Trade.strategy_name.isnot(None)))`. Imports confirmed (`api.py:13`: `from sqlalchemy import and_, case, desc, func, or_`). Strategies-summary uses symmetric filter at `:537-540`. | CLOSED |
| T-04-04 | Denial of Service | unbounded result set on high-volume strategy | accept | Phase 03 D-01 `strategy_name` index + 5min client throttle + `connect_args timeout=5`; documented planned acceptance, no code change required. | CLOSED (accepted) |
| T-04-05 | Repudiation | analytics surface mutating trade records | accept | Both endpoints are GET-only and contain no `session.add` / `session.commit` / `update` / `delete` calls — verified by reading the implementation (`api.py:421-515`, `:518-595`). | CLOSED (accepted) |
| T-04-W0-01 | (Wave 0 test scaffolding) | tests | accept | No production code in Wave 0; planned acceptance. | CLOSED (accepted) |
| T-04-W0-02 | (Wave 0 test scaffolding) | tests | accept | No production code in Wave 0; planned acceptance. | CLOSED (accepted) |
| T-04-W2-01 | XSS (URL param → DOM) | `/analytics?strategy=` | mitigate | `dashboard/app/analytics/page.tsx:142-146` reads param into React state via `URLSearchParams`. Used at `:165` only as `encodeURIComponent(selected)` in `fetch()`. Never rendered as raw HTML; only ever a JSX child (`{selected}` at `:239`). `grep dangerouslySetInnerHTML dashboard/app/analytics/page.tsx` = 0 matches. | CLOSED |
| T-04-W2-02 | Auth bypass (data fetched before auth check) | `AnalyticsPage` useEffect | mitigate | `page.tsx:132-137` — `checkAuth()` runs in mount useEffect; on failure → `window.location.href = "/"`. The data-fetch useEffect at `:155-157` opens with `if (!authed) return;` before any `fetch(`. `authed` initial state is `null` (false-y), so the guard holds during the auth round-trip. Render guard at `:199` returns blank screen until `authed === true`. | CLOSED |
| T-04-W2-03 | XSS via recharts Tooltip rendering | `<Tooltip content={...}>` | mitigate | `dashboard/app/analytics/page.tsx:290-306` — Tooltip `content` callback returns JSX (`<div>`) with `{d.x}`, `{d.ticker}`, `{fmtCents(...)}` as JSX children (React auto-escapes). No `dangerouslySetInnerHTML`. No template-string-to-HTML pattern. | CLOSED |
| T-04-W2-04 | Client-side write surface | (analytics page) | accept | Page is read-only — no POST/PUT/DELETE, no form handlers; planned acceptance. | CLOSED (accepted) |
| T-04-W2-05 | Multi-tab `setInterval` drift | 5 min poller | accept | 5-minute interval well within `connect_args timeout=5` and Phase 03 throttle budget; planned acceptance. | CLOSED (accepted) |
| T-04-W3-01 | XSS via cross-link href | trades-table strategy link | mitigate | `dashboard/app/page.tsx:2670` — `href={`/analytics?strategy=${encodeURIComponent(t.strategy_name)}`}`. | CLOSED |
| T-04-W3-02 | XSS via JSX child rendering | trades-table strategy label | mitigate | `dashboard/app/page.tsx:2673` — `{t.strategy_name}` rendered as JSX child (React auto-escapes). `grep dangerouslySetInnerHTML dashboard/app/page.tsx` = 0 matches. | CLOSED |
| T-04-W3-03 | Information disclosure via header link | header `Analytics →` link | mitigate | `dashboard/app/page.tsx:2316` — `<a href="/analytics">` is a static path (no embedded data). The `/analytics` route itself enforces `checkAuth` (T-04-W2-02 mitigation). | CLOSED |

*Status: open · closed*
*Disposition: mitigate (implementation required) · accept (documented risk) · transfer (third-party)*

---

## Accepted Risks Log

| Risk ID | Threat Ref | Rationale | Accepted By | Date |
|---------|------------|-----------|-------------|------|
| AR-04-01 | T-04-W0-01 | Wave 0 (test scaffolding) introduces no production code path; threats are about test isolation only. | Plan author (04-00-PLAN) | 2026-05-08 |
| AR-04-02 | T-04-W0-02 | Wave 0 (test scaffolding) introduces no production code path; threats are about test isolation only. | Plan author (04-00-PLAN) | 2026-05-08 |
| AR-04-03 | T-04-04 | DoS bounded by Phase 03 D-01 (`strategy_name` index), 5-min client poll throttle, and SQLAlchemy `connect_args timeout=5`. Worst-case per-strategy result set is order of trades in DB; no pagination warranted at current volume. | Plan author (04-01-PLAN) | 2026-05-08 |
| AR-04-04 | T-04-05 | Both endpoints are explicitly GET-only with no write operations; FastAPI route methods enforce HTTP-method semantics. | Plan author (04-01-PLAN) | 2026-05-08 |
| AR-04-05 | T-04-W2-04 | Analytics page is read-only — no mutating UI affordances. No write surface to harden. | Plan author (04-02-PLAN) | 2026-05-08 |
| AR-04-06 | T-04-W2-05 | 5-min poll interval is benign across multiple tabs; SQL timeout (5s) and indexed strategy_name filter cap worst-case load. | Plan author (04-02-PLAN) | 2026-05-08 |

*Accepted risks do not resurface in future audit runs.*

---

## Unregistered Threat Flags

None. All `## Threat Flags` entries in `04-02-SUMMARY.md` and `04-03-SUMMARY.md`
explicitly cite existing threat IDs (T-04-W2-01..03, T-04-W3-01..03). Waves 0
and 1 SUMMARY files contain no Threat-Flags section.

---

## Security Audit Trail

| Audit Date | Threats Total | Closed | Open | Run By |
|------------|---------------|--------|------|--------|
| 2026-05-08 | 14 | 14 | 0 | /gsd-secure-phase (retroactive) |

---

## Verification Commands (audit-time evidence)

```
$ grep -cF 'text(' src/predictions/api.py
1                                          # only pre-existing api.py:692, no new raw SQL

$ grep -n 'dependencies=\[Depends(_check_token)\]' src/predictions/api.py | grep -E ':(424|521)'
424:    dependencies=[Depends(_check_token)],
521:    dependencies=[Depends(_check_token)],

$ grep -c dangerouslySetInnerHTML dashboard/app/analytics/page.tsx dashboard/app/page.tsx
0                                          # both files

$ grep -n 'encodeURIComponent' dashboard/app/analytics/page.tsx dashboard/app/page.tsx
analytics/page.tsx:165:  fetch(`/api/strategy-analytics?strategy=${encodeURIComponent(selected)}`)
page.tsx:2670:           href={`/analytics?strategy=${encodeURIComponent(t.strategy_name)}`}

$ grep -n 'if (!authed) return' dashboard/app/analytics/page.tsx
156:    if (!authed) return;                 # guards the data-fetch useEffect
```

---

## Sign-Off

- [x] All threats have a disposition (mitigate / accept / transfer)
- [x] Accepted risks documented in Accepted Risks Log
- [x] `threats_open: 0` confirmed
- [x] `status: verified` set in frontmatter

**Approval:** verified 2026-05-08
