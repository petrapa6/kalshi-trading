---
last_mapped_commit: d010a403e3997670cdce46c100b8d39438c4783d
last_mapped: 2026-04-30
---

# Coding Conventions

**Analysis Date:** 2026-04-30

## Python Code Style

**Formatter/Linter:**
- `ruff` (version >=0.15.5) — unified formatter + linter
  - Config: `pyproject.toml` `[tool.ruff]`
  - Line length: 100 characters
  - Indent: 4 spaces

**Rules enforced by ruff:**
- Selection: `["E", "F", "W", "I"]` (pycodestyle errors, pyflakes, warnings, isort)
- Ignores: `E402` (module-level import not at top), `E712` (comparison to True/False)
- No custom black/flake8/isort — `ruff` is the single source of truth

**Type checking:**
- `ty` (version >=0.0.21) — fast static type checker
  - Config: `pyproject.toml` `[tool.ty.environment]`
  - Python 3.13 target
  - Checked root: `src/`

**Run verification:**
```bash
uv run ruff check .          # Lint only
uv run ruff format --check . # Format check
uv run ruff format .         # Fix format in place
uv run ty check              # Type check
```

## TypeScript/JavaScript Code Style

**Dashboard (Next.js):**
- Formatter: `oxfmt` (version ^0.7) — unified TS/TSX/CSS formatter
  - Config: `dashboard/oxfmt.json`
  - Indent width: 4 spaces
  - Line width: 100 characters
  - Ignore dirs: `.open-next`, `.next`, `node_modules`

**Linter:**
- `oxlint` (version ^0.16) — unified JS/TS linter
  - Config: `dashboard/oxlint.json`
  - Warns on unused variables; allows console
  - Ignores: `.next`, `node_modules`

**CLI (Ink TUI):**
- Same `oxfmt` and `oxlint` standards as dashboard
- Uses `tsx` to run TypeScript directly (no separate build step)
- Extends React conventions from dashboard

**Run verification:**
```bash
cd dashboard && pnpm lint       # oxlint only
cd dashboard && pnpm fmt:check  # oxfmt check (no changes)
cd dashboard && pnpm fmt        # oxfmt fix in place
cd dashboard && pnpm build      # Next.js build (type-checks via tsc)
```

## Naming Patterns

**Python functions/variables:**
- `snake_case` for functions, variables, parameters
- Examples: `place_bet()`, `market_prices`, `min_yes_price`, `get_config_int()`

**Python classes:**
- `PascalCase` for SQLAlchemy ORM models and Pydantic models
- Examples: `Trade`, `Opportunity`, `StretchOpportunity`, `GameState`

**Python constants (module-level):**
- `UPPER_SNAKE_CASE` for truly immutable module-level constants
- Examples: `MIN_VOLUME = 50`, `SPORTS_GAME_SERIES = [...]`, `KALSHI_TO_ESPN = {...}`

**TypeScript/React:**
- Component names: `PascalCase` (file + export)
  - Example: `components/config.tsx` exports `ConfigView`, `ConfigSet`
- Functions/hooks: `camelCase`
  - Example: `checkAuth()`, `updateConfig()`
- Interface names: `PascalCase`
  - Example: `Stats`, `Trade`, `Opportunity`, `SportConfig`
- Private internal functions: prefix with `_`
  - Examples: `_check_token()` (FastAPI), `_rate_limit()` (KalshiClient)

**Files:**
- Python: `snake_case.py`
  - Example: `kalshi_client.py`, `config_cli.py`, `backtest.py`
- TypeScript: `snake_case.tsx` for React components, `snake_case.ts` for utilities
  - Example: `actions.ts`, `api.ts`, `components/config.tsx`

## Import Organization

**Python — ruff enforces isort order:**
1. Standard library (`asyncio`, `os`, `datetime`, etc.)
2. Third-party (`fastapi`, `sqlalchemy`, `httpx`, etc.)
3. Local imports (`from predictions.db import ...`)

No blank lines between groups (ruff's isort mode).

Example from `api.py`:
```python
import asyncio
import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc, func

from predictions import backtest as backtest_mod
from predictions.backtest import BacktestRequest, BacktestResponse
from predictions.db import (...)
```

**TypeScript/React:**
1. React/framework imports
2. Third-party packages
3. Local app imports (relative or alias-based)
4. CSS/assets

Example from `dashboard/app/page.tsx`:
```typescript
"use client";

import { useEffect, useState } from "react";
import { Tweet } from "react-tweet";
import { login, checkAuth, updateConfig } from "./actions";
```

## Error Handling Patterns

**Python — async exceptions:**
- Callers define what exceptions are recoverable
- Do NOT add blanket `try/except` unless explicitly catching known exceptions
- HTTP error responses handled by FastAPI; `raise HTTPException` for 401/403/400
  - Example: `_check_token()` in `api.py` raises `HTTPException(status_code=401)`

**Python — async race conditions:**
- Race conditions in `market_prices` dict are tolerated (local dict, no external consistency required)
- SQLAlchemy session safety: open/close per-request pattern
  - Example: `get_session()` factory for CRUD ops, `.close()` after use

**TypeScript — promise handling:**
- API calls return typed responses; callers handle errors via fetch status
- Example from `dashboard/app/page.tsx`: auth checks via `checkAuth()` server action, login fallback

## Logging

**Python:**
- Framework: `logging` (standard library)
- Config: Per-module logger in each file
  - `log = logging.getLogger(__name__)`
- Scanner baseline setup in `scanner.py`:
  ```python
  logging.basicConfig(
      level=logging.INFO,
      format="%(asctime)s [%(levelname)s] %(message)s",
      handlers=[
          logging.StreamHandler(),
          logging.FileHandler("scanner.log"),
      ],
  )
  log = logging.getLogger(__name__)
  ```
- Log level: INFO for operational events, DEBUG for tracing, ERROR for exceptions
- No console.log usage (scanner is a background task; logs go to file)

**TypeScript/React:**
- Console logging used minimally (oxlint allows it)
- Example: error logging in server actions (`actions.ts`)

## Comments & Documentation

**Python — default: write no comments:**
- Add comments **only when WHY is non-obvious**
- Docstrings for public functions/classes
  - Format: triple-quote string at start of function/class body
  - Example from `scanner.py`:
    ```python
    """Kalshi Sports Market Scanner
    
    Scans for sports prediction markets where...
    Uses ESPN live scoreboard...
    """
    ```
  - Short single-line docstrings for utility functions
- Inline comments for tricky logic or non-obvious configuration values

**Python — module docstrings:**
- Every `.py` file starts with a docstring explaining its purpose
- Example: `kalshi_client.py` starts with "Async client for the Kalshi trading API."

**TypeScript — same approach:**
- Minimal comments; let the code speak
- JSDoc for exported functions when interface is non-obvious

## Function Design

**Python async functions:**
- Use `async def` + `await` throughout scanner loops and API endpoints
- Rate limiting handled inside `KalshiClient._rate_limit()` — callers do not need to know
- Example: `place_bet()`, `get_scoreboard()` are both async and expect `await`

**Python SQLAlchemy queries:**
- Use `session.query(...).filter_by(...)` pattern for clarity
- No eager loads or relationships — keep models simple
- Example from `db.py`:
  ```python
  entry = session.query(ConfigEntry).filter_by(key=key).first()
  ```

**TypeScript server actions:**
- `"use server"` pragma for auth-required mutations
- Return typed responses matching Pydantic models from backend
- Example: `login()`, `updateConfig()` in `dashboard/app/actions.ts`

**Parameter design:**
- Keep function signatures under 5 parameters where possible
- Use dataclass/Pydantic models for complex multi-param cases
- Example: `BacktestRequest` model in `backtest.py` bundles 7 params into one type

## Module Exports

**Python — explicit public API:**
- Import at module level what you want to export
- Example from `api.py`:
  ```python
  from predictions.db import (
      BalanceSnapshot,
      Opportunity,
      Trade,
      ...
  )
  ```

**TypeScript — no barrel files in this codebase:**
- Direct imports from source files
- Example: `import { ApiClient } from "./api.js"` in CLI `index.tsx`

## Database Patterns

**SQLAlchemy models:**
- Inherit from `Base` (declarative)
- Use `Column(type, defaults, nullable, index, ...)` for schema definition
- Defaults as callables: `default=lambda: datetime.now(timezone.utc)`
- Indexes on frequently-filtered columns: `ticker`, `found_at`
- Example from `db.py`:
  ```python
  class Opportunity(Base):
      __tablename__ = "opportunities"
      id = Column(Integer, primary_key=True)
      found_at = Column(DateTime, ..., index=True)
      ticker = Column(String, index=True)
  ```

**Runtime config storage:**
- Key-value pairs stored in `config` table (SQLite)
- Defaults in `_CONFIG_DEFAULTS` dict (source of truth for fallback)
- Retrieved via `get_config(key)` or `get_config_int(key)`
- Never hardcode tunables — always call helpers

**Migrations (inline):**
- Inline ALTER TABLE calls in `_migrate_add_columns()` after `Base.metadata.create_all()`
- Idempotent: check column existence before adding
- Example: `ADD COLUMN IF NOT EXISTS` pattern in `db.py`

## Config Access Patterns

**Never hardcode values that should be tunable:**
- Integer cents (prices, balances): Always integer (0–100 for Kalshi)
- Min score lead: Always call `get_config_int(f"lead:{sport_path}")`
- Min price: Always call `get_config_int("min_yes_price")`
- Final seconds per sport: Always call `get_config_int(f"final_seconds:{sport_path}")`

**Example from scanner.py:**
```python
min_price = get_config_int("min_yes_price")  # NOT hardcoded
lead = get_config_int(f"lead:{sport_path}")  # NOT hardcoded
```

## Do-Not-Do List (from CLAUDE.md)

**Behaviors to avoid:**

1. **Do not hardcode trading parameters.** Always call `get_config_int(key)` for min_yes_price, max_positions, etc. Reading config every scan loop (~5s) is deliberate.

2. **Do not introduce parallel price converters.** The single boundary where Kalshi's dollar-string format enters is `extract_cents()` in `kalshi_client.py`. Do NOT add similar functions in other modules.

3. **Do not skip checking `trading_paused` before placing orders.** It's the runtime kill switch. Must be checked every loop before any order-placement code path.

4. **Do not forget `DRY_RUN` env var check at process start.** Real trades have `dry_run=False`; simulated ones have status `"dry_run"` and are excluded from API stats.

5. **Do not commit `.env`, `predictions.db`, `scanner.log`, or credential files.** `.gitignore` enforces this. Pre-commit hook does NOT scan for secrets — do that manually.

6. **Do not refactor shared interfaces without flagging blast radius.** When changing `Trade`, `Opportunity`, or `StretchOpportunity` schemas or API endpoints, ask before restructuring (may affect scanner loops, CLI, dashboard, or backtest).

7. **Do not add error handling for cases that can't happen.** Trust framework guarantees. Validate only at system boundaries (API auth, file I/O, external HTTP calls).

8. **Do not add features beyond what the task requires.** Don't design for hypothetical future requirements.

9. **Do not amend pushed commits.** Create new commits. Amending can destroy work.

10. **Do not use git --no-verify.** Hooks exist for a reason.

---

*Convention analysis: 2026-04-30*
