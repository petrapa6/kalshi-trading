"use client";

import { useEffect, useState } from "react";
import { checkAuth } from "../actions";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

type League = "PL" | "PD" | "BL1";

interface FormState {
  league: League;
  date_from: string;
  date_to: string;
  min_minute: number;
  min_lead: number;
  min_yes_price: number;
  initial_balance_cents: number;
  bet_percent: number;
}

interface BacktestSummary {
  matches_scanned: number;
  matches_bet_on: number;
  matches_with_price_data: number;
  wins: number;
  losses: number;
  win_rate: number;
  initial_balance_cents: number;
  final_balance_cents: number;
  pnl_cents: number;
  pnl_pct: number;
}

interface BacktestTrade {
  match_id: string;
  kickoff_at: string;
  league: League;
  home_team: string;
  away_team: string;
  final_home: number;
  final_away: number;
  fired_at_minute: number;
  score_at_fire_home: number;
  score_at_fire_away: number;
  leading_side: "home" | "away";
  result: "win" | "loss";
  observed_yes_ask_cents: number | null;
  count: number | null;
  cost_cents: number | null;
  pnl_cents: number | null;
  bankroll_after_cents: number;
}

interface BacktestCurvePoint {
  t: string;
  balance_cents: number;
}

interface BacktestResponse {
  summary: BacktestSummary;
  trades: BacktestTrade[];
  bankroll_curve: BacktestCurvePoint[];
  partial: boolean;
  missing_count: number;
}

function defaultForm(): FormState {
  const today = new Date();
  const monthAgo = new Date(today);
  monthAgo.setMonth(monthAgo.getMonth() - 1);
  const iso = (d: Date) => d.toISOString().slice(0, 10);
  return {
    league: "PL",
    date_from: iso(monthAgo),
    date_to: iso(today),
    min_minute: 75,
    min_lead: 2,
    min_yes_price: 0,
    initial_balance_cents: 100000,
    bet_percent: 0.02,
  };
}

function fmtUsd(cents: number): string {
  const dollars = cents / 100;
  return dollars.toLocaleString("en-US", {
    style: "currency",
    currency: "USD",
  });
}

function pnlColor(cents: number): string {
  return cents > 0
    ? "text-green-400"
    : cents < 0
      ? "text-red-400"
      : "text-white";
}

function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: string;
  color?: string;
}) {
  return (
    <div className="bg-gray-900 rounded p-3">
      <div className="text-xs uppercase tracking-wider text-gray-400">
        {label}
      </div>
      <div className={`text-lg font-semibold ${color ?? "text-white"}`}>
        {value}
      </div>
    </div>
  );
}

function BankrollChart({ points }: { points: BacktestCurvePoint[] }) {
  const data = points.map((p) => ({
    t: new Date(p.t).getTime(),
    balance: p.balance_cents / 100,
  }));
  return (
    <div className="h-64 bg-gray-900 rounded p-3">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <CartesianGrid stroke="#333" />
          <XAxis
            dataKey="t"
            type="number"
            domain={["dataMin", "dataMax"]}
            tickFormatter={(t) => new Date(t).toISOString().slice(0, 10)}
            stroke="#888"
          />
          <YAxis stroke="#888" tickFormatter={(v) => `$${v.toFixed(0)}`} />
          <Tooltip
            labelFormatter={(t) =>
              new Date(Number(t)).toISOString().slice(0, 16)
            }
            formatter={(v) => `$${Number(v).toFixed(2)}`}
            contentStyle={{ background: "#111", border: "1px solid #333" }}
          />
          <Line
            type="monotone"
            dataKey="balance"
            stroke="#3b82f6"
            dot={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function TradeRow({ trade }: { trade: BacktestTrade }) {
  const won = trade.result === "win";
  const dateStr = new Date(trade.kickoff_at).toISOString().slice(0, 10);
  const emoji = won ? "✅" : "❌";
  const secondLine =
    trade.observed_yes_ask_cents === null
      ? `Fired min ${trade.fired_at_minute} @ ${trade.score_at_fire_home}-${trade.score_at_fire_away} · (no price) · winrate only`
      : `Fired min ${trade.fired_at_minute} @ ${trade.score_at_fire_home}-${trade.score_at_fire_away} · ` +
        `bet $${(trade.cost_cents! / 100).toFixed(2)} · ` +
        `P&L ${trade.pnl_cents! >= 0 ? "+" : ""}$${(trade.pnl_cents! / 100).toFixed(2)} · ` +
        `bankroll $${(trade.bankroll_after_cents / 100).toFixed(2)}`;
  return (
    <div className={`p-2 rounded ${won ? "bg-green-900/30" : "bg-red-900/30"}`}>
      <div className="text-sm">
        {dateStr} · {trade.home_team} {trade.final_home} – {trade.final_away}{" "}
        {trade.away_team} {emoji}
      </div>
      <div className="text-xs text-gray-400">{secondLine}</div>
    </div>
  );
}

export default function BacktestPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [form, setForm] = useState<FormState>(defaultForm);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<BacktestResponse | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    checkAuth().then((ok) => {
      if (!ok) window.location.href = "/";
      else setAuthed(true);
    });
  }, []);

  const update = <K extends keyof FormState>(key: K, value: FormState[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
  };

  async function handleSubmit() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/backtest/soccer", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(form),
      });
      if (res.status === 401) {
        window.location.href = "/";
        return;
      }
      if (!res.ok) {
        const body = await res.text();
        setError(`${res.status}: ${body}`);
        return;
      }
      const data = (await res.json()) as BacktestResponse;
      setResult(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Network error");
    } finally {
      setLoading(false);
    }
  }

  if (!authed) return <div className="min-h-screen bg-black" />;

  return (
    <div className="min-h-screen bg-black text-white p-6">
      <header className="flex items-center justify-between mb-6">
        <a href="/" className="text-sm text-gray-400 hover:text-white">
          ← Dashboard
        </a>
        <h1 className="text-2xl font-semibold">Strategy Backtest</h1>
        <span className="text-sm text-gray-400" />
      </header>
      <div className="grid grid-cols-1 md:grid-cols-[300px_1fr] gap-6">
        <aside className="space-y-4 bg-gray-900 p-4 rounded">
          <div>
            <label className="block text-sm text-gray-300 mb-1">League</label>
            <select
              value={form.league}
              onChange={(e) => update("league", e.target.value as League)}
              className="w-full bg-black border border-gray-700 rounded px-2 py-1"
            >
              <option value="PL">EPL</option>
              <option value="PD">La Liga</option>
              <option value="BL1">Bundesliga</option>
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Date from
            </label>
            <input
              type="date"
              value={form.date_from}
              onChange={(e) => update("date_from", e.target.value)}
              className="w-full bg-black border border-gray-700 rounded px-2 py-1"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Date to</label>
            <input
              type="date"
              value={form.date_to}
              onChange={(e) => update("date_to", e.target.value)}
              className="w-full bg-black border border-gray-700 rounded px-2 py-1"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Min minute: {form.min_minute}
            </label>
            <input
              type="range"
              min={1}
              max={90}
              value={form.min_minute}
              onChange={(e) => update("min_minute", Number(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Min lead: {form.min_lead}
            </label>
            <input
              type="range"
              min={1}
              max={5}
              value={form.min_lead}
              onChange={(e) => update("min_lead", Number(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Min YES price:{" "}
              {form.min_yes_price === 0
                ? "0 = disabled"
                : `${form.min_yes_price}¢`}
            </label>
            <input
              type="range"
              min={0}
              max={99}
              value={form.min_yes_price}
              onChange={(e) => update("min_yes_price", Number(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Initial balance ($)
            </label>
            <input
              type="number"
              min={10}
              value={form.initial_balance_cents / 100}
              onChange={(e) =>
                update(
                  "initial_balance_cents",
                  Math.round(Number(e.target.value) * 100),
                )
              }
              className="w-full bg-black border border-gray-700 rounded px-2 py-1"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Bet %: {(form.bet_percent * 100).toFixed(1)}%
            </label>
            <input
              type="range"
              min={0.005}
              max={0.1}
              step={0.005}
              value={form.bet_percent}
              onChange={(e) => update("bet_percent", Number(e.target.value))}
              className="w-full"
            />
          </div>
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="w-full bg-blue-600 hover:bg-blue-500 disabled:bg-gray-700 px-4 py-2 rounded"
          >
            {loading ? "Running backtest…" : "Run backtest"}
          </button>
          <p className="text-xs text-gray-500">
            P&amp;L reflects only matches with observed Kalshi prices. All bets
            are counted in win rate.
          </p>
        </aside>
        <main className="space-y-6">
          {error && (
            <div className="bg-red-900/40 border border-red-700 text-red-200 rounded p-3 text-sm">
              {error}
            </div>
          )}
          {result?.partial && (
            <div className="bg-yellow-900/40 border border-yellow-700 text-yellow-200 rounded p-3 text-sm">
              {result.missing_count} matches not yet cached — retry in ~60 s.
            </div>
          )}
          {loading && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <div
                  key={i}
                  className="h-16 bg-gray-900 rounded animate-pulse"
                />
              ))}
            </div>
          )}
          {result && !loading && (
            <>
              <section className="grid grid-cols-2 md:grid-cols-4 gap-3">
                <SummaryCard
                  label="Scanned"
                  value={String(result.summary.matches_scanned)}
                />
                <SummaryCard
                  label="Bet on"
                  value={String(result.summary.matches_bet_on)}
                />
                <SummaryCard
                  label="Win rate"
                  value={`${(result.summary.win_rate * 100).toFixed(1)}%`}
                />
                <SummaryCard label="Wins" value={String(result.summary.wins)} />
                <SummaryCard
                  label="Losses"
                  value={String(result.summary.losses)}
                />
                <SummaryCard
                  label="P&L %"
                  value={`${(result.summary.pnl_pct * 100).toFixed(2)}%`}
                  color={pnlColor(result.summary.pnl_cents)}
                />
                <SummaryCard
                  label="P&L $"
                  value={fmtUsd(result.summary.pnl_cents)}
                  color={pnlColor(result.summary.pnl_cents)}
                />
                <SummaryCard
                  label="w/ prices"
                  value={`${result.summary.matches_with_price_data} / ${result.summary.matches_bet_on}`}
                />
              </section>
              {result.summary.matches_with_price_data > 0 ? (
                <BankrollChart points={result.bankroll_curve} />
              ) : (
                <div className="bg-gray-900 rounded p-4 text-sm text-gray-400">
                  No Kalshi price data observed in this range; bankroll curve
                  unavailable.
                </div>
              )}
              {result.trades.length > 0 ? (
                <section className="space-y-2">
                  {result.trades.map((t) => (
                    <TradeRow key={t.match_id} trade={t} />
                  ))}
                </section>
              ) : (
                <div className="text-sm text-gray-400">
                  No fixtures met the trigger in this range.
                </div>
              )}
            </>
          )}
        </main>
      </div>
    </div>
  );
}
