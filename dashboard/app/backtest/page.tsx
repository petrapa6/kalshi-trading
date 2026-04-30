"use client";

import { useEffect, useMemo, useState } from "react";
import { checkAuth } from "../actions";
import { LEAGUES, type LeagueOption } from "./seasons";
import { runBacktest, type BacktestTrade, type Trigger } from "./backtest";

interface ApiTrigger {
  sport?: string;
  min_minute?: number;
  min_lead?: number;
  min_yes_price?: number;
  max_yes_price?: number;
}

interface ApiStrategy {
  name: string;
  description?: string;
  triggers: ApiTrigger[];
}

const CUSTOM_KEY = "__custom__";
const CUSTOM_LABEL = "— Custom —";

// Sport family options. Currently only football is in active use; baseball /
// tennis / etc. drop in by adding rows here. The dropdown renders even with
// one option so the UX is structurally ready for more families.
const SPORTS: Array<{ value: string; label: string }> = [
  { value: "football", label: "Football" },
];

function defaultTriggerForSport(sport: string): Trigger {
  return { sport, min_minute: 75, min_lead: 2 };
}

function strategyMatchesSport(strat: ApiStrategy, sport: string): boolean {
  // ALL triggers must match the page-level sport. Triggers with no sport set
  // are treated as wildcards and pass.
  return strat.triggers.every(
    (t) => t.sport === undefined || t.sport === sport,
  );
}

function formatEuro(value: number): string {
  return value.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

function SummaryCard({
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

function TradeRow({ trade }: { trade: BacktestTrade }) {
  const isZero = trade.contracts === 0;
  const won = trade.result === "win";
  const bgClass = isZero
    ? "bg-[#F28C28]/30"
    : won
      ? "bg-green-900/30"
      : "bg-red-900/30";
  // Zero-contract rows render no icon — they were not real bets, so the
  // win/loss verdict from `result` is hypothetical, not earned.
  const emoji = isZero ? "" : won ? "✅" : "❌";
  const cost_cents = trade.contracts * trade.contract_price_cents;
  const pnlSign = trade.pnl_cents >= 0 ? "+" : "−";
  // Zero-contract rows: pnl text inherits the surrounding gray rather
  // than green-on-+0.00, which would visually overclaim a profit.
  const pnlClass = isZero
    ? "text-gray-300"
    : trade.pnl_cents >= 0
      ? "text-green-400"
      : "text-red-400";
  return (
    <div className={`p-2 rounded ${bgClass}`}>
      <div className="text-sm">
        {trade.date} · {trade.home_team} {trade.final_home} – {trade.final_away}{" "}
        {trade.away_team}
        {emoji ? ` ${emoji}` : ""}
      </div>
      <div className="text-xs text-gray-400">
        Fired min {trade.fired_at_minute} @ {trade.score_at_fire_home}-
        {trade.score_at_fire_away} · {trade.leading_side} leads
      </div>
      <div className="text-xs text-gray-300 mt-1">
        {trade.contracts} contracts @ {trade.contract_price_cents}¢ · €
        {formatEuro(cost_cents / 100)} cost ·{" "}
        <span className={pnlClass}>
          {pnlSign}€{formatEuro(Math.abs(trade.pnl_cents) / 100)}
        </span>{" "}
        · capital €{formatEuro(trade.capital_after_cents / 100)}
      </div>
    </div>
  );
}

export default function BacktestPage() {
  const [authed, setAuthed] = useState<boolean | null>(null);
  const [selectedSport, setSelectedSport] = useState<string>(
    SPORTS[0]?.value ?? "football",
  );
  const initialLeagueKey = useMemo(() => {
    const initial = LEAGUES.find(
      (l) => l.sport === (SPORTS[0]?.value ?? "football"),
    );
    return initial?.key ?? LEAGUES[0]?.key ?? "";
  }, []);
  const [selectedKey, setSelectedKey] = useState<string>(initialLeagueKey);
  const [strategies, setStrategies] = useState<ApiStrategy[]>([]);
  const [selectedStrategy, setSelectedStrategy] = useState<string>(CUSTOM_KEY);
  const [triggers, setTriggers] = useState<Trigger[]>(() => [
    defaultTriggerForSport(SPORTS[0]?.value ?? "football"),
  ]);
  const [initialCapital, setInitialCapital] = useState(1000);
  const [betFractionPct, setBetFractionPct] = useState(2);
  const [contractPriceCents, setContractPriceCents] = useState(97);

  useEffect(() => {
    checkAuth().then((ok) => {
      if (!ok) window.location.href = "/";
      else setAuthed(true);
    });
  }, []);

  useEffect(() => {
    fetch("/api/strategies", { cache: "no-store" })
      .then((r) => r.json())
      .then((data: { strategies: ApiStrategy[] }) => {
        setStrategies(data.strategies);
      })
      .catch(() => {
        // Strategies unreachable — Custom mode still works.
      });
  }, []);

  // Leagues filtered to the page-level Sport. Renders the League dropdown
  // and gates the runBacktest selection.
  const leaguesForSport = useMemo(
    () => LEAGUES.filter((l) => l.sport === selectedSport),
    [selectedSport],
  );

  const selected: LeagueOption | undefined = useMemo(
    () => leaguesForSport.find((l) => l.key === selectedKey),
    [leaguesForSport, selectedKey],
  );

  // Strategies filtered to the page-level Sport. Hidden entirely when a
  // strategy has any non-matching trigger (no graying).
  const strategiesForSport = useMemo(
    () => strategies.filter((s) => strategyMatchesSport(s, selectedSport)),
    [strategies, selectedSport],
  );

  function handleSportChange(sport: string) {
    setSelectedSport(sport);
    // Reset Strategy to Custom and replace triggers with one default for the
    // new sport. Filter League list and auto-pick first match.
    setSelectedStrategy(CUSTOM_KEY);
    setTriggers([defaultTriggerForSport(sport)]);
    const firstMatchingLeague = LEAGUES.find((l) => l.sport === sport);
    if (firstMatchingLeague) {
      setSelectedKey(firstMatchingLeague.key);
    }
  }

  function updateTrigger(idx: number, patch: Partial<Trigger>) {
    setSelectedStrategy(CUSTOM_KEY);
    setTriggers((prev) =>
      prev.map((t, i) => (i === idx ? { ...t, ...patch } : t)),
    );
  }

  function addTrigger() {
    setSelectedStrategy(CUSTOM_KEY);
    setTriggers((prev) => [...prev, defaultTriggerForSport(selectedSport)]);
  }

  function removeTrigger(idx: number) {
    if (!window.confirm("Delete this trigger?")) return;
    setSelectedStrategy(CUSTOM_KEY);
    setTriggers((prev) => prev.filter((_, i) => i !== idx));
  }

  function handleStrategyChange(name: string) {
    if (name === CUSTOM_KEY) {
      setSelectedStrategy(CUSTOM_KEY);
      return;
    }
    const strat = strategies.find((s) => s.name === name);
    if (!strat) return;
    setSelectedStrategy(name);
    setTriggers(strat.triggers.map((t) => ({ ...t })));
  }

  const result = useMemo(
    () =>
      selected
        ? runBacktest(
            selected.data,
            {
              triggers,
              initial_capital: initialCapital,
              bet_fraction: betFractionPct / 100,
              contract_price_cents: contractPriceCents,
            },
            selected.sport,
          )
        : null,
    [selected, triggers, initialCapital, betFractionPct, contractPriceCents],
  );

  if (!authed) return <div className="min-h-screen bg-black" />;

  const selectedDescription =
    selectedStrategy !== CUSTOM_KEY
      ? strategies.find((s) => s.name === selectedStrategy)?.description
      : undefined;

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
            <label className="block text-sm text-gray-300 mb-1">Sport</label>
            <select
              value={selectedSport}
              onChange={(e) => handleSportChange(e.target.value)}
              className="w-full bg-black border border-gray-700 rounded px-2 py-1"
            >
              {SPORTS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">League</label>
            {leaguesForSport.length === 0 ? (
              <select
                disabled
                className="w-full bg-black border border-gray-700 rounded px-2 py-1"
              >
                <option>No leagues for {selectedSport}</option>
              </select>
            ) : (
              <select
                value={selectedKey}
                onChange={(e) => setSelectedKey(e.target.value)}
                className="w-full bg-black border border-gray-700 rounded px-2 py-1"
              >
                {leaguesForSport.map((l) => (
                  <option key={l.key} value={l.key}>
                    {l.parsed.label}
                  </option>
                ))}
              </select>
            )}
          </div>
          <div>
            <label className="block text-sm text-gray-300 mb-1">Strategy</label>
            <select
              value={selectedStrategy}
              onChange={(e) => handleStrategyChange(e.target.value)}
              className="w-full bg-black border border-gray-700 rounded px-2 py-1"
            >
              <option value={CUSTOM_KEY}>{CUSTOM_LABEL}</option>
              {strategiesForSport.map((s) => (
                <option key={s.name} value={s.name}>
                  {s.name}
                </option>
              ))}
            </select>
            {selectedDescription && (
              <p className="mt-1 text-xs text-gray-400">
                {selectedDescription}
              </p>
            )}
          </div>
          <div className="border-t border-gray-800 pt-3 space-y-3">
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                Initial capital (€)
              </label>
              <input
                type="number"
                min={1}
                step={1}
                value={initialCapital}
                onChange={(e) =>
                  setInitialCapital(Math.max(1, Number(e.target.value) || 0))
                }
                className="w-full bg-black border border-gray-700 rounded px-2 py-1"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                Bet size (% of current capital)
              </label>
              <input
                type="number"
                min={0.1}
                max={100}
                step={0.1}
                value={betFractionPct}
                onChange={(e) =>
                  setBetFractionPct(
                    Math.min(100, Math.max(0.1, Number(e.target.value) || 0.1)),
                  )
                }
                className="w-full bg-black border border-gray-700 rounded px-2 py-1"
              />
            </div>
            <div>
              <label className="block text-sm text-gray-300 mb-1">
                Contract price (cents): {contractPriceCents}
              </label>
              <input
                type="range"
                min={50}
                max={99}
                step={1}
                value={contractPriceCents}
                onChange={(e) => setContractPriceCents(Number(e.target.value))}
                className="w-full"
              />
              <p className="text-xs text-gray-500 mt-1">
                Yield per win: {100 - contractPriceCents} cents per contract (€
                {formatEuro((100 - contractPriceCents) / 100)})
              </p>
            </div>
          </div>
          <div className="border-t border-gray-800 pt-3 space-y-3">
            <div className="text-sm text-gray-300">Triggers</div>
            {triggers.map((trigger, idx) => (
              <div
                key={idx}
                className="p-3 rounded border border-gray-600 space-y-2"
              >
                <div>
                  <label className="block text-xs text-gray-300 mb-1">
                    Min minute: {trigger.min_minute ?? "(any)"}
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={90}
                    value={trigger.min_minute ?? 75}
                    onChange={(e) =>
                      updateTrigger(idx, {
                        min_minute: Number(e.target.value),
                      })
                    }
                    className="w-full"
                  />
                </div>
                <div>
                  <label className="block text-xs text-gray-300 mb-1">
                    Min lead: {trigger.min_lead ?? "(any)"}
                  </label>
                  <input
                    type="range"
                    min={1}
                    max={5}
                    value={trigger.min_lead ?? 2}
                    onChange={(e) =>
                      updateTrigger(idx, {
                        min_lead: Number(e.target.value),
                      })
                    }
                    className="w-full"
                  />
                </div>
                {(trigger.min_yes_price !== undefined ||
                  trigger.max_yes_price !== undefined) && (
                  <p className="text-xs text-gray-400">
                    Live trading:{" "}
                    {trigger.min_yes_price !== undefined
                      ? `${trigger.min_yes_price}¢`
                      : "—"}
                    –
                    {trigger.max_yes_price !== undefined
                      ? `${trigger.max_yes_price}¢`
                      : "—"}{" "}
                    (info only — backtest uses contract price slider)
                  </p>
                )}
                {triggers.length > 1 && (
                  <button
                    type="button"
                    onClick={() => removeTrigger(idx)}
                    className="text-xs text-red-400 hover:text-red-300"
                  >
                    Remove trigger
                  </button>
                )}
              </div>
            ))}
            <div className="border-t border-gray-700 pt-3">
              <button
                type="button"
                onClick={addTrigger}
                className="text-sm text-blue-400 hover:text-blue-300"
              >
                + Add trigger
              </button>
            </div>
          </div>
          <p className="text-xs text-gray-500">
            Triggers fire on the first goal where ALL conditions in any trigger
            are met (OR-of-AND, first-fire-wins per match). Stoppage time is
            ignored. All triggers inherit the page-level Sport.
          </p>
        </aside>
        <main className="space-y-6">
          {leaguesForSport.length === 0 ? (
            <div className="bg-gray-900 rounded p-6 text-sm text-gray-400">
              <p className="font-semibold text-white mb-2">
                No league data available for {selectedSport}
              </p>
              <p>
                Add a JSON file under{" "}
                <code className="text-blue-400">resources/</code> and a
                corresponding entry in{" "}
                <code className="text-blue-400">
                  dashboard/app/backtest/seasons.ts
                </code>
                .
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
                  <SummaryCard
                    label="Final capital"
                    value={`€${formatEuro(result.summary.final_capital_cents / 100)}`}
                    tone={
                      result.summary.final_capital_cents >=
                      result.summary.initial_capital_cents
                        ? "positive"
                        : "negative"
                    }
                  />
                  <SummaryCard
                    label="Gain"
                    value={`${result.summary.gain_pct >= 0 ? "+" : ""}${result.summary.gain_pct.toFixed(2)}%`}
                    tone={
                      result.summary.gain_pct >= 0 ? "positive" : "negative"
                    }
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
