import { describe, expect, it } from "vitest";
import {
  accountValueSteps,
  pnlByPrice,
  pnlByTime,
  priceBins,
  timeBins,
} from "./chart-data";

describe("priceBins", () => {
  it("counts a winning trade in its price bin", () => {
    const bins = priceBins([{ yes_price: 94, pnl_cents: 6 }]);

    expect(bins).toHaveLength(15); // 85..99, 1¢ each
    expect(bins[0]).toEqual({ price: 85, wins: 0, losses: 0 });
    expect(bins.find((b) => b.price === 94)).toEqual({
      price: 94,
      wins: 1,
      losses: 0,
    });
  });

  it("drops trades below 85¢, clamps 100¢ into the top bin", () => {
    const bins = priceBins([
      { yes_price: 84, pnl_cents: 10 },
      { yes_price: 100, pnl_cents: -50 },
    ]);

    expect(bins.reduce((s, b) => s + b.wins, 0)).toBe(0);
    expect(bins[14]).toEqual({ price: 99, wins: 0, losses: 1 });
  });

  it("sums P&L per price bin", () => {
    const bins = pnlByPrice([
      { yes_price: 94, pnl_cents: 6 },
      { yes_price: 94.5, pnl_cents: 6 },
      { yes_price: 91, pnl_cents: -94 },
    ]);

    expect(bins).toHaveLength(15);
    expect(bins.find((b) => b.price === 94)).toEqual({ price: 94, pnl: 12 });
    expect(bins.find((b) => b.price === 91)).toEqual({ price: 91, pnl: -94 });
  });

  it("counts zero P&L as a win", () => {
    const bins = priceBins([{ yes_price: 90, pnl_cents: 0 }]);

    expect(bins.find((b) => b.price === 90)).toEqual({
      price: 90,
      wins: 1,
      losses: 0,
    });
  });
});

describe("timeBins", () => {
  it("orders bins from 10 minutes left down to the buzzer", () => {
    const bins = timeBins([
      { clock_seconds: 600, pnl_cents: 5 }, // 10:00 left
      { clock_seconds: 130, pnl_cents: -95 }, // 2:10 left
      { clock_seconds: 30, pnl_cents: 5 }, // 0:30 left
    ]);

    expect(bins).toHaveLength(10);
    expect(bins[0]).toEqual({ minutesLeft: 10, wins: 1, losses: 0 });
    expect(bins.find((b) => b.minutesLeft === 3)).toEqual({
      minutesLeft: 3,
      wins: 0,
      losses: 1,
    });
    expect(bins[9]).toEqual({ minutesLeft: 1, wins: 1, losses: 0 });
  });
});

describe("accountValueSteps", () => {
  it("walks balance from derived start to now, one step per trade", () => {
    // Unsorted on purpose — module must order by placed_at
    const { steps, windowStartBalance, hiddenCount } = accountValueSteps(
      [
        { placed_at: "2026-07-05T16:00:00", pnl_cents: -94 },
        { placed_at: "2026-07-05T14:30:00", pnl_cents: 6 },
      ],
      10000,
      "trade",
    );

    expect(windowStartBalance).toBe(10088); // 10000 − (6 − 94)
    expect(hiddenCount).toBe(0);
    expect(steps).toEqual([
      { label: "Start", value: 10088, periodPnl: 0, kind: "start" },
      { label: "7/5 14:30", value: 10094, periodPnl: 6, kind: "bucket" },
      { label: "7/5 16:00", value: 10000, periodPnl: -94, kind: "bucket" },
      { label: "Now", value: 10000, periodPnl: 0, kind: "now" },
    ]);
  });
});

describe("accountValueSteps bucketing", () => {
  it("merges same-day trades into one step in day mode", () => {
    const { steps } = accountValueSteps(
      [
        { placed_at: "2026-07-05T10:00:00", pnl_cents: 6 },
        { placed_at: "2026-07-05T18:00:00", pnl_cents: 6 },
        { placed_at: "2026-07-06T09:00:00", pnl_cents: -94 },
      ],
      10000,
      "day",
    );

    expect(steps.filter((s) => s.kind === "bucket")).toEqual([
      { label: "7/5", value: 10094, periodPnl: 12, kind: "bucket" },
      { label: "7/6", value: 10000, periodPnl: -94, kind: "bucket" },
    ]);
  });

  it("folds buckets beyond the last 20 into the start balance", () => {
    const trades = Array.from({ length: 25 }, (_, i) => ({
      placed_at: `2026-06-${String(i + 1).padStart(2, "0")}T12:00:00`,
      pnl_cents: 10,
    }));

    const { steps, windowStartBalance, hiddenCount } = accountValueSteps(
      trades,
      10250,
      "day",
    );

    expect(hiddenCount).toBe(5);
    expect(windowStartBalance).toBe(10050); // 10000 start + 5 hidden × 10
    expect(steps.filter((s) => s.kind === "bucket")).toHaveLength(20);
    expect(steps[1]).toEqual({
      label: "6/6",
      value: 10060,
      periodPnl: 10,
      kind: "bucket",
    });
  });

  it("groups a Sunday trade into the prior Monday's week", () => {
    const { steps } = accountValueSteps(
      [
        { placed_at: "2026-07-01T12:00:00", pnl_cents: 5 }, // Wed
        { placed_at: "2026-07-05T12:00:00", pnl_cents: 5 }, // Sun, same week (Mon 6/29)
        { placed_at: "2026-07-06T12:00:00", pnl_cents: 5 }, // Mon, next week
      ],
      10015,
      "week",
    );

    expect(steps.filter((s) => s.kind === "bucket")).toEqual([
      { label: "6/29", value: 10010, periodPnl: 10, kind: "bucket" },
      { label: "7/6", value: 10015, periodPnl: 5, kind: "bucket" },
    ]);
  });
});

describe("pnlByTime", () => {
  it("sums P&L per minute-remaining bin", () => {
    const bins = pnlByTime([
      { clock_seconds: 90, pnl_cents: 6 },
      { clock_seconds: 100, pnl_cents: -94 },
    ]);

    expect(bins).toHaveLength(10);
    expect(bins.find((b) => b.minutesLeft === 2)).toEqual({
      minutesLeft: 2,
      pnl: -88,
    });
  });
});
