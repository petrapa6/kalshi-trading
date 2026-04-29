import type { Match, SeasonFile } from "./seasons";

// ---- Types -----------------------------------------------------------------

export interface BacktestParams {
  min_minute: number;
  min_lead: number;
  initial_capital: number;
  bet_fraction: number; // 0..1, fraction of current capital staked per bet
  contract_price_cents: number;
}

export interface BacktestTrade {
  match_id: string;
  date: string;
  home_team: string;
  away_team: string;
  final_home: number;
  final_away: number;
  fired_at_minute: number;
  score_at_fire_home: number;
  score_at_fire_away: number;
  leading_side: "home" | "away";
  result: "win" | "loss";
  contracts: number;
  contract_price_cents: number;
  pnl_cents: number;
  capital_after_cents: number;
}

export interface BacktestSummary {
  matches_scanned: number;
  matches_bet_on: number;
  wins: number;
  losses: number;
  win_rate: number; // 0..1, 4 decimal places
  initial_capital_cents: number;
  final_capital_cents: number;
  gain_pct: number; // (final − initial) / initial * 100
}

export interface BacktestResult {
  summary: BacktestSummary;
  trades: BacktestTrade[];
}

// ---- Helpers ---------------------------------------------------------------

export function parseGoalTime(time: string): {
  minute: number;
  stoppage: number;
} {
  const parts = time.split("|");
  if (parts.length !== 2) throw new Error(`Invalid goal time: "${time}"`);
  const minute = parseInt(parts[0], 10);
  const stoppage = parseInt(parts[1], 10);
  if (isNaN(minute) || minute < 0 || isNaN(stoppage) || stoppage < 0) {
    throw new Error(`Invalid goal time values: "${time}"`);
  }
  return { minute, stoppage };
}

export function parseScore(score: string): { home: number; away: number } {
  const parts = score.split(":");
  if (parts.length !== 2) throw new Error(`Invalid score: "${score}"`);
  const home = parseInt(parts[0], 10);
  const away = parseInt(parts[1], 10);
  if (isNaN(home) || isNaN(away))
    throw new Error(`Invalid score values: "${score}"`);
  return { home, away };
}

// ---- Strategy engine -------------------------------------------------------

interface FireOutcome {
  match: Match;
  final_home: number;
  final_away: number;
  fired_at_minute: number;
  score_at_fire_home: number;
  score_at_fire_away: number;
  leading_side: "home" | "away";
  result: "win" | "loss";
}

// Detects whether the strategy fires on this match. Independent of capital.
export function detectFire(
  match: Match,
  min_minute: number,
  min_lead: number,
): FireOutcome | null {
  const { home: finalHome, away: finalAway } = parseScore(match.final_score);

  for (const goal of match.goals) {
    const { minute } = parseGoalTime(goal.time);
    const { home, away } = parseScore(goal.score);
    const lead = Math.abs(home - away);

    // base-minute only; stoppage ignored to mirror src/predictions/backtest.py
    if (minute >= min_minute && lead >= min_lead) {
      const leading_side: "home" | "away" = home > away ? "home" : "away";
      const result: "win" | "loss" =
        (leading_side === "home" && finalHome > finalAway) ||
        (leading_side === "away" && finalAway > finalHome)
          ? "win"
          : "loss";

      return {
        match,
        final_home: finalHome,
        final_away: finalAway,
        fired_at_minute: minute,
        score_at_fire_home: home,
        score_at_fire_away: away,
        leading_side,
        result,
      };
    }
  }

  return null;
}

export function runBacktest(
  file: SeasonFile,
  params: BacktestParams,
): BacktestResult {
  const {
    min_minute,
    min_lead,
    initial_capital,
    bet_fraction,
    contract_price_cents,
  } = params;

  // Walk matches chronologically (oldest first) so capital accumulates in time order.
  // YYYY-MM-DD strings are lexicographically sortable.
  const chronological = [...file.matches].sort((a, b) =>
    a.date.localeCompare(b.date),
  );

  const initial_capital_cents = Math.floor(initial_capital * 100);
  const trades: BacktestTrade[] = [];
  let capital_cents = initial_capital_cents;

  for (const match of chronological) {
    const fire = detectFire(match, min_minute, min_lead);
    if (fire === null) continue;

    const bet_amount_cents = Math.floor(capital_cents * bet_fraction);
    const contracts = Math.floor(bet_amount_cents / contract_price_cents);

    let pnl_cents: number;
    if (contracts === 0) {
      pnl_cents = 0;
    } else if (fire.result === "win") {
      pnl_cents = contracts * (100 - contract_price_cents);
    } else {
      pnl_cents = -contracts * contract_price_cents;
    }
    capital_cents += pnl_cents;

    trades.push({
      match_id: fire.match.id,
      date: fire.match.date,
      home_team: fire.match.home_team,
      away_team: fire.match.away_team,
      final_home: fire.final_home,
      final_away: fire.final_away,
      fired_at_minute: fire.fired_at_minute,
      score_at_fire_home: fire.score_at_fire_home,
      score_at_fire_away: fire.score_at_fire_away,
      leading_side: fire.leading_side,
      result: fire.result,
      contracts,
      contract_price_cents,
      pnl_cents,
      capital_after_cents: capital_cents,
    });
  }

  const wins = trades.filter((t) => t.result === "win").length;
  const losses = trades.filter((t) => t.result === "loss").length;
  const settled = wins + losses;
  const win_rate = settled === 0 ? 0 : Math.round((wins / settled) * 1e4) / 1e4;
  const final_capital_cents = capital_cents;
  const gain_pct =
    initial_capital_cents === 0
      ? 0
      : Math.round(
          ((final_capital_cents - initial_capital_cents) /
            initial_capital_cents) *
            100 *
            1e4,
        ) / 1e4;

  // Display newest-first.
  const display_trades = [...trades].sort((a, b) =>
    b.date.localeCompare(a.date),
  );

  return {
    summary: {
      matches_scanned: file.matches.length,
      matches_bet_on: trades.length,
      wins,
      losses,
      win_rate,
      initial_capital_cents,
      final_capital_cents,
      gain_pct,
    },
    trades: display_trades,
  };
}
