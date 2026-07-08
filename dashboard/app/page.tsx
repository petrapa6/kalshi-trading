"use client";

import { type ReactNode, useEffect, useState } from "react";
import {
  Area,
  Bar,
  BarChart,
  CartesianGrid,
  ComposedChart,
  Line,
  Rectangle,
  type RectangleProps,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  type AccountStep,
  accountValueSteps,
  cumulativePnlByStrategy,
  pnlByPrice,
  pnlByTime,
  priceBins,
  type StrategyPnlSeries,
  timeBins,
  type ViewMode,
} from "@/lib/chart-data";
import { login, checkAuth, updateConfig } from "./actions";

// Proxied via Next.js to provide secure token headers transparently from the server
const API = "";

interface PopulationStats {
  trades: number;
  wins: number;
  losses: number;
  win_rate: number;
  realized_pnl_cents: number;
  total_cost_cents: number;
  total_potential_profit_cents: number;
  total_fees_cents: number;
  open_positions: number;
  open_cost_cents: number;
  open_potential_profit_cents: number;
}

type Population = "live" | "dry_run";

interface Stats {
  live: PopulationStats;
  dry_run: PopulationStats;
  balance_cents: number;
  portfolio_value_cents: number;
  total_scans: number;
  total_opportunities: number;
}

interface Trade {
  id: number;
  placed_at: string;
  ticker: string;
  event_ticker: string;
  title: string;
  side: string;
  count: number;
  yes_price: number;
  cost_cents: number;
  potential_profit_cents: number;
  status: string;
  pnl_cents: number | null;
  dry_run: boolean;
  error: string | null;
  espn_clock_seconds: number | null;
  strategy_name?: string | null;
  settled_at?: string | null;
}

interface Opportunity {
  id: number;
  found_at: string;
  ticker: string;
  title: string;
  yes_sub_title: string;
  yes_bid: number;
  yes_ask: number;
  spread: number;
  volume: number;
  series_ticker: string;
}

interface KalshiMarket {
  ticker: string;
  team: string;
  yes_sub_title: string;
  yes_bid: number;
  yes_ask: number;
  volume: number;
}

interface LiveGame {
  espn_id: string;
  sport: string;
  series: string;
  home_team: string;
  away_team: string;
  home_score: number;
  away_score: number;
  period: number;
  display_clock: string;
  clock_seconds: number;
  state: string;
  is_final_minutes: boolean;
  is_target: boolean;
  is_watching: boolean;
  has_bet: boolean;
  score_diff: number;
  min_score_lead: number;
  final_period: number;
  kalshi_markets: KalshiMarket[];
}

interface SportConfig {
  sport_path: string;
  name: string;
  kalshi_series: string;
  final_period: number;
  clock_direction: "down" | "up" | "none";
  final_minutes_desc: string;
  final_minutes_seconds: number | null;
}

interface AppConfig {
  trading: {
    bet_percent: number;
    max_positions: number;
    dry_run: boolean;
    paused: boolean;
  };
  stretch: {
    price_min: number;
  };
  polling: {
    espn_interval_s: number;
    kalshi_scan_interval_s: number;
    kalshi_ws: boolean;
    db_backup_interval_s: number;
  };
  sports: SportConfig[];
}

function cents(c: number): string {
  return `$${(c / 100).toFixed(2)}`;
}

function formatGameTime(g: LiveGame): string {
  const sport = g.sport;
  const p = g.period;
  const clock = g.display_clock;

  // Format clock: "33.2" → "0:33", "11:48" stays, "0.0"/"0:00" → "End"
  const clockNum = parseFloat(clock);
  let timeStr: string;
  if (clock.includes(":")) {
    timeStr = clockNum === 0 ? "End" : clock;
  } else {
    // seconds only (e.g. "33.2")
    const secs = Math.floor(clockNum);
    timeStr = secs === 0 ? "End" : `0:${secs.toString().padStart(2, "0")}`;
  }

  if (sport.startsWith("basketball/")) {
    if (g.final_period === 2) {
      // College basketball: 2 halves
      const label = p > 2 ? "OT" : p === 1 ? "1st Half" : "2nd Half";
      return `${label} · ${timeStr}`;
    }
    const label = p > g.final_period ? "OT" : `Q${p}`;
    return `${label} · ${timeStr}`;
  }
  if (sport.startsWith("hockey/")) {
    const ord = p === 1 ? "1st" : p === 2 ? "2nd" : p === 3 ? "3rd" : "OT";
    return `${ord} · ${timeStr}`;
  }
  if (sport.startsWith("football/")) {
    const label = p > g.final_period ? "OT" : `Q${p}`;
    return `${label} · ${timeStr}`;
  }
  if (sport.startsWith("baseball/")) {
    const ord = p === 1 ? "1st" : p === 2 ? "2nd" : p === 3 ? "3rd" : `${p}th`;
    return `${ord} inning`;
  }
  if (sport.startsWith("soccer/")) {
    // ESPN reports match minute for soccer (e.g. "76" = 76th minute)
    const minute = Math.floor(clockNum);
    return minute > 0 ? `${minute}'` : p === 1 ? "1st Half" : "2nd Half";
  }
  if (sport.startsWith("mma/")) {
    return `R${p} · ${timeStr}`;
  }
  return `P${p} · ${timeStr}`;
}

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function sportLabel(sport: string): string {
  const map: Record<string, string> = {
    "basketball/nba": "NBA",
    "hockey/nhl": "NHL",
    "football/nfl": "NFL",
    "baseball/mlb": "MLB",
    "basketball/mens-college-basketball": "NCAAM",
    "football/college-football": "NCAAF",
    "mma/ufc": "UFC",
    "soccer/eng.1": "EPL",
    "soccer/esp.1": "La Liga",
    "soccer/usa.1": "MLS",
  };
  return map[sport] || sport;
}

function StatCard({
  label,
  value,
  sub,
  delay,
}: {
  label: string;
  value: string;
  sub?: string;
  delay?: number;
}) {
  return (
    <div
      className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm"
      style={{ animationDelay: `${delay || 0}ms` }}
    >
      <div className="text-amber-600 text-sm mb-1 font-medium">{label}</div>
      <div className="text-2xl font-bold text-amber-100">{value}</div>
      {sub && <div className="text-amber-700 text-sm mt-1">{sub}</div>}
    </div>
  );
}

function StatusBadge({ status, dryRun }: { status: string; dryRun: boolean }) {
  if (dryRun)
    return (
      <span className="px-2 py-0.5 text-xs rounded-full bg-zinc-700 text-zinc-300 border border-zinc-600">
        DRY RUN
      </span>
    );
  const colors: Record<string, string> = {
    placed: "bg-amber-900/30 text-amber-300 border-amber-700/50",
    filled: "bg-yellow-900/30 text-yellow-300 border-yellow-700/50",
    settled_win: "bg-green-900/30 text-green-300 border-green-700/50",
    settled_loss: "bg-red-900/30 text-red-300 border-red-700/50",
    error: "bg-red-900/30 text-red-300 border-red-700/50",
  };
  return (
    <span
      className={`px-2 py-0.5 text-xs rounded-full border ${colors[status] || "bg-zinc-700 text-zinc-300 border-zinc-600"}`}
    >
      {status.replace("_", " ").toUpperCase()}
    </span>
  );
}

const WIN_COLOR = "#4ade80";
const LOSS_COLOR = "#f87171";
const CHART_TICK = {
  fill: "#78716c",
  fontSize: 9,
  fontFamily: "monospace",
} as const;
const CHART_CURSOR_LINE = {
  stroke: "#d4a017",
  strokeDasharray: "3 3",
  opacity: 0.5,
} as const;
const CHART_CURSOR_FILL = { fill: "#d4a017", fillOpacity: 0.08 } as const;

function ChartTooltipFrame({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-md border border-amber-800/60 bg-stone-900/95 px-2.5 py-1.5 font-mono">
      {children}
    </div>
  );
}

function AccountTooltip({
  active,
  payload,
  viewMode,
}: {
  active?: boolean;
  payload?: { payload: AccountStep }[];
  viewMode: ViewMode;
}) {
  if (!active || !payload?.length) return null;
  const step = payload[0].payload;
  return (
    <ChartTooltipFrame>
      <div className="text-xs font-bold text-amber-400">
        {cents(step.value)}
      </div>
      {step.kind === "bucket" && (
        <div
          className="text-[10px]"
          style={{ color: step.periodPnl >= 0 ? WIN_COLOR : LOSS_COLOR }}
        >
          {step.periodPnl >= 0 ? "+" : ""}
          {cents(step.periodPnl)}
          {viewMode !== "trade" ? ` · ${step.label}` : ""}
        </div>
      )}
    </ChartTooltipFrame>
  );
}

function WinLossTooltip({
  active,
  payload,
  label,
  formatLabel,
}: {
  active?: boolean;
  payload?: { payload: { wins: number; losses: number } }[];
  label?: number;
  formatLabel: (label: number) => string;
}) {
  if (!active || !payload?.length || label === undefined) return null;
  const { wins, losses } = payload[0].payload;
  return (
    <ChartTooltipFrame>
      <div className="text-xs font-bold text-amber-400">
        {formatLabel(label)}
      </div>
      <div className="text-[10px]" style={{ color: WIN_COLOR }}>
        ✓ {wins} win{wins !== 1 ? "s" : ""}
      </div>
      <div className="text-[10px]" style={{ color: LOSS_COLOR }}>
        ✗ {losses} loss{losses !== 1 ? "es" : ""}
      </div>
    </ChartTooltipFrame>
  );
}

function PnlBarTooltip({
  active,
  payload,
  label,
  formatLabel,
}: {
  active?: boolean;
  payload?: { payload: { pnl: number } }[];
  label?: number;
  formatLabel: (label: number) => string;
}) {
  if (!active || !payload?.length || label === undefined) return null;
  const { pnl } = payload[0].payload;
  return (
    <ChartTooltipFrame>
      <div className="text-xs font-bold text-amber-400">
        {formatLabel(label)}
      </div>
      <div
        className="text-[10px]"
        style={{ color: pnl >= 0 ? WIN_COLOR : LOSS_COLOR }}
      >
        {pnl === 0 ? "No P&L" : `${pnl >= 0 ? "+" : ""}${cents(pnl)}`}
      </div>
    </ChartTooltipFrame>
  );
}

function WinLossLegend({ wins, losses }: { wins: number; losses: number }) {
  return (
    <div className="flex items-center gap-4 text-xs text-zinc-500">
      <span className="flex items-center gap-1.5">
        <span className="w-2.5 h-2.5 rounded-sm bg-green-500/70 inline-block" />
        Wins ({wins})
      </span>
      <span className="flex items-center gap-1.5">
        <span className="w-2.5 h-2.5 rounded-sm bg-red-500/70 inline-block" />
        Losses ({losses})
      </span>
    </div>
  );
}

function pnlBarShape(props: RectangleProps & { payload?: { pnl: number } }) {
  return (
    <Rectangle
      {...props}
      fill={(props.payload?.pnl ?? 0) >= 0 ? WIN_COLOR : LOSS_COLOR}
    />
  );
}

function stepDot(props: {
  cx?: number;
  cy?: number;
  index?: number;
  payload?: AccountStep;
}) {
  const { cx, cy, index, payload } = props;
  if (payload?.kind !== "bucket" || cx == null || cy == null)
    return <g key={`dot-${index}`} />;
  return (
    <circle
      key={`dot-${index}`}
      cx={cx}
      cy={cy}
      r={3.5}
      fill={payload.periodPnl >= 0 ? WIN_COLOR : LOSS_COLOR}
      stroke="#000"
      strokeWidth={1}
    />
  );
}

function PnlChart({
  trades,
  population,
  balanceCents,
  portfolioCents,
}: {
  trades: Trade[];
  population: Population;
  balanceCents: number;
  portfolioCents: number;
}) {
  const [viewMode, setViewMode] = useState<ViewMode>("trade");

  const settledTrades = trades.filter(
    (t) =>
      (population === "dry_run" ? t.dry_run : !t.dry_run) &&
      t.pnl_cents !== null &&
      t.placed_at,
  );

  // Live anchors on the real account (balance + portfolio); dry-run has no
  // real balance, so its curve is pure cumulative counterfactual P&L from 0.
  const dryPnl = settledTrades.reduce((s, t) => s + t.pnl_cents!, 0);
  const totalNow =
    population === "dry_run" ? dryPnl : balanceCents + portfolioCents;
  const { steps, windowStartBalance, hiddenCount } = accountValueSteps(
    settledTrades.map((t) => ({
      placed_at: t.placed_at,
      pnl_cents: t.pnl_cents!,
    })),
    totalNow,
    viewMode,
  );

  const totalPnl = settledTrades.reduce((s, t) => s + t.pnl_cents!, 0);
  const lineColor = totalPnl >= 0 ? WIN_COLOR : LOSS_COLOR;
  const fillColor = totalNow >= windowStartBalance ? WIN_COLOR : LOSS_COLOR;
  const windowPnl = totalNow - windowStartBalance;

  const MODES: { key: ViewMode; label: string }[] = [
    { key: "trade", label: "Trade" },
    { key: "day", label: "Day" },
    { key: "week", label: "Week" },
    { key: "month", label: "Month" },
  ];

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3 flex-wrap gap-2">
        <h2 className="text-sm text-amber-600 font-medium">
          {population === "dry_run" ? "Dry-run P&L" : "Account Value"}
        </h2>
        <div className="flex items-center gap-3 flex-wrap">
          {/* View mode toggle */}
          <div className="flex items-center gap-0.5 bg-zinc-800/70 border border-zinc-700/50 rounded-lg p-0.5">
            {MODES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setViewMode(key)}
                className={`px-2.5 py-0.5 text-xs rounded-md transition-all font-medium ${
                  viewMode === key
                    ? "bg-amber-900/60 text-amber-300 border border-amber-700/50"
                    : "text-zinc-500 hover:text-zinc-300"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          {/* Value summary */}
          <div className="flex items-center gap-3 text-sm">
            {hiddenCount > 0 && (
              <span className="text-zinc-600 text-xs">last 20</span>
            )}
            <span className="text-zinc-500 font-mono">
              {cents(windowStartBalance)}
            </span>
            <span className="text-amber-200 font-bold font-mono">
              {cents(totalNow)}
            </span>
            {windowPnl !== 0 && (
              <span
                className={`font-bold font-mono px-2 py-0.5 rounded ${windowPnl > 0 ? "text-green-400 bg-green-900/30" : "text-red-400 bg-red-900/30"}`}
              >
                {windowPnl > 0 ? "+" : ""}
                {cents(windowPnl)}
              </span>
            )}
          </div>
        </div>
      </div>
      <ResponsiveContainer width="100%" aspect={4}>
        <ComposedChart
          data={steps}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        >
          <defs>
            <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={fillColor} stopOpacity="0.3" />
              <stop offset="100%" stopColor={fillColor} stopOpacity="0.02" />
            </linearGradient>
          </defs>
          <XAxis
            dataKey="label"
            tick={CHART_TICK}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            tick={CHART_TICK}
            tickFormatter={cents}
            width={56}
            axisLine={false}
            tickLine={false}
            domain={["auto", "auto"]}
          />
          <ReferenceLine
            y={windowStartBalance}
            stroke="#78716c"
            strokeDasharray="4 4"
          />
          {totalNow !== windowStartBalance && (
            <ReferenceLine
              y={totalNow}
              stroke={fillColor}
              strokeWidth={0.5}
              strokeDasharray="2 4"
              opacity={0.4}
            />
          )}
          <Tooltip
            content={<AccountTooltip viewMode={viewMode} />}
            cursor={CHART_CURSOR_LINE}
          />
          <Area
            type="stepAfter"
            dataKey="value"
            stroke={lineColor}
            strokeWidth={2.5}
            fill="url(#pnlGrad)"
            baseValue={windowStartBalance}
            dot={stepDot}
            activeDot={{
              r: 5,
              fill: "#f0d060",
              stroke: "#000",
              strokeWidth: 1.5,
            }}
            isAnimationActive={false}
          />
        </ComposedChart>
      </ResponsiveContainer>
    </div>
  );
}

function PopulationToggle({
  population,
  onChange,
}: {
  population: Population;
  onChange: (p: Population) => void;
}) {
  const OPTIONS: { key: Population; label: string }[] = [
    { key: "live", label: "Live" },
    { key: "dry_run", label: "Dry-run" },
  ];
  return (
    <div className="flex items-center gap-0.5 bg-zinc-800/70 border border-zinc-700/50 rounded-lg p-0.5 w-fit mb-6">
      {OPTIONS.map(({ key, label }) => (
        <button
          key={key}
          onClick={() => onChange(key)}
          className={`px-3 py-1 text-xs rounded-md transition-all font-medium ${
            population === key
              ? "bg-amber-900/60 text-amber-300 border border-amber-700/50"
              : "text-zinc-500 hover:text-zinc-300"
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

// Categorical palette for the per-strategy chart — dark-surface steps from the
// dataviz reference palette, validated as a set (worst adjacent ΔE 10.3, floor
// band → identity is carried by the always-present legend, not color alone).
const STRATEGY_COLORS = [
  "#3987e5",
  "#199e70",
  "#c98500",
  "#008300",
  "#9085e9",
  "#e66767",
  "#d55181",
  "#d95926",
];

function StrategyPnlTooltip({
  active,
  payload,
}: {
  active?: boolean;
  payload?: { name: string; value: number; color: string }[];
}) {
  if (!active || !payload?.length) return null;
  return (
    <ChartTooltipFrame>
      {payload.map((p) => (
        <div key={p.name} className="text-[10px]" style={{ color: p.color }}>
          {p.name}: {p.value >= 0 ? "+" : ""}
          {cents(p.value)}
        </div>
      ))}
    </ChartTooltipFrame>
  );
}

function StrategyPnlChart({
  trades,
  population,
}: {
  trades: Trade[];
  population: Population;
}) {
  const series: StrategyPnlSeries[] = cumulativePnlByStrategy(
    trades
      .filter((t) => (population === "dry_run" ? t.dry_run : !t.dry_run))
      .map((t) => ({
        strategy_name: t.strategy_name ?? null,
        settled_at: t.settled_at ?? null,
        pnl_cents: t.pnl_cents ?? 0,
      })),
  );

  // Color follows the strategy, not its rank in the filtered set: derive the
  // index from the stable set of ALL strategies so switching population never
  // repaints a survivor (dataviz non-negotiable).
  const allStrategies = Array.from(
    new Set(trades.map((t) => t.strategy_name).filter((n): n is string => !!n)),
  ).sort();
  const color = (strategy: string) =>
    STRATEGY_COLORS[allStrategies.indexOf(strategy) % STRATEGY_COLORS.length];

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3 flex-wrap gap-3">
        <h2 className="text-sm text-amber-600 font-medium">
          Cumulative P&L by Strategy
        </h2>
        {/* Legend — always present so identity never rests on color alone */}
        {series.length > 0 && (
          <div className="flex items-center gap-3 flex-wrap">
            {series.map((s) => (
              <span
                key={s.strategy}
                className="flex items-center gap-1.5 text-xs text-zinc-400"
              >
                <span
                  className="inline-block w-2.5 h-2.5 rounded-sm"
                  style={{ backgroundColor: color(s.strategy) }}
                />
                {s.strategy}
              </span>
            ))}
          </div>
        )}
      </div>
      {series.length === 0 ? (
        <div className="py-12 text-center text-amber-900 text-sm">
          No settled {population === "dry_run" ? "dry-run" : "live"} trades with
          a strategy yet.
        </div>
      ) : (
        <ResponsiveContainer width="100%" aspect={4}>
          <ComposedChart margin={{ top: 8, right: 12, bottom: 0, left: 0 }}>
            <XAxis
              dataKey="x"
              type="number"
              domain={["dataMin", "dataMax"]}
              tick={CHART_TICK}
              axisLine={false}
              tickLine={false}
              tickFormatter={(x: number) => {
                const d = new Date(x);
                return `${d.getMonth() + 1}/${d.getDate()}`;
              }}
            />
            <YAxis
              tick={CHART_TICK}
              tickFormatter={cents}
              width={56}
              axisLine={false}
              tickLine={false}
              domain={["auto", "auto"]}
            />
            <ReferenceLine y={0} stroke="#78716c" strokeDasharray="4 4" />
            <Tooltip
              content={<StrategyPnlTooltip />}
              cursor={CHART_CURSOR_LINE}
            />
            {series.map((s) => (
              <Line
                key={s.strategy}
                data={s.points}
                dataKey="y"
                name={s.strategy}
                type="stepAfter"
                stroke={color(s.strategy)}
                strokeWidth={2}
                dot={false}
                isAnimationActive={false}
              />
            ))}
          </ComposedChart>
        </ResponsiveContainer>
      )}
    </div>
  );
}

// Only settled, non-dry-run trades with a known price and outcome
function settledWithPrice(trades: Trade[]): Trade[] {
  return trades.filter(
    (t) =>
      !t.dry_run &&
      t.pnl_cents !== null &&
      t.yes_price != null &&
      (t.status === "settled_win" || t.status === "settled_loss"),
  );
}

// Only countdown-sport settled trades with a known clock reading ≤ 10 min
function settledWithClock(trades: Trade[]): Trade[] {
  return trades.filter(
    (t) =>
      !t.dry_run &&
      t.pnl_cents !== null &&
      t.espn_clock_seconds !== null &&
      t.espn_clock_seconds <= 600 &&
      t.espn_clock_seconds >= 0 &&
      (t.status === "settled_win" || t.status === "settled_loss"),
  );
}

function WinLossHistogram({
  title,
  emptyText,
  bins,
  xKey,
  formatTick,
  formatLabel,
}: {
  title: string;
  emptyText: string;
  bins: { wins: number; losses: number }[] | null;
  xKey: string;
  formatTick?: (v: number) => string;
  formatLabel: (label: number) => string;
}) {
  if (!bins) {
    return (
      <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">{title}</h2>
        <p className="text-amber-900 text-sm">{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">{title}</h2>
        <WinLossLegend
          wins={bins.reduce((s, b) => s + b.wins, 0)}
          losses={bins.reduce((s, b) => s + b.losses, 0)}
        />
      </div>
      <ResponsiveContainer width="100%" aspect={4}>
        <BarChart
          data={bins}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="#3f3f46"
            strokeWidth={0.5}
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey={xKey}
            tickFormatter={formatTick}
            tick={CHART_TICK}
            interval={0}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            allowDecimals={false}
            width={36}
            tick={CHART_TICK}
            axisLine={false}
            tickLine={false}
          />
          <Tooltip
            content={<WinLossTooltip formatLabel={formatLabel} />}
            cursor={CHART_CURSOR_FILL}
          />
          <Bar
            dataKey="losses"
            stackId="wl"
            fill={LOSS_COLOR}
            fillOpacity={0.6}
            isAnimationActive={false}
          />
          <Bar
            dataKey="wins"
            stackId="wl"
            fill={WIN_COLOR}
            fillOpacity={0.6}
            radius={[2, 2, 0, 0]}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function SignedPnlHistogram({
  title,
  emptyText,
  bins,
  totalPnl,
  xKey,
  formatTick,
  formatLabel,
}: {
  title: string;
  emptyText: string;
  bins: { pnl: number }[] | null;
  totalPnl: number;
  xKey: string;
  formatTick?: (v: number) => string;
  formatLabel: (label: number) => string;
}) {
  if (!bins) {
    return (
      <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">{title}</h2>
        <p className="text-amber-900 text-sm">{emptyText}</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">{title}</h2>
        <span
          className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${totalPnl >= 0 ? "text-green-400 bg-green-900/30" : "text-red-400 bg-red-900/30"}`}
        >
          {totalPnl >= 0 ? "+" : ""}
          {cents(totalPnl)} total
        </span>
      </div>
      <ResponsiveContainer width="100%" aspect={4}>
        <BarChart
          data={bins}
          margin={{ top: 8, right: 12, bottom: 0, left: 0 }}
        >
          <CartesianGrid
            vertical={false}
            stroke="#3f3f46"
            strokeWidth={0.5}
            strokeDasharray="3 3"
          />
          <XAxis
            dataKey={xKey}
            tickFormatter={formatTick}
            tick={CHART_TICK}
            interval={0}
            axisLine={false}
            tickLine={false}
          />
          <YAxis
            width={56}
            tick={CHART_TICK}
            tickFormatter={(v: number) =>
              `${v >= 0 ? "+" : ""}$${(v / 100).toFixed(2)}`
            }
            axisLine={false}
            tickLine={false}
            domain={["auto", "auto"]}
          />
          <ReferenceLine y={0} stroke="#78716c" />
          <Tooltip
            content={<PnlBarTooltip formatLabel={formatLabel} />}
            cursor={CHART_CURSOR_FILL}
          />
          <Bar
            dataKey="pnl"
            fillOpacity={0.7}
            shape={pnlBarShape}
            isAnimationActive={false}
          />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function ContractValueHistogram({ trades }: { trades: Trade[] }) {
  const settled = settledWithPrice(trades);
  return (
    <WinLossHistogram
      title="Contract Value Distribution"
      emptyText="No settled trades to display yet."
      bins={
        settled.length
          ? priceBins(
              settled.map((t) => ({
                yes_price: t.yes_price,
                pnl_cents: t.pnl_cents!,
              })),
            )
          : null
      }
      xKey="price"
      formatLabel={(p) => `${p}¢`}
    />
  );
}

function PnlHistogram({ trades }: { trades: Trade[] }) {
  const settled = settledWithPrice(trades);
  return (
    <SignedPnlHistogram
      title="P&L by Contract Value"
      emptyText="No settled trades to display yet."
      bins={
        settled.length
          ? pnlByPrice(
              settled.map((t) => ({
                yes_price: t.yes_price,
                pnl_cents: t.pnl_cents!,
              })),
            )
          : null
      }
      totalPnl={settled.reduce((s, t) => s + t.pnl_cents!, 0)}
      xKey="price"
      formatLabel={(p) => `${p}¢`}
    />
  );
}

function TimeHistogram({ trades }: { trades: Trade[] }) {
  const settled = settledWithClock(trades);
  return (
    <WinLossHistogram
      title="Trade Distribution by Time Remaining"
      emptyText="No settled trades with clock data yet."
      bins={
        settled.length
          ? timeBins(
              settled.map((t) => ({
                clock_seconds: t.espn_clock_seconds!,
                pnl_cents: t.pnl_cents!,
              })),
            )
          : null
      }
      xKey="minutesLeft"
      formatTick={(m) => `${m}m`}
      formatLabel={(m) => `~${m}m left`}
    />
  );
}

function TimePnlHistogram({ trades }: { trades: Trade[] }) {
  const settled = settledWithClock(trades);
  return (
    <SignedPnlHistogram
      title="P&L by Time Remaining"
      emptyText="No settled trades with clock data yet."
      bins={
        settled.length
          ? pnlByTime(
              settled.map((t) => ({
                clock_seconds: t.espn_clock_seconds!,
                pnl_cents: t.pnl_cents!,
              })),
            )
          : null
      }
      totalPnl={settled.reduce((s, t) => s + t.pnl_cents!, 0)}
      xKey="minutesLeft"
      formatTick={(m) => `${m}m`}
      formatLabel={(m) => `~${m}m left`}
    />
  );
}

function SportStatsCharts({
  stats,
}: {
  stats: Record<string, { played: number; wins: number; pnl: number }>;
}) {
  const sports = Object.keys(stats)
    .filter(
      (s) => stats[s].played > 0 || stats[s].wins > 0 || stats[s].pnl !== 0,
    )
    .sort((a, b) => stats[b].pnl - stats[a].pnl);

  if (sports.length === 0) return null;

  const maxMatches = Math.max(...sports.map((s) => stats[s].played), 1);
  const maxWins = Math.max(...sports.map((s) => stats[s].wins), 1);
  const maxPnl = Math.max(...sports.map((s) => Math.abs(stats[s].pnl)), 1);

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 gap-6 mb-8 mt-2 animate-fade-in">
      {/* Played Matches */}
      <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm shadow-lg shadow-black/50">
        <h2 className="text-sm text-amber-600 font-medium mb-4">
          Total Matches Tracked
        </h2>
        <div className="space-y-3">
          {sports.map((s) => {
            const count = stats[s].played;
            return (
              <div
                key={s}
                className="grid grid-cols-[65px_1fr_40px] items-center gap-2"
              >
                <span className="text-xs text-zinc-400 font-mono truncate">
                  {s}
                </span>
                <div className="h-4 w-full bg-zinc-800 rounded-sm overflow-hidden">
                  <div
                    className="h-full bg-amber-600/80 rounded-sm"
                    style={{ width: `${(count / maxMatches) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-amber-200 text-right font-mono">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* Won Matches */}
      <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm shadow-lg shadow-black/50">
        <h2 className="text-sm text-green-600 font-medium mb-4">Trades Won</h2>
        <div className="space-y-3">
          {sports.map((s) => {
            const wins = stats[s].wins;
            return (
              <div
                key={s}
                className="grid grid-cols-[65px_1fr_40px] items-center gap-2"
              >
                <span className="text-xs text-zinc-400 font-mono truncate">
                  {s}
                </span>
                <div className="h-4 w-full bg-zinc-800 rounded-sm overflow-hidden">
                  <div
                    className="h-full bg-green-500/80 rounded-sm"
                    style={{ width: `${(wins / maxWins) * 100}%` }}
                  />
                </div>
                <span className="text-xs text-green-200 text-right font-mono">
                  {wins}
                </span>
              </div>
            );
          })}
        </div>
      </div>

      {/* P&L */}
      <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm shadow-lg shadow-black/50">
        <h2 className="text-sm text-amber-500 font-medium mb-4">Net P&L</h2>
        <div className="space-y-3">
          {sports.map((s) => {
            const pnl = stats[s].pnl;
            const isPos = pnl >= 0;
            const wPct = (Math.abs(pnl) / maxPnl) * 50;
            return (
              <div
                key={s}
                className="grid grid-cols-[65px_1fr_60px] items-center gap-2"
              >
                <span className="text-xs text-zinc-400 font-mono truncate">
                  {s}
                </span>
                <div className="h-4 w-full relative flex items-center bg-zinc-800/30 rounded-sm border border-zinc-800/50">
                  <div className="absolute left-1/2 top-0 bottom-0 w-px bg-zinc-600 z-10" />
                  {isPos ? (
                    <div
                      className="absolute left-1/2 h-full bg-green-500/80 rounded-r-sm"
                      style={{ width: `${wPct}%` }}
                    />
                  ) : (
                    <div
                      className="absolute right-1/2 h-full bg-red-500/80 rounded-l-sm"
                      style={{ width: `${wPct}%` }}
                    />
                  )}
                </div>
                <span
                  className={`text-xs text-right font-mono font-medium ${isPos ? "text-green-400" : "text-red-400"}`}
                >
                  {isPos ? "+" : ""}
                  {cents(pnl)}
                </span>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}

function LiveGamesPanel({ games }: { games: LiveGame[] }) {
  if (games.length === 0) {
    return (
      <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">Live Games</h2>
        <p className="text-amber-900 text-sm">No live games right now.</p>
      </div>
    );
  }

  return (
    <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex items-center gap-3 mb-4">
        <h2 className="text-sm text-amber-600 font-medium">Live Games</h2>
        <div className="w-2 h-2 rounded-full bg-red-500 animate-pulse" />
        <span className="text-xs text-zinc-500">{games.length} active</span>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {[...games]
          .sort((a, b) => {
            // Bet placed first, then targets, then watching, then live, then pre
            if (a.has_bet !== b.has_bet) return a.has_bet ? -1 : 1;
            if (a.is_target !== b.is_target) return a.is_target ? -1 : 1;
            if (a.is_watching !== b.is_watching) return a.is_watching ? -1 : 1;
            if (a.state !== b.state) return a.state === "in" ? -1 : 1;
            return 0;
          })
          .map((g) => {
            // Find the leading team's Kalshi market
            const leadingTeam =
              g.home_score >= g.away_score ? g.home_team : g.away_team;
            const trailingTeam =
              g.home_score >= g.away_score ? g.away_team : g.home_team;
            const leadingMarket = g.kalshi_markets?.find(
              (m) => m.team === leadingTeam,
            );
            const trailingMarket = g.kalshi_markets?.find(
              (m) => m.team === trailingTeam,
            );

            return (
              <div
                key={g.espn_id}
                className={`border rounded-lg p-3 transition-all ${
                  g.has_bet
                    ? "border-green-500/50 bg-green-950/20"
                    : g.is_target
                      ? "border-amber-500/50 bg-amber-950/20 gold-glow"
                      : g.is_watching
                        ? "border-amber-800/40 bg-amber-950/10"
                        : "border-zinc-800 bg-zinc-900/50"
                }`}
              >
                <div className="flex justify-between items-start mb-2">
                  <span className="text-xs font-medium text-amber-600">
                    {sportLabel(g.sport)}
                  </span>
                  <div className="flex items-center gap-1.5">
                    {g.has_bet && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-green-600/20 text-green-400 border border-green-600/30 font-bold">
                        BET PLACED
                      </span>
                    )}
                    {g.is_target && !g.has_bet && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-600/20 text-amber-400 border border-amber-600/30 font-bold">
                        TARGET
                      </span>
                    )}
                    {g.is_watching && !g.is_target && !g.has_bet && (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-amber-900/20 text-amber-600 border border-amber-800/30">
                        WATCHING
                      </span>
                    )}
                    {g.state === "in" ? (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-red-900/30 text-red-400 border border-red-700/30">
                        LIVE
                      </span>
                    ) : (
                      <span className="text-[10px] px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400 border border-zinc-700">
                        PRE
                      </span>
                    )}
                  </div>
                </div>
                <div className="flex justify-between items-center">
                  <div className="space-y-1">
                    <div
                      className={`text-sm font-medium ${g.away_score > g.home_score ? "text-amber-200" : "text-zinc-400"}`}
                    >
                      {g.away_team}
                    </div>
                    <div
                      className={`text-sm font-medium ${g.home_score > g.away_score ? "text-amber-200" : "text-zinc-400"}`}
                    >
                      {g.home_team}
                    </div>
                  </div>
                  <div className="text-right space-y-1">
                    <div className="flex items-center gap-2 justify-end">
                      {g.away_team === leadingTeam && leadingMarket && (
                        <span className="text-[10px] text-green-400 font-mono">
                          {leadingMarket.yes_ask}¢
                        </span>
                      )}
                      {g.away_team === trailingTeam && trailingMarket && (
                        <span className="text-[10px] text-zinc-600 font-mono">
                          {trailingMarket.yes_ask}¢
                        </span>
                      )}
                      <span
                        className={`text-sm font-bold ${g.away_score > g.home_score ? "text-amber-100" : "text-zinc-500"}`}
                      >
                        {g.away_score}
                      </span>
                    </div>
                    <div className="flex items-center gap-2 justify-end">
                      {g.home_team === leadingTeam && leadingMarket && (
                        <span className="text-[10px] text-green-400 font-mono">
                          {leadingMarket.yes_ask}¢
                        </span>
                      )}
                      {g.home_team === trailingTeam && trailingMarket && (
                        <span className="text-[10px] text-zinc-600 font-mono">
                          {trailingMarket.yes_ask}¢
                        </span>
                      )}
                      <span
                        className={`text-sm font-bold ${g.home_score > g.away_score ? "text-amber-100" : "text-zinc-500"}`}
                      >
                        {g.home_score}
                      </span>
                    </div>
                  </div>
                </div>
                {g.state === "in" && (
                  <div className="mt-2 text-xs text-amber-700">
                    {formatGameTime(g)}
                  </div>
                )}
              </div>
            );
          })}
      </div>
    </div>
  );
}

function LoginForm({ onLogin }: { onLogin: () => void }) {
  const [password, setPassword] = useState("");
  const [error, setError] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const result = await login(password);
    if (result.success) {
      onLogin();
    } else {
      setError(true);
      setPassword("");
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-black text-white p-6">
      <div className="w-full max-w-md">
        <div className="text-center mb-10 animate-fade-in">
          <h1 className="text-3xl font-black gold-shimmer tracking-tight mb-2">
            Kalshi Sports Market Scanner
          </h1>
          <p className="text-zinc-500 text-sm">Authentication Required</p>
        </div>

        <div className="animate-fade-in">
          {/* Password Form */}
          <form
            onSubmit={handleSubmit}
            className="gold-glow bg-zinc-900/90 border border-amber-900/40 rounded-xl p-8 backdrop-blur-sm"
          >
            <input
              type="password"
              value={password}
              onChange={(e) => {
                setPassword(e.target.value);
                setError(false);
              }}
              placeholder="Password"
              className="w-full bg-zinc-800/80 border border-amber-900/30 rounded-lg px-4 py-3 text-white placeholder-zinc-500 mb-4 focus:outline-none focus:border-amber-600 transition-colors"
              autoFocus
            />
            {error && (
              <p className="text-red-400 text-sm mb-4">Wrong password</p>
            )}
            <button
              type="submit"
              className="w-full bg-gradient-to-r from-amber-700 via-amber-500 to-amber-700 text-black font-bold py-3 rounded-lg hover:from-amber-600 hover:via-amber-400 hover:to-amber-600 transition-all shadow-lg shadow-amber-900/30"
            >
              Enter
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}

function useLiveGames(authed: boolean | null) {
  const [games, setGames] = useState<LiveGame[]>([]);

  useEffect(() => {
    if (!authed) return;

    const fetchGames = async () => {
      try {
        const res = await fetch(`${API}/api/live-games`);
        const data = await res.json();
        setGames(data.games);
      } catch {
        // ignore
      }
    };

    fetchGames();
    const interval = setInterval(fetchGames, 5000);
    return () => clearInterval(interval);
  }, [authed]);

  return games;
}

interface RawStrategy {
  name: string;
  live: boolean;
}

// Raw-YAML catalog editor. Load pulls the current strategies.yaml text; Save
// validates server-side, atomically writes the file, and the scanner hot-reloads
// it on the next tick. A failed save shows the loader's error verbatim and leaves
// the running catalog untouched.
function CatalogEditor({ dryRun }: { dryRun: boolean }) {
  const [content, setContent] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState<RawStrategy[] | null>(null);

  const load = async () => {
    setError(null);
    setSaved(null);
    try {
      const res = await fetch(`${API}/api/strategies/raw`);
      if (res.ok) setContent((await res.json()).content);
      else setError(`Load failed (${res.status})`);
    } catch {
      setError("Cannot reach API");
    }
  };

  useEffect(() => {
    load();
  }, []);

  const save = async () => {
    if (content === null) return;
    setSaving(true);
    setError(null);
    setSaved(null);
    try {
      const res = await fetch(`${API}/api/strategies/raw`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ content }),
      });
      const data = await res.json();
      if (res.ok) {
        setSaved(data.strategies as RawStrategy[]);
      } else {
        setError(
          typeof data.detail === "string"
            ? data.detail
            : JSON.stringify(data.detail, null, 2),
        );
      }
    } catch {
      setError("Save request failed");
    } finally {
      setSaving(false);
    }
  };

  // Live money moves on the next tick only when a live-enabled strategy was
  // saved while dry-run mode is off.
  const liveWarning = saved && !dryRun && saved.some((s) => s.live);

  return (
    <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-sm text-amber-600 font-medium">
          Strategy Catalog (strategies.yaml)
        </h2>
        <div className="flex gap-2">
          <button
            onClick={load}
            disabled={saving}
            className="px-4 py-1.5 rounded-lg text-sm font-bold bg-zinc-800 text-zinc-300 hover:bg-zinc-700 disabled:opacity-50 transition-all"
          >
            Reload
          </button>
          <button
            onClick={save}
            disabled={saving || content === null}
            className="px-4 py-1.5 rounded-lg text-sm font-bold bg-amber-600 text-black hover:bg-amber-500 disabled:opacity-50 transition-all"
          >
            {saving ? "Saving…" : "Save"}
          </button>
        </div>
      </div>

      <textarea
        value={content ?? ""}
        onChange={(e) => {
          setContent(e.target.value);
          setSaved(null);
          setError(null);
        }}
        spellCheck={false}
        rows={20}
        placeholder={content === null ? "Loading…" : ""}
        className="w-full bg-black/40 border border-zinc-800 rounded-lg p-3 font-mono text-xs text-amber-100 focus:outline-none focus:border-amber-600 transition-colors resize-y"
      />

      {error && (
        <pre className="mt-3 whitespace-pre-wrap break-words rounded-lg border border-red-900/60 bg-red-950/40 p-3 font-mono text-xs text-red-300">
          {error}
        </pre>
      )}

      {saved && !error && (
        <div className="mt-3 rounded-lg border border-green-900/60 bg-green-950/30 p-3 text-xs text-green-300">
          Saved {saved.length} strateg{saved.length === 1 ? "y" : "ies"}. The
          scanner picks it up on the next tick.
        </div>
      )}

      {liveWarning && (
        <div className="mt-3 rounded-lg border border-yellow-700/70 bg-yellow-950/40 p-3 text-xs font-bold text-yellow-300">
          ⚠ A live-enabled strategy is active and dry-run mode is OFF — real
          money moves on the next scan tick.
        </div>
      )}
    </div>
  );
}

export default function Dashboard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [allTrades, setAllTrades] = useState<Trade[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [sportStats, setSportStats] = useState<Record<
    string,
    { played: number; wins: number; pnl: number }
  > | null>(null);
  const [config, setConfig] = useState<AppConfig | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"trades" | "losses" | "opportunities">(
    "trades",
  );
  const [mainTab, setMainTab] = useState<
    "overview" | "charts" | "sports" | "live_games" | "config" | "trades"
  >("overview");
  const [isTradingTransition, setIsTradingTransition] = useState<
    "pausing" | "resuming" | null
  >(null);
  const games = useLiveGames(authed);

  // Population filter (issue #16): null until config loads, then defaults to
  // the current trading mode. Once the user toggles, their choice sticks.
  const [population, setPopulation] = useState<Population | null>(null);
  const pop: Population =
    population ?? (config?.trading.dry_run ? "dry_run" : "live");

  useEffect(() => {
    checkAuth().then(setAuthed);
  }, []);

  // Fast poll: live stats, recent trades, opportunities (every 10s only)
  useEffect(() => {
    if (!authed) return;

    const fetchData = async () => {
      try {
        const [statsRes, tradesRes, oppsRes] = await Promise.all([
          fetch(`${API}/api/stats`),
          fetch(`${API}/api/trades?limit=50`),
          fetch(`${API}/api/opportunities?limit=50`),
        ]);
        if (statsRes.status === 401 || statsRes.status === 403) {
          setError(
            `API auth failed (${statsRes.status}): check API_TOKEN in .env and restart the dashboard`,
          );
          return;
        }
        if (statsRes.ok) setStats(await statsRes.json());
        else setError(`API returned ${statsRes.status}`);
        if (tradesRes.ok) setTrades((await tradesRes.json()).trades ?? []);
        if (oppsRes.ok)
          setOpportunities((await oppsRes.json()).opportunities ?? []);
        if (statsRes.ok) setError(null);
      } catch {
        setError("Cannot connect to API");
      }
    };

    fetchData();
    const interval = setInterval(fetchData, 10000);
    return () => clearInterval(interval);
  }, [authed]);

  // Slow poll: full trade history + infrequently-changing data (every 60s)
  useEffect(() => {
    if (!authed) return;

    const fetchSlow = async () => {
      try {
        const [tradesRes, configRes, ssRes] = await Promise.all([
          fetch(`${API}/api/histogram-trades?limit=10000`),
          fetch(`${API}/api/config`),
          fetch(`${API}/api/sport-stats`),
        ]);
        if (tradesRes.ok) setAllTrades((await tradesRes.json()).trades ?? []);
        if (configRes.ok) setConfig(await configRes.json());
        if (ssRes.ok) setSportStats((await ssRes.json()).stats);
      } catch {
        // non-critical
      }
    };

    fetchSlow();
    const interval = setInterval(fetchSlow, 60000);
    return () => clearInterval(interval);
  }, [authed]);

  // Re-fetch full history immediately whenever a new trade appears in the fast poll
  const latestTradeId = trades[0]?.id;
  useEffect(() => {
    if (!authed || !latestTradeId) return;
    fetch(`${API}/api/histogram-trades?limit=10000`)
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data) setAllTrades(data.trades);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [latestTradeId]);

  if (authed === null) return <div className="min-h-screen bg-black" />;
  if (!authed) return <LoginForm onLogin={() => setAuthed(true)} />;

  if (error) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-center animate-fade-in">
          <h1 className="text-2xl font-bold mb-2 gold-shimmer">
            Kalshi Sports Market Scanner
          </h1>
          <p className="text-amber-700">{error}</p>
          <p className="text-zinc-500 text-sm mt-2">
            Make sure the API is running
          </p>
        </div>
      </div>
    );
  }

  if (!stats) {
    return (
      <div className="min-h-screen bg-black text-white flex items-center justify-center">
        <div className="text-amber-500 gold-shimmer text-lg font-bold">
          Loading...
        </div>
      </div>
    );
  }

  return (
    <div className="min-h-screen bg-black text-white p-6">
      {isTradingTransition && (
        <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/60 backdrop-blur-sm animate-fade-in">
          <div className="gold-glow bg-zinc-900/90 border border-amber-900/40 p-8 rounded-xl shadow-2xl flex flex-col items-center gap-4">
            <div className="w-12 h-12 border-4 border-amber-500 border-t-transparent rounded-full animate-spin"></div>
            <h2 className="text-2xl font-black gold-shimmer tracking-tight">
              {isTradingTransition === "pausing"
                ? "Pausing trading..."
                : "Resuming trading..."}
            </h2>
          </div>
        </div>
      )}
      <div
        className={`${isTradingTransition ? "blur-sm pointer-events-none" : ""} transition-all duration-300 max-w-7xl mx-auto`}
      >
        {/* Sticky Header Container */}
        <div className="sticky top-0 z-50 bg-black/95 backdrop-blur-md pt-2 pb-4 mb-8 border-b border-zinc-800 shadow-[0_10px_30px_-10px_rgba(0,0,0,0.8)] mx-[-1rem] px-4 md:mx-0 md:px-0">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-4 animate-fade-in">
            <div>
              <h1 className="text-3xl md:text-4xl font-black gold-shimmer tracking-tight">
                Kalshi Sports Market Scanner
              </h1>
              <a
                href="/backtest"
                className="inline-block mt-2 px-4 py-2 rounded-lg text-sm font-bold transition-all bg-zinc-900 text-zinc-400 hover:text-amber-500 hover:bg-zinc-800"
              >
                Strategy Backtest →
              </a>
              <a
                href="/analytics"
                className="inline-block mt-2 ml-2 px-4 py-2 rounded-lg text-sm font-bold transition-all bg-zinc-900 text-zinc-400 hover:text-amber-500 hover:bg-zinc-800"
              >
                Analytics →
              </a>
            </div>
            {config && (
              <div className="flex flex-wrap gap-3">
                <button
                  onClick={async () => {
                    try {
                      const newVal = !config.trading.paused;
                      setIsTradingTransition(newVal ? "pausing" : "resuming");
                      await new Promise((r) => setTimeout(r, 1000)); // Brief delay to ensure overlay is visible
                      const res = await updateConfig(
                        "trading_paused",
                        newVal ? "true" : "false",
                      );
                      if (res.success) {
                        setConfig({
                          ...config,
                          trading: { ...config.trading, paused: newVal },
                        });
                      } else {
                        console.error("updateConfig failed:", res);
                        alert(
                          `Failed to update config. Debug info: ${res.error}`,
                        );
                      }
                    } catch (e) {
                      console.error("Error updating config:", e);
                      alert("Error while updating config.");
                    } finally {
                      setIsTradingTransition(null);
                    }
                  }}
                  className={`px-6 py-2 rounded-lg font-bold transition-all shadow-lg cursor-pointer relative z-10 pointer-events-auto ${
                    config.trading.paused
                      ? "bg-amber-600 text-black hover:bg-amber-500 shadow-amber-900/30"
                      : "bg-red-900/40 text-red-500 border border-red-900 hover:bg-red-900/60"
                  }`}
                >
                  {config.trading.paused ? "Resume Trading" : "Pause Trading"}
                </button>
                <button
                  onClick={async () => {
                    // Disabling dry-run starts real-money trading (still
                    // subject to the kill switch) — confirm first.
                    const goingLive = config.trading.dry_run;
                    if (
                      goingLive &&
                      !window.confirm(
                        "Disable dry-run mode? The scanner will place REAL orders on the next scan tick (still subject to the pause kill switch).",
                      )
                    ) {
                      return;
                    }
                    const newVal = !config.trading.dry_run;
                    try {
                      const res = await updateConfig(
                        "dry_run",
                        newVal ? "true" : "false",
                      );
                      if (res.success) {
                        setConfig({
                          ...config,
                          trading: { ...config.trading, dry_run: newVal },
                        });
                      } else {
                        console.error("updateConfig failed:", res);
                        alert(
                          `Failed to update config. Debug info: ${res.error}`,
                        );
                      }
                    } catch (e) {
                      console.error("Error updating config:", e);
                      alert("Error while updating config.");
                    }
                  }}
                  className={`px-6 py-2 rounded-lg font-bold transition-all shadow-lg cursor-pointer relative z-10 pointer-events-auto ${
                    config.trading.dry_run
                      ? "bg-green-900/40 text-green-400 border border-green-900 hover:bg-green-900/60"
                      : "bg-yellow-600 text-black hover:bg-yellow-500 shadow-yellow-900/30"
                  }`}
                >
                  {config.trading.dry_run ? "Go Live" : "Enable Dry Run"}
                </button>
              </div>
            )}
          </div>

          {/* Main Tabs */}
          <div className="flex flex-wrap gap-2 animate-fade-in">
            {[
              { id: "overview", label: "Overview" },
              { id: "charts", label: "Charts" },
              { id: "sports", label: "Sports" },
              { id: "live_games", label: "Live Games" },
              { id: "config", label: "Config" },
              { id: "trades", label: "Recent Trades" },
            ].map((t) => (
              <button
                key={t.id}
                onClick={() => setMainTab(t.id as any)}
                className={`px-4 py-2 rounded-lg text-sm font-bold transition-all ${
                  mainTab === t.id
                    ? "bg-amber-600 text-black shadow-lg shadow-amber-900/30"
                    : "bg-zinc-900 text-zinc-400 hover:text-amber-500 hover:bg-zinc-800"
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        {mainTab === "config" && (
          <>
            <div className="grid grid-cols-1 mb-8 animate-fade-in">
              <div className="space-y-6">
                {config && (
                  <div className="bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 backdrop-blur-sm">
                    <h2 className="text-sm text-amber-600 font-medium mb-4">
                      Scanner Configuration
                    </h2>
                    <div className="grid grid-cols-2 md:grid-cols-3 gap-3 mb-5">
                      <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                        <div className="text-zinc-500 text-xs">Max Bet</div>
                        <div className="text-amber-200 text-lg font-bold font-mono">
                          {config.trading.bet_percent}%
                        </div>
                      </div>
                      <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                        <div className="text-zinc-500 text-xs">
                          Max Positions
                        </div>
                        <div className="text-amber-200 text-lg font-bold font-mono">
                          {config.trading.max_positions}
                        </div>
                      </div>
                      <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                        <div className="text-zinc-500 text-xs">Mode</div>
                        <div
                          className={`text-lg font-bold ${config.trading.paused ? "text-red-500" : config.trading.dry_run ? "text-yellow-400" : "text-green-400"}`}
                        >
                          {config.trading.paused
                            ? "PAUSED"
                            : config.trading.dry_run
                              ? "DRY RUN"
                              : "LIVE"}
                        </div>
                      </div>
                    </div>
                    <div className="flex flex-wrap gap-4 mb-5 text-xs text-zinc-500">
                      <span>ESPN: {config.polling.espn_interval_s}s</span>
                      <span>
                        Kalshi scan: {config.polling.kalshi_scan_interval_s}s
                      </span>
                      <span>
                        Kalshi WS:{" "}
                        {config.polling.kalshi_ws ? "✓ real-time" : "off"}
                      </span>
                      <span>Stretch min: {config.stretch.price_min}¢</span>
                      <span>
                        DB backup: {config.polling.db_backup_interval_s / 60}m
                      </span>
                    </div>
                    <div className="overflow-x-auto">
                      <table className="w-full text-xs">
                        <thead>
                          <tr className="text-zinc-500 border-b border-zinc-800">
                            <th className="text-left py-2 pr-4">Sport</th>
                            <th className="text-left py-2 pr-4">
                              Kalshi Series
                            </th>
                            <th className="text-center py-2 pr-4">
                              Final Period
                            </th>
                            <th className="text-center py-2 pr-4">
                              End-of-Game
                            </th>
                          </tr>
                        </thead>
                        <tbody>
                          {config.sports.map((s) => (
                            <tr
                              key={s.sport_path}
                              className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                            >
                              <td className="py-2 pr-4 text-amber-200 font-medium">
                                {s.name}
                              </td>
                              <td className="py-2 pr-4 text-zinc-400 font-mono">
                                {s.kalshi_series}
                              </td>
                              <td className="py-2 pr-4 text-center text-zinc-300">
                                {s.clock_direction === "none"
                                  ? `Inning ${s.final_period}`
                                  : `P${s.final_period}`}
                              </td>
                              <td className="py-2 pr-4 text-center text-zinc-300">
                                {s.final_minutes_desc}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
                <CatalogEditor dryRun={config?.trading.dry_run ?? true} />
              </div>
            </div>
          </>
        )}

        {mainTab === "overview" && (
          <>
            {/* Population filter: Live | Dry-run (issue #16) */}
            <PopulationToggle population={pop} onChange={setPopulation} />

            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
              <StatCard
                label="Balance"
                value={cents(stats.balance_cents)}
                delay={0}
              />
              <StatCard
                label="On the Line"
                value={cents(stats[pop].open_cost_cents || 0)}
                sub={`${stats[pop].open_positions || 0} open positions`}
                delay={50}
              />
              <StatCard
                label="Win Rate"
                value={`${stats[pop].win_rate}%`}
                sub={`${stats[pop].wins}W / ${stats[pop].losses}L`}
                delay={100}
              />
              <StatCard
                label="Realized P&L"
                value={cents(stats[pop].realized_pnl_cents)}
                delay={150}
              />
              <StatCard
                label="Trades"
                value={String(stats[pop].trades)}
                sub={`${cents(stats[pop].total_cost_cents)} deployed`}
                delay={200}
              />
              <StatCard
                label="Fees"
                value={cents(stats[pop].total_fees_cents)}
                sub="Total fees"
                delay={250}
              />
            </div>

            {/* P&L Chart */}
            <PnlChart
              trades={allTrades.some((t) => t.placed_at) ? allTrades : trades}
              population={pop}
              balanceCents={stats.balance_cents}
              portfolioCents={stats.portfolio_value_cents}
            />

            {/* Per-strategy cumulative P&L */}
            <StrategyPnlChart trades={allTrades} population={pop} />
          </>
        )}

        {mainTab === "charts" && (
          <>
            {/* Contract Value Histogram */}
            <ContractValueHistogram trades={allTrades} />

            {/* P&L Histogram */}
            <PnlHistogram trades={allTrades} />

            {/* Time Remaining Histograms */}
            <TimeHistogram trades={allTrades} />
            <TimePnlHistogram trades={allTrades} />
          </>
        )}

        {mainTab === "sports" && (
          <>
            {/* Sport Stats Charts */}
            {sportStats && <SportStatsCharts stats={sportStats} />}
          </>
        )}

        {mainTab === "live_games" && (
          <>
            {/* Live Games */}
            <LiveGamesPanel games={games} />
          </>
        )}

        {mainTab === "trades" && (
          <div className="animate-fade-in">
            {/* Tabs */}
            <div className="flex gap-4 mb-4">
              <button
                onClick={() => setTab("trades")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  tab === "trades"
                    ? "bg-gradient-to-r from-amber-900/50 to-amber-800/50 text-amber-200 border border-amber-700/50 shadow-lg shadow-amber-900/20"
                    : "text-zinc-500 hover:text-amber-400"
                }`}
              >
                Recent Trades
              </button>
              <button
                onClick={() => setTab("losses")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  tab === "losses"
                    ? "bg-gradient-to-r from-amber-900/50 to-amber-800/50 text-amber-200 border border-amber-700/50 shadow-lg shadow-amber-900/20"
                    : "text-zinc-500 hover:text-amber-400"
                }`}
              >
                Recent Losses
              </button>
              <button
                onClick={() => setTab("opportunities")}
                className={`px-4 py-2 rounded-lg text-sm font-medium transition-all ${
                  tab === "opportunities"
                    ? "bg-gradient-to-r from-amber-900/50 to-amber-800/50 text-amber-200 border border-amber-700/50 shadow-lg shadow-amber-900/20"
                    : "text-zinc-500 hover:text-amber-400"
                }`}
              >
                Recent Opportunities
              </button>
            </div>

            {/* Trades Table */}
            {tab === "trades" && (
              <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl overflow-hidden backdrop-blur-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm whitespace-nowrap md:whitespace-normal">
                    <thead>
                      <tr className="border-b border-amber-900/20 text-amber-600">
                        <th className="text-left p-3">Time</th>
                        <th className="text-left p-3">Market</th>
                        <th className="text-right p-3">Time Left</th>
                        <th className="text-right p-3">Qty</th>
                        <th className="text-right p-3">Price</th>
                        <th className="text-right p-3">Cost</th>
                        <th className="text-right p-3">Potential</th>
                        <th className="text-right p-3">P&L</th>
                        <th className="text-right p-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {trades.length === 0 && (
                        <tr>
                          <td
                            colSpan={9}
                            className="p-8 text-center text-amber-900"
                          >
                            No trades yet. Scanner is watching for
                            opportunities.
                          </td>
                        </tr>
                      )}
                      {trades.map((t) => (
                        <tr
                          key={t.id}
                          className="border-b border-amber-900/10 hover:bg-amber-900/10 transition-colors"
                        >
                          <td className="p-3 text-amber-700">
                            {t.placed_at ? timeAgo(t.placed_at) : "-"}
                          </td>
                          <td className="p-3">
                            <div className="text-amber-100 truncate max-w-xs">
                              {t.title}
                            </div>
                            <div className="text-amber-800 text-xs">
                              {t.ticker}
                            </div>
                            {t.strategy_name && (
                              <a
                                href={`/analytics?strategy=${encodeURIComponent(t.strategy_name)}`}
                                className="text-xs text-amber-600 hover:text-amber-400"
                              >
                                {t.strategy_name}
                              </a>
                            )}
                          </td>
                          <td className="p-3 text-right text-amber-500 font-mono text-xs">
                            {t.espn_clock_seconds !== null
                              ? `${Math.floor(t.espn_clock_seconds / 60)}:${(t.espn_clock_seconds % 60).toString().padStart(2, "0")}`
                              : "-"}
                          </td>
                          <td className="p-3 text-right text-amber-200">
                            {t.count}
                          </td>
                          <td className="p-3 text-right text-amber-200">
                            {t.yes_price}c
                          </td>
                          <td className="p-3 text-right text-amber-200">
                            {cents(t.cost_cents)}
                          </td>
                          <td className="p-3 text-right text-green-400">
                            +{cents(t.potential_profit_cents)}
                          </td>
                          <td className="p-3 text-right">
                            {t.pnl_cents !== null ? (
                              <span
                                className={
                                  t.pnl_cents >= 0
                                    ? "text-green-400"
                                    : "text-red-400"
                                }
                              >
                                {t.pnl_cents >= 0 ? "+" : ""}
                                {cents(t.pnl_cents)}
                              </span>
                            ) : (
                              <span className="text-zinc-600">-</span>
                            )}
                          </td>
                          <td className="p-3 text-right">
                            <StatusBadge status={t.status} dryRun={t.dry_run} />
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Losses Table */}
            {tab === "losses" && (
              <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl overflow-hidden backdrop-blur-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm whitespace-nowrap md:whitespace-normal">
                    <thead>
                      <tr className="border-b border-amber-900/20 text-amber-600">
                        <th className="text-left p-3">Time</th>
                        <th className="text-left p-3">Market</th>
                        <th className="text-right p-3">Time Left</th>
                        <th className="text-right p-3">Qty</th>
                        <th className="text-right p-3">Price</th>
                        <th className="text-right p-3">Cost</th>
                        <th className="text-right p-3">Potential</th>
                        <th className="text-right p-3">P&L</th>
                        <th className="text-right p-3">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {allTrades.filter(
                        (t) => t.pnl_cents !== null && t.pnl_cents < 0,
                      ).length === 0 && (
                        <tr>
                          <td
                            colSpan={9}
                            className="p-8 text-center text-amber-900"
                          >
                            No losses in recent trades.
                          </td>
                        </tr>
                      )}
                      {allTrades
                        .filter((t) => t.pnl_cents !== null && t.pnl_cents < 0)
                        .map((t) => (
                          <tr
                            key={t.id}
                            className="border-b border-amber-900/10 hover:bg-amber-900/10 transition-colors"
                          >
                            <td className="p-3 text-amber-700">
                              {t.placed_at ? timeAgo(t.placed_at) : "-"}
                            </td>
                            <td className="p-3">
                              <div className="text-amber-100 truncate max-w-xs">
                                {t.title}
                              </div>
                              <div className="text-amber-800 text-xs">
                                {t.ticker}
                              </div>
                            </td>
                            <td className="p-3 text-right text-amber-500 font-mono text-xs">
                              {t.espn_clock_seconds !== null
                                ? `${Math.floor(t.espn_clock_seconds / 60)}:${(t.espn_clock_seconds % 60).toString().padStart(2, "0")}`
                                : "-"}
                            </td>
                            <td className="p-3 text-right text-amber-200">
                              {t.count}
                            </td>
                            <td className="p-3 text-right text-amber-200">
                              {t.yes_price}c
                            </td>
                            <td className="p-3 text-right text-amber-200">
                              {cents(t.cost_cents)}
                            </td>
                            <td className="p-3 text-right text-green-400">
                              +{cents(t.potential_profit_cents)}
                            </td>
                            <td className="p-3 text-right">
                              <span className="text-red-400">
                                {cents(t.pnl_cents!)}
                              </span>
                            </td>
                            <td className="p-3 text-right">
                              <StatusBadge
                                status={t.status}
                                dryRun={t.dry_run}
                              />
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {/* Opportunities Table */}
            {tab === "opportunities" && (
              <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl overflow-hidden backdrop-blur-sm">
                <div className="overflow-x-auto">
                  <table className="w-full text-sm whitespace-nowrap md:whitespace-normal">
                    <thead>
                      <tr className="border-b border-amber-900/20 text-amber-600">
                        <th className="text-left p-3">Found</th>
                        <th className="text-left p-3">Market</th>
                        <th className="text-left p-3">Sport</th>
                        <th className="text-right p-3">Yes Bid</th>
                        <th className="text-right p-3">Yes Ask</th>
                        <th className="text-right p-3">Spread</th>
                        <th className="text-right p-3">Volume</th>
                      </tr>
                    </thead>
                    <tbody>
                      {opportunities.length === 0 && (
                        <tr>
                          <td
                            colSpan={7}
                            className="p-8 text-center text-amber-900"
                          >
                            No opportunities found yet.
                          </td>
                        </tr>
                      )}
                      {opportunities.map((o) => (
                        <tr
                          key={o.id}
                          className="border-b border-amber-900/10 hover:bg-amber-900/10 transition-colors"
                        >
                          <td className="p-3 text-amber-700">
                            {o.found_at ? timeAgo(o.found_at) : "-"}
                          </td>
                          <td className="p-3">
                            <div className="text-amber-100 truncate max-w-xs">
                              {o.yes_sub_title || o.title}
                            </div>
                            <div className="text-amber-800 text-xs">
                              {o.ticker}
                            </div>
                          </td>
                          <td className="p-3 text-amber-600">
                            {o.series_ticker}
                          </td>
                          <td className="p-3 text-right text-amber-200">
                            {o.yes_bid}c
                          </td>
                          <td className="p-3 text-right text-amber-200">
                            {o.yes_ask}c
                          </td>
                          <td className="p-3 text-right text-green-400">
                            {o.spread}c
                          </td>
                          <td className="p-3 text-right text-amber-600">
                            {o.volume.toLocaleString()}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
