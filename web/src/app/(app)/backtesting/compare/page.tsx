"use client";

import { useEffect, useMemo, useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { ClientOnly } from "@/components/client-only";
import AnimatedDownloadButton from "@/components/ui/download-hover-button";
import { apiGet } from "@/lib/api";

type MetricRow = {
  sizing_mode: string;
  cumulative_return: number;
  sharpe: number;
  max_drawdown: number;
  total_cost_paid: number;
  trade_count: number;
};

type Pt = { ts: string; equity?: number };

type CompareResp = {
  metrics: MetricRow[];
  equity_curves: Record<string, Pt[]>;
  benchmark_curve: Pt[];
  bars: number;
};

function pct(n: number) {
  if (!Number.isFinite(n)) return "—";
  return `${(n * 100).toFixed(2)}%`;
}

export default function BacktestComparePage() {
  const [data, setData] = useState<CompareResp | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [running, setRunning] = useState(false);
  const [buyTh, setBuyTh] = useState(0.08);
  const [sellTh, setSellTh] = useState(-0.08);
  const [feeBps, setFeeBps] = useState(0);
  const [slipBps, setSlipBps] = useState(0);

  const run = async () => {
    setRunning(true);
    setErr(null);
    try {
      const qs = new URLSearchParams();
      qs.set("buy_threshold", String(buyTh));
      qs.set("sell_threshold", String(sellTh));
      qs.set("fee_bps", String(feeBps));
      qs.set("slippage_bps", String(slipBps));
      const r = await apiGet<CompareResp>(`/api/backtest/compare?${qs.toString()}`, { timeoutMs: 180_000 });
      setData(r);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setRunning(false);
    }
  };

  useEffect(() => {
    void run();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const chartData = useMemo(() => {
    if (!data) return [];
    const modes = Object.keys(data.equity_curves);
    const byTs = new Map<string, Record<string, number>>();
    for (const m of modes) {
      for (const p of data.equity_curves[m] ?? []) {
        const row = byTs.get(p.ts) ?? {};
        row[m] = p.equity ?? 0;
        byTs.set(p.ts, row);
      }
    }
    for (const p of data.benchmark_curve ?? []) {
      const row = byTs.get(p.ts) ?? {};
      row.benchmark = p.equity ?? 0;
      byTs.set(p.ts, row);
    }
    return Array.from(byTs.entries())
      .sort((a, b) => (a[0] < b[0] ? -1 : 1))
      .map(([ts, row]) => ({ ts: ts.slice(0, 10), ...row }));
  }, [data]);

  if (err) return <p className="text-destructive">{err}</p>;
  if (!data) return <p className="text-muted-foreground">Loading comparison…</p>;

  return (
    <div>
      <div className="mb-6 rounded-xl border border-border bg-card p-6">
        <h1 className="text-2xl font-semibold tracking-tight text-white">Backtesting · Strategy comparison</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Compare sizing modes side by side using the same thresholds, fees, and slippage.
        </p>
        <div className="mt-4 flex flex-col gap-3 rounded-lg border border-border/60 bg-background/30 p-4 sm:flex-row sm:items-end sm:justify-between">
          <div className="grid gap-3 sm:grid-cols-4">
            <label className="text-xs text-muted-foreground">
              Buy threshold (score)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={buyTh}
                step={0.01}
                onChange={(e) => setBuyTh(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Sell threshold (score)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={sellTh}
                step={0.01}
                onChange={(e) => setSellTh(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Fee (bps)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={feeBps}
                min={0}
                step={1}
                onChange={(e) => setFeeBps(Number(e.target.value))}
              />
            </label>
            <label className="text-xs text-muted-foreground">
              Slippage (bps)
              <input
                type="number"
                className="mt-1 w-full rounded-md border border-border bg-background px-2 py-2 text-sm text-foreground"
                value={slipBps}
                min={0}
                step={1}
                onChange={(e) => setSlipBps(Number(e.target.value))}
              />
            </label>
          </div>
          <AnimatedDownloadButton
            variant="primary"
            label="Run comparison"
            expandedWidth={240}
            pending={running}
            disabled={running}
            onClick={() => void run()}
          />
        </div>
        {running ? (
          <div className="mt-3 overflow-hidden rounded-md border border-border/60 bg-background/40">
            <div className="relative h-2 w-full">
              <div className="absolute inset-0 bg-muted/30" />
              <div className="btc-indeterminate-bar absolute inset-y-0 left-0 w-1/3 bg-foreground/80" />
            </div>
            <div className="px-3 py-2 text-xs text-muted-foreground">Running comparison…</div>
          </div>
        ) : null}
        {err ? <p className="mt-3 text-sm text-destructive">{err}</p> : null}
      </div>

      <div className="mb-8 rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-white">Metrics</h2>
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted-foreground">
              <tr>
                <th className="py-2 pr-3">Sizing</th>
                <th className="py-2 pr-3">Cumulative</th>
                <th className="py-2 pr-3">Sharpe</th>
                <th className="py-2 pr-3">Max DD</th>
                <th className="py-2 pr-3">Trades</th>
                <th className="py-2">Total cost ($)</th>
              </tr>
            </thead>
            <tbody>
              {data.metrics.map((r) => (
                <tr key={r.sizing_mode} className="border-t border-border/60">
                  <td className="py-2 pr-3 font-mono text-foreground">{r.sizing_mode}</td>
                  <td className="py-2 pr-3 font-mono">{pct(r.cumulative_return)}</td>
                  <td className="py-2 pr-3 font-mono">{r.sharpe.toFixed(3)}</td>
                  <td className="py-2 pr-3 font-mono">{pct(r.max_drawdown)}</td>
                  <td className="py-2 pr-3 font-mono">{r.trade_count}</td>
                  <td className="py-2 font-mono">{Number(r.total_cost_paid).toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="rounded-xl border border-border bg-card p-6">
        <h2 className="text-lg font-semibold text-white">Equity curves</h2>
        <p className="mt-1 text-xs text-muted-foreground">
          Strategy lines are different sizing modes; benchmark is buy-and-hold.
        </p>
        <ClientOnly fallback={<div className="mt-4 h-[320px] animate-pulse rounded-lg bg-muted/30" />}>
          <div className="mt-4 h-[320px]">
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
                <CartesianGrid stroke="var(--border)" strokeDasharray="3 3" />
                <XAxis dataKey="ts" tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} />
                <YAxis tick={{ fill: "var(--muted-foreground)", fontSize: 11 }} width={60} />
                <Tooltip
                  contentStyle={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    borderRadius: "8px",
                    fontSize: "12px",
                  }}
                />
                <Line type="monotone" dataKey="fixed" stroke="var(--foreground)" strokeWidth={2} dot={false} />
                <Line
                  type="monotone"
                  dataKey="confidence"
                  stroke="#a1a1aa"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="confidence_vol"
                  stroke="#60a5fa"
                  strokeWidth={1.5}
                  dot={false}
                />
                <Line
                  type="monotone"
                  dataKey="benchmark"
                  stroke="var(--muted-foreground)"
                  strokeDasharray="4 4"
                  strokeWidth={1.5}
                  dot={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </div>
        </ClientOnly>
      </div>
    </div>
  );
}

