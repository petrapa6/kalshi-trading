// Why static imports instead of import.meta.glob or fs.readdir:
//
// next.config.ts sets `output: "standalone"`. The `resources/` directory lives at
// the repo root, outside the `dashboard/` package. A runtime fs.readdir on resources/
// works in `pnpm dev:dashboard` but breaks the standalone bundle because the standalone
// trace does not pull in arbitrary files outside the package boundary. Server-action
// variants (listBacktestSeasons / loadBacktestSeason) have the same problem.
//
// import.meta.glob is a Vite/Webpack-5 plugin feature not available in Next.js 16's
// Webpack configuration without a custom loader plugin.
//
// We sidestep both by importing the JSONs at module scope so Webpack bundles them with
// the client component. No fs, no server actions. Adding a new season requires editing
// the IMPORTS array below — see the TODO comment.
//
// TODO: when a new season JSON is added to resources/, add a corresponding entry to
// IMPORTS below, following the same pattern.

import epl_2024_25 from "../../../resources/epl_2024_25_season.json";
import laliga_2024_25 from "../../../resources/laliga_2024_25_season.json";

// ---- Types -----------------------------------------------------------------

export type Goal = {
  time: string; // "MM|S" — base minute | stoppage minutes
  score: string; // "h:a" snapshot AFTER this goal
};

export type Match = {
  id: string;
  date: string; // "YYYY-MM-DD"
  home_team: string;
  away_team: string;
  final_score: string; // "h:a"
  goals: Goal[];
};

export type SeasonFile = {
  matches: Match[];
};

// ---- Filename parser --------------------------------------------------------

export interface ParsedFilename {
  league: string; // e.g. "epl"
  startYear: number; // 4-digit
  endYear: number; // resolved to 4-digit (e.g. "25" -> 2025)
  label: string; // e.g. "EPL · 2024/25"
}

const FILENAME_RE = /^([a-z0-9]+)_(\d{4})_(\d{2})_season\.json$/;

const LEAGUE_NAMES: Record<string, string> = {
  epl: "EPL",
  laliga: "La Liga",
  bl1: "Bundesliga",
};

export function parseSeasonFilename(name: string): ParsedFilename | null {
  const m = FILENAME_RE.exec(name);
  if (!m) return null;
  const league = m[1];
  const startYear = parseInt(m[2], 10);
  const endYY = parseInt(m[3], 10);
  const endYear = Math.floor(startYear / 100) * 100 + endYY;
  const prettyLeague = LEAGUE_NAMES[league] ?? league.toUpperCase();
  const label = `${prettyLeague} · ${startYear}/${String(endYY).padStart(2, "0")}`;
  return { league, startYear, endYear, label };
}

// ---- Season catalog --------------------------------------------------------

export interface SeasonOption {
  key: string; // basename, e.g. "epl_2024_25_season.json"
  parsed: ParsedFilename;
  data: SeasonFile;
}

// Hand-maintained list of (filename, imported data) pairs.
// Webpack bundles each JSON with the client component at build time.
const IMPORTS: Array<{ filename: string; data: SeasonFile }> = [
  { filename: "epl_2024_25_season.json", data: epl_2024_25 as SeasonFile },
  {
    filename: "laliga_2024_25_season.json",
    data: laliga_2024_25 as SeasonFile,
  },
];

export const SEASONS: SeasonOption[] = IMPORTS.flatMap(({ filename, data }) => {
  const parsed = parseSeasonFilename(filename);
  if (!parsed) {
    if (process.env.NODE_ENV !== "production") {
      console.warn(`[seasons] Skipping unrecognised filename: ${filename}`);
    }
    return [];
  }
  return [{ key: filename, parsed, data }];
}).sort((a, b) => {
  // Sort by league name ascending, then by startYear descending (newest first)
  if (a.parsed.league !== b.parsed.league) {
    return a.parsed.league.localeCompare(b.parsed.league);
  }
  return b.parsed.startYear - a.parsed.startYear;
});
