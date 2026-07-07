# Kalshi Trading — Home Assistant Add-on Dry-Run Deploy

**Date:** 2026-05-11
**Author:** Pavel + Claude (brainstorming)
**Status:** Design (pre-implementation)

## Goal

Ship the existing Kalshi scanner + dashboard as a Home Assistant OS add-on
installable from the GitHub repo URL, modelled directly on
`github.com/petrapa6/family-dashboard`. The add-on runs in dry-run mode only
and is reached from outside the home network at `trading.petra-czech.cc`
via the existing Cloudflared HA add-on. Cloudflare Access is wired manually
as a final step (out of scope for this spec, documented in the README).

## Non-goals

- Live (real-money) trading. DRY_RUN is hardcoded; no UI toggle.
- Replacing or breaking the current SST/AWS deploy. SST stays runnable.
- Automating Cloudflare Tunnel / Cloudflare Access setup. Both are wired
  manually after the add-on is installed.
- Multi-tenant access. A single authenticated user (Pavel) is the only
  expected consumer.

## Constraints (from user, 2026-05-11)

1. Same repo (`kalshi-trading`); add-on shipped alongside existing code.
2. Image must build on amd64 (current dev machine) **and** aarch64 (RPi-class
   HAOS host).
3. Database must live under `/data` so it is included in HA's add-on backup
   sweep. Same pattern as family-dashboard's `DATABASE_URL=file:/data/dashboard.db`.
4. Cloudflare Access is configured manually as the last step; design must
   not depend on it for correctness — only for privacy.

## Architecture

### Topology

```
┌─ Home Assistant OS host (RPi or x86) ──────────────────────────┐
│                                                                  │
│  ┌─ Cloudflared add-on (already installed) ───────────────────┐ │
│  │  trading.petra-czech.cc  →  http://homeassistant.local:8000│ │
│  └─────────────────────────────┬──────────────────────────────┘ │
│                                ▼                                 │
│  ┌─ Kalshi Trading add-on (NEW) ─────────────────────────────── │
│  │  Single container, two processes supervised by tini          │
│  │                                                                │
│  │  Port 8000 (exposed → host)                                   │
│  │  ┌──────────────────┐    localhost:8001    ┌────────────────┐│
│  │  │  Next.js server  │ ───────────────────▶ │ FastAPI +       ││
│  │  │  node server.js  │                       │ scanner (uvicorn)││
│  │  │  :8000           │                       │ :8001 (loopback)││
│  │  └──────────────────┘                       └────────────────┘│
│  │                                                       │       │
│  │                                                       ▼       │
│  │                            /data/predictions.db (HA-backed-up)│
│  │                            /data/soccer-cache.db              │
│  │                            /data/strategies.yaml              │
│  └─────────────────────────────────────────────────────────────── │
└───────────────────────────────────────────────────────────────────┘
```

### Why single-container, two processes

- Only the dashboard needs to be reachable from outside the container. The
  Python API binds to `127.0.0.1:8001` only — there is no public API
  surface, no need for CORS in production, no need for Cloudflare Access on
  the API host.
- Two separate add-ons would have to share `/data` and orchestrate startup
  ordering; HA Supervisor has no native dependency declaration between
  add-ons. Single container side-steps that.
- `tini` (already used by family-dashboard's runtime) reaps zombies and
  forwards SIGTERM so the container shuts down cleanly when HA restarts it.

### Process supervision

`run.sh` starts both uvicorn and `node server.js` as background children,
then uses `wait -n` to block until either exits. On any exit (either
process crashing OR a SIGTERM from HA Supervisor), `run.sh` kills the
surviving process and exits with the dead child's status. HA Supervisor
sees the container exit and restarts the add-on per `boot: auto`,
`startup: application`.

This avoids the "exec the dashboard, background the API" trap where a
silent uvicorn crash would leave the container running with a broken
dashboard. With `wait -n`, either process going down takes the whole
container down, which makes the restart loop observable.

- tini is PID 1; it reaps zombies and forwards SIGTERM to `run.sh`.
- `trap 'kill -TERM $API_PID $DASH_PID 2>/dev/null; wait' SIGTERM SIGINT`
  in `run.sh` makes shutdown clean.

Future-proofing note: if process supervision becomes flaky we'd switch to
s6-overlay (the canonical HA add-on multi-process pattern). YAGNI for now;
the family-dashboard `tini` pattern is the precedent we're following.

## Repo layout (additions)

```text
kalshi-trading/                       (repo root)
├── repository.yaml                   NEW — declares this as a HA repo
├── config.yaml                       NEW — HA add-on manifest
├── build.yaml                        NEW — multi-arch base image map
├── Dockerfile                        NEW — combined Python+Node runtime
├── Dockerfile.api                    RENAMED from current Dockerfile
├── run.sh                            NEW — entrypoint, reads /data/options.json
├── sst.config.ts                     EDITED — dockerfile path → "Dockerfile.api"
├── src/                              (unchanged)
├── dashboard/                        (unchanged)
├── strategies.yaml                   (unchanged; seeded into /data on first boot)
└── docs/superpowers/specs/2026-05-11-haos-addon-deploy-design.md   (this file)
```

Family-dashboard's layout is single-add-on-at-repo-root; we mirror that.
HA Supervisor treats the repo root as both the repository and the
add-on directory when `repository.yaml` and `config.yaml` are siblings.

### Why rename `Dockerfile` → `Dockerfile.api`

The existing `Dockerfile` is Python-only and used by SST for the AWS
deploy. HA Supervisor expects to find `Dockerfile` at the add-on root and
will build whatever is there. To keep both production paths working we
rename the SST one and put the combined image in the canonical filename.

Cost: one line in `sst.config.ts` changes (`dockerfile: "Dockerfile"` →
`dockerfile: "Dockerfile.api"`). Reversible.

## File details

### `repository.yaml`

```yaml
name: Kalshi Trading
url: https://github.com/<owner>/kalshi-trading
maintainer: Pavel
```

(GitHub URL filled in when the repo is pushed under the intended owner.)

### `config.yaml`

```yaml
name: "Kalshi Trading"
version: "1.0.0"
slug: "kalshi_trading"
description: "Kalshi sports market scanner — dry-run only"
url: "https://github.com/<owner>/kalshi-trading"
arch:
  - aarch64
  - amd64
ports:
  8000/tcp: 8000
ports_description:
  8000/tcp: "Dashboard web interface"
map:
  - data:rw
options:
  kalshi_api_key: ""
  kalshi_private_key: ""
  api_token: ""
  dashboard_password: ""
  api_football_key: ""
schema:
  kalshi_api_key: password
  kalshi_private_key: password
  api_token: password
  dashboard_password: password
  api_football_key: str?
startup: "application"
boot: "auto"
```

Notes:
- `arch` includes both architectures per constraint #2.
- `map: - data:rw` is the HA-managed persistent volume; HA's backup system
  snapshots this on add-on backups.
- `schema` field types are HA's typed options (`password` masks the value
  in the UI; `str?` is optional string). `kalshi_private_key` is multi-line
  PEM — `password` handles multi-line fine.
- No `DRY_RUN`/`trading_paused` toggles — both are enforced in code/scripts,
  not user-toggleable (anti-foot-gun).

### `build.yaml`

```yaml
build_from:
  aarch64: "python:3.13-slim-bookworm"
  amd64: "python:3.13-slim-bookworm"
labels:
  org.opencontainers.image.title: "Kalshi Trading"
  org.opencontainers.image.source: "https://github.com/<owner>/kalshi-trading"
```

Per the family-dashboard precedent, `build_from` is metadata that HA
Supervisor records but the actual base image is whatever the `FROM` in
the Dockerfile says. We declare `python:3.13-slim-bookworm` for both
arches so Supervisor's image labelling matches what the Dockerfile uses.

### `Dockerfile` (combined runtime)

Multi-stage:

1. **dashboard-build** (`node:20-alpine`): `pnpm install` + `next build`,
   produce `.next/standalone` + static assets.
2. **python-deps** (`python:3.13-slim-bookworm`): `uv sync --frozen --no-dev`
   into `/app/.venv`.
3. **runner** (`python:3.13-slim-bookworm`):
   - apt-get install `nodejs` (from Debian bookworm repos — node 18/20-class),
     `tini`, `jq`, `ca-certificates`.
   - Copy `.venv` from python-deps stage.
   - Copy `src/` and install the `predictions` package itself (`pip install
     --no-deps -e .` against the venv).
   - Copy dashboard standalone build into `/dashboard/`.
   - Copy `run.sh`, chmod +x.
   - `EXPOSE 8000`, `ENTRYPOINT ["/usr/bin/tini", "--"]`, `CMD ["/run.sh"]`.

Open implementation question (writing-plans will resolve): Debian bookworm
ships Node 18 by default. Next 16 may want Node 20 — if so, add NodeSource
or use `node:20-bookworm-slim` as the runtime base and apt-install Python
3.13. Implementation step will probe + pick the smaller base.

### `run.sh`

Pattern lifted from family-dashboard `run.sh`:

1. `jq` out add-on options from `/data/options.json` → export as env vars.
2. Hardcode `DRY_RUN=true`, `DATABASE_URL=sqlite:////data/predictions.db`,
   `SOCCER_CACHE_DB_PATH=/data/soccer-cache.db`,
   `STRATEGIES_PATH=/data/strategies.yaml`, `NEXT_PUBLIC_API_URL=http://127.0.0.1:8001`.
   (`NEXT_PUBLIC_API_URL` is read server-side by `actions.ts:41` and
   `api/[...path]/route.ts:5` at request time, not baked at build, so
   setting it in `run.sh` is sufficient. The browser never sees it
   because the dashboard proxies all calls server-side.)
3. First-boot seeding (idempotent):
   - If `/data/strategies.yaml` missing → copy from `/app/strategies.yaml`.
   - Write `trading_paused="true"` into the SQLite config table via a tiny
     Python one-liner (sqlite3 stdlib, no SQLAlchemy boot dance).
4. Validate critical env vars present (`api_token`, `dashboard_password`,
   `kalshi_api_key`, `kalshi_private_key`) — fail fast with a clear error
   if any are missing.
5. Background uvicorn on `127.0.0.1:8001`, capture `$API_PID`.
6. Background `node server.js` on `0.0.0.0:8000`, capture `$DASH_PID`.
7. `trap 'kill -TERM $API_PID $DASH_PID 2>/dev/null; wait' SIGTERM SIGINT`.
8. `wait -n $API_PID $DASH_PID` — block until either exits.
9. Kill the survivor, `exit` with the dead child's status so HA Supervisor
   restarts the container.

### `sst.config.ts` (edit)

Single change: `dockerfile: "Dockerfile"` → `dockerfile: "Dockerfile.api"`
on the ECS service definition. Everything else stays. SST keeps working
unchanged for the AWS path.

## Auth & access (the "only I can access" guarantee)

Two independent layers — both must pass:

1. **Cloudflare Access on `trading.petra-czech.cc`** (manual, post-deploy).
   Zero Trust policy: allow only `petracekpav@gmail.com`. Configured via
   the Cloudflare dashboard after the tunnel is up. Documented in the
   add-on README — not in code.

2. **Dashboard password** (existing `actions.ts` flow). User sets
   `dashboard_password` in the HA add-on options UI; `run.sh` exports it
   as `DASHBOARD_PASSWORD`; the Next.js server hashes + cookie-checks as
   today. Unchanged code.

API stays at `127.0.0.1:8001` — not reachable from outside the container.
Bearer `API_TOKEN` is set via add-on options and used by the Next.js proxy
the same way it is today.

If the user skips step 1 entirely the add-on is still gated by the
dashboard password. Cloudflare Access is defense-in-depth, not the only
lock.

## Dry-run safety (three independent locks)

| Lock | Where it lives | Bypass-able by |
|---|---|---|
| `DRY_RUN=true` env | Hardcoded in `run.sh` | Editing the source code |
| `place_strategy_trade` pins `dry_run=True` at the call site | `scanner.py` (existing v1.2 DRY-01 invariant) | Editing the source code |
| `trading_paused="true"` config row | Seeded by `run.sh` on first boot into `/data/predictions.db` | Manual SQL edit, or a dashboard config change (which the user can audit) |

All three must be defeated for a live order to fire. The first two require
a code change; the third is auditable in the config UI.

## Local build & test

The combined Dockerfile must work locally (constraint #1). Test via:

```bash
docker build -t kalshi-trading:local .
docker run --rm -p 8000:8000 \
  -v "$(pwd)/.data:/data" \
  -e SUPERVISOR_TOKEN="" \
  kalshi-trading:local
```

On first run, `run.sh` would fail because `/data/options.json` doesn't
exist in a non-HA environment. To support local Docker testing, `run.sh`
must fall back to environment variables when `/data/options.json` is
absent — same pattern family-dashboard uses (see `if [ -f "$CONFIG_PATH" ]`
check in their `run.sh:8`). With that fallback, local dev can pass the
secrets via `--env-file`.

Existing local dev (`pnpm dev:api` + `pnpm dev:dashboard`) is unchanged
and remains the fast inner loop. The Docker build is for HAOS parity
testing.

## Persistence & migration

- DB file path moves from production's `/tmp/predictions.db` (ephemeral
  Fargate FS + S3 backup loop) to `/data/predictions.db` (HA-managed,
  HA-backup-included).
- Existing 30-min S3 backup loop in `scanner.py` is gated on
  `DB_BACKUP_BUCKET` env. The add-on leaves that env unset → loop becomes
  a no-op. No code change required.
- Strategies file: image ships `strategies.yaml` at `/app/strategies.yaml`;
  `run.sh` copies it to `/data/strategies.yaml` on first boot only,
  letting the user edit it via the HA file editor / Samba share.
- First-time deploy starts with an empty DB. The user can either let it
  populate fresh, or restore from an existing `predictions.db` via the
  HA file editor / Samba (drop into `/addon_configs/<slug>/`).

## Error handling & operations

- HA Supervisor logs (`docker logs`) capture both processes' stdout/stderr
  because both write to the container's standard streams. The Next.js
  proxy logs the API URL it's calling; the Python scanner logs the same as
  in production.
- Restart policy: `boot: auto`, `startup: application` → restarts on
  container exit and on HA host boot. Same as family-dashboard.
- Add-on backup: HA snapshots `/data` automatically on each "Create
  backup" action, which covers the SQLite file. No backup loop needed.

## Decisions log

| Decision | Rationale |
|---|---|
| Single container, two processes (tini-supervised) | Mirrors family-dashboard precedent; avoids cross-add-on dep ordering in HA. |
| API on `127.0.0.1:8001`, not exposed | API has no business being public; reduces attack surface to dashboard alone. |
| `Dockerfile.api` rename | Keep SST/AWS path runnable; root `Dockerfile` is the HA-canonical filename. |
| Drop S3 backup (existing loop becomes no-op) | HA backups cover `/data`; one less AWS dep for a deploy that's escaping AWS. |
| DRY_RUN hardcoded, not in `schema` | Foot-gun avoidance; flipping in the HA UI must not enable live trading. |
| Seed `strategies.yaml` from image into `/data` on first boot | Editable at runtime via HA file editor; doesn't lose user edits across upgrades. |
| Cloudflare Access wired manually post-install | User explicitly chose this; design doesn't depend on Access for correctness. |
| Multi-arch (`aarch64` + `amd64`) | Per constraint #2 — build on dev box for fast iteration, deploy on RPi. |

## Out of scope

- Live trading enablement / kill-switch UI in HA Supervisor.
- Multi-user HA Access policies (only one operator expected).
- HA ingress mode (web UI inside the HA sidebar). The dashboard is reached
  via the Cloudflare-tunneled hostname, not HA's iframe ingress. Could be
  added later as an addition to `config.yaml` (`ingress: true`, `ingress_port: 8000`).
- Automatic strategies.yaml hot-reload — see v1.2 retro.
- Telemetry/metrics export to HA's MQTT broker or similar.

## Risks

1. **Node version mismatch.** Next 16 may require Node 20+; Debian bookworm
   default is Node 18. Implementation must verify and either pin Node 20
   via NodeSource or pick a Node 20 base image and apt-install Python.
   Surfaced as the open implementation question in §Dockerfile.
2. **Container size.** Combined Python+Node image will be larger than
   either alone (probably ~600–900 MB compressed). Acceptable for HAOS
   add-ons; users tolerate big add-ons. Not optimising for size here.
3. **HA Supervisor build time on RPi.** Multi-stage build of pnpm install
   + Next build on a Pi 4 may take 5–10 minutes the first time. One-time
   cost; subsequent rebuilds use layer cache.
4. **`predictions.db` schema drift on upgrade.** The existing scanner
   handles schema additively (idempotent table-creates). Add-on upgrades
   should preserve `/data/predictions.db`. If a future schema change is
   destructive, the user must back up the DB via HA first — call this out
   in the add-on README.

## Open questions (must answer during implementation)

- Exact Node version + base image strategy for the runner stage (see Risk 1).
- Where to put the GitHub repo URL placeholder in `repository.yaml` /
  `config.yaml` — defaults to `petrapa6/kalshi-trading` unless told otherwise.
- Whether `run.sh` should fail loudly or silently no-op when secrets are
  missing on first boot before any UI configuration. Family-dashboard's
  pattern is fail-loudly with a clear error message; we follow that.

## Implementation hand-off

After spec approval, invoke `superpowers:writing-plans` to break this into
ordered, independently-testable steps. Expected step shape:

1. Rename `Dockerfile` → `Dockerfile.api`; update `sst.config.ts`.
2. Write root `Dockerfile` (combined) + verify `docker build` succeeds locally.
3. Write `run.sh` with `/data/options.json` + env-var fallback; verify
   `docker run` boots both processes and serves the login page.
4. Write `config.yaml`, `build.yaml`, `repository.yaml`.
5. Smoke-test on local Docker with `.data/` mounted; confirm DB persists
   across restarts.
6. Push to GitHub; add the repo URL as a HA add-on repository on the RPi;
   install; configure secrets via UI; verify scanner picks up market data
   in dry-run.
7. (Manual, out of scope for the plan) Wire Cloudflared add-on ingress and
   Cloudflare Access policy.
