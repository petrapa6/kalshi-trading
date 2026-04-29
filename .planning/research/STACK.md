# Technology Stack — v1.2 Strategy Engine (delta only)

**Project:** Kalshi Trading Scanner
**Researched:** 2026-04-29
**Scope:** Additions and changes required for v1.2. Existing stack (FastAPI, SQLAlchemy 2,
SQLite, Next.js 16, React 19, Tailwind 4, recharts) is validated and not re-examined.

---

## 1. YAML Config Loading and Validation

### Decision: PyYAML + Pydantic v2 model_validate

**New Python dependency:** `pyyaml>=6.0.2`

Pydantic 2.12.5 is already in uv.lock. The pattern is:

    yaml.safe_load(file) → StrategiesConfig.model_validate(dict)

ruamel.yaml is NOT recommended — its value is round-trip comment preservation, irrelevant for a read-once config file.

**Pydantic model structure for OR-of-AND conditions:**

    class Condition(BaseModel):
        min_yes_price: int = Field(ge=0, le=99)
        min_lead: int = Field(ge=0)
        min_minute: int | None = None
        max_seconds_remaining: int | None = None

    class Strategy(BaseModel):
        name: str
        label: str
        trigger_sets: list[list[Condition]] = Field(min_length=1)
        # outer list = OR; inner list = AND

    class StrategiesConfig(BaseModel):
        strategies: list[Strategy] = Field(min_length=1)

Load once at scanner startup. Validation errors must crash-fast.

---

## 2. Dry-Run Trades Tagged by Strategy

### Decision: Add strategy_name column to existing trades table

No new table. No polymorphic inheritance.

**Migration (add to _migrate_add_columns in db.py):**

    if "strategy_name" not in cols:
        conn.execute(text("ALTER TABLE trades ADD COLUMN strategy_name VARCHAR"))
        conn.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_trades_strategy_name ON trades (strategy_name)"
        ))

**Trade model addition:**

    strategy_name = Column(String, nullable=True, index=True)
    # NULL = default live/dry-run trade (backward compatible)

**stretch_opportunities removal (STR-04):**
Do NOT run ALTER TABLE DROP COLUMN — SQLite doesn't support it reliably. Leave the
physical table as dead storage. Remove: StretchOpportunity ORM model, _migrate entries,
/api/stretch-stats and /api/stretch-opportunities endpoints, stretch tracking in scanner.py.

---

## 3. Analytics Dashboard Auto-Refresh

### Decision: setInterval polling — same pattern as existing dashboard

Do NOT use SSE or WebSocket.

The existing `[...path]/route.ts` proxy buffers every response via `await res.json()`. It
cannot pass through a `text/event-stream` without a new proxy route. Analytics data changes
at scanner-loop cadence (~5s); 15s polling is indistinguishable from SSE for dry-run monitoring.

    useEffect(() => {
        const fetch = async () => { /* GET /api/analytics/strategies */ };
        fetch();
        const id = setInterval(fetch, 15_000);
        return () => clearInterval(id);
    }, []);

---

## 4. New Dependencies

### Python — pyproject.toml

| Package | Version   | Purpose                       |
|---------|-----------|-------------------------------|
| pyyaml  | >=6.0.2   | Parse strategies.yaml at startup |

### JavaScript — dashboard/package.json

No new packages. recharts + useEffect/setInterval + checkAuth cover the analytics page.

---

## 5. What NOT to Add

| Temptation           | Why to skip                                                        |
|----------------------|--------------------------------------------------------------------|
| ruamel.yaml          | Round-trip comment preservation; irrelevant for read-once config   |
| sse-starlette        | Proxy can't forward streams; polling adequate at 15s               |
| WebSocket for dashboard | Overkill for 15s refresh                                        |
| New strategy_trades table | strategy_name column + dry_run filter covers all queries      |
| alembic              | Inline ALTER TABLE is the project standard                         |

---

## 6. Integration Points

| Capability                  | Touch points                                                        |
|-----------------------------|---------------------------------------------------------------------|
| Load strategies.yaml        | scanner.py startup; strategies.py (new module)                      |
| strategy_name column        | db.py (model + migration); scanner.py (pass name to place_bet); api.py (analytics endpoint) |
| Analytics page              | dashboard/app/analytics/page.tsx; GET /api/analytics/strategies     |
| Remove stretch_opportunities| db.py (remove ORM model); api.py (remove endpoints); scanner.py    |
