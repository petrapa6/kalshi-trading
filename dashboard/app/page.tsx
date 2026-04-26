"use client";

import { useEffect, useState } from "react";
import { Tweet } from "react-tweet";
import { login, checkAuth, updateConfig } from "./actions";

// Proxied via Next.js to provide secure token headers transparently from the server
const API = "";

interface Stats {
  total_trades: number;
  live_trades: number;
  dry_run_trades: number;
  total_cost_cents: number;
  total_potential_profit_cents: number;
  realized_pnl_cents: number;
  total_fees_cents: number;
  wins: number;
  losses: number;
  win_rate: number;
  total_scans: number;
  total_opportunities: number;
  balance_cents: number;
  portfolio_value_cents: number;
  open_positions: number;
  open_cost_cents: number;
  open_potential_profit_cents: number;
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

interface BalanceSnapshot {
  recorded_at: string;
  balance_cents: number;
  portfolio_value_cents: number;
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
  min_score_lead: number;
  stretch_score_lead: number;
  clock_direction: "down" | "up" | "none";
  final_minutes_desc: string;
  final_minutes_seconds: number | null;
}

interface AppConfig {
  trading: {
    min_yes_price: number;
    bet_percent: number;
    max_positions: number;
    min_volume: number;
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

interface StrategySetStats {
  label: string;
  total: number;
  wins: number;
  losses: number;
  open: number;
  win_rate: number;
  hypothetical_pnl_cents: number;
  by_reason: Record<
    string,
    { total: number; wins: number; losses: number; pnl_cents: number }
  >;
}

interface StretchStats {
  total: number;
  wins: number;
  losses: number;
  open: number;
  win_rate: number;
  hypothetical_pnl_cents: number;
  by_reason: Record<
    string,
    { total: number; wins: number; losses: number; pnl_cents: number }
  >;
  strategies: Record<string, StrategySetStats>;
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

function PnlChart({
  trades,
  balanceCents,
  portfolioCents,
}: {
  trades: Trade[];
  balanceCents: number;
  portfolioCents: number;
}) {
  const [hoverIdx, setHoverIdx] = useState<number | null>(null);
  const [viewMode, setViewMode] = useState<"trade" | "day" | "week" | "month">(
    "trade",
  );

  const totalNow = balanceCents + portfolioCents;

  const settledTrades = trades
    .filter((t) => !t.dry_run && t.pnl_cents !== null && t.placed_at)
    .sort(
      (a, b) =>
        new Date(a.placed_at).getTime() - new Date(b.placed_at).getTime(),
    );

  let totalPnl = 0;
  for (const t of settledTrades) totalPnl += t.pnl_cents!;
  const startingBalance = totalNow - totalPnl;

  // --- Bucket helpers ---
  const bucketKey = (d: Date): string => {
    if (viewMode === "day")
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    if (viewMode === "week") {
      const tmp = new Date(d);
      tmp.setHours(0, 0, 0, 0);
      tmp.setDate(tmp.getDate() - (tmp.getDay() === 0 ? 6 : tmp.getDay() - 1));
      return `${tmp.getFullYear()}-W${String(tmp.getMonth() + 1).padStart(2, "0")}-${String(tmp.getDate()).padStart(2, "0")}`;
    }
    if (viewMode === "month")
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    return d.toISOString(); // "trade": unique per trade
  };

  const formatBucketLabel = (d: Date): string => {
    if (viewMode === "trade")
      return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`;
    if (viewMode === "day") return `${d.getMonth() + 1}/${d.getDate()}`;
    if (viewMode === "week") {
      const tmp = new Date(d);
      tmp.setDate(tmp.getDate() - (tmp.getDay() === 0 ? 6 : tmp.getDay() - 1));
      return `${tmp.getMonth() + 1}/${tmp.getDate()}`;
    }
    return d.toLocaleString("default", { month: "short", year: "2-digit" });
  };

  // Group into ordered buckets (Map preserves insertion order, trades already sorted)
  const bucketMap = new Map<string, { pnl: number; date: Date }>();
  for (const t of settledTrades) {
    const d = new Date(t.placed_at);
    const key = bucketKey(d);
    if (!bucketMap.has(key)) bucketMap.set(key, { pnl: 0, date: d });
    bucketMap.get(key)!.pnl += t.pnl_cents!;
  }
  const allBuckets = Array.from(bucketMap.values());

  // Limit to last 20 points; accumulate earlier P&L into windowStartBalance
  const WINDOW = 20;
  const hiddenBuckets =
    allBuckets.length > WINDOW ? allBuckets.slice(0, -WINDOW) : [];
  const buckets =
    allBuckets.length > WINDOW ? allBuckets.slice(-WINDOW) : allBuckets;
  const windowStartBalance =
    startingBalance + hiddenBuckets.reduce((s, b) => s + b.pnl, 0);

  type Step = {
    value: number;
    label: string;
    date: Date | null;
    periodPnl: number;
  };
  const steps: Step[] = [
    {
      value: windowStartBalance,
      label: "Start",
      date: buckets.length > 0 ? buckets[0].date : null,
      periodPnl: 0,
    },
  ];
  let runningValue = windowStartBalance;
  for (const { pnl, date } of buckets) {
    runningValue += pnl;
    steps.push({
      value: runningValue,
      label: formatBucketLabel(date),
      date,
      periodPnl: pnl,
    });
  }
  steps.push({ value: totalNow, label: "Now", date: new Date(), periodPnl: 0 });

  // --- SVG geometry ---
  const values = steps.map((s) => s.value);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const dataRange = rawMax - rawMin || 1;
  const padding = dataRange * 0.35;
  const yMin = rawMin - padding;
  const yMax = rawMax + padding;
  const range = yMax - yMin;

  const w = 800,
    h = 200;
  const padLeft = 60,
    padRight = 12,
    padTop = 14,
    padBottom = 24;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  const toY = (val: number) =>
    padTop + chartH - ((val - yMin) / range) * chartH;

  type Point = {
    x: number;
    y: number;
    value: number;
    label: string;
    date: Date | null;
    periodPnl: number;
  };
  const points: Point[] = [];
  for (let i = 0; i < steps.length; i++) {
    const x = padLeft + (i / (steps.length - 1)) * chartW;
    const y = toY(steps[i].value);
    // Step-function: horizontal helper point (same x, previous y) then the real data point
    if (i > 0)
      points.push({
        x,
        y: toY(steps[i - 1].value),
        value: steps[i - 1].value,
        label: "",
        date: null,
        periodPnl: 0,
      });
    points.push({
      x,
      y,
      value: steps[i].value,
      label: steps[i].label,
      date: steps[i].date,
      periodPnl: steps[i].periodPnl,
    });
  }

  const line = points
    .map((p, i) => `${i === 0 ? "M" : "L"}${p.x},${p.y}`)
    .join(" ");
  const baseY = toY(windowStartBalance);
  const area = `${line} L${points[points.length - 1].x},${baseY} L${points[0].x},${baseY} Z`;

  // X-axis labels only on named (non-blank) points that have a date
  const timeLabels = points
    .filter((p) => p.label && p.date)
    .map((p) => ({ x: p.x, label: p.label }));

  // Only snap hover to real labeled data points — never to intermediate step-function helpers
  const snapPoints = points.filter((p) => p.label !== "");
  const findClosest = (mouseX: number) => {
    let closest = 0,
      closestDist = Infinity;
    for (let i = 0; i < snapPoints.length; i++) {
      const d = Math.abs(snapPoints[i].x - mouseX);
      if (d < closestDist) {
        closestDist = d;
        closest = i;
      }
    }
    return closest;
  };

  const hp = hoverIdx !== null ? snapPoints[hoverIdx] : null;

  const MODES: { key: "trade" | "day" | "week" | "month"; label: string }[] = [
    { key: "trade", label: "Trade" },
    { key: "day", label: "Day" },
    { key: "week", label: "Week" },
    { key: "month", label: "Month" },
  ];

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3 flex-wrap gap-2">
        <h2 className="text-sm text-amber-600 font-medium">Account Value</h2>
        <div className="flex items-center gap-3 flex-wrap">
          {/* View mode toggle */}
          <div className="flex items-center gap-0.5 bg-zinc-800/70 border border-zinc-700/50 rounded-lg p-0.5">
            {MODES.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => {
                  setViewMode(key);
                  setHoverIdx(null);
                }}
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
            {hiddenBuckets.length > 0 && (
              <span className="text-zinc-600 text-xs">last {WINDOW}</span>
            )}
            <span className="text-zinc-500 font-mono">
              {cents(windowStartBalance)}
            </span>
            <span className="text-amber-200 font-bold font-mono">
              {cents(totalNow)}
            </span>
            {(() => {
              const windowPnl = totalNow - windowStartBalance;
              if (windowPnl === 0) return null;
              return (
                <span
                  className={`font-bold font-mono px-2 py-0.5 rounded ${windowPnl > 0 ? "text-green-400 bg-green-900/30" : "text-red-400 bg-red-900/30"}`}
                >
                  {windowPnl > 0 ? "+" : ""}
                  {cents(windowPnl)}
                </span>
              );
            })()}
          </div>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ display: "block", aspectRatio: `${w}/${h}` }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          setHoverIdx(findClosest(((e.clientX - rect.left) / rect.width) * w));
        }}
        onMouseLeave={() => setHoverIdx(null)}
        onTouchMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const touch = e.touches[0];
          setHoverIdx(
            findClosest(((touch.clientX - rect.left) / rect.width) * w),
          );
        }}
        onTouchEnd={() => setHoverIdx(null)}
      >
        <defs>
          <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
            <stop
              offset="0%"
              stopColor={totalNow >= windowStartBalance ? "#4ade80" : "#f87171"}
              stopOpacity="0.3"
            />
            <stop
              offset="100%"
              stopColor={totalNow >= windowStartBalance ? "#4ade80" : "#f87171"}
              stopOpacity="0.02"
            />
          </linearGradient>
        </defs>

        {/* Window-start baseline */}
        <line
          x1={padLeft}
          y1={baseY}
          x2={w - padRight}
          y2={baseY}
          stroke="#78716c"
          strokeWidth="1"
          strokeDasharray="4,4"
        />
        <text
          x={padLeft - 6}
          y={baseY + 4}
          textAnchor="end"
          fill="#78716c"
          fontSize="10"
          fontFamily="monospace"
        >
          {cents(windowStartBalance)}
        </text>

        {/* Current value — dashed ref line only when different from baseline */}
        {totalNow !== windowStartBalance && (
          <line
            x1={padLeft}
            y1={toY(totalNow)}
            x2={w - padRight}
            y2={toY(totalNow)}
            stroke={totalNow >= windowStartBalance ? "#4ade80" : "#f87171"}
            strokeWidth="0.5"
            strokeDasharray="2,4"
            opacity="0.4"
          />
        )}

        {/* X-axis labels */}
        {timeLabels.map(({ x, label }, i) => {
          const parts = label.split(" ");
          return (
            <text
              key={i}
              x={x}
              y={h - (parts.length > 1 ? 14 : 4)}
              textAnchor="middle"
              fill="#78716c"
              fontSize="9"
              fontFamily="monospace"
            >
              {parts.map((p, j) => (
                <tspan key={j} x={x} dy={j === 0 ? 0 : 10}>
                  {p}
                </tspan>
              ))}
            </text>
          );
        })}

        {/* Area + step line */}
        <path d={area} fill="url(#pnlGrad)" />
        <path
          d={line}
          fill="none"
          stroke={totalPnl >= 0 ? "#4ade80" : "#f87171"}
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
        />

        {/* Dots at each data point */}
        {points
          .filter((p) => p.label && !["Start", "Now", ""].includes(p.label))
          .map((p, i) => (
            <circle
              key={i}
              cx={p.x}
              cy={p.y}
              r={viewMode === "trade" ? 4 : 3}
              fill={p.periodPnl >= 0 ? "#4ade80" : "#f87171"}
              stroke="#000"
              strokeWidth="1"
            />
          ))}

        {/* Animated end dot */}
        {hoverIdx === null && points.length > 0 && (
          <circle
            cx={points[points.length - 1].x}
            cy={points[points.length - 1].y}
            r="4"
            fill={totalPnl >= 0 ? "#4ade80" : "#f87171"}
            className="animate-pulse"
          />
        )}

        {/* Hover tooltip */}
        {hp && (
          <>
            <line
              x1={hp.x}
              y1={padTop}
              x2={hp.x}
              y2={padTop + chartH}
              stroke="#d4a017"
              strokeWidth="1"
              strokeDasharray="3,3"
              opacity="0.5"
            />
            <circle
              cx={hp.x}
              cy={hp.y}
              r="5"
              fill="#f0d060"
              stroke="#000"
              strokeWidth="1.5"
            />
            {(() => {
              const showPeriod =
                hp.label && !["Start", "Now", ""].includes(hp.label);
              const tx = hp.x < w / 2 ? hp.x + 10 : hp.x - 140;
              const ty = Math.max(hp.y - 32, padTop);
              return (
                <>
                  <rect
                    x={tx}
                    y={ty}
                    width="130"
                    height={showPeriod ? 46 : 36}
                    rx="5"
                    fill="#1c1917"
                    stroke="#92400e"
                    strokeWidth="0.5"
                    opacity="0.95"
                  />
                  <text
                    x={tx + 8}
                    y={ty + 16}
                    fill="#fbbf24"
                    fontSize="12"
                    fontWeight="bold"
                    fontFamily="monospace"
                  >
                    {cents(hp.value)}
                  </text>
                  {showPeriod && (
                    <text
                      x={tx + 8}
                      y={ty + 32}
                      fill={hp.periodPnl >= 0 ? "#4ade80" : "#f87171"}
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      {hp.periodPnl >= 0 ? "+" : ""}
                      {cents(hp.periodPnl)}
                      {viewMode !== "trade" ? ` · ${hp.label}` : ""}
                    </text>
                  )}
                </>
              );
            })()}
          </>
        )}
      </svg>
    </div>
  );
}

function ContractValueHistogram({ trades }: { trades: Trade[] }) {
  const [hoverBin, setHoverBin] = useState<number | null>(null);

  // Only settled, non-dry-run trades with a known price and outcome
  const settled = trades.filter(
    (t) =>
      !t.dry_run &&
      t.pnl_cents !== null &&
      t.yes_price != null &&
      (t.status === "settled_win" || t.status === "settled_loss"),
  );

  if (settled.length === 0) {
    return (
      <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">
          Contract Value Distribution
        </h2>
        <p className="text-amber-900 text-sm">
          No settled trades to display yet.
        </p>
      </div>
    );
  }

  const BIN_SIZE = 1; // cents per bucket
  const MIN_PRICE = 85;
  const MAX_PRICE = 100;
  const numBins = (MAX_PRICE - MIN_PRICE) / BIN_SIZE; // 20 bins

  // Count wins and losses per bin
  const bins: { wins: number; losses: number }[] = Array.from(
    { length: numBins },
    () => ({ wins: 0, losses: 0 }),
  );

  for (const t of settled) {
    const binIdx = Math.min(
      Math.floor((t.yes_price - MIN_PRICE) / BIN_SIZE),
      numBins - 1,
    );
    if (binIdx < 0) continue;
    if (t.pnl_cents! >= 0) {
      bins[binIdx].wins++;
    } else {
      bins[binIdx].losses++;
    }
  }

  const maxCount = Math.max(...bins.map((b) => b.wins + b.losses), 1);

  const w = 800;
  const h = 200;
  const padLeft = 40;
  const padRight = 12;
  const padTop = 14;
  const padBottom = 30;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  const barGap = 2;
  const barW = chartW / numBins - barGap;

  const toBarH = (count: number) => (count / maxCount) * chartH;
  const toX = (binIdx: number) =>
    padLeft + binIdx * (chartW / numBins) + barGap / 2;

  // Y-axis grid lines
  const gridLines = [
    Math.round(maxCount * 0.25),
    Math.round(maxCount * 0.5),
    Math.round(maxCount * 0.75),
    maxCount,
  ].filter((v, i, arr) => arr.indexOf(v) === i && v > 0);

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">
          Contract Value Distribution
        </h2>
        <div className="flex items-center gap-4 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-green-500/70 inline-block" />
            Wins ({settled.filter((t) => t.pnl_cents! >= 0).length})
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-red-500/70 inline-block" />
            Losses ({settled.filter((t) => t.pnl_cents! < 0).length})
          </span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ display: "block", aspectRatio: `${w}/${h}` }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const svgX = ((e.clientX - rect.left) / rect.width) * w;
          if (svgX < padLeft || svgX > w - padRight) {
            setHoverBin(null);
            return;
          }
          const binIdx = Math.floor(((svgX - padLeft) / chartW) * numBins);
          setHoverBin(Math.min(Math.max(binIdx, 0), numBins - 1));
        }}
        onMouseLeave={() => setHoverBin(null)}
      >
        <defs>
          <linearGradient id="histWinGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#4ade80" stopOpacity="0.35" />
          </linearGradient>
          <linearGradient id="histLossGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f87171" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#f87171" stopOpacity="0.35" />
          </linearGradient>
        </defs>

        {/* Y-axis grid lines */}
        {gridLines.map((count) => {
          const y = padTop + chartH - toBarH(count);
          return (
            <g key={count}>
              <line
                x1={padLeft}
                y1={y}
                x2={w - padRight}
                y2={y}
                stroke="#3f3f46"
                strokeWidth="0.5"
                strokeDasharray="3,3"
              />
              <text
                x={padLeft - 4}
                y={y + 4}
                textAnchor="end"
                fill="#78716c"
                fontSize="9"
                fontFamily="monospace"
              >
                {count}
              </text>
            </g>
          );
        })}

        {/* Bars */}
        {bins.map((bin, i) => {
          const x = toX(i);
          const winsH = toBarH(bin.wins);
          const lossH = toBarH(bin.losses);
          const baseY = padTop + chartH;
          const isHovered = hoverBin === i;

          return (
            <g key={i} opacity={isHovered ? 1 : 0.85}>
              {/* Losses bar (bottom) */}
              {bin.losses > 0 && (
                <rect
                  x={x}
                  y={baseY - lossH}
                  width={barW}
                  height={lossH}
                  fill="url(#histLossGrad)"
                  rx="1"
                  stroke={isHovered ? "#f87171" : "none"}
                  strokeWidth="0.5"
                />
              )}
              {/* Wins bar (stacked on top of losses) */}
              {bin.wins > 0 && (
                <rect
                  x={x}
                  y={baseY - lossH - winsH}
                  width={barW}
                  height={winsH}
                  fill="url(#histWinGrad)"
                  rx="1"
                  stroke={isHovered ? "#4ade80" : "none"}
                  strokeWidth="0.5"
                />
              )}
            </g>
          );
        })}

        {/* X-axis labels centered under each bar */}
        {Array.from({ length: numBins }, (_, i) => MIN_PRICE + i).map(
          (val, i) => (
            <text
              key={val}
              x={toX(i) + barW / 2}
              y={h - 4}
              textAnchor="middle"
              fill="#78716c"
              fontSize="9"
              fontFamily="monospace"
            >
              {val}
            </text>
          ),
        )}

        {/* Hover indicator & tooltip */}
        {hoverBin !== null &&
          (() => {
            const bin = bins[hoverBin];
            const x = toX(hoverBin) + barW / 2;
            const total = bin.wins + bin.losses;
            const tooltipX = x < w / 2 ? x + 10 : x - 130;
            const tooltipY = padTop;
            const priceLabel = `${MIN_PRICE + hoverBin * BIN_SIZE}¢`;

            return (
              <>
                <line
                  x1={x}
                  y1={padTop}
                  x2={x}
                  y2={padTop + chartH}
                  stroke="#d4a017"
                  strokeWidth="1"
                  strokeDasharray="3,3"
                  opacity="0.5"
                />
                <rect
                  x={tooltipX}
                  y={tooltipY}
                  width="120"
                  height={total > 0 ? 56 : 36}
                  rx="5"
                  fill="#1c1917"
                  stroke="#92400e"
                  strokeWidth="0.5"
                  opacity="0.95"
                />
                <text
                  x={tooltipX + 8}
                  y={tooltipY + 16}
                  fill="#fbbf24"
                  fontSize="11"
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  {priceLabel}
                </text>
                {total > 0 ? (
                  <>
                    <text
                      x={tooltipX + 8}
                      y={tooltipY + 32}
                      fill="#4ade80"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      ✓ {bin.wins} win{bin.wins !== 1 ? "s" : ""}
                    </text>
                    <text
                      x={tooltipX + 8}
                      y={tooltipY + 46}
                      fill="#f87171"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      ✗ {bin.losses} loss{bin.losses !== 1 ? "es" : ""}
                    </text>
                  </>
                ) : (
                  <text
                    x={tooltipX + 8}
                    y={tooltipY + 32}
                    fill="#78716c"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    No trades
                  </text>
                )}
              </>
            );
          })()}
      </svg>
    </div>
  );
}

function PnlHistogram({ trades }: { trades: Trade[] }) {
  const [hoverBin, setHoverBin] = useState<number | null>(null);

  const settled = trades.filter(
    (t) =>
      !t.dry_run &&
      t.pnl_cents !== null &&
      t.yes_price != null &&
      (t.status === "settled_win" || t.status === "settled_loss"),
  );

  if (settled.length === 0) {
    return (
      <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">
          P&L by Contract Value
        </h2>
        <p className="text-amber-900 text-sm">
          No settled trades to display yet.
        </p>
      </div>
    );
  }

  const BIN_SIZE = 1;
  const MIN_PRICE = 85;
  const MAX_PRICE = 100;
  const numBins = (MAX_PRICE - MIN_PRICE) / BIN_SIZE;

  // Sum pnl_cents per bin
  const bins: { pnl: number }[] = Array.from({ length: numBins }, () => ({
    pnl: 0,
  }));
  for (const t of settled) {
    const binIdx = Math.min(
      Math.floor((t.yes_price - MIN_PRICE) / BIN_SIZE),
      numBins - 1,
    );
    if (binIdx < 0) continue;
    bins[binIdx].pnl += t.pnl_cents!;
  }

  const pnlValues = bins.map((b) => b.pnl);
  const maxPnl = Math.max(...pnlValues, 0);
  const minPnl = Math.min(...pnlValues, 0);
  const absMax = Math.max(Math.abs(maxPnl), Math.abs(minPnl), 1);
  const totalPnl = pnlValues.reduce((a, b) => a + b, 0);

  const w = 800;
  const h = 200;
  const padLeft = 52; // wider for "$" labels
  const padRight = 12;
  const padTop = 14;
  const padBottom = 30;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;

  const barGap = 2;
  const barW = chartW / numBins - barGap;
  const toX = (i: number) => padLeft + i * (chartW / numBins) + barGap / 2;

  // Zero baseline — proportional to the range
  const zeroFrac = Math.abs(minPnl) / (absMax * 2 || 1);
  const zeroY =
    padTop +
    chartH -
    (Math.abs(minPnl) / (absMax === 0 ? 1 : absMax)) * (chartH / 2);
  // Simpler: zero is always in the middle when both sides are non-zero, else at edge
  const posZone = maxPnl >= 0 ? (maxPnl / (maxPnl - minPnl || 1)) * chartH : 0;
  const baseY = padTop + posZone; // y coordinate of the zero line

  const toBarY = (pnl: number) => {
    if (pnl >= 0) {
      const frac = pnl / (absMax || 1);
      return baseY - frac * posZone;
    } else {
      const negZone = chartH - posZone;
      const frac = Math.abs(pnl) / (absMax || 1);
      return baseY + frac * negZone;
    }
  };
  const toBarH = (pnl: number) => Math.abs(toBarY(pnl) - baseY);

  // Y-axis reference lines: 25/50/75/100% of absMax on both sides
  const gridValues: number[] = [];
  for (const frac of [0.5, 1.0]) {
    const v = Math.round(absMax * frac);
    if (v > 0) gridValues.push(v, -v);
  }

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">
          P&L by Contract Value
        </h2>
        <span
          className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${totalPnl >= 0 ? "text-green-400 bg-green-900/30" : "text-red-400 bg-red-900/30"}`}
        >
          {totalPnl >= 0 ? "+" : ""}
          {cents(totalPnl)} total
        </span>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ display: "block", aspectRatio: `${w}/${h}` }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const svgX = ((e.clientX - rect.left) / rect.width) * w;
          if (svgX < padLeft || svgX > w - padRight) {
            setHoverBin(null);
            return;
          }
          setHoverBin(
            Math.min(
              Math.max(Math.floor(((svgX - padLeft) / chartW) * numBins), 0),
              numBins - 1,
            ),
          );
        }}
        onMouseLeave={() => setHoverBin(null)}
      >
        <defs>
          <linearGradient id="pnlHistWinGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#4ade80" stopOpacity="0.35" />
          </linearGradient>
          <linearGradient id="pnlHistLossGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f87171" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#f87171" stopOpacity="0.85" />
          </linearGradient>
        </defs>

        {/* Y-axis grid lines */}
        {gridValues.map((v) => {
          const y = toBarY(v);
          const label = `${v >= 0 ? "+" : ""}$${(v / 100).toFixed(2)}`;
          return (
            <g key={v}>
              <line
                x1={padLeft}
                y1={y}
                x2={w - padRight}
                y2={y}
                stroke="#3f3f46"
                strokeWidth="0.5"
                strokeDasharray="3,3"
              />
              <text
                x={padLeft - 4}
                y={y + 4}
                textAnchor="end"
                fill="#78716c"
                fontSize="9"
                fontFamily="monospace"
              >
                {label}
              </text>
            </g>
          );
        })}

        {/* Zero baseline */}
        <line
          x1={padLeft}
          y1={baseY}
          x2={w - padRight}
          y2={baseY}
          stroke="#78716c"
          strokeWidth="1"
        />
        <text
          x={padLeft - 4}
          y={baseY + 4}
          textAnchor="end"
          fill="#78716c"
          fontSize="9"
          fontFamily="monospace"
        >
          $0
        </text>

        {/* Bars */}
        {bins.map((bin, i) => {
          const x = toX(i);
          const isPos = bin.pnl >= 0;
          const barH = toBarH(bin.pnl);
          const barY = isPos ? baseY - barH : baseY;
          const isHovered = hoverBin === i;
          if (barH < 0.5) return null;
          return (
            <rect
              key={i}
              x={x}
              y={barY}
              width={barW}
              height={barH}
              fill={isPos ? "url(#pnlHistWinGrad)" : "url(#pnlHistLossGrad)"}
              rx="1"
              opacity={isHovered ? 1 : 0.85}
              stroke={isHovered ? (isPos ? "#4ade80" : "#f87171") : "none"}
              strokeWidth="0.5"
            />
          );
        })}

        {/* X-axis labels centered under each bar */}
        {Array.from({ length: numBins }, (_, i) => MIN_PRICE + i).map(
          (val, i) => (
            <text
              key={val}
              x={toX(i) + barW / 2}
              y={h - 4}
              textAnchor="middle"
              fill="#78716c"
              fontSize="9"
              fontFamily="monospace"
            >
              {val}
            </text>
          ),
        )}

        {/* Hover crosshair & tooltip */}
        {hoverBin !== null &&
          (() => {
            const bin = bins[hoverBin];
            const x = toX(hoverBin) + barW / 2;
            const tooltipX = x < w / 2 ? x + 10 : x - 130;
            const tooltipY = padTop;
            const priceLabel = `${MIN_PRICE + hoverBin}¢`;
            const pnlLabel = `${bin.pnl >= 0 ? "+" : ""}${cents(bin.pnl)}`;
            const pnlColor = bin.pnl >= 0 ? "#4ade80" : "#f87171";

            return (
              <>
                <line
                  x1={x}
                  y1={padTop}
                  x2={x}
                  y2={padTop + chartH}
                  stroke="#d4a017"
                  strokeWidth="1"
                  strokeDasharray="3,3"
                  opacity="0.5"
                />
                <rect
                  x={tooltipX}
                  y={tooltipY}
                  width="120"
                  height="46"
                  rx="5"
                  fill="#1c1917"
                  stroke="#92400e"
                  strokeWidth="0.5"
                  opacity="0.95"
                />
                <text
                  x={tooltipX + 8}
                  y={tooltipY + 16}
                  fill="#fbbf24"
                  fontSize="11"
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  {priceLabel}
                </text>
                <text
                  x={tooltipX + 8}
                  y={tooltipY + 32}
                  fill={pnlColor}
                  fontSize="10"
                  fontFamily="monospace"
                >
                  {bin.pnl === 0 ? "No P&L" : pnlLabel}
                </text>
              </>
            );
          })()}
      </svg>
    </div>
  );
}

function TimeHistogram({ trades }: { trades: Trade[] }) {
  const [hoverBin, setHoverBin] = useState<number | null>(null);

  // Only countdown-sport settled trades with a known clock reading ≤ 15 min
  const settled = trades.filter(
    (t) =>
      !t.dry_run &&
      t.pnl_cents !== null &&
      t.espn_clock_seconds !== null &&
      t.espn_clock_seconds <= 600 && // ≤ 10 min
      t.espn_clock_seconds >= 0 &&
      (t.status === "settled_win" || t.status === "settled_loss"),
  );

  if (settled.length === 0) {
    return (
      <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">
          Trade Distribution by Time Remaining
        </h2>
        <p className="text-amber-900 text-sm">
          No settled trades with clock data yet.
        </p>
      </div>
    );
  }

  // Bins: 0 = [14:00–15:00), 1 = [13:00–14:00), ..., 14 = [0:00–1:00)
  // i.e. bin i represents (14 - i) minutes remaining → so bin 0 = 15 min left, bin 14 = 0 min left
  // We store as minutes_remaining = floor(seconds / 60), then bin = 9 - minutes_remaining
  const NUM_BINS = 10; // 0–9 minutes

  const bins: { wins: number; losses: number }[] = Array.from(
    { length: NUM_BINS },
    () => ({ wins: 0, losses: 0 }),
  );

  for (const t of settled) {
    const minsRemaining = Math.min(Math.floor(t.espn_clock_seconds! / 60), 9);
    const binIdx = 9 - minsRemaining; // 0 = 10 min left → bin 0 on left; 9 = 0 min → bin 9 on right
    if (t.pnl_cents! >= 0) bins[binIdx].wins++;
    else bins[binIdx].losses++;
  }

  const maxCount = Math.max(...bins.map((b) => b.wins + b.losses), 1);

  const w = 800;
  const h = 200;
  const padLeft = 40;
  const padRight = 12;
  const padTop = 14;
  const padBottom = 30;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;
  const barGap = 4;
  const barW = chartW / NUM_BINS - barGap;
  const toX = (i: number) => padLeft + i * (chartW / NUM_BINS) + barGap / 2;
  const toBarH = (count: number) => (count / maxCount) * chartH;

  const gridLines = [Math.round(maxCount * 0.5), maxCount].filter(
    (v, i, arr) => arr.indexOf(v) === i && v > 0,
  );

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">
          Trade Distribution by Time Remaining
        </h2>
        <div className="flex items-center gap-4 text-xs text-zinc-500">
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-green-500/70 inline-block" />
            Wins ({settled.filter((t) => t.pnl_cents! >= 0).length})
          </span>
          <span className="flex items-center gap-1.5">
            <span className="w-2.5 h-2.5 rounded-sm bg-red-500/70 inline-block" />
            Losses ({settled.filter((t) => t.pnl_cents! < 0).length})
          </span>
        </div>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ display: "block", aspectRatio: `${w}/${h}` }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const svgX = ((e.clientX - rect.left) / rect.width) * w;
          if (svgX < padLeft || svgX > w - padRight) {
            setHoverBin(null);
            return;
          }
          setHoverBin(
            Math.min(
              Math.max(Math.floor(((svgX - padLeft) / chartW) * NUM_BINS), 0),
              NUM_BINS - 1,
            ),
          );
        }}
        onMouseLeave={() => setHoverBin(null)}
      >
        <defs>
          <linearGradient id="timeWinGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#4ade80" stopOpacity="0.35" />
          </linearGradient>
          <linearGradient id="timeLossGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f87171" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#f87171" stopOpacity="0.35" />
          </linearGradient>
        </defs>

        {gridLines.map((count) => {
          const y = padTop + chartH - toBarH(count);
          return (
            <g key={count}>
              <line
                x1={padLeft}
                y1={y}
                x2={w - padRight}
                y2={y}
                stroke="#3f3f46"
                strokeWidth="0.5"
                strokeDasharray="3,3"
              />
              <text
                x={padLeft - 4}
                y={y + 4}
                textAnchor="end"
                fill="#78716c"
                fontSize="9"
                fontFamily="monospace"
              >
                {count}
              </text>
            </g>
          );
        })}

        {bins.map((bin, i) => {
          const x = toX(i);
          const winsH = toBarH(bin.wins);
          const lossH = toBarH(bin.losses);
          const baseY = padTop + chartH;
          const isHovered = hoverBin === i;
          return (
            <g key={i} opacity={isHovered ? 1 : 0.85}>
              {bin.losses > 0 && (
                <rect
                  x={x}
                  y={baseY - lossH}
                  width={barW}
                  height={lossH}
                  fill="url(#timeLossGrad)"
                  rx="1"
                  stroke={isHovered ? "#f87171" : "none"}
                  strokeWidth="0.5"
                />
              )}
              {bin.wins > 0 && (
                <rect
                  x={x}
                  y={baseY - lossH - winsH}
                  width={barW}
                  height={winsH}
                  fill="url(#timeWinGrad)"
                  rx="1"
                  stroke={isHovered ? "#4ade80" : "none"}
                  strokeWidth="0.5"
                />
              )}
            </g>
          );
        })}

        {/* X-axis: left=10 min, right=0 min */}
        {Array.from({ length: NUM_BINS }, (_, i) => 10 - i).map(
          (minsLabel, i) => {
            const x = toX(i) + barW / 2;
            return (
              <text
                key={i}
                x={x}
                y={h - 4}
                textAnchor="middle"
                fill="#78716c"
                fontSize="9"
                fontFamily="monospace"
              >
                {minsLabel}m
              </text>
            );
          },
        )}

        {hoverBin !== null &&
          (() => {
            const bin = bins[hoverBin];
            const x = toX(hoverBin) + barW / 2;
            const minsRemaining = 9 - hoverBin; // bin 0 = 10 min left, bin 9 = 0 min
            const total = bin.wins + bin.losses;
            const tooltipX = x < w / 2 ? x + 10 : x - 130;
            const tooltipY = padTop;
            const timeLabel = `~${minsRemaining + 1}m left`;
            return (
              <>
                <line
                  x1={x}
                  y1={padTop}
                  x2={x}
                  y2={padTop + chartH}
                  stroke="#d4a017"
                  strokeWidth="1"
                  strokeDasharray="3,3"
                  opacity="0.5"
                />
                <rect
                  x={tooltipX}
                  y={tooltipY}
                  width="120"
                  height={total > 0 ? 56 : 36}
                  rx="5"
                  fill="#1c1917"
                  stroke="#92400e"
                  strokeWidth="0.5"
                  opacity="0.95"
                />
                <text
                  x={tooltipX + 8}
                  y={tooltipY + 16}
                  fill="#fbbf24"
                  fontSize="11"
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  {timeLabel}
                </text>
                {total > 0 ? (
                  <>
                    <text
                      x={tooltipX + 8}
                      y={tooltipY + 32}
                      fill="#4ade80"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      ✓ {bin.wins} win{bin.wins !== 1 ? "s" : ""}
                    </text>
                    <text
                      x={tooltipX + 8}
                      y={tooltipY + 46}
                      fill="#f87171"
                      fontSize="10"
                      fontFamily="monospace"
                    >
                      ✗ {bin.losses} loss{bin.losses !== 1 ? "es" : ""}
                    </text>
                  </>
                ) : (
                  <text
                    x={tooltipX + 8}
                    y={tooltipY + 32}
                    fill="#78716c"
                    fontSize="10"
                    fontFamily="monospace"
                  >
                    No trades
                  </text>
                )}
              </>
            );
          })()}
      </svg>
    </div>
  );
}

function TimePnlHistogram({ trades }: { trades: Trade[] }) {
  const [hoverBin, setHoverBin] = useState<number | null>(null);

  const settled = trades.filter(
    (t) =>
      !t.dry_run &&
      t.pnl_cents !== null &&
      t.espn_clock_seconds !== null &&
      t.espn_clock_seconds <= 600 &&
      t.espn_clock_seconds >= 0 &&
      (t.status === "settled_win" || t.status === "settled_loss"),
  );

  if (settled.length === 0) {
    return (
      <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
        <h2 className="text-sm text-amber-600 font-medium mb-3">
          P&L by Time Remaining
        </h2>
        <p className="text-amber-900 text-sm">
          No settled trades with clock data yet.
        </p>
      </div>
    );
  }

  const NUM_BINS = 10;
  const bins: { pnl: number }[] = Array.from({ length: NUM_BINS }, () => ({
    pnl: 0,
  }));
  for (const t of settled) {
    const minsRemaining = Math.min(Math.floor(t.espn_clock_seconds! / 60), 9);
    const binIdx = 9 - minsRemaining;
    bins[binIdx].pnl += t.pnl_cents!;
  }

  const pnlValues = bins.map((b) => b.pnl);
  const maxPnl = Math.max(...pnlValues, 0);
  const minPnl = Math.min(...pnlValues, 0);
  const absMax = Math.max(Math.abs(maxPnl), Math.abs(minPnl), 1);
  const totalPnl = pnlValues.reduce((a, b) => a + b, 0);

  const w = 800;
  const h = 200;
  const padLeft = 52;
  const padRight = 12;
  const padTop = 14;
  const padBottom = 30;
  const chartW = w - padLeft - padRight;
  const chartH = h - padTop - padBottom;
  const barGap = 4;
  const barW = chartW / NUM_BINS - barGap;
  const toX = (i: number) => padLeft + i * (chartW / NUM_BINS) + barGap / 2;

  const posZone = maxPnl >= 0 ? (maxPnl / (maxPnl - minPnl || 1)) * chartH : 0;
  const baseY = padTop + posZone;

  const toBarY = (pnl: number) => {
    if (pnl >= 0) return baseY - (pnl / (absMax || 1)) * posZone;
    return baseY + (Math.abs(pnl) / (absMax || 1)) * (chartH - posZone);
  };
  const toBarH = (pnl: number) => Math.abs(toBarY(pnl) - baseY);

  const gridValues: number[] = [];
  for (const frac of [0.5, 1.0]) {
    const v = Math.round(absMax * frac);
    if (v > 0) gridValues.push(v, -v);
  }

  return (
    <div className="animate-fade-in gold-glow bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
      <div className="flex justify-between items-center mb-3">
        <h2 className="text-sm text-amber-600 font-medium">
          P&L by Time Remaining
        </h2>
        <span
          className={`text-xs font-mono font-bold px-2 py-0.5 rounded ${
            totalPnl >= 0
              ? "text-green-400 bg-green-900/30"
              : "text-red-400 bg-red-900/30"
          }`}
        >
          {totalPnl >= 0 ? "+" : ""}
          {cents(totalPnl)} total
        </span>
      </div>
      <svg
        viewBox={`0 0 ${w} ${h}`}
        className="w-full"
        style={{ display: "block", aspectRatio: `${w}/${h}` }}
        onMouseMove={(e) => {
          const rect = e.currentTarget.getBoundingClientRect();
          const svgX = ((e.clientX - rect.left) / rect.width) * w;
          if (svgX < padLeft || svgX > w - padRight) {
            setHoverBin(null);
            return;
          }
          setHoverBin(
            Math.min(
              Math.max(Math.floor(((svgX - padLeft) / chartW) * NUM_BINS), 0),
              NUM_BINS - 1,
            ),
          );
        }}
        onMouseLeave={() => setHoverBin(null)}
      >
        <defs>
          <linearGradient id="timePnlWinGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#4ade80" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#4ade80" stopOpacity="0.35" />
          </linearGradient>
          <linearGradient id="timePnlLossGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#f87171" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#f87171" stopOpacity="0.85" />
          </linearGradient>
        </defs>

        {gridValues.map((v) => {
          const y = toBarY(v);
          return (
            <g key={v}>
              <line
                x1={padLeft}
                y1={y}
                x2={w - padRight}
                y2={y}
                stroke="#3f3f46"
                strokeWidth="0.5"
                strokeDasharray="3,3"
              />
              <text
                x={padLeft - 4}
                y={y + 4}
                textAnchor="end"
                fill="#78716c"
                fontSize="9"
                fontFamily="monospace"
              >
                {v >= 0 ? "+" : ""}${(v / 100).toFixed(2)}
              </text>
            </g>
          );
        })}

        <line
          x1={padLeft}
          y1={baseY}
          x2={w - padRight}
          y2={baseY}
          stroke="#78716c"
          strokeWidth="1"
        />
        <text
          x={padLeft - 4}
          y={baseY + 4}
          textAnchor="end"
          fill="#78716c"
          fontSize="9"
          fontFamily="monospace"
        >
          $0
        </text>

        {bins.map((bin, i) => {
          const x = toX(i);
          const isPos = bin.pnl >= 0;
          const barH = toBarH(bin.pnl);
          const barY = isPos ? baseY - barH : baseY;
          const isHovered = hoverBin === i;
          if (barH < 0.5) return null;
          return (
            <rect
              key={i}
              x={x}
              y={barY}
              width={barW}
              height={barH}
              fill={isPos ? "url(#timePnlWinGrad)" : "url(#timePnlLossGrad)"}
              rx="1"
              opacity={isHovered ? 1 : 0.85}
              stroke={isHovered ? (isPos ? "#4ade80" : "#f87171") : "none"}
              strokeWidth="0.5"
            />
          );
        })}

        {Array.from({ length: NUM_BINS }, (_, i) => 10 - i).map(
          (minsLabel, i) => {
            const x = toX(i) + barW / 2;
            return (
              <text
                key={i}
                x={x}
                y={h - 4}
                textAnchor="middle"
                fill="#78716c"
                fontSize="9"
                fontFamily="monospace"
              >
                {minsLabel}m
              </text>
            );
          },
        )}

        {hoverBin !== null &&
          (() => {
            const bin = bins[hoverBin];
            const x = toX(hoverBin) + barW / 2;
            const minsRemaining = 9 - hoverBin;
            const tooltipX = x < w / 2 ? x + 10 : x - 130;
            const tooltipY = padTop;
            const pnlLabel = `${bin.pnl >= 0 ? "+" : ""}${cents(bin.pnl)}`;
            const pnlColor = bin.pnl >= 0 ? "#4ade80" : "#f87171";
            return (
              <>
                <line
                  x1={x}
                  y1={padTop}
                  x2={x}
                  y2={padTop + chartH}
                  stroke="#d4a017"
                  strokeWidth="1"
                  strokeDasharray="3,3"
                  opacity="0.5"
                />
                <rect
                  x={tooltipX}
                  y={tooltipY}
                  width="120"
                  height="46"
                  rx="5"
                  fill="#1c1917"
                  stroke="#92400e"
                  strokeWidth="0.5"
                  opacity="0.95"
                />
                <text
                  x={tooltipX + 8}
                  y={tooltipY + 16}
                  fill="#fbbf24"
                  fontSize="11"
                  fontWeight="bold"
                  fontFamily="monospace"
                >
                  ~{minsRemaining + 1}m left
                </text>
                <text
                  x={tooltipX + 8}
                  y={tooltipY + 32}
                  fill={pnlColor}
                  fontSize="10"
                  fontFamily="monospace"
                >
                  {bin.pnl === 0 ? "No P&L" : pnlLabel}
                </text>
              </>
            );
          })()}
      </svg>
    </div>
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

export default function Dashboard() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [stats, setStats] = useState<Stats | null>(null);
  const [trades, setTrades] = useState<Trade[]>([]);
  const [allTrades, setAllTrades] = useState<Trade[]>([]);
  const [opportunities, setOpportunities] = useState<Opportunity[]>([]);
  const [balanceHistory, _setBalanceHistory] = useState<BalanceSnapshot[]>([]); // unused, kept for type compat
  const [stretchStats, setStretchStats] = useState<StretchStats | null>(null);
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
    | "overview"
    | "charts"
    | "sports"
    | "live_games"
    | "strategy"
    | "config"
    | "trades"
  >("overview");
  const [isTradingTransition, setIsTradingTransition] = useState<
    "pausing" | "resuming" | null
  >(null);
  const games = useLiveGames(authed);

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
        if (statsRes.ok) setStats(await statsRes.json());
        if (tradesRes.ok) setTrades((await tradesRes.json()).trades ?? []);
        if (oppsRes.ok)
          setOpportunities((await oppsRes.json()).opportunities ?? []);
        setError(null);
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
        const [tradesRes, stretchRes, configRes, ssRes] = await Promise.all([
          fetch(`${API}/api/histogram-trades?limit=10000`),
          fetch(`${API}/api/stretch-stats`),
          fetch(`${API}/api/config`),
          fetch(`${API}/api/sport-stats`),
        ]);
        if (tradesRes.ok) setAllTrades((await tradesRes.json()).trades ?? []);
        if (stretchRes.ok) setStretchStats(await stretchRes.json());
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
                className="inline-block mt-1 text-sm text-blue-400 hover:text-blue-200 underline"
              >
                Strategy Backtest →
              </a>
            </div>
            {config && (
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
            )}
          </div>

          {/* Main Tabs */}
          <div className="flex flex-wrap gap-2 animate-fade-in">
            {[
              { id: "overview", label: "Overview" },
              { id: "charts", label: "Charts" },
              { id: "sports", label: "Sports" },
              { id: "live_games", label: "Live Games" },
              { id: "strategy", label: "Strategy" },
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
                    <div className="grid grid-cols-2 md:grid-cols-5 gap-3 mb-5">
                      <div className="bg-black/30 rounded-lg p-3 border border-zinc-800">
                        <div className="text-zinc-500 text-xs">
                          Min YES Price
                        </div>
                        <div className="text-amber-200 text-lg font-bold font-mono">
                          {config.trading.min_yes_price}¢
                        </div>
                      </div>
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
                        <div className="text-zinc-500 text-xs">Min Volume</div>
                        <div className="text-amber-200 text-lg font-bold font-mono">
                          {config.trading.min_volume}
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
                            <th className="text-center py-2 pr-4">Min Lead</th>
                            <th className="text-center py-2 pr-4">
                              Stretch Lead
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
                              <td className="py-2 pr-4 text-center text-amber-300 font-mono">
                                {s.min_score_lead}
                              </td>
                              <td className="py-2 pr-4 text-center text-zinc-500 font-mono">
                                {s.stretch_score_lead}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  </div>
                )}
              </div>
            </div>
          </>
        )}

        {mainTab === "overview" && (
          <>
            {/* Stats Grid */}
            <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4 mb-8">
              <StatCard
                label="Balance"
                value={cents(stats.balance_cents)}
                delay={0}
              />
              <StatCard
                label="On the Line"
                value={cents(stats.open_cost_cents || 0)}
                sub={`${stats.open_positions || 0} open positions`}
                delay={50}
              />
              <StatCard
                label="Win Rate"
                value={`${stats.win_rate}%`}
                sub={`${stats.wins}W / ${stats.losses}L`}
                delay={100}
              />
              <StatCard
                label="Realized P&L"
                value={cents(stats.realized_pnl_cents)}
                delay={150}
              />
              <StatCard
                label="Trades"
                value={String(stats.live_trades)}
                sub={`${cents(stats.total_cost_cents)} deployed`}
                delay={200}
              />
              <StatCard
                label="Fees"
                value={cents(stats.total_fees_cents)}
                sub="Total fees"
                delay={250}
              />
            </div>

            {/* P&L Chart */}
            <PnlChart
              trades={allTrades.some((t) => t.placed_at) ? allTrades : trades}
              balanceCents={stats.balance_cents}
              portfolioCents={stats.portfolio_value_cents}
            />
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

        {mainTab === "strategy" && (
          <>
            {/* What If? Strategy Comparison */}
            {stretchStats &&
              stretchStats.strategies &&
              Object.keys(stretchStats.strategies).length > 0 && (
                <div className="animate-fade-in bg-zinc-900/80 border border-amber-900/30 rounded-xl p-5 mb-8 backdrop-blur-sm">
                  <div className="flex justify-between items-center mb-4">
                    <h2 className="text-sm text-amber-600 font-medium">
                      What If? Strategy Comparison
                    </h2>
                    <span className="text-xs text-zinc-500">
                      Shadow-tracking {stretchStats.total} markets across{" "}
                      {Object.keys(stretchStats.strategies).length} strategies
                    </span>
                  </div>
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="border-b border-zinc-700 text-zinc-500 text-xs">
                          <th className="text-left py-2 pr-4">Strategy</th>
                          <th className="text-center py-2 px-3">Tracked</th>
                          <th className="text-center py-2 px-3">W</th>
                          <th className="text-center py-2 px-3">L</th>
                          <th className="text-center py-2 px-3">Open</th>
                          <th className="text-center py-2 px-3">Win %</th>
                          <th className="text-right py-2 pl-3">Hyp P&L</th>
                        </tr>
                      </thead>
                      <tbody>
                        {Object.entries(stretchStats.strategies)
                          .sort(
                            ([, a], [, b]) =>
                              b.hypothetical_pnl_cents -
                              a.hypothetical_pnl_cents,
                          )
                          .map(([key, s]) => (
                            <tr
                              key={key}
                              className="border-b border-zinc-800/50 hover:bg-zinc-800/30"
                            >
                              <td className="py-2 pr-4 text-amber-200 font-medium">
                                {s.label}
                              </td>
                              <td className="py-2 px-3 text-center text-zinc-300 font-mono">
                                {s.total}
                              </td>
                              <td className="py-2 px-3 text-center text-green-400 font-mono">
                                {s.wins}
                              </td>
                              <td className="py-2 px-3 text-center text-red-400 font-mono">
                                {s.losses}
                              </td>
                              <td className="py-2 px-3 text-center text-zinc-500 font-mono">
                                {s.open}
                              </td>
                              <td className="py-2 px-3 text-center text-zinc-300 font-mono">
                                {s.win_rate > 0 ? `${s.win_rate}%` : "-"}
                              </td>
                              <td
                                className={`py-2 pl-3 text-right font-mono font-bold ${s.hypothetical_pnl_cents >= 0 ? "text-green-400" : "text-red-400"}`}
                              >
                                {s.hypothetical_pnl_cents >= 0 ? "+" : ""}
                                {cents(s.hypothetical_pnl_cents)}
                              </td>
                            </tr>
                          ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}
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
