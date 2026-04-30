---
last_mapped: 2026-04-30
last_mapped_commit: d010a403e3997670cdce46c100b8d39438c4783d
---

# Technology Stack

**Analysis Date:** 2026-04-30

## Languages

**Primary:**
- Python 3.13 - Backend API, scanner loop, database operations, Kalshi client, ESPN integration
- TypeScript 5 - Dashboard (Next.js), CLI (React-ink)
- JavaScript (JSX/TSX) - React frontend components

**Secondary:**
- Shell (bash/zsh) - Installation and deployment scripts

## Runtime

**Environment:**
- Python 3.13.3 slim (Debian Bookworm) - Docker container runtime
- Node.js 20+ - Dashboard and CLI runtime (via pnpm)

**Package Manager:**
- Python: `uv` (v1.x) — replaces pip/poetry, installed as standalone in Docker
- JavaScript: `pnpm` 10.8.1 — monorepo package manager for root + workspace packages

**Lockfiles:**
- Python: `uv.lock` — deterministic dependency resolution
- JavaScript: `pnpm-lock.yaml` — frozen lockfile

## Frameworks

**Core Backend:**
- FastAPI 0.135.1 - RESTful API, CORS middleware, lifespan management
- SQLAlchemy 2.0.48 - ORM for SQLite, models for trades/opportunities/config
- Uvicorn 0.41.0 - ASGI server (0.0.0.0:8000 in containers)

**Frontend:**
- Next.js 16.1.6 - Dashboard SPA via OpenNext (Lambda/CloudFront on SST)
- React 19.2.3 (dashboard) / 19.0.0 (CLI) - Component library
- React-ink 6.8.0 - Terminal UI toolkit for CLI
- Tailwind CSS 4 - Utility-first CSS (dashboard)

**Testing:**
- pytest 8.0 - Python test runner
- pytest-asyncio 0.24 - Async test mode for `asyncio` tests

**Build/Dev Tools:**
- SST v4.2.2 - Infrastructure as code for AWS ECS, S3, Cloudflare DNS

## Key Dependencies

**Critical Backend:**
- `httpx` 0.28 - Async HTTP client for ESPN API and Kalshi REST calls
- `websockets` 16.0 - WebSocket client for Kalshi market lifecycle events (v2 protocol)
- `cryptography` 46.0.5 - RSA signature generation for Kalshi API auth (PSS + SHA256)
- `python-dotenv` 1.2.2 - `.env` file loading for local development
- `boto3` 1.42.63 - AWS S3 client for database snapshots and recovery

**Frontend:**
- `recharts` 3.8.1 - React charting library for dashboard visualizations
- `zod` 4.0.0-beta - TypeScript schema validation for API responses
- `react-tweet` 3.3.0 - Embedded Tweet component

**CLI Tools:**
- `meow` 13.2.0 - Argument parser for CLI
- `ink-big-text` 2.0.0 - Large ASCII text rendering in terminal

**Build/Formatting:**
- `oxfmt` 0.7 - Fast TypeScript/JavaScript formatter (Rust-based)
- `oxlint` 0.16 - Fast ESLint-compatible linter (Rust-based)
- `tsx` 4.19.0 - TypeScript executor for Node.js (CLI runtime)

**Type Checking:**
- `ruff` 0.15.5 - Python linter and formatter (Rust-based, replaces black/isort/flake8)
- `ty` 0.0.21 - Lightweight Python type checker (replaces mypy/pyright)
- TypeScript 5 - JavaScript type checking (CLI, dashboard)

## Configuration

**Environment:**
- `.env.example` - Canonical schema; copy to `.env` for local development (gitignored)
- `.env` file supports:
  - Kalshi API credentials (key ID + RSA private key)
  - Bearer token for API/dashboard auth
  - Dashboard password (hashed server-side)
  - Tuning parameters (min price, bet %, poll interval)
  - S3 bucket for DB backups
  - ESPN/API-Football API keys
  - Database URL override (default: repo-root SQLite)

**Runtime Config:**
- SQLite `config` table in `predictions.db` — holds tunables read every scan loop (~5s)
- Defaults in `src/predictions/db.py::_CONFIG_DEFAULTS`
- Accessed via `get_config_int(key)` and `get_config(key)` helpers

**Build Configuration:**
- `pyproject.toml` - Python dependencies, ruff config (100-char line width, src layout), type checking rules
- `tsconfig.json` (CLI: ES2022, dashboard: ES2017 + Next.js paths)
- `oxfmt.json` (dashboard) - 4-space indent, 100-char line width
- `oxlint.json` (dashboard) - warns on unused vars, allows console
- `sst.config.ts` - AWS VPC, ECS Fargate service, S3 bucket, Cloudflare DNS, secrets injection

## Platform Requirements

**Development:**
- Python 3.13+ (specified in `pyproject.toml`)
- Node.js 18+ (for pnpm)
- `uv` binary (installed via `install.sh`)
- `.env` file with Kalshi API credentials

**Production:**
- AWS account (ECS Fargate container in us-east-2)
- Cloudflare DNS for domain delegation
- S3 bucket (DB backup durability)
- SST v4 CLI for deployment
- IAM roles/policies for ECS task (S3 read/write)

**Container:**
- Multi-layer Docker build: (1) uv + Python deps, (2) src code copy + package install, (3) uvicorn startup
- Base image: `python:3.13.3-slim-bookworm@sha256:…`
- Entry: `uvicorn predictions.api:app --host 0.0.0.0 --port 8000`

---

*Stack analysis: 2026-04-30*
