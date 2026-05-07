"use client";

import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { checkAuth } from "../actions";

interface SummaryEntry {
  name: string;
  total_trades: number;
  wins: number;
  losses: number;
  pnl_cents: number;
}

interface AnalyticsStats {
  total_trades: number;
  wins: number;
  losses: number;
  open_trades: number;
  win_rate: number;
  realized_pnl_cents: number;
}

interface AnalyticsTrade {
  id: number;
  placed_at: string | null;
  settled_at: string | null;
  ticker: string;
  yes_price: number;
  count: number;
  cost_cents: number;
  pnl_cents: number | null;
  status: string;
}

interface PnlPoint {
  x: string | null;
  y: number;
  ticker: string;
  trade_pnl: number;
}

interface AnalyticsResponse {
  stats: AnalyticsStats;
  trades: AnalyticsTrade[];
  pnl_curve: PnlPoint[];
}

function fmtCents(c: number): string {
  const sign = c >= 0 ? "+" : "−";
  return `${sign}$${(Math.abs(c) / 100).toFixed(2)}`;
}

function StatCard({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "positive" | "negative" | "neutral";
}) {
  const valueClass =
    tone === "positive"
      ? "text-green-400"
      : tone === "negative"
        ? "text-red-400"
        : "text-white";
  return (
    <div className="bg-gray-900 rounded p-3">
      <div className="text-xs uppercase tracking-wider text-gray-400">
        {label}
      </div>
      <div className={`text-lg font-semibold ${valueClass}`}>{value}</div>
    </div>
  );
}

function SidebarRow({
  entry,
  selected,
  onClick,
}: {
  entry: SummaryEntry;
  selected: boolean;
  onClick: () => void;
}) {
  const settled = entry.wins + entry.losses;
  const winRate = settled > 0 ? Math.round((entry.wins / settled) * 100) : null;
  const pnlText =
    entry.total_trades === 0
      ? "0 · 0W/0L · —"
      : `${fmtCents(entry.pnl_cents)} · ${entry.wins}W/${entry.losses}L · ${
          winRate !== null ? `${winRate}%` : "—"
        }`;
  const pnlClass =
    entry.total_trades === 0
      ? "text-gray-400"
      : entry.pnl_cents >= 0
        ? "text-green-400"
        : "text-red-400";
  const rowClass = selected
    ? "bg-amber-900/40 border-l-2 border-amber-500 cursor-pointer"
    : "bg-gray-900 hover:bg-gray-800 cursor-pointer";
  return (
    <button
      type="button"
      onClick={onClick}
      className={`${rowClass} w-full text-left rounded p-3 transition-colors`}
    >
      <div className="text-sm font-semibold text-white">{entry.name}</div>
      <div className={`text-xs mt-1 ${pnlClass}`}>{pnlText}</div>
    </button>
  );
}

export default function AnalyticsPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [summary, setSummary] = useState<SummaryEntry[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [detail, setDetail] = useState<AnalyticsResponse | null>(null);
  const [lastUpdated, setLastUpdated] = useState<Date | null>(null);

  useEffect(() => {
    checkAuth().then((ok) => {
      if (!ok) window.location.href = "/";
      else setAuthed(true);
    });
  }, []);

  // Read ?strategy=<name> on mount via window.location.search inside
  // useEffect — avoids the Next.js 16 Suspense boundary build error
  // associated with the dynamic search-params API.
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const initial = params.get("strategy");
    if (initial) setSelected(initial);
  }, []);

  const selectStrategy = (name: string) => {
    setSelected(name);
    const url = new URL(window.location.href);
    url.searchParams.set("strategy", name);
    window.history.pushState({}, "", url.toString());
  };

  useEffect(() => {
    if (!authed) return;
    let cancelled = false;

    const fetchAll = async () => {
      try {
        const [summaryRes, detailRes] = await Promise.all([
          fetch("/api/strategies-summary"),
          selected
            ? fetch(
                `/api/strategy-analytics?strategy=${encodeURIComponent(selected)}`,
              )
            : Promise.resolve(null),
        ]);
        if (cancelled) return;
        if (summaryRes.ok) {
          const data = (await summaryRes.json()) as {
            strategies: SummaryEntry[];
          };
          setSummary(data.strategies ?? []);
          if (!selected && data.strategies && data.strategies.length > 0) {
            const params = new URLSearchParams(window.location.search);
            if (!params.get("strategy")) {
              setSelected(data.strategies[0].name);
            }
          }
        }
        if (detailRes && detailRes.ok) {
          setDetail((await detailRes.json()) as AnalyticsResponse);
        }
        setLastUpdated(new Date());
      } catch {
        // non-critical (project pattern: empty catch on background polling)
      }
    };

    fetchAll();
    const interval = setInterval(fetchAll, 5 * 60 * 1000); // DASH-04 / D-12
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [authed, selected]);

  if (!authed) return <div className="min-h-screen bg-black" />;

  const stats = detail?.stats;
  const winRateText = stats ? `${stats.win_rate.toFixed(1)}%` : "0.0%";

  return (
    <div className="min-h-screen bg-black text-white p-6">
      <header className="flex items-center justify-between mb-6">
        <a href="/" className="text-sm text-gray-400 hover:text-white">
          ← Dashboard
        </a>
        <h1 className="text-2xl font-semibold">Strategy Analytics</h1>
        <span className="text-sm text-gray-400">
          {lastUpdated ? `Updated ${lastUpdated.toLocaleTimeString()}` : ""}
        </span>
      </header>

      <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-6">
        <aside className="space-y-2 bg-gray-900 p-4 rounded">
          <div className="text-xs uppercase tracking-wider text-gray-400 mb-2">
            Strategies
          </div>
          {summary.length === 0 ? (
            <div className="text-sm text-gray-500">No strategies loaded.</div>
          ) : (
            summary.map((s) => (
              <SidebarRow
                key={s.name}
                entry={s}
                selected={s.name === selected}
                onClick={() => selectStrategy(s.name)}
              />
            ))
          )}
        </aside>

        <main className="space-y-6">
          {selected ? (
            <>
              <h2 className="text-xl font-semibold text-amber-300">
                {selected}
              </h2>

              <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
                <StatCard
                  label="Total Trades"
                  value={String(stats?.total_trades ?? 0)}
                />
                <StatCard
                  label="Wins"
                  value={String(stats?.wins ?? 0)}
                  tone="positive"
                />
                <StatCard
                  label="Losses"
                  value={String(stats?.losses ?? 0)}
                  tone="negative"
                />
                <StatCard label="Win Rate" value={winRateText} />
                <StatCard
                  label="Realized P&L"
                  value={stats ? fmtCents(stats.realized_pnl_cents) : "$0.00"}
                  tone={
                    (stats?.realized_pnl_cents ?? 0) >= 0
                      ? "positive"
                      : "negative"
                  }
                />
              </div>

              <div className="bg-gray-900 rounded p-4">
                <div className="text-xs uppercase tracking-wider text-gray-400 mb-2">
                  Cumulative P&L
                </div>
                <ResponsiveContainer width="100%" height={280}>
                  <LineChart
                    data={detail?.pnl_curve ?? []}
                    margin={{ top: 5, right: 20, left: 10, bottom: 5 }}
                  >
                    <CartesianGrid stroke="#27272a" strokeDasharray="3 3" />
                    <XAxis
                      dataKey="x"
                      tickFormatter={(v: string | null) =>
                        v ? new Date(v).toLocaleDateString() : ""
                      }
                      tick={{ fill: "#a1a1aa", fontSize: 11 }}
                    />
                    <YAxis
                      tickFormatter={(v: number) => `$${(v / 100).toFixed(2)}`}
                      tick={{ fill: "#a1a1aa", fontSize: 11 }}
                    />
                    <Tooltip
                      content={({ active, payload }) => {
                        if (!active || !payload || payload.length === 0)
                          return null;
                        const d = payload[0].payload as PnlPoint;
                        return (
                          <div className="bg-zinc-900 border border-zinc-700 p-2 text-xs">
                            <div>
                              {d.x ? new Date(d.x).toLocaleString() : ""}
                            </div>
                            <div>{d.ticker}</div>
                            <div>Trade: {fmtCents(d.trade_pnl)}</div>
                            <div>Running: {fmtCents(d.y)}</div>
                          </div>
                        );
                      }}
                    />
                    <Line
                      type="monotone"
                      dataKey="y"
                      stroke="#d97706"
                      dot={false}
                      strokeWidth={2}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>

              <div className="bg-gray-900 rounded p-4">
                <div className="text-xs uppercase tracking-wider text-gray-400 mb-2">
                  Trades
                </div>
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className="text-xs uppercase tracking-wider text-gray-400 text-left">
                        <th className="p-2">Date</th>
                        <th className="p-2">Ticker</th>
                        <th className="p-2 text-right">Price</th>
                        <th className="p-2 text-right">Contracts</th>
                        <th className="p-2 text-right">P&L</th>
                        <th className="p-2">Status</th>
                      </tr>
                    </thead>
                    <tbody>
                      {(detail?.trades ?? []).length === 0 ? (
                        <tr>
                          <td
                            colSpan={6}
                            className="p-4 text-gray-500 text-center"
                          >
                            &nbsp;
                          </td>
                        </tr>
                      ) : (
                        (detail?.trades ?? []).map((t) => {
                          const dateText = t.placed_at
                            ? new Date(t.placed_at).toLocaleDateString()
                            : "—";
                          const pnlClass =
                            t.pnl_cents == null
                              ? "text-gray-400"
                              : t.pnl_cents >= 0
                                ? "text-green-400"
                                : "text-red-400";
                          const pnlText =
                            t.pnl_cents == null ? "—" : fmtCents(t.pnl_cents);
                          return (
                            <tr
                              key={t.id}
                              className="border-t border-gray-800 hover:bg-gray-800/50"
                            >
                              <td className="p-2 text-gray-300">{dateText}</td>
                              <td className="p-2 font-mono text-xs text-gray-300">
                                {t.ticker}
                              </td>
                              <td className="p-2 text-right text-gray-300">
                                {t.yes_price}c
                              </td>
                              <td className="p-2 text-right text-gray-300">
                                {t.count}
                              </td>
                              <td className={`p-2 text-right ${pnlClass}`}>
                                {pnlText}
                              </td>
                              <td className="p-2 text-xs text-gray-400">
                                {t.status.replace(/_/g, " ")}
                              </td>
                            </tr>
                          );
                        })
                      )}
                    </tbody>
                  </table>
                </div>
              </div>
            </>
          ) : (
            <div className="text-gray-500">
              Select a strategy to view analytics.
            </div>
          )}
        </main>
      </div>
    </div>
  );
}
