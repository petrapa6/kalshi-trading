---
last_mapped_commit: d010a403e3997670cdce46c100b8d39438c4783d
last_mapped: 2026-04-30
---

# Codebase Concerns

**Analysis Date:** 2026-04-30

## Tech Debt

### **[Critical]** SQLite Durability Window on Production

**Issue:** Production `DATABASE_URL` is `/tmp/predictions.db` (ECS task-local, lost on restart). Durability comes from the 30-minute S3 snapshot loop (`backup_loop` in `src/predictions/scanner.py` line 1012).

**Files:** 
- `src/predictions/api.py` lines 176–189, 215–241 (lifespan + backup logic)
- `src/predictions/scanner.py` lines 747–776 (backup_db function)
- `sst.config.ts` (infrastructure)

**Impact:** 
- Data loss window up to 30 minutes on container crash or restart.
- No EFS (persistent volume) mounted.
- Trades placed but not yet settled can be lost entirely.
- Balance snapshots and scan history between backups are not recoverable.

**Fix approach:** 
1. Mount an EFS volume at `/data` on the ECS task and set `DATABASE_URL=sqlite:////data/predictions.db`.
2. OR switch to a managed database (RDS SQLite proxy, DynamoDB, or PostgreSQL).
3. OR reduce backup interval from 30 min to 5–10 min (increases S3 cost but reduces loss window).
4. Recommend option 1 (EFS) as lowest-cost, lowest-latency fix with zero code changes.

---

### **[High]** Settlement P&L Computed in Two Places

**Issue:** Market settlement triggers two independent P&L calculations:

1. **WebSocket path** (`on_lifecycle` in `src/predictions/scanner.py` lines 825–877):
   - Triggered by `market_lifecycle_v2` event.
   - Fee handling: `trade.pnl_cents = trade.potential_profit_cents - fee`
   - Direct writes to DB.

2. **REST poll path** (`check_settlements` in `src/predictions/scanner.py` lines 202–238):
   - Runs every 5 sec as fallback if WS missed an event.
   - Fee handling: `trade.pnl_cents = trade.potential_profit_cents - (trade.fee_cents or 0)`
   - Same DB logic.

**Files:** `src/predictions/scanner.py` lines 202–238, 825–877, 993–996

**Current Risk:**
- If WS fires first, then REST fires on the same ticker, the REST path updates a `settled_win` trade again (no guard on status check before update).
- Stretch opportunities settle via both paths too (lines 707–744 vs 856–873).
- No idempotency guard: `if trade.status == "open"` before settling.

**Why it matters:**
- Low probability of double-settlement on same trade in practice (WS is fast).
- But unguarded updates mean a bug in one path silently corrupts the other.
- Stretch P&L could be updated twice if both paths fire.

**Fix approach:**
1. Add status guard: only update if current status is `"placed"` or `"filled"` (not already settled).
2. Consolidate to single settlement function with both WS + REST checks.
3. Idempotent: settlements are durable if status is checked first.

---

### **[High]** Dashboard Password Uses Hardcoded Salt

**Issue:** Dashboard authentication in `src/dashboard/app/actions.ts` line 10:

```typescript
const COOKIE_VALUE = crypto.createHash("sha256").update(PASSWORD + "salt123").digest("hex");
```

**Files:** `dashboard/app/actions.ts` line 10

**Risk:**
- Salt `"salt123"` is hardcoded in source code.
- Attacker with source code can pre-compute hash for any password in realtime.
- Salt should be unique, random, and stored separately from the hash algorithm.
- Does NOT break authentication (plaintext password check on line 13 still required), but weakens the cookie forgery defense.

**Why it matters:**
- If `DASHBOARD_PASSWORD` is ever leaked or weak, and an attacker has source code, they can instantly forge valid cookies without knowing the password.
- Current security relies solely on password length/entropy, not on the hash.

**Fix approach:**
1. Use a cryptographically random salt (16–32 bytes, base64-encoded).
2. Store salt in `process.env.COOKIE_SALT` (secrets manager, not source).
3. Or use `crypto.pbkdf2` with random salt: `pbkdf2(PASSWORD, salt, 100000, 32, 'sha256')`.
4. Or accept that cookies are a secondary defense; primary is Bearer token on the API.

---

## Known Bugs

### **[Medium]** No Idempotency on `extract_cents` Boundary Conversion

**Issue:** The single entry point for price conversion is `extract_cents` in `src/predictions/kalshi_client.py` lines 19–27. It handles both old integer fields and new FixedPointDollar string fields from Kalshi API v3.

**Files:** `src/predictions/kalshi_client.py` lines 19–27

**Observed Pattern:**
- Called from many places (scanner, API, WS, etc.).
- Converts `"0.9200"` → 92 correctly via `round(float(dollar_val) * 100)`.
- But no tests for boundary cases: `"0.885"` (rounds to 89? 88?), `"0.8849"` (87? 88?).

**Risk:**
- Rounding error of 1–2 cents at the boundary affects bet placement.
- If yes_ask is `"0.885"` and rounds to 89, but our config says `min_yes_price=91`, we wrongly skip it.
- Kalshi's rounding convention is not documented.

**Fix approach:**
1. Add unit tests for `extract_cents` with boundary prices: `"0.88"`, `"0.885"`, `"0.8849"`, `"0.8851"`, etc.
2. Confirm Kalshi's rounding convention (banker's rounding? truncation? round-half-up?).
3. Document the convention in a comment in `kalshi_client.py`.

---

### **[Medium]** No Guard on Volume Extraction in `extract_volume`

**Issue:** `extract_volume` in `src/predictions/kalshi_client.py` lines 30–38 extracts volume from API responses, which may change field names between API versions.

**Files:** `src/predictions/kalshi_client.py` lines 30–38

**Pattern:**
- Tries `volume_fp` first (FixedPoint format), falls back to `volume` (integer).
- If both are missing or non-numeric, returns 0.
- No logging or warning if both fields are absent.

**Risk:**
- Silent zero volume could cause trades to be skipped (has_liquidity checks `volume >= MIN_VOLUME`).
- If Kalshi changes field names again, we won't know until trades mysteriously stop.

**Fix approach:**
1. Add a warning log if both fields are absent: `if vol is None and "volume" not in d: log.warning(...)`.
2. Or track a metric for missing-volume cases to alert ops.

---

## Security Considerations

### **[High]** Pre-Commit Hook Does NOT Scan for Secrets

**Issue:** `scripts/pre-commit-check.sh` runs formatting and type-checking, but explicitly **does NOT scan for secrets**. Per `CLAUDE.md` line 108–112:

> Manual secret scan before every commit. The pre-commit hook handles format + type-check only — it does NOT scan for secrets (API tokens, Kalshi keys, Cloudflare tokens, `BEGIN * PRIVATE KEY`, passwords).

**Files:** `scripts/pre-commit-check.sh`, `CLAUDE.md` lines 108–112

**Current Mitigation:**
- Developer must manually grep before commit.
- Forbidden files (`.env`, `*.key`, `*.pem`) are in `.gitignore`.

**Remaining Risk:**
- Accidental commit of secrets hard-coded in source (e.g., a test fixture with a real token).
- No automated gate.

**Recommendations:**
1. Add a pre-commit hook that runs `git diff --cached | grep -E '(sk-|BEGIN|PRIVATE|API_KEY|api_key|password)'` and fails if matched.
2. Use a tool like `detect-secrets` or `truffleHog` for more sophisticated scanning.
3. Enforce secret scanning in CI (GitHub Actions / SST hooks).

---

### **[Medium]** Single `API_TOKEN` Shared Across All Callers

**Issue:** `src/predictions/api.py` line 260 uses a single `API_TOKEN` env var for all mutable endpoints:

```python
def _check_token(authorization: str | None = Header(None)):
    expected = os.getenv("API_TOKEN", "")
    if not expected:
        raise HTTPException(403, "API_TOKEN not configured")
    ...
```

**Files:** `src/predictions/api.py` lines 258–266

**Impact:**
- Dashboard (Next.js), CLI (React-ink), and any external tooling all use the same token.
- If token is leaked, all surfaces are compromised.
- No audit trail of which caller made which request (API logs don't distinguish).

**Mitigation in place:**
- Token is in `.env` (local) or `sst secret` (production).
- Not committed to source.

**Recommendations:**
1. Separate tokens: `DASHBOARD_API_TOKEN`, `CLI_API_TOKEN`, `EXTERNAL_API_TOKEN`.
2. Add request logging middleware to record token (first 4 chars) + endpoint + caller IP.
3. Consider JWT with claims (role, expiry) instead of a static string.

---

## Performance Bottlenecks

### **[Medium]** `dashboard/app/page.tsx` is a 2,975-Line Monolith

**Issue:** The entire dashboard UI is a single `"use client"` component. Contains:
- Auth logic
- Data fetching for stats, trades, opportunities, stretch stats
- SVG charts (P&L line chart, histograms, time-remaining histogram)
- Tab UI (Overview, Trades, Opportunities, Config)
- Config edit forms
- Responsive layout

**Files:** `dashboard/app/page.tsx` (2,975 lines)

**Impact:**
- Hard to test individual views or charts.
- Changes to one section require reading/understanding the entire file.
- SVG charting logic (hundreds of lines) mixed with UI logic.
- Slow to edit, easy to introduce bugs.

**Why not critical:** The file loads and renders fine; no runtime performance issue. But maintainability cliff.

**Fix approach:**
- Extract charts to separate components: `PnlChart.tsx`, `PnlHistogram.tsx`, `TimePnlHistogram.tsx`.
- Extract config panel to `ConfigPanel.tsx`.
- Extract trades/opportunities tables to `TradesTable.tsx`, `OpportunitiesTable.tsx`.
- Reduce root component to ~500 lines of layout + state management.

---

## Fragile Areas

### **[Medium]** ESPN Score/Clock Parsing in `espn.py` Assumes Stable Field Names

**Issue:** ESPN API is undocumented. The scanner relies on ESPN field names that could change:
- `status.clock` (countdown time in seconds)
- `status.period` (quarter, inning, etc.)
- `competitors[i].score` (team score)
- `shortName` (team abbreviation)

**Files:** `src/predictions/espn.py` (full file)

**Risk:**
- If ESPN changes the response schema (e.g., `clock` → `time_remaining`), games won't match.
- No validation that required fields exist.
- Silent failures: game is fetched but clock/period is `None`, missed trades.

**Fix approach:**
1. Add schema validation: raise if `status`, `clock`, `period` are missing.
2. Log a warning if a game is missing expected fields instead of silently skipping.
3. Add a fallback: if `clock` is missing, assume `status == "final"` → don't trade.

---

### **[Low]** WS Subscription Management is Not Atomic

**Issue:** In `src/predictions/scanner.py` lines 961–981, the scanner subscribes to new market tickers via WebSocket. If a new series appears and we try to subscribe, but the subscription partially fails, the `subscribed_tickers` set may become out of sync with actual subscriptions.

**Files:** `src/predictions/scanner.py` lines 961–981, 966–975

**Pattern:**
```python
if ticker_sub_sid is None:
    ticker_sub_sid = await ws.subscribe(["ticker"], tickers_list)
    lifecycle_sub_sid = await ws.subscribe(["market_lifecycle_v2"], tickers_list)
else:
    await ws.update_subscription(ticker_sub_sid, tickers_list)
    await ws.update_subscription(lifecycle_sub_sid, tickers_list)
subscribed_tickers.update(to_add)
```

**Risk:**
- If the first `ws.subscribe` succeeds but the second fails, we've subscribed to ticker updates but not lifecycle events (settlement) for the same market.
- No retry or rollback.

**Fix approach:**
1. Wrap both subscriptions in a try/except: if either fails, don't add to `subscribed_tickers`.
2. Or add a health check loop that re-syncs subscription state every 30s.
3. Low priority: WS rarely fails; subscription is best-effort.

---

## Scaling Limits

### **[Medium]** SQLite Not Optimized for High-Frequency Writes

**Issue:** The scanner runs four concurrent loops (ESPN 10s, Kalshi 5s, WS continuous, backup 30m). Each Kalshi scan iteration:
1. Records a `Scan` row.
2. Inserts one `Opportunity` row per found market.
3. May insert/update many `Trade` rows.
4. Settlement loop updates multiple trades at once.
5. Backtest mode inserts stretch opportunities continuously.

**Files:** `src/predictions/scanner.py` lines 458–576 (scan recording), `src/predictions/api.py` line 244 (balance snaps)

**Observed Pattern:**
- ~12 opportunities/minute at peak → ~1,440 opportunity rows/day.
- ~20–50 trades/day.
- ~8,640 balance snapshots/day (every 10s).
- Total: ~10,000 rows/day in a busy production run.

**Scaling Risk:**
- SQLite uses file-level locking; concurrent writes block each other.
- High volume of small writes → increased latency.
- At ~10x scale (100 games live at once), WAS could lock during balance recording.

**Threshold:** SQLite comfortably handles ~10K writes/day. At 100–1000 writes/sec, consider moving to PostgreSQL.

**Fix approach:**
- Current scale: no action needed.
- At 10x scale: switch to PostgreSQL with connection pooling.
- Or batch writes: collect 10–20 opportunities before inserting a single batch.

---

## Test Coverage Gaps

### **[High]** No Unit Tests for `extract_cents` Rounding Behavior

**Issue:** `extract_cents` is the critical boundary where Kalshi's API format enters the system. It's called hundreds of times but has no test coverage for:
- Rounding of `"0.885"` → 89 vs 88?
- Handling of `"0.00"`, `"1.00"`, `"0.99"`.
- Invalid inputs: `"abc"`, `None`, missing field.

**Files:** `src/predictions/kalshi_client.py` lines 19–27, `tests/` (missing tests)

**Risk:**
- A single-cent rounding error affects bet placement logic.
- Future changes to `extract_cents` could silently break price filtering.

**Test coverage to add:**
```python
def test_extract_cents_rounding():
    assert extract_cents({"yes_bid_dollars": "0.88"}, "yes_bid") == 88
    assert extract_cents({"yes_bid_dollars": "0.885"}, "yes_bid") == 89  # or 88?
    assert extract_cents({"yes_bid_dollars": "0.8849"}, "yes_bid") == 88
    assert extract_cents({"yes_bid": 88}, "yes_bid") == 88
    assert extract_cents({}, "yes_bid") == 0
```

---

### **[Medium]** No Integration Tests for Settlement Paths

**Issue:** Settlement happens via two paths (WS + REST poll). There are no integration tests that:
1. Mock a market settling via WS, verify Trade status changes.
2. Mock a market settling via REST, verify no double-update.
3. Test settlement with fees (fee_cents is None, 0, or positive).

**Files:** `tests/` (missing tests)

**Risk:**
- Settlement logic is mission-critical and untested.
- A bug in fee calculation could go unnoticed until real trades fail.

**Test coverage to add:**
- Mock `KalshiClient.get_market()` to return `status="settled"` with various results.
- Verify `Trade.pnl_cents` is calculated correctly.
- Verify idempotency: settling twice doesn't double-charge fees.

---

### **[Medium]** No Tests for ESPN Game Matching

**Issue:** The `match_kalshi_to_espn` function in `src/predictions/espn.py` matches Kalshi market tickers to ESPN games. It's heuristic-based and untested.

**Files:** `src/predictions/espn.py` (matching logic), `tests/` (missing tests)

**Risk:**
- A game could be matched to the wrong opponent (e.g., Game 1 matched to Game 2 in a series).
- Score/clock could be wrong, leading to false trade opportunities.

**Test coverage to add:**
```python
def test_match_kalshi_to_espn():
    espn_games = [
        GameState(away_team="LAL", home_team="GSW", ..., sport_path="basketball/nba"),
        GameState(away_team="LBJ", home_team="Steph", ..., sport_path="basketball/nba"),
    ]
    # Test: KXNBA-2026-LAL-GSW matches first game
    # Test: KXNBA-2026-GSW-LAL matches correctly (order)
    # Test: KXNBA-2026-LBJ-Steph doesn't match (no team abbrevs)
```

---

## Missing Critical Features

### **[Low]** No Monitoring/Alerting for Scanner Health

**Issue:** The scanner runs in the background. If it crashes silently (e.g., exception in `run_scanner`), bets stop being placed with no alert.

**Files:** `src/predictions/api.py` line 237 (scanner task spawned), `src/predictions/scanner.py` (exception handling)

**Current Mitigation:**
- Scanner writes logs to `scanner.log` (checked manually).
- CloudWatch can be configured but isn't automatic.

**Recommendations:**
1. Add a heartbeat: scanner writes `last_run_at` to a `heartbeat` table every 5 sec.
2. Dashboard shows "Scanner alive as of X seconds ago" in red if > 30 sec.
3. Send alert to Slack / PagerDuty if scanner is dead > 5 min.

---

### **[Low]** No Config Rollback / Undo

**Issue:** The runtime config (min price, bet %, sport leads) is stored in the SQLite `config` table and can be changed via the dashboard. If a bad config is set (e.g., `min_yes_price=1`), there's no rollback.

**Files:** `src/predictions/db.py` lines 255–308 (config getters/setters), `src/predictions/api.py` (config endpoints)

**Recommendations:**
1. Add a `config_history` table: log every config change with timestamp and old/new values.
2. Dashboard has a "Rollback to previous" button.
3. Or immutable configs: config changes only take effect after manual approval + delay (e.g., 60 sec).

---

## Dependencies at Risk

### **[Medium]** Kalshi API v3 → v4 Migration Path Unclear

**Issue:** Kalshi API v3.10 was released and introduced FixedPointDollar strings (e.g., `yes_bid_dollars` vs old `yes_bid` integer). If Kalshi releases v4 and deprecates v2 entirely, the migration path is unclear.

**Files:** `src/predictions/kalshi_client.py` (API client), `extract_cents` boundary

**Current Approach:**
- `extract_cents` handles both old (int) and new (dollar string) fields.
- But the BASE_URL and TRADE_API are hardcoded to v2.

**Risk:**
- If v2 is sunset, the entire client breaks overnight.

**Recommendations:**
1. Document v2 → v3/v4 migration path in a `MIGRATION.md` file.
2. Consider writing a parallel v3 client and A/B testing before sunsetting v2.
3. Monitor Kalshi's API changelog / announcements.

---

### **[Low]** Kalshi RSA Signature Verification (None)

**Issue:** The KalshiClient signs requests with RSA-PSS, but we never verify Kalshi's responses. If a MITM attacker intercepts API responses, they could return fake settlements.

**Files:** `src/predictions/kalshi_client.py` lines 70–80 (signing), `_get`, `_post` methods

**Current Security:**
- Requests are HTTPS (TLS).
- Kalshi's responses are not signed by them.

**Mitigation:**
- HTTPS + certificate pinning would be the next step.
- Or Kalshi could return signed responses (SHA256 signature of response body).

**Recommendation:** Low priority for now (HTTPS is sufficient for most threats). Revisit if trading large amounts.

---

## Anti-Patterns

### **[Medium]** Global `market_prices` Dict Without Locks

**Issue:** `src/predictions/scanner.py` line 56 declares a module-level dict `market_prices: dict[str, dict] = {}`. It's updated by the WS handler (`on_ticker`) and read by the Kalshi scan loop, but there's no lock protecting concurrent access.

**Files:** `src/predictions/scanner.py` lines 56, 818, 949–954

**Pattern:**
```python
market_prices[ticker] = {
    "yes_bid": yes_bid,
    "yes_ask": yes_ask,
    "volume": volume,
    "open_interest": data.get("open_interest", 0),
}
```

**Risk:**
- In CPython with GIL, dict writes are atomic. But in theory, if the write is interrupted mid-operation, a reader could get a half-updated dict.
- Low practical risk in asyncio (single-threaded), but fragile.

**Fix approach:**
1. Wrap reads/writes with `asyncio.Lock()`:
   ```python
   async with market_prices_lock:
       market_prices[ticker] = {...}
   ```
2. Or use `asyncio.Queue` or `collections.deque` for thread-safe updates.

---

### **[Low]** Hardcoded Sport Series List in `scanner.py`

**Issue:** `src/predictions/scanner.py` lines 77–90 hardcode a list of known sports series:

```python
SPORTS_GAME_SERIES = [
    "KXNBAGAME",  # NBA games
    "KXNFLGAME",  # NFL games
    ...
]
```

**Risk:**
- If Kalshi adds a new series (e.g., "KXNWSLGAME" for women's sports), it won't be discovered until the list is updated.
- There's also a dynamic fallback (lines 112–115) that checks for "GAME" / "FIGHT" keywords, but the hardcoded list is checked first.

**Fix approach:**
- Remove the hardcoded list; rely only on the dynamic keyword check.
- Or fetch the list from a config endpoint / Kalshi series API.

---

## Summary by Severity

| Severity | Count | Issues |
|----------|-------|--------|
| **Critical** | 1 | SQLite durability window |
| **High** | 4 | Settlement P&L duality, dashboard password salt, `extract_cents` boundary, no secret scanning |
| **Medium** | 8 | Volume extraction guard, WS subscription atomicity, SQLite scaling, monolith dashboard, ESPN field parsing, settlement test gap, config history, Kalshi API migration |
| **Low** | 4 | Scanner monitoring, global dict without locks, hardcoded series list, RSA verification |

---

*Concerns audit: 2026-04-30*
