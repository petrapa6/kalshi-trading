# Kalshi Trading Scanner

Glossary for the system that scans Kalshi sports prediction markets against live ESPN game state and buys near-certain YES contracts before the market re-prices.

## Language

### Kalshi market domain

**Series**:
A family of markets for one competition type (e.g. NBA games, EPL games).
_Avoid_: league (that's the ESPN side)

**Event**:
One real-world game or fight within a series.
_Avoid_: game (reserve for the ESPN side), match

**Market**:
A single YES/NO contract offering on one outcome of an event. The unit the scanner evaluates and trades; identified by its ticker.

**Contract**:
One YES share of a market. Pays 100¢ if the market settles YES, 0¢ otherwise.
_Avoid_: share, unit

**Yes ask / Yes bid**:
The lowest offered / highest bid price for a YES contract, in cents.
_Avoid_: price (unqualified)

**Profit per contract**:
The win payoff of one contract at entry: 100¢ minus the yes ask.
_Avoid_: spread (historical misnomer — reads as ask−bid), edge

**Settlement**:
The moment a market's outcome is finalized and the system reconciles its open trades into wins or losses.
_Avoid_: resolution, expiry

### Game state (ESPN)

**Game**:
A live real-world competition as reported by ESPN. The counterpart a market gets matched to.

**Matching**:
Pairing a Kalshi market with the ESPN game it settles on, by team abbreviations.

**Team alias**:
An alternative identity for one team across data sources — ESPN abbreviation vs Kalshi ticker code, or Kalshi title name vs API-Football name. All alias knowledge lives in one reconciliation surface.
_Avoid_: mapping, abbreviation table

**Final period**:
A live game in its last regulation period (4th quarter, 9th inning, 2nd half). The broad net.

**Final minutes**:
A game in its final period that has also crossed the sport's configured end-of-game clock threshold. Strictly narrower than final period; the live-trade entry window.
_Avoid_: endgame, closing minutes

**Lead**:
The absolute score difference between the two teams.
_Avoid_: margin, spread

**Elapsed minutes**:
Game-clock minutes since the start, normalized across count-up (football) and count-down (basketball, NFL, NHL) clocks. Undefined for clockless sports (baseball).

**Sport family**:
Coarse sport grouping used in strategy definitions. UK terminology: "football" is association football; the NFL family is "american_football".
_Avoid_: soccer (in strategy vocabulary)

**Sport path**:
ESPN's fine-grained sport/league identifier (e.g. `hockey/nhl`, `soccer/eng.1`) — the taxonomy the scanner and per-sport config operate on.

**Sport**:
One entry in the sport registry: a sport path together with its structural facts (clock direction, final period, period length, display name) and tunable defaults (lead, final seconds). Multiple series can share one sport.

**Sport registry**:
The single canonical catalog of sports and series the system knows. Every per-sport lookup — clock semantics, matching eligibility, scan list, display names, config defaults — derives from it.
_Avoid_: sport config, sport table

**Matchable**:
A series whose markets are paired with ESPN games. A non-matchable series is still scanned but never matched, so never traded live.
_Avoid_: enabled, active

### Trading

**Opportunity**:
A market that passed every live-trade filter (price band, liquidity, ESPN match, lead, timing) at scan time. Recorded whether or not a bet follows.
_Avoid_: candidate, signal

**Scan**:
One pass of the scanner over all active markets against cached game state; yields zero or more opportunities.

**Live trade**:
A trade backed by a real Kalshi order — money moved.
_Avoid_: real trade, actual trade

**Strategy trade**:
A trade written by a strategy fire. Simulation-only by construction — never reaches Kalshi.
_Avoid_: paper trade, what-if trade

**Process dry-run**:
A trade produced by the process-level `DRY_RUN` mode rather than a strategy. Still written while `DRY_RUN` is on; never settled, excluded from stats — diagnostics only.
_Avoid_: legacy dry-run (rows are still being produced)

**Position**:
An open (unsettled) trade. At most one per event.
_Avoid_: holding

**Kill switch**:
The `trading_paused` runtime flag. Blocks all order placement — live trades and strategy fires alike.

**Fee**:
Kalshi's per-order trading charge; deducted in P&L.

**P&L**:
Realized profit or loss of a settled trade, net of fees.

### Strategy engine

**Strategy**:
A named, declarative entry rule set from the strategy catalog (`strategies.yaml`).

**Trigger**:
One AND-set of entry conditions within a strategy. A strategy matches when any one trigger fully matches (OR-of-AND); a missing condition means unconstrained.
_Avoid_: rule, condition (for the set)

**Fire**:
The event of a strategy matching a market — produces exactly one strategy trade per strategy–market pair, ever.
_Avoid_: signal, hit

### Backtesting

**Backtest**:
Deterministic simulation of a strategy over historical season data using contract-based P&L math.

**Season data**:
Pre-fetched per-league historical match and goal-time records the backtest runs over.

**Bankroll**:
The running simulated balance inside a backtest.
_Avoid_: balance (reserved for the live account)

**Balance**:
Cash in the live Kalshi account.

**Portfolio value**:
Kalshi's valuation of currently held contracts.

### Deprecated concepts

**Stretch opportunity** (deprecated):
Pre-v1.2 near-miss / what-if record. Superseded by strategy trades; data archived.

**What-if strategy** (deprecated):
Hardcoded predecessor of the strategy catalog.
