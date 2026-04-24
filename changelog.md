# Changelog

All notable changes to `get-rich-slow` are documented here.

---

## [1.13.0] — 2026-04-20

### Fixed
- **Future Games Verification**: Fixed a vulnerability in `scan_kalshi_with_espn` matching logic where bets were placed on future games in a series (e.g. Game 2) based on the live score of a current game (e.g. Game 1). The scanner now verifies the Kalshi market's `expected_expiration_time` is within 12 hours of the current time.

---

## [1.12.0] — 2026-04-07

### Fixed
- **Kalshi API Order 400 Bad Request**: Resolved persistent `400 Bad Request` errors on `POST /portfolio/orders`. The v2 API strictly enforces enum constraints for `time_in_force` and rejects `"good_till_cancel"`. It has been corrected natively to `"good_till_canceled"`.
- **spec.md / tasks.md corrected**: Reverted test edits and accurately documented that the payload natively accepts `yes_price` as an integer while `time_in_force` enforces strict string tags.

### Added
- **Full Kalshi API v2 Audit**: Confirmed all other API calls (GET balance, events, markets, fills, positions) are using the correct formats natively without throwing integration errors.

---

## [1.11.9] — 2026-04-06


### Added
- **Total Fees Tracking**: Added explicit tracking and frontend display of Kalshi trading fees. The `Trade` metrics model was updated to natively record the inline taker `fee` from the `create_order` API response payload during the scan cycle. Settled trades correctly subtract this fee directly from their registered `pnl_cents`. Legacy unlogged fees are seamlessly deduced via aggregate delta mapping (`realized_pnl` — true account growth), ensuring all historically paid trading fees are correctly surfaced in real-time under a new "Total fees" badge on the overview dashboard.


## [1.11.8] — 2026-04-06

### Fixed
- **API Stat Overcounting**: Repaired a metric inflation bug where `Trade` attempts that threw a client or runtime error (status `error`) were being erroneously counted as real live deployed capital. They are now explicitly ignored from the UI's active/total cost roll-ups.

---

## [1.11.7] — 2026-04-06

### Added
- **Pre-Commit Linter Hook**: Integrated an automated `.git/hooks/pre-commit` deployment guard. The hook actively enforces all static type analysis (TypeScript/Ty) and linters (Ruff/Oxlint) on every commit specifically for modified files, ensuring broken code can never be checked into the repository or deployed.

---

## [1.11.6] — 2026-04-06

### Fixed
- **Scanner Python Syntax Error**: Restored scanner startup sequence by properly terminating the `WHAT_IF_STRATEGIES` internal dictionary block that was missing its closing brace.

---

## [1.11.5] — 2026-04-06

### Fixed
- **Kalshi API v2 Order Time & Cents Payload Fix**: Corrected the `create_order` API call inside `kalshi_client.py` to correctly send `yes_price` and `no_price` in integer cents instead of decimals. Modified the `time_in_force` parameter string to be exactly `"good_till_cancel"` (omitting the trailing 'ed') to rigidly adhere to the Kalshi API v2 specifications and prevent further 400 Bad Request invalid order errors.

## [1.11.4] — 2026-04-05

### Fixed
- **Kalshi API v2 Order Failures**: Refactored the `kalshi_client.py` request payload to strictly authenticate the Kalshi v2 `/trade-api/v2/portfolio/orders` validation logic. It strictly ignores identically typed dual-fields (dropping legacy `yes_price` cent integers alongside `yes_price_dollars`) to eliminate the `400 Bad Request` ("invalid_order") rejection, and correctly passes the now-mandatory `type: "limit"` flag and a runtime `client_order_id` UUID block.

## [1.11.3] — 2026-04-05

### Added
- **Tabbed Dashboard UX**: Completely overhauled `page.tsx` layout into top-level tabs (Overview, Charts, Sports, Live Games, Strategy, Config, Recent Trades). 
- **Sticky Navigation**: The headers and tabs are rendered directly beneath a sticky navigation ribbon with a glass backdrop (`backdrop-blur-md`) to eliminate scrolling up and down.
- **Local Test Mocking**: Added `test_sport_stats.py` to allow isolated injection and verification of complex DB query outcomes internally, specifically validating `MLB`/`MLBST` logic.

### Fixed
- **Recent Losses Tab Mapping**: The Recent Losses table correctly renders historical deficit positions irrespective of array limits by dynamically iterating the full SQL fetch block rather than truncating at 50 nodes.
- **Chart Axes Styling**: Refined histogram layout metrics across all components. Contract/Value charts now default to 85¢, shrinking horizontal deadweight bins. Time bounds on the time-based histogram models scale starting at 10 minutes, accompanied by correctly aligned numeric boundaries.
- **Strategy Backtester Miss-Tracking**: Rebuilt evaluator internals in `scanner.py` to correctly map `series_ticker` groupings off of market prefixes, eradicating duplicate sport counts due to blanket `KXMLBST` overlap anomalies on ESPN scoreboards while maintaining `MLB`/`MLBST` separation metrics securely. Strategy testing now correctly includes real, executed default markets as part of the total metric calculations.

## [1.11.1] — 2026-04-02

### Added
- **Remote Config Reset**: Added `DELETE /api/config` endpoint to wipe all DB config overrides remotely, reverting to `db.py` defaults without needing SSH or CLI access.

### Fixed
- **Next.js Proxy — Missing HTTP Methods**: The catch-all proxy route only exported `GET`, causing `DELETE` (and `PUT`) requests from the browser to return 405 Method Not Allowed. Refactored into a shared `proxyRequest` helper and exported all four methods (`GET`, `POST`, `PUT`, `DELETE`).
- **Sport Stats Charts Hidden After Shadow Wipe**: The chart filtered `played > 0`, hiding all sports when the shadow table was empty. Fixed to show any sport with wins or P&L data even if `played = 0`.
- **Basketball Config Defaults**: Restored `db.py` defaults to `180s (3m)` for NBA and NCAAMB final window — previously reverted to 300s by mistake.

---

## [1.11.0] — 2026-04-02

### Added
- **Sport Stats Charts**: New 3-panel bar chart section on the dashboard showing (1) total unique matches tracked per sport from shadow opportunities, (2) real-money trades won per sport, and (3) bidirectional net P&L per sport. All served from a new `/api/sport-stats` backend endpoint.
- **Time Left Column**: Added a `Time Left` column to the Recent Trades and Recent Losses tables displaying the ESPN clock at the moment of trade entry (`M:SS` format).
- **Remote Shadow Stats Reset**: Added `DELETE /api/stretch` endpoint to wipe shadow tracking history from anywhere without needing SSH access.
- **Config Reset CLI**: Added `python config_cli.py reset` command and `reset_all_config()` in `db.py` to clear all SQLite overrides and restore `_CONFIG_DEFAULTS` from `db.py`.

### Fixed
- **Shadow Strategy Duplicate Betting**: Fixed a bug where shadow strategies re-logged the same ticker every 5s after settlement. The deduplication query incorrectly filtered to `status == "open"` only, causing settled records to be invisible to the next iteration. Removed that filter so all historical records are checked.
- **MLBST Ticker Labels**: Fixed `KXMLBSTGAME` tickers rendering as the raw Kalshi series prefix in sport charts. Replaced the unordered dict-based prefix lookup with an ordered list ensuring `KXMLBST` is evaluated before `KXMLBG`.

---

## [1.10.0] — 2026-04-02

### Changed
- **Dynamic Percent-based Bet Sizing**: Replaced the static `max_bet_cents` absolute dollar amount configuration with a dynamic `bet_percent` system (defaults to 5%). The scanner now automatically interrogates the Kalshi API for current available cash right before processing opportunities, precisely scaling bet sizes to equal a configurable percentage of your liquid capital.
- **Configuration Reset CLI Utility**: Introduced `python config_cli.py reset` as a rapid developer tool to instantly truncate all manual SQLite table overrides, immediately forcing the framework parameters back to hardcoded `db.py` fallback defaults.
- Dashboard, CLI tools, and documentation were updated to utilize and format the new `bet_percent` system.

---
## [1.9.1] — 2026-03-29

### Security
- **Secure API Endpoints via Next.js Proxy**: The backend `/api/...` endpoints are now fully authenticated via `Depends(_check_token)` and inaccessible to public requests. To support the frontend, a catch-all proxy route (`dashboard/app/api/[...path]/route.ts`) was added to Next.js. This route verifies the user's browser session cookie and natively attaches the secret `API_TOKEN` before proxying requests to the FastAPI backend.
- **Hotfix (API Deployment Crash)**: Addressed an issue where the new API container crashed instantly on startup with `NameError: name '_check_token' is not defined`. The crash occurred because Python evaluated the `Depends(_check_token)` decorator before `_check_token` was defined at the bottom of the file. The definition was moved to the very top, and its signature was properly bound to `Header(None)` to natively enforce unauthorized rejections.

### Changed
- **Final Betting Window Tuning**: Adjusted `final_seconds` for NBA and College Basketball from 300 to 180 seconds to better align with game dynamics and reduce exposure risk.
- **Sport Mapping**: Temporarily disabled UFC fight scanning in `espn.py` due to unreliable scoreboard data matching.

---
## [1.9.0] — 2026-03-26

### Added
- **Dedicated Histogram API**: Implemented a lightweight `/api/histogram-trades` native SQL endpoint to deliver deep historical dataset arrays while avoiding full ORM/Pydantic serialization overhead. Decoupled full-history component fetches (histograms) away from recent-activity components (tables) to vastly improve frontend loading speeds.

### Fixed
- **Authentication Overhaul**: Resolved a severe bypass vulnerability where the auth session was checked against an easily forged external static string (`"authenticated"`). Sessions are now mathematically validated against a secure `SHA-256` digest hashed from the `DASHBOARD_PASSWORD`.
- **Pre-Auth Configuration Leak**: Patched an information disclosure bug where hitting the password prompt incorrectly forced the dashboard to render full internal scanner configurations before authorization occurred. 
- **Gateway Timeouts**: Mitigated a barrage of `504 Gateway Timeout` faults (incorrectly flagged client-side as CORS errors) across multiple APIs:
  - Parallelized `_get_live_games` with `asyncio.gather` for all outgoing Kalshi REST and ESPN HTTP queries to execute concurrently.
  - Rewrote the `/api/stretch-stats` DB query to strictly fetch raw primitive columns required for statistical aggregation, dropping the thousands of instantiated ORM models that deadlocked the application thread.
- **SVG Mobile Constraints**: Stripped `preserveAspectRatio="none"` declarations and rigidly fixed height classes off all rendered dashboard charts. They now utilize unified `aspectRatio: 800/200` blocks, rectifying extreme text squishing on narrow devices.

---

## [1.8.0] — 2026-03-24

### Added
- **Time Remaining Histograms**: Two new charts with minutes-remaining (15→0) on the X axis and 1-minute bins.
  - **Trade Distribution by Time Remaining**: Stacked green/red bars showing wins and losses per minute bucket.
  - **P&L by Time Remaining**: Bidirectional bar chart showing net P&L per minute bucket, green up / red down from a zero baseline.
- **`espn_clock_seconds` on Trade**: The game clock (seconds remaining) is now captured at trade placement time, stored in the DB, and exposed via the API. Existing trades show empty placeholders until new data accumulates.

---

## [1.7.0] — 2026-03-24

### Added
- **P&L by Contract Value Histogram**: A second histogram (below the count histogram) with the same 80–100¢ x-axis, showing net P&L per 1¢ bin. Green bars grow upward for profitable bins, red bars downward for losing bins, with a zero baseline proportionally dividing the chart area. Header badge shows total P&L across all settled trades.

---

## [1.6.0] — 2026-03-24

### Added
- **Contract Value Distribution Histogram**: A new SVG chart below the Account Value chart showing the distribution of accepted contract prices (80–100¢ range, 1¢ bins). Green bars show wins and red bars show losses, stacked per bin. Includes a hover tooltip with exact price range and win/loss counts.

### Fixed
- **SVG hover alignment**: Added `preserveAspectRatio="none"` to both the Account Value chart and the new histogram SVGs. Previously, on wide screens the SVG content was letterboxed (narrower than the element), causing mouse coordinates to map incorrectly and the hover highlight to appear offset from the cursor.

---

## [1.5.0] — 2026-03-23

### Features
- **Project Wrapup Skill**: Added a new agent skill (`project_wrapup`) to standardize the process of finalizing tasks, updating documentation, committing changes, and cutting git tags.
- **Improved Testing Skill**: Updated the local dashboard testing skill to automatically kill lingering processes on ports 8000 and 3777 before starting the servers.
- **UI Polish**: Refined the 'Pausing trading...' modal styling to accurately match the dashboard's gold/amber theme.

---

## [1.4.0] — 2026-03-23

### Features
- **Pause Trading**: Introduced a "Pause Trading" button in the dashboard header. The system can now temporarily halt placing new bets while keeping the scanner active and logging opportunities.
- **Agent Instructions & Skills**: Created `agents.md` instructing AI agents to thoroughly test changes. Added `local_dashboard_testing` skill to ensure AI agents have explicit fallback instructions for spinning up local development environments securely.

### Bug Fixes
- **Infra Configuration**: Passed the `API_TOKEN` explicitly into the `sst.aws.Nextjs` environment configuration in `sst.config.ts`. Previously, server actions running in AWS Lambdas failed to authenticate `PUT` requests to the Python API.

---

## [1.3.0] — 2026-03-22

### Features
- Added a "Recent Losses" tab to the dashboard to filter and display only trades that resulted in a loss.

---

## [1.2.0] — 2026-03-22

### Dashboard Additions & Fixes
- **UI Clean-up**: Removed unnecessary elements ("Inspiration", "Strategy") from the Next.js frontend to declutter the user interface. Cleaned up the "Get Rich Slow Scheme" from titles and made "Kalshi Sports Market Scanner" the main title of the app. Removed the shimmer animation from the title and removed the "Live 5s" text from the top right corner. The webpage tab now correctly displays "Kalshi Sports Market Scanner".
- **Mobile Responsiveness**: Fixed an issue where the "Recent Trades" and "Recent Opportunities" tables were squished or visually clipping on narrow viewports by wrapping them in `overflow-x-auto` to enable horizontal scrolling.

---

## [1.1.0] — 2026-03-22

### Infrastructure
- **EFS → S3 + ephemeral storage**: Eliminated EFS (~$8/month) by removing the EFS mount and loading the SQLite database from S3 into ephemeral `/tmp` storage at startup, and syncing it back on shutdown and periodically.

---

## [1.0.0] — 2026-03-22

First stable release. The bot has been running live on AWS, successfully scanning Kalshi prediction markets and placing bets on nearly-certain game outcomes.

### Features
- **Trading bot core**: Scanner polls ESPN live game data every 10 s and Kalshi markets via REST + WebSocket, placing bets when yes price ≥ 92¢ on games in their final minutes with a sufficient score lead.
- **Multi-sport support**: NBA, NHL, NFL, NCAAFB, NCAAMB, MLB, EPL, La Liga, MLS, UFC.
- **WebSocket price feed**: Real-time price updates from Kalshi WS ticker channel, seeded from REST API on startup.
- **Stretch strategy tracker**: Hypothetical "what-if" analysis for lower-priced entry points (85–91¢), tracked in `StretchOpportunity` table for strategy comparison.
- **FastAPI dashboard API**: REST endpoints for trades, opportunities, balance history, scans, live games, and scanner config.
- **Next.js dashboard**: Real-time frontend showing live games, trade history, PnL chart, and scanner config editor. Deployed via SST OpenNext (CloudFront + Lambda).
- **ECS + EFS deployment**: Single Fargate task (0.25 vCPU / 0.5 GB) running API + scanner together, SQLite persisted on EFS.
- **S3 DB backups**: Periodic SQLite snapshots pushed to S3 every 30 minutes.
- **Configurable parameters**: `min_yes_price`, `max_bet_cents`, `max_positions`, `min_volume`, per-sport `final_seconds` and `min_score_lead` — all editable at runtime via `/api/config`.
- **CLI**: `config_cli.py` for reading/writing scanner config from the terminal.

### Kalshi API v3.10.0 compatibility
- Added `extract_cents(d, prefix)` and `extract_volume(d)` helpers in `kalshi_client.py` to handle the REST API's new FixedPointDollars string format (`yes_ask_dollars`, `yes_bid_dollars`, `volume_fp`) while remaining backward-compatible with WebSocket integer fields.
- Updated all price extraction points in `scanner.py` (~10 occurrences) and `api.py` to use the new helpers.
- Added zero-price warning in WebSocket `on_ticker` handler to surface future field-name changes.
