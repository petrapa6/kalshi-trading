export type SettledTrade = {
  yes_price: number;
  pnl_cents: number;
};

const MIN_PRICE = 85;
const MAX_PRICE = 100;
const NUM_PRICE_BINS = MAX_PRICE - MIN_PRICE;

export type PriceBin = { price: number; wins: number; losses: number };
export type PricePnlBin = { price: number; pnl: number };

function priceBinIndex(yesPrice: number): number | null {
  const idx = Math.floor(yesPrice - MIN_PRICE);
  if (idx < 0) return null;
  return Math.min(idx, NUM_PRICE_BINS - 1);
}

export function priceBins(trades: SettledTrade[]): PriceBin[] {
  const bins: PriceBin[] = Array.from({ length: NUM_PRICE_BINS }, (_, i) => ({
    price: MIN_PRICE + i,
    wins: 0,
    losses: 0,
  }));
  for (const t of trades) {
    const idx = priceBinIndex(t.yes_price);
    if (idx === null) continue;
    if (t.pnl_cents >= 0) bins[idx].wins++;
    else bins[idx].losses++;
  }
  return bins;
}

export type ClockTrade = {
  clock_seconds: number;
  pnl_cents: number;
};

const NUM_TIME_BINS = 10;

export type TimeBin = { minutesLeft: number; wins: number; losses: number };

function timeBinIndex(clockSeconds: number): number {
  const minsRemaining = Math.min(
    Math.floor(clockSeconds / 60),
    NUM_TIME_BINS - 1,
  );
  return NUM_TIME_BINS - 1 - minsRemaining;
}

export function timeBins(trades: ClockTrade[]): TimeBin[] {
  const bins: TimeBin[] = Array.from({ length: NUM_TIME_BINS }, (_, i) => ({
    minutesLeft: NUM_TIME_BINS - i,
    wins: 0,
    losses: 0,
  }));
  for (const t of trades) {
    const bin = bins[timeBinIndex(t.clock_seconds)];
    if (t.pnl_cents >= 0) bin.wins++;
    else bin.losses++;
  }
  return bins;
}

export type PlacedTrade = {
  placed_at: string;
  pnl_cents: number;
};

export type ViewMode = "trade" | "day" | "week" | "month";

export type AccountStep = {
  label: string;
  value: number;
  periodPnl: number;
  kind: "start" | "bucket" | "now";
};

const WINDOW = 20;

function startOfWeek(d: Date): Date {
  const tmp = new Date(d);
  tmp.setHours(0, 0, 0, 0);
  tmp.setDate(tmp.getDate() - (tmp.getDay() === 0 ? 6 : tmp.getDay() - 1));
  return tmp;
}

function bucketKey(d: Date, mode: ViewMode): string {
  if (mode === "day")
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
  if (mode === "week") {
    const w = startOfWeek(d);
    return `${w.getFullYear()}-W${String(w.getMonth() + 1).padStart(2, "0")}-${String(w.getDate()).padStart(2, "0")}`;
  }
  if (mode === "month")
    return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
  return d.toISOString(); // "trade": unique per trade
}

function bucketLabel(d: Date, mode: ViewMode): string {
  if (mode === "trade")
    return `${d.getMonth() + 1}/${d.getDate()} ${d.getHours()}:${d.getMinutes().toString().padStart(2, "0")}`;
  if (mode === "day") return `${d.getMonth() + 1}/${d.getDate()}`;
  if (mode === "week") {
    const w = startOfWeek(d);
    return `${w.getMonth() + 1}/${w.getDate()}`;
  }
  return d.toLocaleString("default", { month: "short", year: "2-digit" });
}

export function accountValueSteps(
  trades: PlacedTrade[],
  totalNowCents: number,
  mode: ViewMode,
): {
  steps: AccountStep[];
  windowStartBalance: number;
  hiddenCount: number;
} {
  const sorted = [...trades].sort(
    (a, b) => new Date(a.placed_at).getTime() - new Date(b.placed_at).getTime(),
  );

  const totalPnl = sorted.reduce((s, t) => s + t.pnl_cents, 0);
  const startingBalance = totalNowCents - totalPnl;

  const bucketMap = new Map<string, { pnl: number; date: Date }>();
  for (const t of sorted) {
    const d = new Date(t.placed_at);
    const key = bucketKey(d, mode);
    if (!bucketMap.has(key)) bucketMap.set(key, { pnl: 0, date: d });
    bucketMap.get(key)!.pnl += t.pnl_cents;
  }
  const allBuckets = Array.from(bucketMap.values());

  const hidden = allBuckets.length > WINDOW ? allBuckets.slice(0, -WINDOW) : [];
  const visible =
    allBuckets.length > WINDOW ? allBuckets.slice(-WINDOW) : allBuckets;
  const windowStartBalance =
    startingBalance + hidden.reduce((s, b) => s + b.pnl, 0);

  const steps: AccountStep[] = [
    { label: "Start", value: windowStartBalance, periodPnl: 0, kind: "start" },
  ];
  let running = windowStartBalance;
  for (const { pnl, date } of visible) {
    running += pnl;
    steps.push({
      label: bucketLabel(date, mode),
      value: running,
      periodPnl: pnl,
      kind: "bucket",
    });
  }
  steps.push({ label: "Now", value: totalNowCents, periodPnl: 0, kind: "now" });

  return { steps, windowStartBalance, hiddenCount: hidden.length };
}

export type TimePnlBin = { minutesLeft: number; pnl: number };

export function pnlByTime(trades: ClockTrade[]): TimePnlBin[] {
  const bins: TimePnlBin[] = Array.from({ length: NUM_TIME_BINS }, (_, i) => ({
    minutesLeft: NUM_TIME_BINS - i,
    pnl: 0,
  }));
  for (const t of trades) {
    bins[timeBinIndex(t.clock_seconds)].pnl += t.pnl_cents;
  }
  return bins;
}

export type StrategyTrade = {
  strategy_name: string | null;
  settled_at: string | null;
  pnl_cents: number;
};

export type PnlPoint = { x: number; y: number };
export type StrategyPnlSeries = { strategy: string; points: PnlPoint[] };

// One cumulative-P&L series per strategy over settled trades. Points are
// sorted by settle time (x = epoch ms) with a running sum of pnl_cents.
// Rows missing a strategy or a settle time can't be placed and are dropped.
// Series are ordered by strategy name for a stable legend; "main" is just
// another line.
export function cumulativePnlByStrategy(
  trades: StrategyTrade[],
): StrategyPnlSeries[] {
  const byStrategy = new Map<string, { x: number; pnl: number }[]>();
  for (const t of trades) {
    if (!t.strategy_name || !t.settled_at) continue;
    const list = byStrategy.get(t.strategy_name) ?? [];
    list.push({ x: new Date(t.settled_at).getTime(), pnl: t.pnl_cents });
    byStrategy.set(t.strategy_name, list);
  }

  return Array.from(byStrategy.keys())
    .sort()
    .map((strategy) => {
      const rows = byStrategy.get(strategy)!.sort((a, b) => a.x - b.x);
      let running = 0;
      const points = rows.map((r) => {
        running += r.pnl;
        return { x: r.x, y: running };
      });
      return { strategy, points };
    });
}

export function pnlByPrice(trades: SettledTrade[]): PricePnlBin[] {
  const bins: PricePnlBin[] = Array.from(
    { length: NUM_PRICE_BINS },
    (_, i) => ({ price: MIN_PRICE + i, pnl: 0 }),
  );
  for (const t of trades) {
    const idx = priceBinIndex(t.yes_price);
    if (idx === null) continue;
    bins[idx].pnl += t.pnl_cents;
  }
  return bins;
}
