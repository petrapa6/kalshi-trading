import type { Match, SeasonFile } from "./seasons";

// ---- Types -----------------------------------------------------------------

export interface BacktestParams {
  min_minute: number;
  min_lead: number;
  initial_capital: number;
  bet_fraction: number; // 0..1, fraction of current capital staked per bet
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
  bet_amount: number;
  pnl: number;
  capital_after: number;
}

export interface BacktestSummary {
  matches_scanned: number;
  matches_bet_on: number;
  wins: number;
  losses: number;
  win_rate: number; // 0..1, 4 decimal places
  initial_capital: number;
  final_capital: number;
  gain_pct: number; // (final − initial) / initial * 100
}

export interface BacktestResult {
  summary: BacktestSummary;
  trades: BacktestTrade[];
}

// Asymmetric Kalshi-style payoff: win earns 3% of the stake, loss forfeits the full stake.
export const WIN_YIELD = 0.03;

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

// Back-compat alias: legacy callers used `simulateMatch` and expected a trade-shaped
// object without monetary fields. Tests/scripts may still depend on the name.
export function simulateMatch(
  match: Match,
  params: { min_minute: number; min_lead: number },
): Omit<BacktestTrade, "bet_amount" | "pnl" | "capital_after"> | null {
  const fire = detectFire(match, params.min_minute, params.min_lead);
  if (fire === null) return null;
  return {
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
  };
}

export function runBacktest(
  file: SeasonFile,
  params: BacktestParams,
): BacktestResult {
  const { min_minute, min_lead, initial_capital, bet_fraction } = params;

  // Walk matches chronologically (oldest first) so capital accumulates in time order.
  // YYYY-MM-DD strings are lexicographically sortable.
  const chronological = [...file.matches].sort((a, b) =>
    a.date.localeCompare(b.date),
  );

  const trades: BacktestTrade[] = [];
  let capital = initial_capital;

  for (const match of chronological) {
    const fire = detectFire(match, min_minute, min_lead);
    if (fire === null) continue;

    const bet_amount = capital * bet_fraction;
    const pnl = fire.result === "win" ? bet_amount * WIN_YIELD : -bet_amount;
    capital += pnl;

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
      bet_amount,
      pnl,
      capital_after: capital,
    });
  }

  const wins = trades.filter((t) => t.result === "win").length;
  const losses = trades.filter((t) => t.result === "loss").length;
  const settled = wins + losses;
  const win_rate = settled === 0 ? 0 : Math.round((wins / settled) * 1e4) / 1e4;
  const final_capital = capital;
  const gain_pct =
    initial_capital === 0
      ? 0
      : Math.round(
          ((final_capital - initial_capital) / initial_capital) * 100 * 1e4,
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
      initial_capital,
      final_capital,
      gain_pct,
    },
    trades: display_trades,
  };
}
