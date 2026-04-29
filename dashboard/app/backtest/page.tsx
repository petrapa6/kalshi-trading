"use client";

import { useEffect, useMemo, useState } from "react";
import { checkAuth } from "../actions";
import { SEASONS, type SeasonOption } from "./seasons";
import { runBacktest, type BacktestTrade } from "./backtest";

function SummaryCard({ label, value }: { label: string; value: string }) {
  return (
    <div className="bg-gray-900 rounded p-3">
      <div className="text-xs uppercase tracking-wider text-gray-400">
        {label}
      </div>
      <div className="text-lg font-semibold text-white">{value}</div>
    </div>
  );
}

function TradeRow({ trade }: { trade: BacktestTrade }) {
  const won = trade.result === "win";
  const emoji = won ? "✅" : "❌";
  return (
    <div className={`p-2 rounded ${won ? "bg-green-900/30" : "bg-red-900/30"}`}>
      <div className="text-sm">
        {trade.date} · {trade.home_team} {trade.final_home} – {trade.final_away}{" "}
        {trade.away_team} {emoji}
      </div>
      <div className="text-xs text-gray-400">
        Fired min {trade.fired_at_minute} @ {trade.score_at_fire_home}-
        {trade.score_at_fire_away} · {trade.leading_side} leads
      </div>
    </div>
  );
}

export default function BacktestPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [selectedKey, setSelectedKey] = useState<string>(SEASONS[0]?.key ?? "");
  const [minMinute, setMinMinute] = useState(75);
  const [minLead, setMinLead] = useState(2);

  useEffect(() => {
    checkAuth().then((ok) => {
      if (!ok) window.location.href = "/";
      else setAuthed(true);
    });
  }, []);

  const selected: SeasonOption | undefined = useMemo(
    () => SEASONS.find((s) => s.key === selectedKey),
    [selectedKey],
  );

  const result = useMemo(
    () =>
      selected
        ? runBacktest(selected.data, {
            min_minute: minMinute,
            min_lead: minLead,
          })
        : null,
    [selected, minMinute, minLead],
  );

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
            <label className="block text-sm text-gray-300 mb-1">Season</label>
            {SEASONS.length === 0 ? (
              <select
                disabled
                className="w-full bg-black border border-gray-700 rounded px-2 py-1"
              >
                <option>No seasons in resources/</option>
              </select>
            ) : (
              <select
                value={selectedKey}
                onChange={(e) => setSelectedKey(e.target.value)}
                className="w-full bg-black border border-gray-700 rounded px-2 py-1"
              >
                {SEASONS.map((s) => (
                  <option key={s.key} value={s.key}>
                    {s.parsed.label}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Min minute: {minMinute}
            </label>
            <input
              type="range"
              min={1}
              max={90}
              value={minMinute}
              onChange={(e) => setMinMinute(Number(e.target.value))}
              className="w-full"
            />
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">
              Min lead: {minLead}
            </label>
            <input
              type="range"
              min={1}
              max={5}
              value={minLead}
              onChange={(e) => setMinLead(Number(e.target.value))}
              className="w-full"
            />
          </div>
          <p className="text-xs text-gray-500">
            Trades fire on the first goal where minute ≥ min_minute and |lead| ≥
            min_lead. Stoppage time is ignored.
          </p>
        </aside>
        <main className="space-y-6">
          {SEASONS.length === 0 ? (
            <div className="bg-gray-900 rounded p-6 text-sm text-gray-400">
              <p className="font-semibold text-white mb-2">
                No season data available
              </p>
              <p>
                Run the{" "}
                <code className="text-blue-400">fetch-football-season</code>{" "}
                skill to populate{" "}
                <code className="text-blue-400">resources/</code> with season
                JSON files.
              </p>
            </div>
          ) : (
            result && (
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
                    label="Wins"
                    value={String(result.summary.wins)}
                  />
                  <SummaryCard
                    label="Losses"
                    value={String(result.summary.losses)}
                  />
                  <SummaryCard
                    label="Win rate"
                    value={`${(result.summary.win_rate * 100).toFixed(1)}%`}
                  />
                </section>
                {result.trades.length > 0 ? (
                  <section className="space-y-2">
                    {result.trades.map((t) => (
                      <TradeRow key={t.match_id} trade={t} />
                    ))}
                  </section>
                ) : (
                  <div className="text-sm text-gray-400">
                    No fixtures met the trigger.
                  </div>
                )}
              </>
            )
          )}
        </main>
      </div>
    </div>
  );
}
