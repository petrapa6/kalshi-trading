import type { Match, SeasonFile } from "./seasons";

// ---- Types -----------------------------------------------------------------

export interface BacktestParams {
  min_minute: number;
  min_lead: number;
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
}

export interface BacktestSummary {
  matches_scanned: number;
  matches_bet_on: number;
  wins: number;
  losses: number;
  win_rate: number; // 0..1, 4 decimal places
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

export function simulateMatch(
  match: Match,
  params: BacktestParams,
): BacktestTrade | null {
  const { min_minute, min_lead } = params;
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
        match_id: match.id,
        date: match.date,
        home_team: match.home_team,
        away_team: match.away_team,
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
  const trades: BacktestTrade[] = [];

  for (const match of file.matches) {
    const trade = simulateMatch(match, params);
    if (trade !== null) {
      trades.push(trade);
    }
  }

  const wins = trades.filter((t) => t.result === "win").length;
  const losses = trades.filter((t) => t.result === "loss").length;
  const settled = wins + losses;
  const win_rate = settled === 0 ? 0 : Math.round((wins / settled) * 1e4) / 1e4;

  return {
    summary: {
      matches_scanned: file.matches.length,
      matches_bet_on: trades.length,
      wins,
      losses,
      win_rate,
    },
    trades,
  };
}
