# Tasks

## Completed

### Prevent Future Games Verification Bug (2026-04-20)
- **Context**: The scanner was incorrectly placing bets on future games (like Game 2 scheduled for 22.4) based on matching team abbreviations (PHX at OKC) during a live game between the same teams (e.g., Game 1 on 19.4).
- **Cause**: Kalshi opens markets for multiple games in a series simultaneously. The `match_kalshi_to_espn` function matched ESPN's live game data to any Kalshi market containing the matching team abbreviations without validating the game date/time, leading to bets on future events based on the LIVE state of the current game.
- **Changes made**:
  - `scanner.py`: Added checks in `scan_kalshi_with_espn` utilizing Kalshi's `expected_expiration_time`. Any market that expects to expire more than 12 hours from the current time or expired more than 12 hours ago is skipped. This prevents evaluating future (and stale) games in the same series.

### Kalshi API Order Price String Format Migration (2026-04-04)
- **Context**: Kalshi API v2 order creation accepts `yes_price` (integer cents) but introduced a new format `yes_price_dollars` (FixedPointDollars string).
- **Changes made**:
  - `kalshi_client.py`: Migrated `create_order` to format and include `yes_price_dollars` and `no_price_dollars` as strings instead of just relying on deprecated integer cents in `yes_price` / `no_price`.
  - `spec.md`: Updated the architectural specification to reflect that `yes_price_dollars` is the new standard.

### WebSocket Ticker Format Verification (2026-04-04)
- **Context**: The user asked to verify if Kalshi WebSocket ticker payload formats changed their price fields from integers to strings.
- **Verification made**:
  - Confirmed via `scanner.py` that `extract_cents` successfully falls back and parses both string dollars and integer objects gracefully, and no zero-price warnings were seen in production logs.

### Dashboard Authentication Vulnerability Fix (2026-03-26)
- **Context**: The user inquired about the security of the Next.js frontend deployed to `matej-kalshi.pp.ua`. It was discovered that the authentication check in `dashboard/app/actions.ts` relied on validating the session cookie `predictions_auth` strictly against a static hardcoded string `"authenticated"`.
- **Cause**: Because the validation string was not a secret, any external malicious actor could manually forge a browser cookie (e.g., in Chrome devtools) `predictions_auth=authenticated` and entirely bypass the password screen. This would have granted them full unverified authorization to hit the `PUT /api/config` backend endpoint under the server's identity.
- **Changes made**:
  - `actions.ts`: Changed `COOKIE_VALUE` to derive from a server-side `SHA-256` hash seeded with the `process.env.DASHBOARD_PASSWORD`. Since the password explicitly never touches the client browser bundle, attackers cannot reverse-engineer or forge the authenticated cookie session value.

### Refine Account Value Chart Labels (2026-04-02)
- **Changes made**:
  - Removed the green sliding current-value price text from the far-right edge of the `PnlChart` line to match user preference.
  - X-axis labels that contain spaces (like the "Trade" view's `"M/D h:mm"`) now split into multiple lines using SVG `<tspan>` tags. This cuts character width in half, stopping the text from colliding/overlapping horizontally when there are 20 tight data points.

### Account Value Chart Flatline Fix (2026-04-02)
- **Context**: The PnlChart was completely flat at the "Now" level even when actual P&L existed.
- **Cause**: The `/api/histogram-trades` query lacked the `placed_at` field in its `SELECT` list. `PnlChart` filtered out all trades without `placed_at`, resulting in zero trades rendered, which caused the mathematical offsets to evaluate to flatlines due to matching Start and Now balances.
- **Changes made**:
  - `api.py`: Added `Trade.placed_at` to the `histogram-trades` query `SELECT`. Used `getattr` to safely `.isoformat()` the result to prevent 500 crashes if the DB adapter returned an unparsed string.
  - `page.tsx`: Added a fallback in the `PnlChart` root so if `allTrades` is missing `placed_at` entirely (due to slow deploy or aggressive CDN caching), it gracefully falls back to `trades` (which is limited to 50 but visually identical to the old chart rather than flatlining).

### Fix 429 Rate-Limit + 502 on sport-stats (2026-04-02)
- **Context**: Dashboard was sending 7 parallel requests every 5 seconds = 84 req/min, triggering Cloudflare/Lambda 429 rate limits on `/api/balance-history` and `/api/config`. `/api/sport-stats` also returned 502 (slow DB query timing out).
- **Root cause**: All 7 endpoints were in the fast poll, including completely static ones (config, stretch-stats, sport-stats) and a dead one (balance-history — state was set but never read).
- **Changes made** (`dashboard/app/page.tsx`):
  - Removed `balance-history` fetch entirely (dead state).
  - Fast poll now fetches only `stats`, `trades`, `opportunities` every **10s** (was 7 endpoints every 5s).
  - Slow poll (60s) now consolidates `histogram-trades`, `stretch-stats`, `config`, `sport-stats`.
  - Net result: **~10 req/min** down from 84 req/min (~88% reduction).

### Account Value Chart: 20-Point Window + Hover Fix (2026-04-02)
- **Context**: Chart showed only last 50 trades (fast-poll cap). Hover snapped to wrong y-position (intermediate step-function helper points). Tooltip was missing P&L delta. Header/baseline showed all-time starting balance even in windowed view.
- **Changes made**:
  - `dashboard/app/page.tsx` — **PnlChart** (`allTrades` already wired from previous session):
    - Added `WINDOW = 20` slicing: `buckets.slice(-20)` for the visible window, `hiddenBuckets.reduce(...)` accumulates earlier P&L into `windowStartBalance`.
    - Fixed `findClosest` to only snap to labeled data points (`snapPoints = points.filter(p => p.label !== "")`), eliminating snapping to step-function horizontal helper points (which caused the tooltip to appear at the wrong height with a blank label).
    - SVG baseline dashed line, baseline label, area gradient, and current-value line now all use `windowStartBalance` / `totalNow >= windowStartBalance` instead of `startingBalance` / `totalPnl`.
    - Header shows `"last 20"` badge when history is truncated, and the P&L badge reflects the windowed range (`totalNow - windowStartBalance`).

### Account Value Chart: Multi-Period View Toggle (2026-04-02)
- **Context**: User wanted to see the account value chart bucketed by day/week/month, not just one point per trade.
- **Changes made**:
  - `dashboard/app/page.tsx`: Added `viewMode` state (`trade | day | week | month`) to `PnlChart`. Settled trades are grouped into time buckets using a `Map` (preserving insertion order). One step-function point is emitted per bucket. X-axis labels adapt: `M/D H:MM` for trade, `M/D` for day, `M/D` (week start) for week, `Mon YY` for month. Hover tooltip shows period P&L and the period label in non-trade modes. A pill-style toggle button group is rendered in the chart header.

### Histogram X-Axis Alignment Fix (2026-04-02)
- **Context**: The 80–100¢ x-axis labels in ContractValueHistogram and PnlHistogram were offset by ~half a bar width — the label for 99¢ appeared under the 98¢ bar, etc.
- **Cause**: Labels were placed at bin *edges* (21 positions for 20 bins) using `binFrac * chartW`, while bars are drawn at `toX(i) + barW/2` (centered in each slot with a gap).
- **Changes made**:
  - `dashboard/app/page.tsx`: Replaced `numBins + 1` edge-based labels with `numBins` bar-centered labels at `toX(i) + barW / 2` in both histograms.

### Fix Crash on API Error Responses (2026-04-02)
- **Context**: Production frontend crashed with `TypeError: Cannot read properties of undefined (reading 'length')` immediately after page load.
- **Cause**: The fast-poll `fetchData` function in `page.tsx` called `setTrades((await tradesRes.json()).trades)` etc. without checking `res.ok` first. When the API returns a non-200 (e.g., 401/403 error JSON like `{"detail":"Unauthorized"}`), `.trades` / `.opportunities` / `.snapshots` are `undefined`. State was set to `undefined`, causing all downstream `.filter()` / `.length` calls to crash.
- **Changes made**:
  - `dashboard/app/page.tsx`: Added `.ok` guards to all `set*` calls in the data-fetching loop. Also added `?? []` fallbacks for array-typed state to be safe.

### Post-Deploy Bug Fixes (2026-04-02)
- **Context**: Several issues found after deploying v1.11.0 — proxy missing DELETE, sport charts invisible after shadow wipe, remote config stuck at wrong values.
- **Changes made**:
  - `dashboard/app/api/[...path]/route.ts`: Refactored into shared `proxyRequest()` helper; exported `GET`, `POST`, `PUT`, `DELETE` — previously only `GET` existed, causing all mutation endpoints to 405.
  - `api.py`: Added `DELETE /api/config` endpoint to clear all DB config overrides remotely.
  - `dashboard/app/page.tsx`: Fixed `SportStatsCharts` filter from `played > 0` to `played > 0 || wins > 0 || pnl !== 0` so charts survive shadow table being wiped.
  - `db.py`: Restored NBA/NCAAMB `final_seconds` default to `180` (previously reverted to `300` by mistake).

### Sport Stats Charts + Bug Fixes (2026-04-02)
- **Context**: User requested per-sport bar charts (total matches played, wins, P&L) and various dashboard/backend fixes.
- **Changes made**:
  - `api.py`: Added `/api/sport-stats` endpoint aggregating unique match counts from `stretch_opportunities` and real P&L/wins from `Trade`.
  - `api.py`: Added `DELETE /api/stretch` to wipe shadow tracking history remotely via authenticated API call.
  - `api.py`: Fixed `KXMLBSTGAME` ticker label resolution — replaced unordered dict prefix map with ordered list so `KXMLBST` is matched before the overlapping `KXMLBG`.
  - `api.py`: Extended `/api/histogram-trades` to include `ticker` and `event_ticker` columns.
  - `scanner.py`: Fixed shadow strategy duplicate-logging bug — removed `status == "open"` filter from deduplication queries so settled records block re-creation.
  - `db.py`: Added `reset_all_config()` helper to truncate the `config` override table atomically.
  - `config_cli.py`: Wired `python config_cli.py reset` command.
  - `dashboard/app/page.tsx`: Added `SportStatsCharts` 3-panel component (Total Matches Tracked, Trades Won, Net P&L) with data from new endpoint.
  - `dashboard/app/page.tsx`: Added `Time Left` column to Recent Trades and Recent Losses tables from `espn_clock_seconds`.
  - `dashboard/app/page.tsx`: Added `event_ticker` field to `Trade` TypeScript interface.

### Remaining Time Display in Trades Table (2026-04-02)
- **Context**: The user asked to add a column indicating the time remaining until the end of the match when a trade is executed. 
- **Changes made**:
  - `dashboard/app/page.tsx`: Embedded a `Time Left` column within the Next.js `Recent Trades` and `Recent Losses` tab views. It mathematically formats `espn_clock_seconds` into an intuitive countdown timestamp (`M:SS`).
### CLI Configuration Hard Reset Utility (2026-04-02)
- **Context**: The user asked for a method to easily wipe manual database overrides and forcefully return all tunable parameters to their original `db.py` defaults.
- **Changes made**:
  - `db.py`: Added a `reset_all_config()` helper that securely truncates all records in the `ConfigEntry` SQLAlchemy override table.
  - `config_cli.py`: Wired up `python config_cli.py reset` functionality natively.
  - `CLAUDE.md`: Documented the new CLI command mapping.

### Dynamic Percent-based Bet Sizing (2026-04-02)
- **Context**: The user wanted to size bets as a dynamic percentage of available cash instead of an absolute cents value per match.
- **Changes made**:
  - `db.py`: Replaced `max_bet_cents` with `bet_percent` globally with a default allocation of `5` (5%).
  - `scanner.py`: Invocations inside `scan_kalshi_with_espn` now call `KalshiClient.get_balance()` locally to accurately query the account's available uninvested cash right before calculation.
  - `scanner.py`: Dynamically computes `max_bet_cents` strictly at evaluation time as `available_cash * (bet_percent / 100.0)`.
  - `api.py`: Updated endpoints to reflect, accept, and parse `bet_percent` instead of `max_bet_cents`.
  - `dashboard/app/page.tsx`: Updated the dashboard GUI to render the "Max Bet" dashboard status panel logically under the new percent format (`5%`).
  - `config_cli.py` & `CLAUDE.md`: Rewrote CLI mappings and specifications to enforce the updated tunable parameter variable namespace.

### Secure API Endpoints via Next.js Proxy
- **Context**: The `/api/...` endpoints on the FastAPI backend were exposed publicly without authentication (except for `PUT /api/config`). Data could be scraped or accessed directly without providing the dashboard password.
- **Changes made**:
  - `api.py`: Added `Depends(_check_token)` to all `GET` endpoints (e.g., stats, trades, config), ensuring only requests with the correct `Bearer` token can access the data. The root health check (`/`) remains public for AWS ELB checks.
  - `dashboard/app/page.tsx`: Replaced the hardcoded frontend `API` absolute URL with a relative path `""`, forcing the client-side app to route all requests back to the Next.js server.
  - `dashboard/app/api/[...path]/route.ts`: Created a Next.js API catch-all route to securely proxy the requests. It first verifies the browser's authentication cookie (`checkAuth()`) and then manually attaches the secret `API_TOKEN` environment variable in the headers before transparently relaying the request to the FastAPI backend.

### Sport Mapping and Timing Adjustments
- **Context**: Some sports required adjustments to their final betting windows based on live observations.
- **Changes made**:
  - `db.py`: Reduced `final_seconds` for NBA and Men's College Basketball from 300 to 180 seconds to reduce risk in high-score-volatility sports.
  - `espn.py`: Disabled UFC fight mapping until better scoreboard reliability is achieved.

### Kalshi API v2 Price Format Migration (2026-03-16)
- **Context**: Kalshi changed market price fields from integer cents to string dollars
  - `yes_ask` → `yes_ask_dollars` (e.g. `92` → `"0.9200"`)
  - `yes_bid` → `yes_bid_dollars` (e.g. `91` → `"0.9100"`)
  - `volume` → `volume_fp` (e.g. `500` → `"500.00"`)
- **Changes made**:
  - `kalshi_client.py`: Added `extract_cents(d, prefix)` and `extract_volume(d)` helpers that gracefully handle both old integer format (WebSocket) and new dollar-string format (REST API)
  - `scanner.py`: Updated all price extraction points to use the new helpers (~10 occurrences), added defensive WS zero-price warning
  - `api.py`: Updated live-games endpoint price extraction
  
### EFS → S3 + ephemeral storage migration
- **Context**: EFS was costing ~$8/month (mostly mount targets), which is unnecessary for a small SQLite database that just needs intermittent persistence.
- **Changes made**:
  - `api.py`: Added `_download_db` and `_backup_db_sync` to download `predictions.db` from S3 on startup and upload it back on graceful shutdown.
  - Periodic syncing is still handled by the existing 30-min backup loop in `scanner.py`.
  - `sst.config.ts`: Removed EFS construct and replaced `DATABASE_URL` mount path (from `/data` to `/tmp`).
  - `spec.md`: Updated architecture documentation to reflect the removed EFS dependency.

### Dashboard UI Refactoring
- **Context**: The Dashboard featured extraneous information ("The Strategy", "Inspiration"). It also had a long title.
- **Changes made**:
  - `page.tsx`: Removed the "Inspiration" and "The Strategy" sections from the dashboard and login view.
  - `page.tsx`, `layout.tsx`, `opengraph-image.tsx`, `twitter-image.tsx`: Refactored the title to act as the main title: "Kalshi Sports Market Scanner", replacing "Rager's Get Rich Slow Scheme" entirely.
  - `globals.css`: Removed the shimmer animation from the `gold-shimmer` class to stop the title animation.
  - `page.tsx`: Removed the "Live 5s" text and indicator from the top right corner.
  - `layout.tsx`: Changed the webpage tab title to "Kalshi Sports Market Scanner".
  - `page.tsx`: Wrapped the "Recent Trades" and "Recent Opportunities" tables in an `<div className="overflow-x-auto">` container to ensure horizontal scrolling works properly on smaller mobile screens.

### Add "Recent Losses" Tab
- **Context**: The user wanted to easily filter out and review the trades that resulted in a loss.
- **Changes made**: 
  - `page.tsx`: Added a new "Recent Losses" tab. The table dynamically filters the `trades` array for items where `t.pnl_cents !== null && t.pnl_cents < 0`.

### Add Pause/Resume Trading Button
- **Context**: The user wanted to pause and resume trading directly from the dashboard.
- **Changes made**:
  - `db.py`: Added `trading_paused` to default configurations.
  - `api.py`: Updated the /api/config endpoint to expose the `paused` boolean based on the `trading_paused` key.
  - `actions.ts`: Added a new `updateConfig` server action to proxy the PUT request successfully.
  - `page.tsx`: Added a Pause/Resume Trading button in the header. The app config state now tracks `paused` correctly.
  - `scanner.py`: Added a run-time check before `place_bet` effectively blocking any new orders while trading is paused.
  - `page.tsx`: Refined the 'Pausing trading...' modal styling to accurately reflect the dashboard's gold/amber theme.

### Write Agents Instructions
- **Context**: The user requested that I add an instruction file named `agents.md` instructing agents to always test their newly implemented features.
- **Changes made**:
  - `agents.md`: Created the file with the instruction.

### Create Testing Skill
- **Context**: The testing process involved fixing multiple local environment issues (`API_TOKEN`) and using complex tool sequences. The user requested this knowledge be captured.
- **Changes made**:
  - `SKILL.md`: Created a new structural `.agents/skills/local_dashboard_testing/SKILL.md` file documenting the exact configuration needed for tests.

### Fix AWS Next.js API_TOKEN Missing Bug
- **Context**: The user deployed the app but kept receiving a 401 Unauthorized API error from AWS specifically.
- **Changes made**:
  - `sst.config.ts`: Mapped `API_TOKEN: apiToken.value` correctly into the Next.js `environment` configuration. The lambda running Server Actions could not pass the token securely because it previously lacked context of it.
  - `api.py`: Reverted the local auth-bypassing override check that we previously tried injecting.

### Update Testing Skill
- **Context**: The testing skill occasionally failed because the previous servers were still running on ports 8000 and 3777.
- **Changes made**:
  - `local_dashboard_testing/SKILL.md`: Added a `fuser -k` step to clear stalled processes before starting the backend and frontend.

### Create Wrapup Skill
- **Context**: The user requested a systematic way to wrap up projects, including updating documentation and cutting a git tag.
- **Changes made**:
  - `project_wrapup/SKILL.md`: Created `.agents/skills/project_wrapup/SKILL.md` enclosing complete steps for finalizing a project.

### Add Contract Value Distribution Histogram (2026-03-24)
- **Context**: The user wanted a visual breakdown of which contract price ranges (¢) tend to win vs lose.
- **Changes made**:
  - `page.tsx`: Added `ContractValueHistogram` component — an SVG histogram rendered in the same card style as the Account Value chart. Settled trades are bucketed into 1¢-wide bins (80–100¢). Green bars = wins stacked above red bars = losses. X-axis shows price in ¢, Y-axis shows count. Hover tooltip shows the exact price range and win/loss counts. The component is rendered immediately below the Account Value chart.
  - `page.tsx`: Fixed SVG hover alignment on both the Account Value chart and the histogram by adding `preserveAspectRatio="none"`.

### Add P&L by Contract Value Histogram (2026-03-24)
- **Context**: The user wanted to see the net P&L contribution of each 1¢ price bin, not just trade counts.
- **Changes made**:
  - `page.tsx`: Added `PnlHistogram` component. Same 80–100¢ x-axis and 1¢ bins. Y-axis shows net `pnl_cents` per bin — green bars grow upward (profit), red bars downward (loss) from a zero baseline. Chart area proportionally splits between positive and negative zones. Header badge shows total settled P&L. Rendered immediately below `ContractValueHistogram`.

### Add Time Remaining Histograms (2026-03-24)
- **Context**: The user wanted to visualise trade distribution and P&L by how much time was left in the game when the bet was placed.
- **Changes made**:
  - `db.py`: Added `espn_clock_seconds INTEGER` column to the `Trade` model with an automatic `ALTER TABLE` migration so existing databases are upgraded on next startup.
  - `scanner.py`: Populated `espn_clock_seconds` from `espn_game.clock_seconds` in the opportunity dict and saved it on the `Trade` row at bet placement time.
  - `api.py`: Added `espn_clock_seconds: Optional[int]` to `TradeResponse` Pydantic model and serialised it in the `get_trades` endpoint.
  - `page.tsx`: Added `espn_clock_seconds` to the `Trade` interface. Added `TimeHistogram` (stacked win/loss count bars) and `TimePnlHistogram` (bidirectional P&L bars) components — both with 15 one-minute bins, X axis 15m → 0m. Only includes countdown-sport trades with `espn_clock_seconds ≤ 900`. Rendered after the contract-value histograms.

### Histogram Full Trade History (2026-03-26)
- **Context**: All four histogram charts (`ContractValueHistogram`, `PnlHistogram`, `TimeHistogram`, `TimePnlHistogram`) were only showing the most recent 50 bets because they consumed the same `trades` state that powered the "Recent Trades" table.
- **Changes made**:
  - `page.tsx`: Added a separate `allTrades` state and split data-fetching into two `useEffect` loops:
    1. **Fast poll (5s)**: fetches stats, 50 recent trades, opportunities, balance, stretch stats, config — powers the live dashboard panels and trade table.
    2. **Slow poll (60s + new-trade trigger)**: fetches full trade history (`limit=10000`) — powers all four histogram components. Also re-fires immediately whenever `trades[0].id` changes, ensuring a new bet shows up in histograms without waiting 60s.

### SVG Chart Aspect Ratio Fix (2026-03-26)
- **Context**: The text in the Account Value chart and all histograms was stretched vertically on mobile viewports. The SVGs used `preserveAspectRatio="none"` and were forced into a fixed height (`h-48` or 192px), causing non-uniform scaling when the container aspect ratio differed from the viewBox's 4:1 ratio.
- **Changes made**:
  - `page.tsx`: Removed `preserveAspectRatio="none"` from all 5 SVGs.
  - `page.tsx`: Replaced `h-48` with uniform `style={{ display: 'block', aspectRatio: '800/200' }}` so chart height correctly scales proportional to screen width, fixing distorted rendering on narrow mobile screens.

### Local Testing Skill Update (2026-03-26)
- **Context**: The browser subagent executing tests sent a rogue Ctrl+C keystroke, which killed the local `pnpm run dev` foreground process and resulted in an unreachable frontend server `ERR_CONNECTION_REFUSED`.
- **Changes made**:
  - `local_dashboard_testing/SKILL.md`: Updated API and frontend server startup instructions to prepend `setsid` (`setsid uv run...` and `setsid pnpm run...`), detaching them from the terminal's tty block so they are immune to keyboard SIGINT (Ctrl+C).

### Fix 504 Gateway Timeout (CORS error) on Large Data Fetch (2026-03-26)
- **Context**: The remote frontend encountered CORS errors combined with `504 Gateway Timeout` errors when fetching from `/api/trades?limit=10000`, `/api/balance-history?limit=200`, and `/api/config`. 
- **Cause**: Fetching 10,000 DB rows sequentially using SQLAlchemy and Pydantic takes significant processing time (seconds) on resource-constrained cloud environments (like standard Lambda deployments). This CPU-bound task blocked the Python event loop, causing the ALB / API Gateway to timeout and terminate the connection (504). Because the connection was abruptly dropped by the gateway, the expected `Access-Control-Allow-Origin` HTTP headers were missing from the response, causing the browser to misreport the issue primarily as a CORS error.
- **Changes made**:
  - `api.py`: Created a dedicated `/api/histogram-trades` endpoint. This queries SQLite directly, asking only for the 5 necessary columns (`id`, `yes_price`, `pnl_cents`, `status`, `espn_clock_seconds`) and bypasses full SQLAlchemy ORM hydration and Pydantic validation. The data is piped directly to a flat JSON object.
  - `page.tsx`: Updated the slow histogram poll to call `/api/histogram-trades` and safely restored the `limit=10000` parameter.

### Fix 504 Gateway Timeout on Secondary Endpoints (2026-03-26)
- **Context**: The `/api/live-games` and `/api/stretch-stats` endpoints were occasionally throwing `504 Gateway Timeout` errors, masked as CORS failures, similar to the historical trades fetch.
- **Cause**:
  - `/api/live-games`: Was making 20+ sequential HTTP calls to the Kalshi REST API and ESPN scoreboards natively in a synchronous 1-by-1 `for` loop, causing the connection to exceed the 29-second API Gateway limit during transient network slowness.
  - `/api/stretch-stats`: Was querying the DB via `session.query(StretchOpportunity).all()`. Since stretch opportunities track near-misses, this table grows massively over time, meaning it was loading 10,000+ full ORM models sequentially, locking the event loop via the GIL.
- **Changes made**:
  - `api.py`: Refactored `_get_live_games()` to use `asyncio.gather` for making all external Kalshi and ESPN asynchronous HTTP requests fully in parallel, cutting total resolve time to the single slowest request instead of traversing them natively in series.
  - `api.py`: Rewrote the `get_stretch_stats` DB query to strictly select the `<enum, int>` column values it actually calculates stats against (`status`, `pnl_cents`, `reason`, `strategy_set`). Built extremely fast transient `namedtuple` mappings in place of the massive ORM pipeline.

### Dashboard UX & Tabbed Navigation (2026-04-05)
- **Context**: The dashboard grew too long vertically with multiple new charts and metrics.
- **Changes made**:
  - `page.tsx`: Split the main layout into a top-level tabbed view covering: Overview, Charts, Sports, Live Games, Strategy, Config, and Recent Trades.
  - Placed the header and the tabs map inside a `sticky top-0 bg-black/95 backdrop-blur-md` wrapper so the navigation header is always beautifully visible, obscuring content underneath gracefully while scrolling vertically.

### Chart Tweaks & Losses Tab Fixes (2026-04-05)
- **Context**: The user requested adjustments to chart offsets and correct behavior for the Losses tab.
- **Changes made**:
  - `page.tsx`: Updated `ContractValueHistogram` and `PnlHistogram` to use an 85¢ to 100¢ scale instead of 80¢.
  - Updated `TimeHistogram` and `TimePnlHistogram` limits to start from 10 minutes instead of 15.
  - Re-centered the min/max X-axis ticks.
  - Adjusted the "Recent Losses" tab to correctly loop over `allTrades` rather than the `trades` short-list map to show all historical losses correctly.

### What-If Strategy Tracker Fixes (2026-04-05)
- **Context**: What-if shadow tracking exhibited multiple bugs: MLB double counting, skip-logic excluding real baseline games, and inaccurate unique match aggregation due to a bad config overwrite.
- **Changes made**:
  - `api.py`: Updated `seen_matches` SQL query to group by `series_ticker` directly, and restored `KXMLBST` routing inside `ticker_prefix_map` to maintain permanent metrics separation between `MLB` and `MLBST`. `test_sport_stats.py` securely validates this.
  - `scanner.py`: Removed the hard `continue` short-circuit in the evaluation step so that stretch trackers now accurately log *all* opportunities they would have bet on, not just near-miss events.
  - `scanner.py`: Fixed the event ticker population step (`event_ticker = series_ticker`) bug where near-miss opportunities accidentally wrote their generic sport string over the localized unique ID. Unique shadow games are now accurately tracked by `/api/stretch-stats`.
  - Scrapped the `sniper` strategy block inside `WHAT_IF_STRATEGIES` dictionary so it unhooks entirely from DB and Dashboard rendering.

### Kalshi API v2 Order Creation 400 Bad Request Fix (2026-04-06)
- **Context**: The `create_order` API call was returning 400 Bad Request: `Field validation for 'TimeInForce' failed on the 'oneof' tag`.
- **Changes made**:
  - `kalshi_client.py`: Updated `time_in_force` default parameter to exactly `"good_till_canceled"` instead of `"good_till_cancel"`. The API strictly validates this string under its `oneof` constraint.
  - Reverted earlier test attempts parsing `yes_price` as a string/float since the live payload natively accepted `yes_price` as an integer.
  - `spec.md`: Updated API notes to reflect the correct enumeration limits.

### Kalshi API v2 Full Request Audit (2026-04-07)
- **Context**: All API calls were audited against the v2 spec.
- **Findings**:
  - All GET endpoints use correct parameters.
  - `extract_cents()` gracefully parses live responses. No further changes needed.

### Fix Syntax Error in scanner.py (2026-04-06)
- **Context**: The `WHAT_IF_STRATEGIES` dictionary inside `scanner.py` was missing its closing brace, causing a `SyntaxError: '{' was never closed` immediately upon execution (preventing the backend and cron tasks from starting).
- **Changes made**:
  - `scanner.py`: Appended the missing closing brace (`}`) to properly complete the `WHAT_IF_STRATEGIES` dictionary block, restoring application startup stability.

### Linter and Static Analysis Hook (2026-04-06)
- **Context**: The user requested that we enforce linters and static code analysis automatically to ensure broken code is never checked in and deployed.
- **Changes made**:
  - `.git/hooks/pre-commit`: Created a local git hook that automatically executes the `scripts/pre-commit-check.sh` script on every commit, formatting and linting Python and TypeScript files before allowing the commit to succeed.

### Fix error trade aggregation (2026-04-06)
- **Context**: The dashboard was incorrectly calculating the total number of trades and overall money deployed by inadvertently including "error" state trades that had failed to execute remotely.
- **Changes made**:
  - `api.py`: Implemented explicit `Trade.status != "error"` query filters across the backend's `/api/stats` aggregate endpoints (cost sums and row counts) to prevent bloated financial accounting on the frontend view.

### Deduplicate error state trades per match (2026-04-06)
- **Context**: The recent trades panel in the UI showed the same error state bet multiple times per match when the scanner continuously retried failed trades.
- **Changes made**:
  - `api.py`: Modified `get_trades` to fetch extra rows and dynamically deduplicate duplicate `"error"` state trades per match (`event_ticker`), ensuring the UI only renders them once per specific game in the recent trades view.

### Track Kalshi trading fees and calculate true P&L (2026-04-06)
- **Context**: The user requested that total fees paid be explicitly tracked and displayed on the dashboard next to the number of trades. Previous trades did not account for Kalshi's fees in their specific `pnl_cents`.
- **Changes made**:
  - `db.py`: Added nullable `fee_cents` column to the `Trade` model with a dynamic SQLite `ALTER TABLE` migration.
  - `scanner.py`: Updated `place_bet` to parse and retro-save Kalshi's embedded order `fee` dynamically. Updated the win/loss settlement logic so that the `fee_cents` correctly reduces the final recorded `pnl_cents`.
  - `api.py`: Updated `StatsResponse` and `get_stats` logic. Aggregates all previously recorded fees linearly, and calculates unrecorded fees on old trades historically using a strict ledger validation against the true raw account growth (`realized_pnl - (current_balance - 20000)`).
  - `dashboard/app/page.tsx`: Embedded a new `Total Fees` dedicated stat box symmetrically next to the `Trades` card layout within the overview panel.

### Kalshi Order 400 Fix: Revert to Integer Cents (2026-04-08)
- **Context**: Despite the previous migration to `yes_price_dollars` (string), orders were still returning 400. Web search + Kalshi docs confirm the v2 API expects `yes_price` as an **integer in cents** (1–99), not a string-dollars field.
- **Root cause**: The `yes_price_dollars` approach was incorrect — the API does not accept that field and returns 400.
- **Changes made**:
  - `kalshi_client.py`: Reverted `create_order` to send `yes_price: int` (integer cents, 1–99) and `no_price: int`. Removed `yes_price_dollars`/`no_price_dollars` string format entirely.
  - `kalshi_client.py`: Added detailed error logging in `_post` that captures and logs the response body (Kalshi's validation message) alongside the sent payload before raising, to aid future debugging.

## Backlog